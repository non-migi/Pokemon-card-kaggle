"""ExIt(Expert Iteration)データ生成: 探索エージェント同士の自己対戦から勝者の決定を収集する。

原理: BC×探索は純BCに58.1%で勝つ(G3実証)= 探索の決定はBCより良い教師。
その決定でBCを再学習(bc_x1)すれば方策自体が強くなり、その上の探索もさらに強くなる
(AlphaZero式の方策改善ループ)。

- 教師: build済みの探索エージェント(fixed_search_worldsで計算量固定=負荷に頑健)
- 出力: **シャードディレクトリ**(--out DIR)。各シャードは data/bc/ と同じpairs形式
  {"sel","cur","act","team","deck"} のjsonl.gz → bc_featurize.py に DIR/*.jsonl.gz を渡せる
- 勝者側の決定のみ保存(公式Daily Top Episodesと同じ規約)
- **再開可能**: 同じコマンドを再実行すると既存シャードの決定数を数え、目標までの不足分だけ生成する
  (シャードはtmp書き→renameの原子的書き込みなので、途中killでも壊れたファイルは残らない)

使い方:
  .venv/bin/python scripts/exit_gen.py --agent build/v4.3a-fixed2 \
      --target-decisions 350000 -j 6 --out data/bc/exit_pairs_v1
"""

import argparse
import glob
import gzip
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BATCH_GAMES = 20          # 1ワーカー仕事あたりの試合数
BATCHES_PER_SHARD = 5     # シャード粒度(=100試合。killで失う最大がこの単位)
DECISIONS_PER_GAME = 74   # 実測平均(残り試合数の見積りに使用)

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


def _play_batch(n_games: int):
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


def count_existing(out_dir: str) -> int:
    """既存シャードの決定数(=再開時の起点)。壊れたファイルは無いはず(原子的書き込み)。"""
    n = 0
    for p in sorted(glob.glob(os.path.join(out_dir, "*.jsonl.gz"))):
        try:
            with gzip.open(p, "rt") as f:
                n += sum(1 for _ in f)
        except Exception as e:  # 万一壊れていたら隔離して数えない
            print(f"警告: 読めないシャードを隔離: {p} ({e})")
            os.rename(p, p + ".broken")
    return n


def write_shard(out_dir: str, lines: list[str]) -> str:
    """tmpに書いてrename(原子的)。名前はエポック秒で一意化(再開しても衝突しない)。"""
    name = f"shard_{int(time.time() * 1000):x}.jsonl.gz"
    tmp = os.path.join(out_dir, f".tmp_{name}")
    with gzip.open(tmp, "wt") as f:
        for ln in lines:
            f.write(ln + "\n")
    dst = os.path.join(out_dir, name)
    os.replace(tmp, dst)
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="教師エージェントのbuildディレクトリ")
    ap.add_argument("--target-decisions", type=int, default=350_000,
                    help="目標決定数(既存シャード分を差し引いて不足分だけ生成)")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--out", required=True, help="出力シャードディレクトリ")
    args = ap.parse_args()

    agent_dir = os.path.abspath(args.agent)
    os.makedirs(args.out, exist_ok=True)
    # 前回のtmp残骸を掃除
    for p in glob.glob(os.path.join(args.out, ".tmp_*")):
        os.remove(p)

    have = count_existing(args.out)
    need = args.target_decisions - have
    print(f"既存 {have} 決定 / 目標 {args.target_decisions} → 不足 {max(0, need)}")
    if need <= 0:
        print("目標到達済み。生成不要")
        return
    n_games = int(need / DECISIONS_PER_GAME) + BATCH_GAMES
    n_batches = max(1, n_games // BATCH_GAMES)
    print(f"追加生成: ~{n_games}試合 ({n_batches}バッチ)")

    # ミラー席用に別パスのコピー(同一パス2回ロードはネイティブ層が落ちる)
    mirror_dir = os.path.join(tempfile.mkdtemp(prefix="exit_mirror_"),
                              os.path.basename(agent_dir))
    shutil.copytree(agent_dir, mirror_dir)
    total = have
    buf = []
    try:
        with ProcessPoolExecutor(max_workers=args.j, initializer=_init,
                                 initargs=(agent_dir, mirror_dir)) as ex:
            for bi, lines in enumerate(ex.map(_play_batch,
                                              [BATCH_GAMES] * n_batches)):
                buf.extend(lines)
                total += len(lines)
                if (bi + 1) % BATCHES_PER_SHARD == 0 or bi == n_batches - 1:
                    name = write_shard(args.out, buf)
                    print(f"batch {bi + 1}/{n_batches} 累計{total}決定 -> {name}",
                          flush=True)
                    buf = []
                if total >= args.target_decisions:
                    print("目標到達、残バッチをスキップ")
                    break
    finally:
        if buf:  # 中断時も手持ち分はシャード化して保存
            write_shard(args.out, buf)
        shutil.rmtree(os.path.dirname(mirror_dir), ignore_errors=True)
    print(f"done: 計{total}決定 -> {args.out}")


if __name__ == "__main__":
    main()
