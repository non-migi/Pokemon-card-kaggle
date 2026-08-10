"""学習済みBC方策のtop-1精度を**選択タイプ別**に出す。

狙い: 総合holdoutは1つの数字なので「どの判断が弱いか」が見えない。
公開知見(citerne "No breakthrough in 2 months")では、950+のルールベース agent との差は
**プランに従ったエネルギー付け(attach)**にあり、ablationでもattachだけが有意(63.5%)で
evolve/discardは中立だった。当リポジトリはExpert Floorを「対象局面が13〜29件しかない」
ルール群で閉じたが、attachは毎ターン発生する高頻度の判断であり、閉じた理由が当てはまらない。

そこで「BCがattachで実際に弱いのか」をデータで確認してからルール実装の可否を決める。

使い方:
    .venv/bin/python scripts/bc_accuracy_by_type.py --model bc_grim2 \
        --data data/bc/pairs_grim2.jsonl.gz --limit 200000
"""

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SELECT_TYPE = {
    0: "MAIN(行動選択)", 1: "CARD(カード)", 2: "ATTACHED_CARD", 3: "CARD_OR_ATTACHED",
    4: "ENERGY(エネ)", 5: "SKILL", 6: "ATTACK(技)", 7: "EVOLVE(進化)",
    8: "COUNT(枚数)", 9: "YES_NO", 10: "SPECIAL_CONDITION",
}
# 「エネルギー付け」に該当する context(SelectContext)
ATTACH_CTX = {21: "ATTACH_FROM(付ける先)", 22: "ATTACH_TO(付ける札)"}


def load_model(name: str):
    """models/<name>/ を src/ptcg へ注入せずに直接読む。"""
    mdir = os.path.join(ROOT, "models", name)
    sys.path.insert(0, mdir)
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import importlib
    vocab_mod = importlib.import_module("policy_vocab")
    P = dict(np.load(os.path.join(mdir, "policy_params.npz")))
    cid2idx = {int(c): i + 1 for i, c in enumerate(vocab_mod.CARD_VOCAB)}  # 0=UNK (train_bc.py:58と同一)
    return P, cid2idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=200000, help="読む行数の上限")
    ap.add_argument("--stride", type=int, default=1, help="N行に1行だけ使う")
    ap.add_argument("--out")
    args = ap.parse_args()

    P, cid2idx = load_model(args.model)
    from ptcg import policy  # noqa: E402

    # 精度は (選択タイプ, context) 単位で集計する
    by_type = defaultdict(lambda: [0, 0])      # key -> [correct, n]
    by_ctx = defaultdict(lambda: [0, 0])
    n_read = n_scored = 0

    with gzip.open(args.data, "rt") as fh:
        for i, line in enumerate(fh):
            if n_read >= args.limit:
                break
            if args.stride > 1 and i % args.stride:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n_read += 1
            sel, cur, act = r.get("sel"), r.get("cur"), r.get("act")
            if not sel or not cur or not act:
                continue
            opts = sel.get("option") or []
            if len(opts) < 2:
                continue          # 選択肢1つは常に正解なので除外
            s = policy.raw_scores_with(P, cid2idx, sel, cur, opts)
            if s is None:
                continue
            n_scored += 1
            t = int(sel.get("type", 0))
            ctx = int(sel.get("context", 0))
            max_count = int(sel.get("maxCount") or 1)
            if max_count > 1:
                # 複数選択は「上位max_countに正解集合が含まれるか」で見る
                order = [int(x) for x in np.argsort(-s)][:max_count]
                ok = int(set(act) <= set(order))
            else:
                ok = int(int(np.argmax(s)) == int(act[0]))
            for d, k in ((by_type, t), (by_ctx, (t, ctx))):
                d[k][0] += ok
                d[k][1] += 1

    print(f"読み込み {n_read:,} 行 / 採点 {n_scored:,} 判断 (選択肢2つ以上)\n")
    tot_c = sum(c for c, _ in by_type.values())
    tot_n = sum(n for _, n in by_type.values())
    print(f"総合 top-1 = {tot_c / max(1, tot_n) * 100:.1f}%  (n={tot_n:,})\n")

    print(f"{'選択タイプ':<24}{'n':>10}{'シェア':>8}{'top-1':>9}")
    for k, (c, n) in sorted(by_type.items(), key=lambda kv: -kv[1][1]):
        print(f"{SELECT_TYPE.get(k, str(k)):<24}{n:>10,}{n / tot_n * 100:>7.1f}%{c / n * 100:>8.1f}%")

    print(f"\n{'エネルギー付け関連の context':<34}{'n':>10}{'top-1':>9}")
    for (t, ctx), (c, n) in sorted(by_ctx.items(), key=lambda kv: -kv[1][1]):
        if ctx in ATTACH_CTX or t == 4:
            label = ATTACH_CTX.get(ctx, f"type={SELECT_TYPE.get(t, t)} ctx={ctx}")
            print(f"{label:<34}{n:>10,}{c / n * 100:>8.1f}%")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump({
            "model": args.model, "data": args.data,
            "scored": tot_n, "overall_top1": tot_c / max(1, tot_n),
            "by_type": {SELECT_TYPE.get(k, str(k)): {"n": n, "top1": c / n}
                        for k, (c, n) in by_type.items()},
            "by_context": {f"{t}:{ctx}": {"n": n, "top1": c / n}
                           for (t, ctx), (c, n) in by_ctx.items()},
        }, open(args.out, "w"), ensure_ascii=False, indent=1)
        print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
