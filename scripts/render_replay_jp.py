"""リプレイを日本語の初心者向けHTMLビューアに変換する。

使い方:
    .venv/bin/python scripts/render_replay_jp.py 85103065 [85047638 ...]
    (エピソードIDまたはreplay.jsonのパス。出力は replays/epXXXX_jp.html)

特徴:
- 盤面(バトル場/ベンチ/手札/サイド/トラッシュ)を日本語カード名で表示、HPバー付き
- カードをクリックすると日本語の効果テキスト(ワザ・特性・サポート効果)をポップアップ
- イベントログを日本語の文章で表示
- 全情報視点(両者の手札・サイドも見える)— 学習用
"""

import csv
import glob
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

SEARCH_DIRS = [
    os.path.expanduser("~/.cache/ptcg-replays"),
    "/private/tmp/claude-501/-Users-non-git-Pokemon-card-kaggle/b1969d4e-1f95-4647-9a92-c80a416a00ba/scratchpad/meta",
    "/private/tmp/claude-501/-Users-non-git-Pokemon-card-kaggle/b1969d4e-1f95-4647-9a92-c80a416a00ba/scratchpad/episodes",
]

AREA_JP = {1: "山札", 2: "手札", 3: "トラッシュ", 4: "バトル場", 5: "ベンチ", 6: "サイド",
           7: "スタジアム", 8: "エネルギー", 9: "どうぐ", 10: "進化元", 11: "プレイヤー", 12: "公開"}
ENERGY_JP = {0: "無", 1: "草", 2: "炎", 3: "水", 4: "雷", 5: "超", 6: "闘", 7: "悪", 8: "鋼", 9: "竜", 10: "虹", 11: "R"}
RESULT_REASON_JP = {1: "サイドを取り切った", 2: "山札切れ", 3: "バトル場に出せるポケモンがいない", 4: "カードの効果"}


def load_jp_db() -> dict:
    """カードID → 日本語カード情報(名前・HP・ワザ/効果一覧)。"""
    db = {}
    with open(os.path.join(ROOT, "data/strategy/JP_Card_Data.csv")) as f:
        for r in csv.DictReader(f):
            cid = int(r["カード ID"])
            e = db.setdefault(cid, {
                "name": r["カード名"], "hp": r["HP"] if r["HP"] not in ("", "n/a") else "",
                "kind": r["ポケモンの進化の段階/エネルギー・トレーナーズの種類"],
                "rule": r["ルール"] if r["ルール"] not in ("", "n/a") else "",
                "type": r["タイプ"] if r["タイプ"] not in ("", "n/a") else "",
                "weak": r["弱点"] if r["弱点"] not in ("", "n/a") else "",
                "retreat": r["にげる"] if r["にげる"] not in ("", "n/a") else "",
                "pre": r["進化前"] if r["進化前"] not in ("", "n/a") else "",
                "moves": [],
            })
            move_name = r["ワザ名"] if r["ワザ名"] not in ("", "n/a") else ""
            text = r["効果の説明"] or ""
            cat = r["カテゴリ"] if r["カテゴリ"] not in ("", "n/a") else ""
            if move_name or text:
                e["moves"].append({
                    "name": move_name, "cat": cat,
                    "cost": r["コスト"] if r["コスト"] not in ("", "n/a") else "",
                    "dmg": r["ダメージ"] if r["ダメージ"] not in ("", "n/a") else "",
                    "text": text,
                })
    return db


def load_attack_jp(jp_db) -> dict:
    """attackId → 日本語ワザ名(EN CSVとJP CSVの行整列 + engineのattack名で対応付け)。"""
    from cg.api import all_attack, all_card_data

    en_rows = {}
    with open(os.path.join(ROOT, "data/strategy/EN_Card_Data.csv")) as f:
        for r in csv.DictReader(f):
            name = r["Move Name"]
            if name and name != "n/a":
                en_rows.setdefault(int(r["Card ID"]), []).append(name)
    attacks = {a.attackId: a for a in all_attack()}
    out = {}
    for c in all_card_data():
        ens = en_rows.get(c.cardId, [])
        jps = [m["name"] for m in jp_db.get(c.cardId, {}).get("moves", []) if m["name"]]
        for aid in c.attacks:
            a = attacks.get(aid)
            if a and a.name in ens:
                i = ens.index(a.name)
                if i < len(jps):
                    out[aid] = jps[i]
    return out


