"""ExIt(Expert Iteration)データ生成: 探索エージェント同士の自己対戦から勝者の決定を収集する。

原理: BC×探索は純BCに58.1%で勝つ(G3実証)= 探索の決定はBCより良い教師。
その決定でBCを再学習(bc_x1)すれば方策自体が強くなり、その上の探索もさらに強くなる
(AlphaZero式の方策改善ループ)。

- 教師: build済みの探索エージェント(fixed_search_worldsで計算量固定=負荷に頑健)
- 出力: data/bc/ と同じpairs形式 {"sel","cur","act","team","deck"} のjsonl.gz
  → 既存の bc_featurize.py / train_bc2.py がそのまま使える
- 勝者側の決定のみ保存(公式Daily Top Episodesと同じ規約)

使い方:
  .venv/bin/python scripts/exit_gen.py --agent build/v4.3a-fixed2 \
      --games 8000 -j 6 --out data/bc/exit_pairs_v1.jsonl.gz
"""

import argparse
import gzip
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_W = {}


def _init(agent_dir: str, mirror_dir: str):
    import logging

    logging.disable(logging.WARNING)
    from ptcglab.arena import load_agent

    # 注意: cgのネイティブ拡張は「同一パス」を同一プロセスに2回ロードすると
    # C++例外(buffer full. capacity:7)で落ちる。ミラー対戦は必ず別パスのコピーから。
    _W["a0"] = load_agent(agent_dir)
    _W["a1"] = load_agent(mirror_dir)
    with open(os.path.join(agent_dir, "deck.csv")) as f:
        _W["deck"] = [int(x) for x in f.read().split("\n")[:60]]
    _W["team"] = f"exit_{os.path.basename(agent_dir.rstrip('/'))}"


def _play_batch(args):
    batch_id, n_games = args
    from kaggle_environments import make

    lines = []
    for _ in range(n_games):
        rows = {0: [], 1: []}

        def wrap(fn, seat):
            def agent(od):
                act = fn(od)
                if od.get("select") is not None:
                    rows[seat].append((od["select"], od["current"], act))
                return act
            return agent

        env = make("cabt")
        env.run([wrap(_W["a0"], 0), wrap(_W["a1"], 1)])
        for seat in (0, 1):
            if env.state[seat].reward == 1:  # 勝者のみ
                for sel, cur, act in rows[seat]:
                    lines.append(json.dumps(
                        {"sel": sel, "cur": cur, "act": act,
                         "team": _W["team"], "deck": _W["deck"]},
                        separators=(",", ":")))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="教師エージェントのbuildディレクトリ")
    ap.add_argument("--games", type=int, default=8000)
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--out", required=True, help="出力 jsonl.gz パス")
    args = ap.parse_args()

    agent_dir = os.path.abspath(args.agent)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # ミラー席用に別パスのコピーを作る(同一パス2回ロードはネイティブ層が落ちる)
    mirror_dir = os.path.join(tempfile.mkdtemp(prefix="exit_mirror_"),
                              os.path.basename(agent_dir))
    shutil.copytree(agent_dir, mirror_dir)
    n_batches = args.games // args.batch
    tasks = [(i, args.batch) for i in range(n_batches)]
    total = 0
    try:
        with gzip.open(args.out, "wt") as out, \
                ProcessPoolExecutor(max_workers=args.j, initializer=_init,
                                    initargs=(agent_dir, mirror_dir)) as ex:
            for bi, lines in enumerate(ex.map(_play_batch, tasks)):
                for ln in lines:
                    out.write(ln + "\n")
                total += len(lines)
                if (bi + 1) % 10 == 0 or bi == n_batches - 1:
                    print(f"batch {bi + 1}/{n_batches} decisions={total}", flush=True)
    finally:
        shutil.rmtree(os.path.dirname(mirror_dir), ignore_errors=True)
    print(f"done: {total} decisions -> {args.out}")


if __name__ == "__main__":
    main()
