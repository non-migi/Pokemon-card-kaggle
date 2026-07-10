"""自分の提出ごとのラダー成績(対戦数・勝率)を集計する。

使い方:
    .venv/bin/python scripts/ladder_stats.py            # 全提出
    .venv/bin/python scripts/ladder_stats.py 54524748   # 指定提出のみ

リプレイはキャッシュディレクトリに保存し、既取得分は再ダウンロードしない。
"""

import glob
import json
import os
import subprocess
import sys

TEAM_NAME = "gogogozi migimimi"
CACHE = os.path.expanduser("~/.cache/ptcg-replays")


def kg(*args) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=180)
    return r.stdout


def my_submissions() -> list[tuple[str, str]]:
    out = kg("competitions", "submissions", "-c", "pokemon-tcg-ai-battle")
    subs = []
    for l in out.splitlines():
        parts = l.split()
        if parts and parts[0].isdigit():
            subs.append((parts[0], parts[1]))
    return subs


def episodes_of(sub_id: str) -> list[tuple[str, str]]:
    out = kg("competitions", "episodes", sub_id)
    eps = []
    for l in out.splitlines():
        parts = l.split()
        if parts and parts[0].isdigit():
            eps.append((parts[0], parts[-1]))  # (episode_id, type)
    return eps


def fetch_replay(ep_id: str) -> dict | None:
    path = os.path.join(CACHE, f"episode-{ep_id}-replay.json")
    if not os.path.exists(path):
        kg("competitions", "replay", ep_id, "-p", CACHE)
    matches = glob.glob(os.path.join(CACHE, f"*{ep_id}*replay.json"))
    if not matches:
        return None
    try:
        return json.load(open(matches[0]))
    except Exception:
        return None


def stats_for(sub_id: str, fname: str) -> None:
    eps = episodes_of(sub_id)
    pub = [(e, t) for e, t in eps if "VALIDATION" not in t]
    w = l = d = skip = 0
    for ep_id, _ in pub:
        rep = fetch_replay(ep_id)
        if rep is None:
            skip += 1
            continue
        names = rep.get("info", {}).get("TeamNames", [])
        if TEAM_NAME not in names:
            skip += 1
            continue
        seat = names.index(TEAM_NAME)
        r = (rep.get("rewards") or [None, None])[seat]
        if r == 1:
            w += 1
        elif r == -1:
            l += 1
        else:
            d += 1
    n = w + l + d
    wr = (w + 0.5 * d) / n * 100 if n else 0.0
    print(f"{fname} (sub {sub_id}): {n}戦 {w}勝{l}敗{d}分 勝率{wr:.1f}%" + (f" (取得失敗{skip})" if skip else ""))


def main():
    os.makedirs(CACHE, exist_ok=True)
    targets = sys.argv[1:]
    for sub_id, fname in my_submissions():
        if targets and sub_id not in targets:
            continue
        stats_for(sub_id, fname)


if __name__ == "__main__":
    main()
