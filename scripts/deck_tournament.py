"""デッキ総当たりトーナメント(ヒューリスティックagent操縦)。

使い方:
    .venv/bin/python scripts/deck_tournament.py decks/meta/*.csv decks/sample.csv --pairs 30 -j 8
"""

import argparse
import itertools
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _init():
    import logging

    logging.disable(logging.WARNING)
    sub = os.path.join(ROOT, "src")
    if sub not in sys.path:
        sys.path.insert(0, sub)


def _play_pair(args):
    deck_a, deck_b = args
    from kaggle_environments import make
    from cg.api import to_observation_class
    from ptcg import heuristics

    def agent_of(deck):
        def agent(od):
            obs = to_observation_class(od)
            if obs.select is None:
                return list(deck)
            try:
                return heuristics.choose(obs)
            except Exception:
                n = len(obs.select.option)
                return list(range(max(obs.select.minCount, min(obs.select.maxCount, n))))
        return agent

    score = 0.0
    for swap in (False, True):
        env = make("cabt")
        a, b = agent_of(deck_a), agent_of(deck_b)
        env.run([b, a] if swap else [a, b])
        r = env.state[1 if swap else 0].reward
        score += {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)
    return score


def main():
    import deck_lib

    ap = argparse.ArgumentParser()
    ap.add_argument("decks", nargs="+")
    ap.add_argument("--pairs", type=int, default=30, help="1組あたりのペア数(1ペア=2戦)")
    ap.add_argument("-j", type=int, default=8)
    args = ap.parse_args()

    decks = {os.path.basename(p): deck_lib.load_deck(p) for p in args.decks}
    names = list(decks)
    pairs = list(itertools.combinations(names, 2))
    tasks, index = [], []
    for a, b in pairs:
        for _ in range(args.pairs):
            tasks.append((decks[a], decks[b]))
            index.append((a, b))

    with ProcessPoolExecutor(max_workers=args.j, initializer=_init) as ex:
        results = list(ex.map(_play_pair, tasks, chunksize=2))

    score = defaultdict(float)
    games = defaultdict(int)
    h2h = defaultdict(float)
    h2h_n = defaultdict(int)
    for (a, b), s in zip(index, results):
        score[a] += s
        score[b] += 2 - s
        games[a] += 2
        games[b] += 2
        h2h[(a, b)] += s
        h2h_n[(a, b)] += 2

    print("=== 総合勝率 ===")
    for n in sorted(names, key=lambda x: score[x] / games[x], reverse=True):
        print(f"  {score[n] / games[n] * 100:5.1f}%  {n}")
    print("=== 対戦成績(行 vs 列) ===")
    for a, b in pairs:
        print(f"  {a} vs {b}: {h2h[(a, b)] / h2h_n[(a, b)] * 100:.0f}%")


if __name__ == "__main__":
    main()
