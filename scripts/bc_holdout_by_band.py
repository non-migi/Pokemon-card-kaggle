"""学習済みBCモデルのholdout top-1を、勝者チームのLBスコア帯ごとに分解する。

用途: エリート加重(train_bc.py の --weight-min-score)の効果を測る。
総合holdoutは「平均的なチームの手をどれだけ当てるか」なので、
エリートに寄せたモデルはむしろ下がりうる。加重が狙いどおり効いているかは
**加重対象の帯に限定したtop-1**で見なければならない。

holdout集合は train_bc.py と同じ `default_rng(0).permutation(n)` の先頭10%を再現する。
同じデータで学習したモデル同士なら n が一致するので、**完全に同じ行**を比較できる。

使い方:
    .venv/bin/python scripts/bc_holdout_by_band.py \
        --data data/bc/pairs_grim6.jsonl.gz --lb results/lb_20260810.csv \
        --band 1050 --models bc_grim6 bc_grim6_ew
"""

import argparse
import csv
import gzip
import importlib.util
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ptcg import policy_features as PF  # noqa: E402

MAX_OPTS = 24
OUT = 64


def _iter_lines(paths):
    for p in paths:
        with gzip.open(p, "rt") as f:
            yield from f


def load_vocab(model: str) -> list:
    path = os.path.join(ROOT, "models", model, "policy_vocab.py")
    spec = importlib.util.spec_from_file_location("v", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.CARD_VOCAB


def forward(P, s, o, c, mask):
    """train_bc.py の TwoTower と同じ前向き計算(numpy版)。HIDに依存しない。"""
    def relu(x):
        return np.maximum(x, 0.0)
    sv = relu(s @ P["s_w1"].T + P["s_b1"]) @ P["s_w2"].T + P["s_b2"]          # (B, OUT)
    om = np.concatenate([o, P["emb"][c]], -1)                                  # (B, M, ...)
    ov = relu(om @ P["o_w1"].T + P["o_b1"]) @ P["o_w2"].T + P["o_b2"]          # (B, M, OUT)
    logits = np.einsum("bmo,bo->bm", ov, sv) / (OUT ** 0.5)
    return np.where(mask, logits, -1e9).argmax(-1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--lb", required=True, help="LeaderboardのCSV(TeamName,Score)")
    ap.add_argument("--band", type=float, default=1050.0, help="この値以上を『エリート』とする")
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--n-samples", type=int, default=None,
                    help="学習時の総サンプル数(META.jsonのsamples)。省略時は1パス数える")
    args = ap.parse_args()

    with open(args.lb, encoding="utf-8-sig") as fh:
        scores = {r["TeamName"]: float(r["Score"]) for r in csv.DictReader(fh)}

    def keep(d):
        """train_bc.load_decisions の pass2 と同一の採否条件。"""
        sel, act = d["sel"], d["act"]
        opts = sel.get("option") or []
        if sel.get("maxCount") != 1 or len(opts) < 2 or len(act) != 1:
            return None
        label = act[0]
        if not (0 <= label < min(len(opts), MAX_OPTS)):
            return None
        return label

    n = args.n_samples
    if n is None:
        n = sum(1 for line in _iter_lines(args.data) if keep(json.loads(line)) is not None)
    print(f"総サンプル数 n={n:,d}")

    n_hold = n // 10
    hold = set(np.random.default_rng(0).permutation(n)[:n_hold].tolist())
    print(f"holdout {len(hold):,d} 行を再現(train_bc.pyと同じ default_rng(0) 分割)")

    # holdout行だけを収集する
    rows, i = [], 0
    for line in _iter_lines(args.data):
        d = json.loads(line)
        label = keep(d)
        if label is None:
            continue
        if i in hold:
            rows.append((d, label, scores.get(d.get("team"))))
        i += 1
        if i >= n:
            break
    print(f"収集 {len(rows):,d} 行")

    elite = np.array([s is not None and s >= args.band for _, _, s in rows])
    listed = np.array([s is not None for _, _, s in rows])
    print(f"  うちエリート(LB{args.band:g}+): {elite.sum():,d} ({100 * elite.mean():.1f}%) / "
          f"LB掲載: {listed.sum():,d} ({100 * listed.mean():.1f}%)")

    print(f"\n{'model':22} {'総合':>8} {f'LB{args.band:g}+':>9} {'非エリート':>10}")
    base = {}
    for mi, model in enumerate(args.models):
        vocab = load_vocab(model)
        cid2idx = {cid: k + 1 for k, cid in enumerate(vocab)}
        P = dict(np.load(os.path.join(ROOT, "models", model, "policy_params.npz")))
        correct = np.zeros(len(rows), bool)
        B = 2048
        for st in range(0, len(rows), B):
            chunk = rows[st:st + B]
            b = len(chunk)
            s = np.zeros((b, PF.N_STATE), np.float32)
            o = np.zeros((b, MAX_OPTS, PF.N_OPTION), np.float32)
            c = np.zeros((b, MAX_OPTS), np.int64)
            mask = np.zeros((b, MAX_OPTS), bool)
            y = np.zeros(b, np.int64)
            for j, (d, label, _) in enumerate(chunk):
                sel, cur = d["sel"], d["cur"]
                s[j] = PF.state_features(sel, cur)
                for k, opt in enumerate((sel.get("option") or [])[:MAX_OPTS]):
                    feats, cid = PF.option_features(sel, cur, opt)
                    o[j, k] = feats
                    c[j, k] = cid2idx.get(cid, 0)
                    mask[j, k] = True
                y[j] = label
            correct[st:st + b] = forward(P, s, o, c, mask) == y
        tot, el, non = correct.mean(), correct[elite].mean(), correct[~elite].mean()
        if mi == 0:
            base = {"tot": tot, "el": el, "non": non}
            print(f"{model:22} {100 * tot:7.2f}% {100 * el:8.2f}% {100 * non:9.2f}%")
        else:
            print(f"{model:22} {100 * tot:7.2f}% {100 * el:8.2f}% {100 * non:9.2f}%"
                  f"   (基準比 総合{100 * (tot - base['tot']):+.2f} / "
                  f"エリート{100 * (el - base['el']):+.2f} / 非{100 * (non - base['non']):+.2f})")


if __name__ == "__main__":
    main()
