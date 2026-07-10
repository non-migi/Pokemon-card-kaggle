"""自己対戦データ生成: ヒューリスティック対戦から (特徴量, 勝敗) を収集。

デッキはサンプルデッキ+メタデッキ6種からランダムに組み合わせ、多様な盤面を生成する。
各対戦で両プレイヤーのMAIN選択時の盤面から最大8フレームをサンプリングし、
自分視点の特徴量+最終勝敗(1/0.5/0)を記録。

使い方:
    .venv/bin/python scripts/selfplay_gen.py --games 100000 -j 8 --out data/selfplay/v0
"""

import argparse
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _init():
    import logging

    logging.disable(logging.WARNING)
    sub = os.path.join(ROOT, "submission")
    if sub not in sys.path:
        sys.path.insert(0, sub)


def _play_batch(args):
    batch_id, n_games, seed = args
    import deck_lib
    from kaggle_environments import make
    from cg.api import to_observation_class
    from ptcg import heuristics
    from ptcg.features import extract

    rng = random.Random(seed)
    decks = [deck_lib.load_deck(os.path.join(ROOT, "submission", "deck.csv"))]
    for i in range(6):
        p = os.path.join(ROOT, "decks", "meta", f"meta_{i:02d}.csv")
        if os.path.exists(p):
            decks.append(deck_lib.load_deck(p))

    X, y = [], []
    for _ in range(n_games):
        da, db = rng.choice(decks), rng.choice(decks)
        rows = {0: [], 1: []}  # seat -> [features]

        def make_agent(deck, seat):
            def agent(od):
                obs = to_observation_class(od)
                if obs.select is None:
                    return list(deck)
                if obs.select.type == 0 and obs.current and rng.random() < 0.35:
                    rows[seat].append(extract(obs.current, obs.current.yourIndex))
                try:
                    return heuristics.choose(obs)
                except Exception:
                    n = len(obs.select.option)
                    return list(range(max(obs.select.minCount, min(obs.select.maxCount, n))))
            return agent

        env = make("cabt")
        env.run([make_agent(da, 0), make_agent(db, 1)])
        for seat in (0, 1):
            r = env.state[seat].reward
            label = {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)
            take = rows[seat][:8] if len(rows[seat]) <= 8 else rng.sample(rows[seat], 8)
            for f in take:
                X.append(f)
                y.append(label)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100000)
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--out", default="data/selfplay/v0")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    n_batches = args.games // args.batch
    tasks = [(i, args.batch, 1000 + i) for i in range(n_batches)]
    total = 0
    with ProcessPoolExecutor(max_workers=args.j, initializer=_init) as ex:
        Xs, ys = [], []
        for bi, (X, y) in enumerate(ex.map(_play_batch, tasks)):
            Xs.append(X)
            ys.append(y)
            total += len(y)
            if (bi + 1) % 20 == 0 or bi == n_batches - 1:
                np.savez_compressed(
                    os.path.join(args.out, f"shard_{bi:04d}.npz"),
                    X=np.concatenate(Xs), y=np.concatenate(ys),
                )
                Xs, ys = [], []
                print(f"batch {bi + 1}/{n_batches} rows={total}", flush=True)
    print(f"done: {total} rows -> {args.out}")


if __name__ == "__main__":
    main()
