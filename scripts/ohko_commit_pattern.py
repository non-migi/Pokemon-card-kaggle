"""「計算可能な一撃死圏内に主力をアクティブへ出す」悪手パターンの検出器。

2026-08-10のLopunny/Ogerpon敗戦調査(13敗)で特定したパターンを定量化する:
  進化直後または自発的入れ替えでGrimmsnarl系統をアクティブに出し、
  相手のOgerpon「Myriad Leaf Shower」/ Lopunny「Gale Thrust/Spiky Hopper」で
  KOされ、かつその時ベンチに身代わり候補が1体以上いた局面(★該当)。

結果(v5.1g sub 55172873の13敗): 9試合19局面が★該当、境界事例込み最大12試合34局面。
詳細は docs/experiments.md の2026-08-10エントリ参照。

使い方: .venv/bin/python scripts/ohko_commit_pattern.py <episode_id> [...]
制約: MAXHPはGrimmsnarl系統3種のみハードコード。「不明(自動昇格)」分類には
自発Switchのログ形式不一致による見逃しが混入しうる(保守的に非該当扱い)。
"""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from cg.api import all_attack
ATK = {a.attackId: a.name for a in all_attack()}
CACHE = os.path.expanduser("~/.cache/ptcg-replays")

MAINLINE = {646: "Marnie's Impidimp", 647: "Marnie's Morgrem", 648: "Marnie's Grimmsnarl ex"}
MAXHP = {646: 70, 647: 100, 648: 320}
OGERPON, LOPUNNY = 96, 849
OGERPON_ATK = "Myriad Leaf Shower"
LOPUNNY_ATKS = {"Gale Thrust", "Spiky Hopper"}

def load(ep_id):
    return json.load(open(os.path.join(CACHE, f"episode-{ep_id}-replay.json")))

def analyze(ep_id, team_name="gogogozi migimimi", verbose=True):
    d = load(ep_id)
    teams = d["info"]["TeamNames"]
    seat = teams.index(team_name)
    opp_seat = 1 - seat
    viz = d["steps"][0][0]["visualize"]
    reward = d["rewards"][seat]

    hp_track = {}          # serial -> last known hp
    prev_active_serial = None
    commits = {}           # serial -> (turn, how, bench_alive_count_excl_self)
    events = []

    for i, f in enumerate(viz):
        cur = f["current"]
        turn = cur.get("turn")
        me = cur["players"][seat]
        op = cur["players"][opp_seat]
        my_active = (me.get("active") or [None])[0]
        my_bench = [x for x in (me.get("bench") or []) if x]

        # detect active-slot change (commit event) -- who is now active vs before
        cur_active_serial = my_active["serial"] if my_active else None
        if my_active and my_active.get("id") in MAINLINE and cur_active_serial != prev_active_serial:
            bench_alive_excl = len(my_bench)  # bench already excludes active by definition
            # classify how: look at this frame's logs for Evolve/Switch by us
            how = "不明(自動昇格の可能性)"
            for l in f.get("logs") or []:
                if l.get("playerIndex") != seat:
                    continue
                if l.get("type") == "Evolve" and l.get("cardId") == my_active.get("id"):
                    how = "進化してアクティブへ"
                elif l.get("type") == "Switch":
                    how = "入れ替えでアクティブへ(自発)"
            commits[cur_active_serial] = (turn, how, bench_alive_excl)  # always keep the MOST RECENT transition
        prev_active_serial = cur_active_serial

        # opponent Ogerpon/Lopunny attack (same-frame or next-frame) + our mainline HpChange
        logs = f.get("logs") or []
        atk_info = None
        for l in logs:
            if l.get("type") == "Attack" and l.get("playerIndex") == opp_seat:
                name = ATK.get(l.get("attackId"), "")
                cid = l.get("cardId")
                if (cid == OGERPON and name == OGERPON_ATK) or (cid == LOPUNNY and name in LOPUNNY_ATKS):
                    atk_info = (cid, name)
        if atk_info:
            for j in (i, i + 1):
                if j >= len(viz):
                    continue
                for l in viz[j].get("logs") or []:
                    if l.get("type") == "HpChange" and l.get("playerIndex") == seat and l.get("cardId") in MAINLINE and l.get("value", 0) < 0:
                        serial = l.get("serial")
                        dmg = -l.get("value")
                        pre_hp = hp_track.get(serial, MAXHP[l["cardId"]])
                        ko = dmg >= pre_hp
                        commit = commits.get(serial)
                        events.append({
                            "turn": turn, "victim": MAINLINE[l["cardId"]], "serial": serial,
                            "dmg": dmg, "pre_hp_est": pre_hp, "ko": ko,
                            "attacker": "ogerpon" if atk_info[0] == OGERPON else "lopunny",
                            "atk_name": atk_info[1], "commit": commit,
                        })

        # NOW update hp_track using this frame's post-log state, for use by the NEXT frame's estimates
        for zone in ("active", "bench"):
            for pk in (me.get(zone) or []):
                if pk:
                    hp_track[pk["serial"]] = pk["hp"]

    if verbose:
        print(f"\n### ep {ep_id} 自分seat={seat} 結果={'WIN' if reward==1 else 'LOSS'} 相手={teams[opp_seat]} ###")
        if not events:
            print("  (該当イベントなし)")
        for e in events:
            c = e["commit"]
            c_str = f"T{c[0]}に{c[1]}(bench生存{c[2]})" if c else "不明"
            flag = "★該当" if (e["ko"] and c and c[2] >= 1 and c[1] != "不明(自動昇格の可能性)") else ""
            print(f"  T{e['turn']:2d} {e['victim']:26s} 被弾{e['dmg']:4d}(推定所持HP{e['pre_hp_est']:4d}) "
                  f"KO={e['ko']} attacker={e['attacker']}/{e['atk_name']:18s} 出した経緯: {c_str} {flag}")
    return events

if __name__ == "__main__":
    for ep in sys.argv[1:]:
        analyze(ep)
