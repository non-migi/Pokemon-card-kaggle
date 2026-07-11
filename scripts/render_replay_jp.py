"""リプレイを「実物のプレイマット風」日本語HTMLビューアに変換する。

使い方:
    .venv/bin/python scripts/render_replay_jp.py 85103065 [85047638 ...]
    (エピソードIDまたはreplay.jsonのパス。出力は replays/epXXXX_jp.html)

特徴:
- 実際の対戦配置(バトル場中央・ベンチ・サイド・山札/トラッシュ・手札)を再現
- 公式カード画像(コンペ配布PDFから抽出、data/card_images/)を使用。HPバー・エネルギー・ダメカン表示
- カードをクリックすると拡大画像+日本語の効果テキスト
- イベントログを日本語の文章で表示。全情報視点(両者の手札も見える)

⚠ ライセンス注意: カード画像はコンペ限定利用の「Pokémon Elements」。
   生成HTML(replays/、git管理外)を公開・再配布しないこと。Writeupにも載せない。

前提: .venv/bin/python scripts/extract_card_images.py を一度実行しておく
"""

import base64
import csv
import glob
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

IMG_DIR = os.path.join(ROOT, "data/card_images")
SEARCH_DIRS = [
    os.path.expanduser("~/.cache/ptcg-replays"),
]

AREA_JP = {1: "山札", 2: "手札", 3: "トラッシュ", 4: "バトル場", 5: "ベンチ", 6: "サイド",
           7: "スタジアム", 8: "エネルギー", 9: "どうぐ", 10: "進化元", 11: "プレイヤー", 12: "公開"}
ENERGY_JP = {0: "無", 1: "草", 2: "炎", 3: "水", 4: "雷", 5: "超", 6: "闘", 7: "悪", 8: "鋼", 9: "竜", 10: "虹", 11: "R"}
ENERGY_COLOR = {"草": "#4a9e4a", "炎": "#d9573b", "水": "#3b7fd9", "雷": "#d9b93b", "超": "#9b59b6",
                "闘": "#b06a3b", "悪": "#4a4a5e", "鋼": "#8a9aa5", "竜": "#c9a227", "無": "#a8a29a",
                "虹": "#d96ab0", "R": "#666"}
RESULT_REASON_JP = {1: "サイドを取り切った", 2: "山札切れ", 3: "バトル場に出せるポケモンがいない", 4: "カードの効果"}


def load_jp_db() -> dict:
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
            "tools": [{"id": t["id"], "name": t["name"]} for t in p.get("tools", [])]}


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
        "selCtx": sel.get("context", ""), "chosen": f.get("selected"),
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


def image_map(ids) -> dict:
    out = {}
    for cid in ids:
        p = os.path.join(IMG_DIR, f"{cid}.jpg")
        if os.path.exists(p):
            with open(p, "rb") as f:
                out[cid] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return out


