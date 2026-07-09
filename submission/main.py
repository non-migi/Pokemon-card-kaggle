"""ヒューリスティックエージェント v1.

方針(ドメイン知識最小):
- メイン行動: 進化 > エネルギー付与(バトル場優先) > カードプレイ > 特性 > ワザ(最大ダメージ) > 逃げる > 番を終える
- ワザ選択: ダメージ最大
- カード選択: contextに応じてHP・ダメージ蓄積などの汎用スコアで貪欲に選ぶ
- YES/NO: 原則YES(退化継続のみNO)
- 数選択: 最大値

enum値はコンペ期間中に追加されうるため、未知の値でも落ちないように
すべてintで比較し、デフォルト分岐を必ず持つ。
"""

import os
import random

from cg.api import to_observation_class, all_card_data, all_attack

# ---- 静的データ(プロセス内で1回だけロード) ----
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

# SelectContext(スコアリングに使うもの)
CTX_DAMAGE_TARGETS = {13, 14, 15}          # ダメカン/ダメージを与える対象
CTX_HEAL_TARGETS = {16, 17}                # 回復対象
CTX_PICK_STRONG = {1, 2, 3, 4, 5, 6, 7}    # 場に出す/手札に加えるポケモン
CTX_BAD_FOR_ME = {8, 9, 10, 11, 26, 27, 29, 30}  # 自分のリソースを失う選択
CTX_MORE_DEVOLVE = 45


def read_deck_csv() -> list[int]:
    # 注意: Kaggleのローダーはexec()でロードするため __file__ は使えない。
    # 同梱の cg パッケージの位置から提出ディレクトリを特定する。
    import cg

    agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(cg.__file__)))
    candidates = [
        os.path.join(agent_dir, "deck.csv"),
        "deck.csv",
        "/kaggle_simulations/agent/deck.csv",
    ]
    file_path = next((p for p in candidates if os.path.exists(p)), candidates[-1])
    with open(file_path, "r") as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


def _resolve_card_id(obs, opt):
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


def _resolve_pokemon(obs, opt):
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


def _card_value(card_id) -> float:
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
    if c.cardType == 3:  # SUPPORTER(ドロー系が多く価値が高い)
        return 90.0
    if c.cardType == 1:  # ITEM
        return 80.0
    if c.cardType in (5, 6):  # ENERGY
        return 60.0
    return 50.0


def _attack_damage(attack_id) -> int:
    a = ATTACKS.get(attack_id)
    return a.damage if a else 0


def _score_main(obs, opt) -> float:
    """メインフェーズの行動スコア。高いほど先に選ぶ。"""
    t = opt.type
    if t == OT_EVOLVE:
        return 900
    if t == OT_ATTACH:
        # エネルギー手貼り。バトル場を優先
        return 800 + (50 if opt.inPlayArea == AR_ACTIVE else 0)
    if t == OT_PLAY:
        try:
            cid = obs.current.players[obs.current.yourIndex].hand[opt.index].id
            return 700 + _card_value(cid) / 10
        except (IndexError, TypeError, AttributeError):
            return 700
    if t == OT_ABILITY:
        return 600
    if t == OT_ATTACK:
        return 500 + _attack_damage(opt.attackId) / 10
    # 自発的な逃げは実測で悪手(エネルギー損失)。ENDより下げて選ばない
    if t == OT_RETREAT:
        return -10
    if t == OT_DISCARD:
        return 40
    if t == OT_END:
        return 0
    return 10  # 未知のOptionType


def _score_card(obs, opt, context) -> float:
    """カード選択のスコア(context依存)。"""
    if context in CTX_DAMAGE_TARGETS:
        # 相手ポケモンにダメージ: HPが低い個体を狙って倒しにいく
        p = _resolve_pokemon(obs, opt)
        return 1000 - p.hp if p else 0
    if context in CTX_HEAL_TARGETS:
        # 回復: ダメージ蓄積が大きい個体
        p = _resolve_pokemon(obs, opt)
        return (p.maxHp - p.hp) if p else 0
    cid = _resolve_card_id(obs, opt)
    v = _card_value(cid) if cid is not None else 50.0
    if context in CTX_BAD_FOR_ME:
        return -v  # 失うものは価値が低い順
    return v  # 得るもの・場に出すものは価値が高い順


def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return read_deck_csv()

    sel = obs.select
    opts = sel.option
    n = len(opts)
    lo, hi = sel.minCount, min(sel.maxCount, n)
    stype = sel.type
    ctx = sel.context

    # 選択数: 自分が損する選択は最小限、それ以外は最大限
    k = lo if ctx in CTX_BAD_FOR_ME else hi
    k = max(lo, min(k, hi))

    # YES/NO
    if stype == ST_YES_NO:
        want_yes = ctx != CTX_MORE_DEVOLVE
        for i, o in enumerate(opts):
            if (o.type == OT_YES) == want_yes:
                return [i]
        return [0]

    # 数選択: 最大値
    if stype == ST_COUNT:
        best = max(range(n), key=lambda i: opts[i].number or 0)
        return [best]

    # メイン行動
    if stype == ST_MAIN:
        # 行動しすぎたターンは強制的に収束させる(無限ループ対策)
        if obs.current and obs.current.turnActionCount > 40:
            for i, o in enumerate(opts):
                if o.type == OT_ATTACK:
                    return [i]
            for i, o in enumerate(opts):
                if o.type == OT_END:
                    return [i]
        best = max(range(n), key=lambda i: _score_main(obs, opts[i]))
        return [best]

    # ワザ選択: 最大ダメージ
    if stype == ST_ATTACK:
        best = max(range(n), key=lambda i: _attack_damage(opts[i].attackId or 0))
        return [best]

    # カード選択: スコア上位k件
    if stype in (ST_CARD, ST_CARD_OR_ATT, ST_ATTACHED):
        ranked = sorted(range(n), key=lambda i: _score_card(obs, opts[i], ctx), reverse=True)
        return ranked[:k]

    # その他(ENERGY, SKILL, EVOLVE, COND, 未知のtype): 先頭からk件
    if k <= 0:
        return []
    return list(range(k))
