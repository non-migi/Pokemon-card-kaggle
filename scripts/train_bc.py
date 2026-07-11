"""BC方策の学習(2タワー・選択肢内softmax)。

データ: bc_extract.pyのjsonl.gz。単数選択(maxCount==1, 選択肢2以上)のみ学習。
モデル: state塔(MLP) と option塔(数値特徴+カード埋め込み→MLP) の内積スコア。
出力: models/<name>/(policy_params.npz + policy_vocab.py + META.json)。上書き禁止

使い方:
    .venv/bin/python scripts/train_bc.py --data data/bc/pairs_0709.jsonl.gz --epochs 5 --name bc_v1
"""

import argparse
import gzip
import json
import os
import sys
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ptcg import policy_features as PF  # noqa: E402

EMB_DIM = 16
HID = 128
OUT = 64
MAX_OPTS = 24


def _iter_lines(paths):
    for path in paths:
        with gzip.open(path, "rt") as f:
            yield from f


def load_decisions(paths, limit=None):
    """jsonl.gz(複数可) → (state_feats, [opt_feats], [card_vocab_idx], label)。2パス: 語彙→特徴量。"""
    print(f"pass1: カード語彙を構築... ({len(paths)}ファイル)")
    card_count = Counter()
    n = 0
    for line in _iter_lines(paths):
        d = json.loads(line)
        sel = d["sel"]
        if sel.get("maxCount") != 1 or len(sel.get("option") or []) < 2:
            continue
        n += 1
        for opt in sel["option"][:MAX_OPTS]:
            _, cid = PF.option_features(sel, d["cur"], opt)
            if cid is not None:
                card_count[cid] += 1
        if limit and n >= limit:
            break
    vocab = [cid for cid, _ in card_count.most_common(300)]
    cid2idx = {cid: i + 1 for i, cid in enumerate(vocab)}  # 0=UNK/None
    print(f"  対象決定数={n} 語彙={len(vocab)}")

    print("pass2: 特徴量を構築...")
    S, O, C, Y, NOPT = [], [], [], [], []
    n = 0
    for line in _iter_lines(paths):
        d = json.loads(line)
        sel, cur, act = d["sel"], d["cur"], d["act"]
        opts = sel.get("option") or []
        if sel.get("maxCount") != 1 or len(opts) < 2 or len(act) != 1:
            continue
        label = act[0]
        if not (0 <= label < min(len(opts), MAX_OPTS)):
            continue
        sf = PF.state_features(sel, cur)
        of, ci = [], []
        for opt in opts[:MAX_OPTS]:
            feats, cid = PF.option_features(sel, cur, opt)
            of.append(feats)
            ci.append(cid2idx.get(cid, 0))
        S.append(sf)
        O.append(of)
        C.append(ci)
        Y.append(label)
        NOPT.append(len(of))
        n += 1
        if limit and n >= limit:
            break
    print(f"  学習サンプル={n}")
    return S, O, C, Y, NOPT, vocab


class TwoTower(nn.Module):
    def __init__(self, n_vocab):
        super().__init__()
        self.emb = nn.Embedding(n_vocab + 1, EMB_DIM)
        self.state = nn.Sequential(nn.Linear(PF.N_STATE, HID), nn.ReLU(), nn.Linear(HID, OUT))
        self.option = nn.Sequential(nn.Linear(PF.N_OPTION + EMB_DIM, HID), nn.ReLU(), nn.Linear(HID, OUT))

    def forward(self, s, o, c, mask):
        sv = self.state(s)                              # (B, OUT)
        ov = self.option(torch.cat([o, self.emb(c)], -1))  # (B, M, OUT)
        logits = (ov @ sv.unsqueeze(-1)).squeeze(-1) / (OUT ** 0.5)
        return logits.masked_fill(~mask, -1e9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/bc/pairs_0709.jsonl.gz"])
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--bs", type=int, default=512)
    ap.add_argument("--name", required=True, help="モデル名(models/<name>/ に出力。上書き禁止)")
    args = ap.parse_args()

    out_dir = os.path.join(ROOT, "models", args.name)
    if os.path.exists(out_dir):
        raise SystemExit(f"models/{args.name} は既に存在する(上書き禁止 — 別名を使う)")
    os.makedirs(out_dir)

    S, O, C, Y, NOPT, vocab = load_decisions(args.data, args.limit)
    n = len(Y)
    M = MAX_OPTS
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

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model = TwoTower(len(vocab)).to(dev)
    optim = torch.optim.Adam(model.parameters(), lr=1e-3)
    ts = torch.tensor(s), torch.tensor(o), torch.tensor(c), torch.tensor(mask), torch.tensor(y)

    n_hold = n // 10
    perm = np.random.default_rng(0).permutation(n)
    hold_idx, tr_idx = perm[:n_hold], perm[n_hold:]

    def batches(idx, bs, shuffle=True):
        if shuffle:
            idx = idx[np.random.permutation(len(idx))]
        for i in range(0, len(idx), bs):
            j = idx[i:i + bs]
            yield tuple(t[j].to(dev) for t in ts)

    for ep in range(args.epochs):
        model.train()
        tot = cnt = 0
        for sb, ob, cb, mb, yb in batches(tr_idx, args.bs):
            logits = model(sb, ob, cb, mb)
            loss = F.cross_entropy(logits, yb)
            optim.zero_grad()
            loss.backward()
            optim.step()
            tot += loss.item() * len(yb)
            cnt += len(yb)
        # holdout精度
        model.eval()
        correct = htot = 0
        with torch.no_grad():
            for sb, ob, cb, mb, yb in batches(hold_idx, 2048, shuffle=False):
                pred = model(sb, ob, cb, mb).argmax(-1)
                correct += (pred == yb).sum().item()
                htot += len(yb)
        print(f"epoch {ep}: loss={tot / cnt:.4f} holdout_top1={correct / htot * 100:.1f}%")

    # エクスポート(numpy推論用) → モデルレジストリ(ビルド時に ptcg/ へ注入される)
    import datetime
    import json as _json

    sd = {k: v.cpu().numpy() for k, v in model.state_dict().items()}
    np.savez_compressed(
        os.path.join(out_dir, "policy_params.npz"),
        emb=sd["emb.weight"],
        s_w1=sd["state.0.weight"], s_b1=sd["state.0.bias"],
        s_w2=sd["state.2.weight"], s_b2=sd["state.2.bias"],
        o_w1=sd["option.0.weight"], o_b1=sd["option.0.bias"],
        o_w2=sd["option.2.weight"], o_b2=sd["option.2.bias"],
    )
    with open(os.path.join(out_dir, "policy_vocab.py"), "w") as f:
        f.write('"""BC方策のカード語彙(train_bc.pyが自動生成)。"""\n\n')
        f.write(f"POLICY_FEATURE_VERSION = {PF.POLICY_FEATURE_VERSION}\n")
        f.write(f"CARD_VOCAB = {vocab}\n")
    with open(os.path.join(out_dir, "META.json"), "w") as f:
        _json.dump({
            "model": args.name,
            "trained": datetime.date.today().isoformat(),
            "data": args.data,
            "samples": n,
            "epochs": args.epochs,
        }, f, ensure_ascii=False, indent=1)
    print(f"exported -> models/{args.name}/ (policy_params.npz, policy_vocab.py, META.json)")


if __name__ == "__main__":
    main()
