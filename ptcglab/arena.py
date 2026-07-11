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
import importlib.util
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "results", "arena.jsonl")

_worker_agents = {}


def load_agent(spec: str):
    """spec: 組み込み名("random"/"first") or エージェントディレクトリ or main.pyパス。"""
    if spec in ("random", "first"):
        return spec
    path = os.path.abspath(spec)
    if os.path.isdir(path):
        path = os.path.join(path, "main.py")
    dirp = os.path.dirname(path)
    sys.path.insert(0, dirp)
    name = f"agent_module_{abs(hash(path))}"
    module_spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = mod
    module_spec.loader.exec_module(mod)
    # 重要: エージェントごとに ptcg/cg を分離(共有すると A/B が自己対戦になる)
    for key in list(sys.modules):
        if key == "ptcg" or key.startswith("ptcg.") or key == "cg" or key.startswith("cg."):
            del sys.modules[key]
    sys.path.remove(dirp)
    return mod.agent


def _init_worker(spec_a: str, spec_b: str):
    import logging

    logging.disable(logging.WARNING)
    _worker_agents["a"] = load_agent(spec_a)
    _worker_agents["b"] = load_agent(spec_b)


def _play(swap: bool) -> float:
    from kaggle_environments import make

    a, b = _worker_agents["a"], _worker_agents["b"]
    env = make("cabt")
    env.run([b, a] if swap else [a, b])
    r = env.state[1 if swap else 0].reward
    if r is None:
        return 0.0
    return {1: 1.0, 0: 0.5, -1: 0.0}[r]


def wilson_ci(score: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = score / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (center - margin, center + margin)


def run_match_series(agent_a: str, agent_b: str, n: int = 200, jobs: int = 8, note: str = "") -> dict:
    """AのBに対する成績を測る。結果はledgerに自動追記して返す。"""
    t0 = time.time()
    swaps = [i % 2 == 1 for i in range(n)]
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(agent_a, agent_b)) as ex:
        results = list(ex.map(_play, swaps, chunksize=4))
    score = sum(results)
    lo, hi = wilson_ci(score, n)
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "a": os.path.relpath(agent_a, ROOT) if os.path.exists(agent_a) else agent_a,
        "b": os.path.relpath(agent_b, ROOT) if os.path.exists(agent_b) else agent_b,
        "n": n,
        "winrate": round(score / n, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "sec": round(time.time() - t0, 1),
        "note": note,
    }
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