TEMPLATE = """<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
:root{--mat:#2e6b4f;--mat2:#275d44;--line:#1d4634;--tx:#e9e6dc;--panel:#f5f4ef;--ptx:#2b2a26;--sub:#6f6c63;
--me:#7fd6a8;--op:#e89a9a;--gold:#e8c86a}
*{box-sizing:border-box}
body{margin:0;font-family:"Hiragino Sans","Yu Gothic",sans-serif;background:#1b1a17;color:var(--tx);font-size:13px}
header{display:flex;gap:10px;align-items:center;padding:7px 12px;background:#26251f;border-bottom:1px solid #3a382f;
position:sticky;top:0;z-index:5;flex-wrap:wrap}
header b{font-size:14px;color:#f0eee6} button{font-size:13px;padding:3px 10px;cursor:pointer}
#frame{width:230px} .meta{font-size:11px;color:#9a978c}
.wrap{display:grid;grid-template-columns:1fr 330px;gap:8px;padding:8px;max-width:1500px;margin:0 auto}
.mat{background:linear-gradient(175deg,var(--mat) 0%,var(--mat2) 100%);border-radius:12px;padding:8px 10px;
border:2px solid var(--line)}
.parea{display:grid;grid-template-columns:64px 1fr 64px;gap:6px;align-items:start;padding:4px 0}
.pname{font-size:12px;font-weight:700;padding:1px 8px;border-radius:4px;display:inline-block}
.pname.me{background:#1d4634;color:var(--me)} .pname.op{background:#4a2626;color:var(--op)}
.centercol{display:flex;flex-direction:column;gap:5px;align-items:center}
.row{display:flex;gap:5px;justify-content:center;flex-wrap:wrap;min-height:20px}
.card{position:relative;width:76px;cursor:pointer;flex-shrink:0}
.card img{width:100%;border-radius:4px;display:block;box-shadow:0 1px 4px rgba(0,0,0,.5)}
.card.big{width:104px}
.card .hpb{position:absolute;left:2px;right:2px;bottom:20px;height:5px;background:rgba(0,0,0,.55);border-radius:3px}
.card .hpb i{display:block;height:100%;border-radius:3px;background:#5ad08a}
.card .hpb i.mid{background:#e0b040} .card .hpb i.low{background:#e05545}
.card .hpt{position:absolute;right:2px;top:2px;background:rgba(0,0,0,.7);color:#fff;font-size:10px;
padding:0 4px;border-radius:3px;font-weight:700}
.card .enes{position:absolute;left:2px;bottom:2px;display:flex;gap:1px;flex-wrap:wrap;max-width:72px}
.ene{width:14px;height:14px;border-radius:50%;font-size:9px;color:#fff;text-align:center;line-height:14px;
border:1px solid rgba(255,255,255,.6);font-weight:700}
.card .tool{position:absolute;right:2px;bottom:20px;background:rgba(30,30,60,.85);color:#cfe;font-size:9px;
padding:0 3px;border-radius:3px}
.back{width:76px;aspect-ratio:63/88;border-radius:4px;background:repeating-linear-gradient(45deg,#33507e,#33507e 6px,#2a4066 6px,#2a4066 12px);
border:1px solid #223354;box-shadow:0 1px 4px rgba(0,0,0,.5)}
.back.small{width:44px}
.stack{position:relative;width:56px;text-align:center}
.stack .back{width:56px;margin:0 auto}
.stack .cnt{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,.75);
color:#fff;border-radius:10px;padding:1px 7px;font-size:12px;font-weight:700}
.zlbl{font-size:10px;color:rgba(255,255,255,.75);text-align:center;margin-top:2px}
.hand{display:flex;justify-content:center;margin:2px 0}
.hand .card{width:52px;margin:0 -7px;transition:margin .1s}
.hand .card:hover{margin:0 2px;z-index:2}
.prizes{display:grid;grid-template-columns:1fr 1fr;gap:2px}
.prizes .card,.prizes .back{width:28px}
.midbar{display:flex;align-items:center;justify-content:center;gap:14px;padding:3px 0;border-top:1px dashed rgba(255,255,255,.25);
border-bottom:1px dashed rgba(255,255,255,.25);margin:2px 0}
.cond{background:#7e3030;color:#ffd7d7;font-size:10px;border-radius:3px;padding:0 5px;margin-left:4px}
.logs{background:var(--panel);color:var(--ptx);border:1px solid #d8d5cc;border-radius:10px;padding:9px;
overflow-y:auto;max-height:calc(100vh - 80px)}
.logs h3{margin:0 0 5px;font-size:12px} .logs .ln{padding:2px 0;border-bottom:1px dashed #e5e2d8;font-size:12.5px;line-height:1.45}
.logs .p0{color:#2f6f4f;font-weight:700} .logs .p1{color:#8a3b3b;font-weight:700}
.selbox{background:#eef3ee;border-radius:6px;padding:5px 8px;margin-bottom:7px;font-size:11.5px;color:#2b3a2e}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:10;align-items:center;justify-content:center}
.modal .box{background:#fbfaf6;color:var(--ptx);border-radius:12px;max-width:640px;width:94%;max-height:86vh;
overflow-y:auto;padding:14px;display:grid;grid-template-columns:200px 1fr;gap:12px}
.modal img{width:200px;border-radius:8px}
.modal h2{margin:0 0 4px;font-size:16px} .modal .kind{font-size:11px;color:var(--sub);margin-bottom:6px}
.mv{border-top:1px solid #e0ddd2;padding:6px 0} .mv b{font-size:13px}
.mv .cost{color:#7a6a2f;font-size:11px;margin-left:6px} .mv .dmg{color:#a33;font-weight:700;margin-left:6px}
.mv p{margin:2px 0 0;font-size:12px;line-height:1.5}
.notesbox{margin-top:12px;border-top:2px solid #d8d5cc;padding-top:8px}
.notesbox textarea{width:100%;box-sizing:border-box;font-family:inherit;font-size:12.5px;border:1px solid #c9c6bb;
border-radius:6px;padding:6px 8px;resize:vertical;background:#fff}
.notebtns{display:flex;gap:6px;margin:6px 0}
.notebtns button{flex:1;padding:5px 4px;border-radius:6px;border:1px solid #b9b6ab;background:#fff;font-size:12px}
.notebtns button:hover{background:#eef3ee}
.noteitem{background:#f2f0e8;border-radius:6px;padding:6px 9px;margin:5px 0;font-size:12px;position:relative}
.noteitem .where{color:#2f6f4f;font-weight:700;cursor:pointer;text-decoration:underline}
.noteitem .del{position:absolute;right:6px;top:4px;cursor:pointer;color:#a33;font-weight:700}
@media(max-width:1000px){.wrap{grid-template-columns:1fr}}
</style></head><body>
<header><b>__TITLE__</b>
<button onclick="go(-1)">◀ 前</button><button onclick="go(1)">次 ▶</button>
<input id="frame" type="range" min="0" max="__MAXF__" value="0" oninput="show(+this.value)">
<span id="pos" style="color:#f0eee6"></span><span class="meta">←→キー / カードクリックで効果</span></header>
<div class="wrap"><div class="mat" id="board"></div>
<div class="logs"><div class="selbox" id="selbox"></div><h3>この場面までの出来事</h3><div id="loglines"></div>
<div class="notesbox">
  <h3>📝 感想メモ(この場面に紐づきます)</h3>
  <textarea id="noteinput" rows="3" placeholder="例: この場面で逃げないのは変。ベンチのマシマシラにエネを貼るべきでは"></textarea>
  <div class="notebtns">
    <button onclick="addNote()">＋ この場面にメモ</button>
    <button onclick="copyNotes()" id="copybtn">📋 感想をまとめてコピー</button>
  </div>
  <div id="notelist"></div>
</div></div></div>
<div class="modal" id="modal" onclick="this.style.display='none'"><div class="box" id="modalbox"></div></div>
<script>
const DATA=__DATA__;const JP=__JPDB__;const ATK=__ATKJP__;const TEAMS=__TEAMS__;const MYSEAT=__MYSEAT__;
const AREA=__AREAJP__;const REASON=__REASONJP__;const IMG=__IMGMAP__;const ECOL=__ECOL__;
let cur=0;
const jp=id=>(JP[id]&&JP[id].name)||("card#"+id);
function imgTag(id){return IMG[id]?`<img src="${IMG[id]}" alt="${jp(id)}">`:`<div class="back"></div>`}
function eneChips(p){return p.ene.map(e=>`<span class="ene" style="background:${ECOL[e]||'#888'}">${e}</span>`).join('')}
function pkCard(p,big){if(!p)return `<div class="back${big?'':''}"></div>`;
 const r=p.hp/Math.max(p.maxHp,1);const cls=r<=0.3?'low':(r<=0.6?'mid':'');
 return `<div class="card ${big?'big':''}" onclick="openCard(${p.id});event.stopPropagation()">
 ${imgTag(p.id)}<span class="hpt">${p.hp}</span>
 <div class="hpb"><i class="${cls}" style="width:${Math.max(r*100,3)}%"></i></div>
 <div class="enes">${eneChips(p)}</div>
 ${p.tools.length?`<span class="tool">${p.tools.map(t=>jp(t.id)).join('/')}</span>`:''}</div>`}
function handRow(cards){if(!cards.length)return '<div class="hand"><span class="meta">手札なし</span></div>';
 return `<div class="hand">${cards.map(c=>c?`<div class="card" onclick="openCard(${c.id})">${imgTag(c.id)}</div>`:'<div class="back small"></div>').join('')}</div>`}
function prizeGrid(prize){return `<div class="prizes">${prize.map(c=>c?`<div class="card" onclick="openCard(${c.id})">${imgTag(c.id)}</div>`:'<div class="back"></div>').join('')}</div><div class="zlbl">サイド ${prize.length}</div>`}
function stacks(p){const top=p.discard.length?p.discard[p.discard.length-1]:null;
 return `<div class="stack"><div class="back"></div><span class="cnt">${p.deckCount}</span><div class="zlbl">山札</div></div>
 <div class="stack">${top?`<div class="card" style="width:56px" onclick="openCard(${top.id})">${imgTag(top.id)}</div>`:'<div class="back" style="opacity:.25"></div>'}
 <div class="zlbl">トラッシュ ${p.discard.length}</div></div>`}
function sideArea(f,idx,isTop){const p=f.players[idx];const seat=idx===MYSEAT?'me':'op';
 const label=`<span class="pname ${seat}">${TEAMS[idx]}${idx===MYSEAT?'(自軍)':''}</span>`+
   (p.cond.length?`<span class="cond">${p.cond.join('・')}</span>`:'');
 const active=`<div class="row">${p.active.map(x=>pkCard(x,true)).join('')||'<span class="meta">バトル場なし</span>'}</div>`;
 const bench=`<div class="row">${p.bench.map(x=>pkCard(x,false)).join('')||'<span class="meta" style="color:rgba(255,255,255,.5)">ベンチなし</span>'}</div><div class="zlbl">ベンチ</div>`;
 const hand=handRow(p.hand);
 const inner=isTop?[hand,bench,active]:[active,bench,hand];
 return `<div class="parea">
   <div>${prizeGrid(p.prize)}</div>
   <div class="centercol">${isTop?'':label}${inner.join('')}${isTop?label:''}</div>
   <div style="display:flex;flex-direction:column;gap:4px">${stacks(p)}</div></div>`}
function show(i){cur=Math.max(0,Math.min(i,DATA.length-1));const f=DATA[cur];
 document.getElementById('frame').value=cur;
 document.getElementById('pos').textContent=`${cur+1}/${DATA.length} ターン${f.turn}`;
 const top=1-MYSEAT;
 const stad=f.stadium.length&&f.stadium[0]?`<div class="card" style="width:56px" onclick="openCard(${f.stadium[0].id})">${imgTag(f.stadium[0].id)}</div><span class="zlbl">スタジアム: ${jp(f.stadium[0].id)}</span>`:'<span class="meta" style="color:rgba(255,255,255,.5)">スタジアムなし</span>';
 document.getElementById('board').innerHTML=sideArea(f,top,true)+`<div class="midbar">${stad}</div>`+sideArea(f,MYSEAT,false);
 const who=f.who===MYSEAT?'自軍':'相手';
 document.getElementById('selbox').innerHTML=`<b>${who}の選択場面</b>: ${f.selCtx||''}${f.chosen?` → 選択 [${f.chosen}]`:''}`;
 document.getElementById('loglines').innerHTML=f.logs.map(logJp).filter(x=>x).map(x=>`<div class="ln">${x}</div>`).join('')||'<span class="meta">(出来事なし)</span>'}
function logJp(l){const P=`<b class="p${l.playerIndex}">${l.playerIndex===MYSEAT?'自':'相'}</b>`;const n=jp;
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
function go(d){show(cur+d)}
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')go(-1);if(e.key==='ArrowRight')go(1)});
function openCard(id){const c=JP[id];if(!c)return;const mb=document.getElementById('modalbox');
 mb.innerHTML=`<div>${IMG[id]?`<img src="${IMG[id]}">`:''}</div><div><h2>${c.name}</h2>
 <div class="kind">${c.kind}${c.rule?' / '+c.rule:''}${c.hp?' / HP'+c.hp:''}${c.type?' / '+c.type:''}${c.pre?' / 進化前:'+c.pre:''}${c.weak?' / 弱点:'+c.weak:''}${c.retreat!==''?' / にげる:'+c.retreat:''}</div>`+
 c.moves.map(m=>`<div class="mv"><b>${m.cat?'['+m.cat+'] ':''}${m.name||'効果'}</b>${m.cost?`<span class="cost">${m.cost}</span>`:''}${m.dmg?`<span class="dmg">${m.dmg}</span>`:''}<p>${m.text}</p></div>`).join('')+`</div>`;
 document.getElementById('modal').style.display='flex'}
show(0);
/* ---- 感想メモ ---- */
const NKEY = 'ptcg-notes-' + location.pathname.split('/').pop();
let notes = [];
try{ notes = JSON.parse(localStorage.getItem(NKEY) || '[]'); }catch(e){}
function saveNotes(){ localStorage.setItem(NKEY, JSON.stringify(notes)); renderNotes(); }
function addNote(){
  const t = document.getElementById('noteinput').value.trim();
  if(!t) return;
  notes.push({frame: cur, turn: DATA[cur].turn, text: t});
  document.getElementById('noteinput').value = '';
  saveNotes();
}
function delNote(i){ notes.splice(i,1); saveNotes(); }
function renderNotes(){
  document.getElementById('notelist').innerHTML = notes.map((n,i) =>
    `<div class="noteitem"><span class="where" onclick="show(${n.frame})">ターン${n.turn}・場面${n.frame+1}</span>
     <span class="del" onclick="delNote(${i})">×</span><br>${n.text.replace(/</g,'&lt;')}</div>`).join('')
    || '<span class="meta">メモはまだありません</span>';
}
function copyNotes(){
  const head = document.title;
  const body = notes.map(n => `- ターン${n.turn}(場面${n.frame+1}/${DATA.length}): ${n.text}`).join('\n');
  const txt = `【リプレイ感想】${head}\n${body || '(メモなし)'}`;
  const done = () => { const b = document.getElementById('copybtn'); b.textContent = '✅ コピーしました'; setTimeout(()=>b.textContent='📋 感想をまとめてコピー', 1600); };
  if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(txt).then(done); }
  else { const ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); done(); }
}
renderNotes();
</script></body></html>"""


