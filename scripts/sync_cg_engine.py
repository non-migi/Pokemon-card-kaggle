#!/usr/bin/env python3
"""Compare the bundled cg native libraries with the official Kaggle files.

The default mode is read-only and exits with status 1 when any bundled file is
missing or differs.  ``--apply`` stages every download first, then installs only
the differing files with atomic per-file replacements.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Iterable, TextIO


COMPETITION = "pokemon-tcg-ai-battle"
REMOTE_DIRECTORY = "sample_submission/sample_submission/cg"
NATIVE_FILES = (
    "libcg.dylib",
    "libcg.so",
    "libcg-arm64.so",
    "cg.dll",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIRECTORY = REPOSITORY_ROOT / "src" / "cg"

Runner = Callable[..., subprocess.CompletedProcess]
ReplaceFunction = Callable[[Path, Path], object]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_one(name: str, destination: Path, runner: Runner) -> Path:
    remote_path = f"{REMOTE_DIRECTORY}/{name}"
    command = [
        "kaggle",
        "competitions",
        "download",
        COMPETITION,
        "--file",
        remote_path,
        "--path",
        str(destination),
        "--force",
        "--quiet",
    ]
    runner(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Current Kaggle CLI uses the response URL's basename.  The recursive
    # fallback also keeps this usable with mocked or future path-preserving CLIs.
    candidates = [path for path in destination.rglob(name) if path.is_file()]
    if len(candidates) != 1:
        raise RuntimeError(
            f"downloaded {remote_path!r}, expected one {name!r} file, "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _stage_and_replace(
    downloaded: dict[str, Path],
    names: Iterable[str],
    target_directory: Path,
    replace_fn: ReplaceFunction,
) -> None:
    """Fully stage files on the target filesystem before replacing any file."""
    target_directory.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name in names:
            destination = target_directory / name
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{name}.", suffix=".tmp", dir=target_directory
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    with downloaded[name].open("rb") as source:
                        shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
                mode_source = destination if destination.exists() else downloaded[name]
                os.chmod(temporary_path, mode_source.stat().st_mode & 0o777)
            except BaseException:
                temporary_path.unlink(missing_ok=True)
                raise
            staged.append((temporary_path, destination))

        for temporary_path, destination in staged:
            replace_fn(temporary_path, destination)
    finally:
        for temporary_path, _ in staged:
            temporary_path.unlink(missing_ok=True)


def sync_cg_engine(
    target_directory: Path = DEFAULT_TARGET_DIRECTORY,
    *,
    apply: bool = False,
    runner: Runner | None = None,
    replace_fn: ReplaceFunction | None = None,
    temporary_directory_factory: Callable[..., object] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Download, compare, and optionally install the official native files."""
    runner = subprocess.run if runner is None else runner
    replace_fn = os.replace if replace_fn is None else replace_fn
    if temporary_directory_factory is None:
        temporary_directory_factory = tempfile.TemporaryDirectory
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    target_directory = Path(target_directory)

    try:
        with temporary_directory_factory(prefix="ptcg-cg-sync-") as temporary_name:
            download_directory = Path(temporary_name)
            downloaded = {
                name: _download_one(name, download_directory, runner)
                for name in NATIVE_FILES
            }

            differing: list[str] = []
            for name in NATIVE_FILES:
                official_hash = sha256_file(downloaded[name])
                local_path = target_directory / name
                local_hash = sha256_file(local_path) if local_path.is_file() else None
                status = "MATCH" if local_hash == official_hash else "DIFF"
                if status == "DIFF":
                    differing.append(name)
                print(
                    f"{status} {name} "
                    f"local={local_hash or 'MISSING'} official={official_hash}",
                    file=stdout,
                )

            if not apply:
                return 1 if differing else 0

            if differing:
                _stage_and_replace(
                    downloaded,
                    differing,
                    target_directory,
                    replace_fn,
                )
                for name in differing:
                    print(f"UPDATED {name}", file=stdout)
            else:
                print("All native cg files are already current.", file=stdout)
            return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        print(f"ERROR: cg engine sync failed: {detail}", file=stderr)
        return 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="replace each differing file atomically after every download succeeds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return sync_cg_engine(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
