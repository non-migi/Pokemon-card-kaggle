"""敗因診断: agent vs 相手 でN戦し、決着理由(RESULT log の reason)を集計する。

reason: 1=サイド取り切り 2=山札切れ 3=バトル場に出せるポケモンなし 4=カード効果
"""

import sys
from collections import Counter

sys.path.insert(0, "submission")

from kaggle_environments import make
import main as my  # submission/main.py


def run(n: int, opponent: str) -> None:
    reasons_win = Counter()
    reasons_loss = Counter()
    turns_dist = []
    for i in range(n):
        swap = i % 2 == 1
        env = make("cabt")
        env.run([opponent, my.agent] if swap else [my.agent, opponent])
        me = 1 if swap else 0
        r = env.state[me].reward
        # visualize データから RESULT ログを探す
        vis = env.steps[0][0].get("visualize", [])
        result_reason = None
        max_turn = 0
        for frame in vis:
            for log in frame.get("logs", []):
                if log.get("type") in (23, "Result"):
                    result_reason = log.get("reason")
            t = (frame.get("current") or {}).get("turn") or 0
            max_turn = max(max_turn, t)
        turns_dist.append(max_turn)
        if r == 1:
            reasons_win[result_reason] += 1
        elif r == -1:
            reasons_loss[result_reason] += 1
    name = {1: "サイド", 2: "山札切れ", 3: "ポケモン無し", 4: "効果", None: "不明"}
    print(f"vs {opponent} x{n}")
    print("  勝ち内訳:", {name.get(k, k): v for k, v in reasons_win.items()})
    print("  負け内訳:", {name.get(k, k): v for k, v in reasons_loss.items()})
    if turns_dist:
        turns_dist.sort()
        print(f"  ターン数 中央値={turns_dist[len(turns_dist) // 2]} 最小={turns_dist[0]} 最大={turns_dist[-1]}")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 60, sys.argv[2] if len(sys.argv) > 2 else "first")
