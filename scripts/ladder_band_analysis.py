#!/usr/bin/env python3
"""最終提出の公開リプレイを最終LBと結合し、相手の最終レート帯ごとに
(a) 相手アーキタイプの構成 (b) 自分の勝率 を出す。Writeup用。

    .venv/bin/python scripts/ladder_band_analysis.py 55565273:Ogerpon 55565063:Grimmsnarl \
        --lb results/lb_final_20260905.csv --out results/ladder_band_20260906
"""
import argparse, csv, json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ladder_matchups import episode_ids, load_replay, archetype, TEAM_NAME  # noqa: E402

MAJOR = {"Grimmsnarl+Froslass": "Grimmsnarl", "Grimmsnarl": "Grimmsnarl", "Alakazam": "Alakazam",
         "Ogerpon": "Ogerpon", "Kangaskhan": "Kangaskhan", "Kangaskhan+Ogerpon": "Kangaskhan",
         "Dragapult": "Dragapult", "Lucario": "Lucario", "Froslass+Lopunny": "Lopunny", "Lopunny": "Lopunny",
         "Archaludon+Cinderace": "Archaludon", "Garchomp": "Garchomp"}
BANDS = [(-1e9, 700, "<700"), (700, 800, "700-800"), (800, 900, "800-900"), (900, 1000, "900-1000"), (1000, 1e9, "1000+")]


def band(x):
    for lo, hi, name in BANDS:
        if lo <= x < hi:
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subs", nargs="+", help="sub_id:label")
    ap.add_argument("--lb", required=True)
    ap.add_argument("--out", required=True, help="出力プレフィックス(.csv/.jsonを付けて書く)")
    a = ap.parse_args()
    lb = {r["TeamName"]: float(r["Score"]) for r in csv.DictReader(open(a.lb, encoding="utf-8-sig"))}
    rows = []
    for spec in a.subs:
        sub, label = spec.split(":")
        for ep in episode_ids(sub):
            rep = load_replay(ep)
            if rep is None:
                continue
            names = rep.get("info", {}).get("TeamNames", [])
            if TEAM_NAME not in names:
                continue
            seat = names.index(TEAM_NAME)
            opp = names[1 - seat]
            deck = rep["steps"][1][1 - seat].get("action")
            if not deck or len(deck) != 60:
                continue
            arch = archetype(deck)
            rows.append({"agent": label, "sub": sub, "episode": ep, "opponent": opp,
                         "opp_final_rating": lb.get(opp), "opp_archetype": arch,
                         "opp_major": MAJOR.get(arch, "other"), "win": int(rep["rewards"][seat] == 1),
                         "seat": seat, "steps": len(rep["steps"])})
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # aggregates
    summary = {}
    for label in sorted({r["agent"] for r in rows}):
        rs = [r for r in rows if r["agent"] == label]
        matched = [r for r in rs if r["opp_final_rating"] is not None]
        by_band = defaultdict(lambda: {"n": 0, "wins": 0, "arch": Counter()})
        for r in matched:
            b = band(r["opp_final_rating"])
            by_band[b]["n"] += 1; by_band[b]["wins"] += r["win"]; by_band[b]["arch"][r["opp_major"]] += 1
        summary[label] = {"games": len(rs), "matched_to_lb": len(matched),
                          "by_band": {b: {"n": v["n"], "win_rate": round(v["wins"] / v["n"], 3) if v["n"] else None,
                                          "arch_share": {k: round(c / v["n"], 3) for k, c in v["arch"].most_common()}}
                                      for b, v in sorted(by_band.items(), key=lambda kv: [x[2] for x in BANDS].index(kv[0]))}}
        # per (band, major) win rate
        cell = defaultdict(lambda: [0, 0])
        for r in matched:
            k = (band(r["opp_final_rating"]), r["opp_major"]); cell[k][1] += 1; cell[k][0] += r["win"]
        summary[label]["by_band_major"] = {f"{b}|{m}": {"n": n, "win_rate": round(w / n, 3)} for (b, m), (w, n) in cell.items()}
    json.dump(summary, open(a.out + ".json", "w"), ensure_ascii=False, indent=1)
    for label, s in summary.items():
        print(f"== {label}: games={s['games']} matched={s['matched_to_lb']}")
        for b, v in s["by_band"].items():
            top = ", ".join(f"{k} {100*p:.0f}%" for k, p in list(v["arch_share"].items())[:4])
            print(f"  {b:9s} n={v['n']:4d} win={100*(v['win_rate'] or 0):5.1f}%  | {top}")


if __name__ == "__main__":
    main()