def slim_pokemon(p):
    if p is None:
        return None
    return {"id": p["id"], "name": p["name"], "hp": p["hp"], "maxHp": p["maxHp"],
            "ene": [ENERGY_JP.get(e, "?") for e in p.get("energies", [])],
            "tools": [{"id": t["id"], "name": t["name"]} for t in p.get("tools", [])],
            "pre": len(p.get("preEvolution", []))}


def slim_cards(cards):
    return [None if c is None else {"id": c["id"], "name": c["name"]} for c in (cards or [])]


def slim_frame(f):
    cur = f["current"]
    players = []
    for p in cur["players"]:
        players.append({
            "active": [slim_pokemon(x) for x in p.get("active", [])],
            "bench": [slim_pokemon(x) for x in p.get("bench", [])],
            "hand": slim_cards(p.get("hand")),
            "prize": slim_cards(p.get("prize")),
            "discard": slim_cards(p.get("discard")),
            "deckCount": p.get("deckCount", 0),
            "cond": [n for n, k in [("どく", "poisoned"), ("やけど", "burned"), ("ねむり", "asleep"),
                                     ("マヒ", "paralyzed"), ("こんらん", "confused")] if p.get(k)],
        })
    sel = f.get("select") or {}
    return {
        "turn": cur.get("turn", 0), "who": cur.get("yourIndex", 0),
        "stadium": slim_cards(cur.get("stadium")),
        "players": players, "logs": f.get("logs", []),
        "selCtx": sel.get("context", ""), "selType": sel.get("type", ""),
        "chosen": f.get("selected"),
    }


def collect_ids(frames) -> set:
    ids = set()
    for f in frames:
        for p in f["players"]:
            for z in ("hand", "prize", "discard"):
                ids.update(c["id"] for c in p[z] if c)
            for z in ("active", "bench"):
                for pk in p[z]:
                    if pk:
                        ids.add(pk["id"])
                        ids.update(t["id"] for t in pk["tools"])
        ids.update(c["id"] for c in f["stadium"] if c)
        for lg in f["logs"]:
            for k in ("cardId", "cardIdTarget", "cardIdActive", "cardIdBench", "cardIdBefore", "cardIdAfter"):
                if lg.get(k):
                    ids.add(lg[k])
    return ids


