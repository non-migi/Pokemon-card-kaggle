"""自エージェント同士/対相手の1試合を、render_replay_jp が読める replay.json 形式で保存する。

使い方:
    .venv/bin/python scripts/gen_replay.py build/v4.0a <相手build> --tag v40a_vs_wall
出力: ~/.cache/ptcg-replays/episode-<tag>-replay.json (render_replay_jp <tag> で描画)

env.toJSON() はKaggleの公開エピソードと同じスキーマ(steps付き)を返すので、
ダウンロード版リプレイと同じビューアでそのまま見られる。
"""

import argparse
import json
import os

from kaggle_environments import make

from ptcglab.arena import load_agent

CACHE = os.path.expanduser("~/.cache/ptcg-replays")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_a")
    ap.add_argument("agent_b")
    ap.add_argument("--tag", required=True, help="出力ファイル名の識別子")
    ap.add_argument("--swap", action="store_true", help="席を入れ替える(自分をP1に)")
    args = ap.parse_args()

    a = load_agent(args.agent_a)
    b = load_agent(args.agent_b)
    env = make("cabt")
    env.run([b, a] if args.swap else [a, b])
    r = env.state[1 if args.swap else 0].reward
    outcome = {1: "勝ち", 0: "引き分け", -1: "負け", None: "不明"}.get(r, "不明")

    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"episode-{args.tag}-replay.json")
    with open(out, "w") as f:
        json.dump(env.toJSON(), f)
    print(f"自エージェント={'P1' if args.swap else 'P0'} 結果={outcome} → {out}")
    print(f"描画: .venv/bin/python scripts/render_replay_jp.py {args.tag}")


if __name__ == "__main__":
    main()
