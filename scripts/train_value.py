"""価値関数v0の学習: ロジスティック回帰(numpyのみ)。

data/selfplay/*.npz(X=特徴量, y=勝敗)を読み、勝率予測モデルを学習。
学習結果は submission/ptcg/value_params.py に埋め込みコードとして出力する
(提出物の推論は純Python — 依存を増やさない)。

使い方:
    .venv/bin/python scripts/train_value.py --data data/selfplay/v0
"""

import argparse
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def load(data_dir: str):
    Xs, ys = [], []
    for p in sorted(glob.glob(os.path.join(data_dir, "*.npz"))):
        d = np.load(p)
        Xs.append(d["X"])
        ys.append(d["y"])
    X = np.concatenate(Xs)
    y = np.concatenate(ys)
    return X, y


def train_lr(X, y, epochs=60, lr=0.05, l2=1e-5):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xn = (X - mu) / sd
    n, d = Xn.shape
    w = np.zeros(d)
    b = 0.0
    idx = np.arange(n)
    bs = 65536
    for ep in range(epochs):
        np.random.shuffle(idx)
        for s in range(0, n, bs):
            j = idx[s:s + bs]
            z = Xn[j] @ w + b
            p = 1 / (1 + np.exp(-z))
            g = p - y[j]
            w -= lr * (Xn[j].T @ g / len(j) + l2 * w)
            b -= lr * g.mean()
    return w, b, mu, sd


def evaluate(X, y, w, b, mu, sd):
    Xn = (X - mu) / sd
    p = 1 / (1 + np.exp(-(Xn @ w + b)))
    eps = 1e-7
    ll = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
    # AUC(引き分け0.5は除外)
    mask = (y == 0) | (y == 1)
    yy, pp = y[mask], p[mask]
    order = np.argsort(pp)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(pp) + 1)
    n1, n0 = (yy == 1).sum(), (yy == 0).sum()
    auc = (ranks[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    acc = ((pp > 0.5) == (yy > 0.5)).mean() if len(yy) else 0.0
    return ll, auc, acc


def export(w, b, mu, sd, path):
    from ptcg.features import FEATURE_VERSION

    with open(path, "w") as f:
        f.write('"""学習済み価値関数パラメータ(train_value.pyが自動生成)。"""\n\n')
        f.write(f"FEATURE_VERSION = {FEATURE_VERSION}\n")
        f.write(f"W = {w.tolist()}\n")
        f.write(f"B = {float(b)}\n")
        f.write(f"MU = {mu.tolist()}\n")
        f.write(f"SD = {sd.tolist()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/selfplay/v0")
    ap.add_argument("--holdout", type=float, default=0.1)
    args = ap.parse_args()

    X, y = load(args.data)
    print(f"data: {X.shape[0]} rows, {X.shape[1]} features, 勝ちラベル率 {y.mean():.3f}")
    n_hold = int(len(y) * args.holdout)
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(y))
    hold, tr = perm[:n_hold], perm[n_hold:]

    w, b, mu, sd = train_lr(X[tr], y[tr])
    ll, auc, acc = evaluate(X[hold], y[hold], w, b, mu, sd)
    print(f"holdout: logloss={ll:.4f} AUC={auc:.4f} acc={acc:.4f}")

    out = os.path.join(ROOT, "src", "ptcg", "value_params.py")
    export(w, b, mu, sd, out)
    print(f"exported -> {out}")

    # 重要特徴量の表示
    from ptcg.features import FEATURE_NAMES
    imp = sorted(zip(FEATURE_NAMES, w), key=lambda t: abs(t[1]), reverse=True)[:10]
    for name, wi in imp:
        print(f"  {wi:+.3f} {name}")


if __name__ == "__main__":
    main()