TEMPLATE = """<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
:root{--bg:#f5f4ef;--card:#fff;--line:#d8d5cc;--tx:#2b2a26;--sub:#6f6c63;--me:#2f6f4f;--op:#8a3b3b;--hl:#f0ede2}
body{margin:0;font-family:"Hiragino Sans","Yu Gothic",sans-serif;background:var(--bg);color:var(--tx);font-size:14px}
header{display:flex;gap:12px;align-items:center;padding:8px 14px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;flex-wrap:wrap}
header b{font-size:15px} button{font-size:14px;padding:4px 12px;cursor:pointer}
#frame{width:260px} .wrap{display:grid;grid-template-columns:1fr 340px;gap:10px;padding:10px;max-width:1400px;margin:0 auto}
.board{display:flex;flex-direction:column;gap:8px}
.side{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
.side h3{margin:0 0 6px;font-size:13px} .side.me h3{color:var(--me)} .side.op h3{color:var(--op)}
.zonerow{display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start;margin:4px 0}
.zlabel{font-size:11px;color:var(--sub);width:58px;flex-shrink:0;padding-top:6px}
.pk{border:1.5px solid var(--line);border-radius:6px;padding:5px 7px;min-width:120px;cursor:pointer;background:var(--hl)}
.pk.active{border-color:#b98c2c;background:#fdf6e0}
.pk .nm{font-weight:600;font-size:13px} .pk .hp{font-size:11px;color:var(--sub)}
.hpbar{height:5px;background:#e3e0d6;border-radius:3px;margin:3px 0}
.hpbar i{display:block;height:100%;border-radius:3px;background:#4d9c6c}
.hpbar i.low{background:#c94f42} .hpbar i.mid{background:#d99a2b}
.chip{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:1px 6px;margin:1px;font-size:12px;background:#fff;cursor:pointer}
.ene{display:inline-block;width:16px;height:16px;border-radius:50%;background:#dceafc;border:1px solid #9db8d8;font-size:10px;text-align:center;line-height:16px;margin-right:2px}
.meta{font-size:12px;color:var(--sub)}
.logs{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-y:auto;max-height:calc(100vh - 90px)}
.logs h3{margin:0 0 6px;font-size:13px}
.logs .ln{padding:2px 0;border-bottom:1px dashed #eceae2;font-size:13px}
.logs .p0{color:var(--me)} .logs .p1{color:var(--op)}
.selbox{background:#eef3ee;border-radius:6px;padding:6px 8px;margin-bottom:8px;font-size:12px}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10;align-items:center;justify-content:center}
.modal .box{background:#fff;border-radius:10px;max-width:520px;width:92%;max-height:80vh;overflow-y:auto;padding:16px}
.modal h2{margin:0 0 4px;font-size:17px} .modal .kind{font-size:12px;color:var(--sub);margin-bottom:8px}
.mv{border-top:1px solid var(--line);padding:7px 0} .mv b{font-size:14px}
.mv .cost{color:#7a6a2f;font-size:12px;margin-left:6px} .mv .dmg{color:#a33;font-weight:700;margin-left:6px}
.mv p{margin:3px 0 0;font-size:13px;line-height:1.5}
@media(prefers-color-scheme:dark){:root{--bg:#191813;--card:#23221c;--line:#3a382f;--tx:#e8e6dd;--sub:#a09d90;--hl:#2b2a22}
.chip{background:#2e2d25}.pk.active{background:#332c14}.modal .box{background:#26251e}.selbox{background:#233026}.hpbar{background:#3a382f}}
</style></head><body>
<header><b>__TITLE__</b>
<button onclick="go(-1)">◀ 前</button><button onclick="go(1)">次 ▶</button>
<input id="frame" type="range" min="0" max="__MAXF__" value="0" oninput="show(+this.value)">
<span id="pos"></span><span class="meta">←→キーでも操作可 / カードをクリックで効果表示</span></header>
<div class="wrap"><div class="board" id="board"></div>
<div class="logs"><div class="selbox" id="selbox"></div><h3>この場面までの出来事</h3><div id="loglines"></div></div></div>
<div class="modal" id="modal" onclick="this.style.display='none'"><div class="box" id="modalbox"></div></div>
<script>
const DATA=__DATA__;const JP=__JPDB__;const ATK=__ATKJP__;const TEAMS=__TEAMS__;const MYSEAT=__MYSEAT__;
const AREA=__AREAJP__;const REASON=__REASONJP__;
let cur=0;
function jp(id){return (JP[id]&&JP[id].name)||("card#"+id)}
function pkBox(p,act){if(!p)return '<div class="pk">(裏向き)</div>';
 const r=p.hp/Math.max(p.maxHp,1);const cls=r<=0.3?'low':(r<=0.6?'mid':'');
 return `<div class="pk ${act?'active':''}" onclick="openCard(${p.id});event.stopPropagation()">
 <div class="nm">${jp(p.id)}</div><div class="hp">HP ${p.hp}/${p.maxHp}</div>
 <div class="hpbar"><i class="${cls}" style="width:${Math.max(r*100,2)}%"></i></div>
 <div>${p.ene.map(e=>`<span class="ene">${e}</span>`).join('')}${p.tools.map(t=>`<span class="chip">${jp(t.id)}</span>`).join('')}</div></div>`}
function chips(cards,hidden){return cards.map(c=>c?`<span class="chip" onclick="openCard(${c.id})">${jp(c.id)}</span>`:`<span class="chip">裏</span>`).join('')||'<span class="meta">なし</span>'}
function sideHtml(p,idx){const seatCls=idx===MYSEAT?'me':'op';const label=TEAMS[idx]+(idx===MYSEAT?'(自軍)':'');
 return `<div class="side ${seatCls}"><h3>${label} — サイド残り${p.prize.length} / 山札${p.deckCount}枚 ${p.cond.length?'【'+p.cond.join('・')+'】':''}</h3>
 <div class="zonerow"><span class="zlabel">バトル場</span>${p.active.map(x=>pkBox(x,true)).join('')||'<span class="meta">なし</span>'}</div>
 <div class="zonerow"><span class="zlabel">ベンチ</span>${p.bench.map(x=>pkBox(x,false)).join('')||'<span class="meta">なし</span>'}</div>
 <div class="zonerow"><span class="zlabel">手札(${p.hand.length})</span><div>${chips(p.hand)}</div></div>
 <div class="zonerow"><span class="zlabel">サイド</span><div>${chips(p.prize)}</div></div>
 <div class="zonerow"><span class="zlabel">トラッシュ(${p.discard.length})</span><div>${chips(p.discard.slice(-14))}</div></div></div>`}
function logJp(l){const P=`<b class="p${l.playerIndex}">${l.playerIndex===MYSEAT?'自':'相'}</b>`;const n=id=>jp(id);
 switch(l.type){
 case 'TurnStart':return `━━ ターン開始 (${P})`;case 'TurnEnd':return `${P} 番を終えた`;
 case 'Shuffle':return `${P} 山札を切った`;case 'Draw':return `${P} ${n(l.cardId)}を引いた`;
 case 'DrawReverse':return `${P} カードを1枚引いた`;
 case 'MoveCard':return `${P} ${n(l.cardId)}: ${AREA[l.fromArea]||'?'}→${AREA[l.toArea]||'?'}`;
 case 'MoveCardReverse':return `${P} 裏向きカード: ${AREA[l.fromArea]||'?'}→${AREA[l.toArea]||'?'}`;
 case 'Play':return `${P} <b>${n(l.cardId)}</b>を使った`;
 case 'Attach':return `${P} ${n(l.cardId)}を${n(l.cardIdTarget)}につけた`;
 case 'Evolve':return `${P} ${n(l.cardIdTarget)}が<b>${n(l.cardId)}</b>に進化`;
 case 'Devolve':return `${P} ${n(l.cardIdTarget)}が退化`;
 case 'Switch':return `${P} ${n(l.cardIdActive)}⇄${n(l.cardIdBench)}を入れ替え`;
 case 'Change':return `${P} ${n(l.cardIdBefore)}→${n(l.cardIdAfter)}`;
 case 'Attack':return `${P} <b>${n(l.cardId)}</b>のワザ「<b>${ATK[l.attackId]||('#'+l.attackId)}</b>」`;
 case 'HpChange':return `${P} ${n(l.cardId)} ${l.value<0?'に'+(-l.value)+'ダメージ':'が'+l.value+'回復'}`;
 case 'Poisoned':return `${P} ${n(l.cardId)}は${l.isRecover?'どくが治った':'どくになった'}`;
 case 'Burned':return `${P} ${n(l.cardId)}は${l.isRecover?'やけどが治った':'やけどになった'}`;
 case 'Asleep':return `${P} ${n(l.cardId)}は${l.isRecover?'目を覚ました':'ねむりになった'}`;
 case 'Paralyzed':return `${P} ${n(l.cardId)}は${l.isRecover?'マヒが治った':'マヒになった'}`;
 case 'Confused':return `${P} ${n(l.cardId)}は${l.isRecover?'こんらんが治った':'こんらんになった'}`;
 case 'Coin':return `${P} コイン: ${l.head?'オモテ':'ウラ'}`;
 case 'MoveAttached':return `${P} ${n(l.cardId)}を${n(l.cardIdAfter)}へ付け替え`;
 case 'Result':return `🏁 <b>${l.result===2?'引き分け':TEAMS[l.result]+' の勝ち'}</b>(${REASON[l.reason]||''})`;
 case 'HasBasicPokemon':return l.hasBasicPokemon?null:`${P} 手札にたねポケモンがない(引き直し)`;
 default:return null}}
function show(i){cur=Math.max(0,Math.min(i,DATA.length-1));const f=DATA[cur];
 document.getElementById('frame').value=cur;
 document.getElementById('pos').textContent=`${cur+1}/${DATA.length} ターン${f.turn}`;
 const top=1-MYSEAT;
 let b=sideHtml(f.players[top],top);
 if(f.stadium.length&&f.stadium[0])b+=`<div class="side"><h3>スタジアム</h3>${chips(f.stadium)}</div>`;
 b+=sideHtml(f.players[MYSEAT],MYSEAT);
 document.getElementById('board').innerHTML=b;
 const who=f.who===MYSEAT?'自軍':'相手';
 document.getElementById('selbox').innerHTML=`<b>${who}の選択場面</b>: ${f.selCtx||f.selType||''}${f.chosen?` → 選択 [${f.chosen}]`:''}`;
 document.getElementById('loglines').innerHTML=f.logs.map(logJp).filter(x=>x).map(x=>`<div class="ln">${x}</div>`).join('')||'<span class="meta">(出来事なし)</span>'}
function go(d){show(cur+d)}
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')go(-1);if(e.key==='ArrowRight')go(1)});
function openCard(id){const c=JP[id];if(!c)return;const mb=document.getElementById('modalbox');
 mb.innerHTML=`<h2>${c.name}</h2><div class="kind">${c.kind}${c.rule?' / '+c.rule:''}${c.hp?' / HP'+c.hp:''}${c.type?' / '+c.type:''}${c.pre?' / 進化前:'+c.pre:''}${c.weak?' / 弱点:'+c.weak:''}${c.retreat!==''?' / にげる:'+c.retreat:''}</div>`+
 c.moves.map(m=>`<div class="mv"><b>${m.cat?'['+m.cat+'] ':''}${m.name||'効果'}</b>${m.cost?`<span class="cost">${m.cost}</span>`:''}${m.dmg?`<span class="dmg">${m.dmg}</span>`:''}<p>${m.text}</p></div>`).join('');
 document.getElementById('modal').style.display='flex'}
show(0);
</script></body></html>"""


