"""エージェントのA/B評価ハーネス。

使い方:
    .venv/bin/python scripts/evaluate.py submission/main.py --vs random -n 200 -j 8
    .venv/bin/python scripts/evaluate.py submission/main.py --vs first -n 200

先手後手を交互に入れ替えてN戦し、勝率とWilson 95%信頼区間を表示する。
エージェント指定は main.py のパス、または組み込みの "random"/"first"。
"""

import argparse
import importlib.util
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

_worker_agents = {}


def _load_agent(spec: str):
    if spec in ("random", "first"):
        return spec
    path = os.path.abspath(spec)
    dirp = os.path.dirname(path)
    if dirp not in sys.path:
        sys.path.insert(0, dirp)
    name = f"agent_module_{abs(hash(path))}"
    module_spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = mod
    module_spec.loader.exec_module(mod)
    return mod.agent


def _init_worker(spec_a: str, spec_b: str):
    import logging

    logging.disable(logging.WARNING)
    _worker_agents["a"] = _load_agent(spec_a)
    _worker_agents["b"] = _load_agent(spec_b)


def _play(swap: bool) -> float:
    """1戦実行し、エージェントAの結果を返す(1=勝ち, 0.5=引き分け, 0=負け)。"""
    from kaggle_environments import make

    a, b = _worker_agents["a"], _worker_agents["b"]
    env = make("cabt")
    env.run([b, a] if swap else [a, b])
    r = env.state[1 if swap else 0].reward
    if r is None:
        return 0.0  # エラー・タイムアウトは負け扱い
    return {1: 1.0, 0: 0.5, -1: 0.0}[r]


def wilson_ci(wins: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (center - margin, center + margin)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", help="main.pyのパス or random/first")
    ap.add_argument("--vs", default="random", help="対戦相手 (main.pyのパス or random/first)")
    ap.add_argument("-n", type=int, default=200, help="対戦数")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4, help="並列プロセス数")
    args = ap.parse_args()

    t0 = time.time()
    swaps = [i % 2 == 1 for i in range(args.n)]  # 先後を交互に
    with ProcessPoolExecutor(
        max_workers=args.j, initializer=_init_worker, initargs=(args.agent, args.vs)
    ) as ex:
        results = list(ex.map(_play, swaps, chunksize=4))
    dt = time.time() - t0

    score = sum(results)
    n = len(results)
    lo, hi = wilson_ci(score, n)
    print(f"{args.agent} vs {args.vs}: {n}戦")
    print(f"  スコア(勝ち1/分け0.5): {score:.1f}  勝率 {score / n * 100:.1f}%  [Wilson95%: {lo * 100:.1f}%–{hi * 100:.1f}%]")
    print(f"  {dt:.1f}s ({dt / n * 1000:.0f}ms/試合, {args.j}並列)")


if __name__ == "__main__":
    main()
