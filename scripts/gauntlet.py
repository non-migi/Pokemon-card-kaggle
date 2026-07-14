"""複数相手ガントレットCLI。

使い方:
    .venv/bin/python scripts/gauntlet.py build/candidate \
        --vs build/meta-alakazam build/meta-lucario build/meta-archaludon \
        --weights 0.5 0.2 0.3 -n 80 -j 8 --note "直近メタ"

各対面は先後を交互にし、results/arena.jsonlへ記録する。全体要約は
results/gauntlet.jsonlへ記録する。search系は相手ごとに直列実行される。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ptcglab.arena import run_gauntlet  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--vs", nargs="+", required=True, dest="opponents")
    ap.add_argument("--weights", nargs="+", type=float, default=None)
    ap.add_argument("-n", type=int, default=80, help="相手ごとの試合数")
    ap.add_argument("-j", type=int, default=1,
                    help="productionは1必須。fixed-worlds/純BCのみ並列可")
    ap.add_argument("--profile", choices=("auto", "standard", "production", "fixed-worlds"),
                    default="auto")
    ap.add_argument("--suite", default="")
    ap.add_argument("--reuse-agent", action="store_true",
                    help="高速だがKaggle同等性が下がる。提出判定では使わない")
    ap.add_argument("--dry-run", action="store_true",
                    help="対戦せずpath/hash/config/総試合数を検証")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    r = run_gauntlet(
        args.agent,
        args.opponents,
        n=args.n,
        jobs=args.j,
        weights=args.weights,
        note=args.note,
        profile=args.profile,
        suite=args.suite,
        fresh_process_per_pair=not args.reuse_agent,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"{r['agent']}: 入力対面内の加重 {r['weighted_winrate'] * 100:.1f}% "
          f"(weight_sum={r['weight_sum']:g}) / "
          f"単純合算 {r['pooled_winrate'] * 100:.1f}% "
          f"[Wilson95% {r['pooled_ci95'][0] * 100:.1f}–{r['pooled_ci95'][1] * 100:.1f}%]")
    for row in r["opponents"]:
        print(f"  vs {row['spec']}: {row['winrate'] * 100:.1f}% "
              f"[{row['ci95'][0] * 100:.1f}–{row['ci95'][1] * 100:.1f}%] "
              f"weight={row['weight']:g}")
    print("summary=" + json.dumps(r, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
