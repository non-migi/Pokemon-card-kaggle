"""BC方策×デッキのマッチアップ表(相手はヒューリスティック操縦)。"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _init(build_name: str):
    import logging

    logging.disable(logging.WARNING)
    # BCモデル入りのptcgが必要なため、srcではなくビルド済みディレクトリを使う
    # (src/ptcgはモデル非同梱 — models/はビルド時に注入される設計)
    agent_dir = os.path.join(ROOT, "build", build_name)
    if not os.path.exists(agent_dir):
        raise SystemExit("先に .venv/bin/python -m ptcglab.build v3.0g --no-tar を実行")
    sys.path.insert(0, agent_dir)


def _play(args):
    my_deck_path, opp_deck_path, swap = args
    # 重要: ptcgを先にimportする(deck_libがsrcをsys.path先頭に挿すため、
    # 後からだとモデル非同梱のsrc/ptcgに化ける)
    from ptcg import heuristics, policy

    assert policy.ENABLED, "BCモデルがロードされていない(build/v3.0gを確認)"
    import deck_lib
    from kaggle_environments import make
    from cg.api import to_observation_class

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
        act = policy.choose(od)
        return act if act is not None else fallback(obs)

    def h_agent(od):
        obs = to_observation_class(od)
        if obs.select is None:
            return list(opp_deck)
        return fallback(obs)

    env = make("cabt")
    env.run([h_agent, bc_agent] if swap else [bc_agent, h_agent])
    r = env.state[1 if swap else 0].reward
    return {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)


MY = {"BCブリジュラス": "decks/meta/meta_07.csv", "BCオーロンゲ": "decks/meta/meta_01.csv"}
OPP = {"フーディン": "decks/meta/meta_00.csv", "オーロンゲ": "decks/meta/meta_01.csv",
       "ブリジュラス": "decks/meta/meta_07.csv", "ルカリオ": "decks/meta/meta_06.csv",
       "ガルーラ": "decks/meta/meta_02.csv"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=200)
    ap.add_argument("--build", default="v3.2g",
                    help="BCモデル同梱済みのbuild/<name>")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    args = ap.parse_args()
    with ProcessPoolExecutor(
        max_workers=args.jobs, initializer=_init, initargs=(args.build,),
    ) as ex:
        for my_name, my_path in MY.items():
            row = []
            for opp_name, opp_path in OPP.items():
                tasks = [(my_path, opp_path, i % 2 == 1) for i in range(args.n)]
                res = list(ex.map(_play, tasks, chunksize=4))
                row.append(f"{opp_name}:{sum(res) / len(res) * 100:.0f}%")
            print(f"{my_name} → " + " ".join(row), flush=True)
