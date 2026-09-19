#!/usr/bin/env python3
"""開催中のメダル対象Kaggleコンペを一覧し、前回からの新規を検出する。

    python3 scripts/kaggle_watch.py                 # 一覧 + 新規検出
    python3 scripts/kaggle_watch.py --medals        # メダル閾値もLBから計算(遅い)
    python3 scripts/kaggle_watch.py --state <path>  # スナップショットの保存先

メダルが出るのは awardsPoints=true のコンペだけ(Featured / Research の一部)。
Playground / Getting Started / Community はメダルもポイントも出ないので除外する。
新規コンペは `kaggle competitions list` のカテゴリ別走査では漏れることがあるため、
recentlyCreated でも引いて和集合を取る。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import zipfile

STATE_DEFAULT = os.path.expanduser("~/.cache/kaggle_watch_state.json")
CATEGORIES = ["all", "featured", "research", "recruitment", "masters", "analytics"]


def kg(*args, timeout=180):
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout


def parse_arrays(txt):
    """CLI出力に混じる注記を飛ばしてJSON配列だけ拾う。"""
    dec, out, i = json.JSONDecoder(), [], 0
    while i < len(txt):
        j = txt.find("[", i)
        if j < 0:
            break
        try:
            arr, end = dec.raw_decode(txt[j:])
            out += arr
            i = j + end
        except Exception:
            i = j + 1
    return out


def list_all():
    seen = {}
    for cat in CATEGORIES:
        for page in (1, 2, 3):
            for o in parse_arrays(kg("competitions", "list", "--category", cat, "-p", str(page), "--format", "json")):
                if isinstance(o, dict) and o.get("ref"):
                    seen[o["ref"]] = o
    for page in (1, 2):  # 新規は category 走査から漏れることがある
        for o in parse_arrays(kg("competitions", "list", "--sort-by", "recentlyCreated",
                                 "--category", "all", "-p", str(page), "--format", "json")):
            if isinstance(o, dict) and o.get("ref"):
                seen.setdefault(o["ref"], o)
    return seen


def _sdk_python():
    """kagglesdk が入っている Python を探す。`kaggle` CLI のshebangが最も確実。"""
    import shutil
    exe = shutil.which("kaggle")
    if exe:
        try:
            first = open(exe, "r", encoding="utf-8", errors="ignore").readline()
            if first.startswith("#!"):
                cand = first[2:].strip().split()[0]
                if os.path.exists(cand):
                    return cand
        except Exception:
            pass
    return sys.executable


_SDK_PY = None
_DETAIL_SRC = """
import json,sys
from kagglesdk import KaggleClient
from kagglesdk.competitions.types.competition_api_service import ApiGetCompetitionRequest
out={}
with KaggleClient() as c:
    for n in sys.argv[1:]:
        r=ApiGetCompetitionRequest(); r.competition_name=n
        try: out[n]=c.competitions.competition_api_client.get_competition(r).to_dict()
        except Exception as e: out[n]={"_error":str(e)}
