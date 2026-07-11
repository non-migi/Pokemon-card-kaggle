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

from ptcglab.arena import run_match_series  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--vs", default="random")
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    r = run_match_series(args.agent, args.vs, n=args.n, jobs=args.j, note=args.note)
    print(f"{r['a']} vs {r['b']}: {r['n']}戦 勝率 {r['winrate'] * 100:.1f}% "
          f"[Wilson95%: {r['ci95'][0] * 100:.1f}%–{r['ci95'][1] * 100:.1f}%] ({r['sec']}s)")


if __name__ == "__main__":
    main()
