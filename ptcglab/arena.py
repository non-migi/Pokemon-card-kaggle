"""対戦アリーナ: エージェント同士のA/B対戦の唯一の実装。

- ビルド済みエージェントディレクトリ(main.pyを含む)または組み込み("random"/"first")をロード
- モジュール分離ロード(ptcg/cgをsys.modulesから追い出す — 共有すると「新vs新」事故になる)
- 先手後手を交互に入れ替え、並列実行、Wilson CI
- すべての結果を results/arena.jsonl に自動追記(測定の台帳)

使い方(ライブラリ):
    from ptcglab.arena import run_match_series
    r = run_match_series("build/v3.0g", "build/v3.0a", n=200, jobs=8, note="deck A/B")
"""

import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import multiprocessing
import os
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.connection import wait as wait_connections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "results", "arena.jsonl")
GAUNTLET_LEDGER = os.path.join(ROOT, "results", "gauntlet.jsonl")
DEFAULT_PAIR_TIMEOUT_SEC = 3600.0
PAIR_EXIT_GRACE_SEC = 0.5
PAIR_TERMINATE_GRACE_SEC = 1.0
PAIR_KILL_GRACE_SEC = 1.0

_RESULT_KEYS = frozenset({
    "a_seat", "reward", "score", "status_a", "status_b", "error_a", "error_b",
    "remaining_overage_sec_a", "remaining_overage_sec_b", "metrics_a", "metrics_b",
    "failures", "sec",
})

_worker_agents = {}


class ArenaRunError(RuntimeError):
    """対戦自体のERROR/INVALID/Noneを含み、証拠測定として採用できない。"""

    def __init__(self, message: str, record: dict):
        super().__init__(message)
        self.record = record


def _clear_agent_modules() -> None:
    for key in list(sys.modules):
        if key == "ptcg" or key.startswith("ptcg.") or key == "cg" or key.startswith("cg."):
            del sys.modules[key]


def load_agent(spec: str):
    """spec: 組み込み名("random"/"first") or エージェントディレクトリ or main.pyパス。"""
    if spec in ("random", "first"):
        return spec
    path = os.path.abspath(spec)
    if os.path.isdir(path):
        path = os.path.join(path, "main.py")
    dirp = os.path.dirname(path)
    sys.path.insert(0, dirp)
    try:
        name = f"agent_module_{hashlib.sha256(path.encode()).hexdigest()[:16]}"
        module_spec = importlib.util.spec_from_file_location(name, path)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"agentをロードできない: {path}")
        mod = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = mod
        module_spec.loader.exec_module(mod)
        algo = str(getattr(mod, "ALGO", ""))
        policy_module = getattr(mod, "policy", None)
        if "bc" in algo and not bool(getattr(policy_module, "ENABLED", False)):
            raise RuntimeError(f"{path}: BCモデルが有効でない(policy.ENABLED=False)")
        return mod.agent
    finally:
        # 重要: エージェントごとにptcg/cgを分離(共有するとA/Bが自己対戦になる)。
        _clear_agent_modules()
        try:
            sys.path.remove(dirp)
        except ValueError:
            pass


def _init_worker(spec_a: str, spec_b: str):
    import logging

    logging.disable(logging.WARNING)
    _worker_agents["a"] = load_agent(spec_a)
    _worker_agents["b"] = load_agent(spec_b)


def _state_error(env, seat: int):
    for step in reversed(env.steps):
        error = step[seat].get("error")
        if error:
            return str(error)
    return None


def _remaining_overage_min(env, seat: int) -> float | None:
    """Kaggleの全stepから、その席の最小残りoverage秒を取る。"""
    values: list[float] = []
    for step in (getattr(env, "steps", None) or ()):
        try:
            observation = step[seat].get("observation") or {}
            value = observation.get("remainingOverageTime")
        except (AttributeError, IndexError, TypeError):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                values.append(number)
    return round(min(values), 4) if values else None


def _agent_metrics(agent) -> dict:
    metrics = getattr(agent, "__globals__", {}).get("AGENT_METRICS", {})
    return dict(metrics) if isinstance(metrics, dict) else {}


