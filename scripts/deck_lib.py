"""デッキの生成・合法性チェック・変異オペレータ。

ドメイン知識レス方針: カードの効果テキストは使わない。
初期集団の生成にのみ統計的事前分布(HP・ワザダメージ)を使い、良し悪しの判断は
すべて対戦勝率(deck_opt.py)に委ねる。
"""

import random
import sys
from collections import Counter

sys.path.insert(0, "src")

from cg.api import all_card_data, all_attack

CARDS = {c.cardId: c for c in all_card_data()}
ATTACKS = {a.attackId: a for a in all_attack()}

POKEMON, ITEM, TOOL, SUPPORTER, STADIUM, BASIC_ENERGY, SPECIAL_ENERGY = 0, 1, 2, 3, 4, 5, 6

# 名前→そのカードの全ID(同名制限は名前単位)
NAME_TO_IDS: dict[str, list[int]] = {}
for c in CARDS.values():
    NAME_TO_IDS.setdefault(c.name, []).append(c.cardId)

BASIC_ENERGY_IDS = {c.cardId: c.energyType for c in CARDS.values() if c.cardType == BASIC_ENERGY}
# エネルギータイプ → 基本エネルギーID
ENERGY_ID_OF_TYPE = {t: cid for cid, t in BASIC_ENERGY_IDS.items()}

TRAINER_IDS = [c.cardId for c in CARDS.values() if c.cardType in (ITEM, TOOL, SUPPORTER, STADIUM)]
NON_ACE_TRAINER_IDS = [i for i in TRAINER_IDS if not CARDS[i].aceSpec]


def max_damage(card) -> int:
    return max((ATTACKS[a].damage for a in card.attacks if a in ATTACKS), default=0)


def _build_lines() -> list[dict]:
    """進化ライン(たね[→1進化[→2進化]])の一覧を作る。"""
    by_name = {}
    for c in CARDS.values():
        if c.cardType == POKEMON:
            by_name.setdefault(c.name, []).append(c)
    lines = []
    for c in CARDS.values():
        if c.cardType != POKEMON:
            continue
        if c.basic:
            lines.append({"type": c.energyType, "stages": [c.cardId], "top": c})
        else:
            # 進化元をたねまで辿る
            chain = [c]
            cur = c
            ok = True
            while not cur.basic:
                prevs = by_name.get(cur.evolvesFrom or "", [])
                if not prevs:
                    ok = False
                    break
                cur = max(prevs, key=lambda x: x.hp or 0)
                chain.append(cur)
            if ok:
                lines.append({
                    "type": c.energyType,
                    "stages": [x.cardId for x in reversed(chain)],
                    "top": c,
                })
    return lines


LINES = _build_lines()


def line_score(line) -> float:
    """初期集団用の事前スコア: 最終進化の打点とHP、少ない段数を好む。"""
    top = line["top"]
    dmg = max_damage(top)
    prize_risk = 40 * (2 if top.ex else 0) + 40 * (1 if top.megaEx else 0)
    return dmg * 1.5 + (top.hp or 0) - 30 * (len(line["stages"]) - 1) - prize_risk


# ---- 合法性 ----

def legality_error(deck: list[int]) -> str | None:
    """静的な合法性チェック。問題なければNone。"""
    if len(deck) != 60:
        return f"60枚でない({len(deck)})"
    names = Counter()
    n_basic_pokemon = 0
    n_ace = 0
    for cid in deck:
        c = CARDS.get(cid)
        if c is None:
            return f"未知のカードID {cid}"
        if c.cardType != BASIC_ENERGY:
            names[c.name] += 1
        if c.cardType == POKEMON and c.basic:
            n_basic_pokemon += 1
        if c.aceSpec:
            n_ace += 1
    over = [n for n, k in names.items() if k > 4]
    if over:
        return f"同名5枚以上: {over[:3]}"
    if n_basic_pokemon == 0:
        return "たねポケモンが0枚"
    if n_ace > 1:
        return f"ACE SPECが{n_ace}枚"
    return None


