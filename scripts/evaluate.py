"""エージェントのA/B評価CLI(実装は ptcglab.arena に一本化)。

使い方:
    .venv/bin/python scripts/evaluate.py build/v3.0g --vs build/v3.0a -n 200 -j 8 --note "デッキA/B"
    .venv/bin/python scripts/evaluate.py build/v3.0g --vs random -n 100

エージェント指定はビルド済みディレクトリ(ptcglab.buildで作る)、main.pyパス、または random/first。
結果は results/arena.jsonl に自動追記される。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ptcglab.arena import DEFAULT_PAIR_TIMEOUT_SEC, run_match_series  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--vs", default="random")
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("-j", type=int, default=1,
                    help="wall-clock searchは1必須。fixed-worlds/純BCのみ並列可")
    ap.add_argument("--profile", choices=("auto", "standard", "production", "fixed-worlds"),
                    default="auto")
    ap.add_argument("--suite", default="")
    ap.add_argument("--reuse-agent", action="store_true",
                    help="高速だがKaggle同等性が下がる。提出判定では使わない")
    ap.add_argument("--pair-timeout-sec", type=float, default=DEFAULT_PAIR_TIMEOUT_SEC,
                    help="fresh processの席反転1ペア上限秒。productionでは十分長くする")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    r = run_match_series(
        args.agent, args.vs, n=args.n, jobs=args.j, note=args.note,
        profile=args.profile, suite=args.suite,
        fresh_process_per_pair=not args.reuse_agent,
        pair_timeout_sec=args.pair_timeout_sec,
    )
    print(f"{r['a']} vs {r['b']}: {r['n']}戦 勝率 {r['winrate'] * 100:.1f}% "
          f"[Wilson95%: {r['ci95'][0] * 100:.1f}%–{r['ci95'][1] * 100:.1f}%] ({r['sec']}s)")


if __name__ == "__main__":
    main()
