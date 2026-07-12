"""BC操縦の自己対戦データ生成(route B: 価値網の教師データ)。

v0(selfplay_gen.py)との違い:
- 操縦が**BC**(ヒューリスティックでなく強いプレイ)= 探索で実際に出会う盤面分布に一致
- デッキは**トップメタ3種**(フーディン/オーロンゲ/Archaludon)= 1000+帯の局面を学習対象に
- 単数選択をsoftmaxサンプリング(温度T)で多様化 = 単一軌道への過適合を防ぐ

出力: data/selfplay/bc_vN/*.npz (X=features.extract, y=最終勝敗 1/0.5/0)

使い方(モデル入りbuildを指定):
  .venv/bin/python scripts/selfplay_gen_bc.py --model-dir build/v3.3g --games 40000 -j 8 --out data/selfplay/bc_v1
"""

import argparse
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECKS = ["meta/meta_00.csv", "meta/meta_01.csv", "meta/meta_07.csv"]  # フーディン/オーロンゲ/Archaludon
_MODEL_DIR = None


def _init(model_dir: str):
    import logging
    logging.disable(logging.WARNING)
    # モデル入りptcgが**必ず先頭**に来るよう、src→scripts→model_dirの順にinsert(0)する
    # (最後にinsertしたものが先頭)。AGENTS規約9: モデル入りptcgをsrcより先に。
    for p in (os.path.join(ROOT, "src"), os.path.join(ROOT, "scripts"), model_dir):
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    # ptcgをdeck_libより先にロードしてモデル入りに固定(deck_libはsrcをsys.pathへ挿す)
    import ptcg.policy  # noqa: F401
    global _MODEL_DIR
    _MODEL_DIR = model_dir


def _play_batch(args):
    batch_id, n_games, seed, temp = args
    # ptcg(モデル入り)をdeck_libより**先**にimport(規約9)
    from ptcg import policy, heuristics
    from ptcg.features import extract
    assert policy.ENABLED, "BCモデル未ロード(model-dirを確認)"
    import deck_lib
    from kaggle_environments import make
    from cg.api import to_observation_class

    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    decks = [deck_lib.load_deck(os.path.join(ROOT, "decks", d)) for d in DECKS]

    def sample_action(od):
        """単数選択は温度softmaxでサンプル、それ以外はBC choose。"""
        sel = od.get("select") or {}
        if sel.get("maxCount") == 1 and len(sel.get("option") or []) >= 2:
            s = policy.scores(od)
            if s is not None:
                p = np.exp((s - s.max()) / max(temp, 1e-3))
                p /= p.sum()
                return [int(np_rng.choice(len(s), p=p))]
        act = policy.choose(od)
        if act is not None:
            return act
        try:
            return heuristics.choose(to_observation_class(od))
        except Exception:
            n = len(sel.get("option") or [])
            return list(range(max(sel.get("minCount", 1), min(sel.get("maxCount", 1), n))))

    X, y = [], []
    for _ in range(n_games):
        da, db = rng.choice(decks), rng.choice(decks)
        rows = {0: [], 1: []}

        def make_agent(deck, seat):
            def agent(od):
                obs = to_observation_class(od)
                if obs.select is None:
                    return list(deck)
                cur = od.get("current")
                if od["select"].get("type") == 0 and cur and rng.random() < 0.35:
                    rows[seat].append(extract(obs.current, obs.current.yourIndex))
                return sample_action(od)
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
    ap.add_argument("--model-dir", required=True, help="モデル入りbuildディレクトリ(例 build/v3.3g)")
    ap.add_argument("--games", type=int, default=40000)
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--temp", type=float, default=0.7, help="単数選択のsoftmax温度(多様化)")
    ap.add_argument("--out", default="data/selfplay/bc_v1")
    args = ap.parse_args()

    model_dir = os.path.abspath(args.model_dir)
    os.makedirs(args.out, exist_ok=True)
    n_batches = args.games // args.batch
    tasks = [(i, args.batch, 2000 + i, args.temp) for i in range(n_batches)]
    total = 0
    with ProcessPoolExecutor(max_workers=args.j, initializer=_init, initargs=(model_dir,)) as ex:
        Xs, ys = [], []
        for bi, (X, y) in enumerate(ex.map(_play_batch, tasks)):
            if len(y):
                Xs.append(X); ys.append(y); total += len(y)
            if (bi + 1) % 20 == 0 or bi == n_batches - 1:
                if Xs:
                    np.savez_compressed(os.path.join(args.out, f"shard_{bi:04d}.npz"),
                                        X=np.concatenate(Xs), y=np.concatenate(ys))
                    Xs, ys = [], []
                print(f"batch {bi + 1}/{n_batches} rows={total}", flush=True)
    print(f"done: {total} rows -> {args.out}")


if __name__ == "__main__":
    main()
