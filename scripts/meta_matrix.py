"""公開リプレイ全体から**アーキタイプ×アーキタイプの相性行列**を作る。

`ladder_matchups.py` が「自分 vs 相手」しか見ないのに対し、こちらは
キャッシュ済みリプレイに写っている**他人同士の対戦**も全部使う。
これで「フィールド全体でどのデッキがどのデッキに勝つか」が測れる。

アーキタイプはハードコードした名前リストではなく、ポケモン構成の
Jaccard類似でクラスタリングして決める(新種デッキを取りこぼさないため)。
ラベルは「全デッキの過半数に入る汎用ポケモン」を除いた頻出名から付ける。

使い方:
    .venv/bin/python scripts/meta_matrix.py                     # 全キャッシュ
    .venv/bin/python scripts/meta_matrix.py --min-score 1000    # 高レート帯の対戦のみ
    .venv/bin/python scripts/meta_matrix.py --out results/meta_matrix.json
"""

import argparse
import csv
import glob
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import deck_lib  # noqa: E402

CACHE = os.path.expanduser("~/.cache/ptcg-replays")
MY_TEAM = "gogogozi migimimi"
POKEMON = 0


def wilson(w: float, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z, p = 1.96, w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def pokemon_set(deck: list[int]) -> frozenset[str]:
    C = deck_lib.CARDS
    return frozenset(C[x].name for x in deck if x in C and C[x].cardType == POKEMON)


def load_games(min_len: int = 2) -> list[dict]:
    """キャッシュ内の全リプレイから (両デッキ, 勝敗, チーム名) を取り出す。"""
    games = []
    for path in sorted(glob.glob(os.path.join(CACHE, "*replay.json"))):
        base = os.path.basename(path)
        if not base.split("-")[1].isdigit():
            continue  # 自己対戦・壁テスト等のローカル生成物を除外
        try:
            d = json.load(open(path))
        except Exception:
            continue
        steps = d.get("steps") or []
        if len(steps) < min_len:
            continue
        decks = [steps[1][pi].get("action") for pi in range(2)]
        if not all(isinstance(x, list) and len(x) == 60 for x in decks):
            continue
        rewards = d.get("rewards") or [None, None]
        if rewards[0] is None or rewards[1] is None or rewards[0] == rewards[1]:
            continue  # 引分・不明は行列から除く
        names = (d.get("info") or {}).get("TeamNames") or ["?", "?"]
        games.append({
            "id": base.split("-")[1],
            "decks": decks,
            "pk": [pokemon_set(x) for x in decks],
            "winner": 0 if rewards[0] > rewards[1] else 1,
            "teams": names,
        })
    return games


def cluster(sigs: Counter, thresh: float = 0.6) -> dict[frozenset, int]:
    """ポケモン構成をJaccard類似でクラスタリング。頻出構成を核にして貪欲に併合。"""
    cores: list[frozenset] = []
    assign: dict[frozenset, int] = {}
    for sig, _ in sigs.most_common():
        best, best_j = -1, 0.0
        for i, c in enumerate(cores):
            u = len(sig | c)
            j = len(sig & c) / u if u else 0.0
            if j > best_j:
                best, best_j = i, j
        if best_j >= thresh:
            assign[sig] = best
        else:
            cores.append(sig)
            assign[sig] = len(cores) - 1
    return assign, cores


def label_clusters(assign, cores, sigs: Counter) -> list[str]:
    """クラスタ名を付ける。全体の過半数に入る汎用ポケモンは名前に使わない。"""
    total = sum(sigs.values())
    generic = {n for n in set().union(*sigs.keys()) if
               sum(c for s, c in sigs.items() if n in s) > 0.5 * total} if sigs else set()
    names = []
    for i, core in enumerate(cores):
        cnt = Counter()
        for sig, c in sigs.items():
            if assign[sig] == i:
                for n in sig:
                    cnt[n] += c
        n_games = sum(c for sig, c in sigs.items() if assign[sig] == i)
        picks = [n for n, c in cnt.most_common() if n not in generic and c >= 0.5 * n_games]
        names.append("+".join(picks[:2]) if picks else "+".join(n for n, _ in cnt.most_common(2)))
    # 同名クラスタは連番で区別
    seen = Counter()
    out = []
    for n in names:
        seen[n] += 1
        out.append(n if seen[n] == 1 else f"{n}#{seen[n]}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=float, default=0.0,
                    help="両者のLBスコアがこの値以上の対戦のみ使う")
    ap.add_argument("--lb", help="LeaderboardのCSV(TeamName,Score)")
    ap.add_argument("--min-games", type=int, default=15, help="行列に載せる最小試合数")
    ap.add_argument("--exclude-me", action="store_true", help="自チームの対戦を除外")
    ap.add_argument("--out")
    args = ap.parse_args()

    scores: dict[str, float] = {}
    if args.lb:
        for r in csv.DictReader(open(args.lb)):
            scores[r["TeamName"]] = float(r["Score"])

    games = load_games()
    if args.min_score > 0:
        if not scores:
            sys.exit("--min-score には --lb が必要")
        games = [g for g in games
                 if min(scores.get(t, -1) for t in g["teams"]) >= args.min_score]
    if args.exclude_me:
        games = [g for g in games if MY_TEAM not in g["teams"]]

    sigs = Counter()
    for g in games:
        for s in g["pk"]:
            sigs[s] += 1
    if not sigs:
        sys.exit("該当する対戦なし")
    assign, cores = cluster(sigs)
    labels = label_clusters(assign, cores, sigs)

    # 出現数と相性行列
    pop = Counter()
    pair: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])  # [win, n]
    for g in games:
        a, b = assign[g["pk"][0]], assign[g["pk"][1]]
        pop[a] += 1
        pop[b] += 1
        if a == b:
            continue
        w = g["winner"]
        pair[(a, b)][1] += 1
        pair[(b, a)][1] += 1
        pair[(a, b)][0] += 1 if w == 0 else 0
        pair[(b, a)][0] += 1 if w == 1 else 0

    tot = sum(pop.values())
    keep = [i for i, c in pop.most_common() if c >= args.min_games]
    print(f"=== 対戦 {len(games)} / デッキ出現 {tot} / クラスタ {len(cores)} "
          f"(>= {args.min_games}戦: {len(keep)}) ===\n")

    print(f"{'アーキタイプ':<38} {'出現':>6} {'シェア':>7} {'全体勝率':>9}")
    overall = {}
    for i in keep:
        w = sum(pair[(i, j)][0] for j in keep if j != i)
        n = sum(pair[(i, j)][1] for j in keep if j != i)
        overall[i] = (w, n)
        wr = w / n * 100 if n else float("nan")
        print(f"{labels[i][:37]:<38} {pop[i]:>6} {pop[i] / tot * 100:>6.1f}% "
              f"{wr:>8.1f}% ({n}戦)")

    print("\n=== 相性行列 (行が勝つ%、括弧はn) ===")
    hdr = "".join(f"{labels[j][:11]:>13}" for j in keep)
    print(f"{'':<26}{hdr}")
    for i in keep:
        row = ""
        for j in keep:
            if i == j:
                row += f"{'—':>13}"
                continue
            w, n = pair[(i, j)]
            row += f"{(f'{w / n * 100:.0f}%({n})' if n else '-'):>13}"
        print(f"{labels[i][:25]:<26}{row}")

    # フィールド分布に対する期待勝率(=ベストレスポンス)
    share = {j: pop[j] / tot for j in keep}
    ssum = sum(share.values())
    print("\n=== フィールド期待勝率 (現メタ分布に対する best response) ===")
    br = []
    for i in keep:
        num = den = 0.0
        cov = 0.0
        for j in keep:
            if i == j:
                continue
            w, n = pair[(i, j)]
            if n < 5:
                continue  # 標本が薄い対面は期待値から外す
            num += share[j] / ssum * (w / n)
            den += share[j] / ssum
            cov += share[j] / ssum
        if den > 0:
            br.append((num / den, cov, i))
    br.sort(reverse=True)
    for exp, cov, i in br:
        w, n = overall[i]
        lo, hi = wilson(w, n)
        print(f"{labels[i][:37]:<38} 期待{exp * 100:>5.1f}%  "
              f"(相性カバー率{cov * 100:.0f}% / 実績{w / n * 100:.1f}% [{lo * 100:.0f}-{hi * 100:.0f}] n={n})")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump({
            "n_games": len(games),
            "min_score": args.min_score,
            "labels": labels,
            "popularity": {labels[i]: pop[i] for i in keep},
            "share": {labels[i]: share[i] / ssum for i in keep},
            "matrix": {f"{labels[i]}|{labels[j]}": pair[(i, j)]
                       for i in keep for j in keep if i != j and pair[(i, j)][1]},
            "best_response": [{"deck": labels[i], "expected": e, "coverage": c} for e, c, i in br],
        }, open(args.out, "w"), ensure_ascii=False, indent=1)
        print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
