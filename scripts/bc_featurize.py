"""BCペア(jsonl.gz)を学習用npzシャードに変換する(大規模データのストリーミング学習用)。

- pass1: 全ファイルをストリームしてカード語彙(top300)を確定 → vocab.json
- pass2: 10万決定ごとにnpzシャードを書き出し(O行列はfloat16でメモリ半減)

使い方:
    .venv/bin/python scripts/bc_featurize.py data/bc/pairs_*.jsonl.gz --out data/bc/feat_v1
"""

import argparse
import glob
import gzip
import json
import os
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ptcg import policy_features as PF  # noqa: E402

MAX_OPTS = 24


def iter_decisions(paths):
    for path in paths:
        with gzip.open(path, "rt") as f:
            for line in f:
                d = json.loads(line)
                sel = d["sel"]
                opts = sel.get("option") or []
                if sel.get("maxCount") != 1 or len(opts) < 2:
                    continue
                yield d, sel, opts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shard-size", type=int, default=100_000)
    args = ap.parse_args()

    paths = sorted(set(p for pat in args.inputs for p in glob.glob(pat)))
    print(f"入力: {len(paths)}ファイル {[os.path.basename(p) for p in paths]}")
    os.makedirs(args.out, exist_ok=True)

    print("pass1: 語彙...")
    card_count = Counter()
    n = 0
    for d, sel, opts in iter_decisions(paths):
        n += 1
        for opt in opts[:MAX_OPTS]:
            _, cid = PF.option_features(sel, d["cur"], opt)
            if cid is not None:
                card_count[cid] += 1
    vocab = [cid for cid, _ in card_count.most_common(300)]
    cid2idx = {cid: i + 1 for i, cid in enumerate(vocab)}
    with open(os.path.join(args.out, "vocab.json"), "w") as f:
        json.dump({"feature_version": PF.POLICY_FEATURE_VERSION, "vocab": vocab,
                   "n_state": PF.N_STATE, "n_option": PF.N_OPTION, "max_opts": MAX_OPTS,
                   "sources": [os.path.basename(p) for p in paths]}, f)
    print(f"  決定数={n} 語彙={len(vocab)}")

    print("pass2: シャード書き出し...")
    S, O, C, Y, NOPT = [], [], [], [], []
    shard_i = written = 0

    def flush():
        nonlocal S, O, C, Y, NOPT, shard_i, written
        if not Y:
            return
        m = len(Y)
        s = np.array(S, np.float32)
        o = np.zeros((m, MAX_OPTS, PF.N_OPTION), np.float16)
        c = np.zeros((m, MAX_OPTS), np.int16)
        mask = np.zeros((m, MAX_OPTS), bool)
        for i in range(m):
            k = NOPT[i]
            o[i, :k] = O[i]
            c[i, :k] = C[i]
            mask[i, :k] = True
        np.savez_compressed(os.path.join(args.out, f"shard_{shard_i:04d}.npz"),
                            s=s, o=o, c=c, mask=mask, y=np.array(Y, np.int16))
        written += m
        shard_i += 1
        print(f"  shard_{shard_i - 1:04d}: {m}件 (累計{written})", flush=True)
        S, O, C, Y, NOPT = [], [], [], [], []

    for d, sel, opts in iter_decisions(paths):
        act = d["act"]
        if len(act) != 1 or not (0 <= act[0] < min(len(opts), MAX_OPTS)):
            continue
        S.append(PF.state_features(sel, d["cur"]))
        of, ci = [], []
        for opt in opts[:MAX_OPTS]:
            feats, cid = PF.option_features(sel, d["cur"], opt)
            of.append(feats)
            ci.append(cid2idx.get(cid, 0))
        O.append(of)
        C.append(ci)
        Y.append(act[0])
        NOPT.append(len(of))
        if len(Y) >= args.shard_size:
            flush()
    flush()
    print(f"done: {written}件 -> {args.out}")


if __name__ == "__main__":
    main()
