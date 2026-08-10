"""既存のBCペア(pairs_*.jsonl.gz)から、特定アーキタイプの勝者側判断だけを抜き出す。

用途: **対戦相手用の方策**を作る。bc_v2(Alakazam中心)にGrimを操縦させると分布外で弱くなり、
ローカル壁が本番と乖離する(07-25分析: ローカル88.95% vs 本番25.7%)。壁は必ず
「そのデッキで実際に勝っている人のデータ」で学習した方策に操縦させる。

使い方:
    .venv/bin/python scripts/bc_filter_deck.py --key Grimmsnarl --out data/bc/pairs_grim.jsonl.gz
    .venv/bin/python scripts/bc_filter_deck.py --key Dragapult --out data/bc/pairs_dragapult.jsonl.gz \
        --sources data/bc/pairs_0713.jsonl.gz data/bc/pairs_0714.jsonl.gz
"""

import argparse
import glob
import gzip
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import deck_lib  # noqa: E402


def card_name(cid: int) -> str:
    c = deck_lib.CARDS.get(cid)
    return c.name if c else str(cid)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="デッキに含まれるポケモン名の部分一致 (例: Grimmsnarl)")
    ap.add_argument("--exclude", nargs="*", default=[], help="これを含むデッキは除外する")
    ap.add_argument("--min-copies", type=int, default=None,
                    help="--key に一致するカードをこの枚数以上積んでいるデッキだけ残す。"
                         "1枚差し(タッチ)を主軸デッキと区別するために使う。"
                         "例: --key Ogerpon --min-copies 4 とすると、Kangaskhan-Crustle(mill)が"
                         "Cornerstone Ogerponを1枚差ししているだけのデッキを落とせる")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sources", nargs="*", default=None,
                    help="省略時は data/bc/pairs_0*.jsonl.gz 全部")
    ap.add_argument("--min-team-score", type=float, default=None,
                    help="このLBスコア以上のチームの判断だけ残す(--lb が必要)。"
                         "BCは模倣した集団の平均を超えられないので、天井を上げたい時に使う")
    ap.add_argument("--lb", help="LeaderboardのCSV(TeamName,Score)")
    args = ap.parse_args()

    if os.path.exists(args.out):
        sys.exit(f"既存: {args.out} (上書きしない)")

    scores: dict[str, float] = {}
    if args.min_team_score is not None:
        if not args.lb:
            sys.exit("--min-team-score には --lb が必要")
        import csv
        with open(args.lb) as fh:
            for r in csv.DictReader(fh):
                scores[r["TeamName"]] = float(r["Score"])
        print(f"LB {len(scores)}チーム読み込み、{args.min_team_score}以上に絞る")
    sources = args.sources or sorted(glob.glob(os.path.join(ROOT, "data/bc/pairs_0*.jsonl.gz")))

    # deck(60枚のカードIDタプル)ごとに判定をキャッシュする
    verdict: dict[tuple, bool] = {}
    kept = seen = 0
    decks = Counter()
    teams: Counter = Counter()
    with gzip.open(args.out + ".tmp", "wt") as out:
        for path in sources:
            with gzip.open(path, "rt") as fh:
                for line in fh:
                    seen += 1
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    deck = tuple(sorted(d.get("deck") or []))
                    if deck not in verdict:
                        names = {card_name(i) for i in set(deck)}
                        ok = any(args.key in n for n in names) and not any(
                            any(x in n for n in names) for x in args.exclude)
                        if ok and args.min_copies is not None:
                            # setではなくdeck全体で数える(同名カードの重複を枚数として数えるため)
                            ok = sum(1 for i in deck if args.key in card_name(i)) >= args.min_copies
                        verdict[deck] = ok
                    if not verdict[deck]:
                        continue
                    if args.min_team_score is not None:
                        # LBに載っていないチームは除外する(強さ不明を混ぜない)
                        if scores.get(d.get("team"), -1.0) < args.min_team_score:
                            continue
                    kept += 1
                    decks[deck] += 1
                    teams[d.get("team")] += 1
                    out.write(line if line.endswith("\n") else line + "\n")
            print(f"  {os.path.basename(path)}: 累計 {kept:,d}/{seen:,d}", flush=True)
    os.rename(args.out + ".tmp", args.out)
    print(f"\n{args.out}: {kept:,d} 判断 / 全 {seen:,d} ({100 * kept / max(1, seen):.1f}%)")
    print(f"  ユニークデッキ {len(decks)} / ユニーク勝者チーム {len(teams)}")
    print("  最頻デッキ上位5件の判断数:", [n for _, n in decks.most_common(5)])


if __name__ == "__main__":
    main()
