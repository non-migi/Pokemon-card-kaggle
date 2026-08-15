"""学習済みモデルの holdout top-1 を train_bc.py と同一の分割で測る。

train_bc.py はエクスポート後のモデルを再評価できない(学習時にしかholdoutを出さない)ので、
soup(重み平均)のような「学習を伴わないモデル」の評価に使う。
分割は train_bc.py と同一: default_rng(0) で全サンプルの10%(シード非依存)。

使い方:
    .venv/bin/python scripts/eval_holdout.py --data data/bc/pairs_grim6.jsonl.gz \
        --models bc_grim6_e12 bc_grim6_soup
(2026-08-15 soup評価のために作成)
"""

import argparse
import importlib.util
import os
import sys

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from ptcg import policy_features as PF  # noqa: E402
import train_bc  # noqa: E402


def load_model_arrays(name):
    mdir = os.path.join(ROOT, "models", name)
    P = dict(np.load(os.path.join(mdir, "policy_params.npz")))
    spec = importlib.util.spec_from_file_location("pv", os.path.join(mdir, "policy_vocab.py"))
    pv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pv)
    return P, list(pv.CARD_VOCAB)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    # 語彙はデータから再構築される(train_bc.load_decisionsと同一)ため、
    # 評価対象モデルの語彙と一致するかを必ず検証する
    S, O, C, Y, NOPT, _W, vocab = train_bc.load_decisions(args.data, args.limit)
    n = len(Y)
    M = train_bc.MAX_OPTS
    s = np.zeros((n, PF.N_STATE), np.float32)
    o = np.zeros((n, M, PF.N_OPTION), np.float32)
    c = np.zeros((n, M), np.int64)
    mask = np.zeros((n, M), bool)
    y = np.array(Y, np.int64)
    for i in range(n):
        s[i] = S[i]
        k = NOPT[i]
        o[i, :k] = O[i]
        c[i, :k] = C[i]
        mask[i, :k] = True
    n_hold = n // 10
    perm = np.random.default_rng(0).permutation(n)
    hold = perm[:n_hold]
    print(f"holdout {len(hold):,d} / {n:,d}")

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    ts = (torch.tensor(s), torch.tensor(o), torch.tensor(c), torch.tensor(mask), torch.tensor(y))

    for name in args.models:
        P, mv = load_model_arrays(name)
        if mv != vocab:
            print(f"{name}: ⚠️ 語彙不一致(モデル{len(mv)} vs データ{len(vocab)}) — スキップ")
            continue
        model = train_bc.TwoTower(len(vocab), P["s_w1"].shape[0])
        sd = {
            "emb.weight": P["emb"],
            "state.0.weight": P["s_w1"], "state.0.bias": P["s_b1"],
            "state.2.weight": P["s_w2"], "state.2.bias": P["s_b2"],
            "option.0.weight": P["o_w1"], "option.0.bias": P["o_b1"],
            "option.2.weight": P["o_w2"], "option.2.bias": P["o_b2"],
        }
        model.load_state_dict({k: torch.tensor(v) for k, v in sd.items()})
        model.to(dev).eval()
        correct = tot = 0
        with torch.no_grad():
            for i in range(0, len(hold), 2048):
                j = hold[i:i + 2048]
                sb, ob, cb, mb, yb = (t[j].to(dev) for t in ts)
                pred = model(sb, ob, cb, mb).argmax(-1)
                correct += (pred == yb).sum().item()
                tot += len(yb)
        print(f"{name}: holdout_top1 = {correct / tot * 100:.2f}% ({correct:,d}/{tot:,d})")


if __name__ == "__main__":
    main()
