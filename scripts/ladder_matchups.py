"""実ラダーの公開リプレイから「相手デッキ別の実勝率」と敗因を集計する。

ローカルA/B(自分の系列との一騎打ち)ではなく、**本番の相手分布での成績**を出すのが目的。
リプレイは ladder_stats.py と同じキャッシュを使う(既取得分は再ダウンロードしない)。

使い方:
    .venv/bin/python scripts/ladder_matchups.py 54731784
    .venv/bin/python scripts/ladder_matchups.py 54731784 --out results/ladder_matchups_v4.3a.json
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import deck_lib  # noqa: E402

TEAM_NAME = "gogogozi migimimi"
CACHE = os.path.expanduser("~/.cache/ptcg-replays")

# アーキタイプ判定に使うポケモン名(デッキ内に1枚でもあれば該当)
ARCHETYPE_KEYS = (
    "Alakazam", "Grimmsnarl", "Kangaskhan", "Dragapult", "Garchomp",
    "Froslass", "Lucario", "Great Tusk", "Archaludon", "Starmie", "Cinderace",
    "Lopunny", "Ogerpon",
)


def kg(*args: str) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=180)
    return r.stdout


def episode_ids(sub_id: str) -> list[str]:
    out = kg("competitions", "episodes", sub_id)
    return [l.split()[0] for l in out.splitlines() if l.split() and l.split()[0].isdigit()]


def load_replay(ep_id: str) -> dict | None:
    path = os.path.join(CACHE, f"episode-{ep_id}-replay.json")
    if not os.path.exists(path):
        kg("competitions", "replay", ep_id, "-p", CACHE)
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def card_name(cid: int) -> str:
    c = deck_lib.CARDS.get(cid)
    return c.name if c else str(cid)


def archetype(deck: list[int]) -> str:
    names = {card_name(i) for i in set(deck)}
    tags = [k for k in ARCHETYPE_KEYS if any(k in n for n in names)]
    return "+".join(tags) if tags else "(other)"


def last_state(replay: dict, seat: int) -> dict | None:
    """観測に current が残っている最後のステップを返す(終局処理の1手前まで)。"""
    for step in reversed(replay["steps"]):
        cur = step[seat].get("observation", {}).get("current")
        if cur:
            return cur
    return None


def loss_cause(replay: dict, seat: int) -> str:
    cur = last_state(replay, seat)
    if cur is None:
        return "不明(状態なし)"
    me, op = cur["players"][seat], cur["players"][1 - seat]
    if me.get("deckCount", 99) <= 0:
        return "自山切れ"
    if len(op.get("prize") or []) <= 1:
        return "サイド取り切られ"
    if len(replay["steps"]) <= 80:
        return "短期崩壊(80step以内)"
    return "その他(長期戦で失速)"


def opening_basics(replay: dict, seat: int) -> int | None:
    """初手でバトル場に置ける Basic の選択肢数(=手札のBasic枚数)。"""
    for step in replay["steps"][:6]:
        if step[seat].get("status") != "ACTIVE":
            continue
        sel = step[seat].get("observation", {}).get("select")
        if sel and sel.get("type") == 1 and sel.get("context") == 1:
            return len(sel.get("option") or [])
    return None


def overage_used(replay: dict, seat: int) -> float | None:
    tr = [s[seat].get("observation", {}).get("remainingOverageTime") for s in replay["steps"]]
    tr = [x for x in tr if x is not None]
    return 600.0 - min(tr) if tr else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--out")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    by_deck: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [win, n]
    causes: dict[str, Counter] = defaultdict(Counter)
    by_basics: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    times: list[float] = []
    skipped = 0

    for ep in episode_ids(args.submission):
        rep = load_replay(ep)
        if rep is None:
            skipped += 1
            continue
        names = rep.get("info", {}).get("TeamNames", [])
        if TEAM_NAME not in names:
            skipped += 1
            continue
        seat = names.index(TEAM_NAME)
        reward = rep["rewards"][seat]
        opp_deck = rep["steps"][1][1 - seat].get("action")
        if not opp_deck or len(opp_deck) != 60:
            skipped += 1
            continue
        key = archetype(opp_deck)
        by_deck[key][1] += 1
        if reward == 1:
            by_deck[key][0] += 1
        else:
            causes[key][loss_cause(rep, seat)] += 1
        nb = opening_basics(rep, seat)
        if nb is not None:
            by_basics[nb][1] += 1
            if reward == 1:
                by_basics[nb][0] += 1
        t = overage_used(rep, seat)
        if t is not None:
            times.append(t)

    total = sum(v[1] for v in by_deck.values())
    wins = sum(v[0] for v in by_deck.values())
    print(f"submission {args.submission}: {total}戦 勝率 {100 * wins / max(1, total):.1f}% (取得失敗 {skipped})\n")
    print("=== 相手デッキ別 ===")
    for key, (w, n) in sorted(by_deck.items(), key=lambda x: -x[1][1]):
        print(f"  {key:34s} n={n:3d} ({100 * n / total:4.1f}%)  勝率 {100 * w / n:5.1f}%")
        for cause, cnt in causes[key].most_common(3):
            print(f"       敗因 {cause:24s} {cnt}")
    print("\n=== 初手Basic枚数別 ===")
    for k in sorted(by_basics):
        w, n = by_basics[k]
        print(f"  Basic {k}枚: n={n:3d}  勝率 {100 * w / n:5.1f}%")
    if times:
        times.sort()
        print(f"\n=== 消費思考時間(600s/試合中) === median {times[len(times) // 2]:.0f}s"
              f"  p90 {times[int(0.9 * len(times))]:.0f}s  max {times[-1]:.0f}s")

    if args.out:
        payload = {
            "submission": args.submission,
            "games": total,
            "wins": wins,
            "by_opponent_deck": {k: {"wins": v[0], "games": v[1],
                                     "loss_causes": dict(causes[k])} for k, v in by_deck.items()},
            "by_opening_basics": {str(k): {"wins": v[0], "games": v[1]} for k, v in by_basics.items()},
            "overage_used_seconds": {"median": times[len(times) // 2] if times else None,
                                     "p90": times[int(0.9 * len(times))] if times else None,
                                     "max": times[-1] if times else None},
        }
        with open(args.out, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
