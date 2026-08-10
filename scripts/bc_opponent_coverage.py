"""BC学習データを**相手アーキタイプ別**に分解する。

各判断の`cur.players[相手]`には相手の場・トラッシュのカードIDが入っているので、
「その判断がどの対面で起きたか」をラベル付けできる。これまで使っていなかった情報。

用途:
1. **カバレッジ測定**: 本番で負けている対面(例: Lopunny 12.4% / Ogerpon 9.1%)の
   学習データを実際にどれだけ持っているかを見る。BCは見ていない盤面で崩れる。
2. **対面フィルタ**: `--keep`で特定対面の判断だけを書き出し、重点学習に使う。

使い方:
    .venv/bin/python scripts/bc_opponent_coverage.py --data data/bc/pairs_grim3.jsonl.gz
    .venv/bin/python scripts/bc_opponent_coverage.py --data data/bc/pairs_grim3.jsonl.gz \
        --keep Lopunny Ogerpon --out data/bc/pairs_grim3_vs_rare.jsonl.gz
"""

import argparse
import gzip
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import deck_lib  # noqa: E402

# 相手の場に1枚でも見えたらその対面とみなす代表カード
ARCHETYPE = [
    ("Lopunny", "Mega Lopunny ex"),
    ("Ogerpon", "Teal Mask Ogerpon ex"),
    ("Grim", "Marnie's Grimmsnarl ex"),
    ("Alakazam", "Alakazam"),
    ("Kang", "Mega Kangaskhan ex"),
    ("Dragapult", "Dragapult ex"),
    ("Garchomp", "Cynthia's Garchomp ex"),
    ("Lucario", "Mega Lucario ex"),
    ("Archaludon", "Archaludon ex"),
    ("Rocket", "Team Rocket's"),
    ("Iono", "Iono’s"),
    ("Starmie", "Mega Starmie ex"),
    ("Abomasnow", "Mega Abomasnow ex"),
]


def opp_cards(cur: dict) -> set[int]:
    """相手の可視カードID(場・付属・進化元・トラッシュ)。"""
    me = cur.get("yourIndex", 0)
    op = cur["players"][1 - me]
    ids: set[int] = set()
    for zone in ("active", "bench"):
        for pk in op.get(zone) or []:
            if not pk:
                continue
            ids.add(pk.get("id"))
            for c in (pk.get("energyCards") or []) + (pk.get("tools") or []):
                ids.add(c.get("id") if isinstance(c, dict) else c)
            for pe in pk.get("preEvolution") or []:
                ids.add(pe.get("id") if isinstance(pe, dict) else pe)
    for c in op.get("discard") or []:
        ids.add(c.get("id") if isinstance(c, dict) else c)
    return {i for i in ids if isinstance(i, int)}


def label(ids: set[int], name_of: dict[int, str]) -> str:
    names = {name_of.get(i, "") for i in ids}
    for tag, key in ARCHETYPE:
        if any(key in n for n in names):
            return tag
    return "(unseen)" if not names else "(other)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0で全件")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--keep", nargs="*", help="この対面の判断だけを --out へ書き出す")
    ap.add_argument("--oversample", nargs="*", default=None, metavar="TAG=N",
                    help="対面ごとの複製倍率 (例: Lopunny=3 Ogerpon=3 Lucario=4)。"
                         "少数対面が勾配で埋もれるのを防ぐ。指定外は等倍")
    ap.add_argument("--out")
    args = ap.parse_args()

    factor: dict[str, int] = {}
    for spec in args.oversample or []:
        tag, _, mult = spec.partition("=")
        factor[tag] = max(1, int(mult or 1))

    if args.out and os.path.exists(args.out):
        sys.exit(f"既存: {args.out} (上書きしない)")

    name_of = {cid: c.name for cid, c in deck_lib.CARDS.items()}
    cnt = Counter()
    n = kept = 0
    out = gzip.open(args.out + ".tmp", "wt") if args.out else None

    with gzip.open(args.data, "rt") as fh:
        for i, line in enumerate(fh):
            if args.limit and n >= args.limit:
                break
            if args.stride > 1 and i % args.stride:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n += 1
            tag = label(opp_cards(r["cur"]), name_of)
            cnt[tag] += 1
            if not out:
                continue
            if args.keep and tag not in args.keep:
                continue
            row = line if line.endswith("\n") else line + "\n"
            for _ in range(factor.get(tag, 1)):
                out.write(row)
                kept += 1

    if out:
        out.close()
        os.rename(args.out + ".tmp", args.out)

    print(f"判断 {n:,} 件を相手アーキタイプ別に分解\n")
    print(f"{'対面':<14}{'判断数':>12}{'シェア':>9}")
    for tag, c in cnt.most_common():
        print(f"{tag:<14}{c:>12,}{c / n * 100:>8.2f}%")
    if args.out:
        print(f"\n{args.out}: {kept:,} 判断 ({args.keep})")


if __name__ == "__main__":
    main()
