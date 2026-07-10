"""LB上位チームのエピソードを収集し、メタデッキを分析する。

kaggle CLI経由: leaderboard → team-submissions → episodes → replay
リプレイの steps[1][pi]["action"] が各プレイヤーの60枚デッキ。

使い方:
    .venv/bin/python scripts/meta_scrape.py --teams 12 --eps 6 --outdir <dir>
    .venv/bin/python scripts/meta_scrape.py --analyze --outdir <dir>
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def kg(*args) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=120)
    return r.stdout


def parse_table(out: str) -> list[list[str]]:
    lines = [l for l in out.splitlines() if l.strip()]
    rows = []
    for l in lines:
        if l.startswith("---") or l.lstrip().startswith(("id ", "teamId", "Next Page")):
            continue
        rows.append(l.split())
    return rows


def scrape(n_teams: int, n_eps: int, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    lb = kg("competitions", "leaderboard", "-c", "pokemon-tcg-ai-battle", "--show")
    teams = []
    for row in parse_table(lb):
        if row and row[0].isdigit():
            teams.append((row[0], " ".join(row[1:-2]), row[-1]))
    teams = teams[:n_teams]
    print(f"{len(teams)} teams")
    for tid, name, score in teams:
        subs = parse_table(kg("competitions", "team-submissions", tid))
        subs = [r for r in subs if r and r[0].isdigit()]
        if not subs:
            continue
        sub_id = subs[0][0]  # 最新
        eps = parse_table(kg("competitions", "episodes", sub_id))
        ep_ids = [r[0] for r in eps if r and r[0].isdigit()][:n_eps]
        print(f"team={name}({score}) sub={sub_id} eps={len(ep_ids)}")
        for ep in ep_ids:
            dest = os.path.join(outdir, f"episode-{ep}-replay.json")
            if os.path.exists(dest):
                continue
            kg("competitions", "replay", ep, "-p", outdir)


def analyze(outdir: str) -> None:
    import deck_lib

    C = deck_lib.CARDS
    deck_stats = defaultdict(lambda: {"games": 0, "wins": 0.0, "teams": set(), "deck": None})

    def deck_key(deck: list[int]) -> str:
        """ポケモン構成でアーキタイプを識別。"""
        pk = sorted({C[x].name for x in deck if x in C and C[x].cardType == 0})
        return " / ".join(pk)

    n_files = 0
    for path in glob.glob(os.path.join(outdir, "*replay.json")):
        try:
            d = json.load(open(path))
            steps = d["steps"]
            rewards = d.get("rewards", [None, None])
            names = d.get("info", {}).get("TeamNames", ["?", "?"])
            if len(steps) < 2:
                continue
            n_files += 1
            for pi in range(2):
                deck = steps[1][pi].get("action")
                if not (isinstance(deck, list) and len(deck) == 60):
                    continue
                key = deck_key(deck)
                s = deck_stats[key]
                s["games"] += 1
                r = rewards[pi]
                s["wins"] += {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)
                s["teams"].add(names[pi])
                s["deck"] = deck
        except Exception as e:
            print(f"skip {os.path.basename(path)}: {e}")

    print(f"\n=== メタ分析 ({n_files}リプレイ) ===")
    ranked = sorted(deck_stats.items(), key=lambda kv: kv[1]["games"], reverse=True)
    for key, s in ranked[:20]:
        wr = s["wins"] / s["games"] * 100
        print(f"{s['games']:3d}戦 勝率{wr:5.1f}% teams={len(s['teams'])} | {key[:110]}")

    # 勝率上位のデッキを保存
    good = [(k, s) for k, s in deck_stats.items() if s["games"] >= 6]
    good.sort(key=lambda kv: kv[1]["wins"] / kv[1]["games"], reverse=True)
    os.makedirs("decks/meta", exist_ok=True)
    for i, (k, s) in enumerate(good[:8]):
        p = f"decks/meta/meta_{i:02d}.csv"
        deck_lib.save_deck(s["deck"], p)
        print(f"saved {p} 勝率{s['wins'] / s['games'] * 100:.0f}% ({s['games']}戦) {k[:80]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, default=12)
    ap.add_argument("--eps", type=int, default=6)
    ap.add_argument("--outdir", default="/private/tmp/claude-501/-Users-non-git-Pokemon-card-kaggle/b1969d4e-1f95-4647-9a92-c80a416a00ba/scratchpad/meta")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--scrape", action="store_true")
    args = ap.parse_args()
    if args.scrape or not args.analyze:
        scrape(args.teams, args.eps, args.outdir)
    analyze(args.outdir)
