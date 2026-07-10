"""ヒューリスティック方針(v1.1由来)。

Observationデータクラスを受け取り行動を返す `choose(obs)` を提供する。
- エージェント本体のフォールバック
- 決定化探索のロールアウト方針
の両方で使う。enumはコンペ中に追加されうるため、intで比較しデフォルト分岐を持つ。
"""

import random

from cg.api import all_card_data, all_attack

CARDS = {c.cardId: c for c in all_card_data()}
ATTACKS = {a.attackId: a for a in all_attack()}

# SelectType
ST_MAIN, ST_CARD, ST_ATTACHED, ST_CARD_OR_ATT, ST_ENERGY = 0, 1, 2, 3, 4
ST_SKILL, ST_ATTACK, ST_EVOLVE, ST_COUNT, ST_YES_NO, ST_COND = 5, 6, 7, 8, 9, 10

# OptionType
OT_NUMBER, OT_YES, OT_NO, OT_CARD = 0, 1, 2, 3
OT_PLAY, OT_ATTACH, OT_EVOLVE, OT_ABILITY = 7, 8, 9, 10
OT_DISCARD, OT_RETREAT, OT_ATTACK, OT_END = 11, 12, 13, 14

# AreaType
AR_DECK, AR_HAND, AR_DISCARD, AR_ACTIVE, AR_BENCH, AR_PRIZE = 1, 2, 3, 4, 5, 6
AR_LOOKING = 12

# SelectContext
CTX_DAMAGE_TARGETS = {13, 14, 15}
CTX_HEAL_TARGETS = {16, 17}
CTX_BAD_FOR_ME = {8, 9, 10, 11, 26, 27, 29, 30}
CTX_MORE_DEVOLVE = 45


def resolve_card_id(obs, opt):
    """CARD option (area/index/playerIndex) → カードID。不明ならNone。"""
    try:
        area, idx = opt.area, opt.index
        if area == AR_LOOKING:
            c = obs.current.looking[idx]
            return c.id if c else None
        if area == AR_DECK:
            if obs.select.deck:
                return obs.select.deck[idx].id
            return None
        pl = obs.current.players[opt.playerIndex]
        if area == AR_HAND:
            return pl.hand[idx].id if pl.hand else None
        if area == AR_ACTIVE:
            p = pl.active[idx]
            return p.id if p else None
        if area == AR_BENCH:
            return pl.bench[idx].id
        if area == AR_DISCARD:
            return pl.discard[idx].id
        if area == AR_PRIZE:
            c = pl.prize[idx]
            return c.id if c else None
    except (IndexError, TypeError, AttributeError):
        pass
    return None


def resolve_pokemon(obs, opt):
    """CARD optionが場のポケモンを指す場合、Pokemonオブジェクトを返す。"""
    try:
        pl = obs.current.players[opt.playerIndex]
        if opt.area == AR_ACTIVE:
            return pl.active[opt.index]
        if opt.area == AR_BENCH:
            return pl.bench[opt.index]
    except (IndexError, TypeError, AttributeError):
        pass
    return None


def card_value(card_id) -> float:
    """カードの汎用価値。ポケモンはHP、トレーナーズ系は固定値。"""
    c = CARDS.get(card_id)
    if c is None:
        return 50.0
    if c.cardType == 0:  # POKEMON
        v = float(c.hp or 0)
        if c.ex:
            v += 40
        if c.megaEx:
            v += 60
        return v
    if c.cardType == 3:  # SUPPORTER
        return 90.0
    if c.cardType == 1:  # ITEM
        return 80.0
    if c.cardType in (5, 6):  # ENERGY
        return 60.0
    return 50.0


def attack_damage(attack_id) -> int:
    a = ATTACKS.get(attack_id)
    return a.damage if a else 0


def max_attack_cost(card_id) -> int:
    """そのポケモンの最大ワザコスト(=これ以上エネを貼っても無駄になる枚数)。"""
    c = CARDS.get(card_id)
    if c is None:
        return 3
    return max((len(ATTACKS[a].energies) for a in c.attacks if a in ATTACKS), default=0)


