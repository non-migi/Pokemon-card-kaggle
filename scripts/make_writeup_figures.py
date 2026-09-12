#!/usr/bin/env python3
"""Strategy Writeup の図(fig1..fig10)を一括生成する。

    .venv/bin/python scripts/make_writeup_figures.py [--out docs/writeup/figures]

データ源(すべてリポジトリ内):
  fig1  results/final_convergence_log.csv
  fig2  results/ladder_matchups_{v60o,v512g}_final_20260905.json
  fig3  results/lb_final_20260905.csv
  fig4  docs/experiments.md の確定値(定数として埋め込み)
  fig5  docs/versions.md / models/*/META.json の確定値(定数)
  fig6  概念図(定数)
  fig7  STATUS.md のメタ時系列(定数)
  fig8  decks/meta/*.csv + data/strategy/EN_Card_Data.csv
  fig9  results/ladder_band_final_20260906.csv
  fig10 results/ladder_band_model_20260906.json

方針: 文字の重なりを作らない。ラベルは棒/線の外側に置くか、凡例へ逃がす。
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DPI = 200
BRONZE, SILVER, GOLD, OURS = 853.7, 924.0, 1130.9, 905.8
C_OGER, C_GRIM = "#2f8f4e", "#2b5fa8"

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def p(*parts):
    return os.path.join(ROOT, *parts)


#: 線や棒の上に重なっても読めるよう、注記の背後を白で抜く
HALO = dict(boxstyle="round,pad=0.16", fc="white", ec="none", alpha=0.88)


def wilson(w, n, z=1.96):
    if not n:
        return 0.0, 0.0, 0.0
    ph = w / n
    c = (ph + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * ph, 100 * max(0.0, c - h), 100 * min(1.0, c + h)


# --------------------------------------------------------------------------- fig1
def fig1(out):
    rows = [r for r in csv.DictReader(open(p("results/final_convergence_log.csv"))) if r["score"]]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["name"]].append((dt.datetime.fromisoformat(r["utc"]), float(r["score"]), int(r["episodes"])))

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=DPI)
    label = {"v6.0o": "Ogerpon agent (slot 1) — final 905.8",
             "v5.12g": "Grimmsnarl agent (slot 2) — final 834.6"}
    for k, c in [("v6.0o", C_OGER), ("v5.12g", C_GRIM)]:
        pts = sorted(by[k])
        ax.plot([x[0] for x in pts], [x[1] for x in pts], marker="o", ms=3.2, lw=1.6, color=c, label=label[k], zorder=3)
    last = max(x[0] for x in by["v6.0o"])

    ax.set_ylim(690, 960)
    for y, t in [(BRONZE, "bronze line 853.7"), (SILVER, "silver line 924.0")]:
        ax.axhline(y, ls="--", lw=0.9, color="#999", zorder=1)
        ax.text(last, y + 3, t, fontsize=7.5, color="#777", ha="right", va="bottom")

    stop = dt.datetime(2026, 8, 31, 23, 44)
    ax.axvline(stop, ls=":", lw=1.2, color="#333", zorder=2)
    ax.annotate("ladder stopped\nAug 31, 23:44 UTC", xy=(stop, 942), xytext=(-8, 0),
                textcoords="offset points", fontsize=7.5, ha="right", va="center", color="#333")

    # the first days are the high-uncertainty phase of the rating system
    ax.axvspan(dt.datetime(2026, 8, 16, 12), dt.datetime(2026, 8, 18, 12), color="#f0a30a", alpha=0.10, zorder=0)
    ax.annotate("first ~50 games:\nswings of ±100", xy=(dt.datetime(2026, 8, 17, 12), 735),
                fontsize=7.5, color="#a1701a", ha="center", va="center", bbox=HALO, zorder=4)

    # game-count milestones; white halo so a crossing line never cuts the text
    offsets = {306: (0, 11, "center"), 581: (0, 11, "center"),
               318: (0, 12, "center"), 579: (0, -17, "center")}
    for k, c in [("v6.0o", C_OGER), ("v5.12g", C_GRIM)]:
        for x, y, n in sorted(by[k]):
            if n in offsets:
                dx, dy, ha = offsets[n]
                ax.annotate(f"{n} games", (x, y), fontsize=7, color=c, xytext=(dx, dy),
                            textcoords="offset points", ha=ha, va="center", bbox=HALO, zorder=4)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=4))
    ax.set_ylabel("ladder rating")
    ax.set_xlabel("date (UTC).  Competition deadline: Aug 16, 23:59")
    ax.set_title("Post-deadline rating trajectories of the two final submissions")
    ax.legend(loc="lower right", framealpha=0.95)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig1_convergence.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig2
ORDER = ["Grimmsnarl+Froslass", "Alakazam", "Ogerpon", "Dragapult", "Archaludon+Cinderace",
         "(other)", "Froslass+Lopunny", "Kangaskhan", "Lucario", "Kangaskhan+Ogerpon", "Garchomp"]
NICE = {"Grimmsnarl+Froslass": "Grimmsnarl (Froslass)", "Froslass+Lopunny": "Lopunny (Froslass)",
        "(other)": "other / rare decks", "Archaludon+Cinderace": "Archaludon+Cinderace",
        "Kangaskhan+Ogerpon": "Kangaskhan+Ogerpon"}


def fig2(out):
    data = {"Ogerpon agent (slot 1)": json.load(open(p("results/ladder_matchups_v60o_final_20260905.json"))),
            "Grimmsnarl agent (slot 2)": json.load(open(p("results/ladder_matchups_v512g_final_20260905.json")))}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), dpi=DPI, sharey=True)
    for ax, (name, d) in zip(axes, data.items()):
        b, tot = d["by_opponent_deck"], d["games"]
        ws, los, his, ns = [], [], [], []
        for k in ORDER:
            v = b.get(k, {"wins": 0, "games": 0})
            w, lo, hi = wilson(v["wins"], v["games"])
            ws.append(w), los.append(lo), his.append(hi), ns.append(v["games"])
        y = np.arange(len(ORDER))
        cols = ["#2f8f4e" if w >= 55 else ("#c0392b" if w < 45 else "#8a8a8a") for w in ws]
        ax.barh(y, ws, color=cols, alpha=0.92,
                xerr=[np.array(ws) - np.array(los), np.array(his) - np.array(ws)],
                ecolor="#333", capsize=2.5, error_kw={"lw": 0.9})
        ax.axvline(50, color="k", lw=0.9, ls="--")
        ax.set_yticks(y)
        ax.set_yticklabels([f"{NICE.get(k, k)}   n={n} ({100*n/tot:.0f}%)" for k, n in zip(ORDER, ns)], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, 122)
        ax.set_xticks([0, 20, 40, 60, 80, 100])
        ax.set_xlabel("win rate %  (bar = point estimate, whisker = Wilson 95% CI)")
        ax.set_title(f"{name}\noverall {100*d['wins']/tot:.1f}% over {tot} games")
        ax.grid(alpha=0.3, axis="x")
        for yi, w, hi in zip(y, ws, his):  # always outside the whisker: never collides
            ax.text(hi + 2.5, yi, f"{w:.0f}%", va="center", ha="left", fontsize=8, fontweight="bold",
                    color="#222")
    fig.suptitle("Per-opponent-archetype results of the two final submissions (1,000 ladder games each)")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig2_matchups.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig3
def fig3(out):
    rows = list(csv.DictReader(open(p("results/lb_final_20260905.csv"), encoding="utf-8-sig")))
    sc = [float(r["Score"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.0), dpi=DPI)
    ax.hist(sc, bins=90, color="#c9c9c9", edgecolor="white", lw=0.4)
    ax.set_xlim(-150, 1450)
    handles = []
    for x, lab, c, ls in [(BRONZE, "bronze line  853.7  (rank 680)", "#b5762a", "--"),
                          (SILVER, "silver line  924.0  (rank 340)", "#7a7a7a", "--"),
                          (GOLD, "gold line  1130.9  (rank 23)", "#c9a227", "--"),
                          (OURS, "our team  905.8  (rank 429 of 6,807)", "#1f4e9c", "-")]:
        lw = 2.2 if x == OURS else 1.2
        ax.axvline(x, color=c, ls=ls, lw=lw, zorder=3)
        handles.append(Line2D([0], [0], color=c, ls=ls, lw=lw, label=lab))
    ymax = ax.get_ylim()[1]
    ax.annotate("us", xy=(OURS, ymax * 0.52), xytext=(OURS + 190, ymax * 0.72),
                fontsize=9, fontweight="bold", color="#1f4e9c", ha="left",
                arrowprops=dict(arrowstyle="->", color="#1f4e9c", lw=1.2))
    ax.legend(handles=handles, loc="upper left", framealpha=0.95, fontsize=8)
    ax.set_xlabel("final ladder rating")
    ax.set_ylabel("number of teams")
    ax.set_title("Final leaderboard distribution — 6,807 teams (Sep 5, 2026)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig3_lb_distribution.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig4
def fig4(out):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 4.2), dpi=DPI)
    # left: production ladder
    bars = ax1.bar([0, 1], [840.0, 751.6], color=[C_OGER, "#c0392b"], width=0.55)
    ax1.set_ylim(600, 920)
    ax1.set_xticks([0, 1])
    ax1.set_xticklabels(["pure imitation\n(v5.1g, 210 games)", "imitation + search\n(v5.0g, 158 games)"], fontsize=8)
    ax1.set_ylabel("ladder rating")
    ax1.set_xlabel("axis starts at 600, the rating every submission begins from", fontsize=7.5, color="#666")
    ax1.set_title("Production ladder\nsame deck, same weights", fontsize=9.5)
    for b, v in zip(bars, [840.0, 751.6]):
        ax1.text(b.get_x() + b.get_width() / 2, v + 7, f"{v:.1f}", ha="center", fontsize=9.5, fontweight="bold")
    ax1.annotate("", xy=(0.98, 770), xytext=(0.02, 858),
                 arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.4,
                                 connectionstyle="arc3,rad=-0.12"))
    ax1.text(0.5, 845, "−88.4 rating", ha="center", fontsize=10, fontweight="bold", color="#c0392b", bbox=HALO)
    ax1.grid(alpha=0.3, axis="y")
    # right: local wall
    bars = ax2.bar([0, 1], [67.1, 46.0], color=[C_OGER, "#c0392b"], width=0.55)
    ax2.set_ylim(0, 100)
    ax2.axhline(50, ls="--", lw=0.9, color="k", zorder=1)
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["pure imitation\n(400 games)", "imitation + search\n(200 games)"], fontsize=8)
    ax2.set_ylabel("win rate against the same Grimmsnarl wall (%)", fontsize=8)
    ax2.set_xlabel("dashed line = 50%", fontsize=7.5, color="#666")
    ax2.set_title("Local sparring wall\nsame deck, same weights", fontsize=9.5)
    ax2.text(0, 67.1 + 2.5, "67.1%", ha="center", fontsize=9.5, fontweight="bold", zorder=4)
    ax2.text(1, 46.0 - 5.0, "46.0%", ha="center", fontsize=9.5, fontweight="bold", color="white", zorder=4)
    ax2.annotate("", xy=(0.98, 51), xytext=(0.02, 72),
                 arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.4, connectionstyle="arc3,rad=-0.12"))
    ax2.text(0.5, 78, "−21.1 points", ha="center", fontsize=10, fontweight="bold", color="#c0392b", bbox=HALO)
    ax2.grid(alpha=0.3, axis="y")
    fig.suptitle("Adding determinized search on top of the imitation policy hurt, in production and locally")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig4_search_ab.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig5
def fig5(out):
    rows = [["bc_grim", "Jul 25", "1.64 M", "100", "—", "70.3%", "first archetype-specific policy"],
            ["bc_grim2", "Aug 1", "1.83 M", "182", "143", "74.0%", "ladder 840 (pure) vs 752 (with search)"],
            ["bc_grim3", "Aug 8", "2.76 M", "329", "186", "74.6%", "mirror vs grim2:  54.9% / 400"],
            ["bc_grim5", "Aug 10", "3.03 M", "—", "196", "74.2%", "mirror vs grim3:  46.1% / 400"],
            ["bc_grim6", "Aug 11", "3.16 M", "394", "203", "74.7%", "mirror vs grim3:  47.1% / 400"],
            ["bc_grim7  (shipped)", "Aug 16", "3.47 M", "470", "211", "75.6%", "mirror vs grim3:  56.9% / 400  [52.0–61.6]"],
            ["bc_ogerpon  (shipped)", "Aug 10", "0.39 M", "86", "176", "69.2%", "beat our best Grim agents 90–99% as a wall"]]
    cols = ["model", "trained", "winner-side\ndecisions", "winner\nteams", "card\nvocab", "holdout\ntop-1", "key evidence"]
    fig, ax = plt.subplots(figsize=(10, 2.9), dpi=DPI)
    ax.axis("off")
    t = ax.table(cellText=rows, colLabels=cols, loc="center", cellLoc="left", colLoc="left",
                 colWidths=[0.165, 0.075, 0.10, 0.075, 0.065, 0.075, 0.40])
    t.auto_set_font_size(False)
    t.set_fontsize(8)
    t.scale(1, 1.55)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#bbb")
        cell.PAD = 0.04
        if r == 0:
            cell.set_facecolor("#e6e6e6")
            cell.set_text_props(fontweight="bold")
        elif r in (6, 7):
            cell.set_facecolor("#e8f1fb")
            cell.set_text_props(fontweight="bold")
    ax.set_title("Behaviour-cloning model family: more days of winner replays → larger vocabulary → higher fidelity",
                 pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig5_model_family.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig6
def fig6(out):
    fig, ax = plt.subplots(figsize=(10, 4.4), dpi=DPI)
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)

    def box(x, y, w, h, text, fc, fs=8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=fc, ec="#555", lw=1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, color="#333", lw=1.1))

    ax.text(0.1, 4.18, "OFFLINE  (repeated daily)", fontsize=9, fontweight="bold", color="#1f4e9c")
    ax.text(6.15, 4.18, "RUNTIME  (one decision, < 1 ms)", fontsize=9, fontweight="bold", color="#b03a2e")
    box(0.1, 3.05, 2.7, 0.85, 'Official "Daily Top" replays\n(winning teams, 20 days)', "#e8f0fb")
    box(0.1, 1.80, 2.7, 0.95, "Keep winner-side decisions only.\nFilter by deck: key card ≥ 4 copies\n(removes mill-deck contamination)", "#e8f0fb", 7.5)
    box(0.1, 0.55, 2.7, 0.85, "Modal 60-card list of those\nsame winning teams → deck.csv", "#fff2df", 7.5)
    box(3.25, 1.80, 2.6, 0.95, "Two-tower ranker\n94-d state MLP · 48-d option MLP\n+ 16-d card embedding, CE loss", "#e8f0fb", 7.5)
    box(3.25, 0.55, 2.6, 0.85, "policy_params.npz (150 KB)\nholdout top-1  75.6% / 69.2%", "#e8f0fb", 7.5)
    arrow(1.45, 3.05, 1.45, 2.78)
    arrow(1.45, 1.80, 1.45, 1.43)
    arrow(2.8, 2.28, 3.25, 2.28)
    arrow(4.55, 1.80, 4.55, 1.43)
    ax.plot([6.02, 6.02], [0.3, 4.05], ls="--", color="#aaa", lw=1)
    box(6.2, 3.05, 3.7, 0.72, "observation:  public state  +  list of legal options", "#fdecea", 8)
    box(6.2, 2.10, 3.7, 0.72, "1.  OHKO guard (Grimmsnarl agent only)\n     veto moves into a computable one-hit-KO range", "#fdecea", 7.5)
    box(6.2, 1.15, 3.7, 0.72, "2.  imitation policy argmax  (multi-select: top-N)", "#fdecea", 7.5)
    box(6.2, 0.20, 3.7, 0.72, "3.  fallback: priority heuristics → first legal option\n     (on exception or out-of-distribution; never crashes)", "#fdecea", 7.5)
    arrow(8.05, 3.05, 8.05, 2.85)
    arrow(8.05, 2.10, 8.05, 1.90)
    arrow(8.05, 1.15, 8.05, 0.95)
    ax.add_patch(FancyArrowPatch((5.85, 0.98), (6.2, 1.45), arrowstyle="-|>", mutation_scale=12,
                                 color="#333", lw=1.1, connectionstyle="arc3,rad=0.15"))
    ax.text(2.95, 0.22, "deck.csv and the weights are shipped together as one artefact",
            fontsize=7.5, ha="center", color="#444", style="italic")
    ax.set_title("Pipeline: imitate the winners of the archetype you play, and ship deck and policy as a pair")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig6_pipeline.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig7
def fig7(out):
    days = ["Jul 22", "Jul 26", "Jul 28", "Jul 30", "Jul 31", "Aug 5", "Aug 7"]
    series = [("Grimmsnarl", [33.6, 53.2, 55.8, 58.4, 62.7, 40.6, 41.9], "#2b5fa8"),
              ("Alakazam", [34.5, 26.2, 20.1, 16.8, 13.4, 24.3, 24.2], "#e08b3c"),
              ("Kangaskhan", [9.2, 6.4, 13.0, 16.1, 15.5, 13.0, 13.4], "#2f8f4e"),
              ("Lopunny", [4.2, 2.1, 0.6, 2.7, 3.5, 8.3, 12.4], "#c0392b"),
              ("Ogerpon", [0, 0, 0, 0, 2.8, 10.5, 9.1], "#7d5ba6")]
    fig, ax = plt.subplots(figsize=(8, 4.0), dpi=DPI)
    for name, ys, c in series:
        ax.plot(days, ys, marker="o", ms=4, lw=1.8, color=c, label=name)
    ax.text(0.30, 0.63, "Ogerpon: 0% → 9-12% in two weeks.\nWe cloned its winners for the final submission.",
            transform=ax.transAxes, fontsize=7.5, color="#7d5ba6", ha="center", va="center", bbox=HALO)
    ax.set_ylim(-2, 70)
    ax.set_ylabel("share of winning teams in the official Daily Top (%)")
    ax.set_xlabel("date (2026)")
    ax.set_title("Metagame drift: Grimmsnarl peaked and fell back, Ogerpon appeared from zero")
    ax.legend(loc="upper right", ncol=2, framealpha=0.95)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig7_meta_timeseries.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig8
def _cards():
    m = {}
    for r in csv.DictReader(open(p("data/strategy/EN_Card_Data.csv"), encoding="utf-8-sig")):
        cid = r["Card ID"].strip()
        if cid and cid not in m:
            m[cid] = (r["Card Name"], r["Stage (Pokémon)/Type (Energy and Trainer)"])
    return m


def _deck(path, cards):
    c = collections.Counter(l.strip() for l in open(p(path)) if l.strip())
    rows = []
    for cid, k in c.items():
        nm, st = cards.get(cid, ("?", "?"))
        g = "Pokémon" if st.endswith("Pokémon") else ("Energy" if "Energy" in st else "Trainer")
        rows.append((g, st, nm, cid, k))
    go = {"Pokémon": 0, "Trainer": 1, "Energy": 2}
    so = {"Basic Pokémon": 0, "Stage 1 Pokémon": 1, "Stage 2 Pokémon": 2,
          "Item": 0, "Pokémon Tool": 1, "Supporter": 2, "Stadium": 3,
          "Basic Energy": 0, "Special Energy": 1}
    rows.sort(key=lambda r: (go[r[0]], so.get(r[1], 9), -r[4], r[2]))
    return rows


def fig8(out):
    cards = _cards()
    decks = {"ogerpon": _deck("decks/meta/snapshot_20260809_ogerpon_teal.csv", cards),
             "grimmsnarl": _deck("decks/meta/snapshot_20260723_grim_top8.csv", cards)}
    for name, rows in decks.items():
        with open(p(f"docs/writeup/deck_{name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["count", "card_name", "card_id", "group", "stage_or_type"])
            for g, st, nm, cid, k in rows:
                w.writerow([k, nm, cid, g, st])
    title = {"ogerpon": "Deck A — Teal Mask Ogerpon ex\nagent v6.0o, final rating 905.8",
             "grimmsnarl": "Deck B — Marnie's Grimmsnarl ex / Froslass\nagent v5.12g, final rating 834.6"}
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 5.4), dpi=DPI)
    for ax, name in zip(axes, ["ogerpon", "grimmsnarl"]):
        ax.axis("off")
        rows = decks[name]
        ax.text(0, 1.0, title[name], fontsize=9.5, fontweight="bold", va="top", transform=ax.transAxes)
        y, cur = 0.885, None
        for g, st, nm, cid, k in rows:
            if g != cur:
                cur = g
                n = sum(r[4] for r in rows if r[0] == g)
                ax.text(0, y, f"{g}  —  {n} cards", fontsize=8.5, fontweight="bold", color="#1f4e9c",
                        transform=ax.transAxes)
                y -= 0.042
            ax.text(0.035, y, f"{k}×", fontsize=8, transform=ax.transAxes, fontfamily="monospace")
            ax.text(0.10, y, nm, fontsize=8, transform=ax.transAxes)
            ax.text(0.62, y, st, fontsize=7, color="#777", transform=ax.transAxes)
            y -= 0.036
    fig.suptitle("Final 60-card deck lists — the modal list of the winning teams we cloned (card IDs in the attached CSVs)",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig8_decklists.png"))
    plt.close(fig)


# --------------------------------------------------------------------------- fig9 / fig10
BANDS = ["<700", "700-800", "800-900", "900-1000", "1000+"]
MAJORS = ["Grimmsnarl", "Alakazam", "Ogerpon", "Kangaskhan", "Dragapult",
          "Lucario", "Lopunny", "Archaludon", "Garchomp", "other"]
MCOL = dict(zip(MAJORS, ["#2b5fa8", "#e08b3c", "#2f8f4e", "#c0392b", "#7d5ba6",
                         "#8d6e5c", "#d98cc0", "#8a8a8a", "#c9b458", "#dcdcdc"]))


def _band(x):
    x = float(x)
    return "<700" if x < 700 else "700-800" if x < 800 else "800-900" if x < 900 else "900-1000" if x < 1000 else "1000+"


def fig9(out):
    rows = list(csv.DictReader(open(p("results/ladder_band_final_20260906.csv"))))
    S = json.load(open(p("results/ladder_band_final_20260906.json")))
    pool = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["opp_final_rating"]:
            pool[_band(r["opp_final_rating"])][r["opp_major"]] += 1
    ns = [sum(pool[b].values()) for b in BANDS]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.8), dpi=DPI, gridspec_kw={"width_ratios": [1.15, 1]})
    x = np.arange(len(BANDS))
    bottom = np.zeros(len(BANDS))
    for m in MAJORS:
        vals = np.array([100 * pool[b][m] / ns[i] if ns[i] else 0 for i, b in enumerate(BANDS)])
        ax1.bar(x, vals, bottom=bottom, color=MCOL[m], label=m, edgecolor="white", lw=0.6)
        for i, v in enumerate(vals):
            if v >= 8:
                ax1.text(i, bottom[i] + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                         color="white" if m != "other" else "#444", fontweight="bold")
        bottom += vals
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{b}\nn={n}" for b, n in zip(BANDS, ns)])
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("share of opponents met (%)")
    ax1.set_xlabel("opponent's final rating band")
    ax1.set_title("Who you meet depends on the band\n(1,983 games, opponents joined to the final leaderboard)", fontsize=9.5)
    ax1.legend(fontsize=7.5, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False)

    for label, key, c, dy in [("Ogerpon agent (slot 1)", "Ogerpon", C_OGER, 13),
                              ("Grimmsnarl agent (slot 2)", "Grimmsnarl", C_GRIM, -17)]:
        bb = S[key]["by_band"]
        xs = [b for b in BANDS if b in bb and bb[b]["n"] >= 20]
        ys = [100 * bb[b]["win_rate"] for b in xs]
        ax2.plot(xs, ys, marker="o", ms=5, lw=1.8, color=c, label=label, zorder=3)
        for i, (xx, yy, b) in enumerate(zip(xs, ys, xs)):
            ha = "left" if i == 0 else ("right" if i == len(xs) - 1 else "center")
            dx = -6 if ha == "right" else (6 if ha == "left" else 0)
            ax2.annotate(f"{yy:.0f}%  n={bb[b]['n']}", (xx, yy), fontsize=7.5, color=c, ha=ha,
                         va="center", xytext=(dx, dy), textcoords="offset points", bbox=HALO, zorder=5)
    ax2.axhline(50, ls="--", color="k", lw=0.9)
    ax2.set_ylim(0, 100)
    ax2.set_xlim(-0.45, 4.45)
    ax2.set_ylabel("our win rate (%)")
    ax2.set_xlabel("opponent's final rating band")
    ax2.set_title("...and so does each agent's win rate\n(bands with n ≥ 20)", fontsize=9.5)
    ax2.legend(loc="lower left", framealpha=0.95)
    ax2.grid(alpha=0.3)
    fig.suptitle("Rating-band ecology: the specialist thrives where Grimmsnarl is ~60% of the pool and stalls where it is ~30%",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig9_band_ecology.png"))
    plt.close(fig)


def fig10(out):
    M = json.load(open(p("results/ladder_band_model_20260906.json")))
    S = json.load(open(p("results/ladder_band_final_20260906.json")))
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2), dpi=DPI, sharey=True)
    for ax, key, name, c in [(axes[0], "Ogerpon", "Ogerpon agent (slot 1)", C_OGER),
                             (axes[1], "Grimmsnarl", "Grimmsnarl agent (slot 2)", C_GRIM)]:
        bb = S[key]["by_band"]
        xs = [b for b in BANDS if b in bb and bb[b]["n"] >= 20]
        obs = [100 * bb[b]["win_rate"] for b in xs]
        pred = [100 * M["predicted_by_band"][key][b] for b in xs]
        ax.plot(xs, pred, marker="s", ms=5, ls="--", lw=1.6, color=c, alpha=0.75,
                label="predicted from band composition alone", zorder=3)
        ax.plot(xs, obs, marker="o", ms=5, lw=1.9, color=c, label="observed win rate", zorder=3)
        for i, (xx, yy, b) in enumerate(zip(xs, obs, xs)):
            above = yy >= pred[i]
            ax.annotate(f"n={bb[b]['n']}", (xx, yy), fontsize=7, color=c, ha="center", va="center",
                        xytext=(0, 14 if above else -14), textcoords="offset points", bbox=HALO, zorder=5)
        ax.axhline(50, ls=":", color="k", lw=0.9)
        ax.set_ylim(0, 100)
        ax.set_xlim(-0.4, len(xs) - 0.6)
        ax.set_title(name, fontsize=9.5)
        ax.set_xlabel("opponent's final rating band")
        ax.grid(alpha=0.3)
        ax.legend(loc="lower left", fontsize=7.5, framealpha=0.95)
    axes[0].set_ylabel("win rate (%)")
    fig.suptitle("Band composition × per-archetype win rate reproduces the win rate per band, with no band-specific fitting",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig10_ecology_model.png"))
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=p("docs/writeup/figures"))
    ap.add_argument("--only", help="カンマ区切りで図番号を指定(例: 1,3,9)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fns = {1: fig1, 2: fig2, 3: fig3, 4: fig4, 5: fig5, 6: fig6, 7: fig7, 8: fig8, 9: fig9, 10: fig10}
    want = [int(x) for x in a.only.split(",")] if a.only else sorted(fns)
    for i in want:
        fns[i](a.out)
        print(f"fig{i} written")


if __name__ == "__main__":
    main()