def _metric_delta(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def _sum_agent_metrics(results: list[dict], side: str,
                       seat: int | None = None) -> dict:
    """各gameのflat numeric metricsをagent/席ごとに合算する。"""
    if side not in {"a", "b"}:
        raise ValueError(f"sideはa/b: {side}")
    key = f"metrics_{side}"
    total: dict[str, float] = {}
    for row in results:
        agent_seat = row.get("a_seat") if side == "a" else 1 - row.get("a_seat", 0)
        if seat is not None and agent_seat != seat:
            continue
        metrics = row.get(key) or {}
        if not isinstance(metrics, dict):
            continue
        for name, value in metrics.items():
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(float(value))):
                continue
            total[name] = total.get(name, 0) + value
    return {
        name: int(value) if float(value).is_integer() else round(float(value), 6)
        for name, value in sorted(total.items())
    }


def _play(swap: bool) -> dict:
    # agent側cgはworker initializerで先にロード済み。cabt環境を先にimportすると、
    # macOSの共有native bufferへ別cgが先行登録されるため順序を維持する。
    a, b = _worker_agents["a"], _worker_agents["b"]
    from kaggle_environments import make

    t0 = time.time()
    metrics_a_before, metrics_b_before = _agent_metrics(a), _agent_metrics(b)
    env = make("cabt")
    env.run([b, a] if swap else [a, b])
    a_seat = 1 if swap else 0
    b_seat = 1 - a_seat
    a_state, b_state = env.state[a_seat], env.state[b_seat]
    reward = a_state.reward
    status_a, status_b = str(a_state.status), str(b_state.status)
    failures = []
    if reward not in (-1, 0, 1):
        failures.append(f"reward={reward!r}")
    if status_a != "DONE":
        failures.append(f"a_status={status_a}")
    if status_b != "DONE":
        failures.append(f"b_status={status_b}")
    metrics_a = _metric_delta(metrics_a_before, _agent_metrics(a))
    metrics_b = _metric_delta(metrics_b_before, _agent_metrics(b))
    for side, metrics in (("a", metrics_a), ("b", metrics_b)):
        for key in (
            "fixed_search_incomplete", "fixed_search_errors",
            "expert_rule_errors", "expert_rule_invalid",
        ):
            if metrics.get(key, 0):
                failures.append(f"{side}_{key}={metrics[key]}")
    return {
        "a_seat": a_seat,
        "reward": reward,
        # INVALIDはルールどおり即負けとして0点。ただしfailureを必ず表へ出す。
        "score": {1: 1.0, 0: 0.5, -1: 0.0}.get(reward, 0.0),
        "status_a": status_a,
        "status_b": status_b,
        "error_a": _state_error(env, a_seat),
        "error_b": _state_error(env, b_seat),
        "remaining_overage_sec_a": _remaining_overage_min(env, a_seat),
        "remaining_overage_sec_b": _remaining_overage_min(env, b_seat),
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "failures": failures,
        "sec": round(time.time() - t0, 4),
    }


def _play_seat_pair(pair_index: int) -> list[dict]:
    """同じfresh process内でP0/P1を1戦ずつ行い、席と実行順を両方均す。"""
    swaps = _seat_pair_swaps(pair_index)
    return [_play(swap) for swap in swaps]


def _seat_pair_swaps(pair_index: int) -> tuple[bool, bool]:
    return (False, True) if pair_index % 2 == 0 else (True, False)


def _seat_pair_worker(send_conn, pair_index: int, spec_a: str, spec_b: str) -> None:
    """spawn child entry。例外objectをPipeへ流さず、文字列のprotocolに固定する。"""
    try:
        _init_worker(spec_a, spec_b)
        send_conn.send({"status": "ok", "rows": _play_seat_pair(pair_index)})
    except BaseException as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
        try:
            send_conn.send({"status": "error", "detail": detail})
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        try:
            send_conn.close()
        except OSError:
            pass


def _synthetic_failed_pair(pair_index: int, kind: str, detail: str,
                           elapsed_sec: float) -> list[dict]:
    """pairが結果を返せない場合も、既存schemaの両席2行を必ず残す。"""
    message = f"arena_pair_{kind}: {detail}"
    sec = round(max(0.0, elapsed_sec), 4)
    rows = []
    for swap in _seat_pair_swaps(pair_index):
        rows.append({
            "a_seat": 1 if swap else 0,
            "reward": None,
            "score": 0.0,
            "status_a": "ERROR",
            "status_b": "ERROR",
            "error_a": message,
            "error_b": message,
            "remaining_overage_sec_a": None,
            "remaining_overage_sec_b": None,
            "metrics_a": {},
            "metrics_b": {},
            "failures": [message],
            "sec": sec,
        })
    return rows