def find_replay(arg: str) -> str:
    if os.path.exists(arg):
        return arg
    for d in SEARCH_DIRS:
        hits = glob.glob(os.path.join(d, f"*{arg}*replay.json"))
        if hits:
            return hits[0]
    raise SystemExit(f"リプレイが見つからない: {arg}(kaggle competitions replay {arg} で取得可能)")


def render(path: str, jp_db: dict, atk_jp: dict) -> str:
    d = json.load(open(path))
    frames = [slim_frame(f) for f in d["steps"][0][0]["visualize"]]
    teams = d.get("info", {}).get("TeamNames", ["P0", "P1"])
    my_seat = teams.index("gogogozi migimimi") if "gogogozi migimimi" in teams else 0
    ids = collect_ids(frames)
    jp_slim = {i: jp_db[i] for i in ids if i in jp_db}
    rewards = d.get("rewards", [None, None])
    res = "勝ち" if rewards[my_seat] == 1 else ("負け" if rewards[my_seat] == -1 else "引き分け")
    ep = os.path.basename(path).split("-")[1] if "-" in os.path.basename(path) else "local"
    title = f"ep{ep} {teams[0]} vs {teams[1]}({res})"
    page = (TEMPLATE
            .replace("__TITLE__", html.escape(title))
            .replace("__MAXF__", str(len(frames) - 1))
            .replace("__DATA__", json.dumps(frames, ensure_ascii=False))
            .replace("__JPDB__", json.dumps(jp_slim, ensure_ascii=False))
            .replace("__ATKJP__", json.dumps(atk_jp, ensure_ascii=False))
            .replace("__TEAMS__", json.dumps(teams, ensure_ascii=False))
            .replace("__MYSEAT__", str(my_seat))
            .replace("__AREAJP__", json.dumps(AREA_JP, ensure_ascii=False))
            .replace("__REASONJP__", json.dumps(RESULT_REASON_JP, ensure_ascii=False)))
    out = os.path.join(ROOT, "replays", f"ep{ep}_jp.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(page)
    return out


def main():
    jp_db = load_jp_db()
    atk_jp = load_attack_jp(jp_db)
    for arg in sys.argv[1:]:
        out = render(find_replay(arg), jp_db, atk_jp)
        print("->", out)


if __name__ == "__main__":
    main()
