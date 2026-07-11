"""BC方策×デッキのマッチアップ表(相手はヒューリスティック操縦)。"""

import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _init():
    import logging

    logging.disable(logging.WARNING)
    sys.path.insert(0, os.path.join(ROOT, "submission"))


def _play(args):
    my_deck_path, opp_deck_path, swap = args
    import deck_lib
    from kaggle_environments import make
    from cg.api import to_observation_class
    from ptcg import heuristics, policy

    my_deck = deck_lib.load_deck(os.path.join(ROOT, my_deck_path))
    opp_deck = deck_lib.load_deck(os.path.join(ROOT, opp_deck_path))

    def fallback(obs):
        try:
            return heuristics.choose(obs)
        except Exception:
            n = len(obs.select.option)
            return list(range(max(obs.select.minCount, min(obs.select.maxCount, n))))

    def bc_agent(od):
        obs = to_observation_class(od)
        if obs.select is None:
            return list(my_deck)
        return policy.choose(od) or fallback(obs)

    def h_agent(od):
        obs = to_observation_class(od)
        if obs.select is None:
            return list(opp_deck)
        return fallback(obs)

    env = make("cabt")
    env.run([h_agent, bc_agent] if swap else [bc_agent, h_agent])
    r = env.state[1 if swap else 0].reward
    return {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)


MY = {"BCフーディン": "decks/meta/meta_00.csv", "BCオーロンゲ": "decks/meta/meta_01.csv"}
OPP = {"フーディン": "decks/meta/meta_00.csv", "オーロンゲ": "decks/meta/meta_01.csv",
       "ガルーラ": "decks/meta/meta_02.csv", "ルカリオ": "decks/meta/meta_06.csv",
       "サンプル": "submission/deck.csv"}

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    with ProcessPoolExecutor(max_workers=8, initializer=_init) as ex:
        for my_name, my_path in MY.items():
            row = []
            for opp_name, opp_path in OPP.items():
                tasks = [(my_path, opp_path, i % 2 == 1) for i in range(n)]
                res = list(ex.map(_play, tasks, chunksize=4))
                row.append(f"{opp_name}:{sum(res) / len(res) * 100:.0f}%")
            print(f"{my_name} → " + " ".join(row), flush=True)