def _validate_pair_payload(rows, pair_index: int) -> str | None:
    if not isinstance(rows, list) or len(rows) != 2:
        return "ok payloadのrowsが長さ2のlistでない"
    expected_seats = [1 if swap else 0 for swap in _seat_pair_swaps(pair_index)]
    for i, (row, expected_seat) in enumerate(zip(rows, expected_seats)):
        if not isinstance(row, dict):
            return f"rows[{i}]がdictでない"
        missing = sorted(_RESULT_KEYS - row.keys())
        if missing:
            return f"rows[{i}]の必須key不足: {missing}"
        if row.get("a_seat") != expected_seat:
            return f"rows[{i}].a_seat={row.get('a_seat')!r}, expected={expected_seat}"
    return None


def _reap_pair_process(process, exit_grace_sec: float, terminate_grace_sec: float,
                       kill_grace_sec: float) -> tuple[str | None, bool]:
    """processを有限時間で回収し、強制したactionと最終生存状態を返す。"""
    process.join(max(0.0, exit_grace_sec))
    if not process.is_alive():
        return None, False
    action = "terminate"
    process.terminate()
    process.join(max(0.0, terminate_grace_sec))
    if process.is_alive():
        action = "kill"
        kill = getattr(process, "kill", process.terminate)
        kill()
        process.join(max(0.0, kill_grace_sec))
    return action, process.is_alive()


