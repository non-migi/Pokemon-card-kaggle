"""リプレイのvisualize配列を日本語ログとしてダンプする軽量トレーサ。

render_replay_jp.py(HTML生成)より軽く、敗戦調査の一次情報として読む用。
visualize配列は両陣営フルネーム入りの完全情報リプレイで、logイベントの
type文字列('Attack','Attach','Evolve'等)をそのまま解釈できる。

使い方: .venv/bin/python scripts/replay_log_trace.py <episode_id> [...]
リプレイは ~/.cache/ptcg-replays/episode-<id>-replay.json を参照する。
(2026-08-10 Lopunny/Ogerpon敗戦調査で作成)
"""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from cg.api import all_attack
ATK = {a.attackId: a.name for a in all_attack()}
CACHE = os.path.expanduser("~/.cache/ptcg-replays")

def load(ep_id):
    return json.load(open(os.path.join(CACHE, f"episode-{ep_id}-replay.json")))

def build_name_map(viz):
    """visualizeの全frameのhand/deck/discard/active/benchからid->name辞書を作る(全知視点なので確実)。"""
    names = {}
    def add(lst):
        for c in (lst or []):
            if c and c.get("id") is not None and c.get("name"):
                names[c["id"]] = c["name"]
    for f in viz:
        for p in f["current"]["players"]:
            add(p.get("hand"))
            add(p.get("deck"))
            add(p.get("discard"))
            for zone in ("active", "bench"):
                for pk in (p.get(zone) or []):
                    if pk:
                        names[pk["id"]] = pk["name"]
                        add(pk.get("energyCards"))
                        add(pk.get("tools"))
            add(p.get("prize"))
    return names

def nm(names, cid):
    return names.get(cid, f"#{cid}")

def fmt_log(l, names, seat):
    t = l.get("type")
    who = "自分" if l.get("playerIndex") == seat else "相手"
    if t == "Attack":
        return f"[{who}] 攻撃: {nm(names,l.get('cardId'))} の「{ATK.get(l.get('attackId'), l.get('attackId'))}」"
    if t == "HpChange":
        v = l.get("value", 0)
        return f"    → {nm(names,l.get('cardId'))} に{-v}ダメージ" if v < 0 else f"    → {nm(names,l.get('cardId'))} が{v}回復"
    if t == "Attach":
        return f"[{who}] {nm(names,l.get('cardId'))} を {nm(names,l.get('cardIdTarget'))} に付けた"
    if t == "Evolve":
        return f"[{who}] {nm(names,l.get('cardIdTarget'))} が {nm(names,l.get('cardId'))} に進化"
    if t == "Switch":
        return f"[{who}] {nm(names,l.get('cardIdActive'))} ⇄ {nm(names,l.get('cardIdBench'))} 入れ替え"
    if t == "Play":
        return f"[{who}] {nm(names,l.get('cardId'))} を使用"
    if t == "Retreat":
        return f"[{who}] にげる"
    if t in ("TurnStart",):
        return f"━━ {who}のターン開始 ━━"
    if t in ("TurnEnd", "Draw", "Shuffle", "MoveCard", "MoveCardReverse", "DrawReverse"):
        return None  # ノイズなので省略
    if t == "Result":
        return f"🏁 決着: reason={l.get('reason')} result={l.get('result')}"
    if t in ("Poisoned", "Burned", "Asleep", "Paralyzed", "Confused"):
        return f"[{who}] {nm(names,l.get('cardId'))} 状態異常: {t} recover={l.get('isRecover')}"
    if t == "Coin":
        return f"[{who}] コイン: {'オモテ' if l.get('head') else 'ウラ'}"
    if t == "Ability":
        return f"[{who}] 特性発動: {nm(names,l.get('cardId'))}"
    return f"[{who}] {t} {l}"

def trace(ep_id, team_name="gogogozi migimimi"):
    d = load(ep_id)
    teams = d["info"]["TeamNames"]
    seat = teams.index(team_name)
    viz = d["steps"][0][0]["visualize"]
    names = build_name_map(viz)
    reward = d["rewards"][seat]
    print(f"\n########## ep {ep_id} 自分seat={seat} 結果={'WIN' if reward==1 else 'LOSS'} 相手={teams[1-seat]} ##########")
    last_turn = None
    for f in viz:
        cur = f["current"]
        turn = cur.get("turn")
        if turn != last_turn:
            print(f"\n--- ターン{turn} ---")
            last_turn = turn
        for l in f.get("logs") or []:
            s = fmt_log(l, names, seat)
            if s:
                print(" ", s)

if __name__ == "__main__":
    for ep in sys.argv[1:]:
        trace(ep)
