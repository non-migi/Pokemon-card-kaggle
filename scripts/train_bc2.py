"""BC方策の学習 v2: npzシャードのストリーミング学習(数百万手対応)。

前提: scripts/bc_featurize.py で data/bc/feat_vX/ を作っておく。

使い方:
    .venv/bin/python scripts/train_bc2.py --feat data/bc/feat_v1 --epochs 6 --name bc_v2
"""

import argparse
import datetime
import glob
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

EMB_DIM = 16
HID = 128
OUT = 64


class TwoTower(nn.Module):
    def __init__(self, n_vocab, n_state, n_option):
        super().__init__()
        self.emb = nn.Embedding(n_vocab + 1, EMB_DIM)
        self.state = nn.Sequential(nn.Linear(n_state, HID), nn.ReLU(), nn.Linear(HID, OUT))
        self.option = nn.Sequential(nn.Linear(n_option + EMB_DIM, HID), nn.ReLU(), nn.Linear(HID, OUT))

    def forward(self, s, o, c, mask):
        sv = self.state(s)
        ov = self.option(torch.cat([o, self.emb(c)], -1))
        logits = (ov @ sv.unsqueeze(-1)).squeeze(-1) / (OUT ** 0.5)
        return logits.masked_fill(~mask, -1e9)


def shard_batches(path, dev, bs, shuffle=True):
    d = np.load(path)
    s = torch.tensor(d["s"])
    o = torch.tensor(d["o"].astype(np.float32))
    c = torch.tensor(d["c"].astype(np.int64))
    mask = torch.tensor(d["mask"])
    y = torch.tensor(d["y"].astype(np.int64))
    n = len(y)
    idx = np.random.permutation(n) if shuffle else np.arange(n)
    for i in range(0, n, bs):
        j = idx[i:i + bs]
        yield (s[j].to(dev), o[j].to(dev), c[j].to(dev), mask[j].to(dev), y[j].to(dev))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feat", required=True)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--bs", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    out_dir = os.path.join(ROOT, "models", args.name)
    if os.path.exists(out_dir):
        raise SystemExit(f"models/{args.name} は既に存在する(上書き禁止)")
    os.makedirs(out_dir)

    meta = json.load(open(os.path.join(args.feat, "vocab.json")))
    vocab = meta["vocab"]
    shards = sorted(glob.glob(os.path.join(args.feat, "shard_*.npz")))
    if len(shards) < 2:
        raise SystemExit("シャードが足りない")
    hold_shard, train_shards = shards[-1], shards[:-1]
    print(f"shards: train={len(train_shards)} holdout=1 vocab={len(vocab)}")

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model = TwoTower(len(vocab), meta["n_state"], meta["n_option"]).to(dev)
    optim = torch.optim.Adam(model.parameters(), lr=args.lr)

    for ep in range(args.epochs):
        model.train()
        tot = cnt = 0
        order = np.random.permutation(len(train_shards))
        for si in order:
            for sb, ob, cb, mb, yb in shard_batches(train_shards[si], dev, args.bs):
                loss = F.cross_entropy(model(sb, ob, cb, mb), yb)
                optim.zero_grad()
                loss.backward()
                optim.step()
                tot += loss.item() * len(yb)
                cnt += len(yb)
        model.eval()
        correct = htot = 0
        with torch.no_grad():
            for sb, ob, cb, mb, yb in shard_batches(hold_shard, dev, 2048, shuffle=False):
                correct += (model(sb, ob, cb, mb).argmax(-1) == yb).sum().item()
                htot += len(yb)
        print(f"epoch {ep}: loss={tot / cnt:.4f} holdout_top1={correct / htot * 100:.1f}%", flush=True)

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
        f.write('"""BC方策のカード語彙(train_bc2.pyが自動生成)。"""\n\n')
        f.write(f"POLICY_FEATURE_VERSION = {meta['feature_version']}\n")
        f.write(f"CARD_VOCAB = {vocab}\n")
    with open(os.path.join(out_dir, "META.json"), "w") as f:
        json.dump({"model": args.name, "trained": datetime.date.today().isoformat(),
                   "feat_dir": args.feat, "sources": meta.get("sources"),
                   "epochs": args.epochs}, f, ensure_ascii=False, indent=1)
    print(f"exported -> models/{args.name}/")


if __name__ == "__main__":
    main()