def _run_fresh_seat_pairs(spec_a: str, spec_b: str, pair_count: int, jobs: int,
                          pair_timeout_sec: float, *, worker_target=None,
                          exit_grace_sec: float = PAIR_EXIT_GRACE_SEC,
                          terminate_grace_sec: float = PAIR_TERMINATE_GRACE_SEC,
                          kill_grace_sec: float = PAIR_KILL_GRACE_SEC,
                          ) -> tuple[list[list[dict]], list[dict], list[str]]:
    """boundedなspawn childを監視し、pair index順の結果を返す。"""
    worker_target = worker_target or _seat_pair_worker
    ctx = multiprocessing.get_context("spawn")
    paired: list[list[dict] | None] = [None] * pair_count
    watchdog_events: list[dict] = []
    cleanup_run_failures: list[str] = []
    active = {}
    next_pair = 0

    def _record_start_failure(pair_index: int, exc: Exception, elapsed: float) -> None:
        detail = f"{type(exc).__name__}: {exc}"
        paired[pair_index] = _synthetic_failed_pair(
            pair_index, "start_error", detail, elapsed,
        )
        watchdog_events.append({
            "pair_index": pair_index,
            "kind": "start_error",
            "detail": detail,
        })

    def _launch(pair_index: int) -> None:
        started = time.monotonic()
        recv_conn = send_conn = process = None
        try:
            recv_conn, send_conn = ctx.Pipe(duplex=False)
            process = ctx.Process(
                target=worker_target,
                args=(send_conn, pair_index, spec_a, spec_b),
                name=f"arena-pair-{pair_index}",
            )
            process.start()
            # 親がsend端を保持するとchild crash時にrecv側へEOFが届かない。
            send_conn.close()
            active[recv_conn] = {
                "pair_index": pair_index,
                "process": process,
                "started": started,
                "deadline": started + pair_timeout_sec,
            }
        except Exception as exc:
            if send_conn is not None:
                send_conn.close()
            if recv_conn is not None:
                recv_conn.close()
            if process is not None and process.is_alive():
                process.terminate()
                process.join(kill_grace_sec)
            _record_start_failure(pair_index, exc, time.monotonic() - started)

    def _finish(recv_conn, *, rows: list[dict] | None, kind: str | None,
                detail: str = "", payload_received: bool = False) -> None:
        state = active.pop(recv_conn)
        pair_index = state["pair_index"]
        process = state["process"]
        elapsed = time.monotonic() - state["started"]
        if rows is None:
            rows = _synthetic_failed_pair(pair_index, kind or "unknown", detail, elapsed)
        paired[pair_index] = rows

        action, still_alive = _reap_pair_process(
            process, exit_grace_sec, terminate_grace_sec, kill_grace_sec,
        )
        exitcode = process.exitcode
        event = None
        if kind is not None:
            event = {
                "pair_index": pair_index,
                "kind": kind,
                "detail": detail,
                "exitcode": exitcode,
            }
        elif action is not None:
            event = {
                "pair_index": pair_index,
                "kind": "forced_cleanup_after_payload",
                "action": action,
                "exitcode": exitcode,
            }
        elif payload_received and exitcode not in (0, None):
            event = {
                "pair_index": pair_index,
                "kind": "nonzero_exit_after_payload",
                "exitcode": exitcode,
            }
        if event is not None:
            if action is not None:
                event["action"] = action
            event["elapsed_sec"] = round(elapsed, 4)
            watchdog_events.append(event)
        if still_alive:
            cleanup_run_failures.append(
                f"pair {pair_index} process remained alive after kill"
            )
        recv_conn.close()
        if not still_alive:
            process.close()

    def _receive(recv_conn) -> None:
        state = active[recv_conn]
        process = state["process"]
        try:
            envelope = recv_conn.recv()
        except (EOFError, OSError) as exc:
            process.join(0)
            detail = f"{type(exc).__name__}: {exc}; exitcode={process.exitcode}"
            _finish(recv_conn, rows=None, kind="worker_crash", detail=detail)
            return
        if not isinstance(envelope, dict):
            _finish(
                recv_conn, rows=None, kind="protocol_error",
                detail=f"envelopeがdictでない: {type(envelope).__name__}",
                payload_received=True,
            )
            return
        if envelope.get("status") == "error":
            _finish(
                recv_conn, rows=None, kind="worker_error",
                detail=str(envelope.get("detail", "worker error"))[-4000:],
                payload_received=True,
            )
            return
        if envelope.get("status") != "ok":
            _finish(
                recv_conn, rows=None, kind="protocol_error",
                detail=f"未知status={envelope.get('status')!r}", payload_received=True,
            )
            return
        rows = envelope.get("rows")
        invalid = _validate_pair_payload(rows, state["pair_index"])
        if invalid:
            _finish(
                recv_conn, rows=None, kind="protocol_error", detail=invalid,
                payload_received=True,
            )
            return
        _finish(recv_conn, rows=rows, kind=None, payload_received=True)

    try:
        while next_pair < pair_count or active:
            while next_pair < pair_count and len(active) < jobs:
                _launch(next_pair)
                next_pair += 1
            if not active:
                continue
            now = time.monotonic()
            wait_sec = max(0.0, min(s["deadline"] for s in active.values()) - now)
            ready = wait_connections(list(active), timeout=wait_sec)
            for recv_conn in sorted(ready, key=lambda c: active[c]["pair_index"]):
                if recv_conn in active:
                    _receive(recv_conn)

            now = time.monotonic()
            overdue = sorted(
                (conn for conn, state in active.items() if state["deadline"] <= now),
                key=lambda c: active[c]["pair_index"],
            )
            for recv_conn in overdue:
                # deadlineとpayload到着が競合した場合は完成済みpayloadを優先する。
                if recv_conn.poll():
                    _receive(recv_conn)
                    continue
                state = active[recv_conn]
                elapsed = now - state["started"]
                _finish(
                    recv_conn, rows=None, kind="timeout",
                    detail=f"no payload within {pair_timeout_sec:g}s (elapsed={elapsed:.3f}s)",
                )
    finally:
        # KeyboardInterruptを含む親側例外でもorphan childを残さない。
        for recv_conn, state in list(active.items()):
            process = state["process"]
            try:
                _reap_pair_process(process, 0.0, terminate_grace_sec, kill_grace_sec)
            finally:
                recv_conn.close()
                if not process.is_alive():
                    process.close()
        active.clear()

    if any(pair is None for pair in paired):
        raise RuntimeError("watchdog internal error: 未完了のseat pairがある")
    watchdog_events.sort(key=lambda event: (event["pair_index"], event["kind"]))
    return paired, watchdog_events, cleanup_run_failures  # type: ignore[return-value]


