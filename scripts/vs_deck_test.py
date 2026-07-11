"""非ミラー相手に対する v2.0(探索) vs v1.1(ヒューリスティック) の比較テスト。

自分: sample deck固定。相手: 指定デッキをヒューリスティックが操作。
ミラー仮定beliefの害を検証する。
"""

import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

OPP_DECK_PATH = sys.argv[1] if len(sys.argv) > 1 else None
N = int(sys.argv[2]) if len(sys.argv) > 2 else 100
MODE = sys.argv[3] if len(sys.argv) > 3 else "search"  # search / heuristic
MY_DECK_PATH = sys.argv[4] if len(sys.argv) > 4 else os.path.join(ROOT, "decks", "sample.csv")


def _init():
    import logging

    logging.disable(logging.WARNING)
    sub = os.path.join(ROOT, "src")
    if sub not in sys.path:
        sys.path.insert(0, sub)


def _play(args):
    swap, opp_deck_path, mode, my_deck_path = args
    import deck_lib
    from kaggle_environments import make
    from cg.api import to_observation_class
    from ptcg import heuristics
    from ptcg import search as psearch

    my_deck = deck_lib.load_deck(my_deck_path)
    opp_deck = deck_lib.load_deck(opp_deck_path)

    def heuristic_agent_of(deck):
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

    def search_agent(od):
        obs = to_observation_class(od)
        if obs.select is None:
            return list(my_deck)
        act = None
        try:
            act = psearch.decide(obs, my_deck, 0.5)
        except Exception:
            act = None
        if act is None:
            try:
                act = heuristics.choose(obs)
            except Exception:
                n = len(obs.select.option)
                act = list(range(max(obs.select.minCount, min(obs.select.maxCount, n))))
        return act

    me = search_agent if mode == "search" else heuristic_agent_of(my_deck)
    opp = heuristic_agent_of(opp_deck)
    env = make("cabt")
    env.run([opp, me] if swap else [me, opp])
    r = env.state[1 if swap else 0].reward
    return {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)


def main():
    tasks = [(i % 2 == 1, OPP_DECK_PATH, MODE, MY_DECK_PATH) for i in range(N)]
    with ProcessPoolExecutor(max_workers=8, initializer=_init) as ex:
        res = list(ex.map(_play, tasks, chunksize=2))
    print(f"mode={MODE} my={os.path.basename(MY_DECK_PATH)} vs {os.path.basename(OPP_DECK_PATH)}: "
          f"{sum(res) / len(res) * 100:.1f}% ({N}戦)")


if __name__ == "__main__":
    main()
