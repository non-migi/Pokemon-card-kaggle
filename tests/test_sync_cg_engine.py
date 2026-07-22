import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import sync_cg_engine as sync


def payloads(prefix=b"official"):
    return {name: prefix + b":" + name.encode() for name in sync.NATIVE_FILES}


class FakeKaggleRunner:
    def __init__(self, remote_payloads, fail_on=None, preserve_path=False):
        self.remote_payloads = remote_payloads
        self.fail_on = fail_on
        self.preserve_path = preserve_path
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append((list(command), dict(kwargs)))
        remote_path = command[command.index("--file") + 1]
        name = Path(remote_path).name
        if name == self.fail_on:
            raise subprocess.CalledProcessError(
                1, command, stderr=f"could not download {name}"
            )
        destination = Path(command[command.index("--path") + 1])
        output = destination / (remote_path if self.preserve_path else name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(self.remote_payloads[name])
        return subprocess.CompletedProcess(command, 0, "", "")


class SyncCgEngineTests(unittest.TestCase):
    def make_target(self, root, local_payloads):
        target = Path(root) / "src" / "cg"
        target.mkdir(parents=True)
        for name, content in local_payloads.items():
            (target / name).write_bytes(content)
        return target

    def test_read_only_match_downloads_only_the_four_native_files(self):
        remote = payloads()
        runner = FakeKaggleRunner(remote, preserve_path=True)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            target = self.make_target(root, remote)
            before = {name: (target / name).read_bytes() for name in sync.NATIVE_FILES}

            result = sync.sync_cg_engine(target, runner=runner, stdout=output)

            self.assertEqual(0, result)
            self.assertEqual(
                before,
                {name: (target / name).read_bytes() for name in sync.NATIVE_FILES},
            )

        requested = [
            command[command.index("--file") + 1]
            for command, _ in runner.commands
        ]
        self.assertEqual(
            [f"{sync.REMOTE_DIRECTORY}/{name}" for name in sync.NATIVE_FILES],
            requested,
        )
        self.assertNotIn("EffectProc.h", repr(runner.commands))
        self.assertEqual(4, output.getvalue().count("MATCH "))
        for _, kwargs in runner.commands:
            self.assertTrue(kwargs["check"])

    def test_read_only_difference_exits_nonzero_without_writing(self):
        remote = payloads()
        local = dict(remote)
        local["libcg.so"] = b"stale"
        del local["cg.dll"]
        runner = FakeKaggleRunner(remote)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            target = self.make_target(root, local)

            result = sync.sync_cg_engine(target, runner=runner, stdout=output)

            self.assertEqual(1, result)
            self.assertEqual(b"stale", (target / "libcg.so").read_bytes())
            self.assertFalse((target / "cg.dll").exists())
        self.assertIn("DIFF libcg.so", output.getvalue())
        self.assertIn("DIFF cg.dll local=MISSING", output.getvalue())

    def test_apply_atomically_replaces_only_differing_files(self):
        remote = payloads()
        local = {name: b"stale:" + name.encode() for name in sync.NATIVE_FILES}
        runner = FakeKaggleRunner(remote)
        replacements = []

        def recorded_replace(source, destination):
            replacements.append((Path(source), Path(destination)))
            os.replace(source, destination)

        with tempfile.TemporaryDirectory() as root:
            target = self.make_target(root, local)
            result = sync.sync_cg_engine(
                target,
                apply=True,
                runner=runner,
                replace_fn=recorded_replace,
                stdout=io.StringIO(),
            )

            self.assertEqual(0, result)
            for name in sync.NATIVE_FILES:
                self.assertEqual(remote[name], (target / name).read_bytes())
            self.assertEqual(
                [target / name for name in sync.NATIVE_FILES],
                [destination for _, destination in replacements],
            )
            self.assertTrue(all(source.parent == target for source, _ in replacements))

    def test_apply_download_failure_leaves_every_existing_file_unchanged(self):
        remote = payloads()
        local = {name: b"local:" + name.encode() for name in sync.NATIVE_FILES}
        runner = FakeKaggleRunner(remote, fail_on="libcg-arm64.so")
        replacements = []
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            target = self.make_target(root, local)
            before = {name: (target / name).read_bytes() for name in sync.NATIVE_FILES}

            result = sync.sync_cg_engine(
                target,
                apply=True,
                runner=runner,
                replace_fn=lambda source, destination: replacements.append(
                    (source, destination)
                ),
                stdout=io.StringIO(),
                stderr=errors,
            )

            self.assertEqual(2, result)
            self.assertEqual([], replacements)
            self.assertEqual(
                before,
                {name: (target / name).read_bytes() for name in sync.NATIVE_FILES},
            )
        self.assertIn("could not download libcg-arm64.so", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