def wilson_ci(score: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = score / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (center - margin, center + margin)


def _sha256_file(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def agent_fingerprint(spec: str) -> dict:
    """mutableなbuildを内容hashで固定し、別環境でも同一物か判定できるようにする。"""
    if spec in ("random", "first"):
        return {"spec": spec, "sha256": f"builtin:{spec}", "config": {}}
    path = os.path.abspath(spec)
    if not os.path.exists(path):
        raise FileNotFoundError(f"agent specがない: {spec}")
    agent_dir = path if os.path.isdir(path) else os.path.dirname(path)
    h = hashlib.sha256()
    for base, dirs, files in os.walk(agent_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for filename in sorted(files):
            if filename.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(base, filename)
            rel = os.path.relpath(full, agent_dir)
            h.update(rel.encode())
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
    config_path = os.path.join(agent_dir, "agent_config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (OSError, ValueError):
        config = {}
    cg_names = ("libcg.dylib", "libcg.so", "libcg-arm64.so", "cg.dll")
    cg_path = next((os.path.join(agent_dir, "cg", x) for x in cg_names
                    if os.path.isfile(os.path.join(agent_dir, "cg", x))), "")
    return {
        "spec": os.path.relpath(spec, ROOT) if os.path.exists(spec) else spec,
        "sha256": h.hexdigest(),
        "config": config,
        "deck_sha256": _sha256_file(os.path.join(agent_dir, "deck.csv")),
        "model_sha256": _sha256_file(os.path.join(agent_dir, "ptcg", "policy_params.npz")),
        "cg_sha256": _sha256_file(cg_path),
    }


def _git_commit() -> str | None:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _resolve_profile(meta_a: dict, meta_b: dict, jobs: int, requested: str) -> str:
    configs = [meta_a.get("config") or {}, meta_b.get("config") or {}]
    search_configs = [c for c in configs if c.get("algo") == "bcs" or "search" in str(c.get("algo", ""))]
    fixed = [c.get("fixed_search_worlds") for c in search_configs
             if c.get("fixed_search_worlds") is not None]
    wall_clock = any(c.get("fixed_search_worlds") is None for c in search_configs)
    if requested not in ("standard", "production", "fixed-worlds"):
        if requested != "auto":
            raise ValueError(f"未知のprofile: {requested}")
    if fixed and wall_clock:
        raise ValueError("wall-clock search agentとfixed-worlds agentは同じA/Bで比較できない")
    actual = "production" if wall_clock else "fixed-worlds" if fixed else "standard"
    if requested != "auto" and requested != actual:
        raise ValueError(f"profile指定とagent設定が不一致: requested={requested}, actual={actual}")
    if actual == "production" and jobs != 1:
        raise ValueError("wall-clock searchのproduction評価はCPU競合を避けるため-j 1必須")
    if actual == "fixed-worlds":
        if len(set(fixed)) != 1:
            raise ValueError(f"fixed_search_worldsが不一致: {fixed}")
    return actual


def _summarize(results: list[dict]) -> dict:
    n = len(results)
    score = sum(r["score"] for r in results)
    wins = sum(r["reward"] == 1 for r in results)
    draws = sum(r["reward"] == 0 for r in results)
    losses = sum(r["reward"] == -1 for r in results)
    unscored = n - wins - draws - losses
    lo, hi = wilson_ci(score, n)
    return {
        "n": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "unscored": unscored,
        "score": score,
        "score_rate": round(score / n, 4) if n else 0.0,
        "score_ci95_approx": [round(lo, 4), round(hi, 4)],
    }


def _min_present(results: list[dict], key: str) -> float | None:
    values = [r.get(key) for r in results if r.get(key) is not None]
    return round(min(values), 4) if values else None


def run_match_series(agent_a: str, agent_b: str, n: int = 200, jobs: int = 1,
                     note: str = "", profile: str = "auto", run_id: str | None = None,
                     suite: str = "", fresh_process_per_pair: bool = True,
                     strict: bool = True,
                     pair_timeout_sec: float = DEFAULT_PAIR_TIMEOUT_SEC) -> dict:
    """AのBに対する成績を測る。結果はschema v2 ledgerへ自動追記する。"""
    if n <= 0 or n % 2:
        raise ValueError("nは正の偶数が必要(両席を同数にする)")
    if jobs <= 0:
        raise ValueError("jobsは正数が必要")
    if (not isinstance(pair_timeout_sec, (int, float)) or isinstance(pair_timeout_sec, bool)
            or not math.isfinite(float(pair_timeout_sec)) or pair_timeout_sec <= 0):
        raise ValueError("pair_timeout_secは有限の正数が必要")
    pair_timeout_sec = float(pair_timeout_sec)
    t0 = time.time()
    run_id = run_id or uuid.uuid4().hex
    meta_a, meta_b = agent_fingerprint(agent_a), agent_fingerprint(agent_b)
    profile = _resolve_profile(meta_a, meta_b, jobs, profile)
    watchdog_events: list[dict] = []
    cleanup_run_failures: list[str] = []
    if fresh_process_per_pair:
        # main/cgを同一processで何度も再importするとnative bufferが解放されずabortする。
        # そこで1 process=席反転1ペアとし、agentはinitializerで1回だけロードする。
        paired, watchdog_events, cleanup_run_failures = _run_fresh_seat_pairs(
            agent_a, agent_b, n // 2, jobs, pair_timeout_sec,
        )
        results = [row for pair in paired for row in pair]
    else:
        swaps = [i % 2 == 1 for i in range(n)]
        with ProcessPoolExecutor(
            max_workers=jobs,
            initializer=_init_worker,
            initargs=(agent_a, agent_b),
        ) as ex:
            results = list(ex.map(_play, swaps, chunksize=4))
    overall = _summarize(results)
    by_seat = {}
    for label, seat in (("P0", 0), ("P1", 1)):
        seat_rows = [r for r in results if r["a_seat"] == seat]
        by_seat[label] = _summarize(seat_rows)
        by_seat[label]["a_min_remaining_overage_sec"] = _min_present(
            seat_rows, "remaining_overage_sec_a",
        )
    failure_rows = [r for r in results if r["failures"]]
    end_meta_a, end_meta_b = agent_fingerprint(agent_a), agent_fingerprint(agent_b)
    run_failures = list(cleanup_run_failures)
    if end_meta_a["sha256"] != meta_a["sha256"]:
        run_failures.append("agent_a artifact changed during evaluation")
    if end_meta_b["sha256"] != meta_b["sha256"]:
        run_failures.append("agent_b artifact changed during evaluation")
    rec = {
        "schema": 2,
        "run_id": run_id,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "suite": suite,
        "git_commit": _git_commit(),
        "kaggle_env_version": importlib.metadata.version("kaggle-environments"),
        "profile": profile,
        "jobs": jobs,
        "isolation": "fresh_process_per_seat_pair" if fresh_process_per_pair else "reuse_worker",
        "a": meta_a["spec"],
        "b": meta_b["spec"],
        "a_meta": meta_a,
        "b_meta": meta_b,
        "n": n,
        "score": overall["score"],
        # v1互換名。CIは引分を0.5 Bernoulliとして扱う近似なので明示する。
        "winrate": overall["score_rate"],
        "ci95": overall["score_ci95_approx"],
        "overall": overall,
        "by_seat": by_seat,
        "min_remaining_overage_sec": {
            "a": _min_present(results, "remaining_overage_sec_a"),
            "b": _min_present(results, "remaining_overage_sec_b"),
        },
        "agent_metrics_total": {
            "a": _sum_agent_metrics(results, "a"),
            "b": _sum_agent_metrics(results, "b"),
        },
        "agent_metrics_by_seat": {
            "a": {
                "P0": _sum_agent_metrics(results, "a", 0),
                "P1": _sum_agent_metrics(results, "a", 1),
            },
            "b": {
                "P0": _sum_agent_metrics(results, "b", 0),
                "P1": _sum_agent_metrics(results, "b", 1),
            },
        },
        "failure_count": len(failure_rows),
        "failures": failure_rows[:20],
        "run_failures": run_failures,
        # schema v2への後方互換な付加情報。forced cleanupだけなら測定失敗にしない。
        "watchdog": {
            "enabled": fresh_process_per_pair,
            "pair_timeout_sec": pair_timeout_sec if fresh_process_per_pair else None,
            "event_count": len(watchdog_events),
            "events": watchdog_events[:20],
        },
        "statuses_a": dict(Counter(r["status_a"] for r in results)),
        "statuses_b": dict(Counter(r["status_b"] for r in results)),
        "sec": round(time.time() - t0, 1),
        "note": note,
    }
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if strict and (failure_rows or run_failures):
        raise ArenaRunError(
            f"game failures={len(failure_rows)}/{n}, run failures={len(run_failures)}", rec
        )
    return rec


def run_gauntlet(agent: str, opponents: list[str], n: int = 80, jobs: int = 1,
                  weights: list[float] | None = None, note: str = "",
                  profile: str = "auto", suite: str = "",
                  fresh_process_per_pair: bool = True, strict: bool = True,
                  dry_run: bool = False) -> dict:
    """1候補を複数相手へ順番に当て、メタ加重成績と最悪対面を記録する。

    個々の対戦はrun_match_seriesに委譲するため、席入替・モジュール分離・
    arena ledgerの性質は単体A/Bと同一。重いsearch評価を同時実行しない。
    """
    if not opponents:
        raise ValueError("opponentsが空")
    if n <= 0 or n % 2:
        raise ValueError("nは正の偶数が必要(相手ごとに両席を同数にする)")
    if weights is None:
        weights = [1.0] * len(opponents)
    if len(weights) != len(opponents) or any(w <= 0 for w in weights):
        raise ValueError("weightsはopponentsと同数の正数が必要")

    run_id = uuid.uuid4().hex
    agent_meta = agent_fingerprint(agent)
    opponent_meta = [agent_fingerprint(x) for x in opponents]
    resolved_profiles = [_resolve_profile(agent_meta, m, jobs, profile) for m in opponent_meta]
    if dry_run:
        return {
            "schema": 2,
            "status": "dry-run",
            "run_id": run_id,
            "suite": suite,
            "agent": agent_meta,
            "opponents": opponent_meta,
            "weights": weights,
            "weight_sum": sum(weights),
            "n_per_opponent": n,
            "total_games": n * len(opponents),
            "jobs": jobs,
            "profiles": resolved_profiles,
            "isolation": "fresh_process_per_seat_pair" if fresh_process_per_pair else "reuse_worker",
            "note": note,
        }

    t0 = time.time()
    rows = []
    for opponent, resolved_profile in zip(opponents, resolved_profiles):
        match_note = f"gauntlet: {note}" if note else "gauntlet"
        rows.append(run_match_series(
            agent, opponent, n=n, jobs=jobs, note=match_note,
            profile=resolved_profile, run_id=run_id, suite=suite,
            fresh_process_per_pair=fresh_process_per_pair, strict=strict,
        ))

    weight_sum = sum(weights)
    weighted = sum(w * r["winrate"] for w, r in zip(weights, rows)) / weight_sum
    pooled_score = sum(r["score"] for r in rows)
    pooled_n = sum(r["n"] for r in rows)
    pooled_lo, pooled_hi = wilson_ci(pooled_score, pooled_n)
    worst_i = min(range(len(rows)), key=lambda i: rows[i]["winrate"])
    rec = {
        "schema": 2,
        "status": "complete",
        "run_id": run_id,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "suite": suite,
        "agent": os.path.relpath(agent, ROOT) if os.path.exists(agent) else agent,
        "n_per_opponent": n,
        "opponents": [
            {
                "spec": r["b"],
                "weight": weights[i],
                "winrate": r["winrate"],
                "ci95": r["ci95"],
            }
            for i, r in enumerate(rows)
        ],
        "weighted_winrate": round(weighted, 4),
        "weighted_is_point_estimate": True,
        "weight_sum": weight_sum,
        "weight_normalized_within_list": True,
        "pooled_winrate": round(pooled_score / pooled_n, 4),
        "pooled_is_unweighted": True,
        "pooled_ci95": [round(pooled_lo, 4), round(pooled_hi, 4)],
        "worst_opponent": rows[worst_i]["b"],
        "worst_winrate": rows[worst_i]["winrate"],
        "worst_ci95_lower": rows[worst_i]["ci95"][0],
        "profiles": resolved_profiles,
        "jobs": jobs,
        "isolation": "fresh_process_per_seat_pair" if fresh_process_per_pair else "reuse_worker",
        "sec": round(time.time() - t0, 1),
        "note": note,
    }
    os.makedirs(os.path.dirname(GAUNTLET_LEDGER), exist_ok=True)
    with open(GAUNTLET_LEDGER, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