# ---- 生成 ----

def generate_deck(rng: random.Random) -> list[int]:
    """テンプレートベースでランダムな合法デッキを1つ生成。"""
    for _ in range(50):
        deck = _try_generate(rng)
        if deck is not None and legality_error(deck) is None:
            return deck
    raise RuntimeError("デッキ生成に失敗")


def _try_generate(rng: random.Random) -> list[int] | None:
    etype = rng.choice([t for t in ENERGY_ID_OF_TYPE if t != 0])  # 無色以外
    cand = [l for l in LINES if l["type"] == etype]
    if not cand:
        return None
    cand.sort(key=line_score, reverse=True)
    topk = cand[: max(8, len(cand) // 20)]
    deck: list[int] = []

    # アタッカーライン1-2本
    lines = rng.sample(topk, k=min(len(topk), rng.choice([1, 2, 2])))
    for li, line in enumerate(lines):
        n = 4 if li == 0 else rng.choice([2, 3])
        for stage_id in line["stages"]:
            deck += [stage_id] * n
    # たねが薄いなら高HPのたねを足す
    n_basic = sum(1 for cid in deck if CARDS[cid].basic and CARDS[cid].cardType == POKEMON)
    if n_basic < 6:
        fillers = sorted(
            (l for l in LINES if len(l["stages"]) == 1),
            key=lambda l: (l["top"].hp or 0) - 40 * (l["top"].ex + l["top"].megaEx),
            reverse=True,
        )[:12]
        f = rng.choice(fillers)
        deck += [f["stages"][0]] * rng.choice([2, 3])

    # エネルギー
    n_energy = rng.randint(10, 16)
    deck += [ENERGY_ID_OF_TYPE[etype]] * n_energy

    # トレーナーズで60枚まで埋める(4枚単位で数種類)
    while len(deck) < 60:
        t = rng.choice(NON_ACE_TRAINER_IDS)
        k = min(rng.choice([2, 3, 4]), 60 - len(deck))
        deck += [t] * k
    return deck[:60]


# ---- 変異 ----

def _counts(deck: list[int]) -> Counter:
    return Counter(deck)


def _can_add(deck: list[int], cid: int) -> bool:
    c = CARDS[cid]
    if c.cardType == BASIC_ENERGY:
        return True
    if c.aceSpec and any(CARDS[x].aceSpec for x in deck):
        return False
    same = sum(1 for x in deck if CARDS[x].name == c.name)
    return same < 4


def mutate(deck: list[int], rng: random.Random) -> list[int]:
    """合法性を保ったまま1〜3箇所を変異させる。"""
    for _ in range(60):
        d = list(deck)
        op = rng.random()
        if op < 0.35:
            _op_count_shift(d, rng)
        elif op < 0.65:
            _op_replace_card(d, rng)
        elif op < 0.85:
            _op_replace_line(d, rng)
        else:
            _op_energy_shift(d, rng)
        if len(d) == 60 and legality_error(d) is None:
            return d
    return list(deck)


def _op_count_shift(d: list[int], rng: random.Random) -> None:
    """あるカードを1枚減らし、デッキ内の別カードを1枚増やす。"""
    i = rng.randrange(len(d))
    victim = d.pop(i)
    grow = rng.choice([x for x in d if x != victim] or d)
    if _can_add(d, grow):
        d.append(grow)
    else:
        d.append(victim)


def _op_replace_card(d: list[int], rng: random.Random) -> None:
    """あるカード(同名全部)をランダムな別カードに入れ替える。"""
    victim = rng.choice(d)
    vname = CARDS[victim].name
    k = sum(1 for x in d if CARDS[x].name == vname)
    d[:] = [x for x in d if CARDS[x].name != vname]
    vt = CARDS[victim].cardType
    if vt == POKEMON:
        pool = [l["stages"][-1] for l in LINES]
        new = rng.choice(pool)
        line = next(l for l in LINES if l["stages"][-1] == new)
        per = max(1, k // len(line["stages"]))
        for sid in line["stages"]:
            for _ in range(min(per, 4)):
                if len(d) < 60 and _can_add(d, sid):
                    d.append(sid)
    else:
        new = rng.choice(NON_ACE_TRAINER_IDS + list(BASIC_ENERGY_IDS))
        for _ in range(k):
            if len(d) < 60 and _can_add(d, new):
                d.append(new)
    while len(d) < 60:
        filler = rng.choice(d)
        d.append(filler if _can_add(d, filler) else next(iter(ENERGY_ID_OF_TYPE.values())))


def _op_replace_line(d: list[int], rng: random.Random) -> None:
    """ポケモンの進化ライン1本を、同タイプの別ラインに入れ替える。"""
    pk_names = {CARDS[x].name for x in d if CARDS[x].cardType == POKEMON}
    if not pk_names:
        return
    name = rng.choice(sorted(pk_names))
    old = [x for x in d if CARDS[x].name == name]
    k = len(old)
    etypes = {CARDS[x].energyType for x in d if CARDS[x].cardType == BASIC_ENERGY}
    cand = [l for l in LINES if not etypes or l["type"] in etypes]
    if not cand:
        return
    cand.sort(key=line_score, reverse=True)
    line = rng.choice(cand[:40])
    d[:] = [x for x in d if CARDS[x].name != name]
    per = max(1, min(4, k // len(line["stages"])))
    for sid in line["stages"]:
        for _ in range(per):
            if len(d) < 60 and _can_add(d, sid):
                d.append(sid)
    while len(d) < 60:
        d.append(rng.choice([x for x in d] or [next(iter(ENERGY_ID_OF_TYPE.values()))]))


def _op_energy_shift(d: list[int], rng: random.Random) -> None:
    """エネルギー枚数を±1(トレーナーズと入れ替え)。"""
    energies = [i for i, x in enumerate(d) if CARDS[x].cardType == BASIC_ENERGY]
    if rng.random() < 0.5 and energies:
        d.pop(rng.choice(energies))
        d.append(rng.choice(NON_ACE_TRAINER_IDS))
    elif energies:
        i = rng.randrange(len(d))
        if CARDS[d[i]].cardType != BASIC_ENERGY:
            d[i] = d[energies[0]]


def crossover(a: list[int], b: list[int], rng: random.Random) -> list[int]:
    """Aのポケモン+エネルギー核とBのトレーナーズを合成。"""
    core = [x for x in a if CARDS[x].cardType in (POKEMON, BASIC_ENERGY, SPECIAL_ENERGY)]
    trainers = [x for x in b if CARDS[x].cardType in (ITEM, TOOL, SUPPORTER, STADIUM)]
    rng.shuffle(trainers)
    d = list(core)
    for t in trainers:
        if len(d) >= 60:
            break
        if _can_add(d, t):
            d.append(t)
    while len(d) < 60:
        d.append(next(iter(ENERGY_ID_OF_TYPE.values())))
    d = d[:60]
    return d if legality_error(d) is None else list(a)


def save_deck(deck: list[int], path: str) -> None:
    with open(path, "w") as f:
        f.write("\n".join(str(x) for x in deck) + "\n")


def load_deck(path: str) -> list[int]:
    with open(path) as f:
        return [int(l) for l in f.read().split("\n") if l.strip()][:60]


def describe(deck: list[int]) -> str:
    names = Counter(CARDS[x].name for x in deck)
    groups = {"PKM": [], "TRA": [], "ENE": []}
    seen = set()
    for x in deck:
        c = CARDS[x]
        if c.name in seen:
            continue
        seen.add(c.name)
        g = "PKM" if c.cardType == POKEMON else ("ENE" if c.cardType in (BASIC_ENERGY, SPECIAL_ENERGY) else "TRA")
        groups[g].append(f"{names[c.name]}x {c.name}")
    return " | ".join(f"{g}: {', '.join(v)}" for g, v in groups.items())