def prize_give(card_id) -> int:
    """このポケモンが倒されたとき相手に取られるサイド枚数。"""
    c = CARDS.get(card_id)
    if c is None:
        return 1
    return 3 if c.megaEx else (2 if c.ex else 1)


def _in_play_pokemon(obs, area, index):
    """自分の場のポケモン(inPlayArea/inPlayIndex)を解決。"""
    try:
        pl = obs.current.players[obs.current.yourIndex]
        if area == AR_ACTIVE:
            return pl.active[index]
        if area == AR_BENCH:
            return pl.bench[index]
    except (IndexError, TypeError, AttributeError):
        pass
    return None


def score_main(obs, opt) -> float:
    t = opt.type
    if t == OT_EVOLVE:
        return 900
    if t == OT_ATTACH:
        # 人間レビューH1(2026-07-10): 最大ワザコスト分だけ貼れたポケモンへの追加は無駄。
        # 未充電のバトル場 > 未充電のベンチ(次アタッカー) > 充電済み の順
        target = _in_play_pokemon(obs, opt.inPlayArea, opt.inPlayIndex)
        if target is not None and len(target.energies) >= max_attack_cost(target.id) > 0:
            return 640  # 充電済み: 他にやることがなければ貼る(手貼り権は無料)
        bonus = card_value(target.id) / 50 if target is not None else 0
        return 800 + (50 if opt.inPlayArea == AR_ACTIVE else 0) + bonus
    if t == OT_PLAY:
        try:
            cid = obs.current.players[obs.current.yourIndex].hand[opt.index].id
            return 700 + card_value(cid) / 10
        except (IndexError, TypeError, AttributeError):
            return 700
    if t == OT_ABILITY:
        return 600
    if t == OT_ATTACK:
        return 500 + attack_damage(opt.attackId) / 10
    # 自発的な逃げは実測で悪手(experiments.md 2026-07-09)
    if t == OT_RETREAT:
        return -10
    if t == OT_DISCARD:
        return 40
    if t == OT_END:
        return 0
    return 10


def score_card(obs, opt, context) -> float:
    if context in CTX_DAMAGE_TARGETS:
        p = resolve_pokemon(obs, opt)
        return 1000 - p.hp if p else 0
    if context in CTX_HEAL_TARGETS:
        p = resolve_pokemon(obs, opt)
        return (p.maxHp - p.hp) if p else 0
    cid = resolve_card_id(obs, opt)
    v = card_value(cid) if cid is not None else 50.0
    return -v if context in CTX_BAD_FOR_ME else v


def choose(obs) -> list[int]:
    """Observationデータクラスから行動を選ぶ(v1.1ヒューリスティック)。"""
    sel = obs.select
    opts = sel.option
    n = len(opts)
    lo, hi = sel.minCount, min(sel.maxCount, n)
    stype = sel.type
    ctx = sel.context

    k = lo if ctx in CTX_BAD_FOR_ME else hi
    k = max(lo, min(k, hi))

    if stype == ST_YES_NO:
        want_yes = ctx != CTX_MORE_DEVOLVE
        for i, o in enumerate(opts):
            if (o.type == OT_YES) == want_yes:
                return [i]
        return [0]

    if stype == ST_COUNT:
        return [max(range(n), key=lambda i: opts[i].number or 0)]

    if stype == ST_MAIN:
        if obs.current and obs.current.turnActionCount > 40:
            for i, o in enumerate(opts):
                if o.type == OT_ATTACK:
                    return [i]
            for i, o in enumerate(opts):
                if o.type == OT_END:
                    return [i]
        return [max(range(n), key=lambda i: score_main(obs, opts[i]))]

    if stype == ST_ATTACK:
        return [max(range(n), key=lambda i: attack_damage(opts[i].attackId or 0))]

    if stype in (ST_CARD, ST_CARD_OR_ATT, ST_ATTACHED):
        ranked = sorted(range(n), key=lambda i: score_card(obs, opts[i], ctx), reverse=True)
        return ranked[:k]

    if k <= 0:
        return []
    return list(range(k))