print(json.dumps(out,default=str))
"""


def details_many(names):
    """複数コンペの詳細を1プロセスでまとめて取る(awardsPoints等)。"""
    global _SDK_PY
    if _SDK_PY is None:
        _SDK_PY = _sdk_python()
    if not names:
        return {}
    try:
        r = subprocess.run([_SDK_PY, "-c", _DETAIL_SRC, *names],
                           capture_output=True, text=True, timeout=600)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print(f"  (詳細取得に失敗: {e})", file=sys.stderr)
        return {}


def medal_ranks(n):
    """Kaggle標準のメダル境界(順位)。"""
    if n < 250:
        return int(n * 0.10), int(n * 0.20), int(n * 0.40)   # 金, 銀, 銅
    if n < 1000:
        return 20, 50, 100
    return 10 + int(n * 0.002), int(n * 0.05), int(n * 0.10)


def thresholds(name, out_dir="/tmp/kaggle_watch_lb"):
    os.makedirs(out_dir, exist_ok=True)
    kg("competitions", "leaderboard", name, "--download", "-p", out_dir, "-q")
    z = os.path.join(out_dir, f"{name}.zip")
    if not os.path.exists(z):
        return None
    with zipfile.ZipFile(z) as zf:
        csvname = [x for x in zf.namelist() if x.endswith(".csv")][0]
        import csv as _csv
        import io
        rows = list(_csv.DictReader(io.TextIOWrapper(zf.open(csvname), encoding="utf-8-sig")))
    sc = [float(r["Score"]) for r in rows]
    if not sc:
        return None
    g, s, b = medal_ranks(len(sc))
    pick = lambda k: sc[k - 1] if k <= len(sc) else None
    return {"n": len(sc), "top": sc[0], "gold": pick(g), "silver": pick(s), "bronze": pick(b),
            "median": sorted(sc)[len(sc) // 2]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=STATE_DEFAULT)
    ap.add_argument("--medals", action="store_true", help="LBを落としてメダル閾値も出す")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    comps = list_all()
    cand = []
    for ref, c in comps.items():
        try:
            d = dt.datetime.fromisoformat(str(c["deadline"]).replace("Z", "").split(".")[0])
        except Exception:
            continue
        if d <= now or c.get("category") in ("Getting Started", "Community", "Playground"):
            continue
        cand.append((ref.rstrip("/").split("/")[-1], d, c))
    print(f"開催中の候補 {len(cand)} 件の詳細を取得中...", file=sys.stderr)
    det_all = details_many([n for n, _, _ in cand])

    active = []
    for name, d, c in cand:
        det = det_all.get(name, {})
        if not det.get("awardsPoints"):
            continue  # メダルが出ないものは除外
        active.append({
            "name": name, "title": det.get("title", name), "category": c.get("category"),
            "deadline": d.date().isoformat(), "days": (d - now).days,
            "entry": (det.get("newEntrantDeadline") or "")[:10],
            "teams": c.get("teamCount"), "reward": str(c.get("reward")),
            "subs_per_day": det.get("maxDailySubmissions"),
            "notebook_only": bool(det.get("isKernelsSubmissionsOnly")),
        })
    active.sort(key=lambda x: x["deadline"])

    prev = {}
    if os.path.exists(a.state):
        try:
            prev = {x["name"]: x for x in json.load(open(a.state)).get("active", [])}
        except Exception:
            pass
    new = [x for x in active if x["name"] not in prev]

    print(f"メダル対象の開催中コンペ: {len(active)} 件  ({now.date()} UTC)\n")
    hdr = f"{'締切':<12}{'残':>4} {'参加締切':<11}{'チーム':>7}{'/日':>4} {'NB':>3}  {'賞金':<14}名前"
    print(hdr); print("-" * len(hdr))
    for x in active:
        mark = "🆕 " if x["name"] in {y["name"] for y in new} else "   "
        print(f"{x['deadline']:<12}{x['days']:>4} {x['entry']:<11}{x['teams']:>7}"
              f"{x['subs_per_day'] or '-':>4} {'yes' if x['notebook_only'] else 'no':>3}  "
              f"{x['reward'][:14]:<14}{mark}{x['name']}")

    if new:
        print(f"\n🆕 前回から増えたもの: {len(new)} 件")
        for x in new:
            print(f"  - {x['title']}  ({x['name']})")
    elif prev:
        print("\n新規なし")

    if a.medals:
        print("\nメダル閾値(公開LB実測):")
        for x in active:
            t = thresholds(x["name"])
            if t:
                print(f"  {x['name'][:44]:<46} n={t['n']:<6} 1位={t['top']:.4f} "
                      f"金={t['gold']} 銀={t['silver']} 銅={t['bronze']} 中央={t['median']:.4f}")

    os.makedirs(os.path.dirname(a.state), exist_ok=True)
    json.dump({"checked": now.isoformat(), "active": active}, open(a.state, "w"), indent=1)
    print(f"\n状態を保存: {a.state}")


if __name__ == "__main__":
    main()
