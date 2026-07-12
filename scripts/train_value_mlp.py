"""価値網の学習(route B): numpy MLP(非線形)。v0(LR, AUC0.73)の後継。

data/selfplay/*.npz(X=features.extract, y=勝敗)を読み、40→H→H→1のMLPを学習。
出力は src/ptcg/value_params.py(numpy推論用の重み)。value.py がMLPとして読む。

使い方:
  .venv/bin/python scripts/train_value_mlp.py --data data/selfplay/bc_v1 --hid 96 --epochs 30
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
        Xs.append(d["X"]); ys.append(d["y"])
    return np.concatenate(Xs), np.concatenate(ys)


def _relu(x):
    return np.maximum(x, 0.0)


def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def auc_score(y, p):
    mask = (y == 0) | (y == 1)
    yy, pp = y[mask], p[mask]
    order = np.argsort(pp)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(pp) + 1)
    n1, n0 = (yy == 1).sum(), (yy == 0).sum()
    if n1 == 0 or n0 == 0:
        return 0.5
    return (ranks[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


class MLP:
    def __init__(self, d, h, seed=0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, np.sqrt(2 / d), (d, h))
        self.b1 = np.zeros(h)
        self.W2 = rng.normal(0, np.sqrt(2 / h), (h, h))
        self.b2 = np.zeros(h)
        self.W3 = rng.normal(0, np.sqrt(2 / h), (h,))
        self.b3 = 0.0

    def forward(self, X):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = _relu(self.z1)
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = _relu(self.z2)
        self.z3 = self.a2 @ self.W3 + self.b3
        return _sig(self.z3)

    def params(self):
        return ["W1", "b1", "W2", "b2", "W3", "b3"]


def train(X, y, hid=96, epochs=30, bs=8192, lr=2e-3, l2=1e-6, seed=0):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xn = ((X - mu) / sd).astype(np.float32)
    n, d = Xn.shape
    net = MLP(d, hid, seed)
    # Adam状態
    m = {k: np.zeros_like(getattr(net, k)) for k in net.params()}
    v = {k: np.zeros_like(getattr(net, k)) for k in net.params()}
    b1a, b2a, eps, t = 0.9, 0.999, 1e-8, 0
    idx = np.arange(n)
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        rng.shuffle(idx)
        for s in range(0, n, bs):
            j = idx[s:s + bs]
            xb, yb = Xn[j], y[j]
            p = net.forward(xb)
            g = {}
            dz3 = (p - yb) / len(j)                       # (b,)
            g["W3"] = net.a2.T @ dz3 + l2 * net.W3
            g["b3"] = dz3.sum()
            da2 = np.outer(dz3, net.W3)                   # (b, h)
            dz2 = da2 * (net.z2 > 0)
            g["W2"] = net.a1.T @ dz2 + l2 * net.W2
            g["b2"] = dz2.sum(0)
            da1 = dz2 @ net.W2.T
            dz1 = da1 * (net.z1 > 0)
            g["W1"] = xb.T @ dz1 + l2 * net.W1
            g["b1"] = dz1.sum(0)
            t += 1
            for k in net.params():
                m[k] = b1a * m[k] + (1 - b1a) * g[k]
                v[k] = b2a * v[k] + (1 - b2a) * g[k] ** 2
                mh = m[k] / (1 - b1a ** t)
                vh = v[k] / (1 - b2a ** t)
                setattr(net, k, getattr(net, k) - lr * mh / (np.sqrt(vh) + eps))
    return net, mu, sd


def export(net, mu, sd, path):
    from ptcg.features import FEATURE_VERSION
    with open(path, "w") as f:
        f.write('"""価値網パラメータ(train_value_mlp.pyが自動生成)。MLP: 40->H->H->1。"""\n\n')
        f.write(f"FEATURE_VERSION = {FEATURE_VERSION}\n")
        f.write('MODEL = "mlp"\n')
        f.write(f"MU = {mu.tolist()}\n")
        f.write(f"SD = {sd.tolist()}\n")
        for k in ("W1", "b1", "W2", "b2", "W3"):
            f.write(f"{k} = {getattr(net, k).tolist()}\n")
        f.write(f"b3 = {float(net.b3)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/selfplay/bc_v1")
    ap.add_argument("--hid", type=int, default=96)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--holdout", type=float, default=0.1)
    ap.add_argument("--export", action="store_true", help="src/ptcg/value_params.pyへ書き出す")
    args = ap.parse_args()

    X, y = load(args.data)
    print(f"data: {X.shape[0]} rows, {X.shape[1]} feat, 勝ちラベル率 {y.mean():.3f}")
    n_hold = int(len(y) * args.holdout)
    perm = np.random.default_rng(0).permutation(len(y))
    hold, tr = perm[:n_hold], perm[n_hold:]

    net, mu, sd = train(X[tr], y[tr], hid=args.hid, epochs=args.epochs)
    Xh = ((X[hold] - mu) / sd).astype(np.float32)
    p = net.forward(Xh)
    yh = y[hold]
    auc = auc_score(yh, p)
    eps = 1e-7
    ll = -np.mean(yh * np.log(p + eps) + (1 - yh) * np.log(1 - p + eps))
    acc = ((p > 0.5) == (yh > 0.5)).mean()
    print(f"holdout: AUC={auc:.4f} acc={acc:.4f} logloss={ll:.4f}  (v0 LR: AUC 0.731)")

    if args.export:
        out = os.path.join(ROOT, "src", "ptcg", "value_params.py")
        export(net, mu, sd, out)
        print(f"exported -> {out}")


if __name__ == "__main__":
    main()
