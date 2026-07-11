"""レート帯ごとのデッキ遭遇率を集計する。

リーダーボードから各帯のチームをサンプリング → 最新提出のエピソードを取得 →
リプレイの両プレイヤーのデッキをアーキタイプ分類して帯別の分布を出す。
(マッチメイキングは同格同士なので、帯Xのチームの対戦に現れるデッキ ≈ 帯Xの環境)

使い方:
    .venv/bin/python scripts/band_meta.py [--teams-per-band 5] [--eps 5]
"""

import argparse
import csv
import glob
import json
import os
import random
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

CACHE = os.path.expanduser("~/.cache/ptcg-replays")
BANDS = [(550, 700), (700, 850), (850, 1000), (1000, 1400)]

import deck_lib  # noqa: E402

JP = {}
with open(os.path.join(ROOT, "data/strategy/JP_Card_Data.csv")) as f:
    for r in csv.DictReader(f):
        JP[int(r["カード ID"])] = r["カード名"]

RULES = [
    ("フーディン型", {"フーディン"}),
    ("オーロンゲ型", {"マリィのオーロンゲex", "マリィのベロバー"}),
    ("ガルーラ型", {"メガガルーラex"}),
    ("イワパレス型", {"イワパレス"}),
    ("ルカリオ型", {"メガルカリオex"}),
    ("初期デッキ系", {"メガユキノオーex", "ユキカブリ"}),
    ("ノココッチ系", {"ノココッチ"}),
    ("ブリジュラス型", {"ブリジュラスex"}),
    ("ユキメノコex型", {"メガユキメノコex"}),
    ("サーナイト型", {"メガサーナイトex"}),
    ("シロナ型", {"シロナのガチグマex", "シロナのフカマル"}),
]


def classify(deck):
    names = {JP.get(cid, "") for cid in deck if (c := deck_lib.CARDS.get(cid)) and c.cardType == 0}
    for label, keys in RULES:
        if keys & names:
            return label
    return "その他"


def kg(*args) -> str:
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=180)
    return r.stdout


def table_rows(out: str) -> list[list[str]]:
    return [l.split() for l in out.splitlines() if l.strip() and l.split()[0].isdigit()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams-per-band", type=int, default=5)
    ap.add_argument("--eps", type=int, default=5)
    ap.add_argument("--lb", default=None, help="leaderboard csv(省略時は最新をscratchpadから)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    lb_path = args.lb
    if lb_path is None:
        cands = sorted(glob.glob("/private/tmp/claude-501/*/*/scratchpad/*publicleaderboard*.csv"))
        lb_path = cands[-1]
    teams_by_band = defaultdict(list)
    with open(lb_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            score = float(r["Score"])
            for lo, hi in BANDS:
                if lo <= score < hi:
                    teams_by_band[(lo, hi)].append((r["TeamId"], r["TeamName"], score))

    os.makedirs(CACHE, exist_ok=True)
    dist = defaultdict(lambda: defaultdict(int))
    for band, teams in sorted(teams_by_band.items()):
        picked = rng.sample(teams, min(args.teams_per_band, len(teams)))
        n_replays = 0
        for tid, tname, score in picked:
            subs = table_rows(kg("competitions", "team-submissions", tid))
            if not subs:
                continue
            eps = table_rows(kg("competitions", "episodes", subs[0][0]))
            for ep_row in eps[: args.eps]:
                ep = ep_row[0]
                path = os.path.join(CACHE, f"episode-{ep}-replay.json")
                if not os.path.exists(path):
                    kg("competitions", "replay", ep, "-p", CACHE)
                hits = glob.glob(os.path.join(CACHE, f"*{ep}*replay.json"))
                if not hits:
                    continue
                try:
                    d = json.load(open(hits[0]))
                    for pi in range(2):
                        deck = d["steps"][1][pi].get("action")
                        if isinstance(deck, list) and len(deck) == 60:
                            dist[band][classify(deck)] += 1
                            n_replays += 1
                except Exception:
                    pass
        print(f"band {band}: {len(picked)}チーム {n_replays}デッキ収集", flush=True)

    print("\n=== レート帯別のデッキ遭遇率 ===")
    archetypes = sorted({a for d in dist.values() for a in d}, key=lambda a: -sum(d.get(a, 0) for d in dist.values()))
    header = "アーキタイプ".ljust(12) + "".join(f"{lo}-{hi}".rjust(12) for lo, hi in sorted(dist))
    print(header)
    for a in archetypes:
        row = a.ljust(12)
        for band in sorted(dist):
            total = sum(dist[band].values())
            share = dist[band].get(a, 0) / total * 100 if total else 0
            row += f"{share:11.1f}%"
        print(row)
    print("サンプル数".ljust(12) + "".join(f"{sum(dist[band].values()):12d}" for band in sorted(dist)))


if __name__ == "__main__":
    main()
