"""H5-H8のプログラム監査: リプレイのMAIN選択を解析し、戦術欠陥の頻度を測る。

自機(us)と相手(them)を同一試合で比較してベースラインを持つ。
- H5 進化: MAINにEVOLVE選択肢があった回数と、実際に進化した回数
- H6 攻撃: ATTACK選択肢があったのにENDした回数(攻撃見送り)
- H7 逃げ: RETREATを選んだ回数
- H8 早期END: PLAY/ATTACH/EVOLVEが残っているのにENDした回数

使い方: .venv/bin/python scripts/audit_h5h8.py <tag> [tag...] --us P0|P1 ...
簡単のため gen_replay の swap 規則(no-swap=P0, swap=P1)をタグ順で与える。
"""

import argparse
import json
import os
from collections import defaultdict

CACHE = os.path.expanduser("~/.cache/ptcg-replays")

# OptionType
OT_PLAY, OT_ATTACH, OT_EVOLVE, OT_ABILITY = 7, 8, 9, 10
OT_DISCARD, OT_RETREAT, OT_ATTACK, OT_END = 11, 12, 13, 14
ST_MAIN = 0
PRODUCTIVE = {OT_PLAY, OT_ATTACH, OT_EVOLVE, OT_ABILITY}


def audit_game(path: str, us: int, stats: dict) -> None:
    steps = json.load(open(path))["steps"]
    for st in steps:
        for pi in (0, 1):
            who = "us" if pi == us else "them"
            e = st[pi]
            obs = e.get("observation") or {}
            sel = obs.get("select")
            act = e.get("action")
            if not sel or sel.get("type") != ST_MAIN:
                continue
            opts = sel.get("option") or []
            if not opts or not isinstance(act, list) or len(act) != 1:
                continue
            types = [o.get("type") for o in opts if isinstance(o, dict)]
            chosen = opts[act[0]].get("type") if 0 <= act[0] < len(opts) else None
            s = stats[who]
            s["main_decisions"] += 1
            if OT_EVOLVE in types:
                s["evolve_available"] += 1
                if chosen == OT_EVOLVE:
                    s["evolve_taken"] += 1
            if OT_ATTACK in types:
                s["attack_available"] += 1
                if chosen == OT_ATTACK:
                    s["attack_taken"] += 1
                elif chosen == OT_END:
                    s["attack_skipped_end"] += 1
            if chosen == OT_RETREAT:
                s["retreat"] += 1
            if chosen == OT_END and (set(types) & PRODUCTIVE):
                s["end_with_productive"] += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--us", nargs="+", required=True, help="各tagの自機席(P0/P1)")
    args = ap.parse_args()
    assert len(args.us) == len(args.tags)

    stats = {"us": defaultdict(int), "them": defaultdict(int)}
    for tag, us in zip(args.tags, args.us):
        path = os.path.join(CACHE, f"episode-{tag}-replay.json")
        audit_game(path, 0 if us.upper() == "P0" else 1, stats)

    def pct(a, b):
        return f"{a}/{b} ({a / b * 100:.0f}%)" if b else f"{a}/0"

    for who in ("us", "them"):
        s = stats[who]
        label = "自機(v4.0a)" if who == "us" else "相手(壁ボット)"
        print(f"\n=== {label} — MAIN決定 {s['main_decisions']} ===")
        print(f"  H5 進化: 選択肢あり時に進化 {pct(s['evolve_taken'], s['evolve_available'])}")
        print(f"  H6 攻撃: 攻撃可能時に攻撃 {pct(s['attack_taken'], s['attack_available'])}"
              f" / うちEND見送り {s['attack_skipped_end']}")
        print(f"  H7 逃げ回数: {s['retreat']}")
        print(f"  H8 生産的手が残る中でEND: {s['end_with_productive']}")


if __name__ == "__main__":
    main()
