"""ローカルでcabt対戦を回す動作確認スクリプト。

使い方:
    .venv/bin/python scripts/run_match.py [対戦数]

組み込みの random / first エージェント同士を対戦させ、勝敗と所要時間を表示する。
"""

import sys
import time

from kaggle_environments import make


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    wins = [0, 0, 0]  # p0勝ち, p1勝ち, 引き分け
    t0 = time.time()
    for _ in range(n):
        env = make("cabt")
        env.run(["random", "first"])
        r = env.state[0].reward
        wins[0 if r == 1 else 1 if r == -1 else 2] += 1
    dt = time.time() - t0
    print(f"random(P0) vs first(P1) x{n}: P0勝ち={wins[0]} P1勝ち={wins[1]} 引き分け={wins[2]}")
    print(f"合計 {dt:.2f}s ({dt / n * 1000:.0f}ms/試合)")


if __name__ == "__main__":
    main()