def find_replay(arg: str) -> str:
    if os.path.exists(arg):
        return arg
    for d in SEARCH_DIRS:
        hits = glob.glob(os.path.join(d, f"*{arg}*replay.json"))
        if hits:
            return hits[0]
    raise SystemExit(f"リプレイが見つからない: {arg}(kaggle competitions replay {arg} で取得可能)")


ARCH_RULES = [("フーディン型", "フーディン"), ("オーロンゲ型", "マリィのオーロンゲex"),
              ("ガルーラ型", "メガガルーラex"), ("ブリジュラス型", "ブリジュラスex"),
              ("ルカリオ型", "メガルカリオex"), ("イワパレス型", "イワパレス"),
              ("初期デッキ型", "メガユキノオーex"), ("スターミー型", "メガスターミーex")]


def archetype(deck, jp_db) -> str:
    names = {jp_db.get(cid, {}).get("name", "") for cid in deck}
    for label, key in ARCH_RULES:
        if key in names:
            return label
    return "その他"


def render(path: str, jp_db: dict, atk_jp: dict, outdir: str = None, prefix: str = "") -> str:
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
            .replace("__REASONJP__", json.dumps(RESULT_REASON_JP, ensure_ascii=False))
            .replace("__IMGMAP__", json.dumps(image_map(ids)))
            .replace("__ECOL__", json.dumps(ENERGY_COLOR, ensure_ascii=False)))
    # 説明的なファイル名: 勝敗_自デッキ_vs_相手デッキ_ep番号
    try:
        my_deck = d["steps"][1][my_seat].get("action") or []
        opp_deck = d["steps"][1][1 - my_seat].get("action") or []
        my_arch = archetype(my_deck, jp_db)
        opp_arch = archetype(opp_deck, jp_db)
    except Exception:
        my_arch = opp_arch = "不明"
    fname = f"{prefix}{res}_{my_arch}_vs_{opp_arch}_ep{ep}.html"
    out = os.path.join(outdir or os.path.join(ROOT, "replays"), fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(page)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+", help="エピソードID or replay.jsonパス")
    ap.add_argument("--outdir", default=None, help="出力フォルダ(既定: replays/)")
    ap.add_argument("--prefix", default="", help="ファイル名の接頭辞(例: A_ガルーラ検証_)")
    args = ap.parse_args()
    jp_db = load_jp_db()
    atk_jp = load_attack_jp(jp_db)
    outdir = None
    if args.outdir:
        outdir = args.outdir if os.path.isabs(args.outdir) else os.path.join(ROOT, args.outdir)
    for i, arg in enumerate(args.episodes):
        prefix = args.prefix
        out = render(find_replay(arg), jp_db, atk_jp, outdir=outdir, prefix=prefix)
        print("->", out)


if __name__ == "__main__":
    main()
