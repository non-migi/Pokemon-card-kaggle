"""公式トップエピソードから模倣学習(BC)用の (観測, 行動) ペアを抽出する。

- 勝者側の意思決定のみを教師にする
- 対象: obs.select が存在する全決定(デッキ選択は除外し、デッキは別途記録)
- 出力: gzip圧縮JSONL。1行 = {"sel": select, "cur": current, "act": [..], "team": 勝者名, "deck": [60]}

使い方:
    .venv/bin/python scripts/bc_extract.py <episode_jsonのディレクトリ> --out data/bc/pairs_0709.jsonl.gz
"""

import argparse
import glob
import gzip
import json
import os


def slim_obs(obs: dict) -> tuple[dict, dict] | None:
    sel = obs.get("select")
    cur = obs.get("current")
    if sel is None or cur is None:
        return None
    sel = dict(sel)
    sel.pop("deck", None) if False else None  # deckは山札サーチ時に必要なので残す
    return sel, cur


def extract_file(path: str):
    try:
        d = json.load(open(path))
    except Exception:
        return
    rewards = d.get("rewards") or [None, None]
    if 1 not in rewards:
        return  # 引き分け・異常は除外
    w = rewards.index(1)
    names = d.get("info", {}).get("TeamNames", ["?", "?"])
    steps = d.get("steps", [])
    if len(steps) < 3:
        return
    deck = steps[1][w].get("action")
    if not (isinstance(deck, list) and len(deck) == 60):
        return
    for t in range(1, len(steps) - 1):
        s = steps[t][w]
        if s.get("status") != "ACTIVE":
            continue
        obs = s.get("observation") or {}
        slim = slim_obs(obs)
        if slim is None:
            continue
        act = steps[t + 1][w].get("action")
        if not isinstance(act, list):
            continue
        sel, cur = slim
        yield {"sel": sel, "cur": cur, "act": act, "team": names[w], "deck": deck}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    n_pairs = n_files = 0
    teams = {}
    with gzip.open(args.out, "wt") as f:
        for path in sorted(glob.glob(os.path.join(args.indir, "*.json"))):
            n_files += 1
            for pair in extract_file(path) or []:
                f.write(json.dumps(pair, separators=(",", ":")) + "\n")
                n_pairs += 1
                teams[pair["team"]] = teams.get(pair["team"], 0) + 1
    print(f"{n_files}試合 → {n_pairs}ペア -> {args.out}")
    top = sorted(teams.items(), key=lambda kv: -kv[1])[:8]
    print("勝者内訳:", {k: v for k, v in top})


if __name__ == "__main__":
    main()
