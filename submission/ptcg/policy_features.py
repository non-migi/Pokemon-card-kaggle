"""BC方策の特徴量(学習と推論で共有)。

すべて「生のobs dict」(select/currentのdict形式、enumはint)を入力にする —
学習データ(エピソードJSON)と本番のobs_dictが同一形式のため。
特徴量バージョンを変えたら POLICY_FEATURE_VERSION を上げること。
"""

POLICY_FEATURE_VERSION = 1

# SelectType 0..10 / OptionType 0..16 / AreaType 1..12
N_SELECT_TYPE = 11
N_OPTION_TYPE = 17
N_AREA = 13
N_CARD_TYPE = 7
N_CONTEXT = 50  # SelectContextは49+今後の追加をクリップ

try:
    from cg.api import all_card_data, all_attack

    _CARDS = {c.cardId: c for c in all_card_data()}
    _ATTACKS = {a.attackId: a for a in all_attack()}
except Exception:  # 学習側でcgが無い場合は呼び手が注入する
    _CARDS, _ATTACKS = {}, {}


def _onehot(i, n):
    v = [0.0] * n
    if 0 <= i < n:
        v[i] = 1.0
    return v


def _side_feats(p: dict) -> list[float]:
    active = (p.get("active") or [None])
    a = active[0] if active else None
    bench = [x for x in (p.get("bench") or []) if x]
    return [
        len(p.get("prize") or []) / 6.0,
        (a.get("hp", 0) / 300.0) if a else 0.0,
        (a.get("maxHp", 0) / 300.0) if a else 0.0,
        (len(a.get("energies") or []) / 5.0) if a else 0.0,
        1.0 if a is None else 0.0,
        len(bench) / 5.0,
        sum(x.get("hp", 0) for x in bench) / 800.0,
        sum(len(x.get("energies") or []) for x in bench) / 10.0,
        p.get("deckCount", 0) / 60.0,
        p.get("handCount", len(p.get("hand") or [])) / 15.0,
        len(p.get("discard") or []) / 40.0,
        1.0 if p.get("poisoned") else 0.0,
        1.0 if p.get("asleep") or p.get("paralyzed") or p.get("confused") or p.get("burned") else 0.0,
    ]


def state_features(sel: dict, cur: dict) -> list[float]:
    me = cur.get("yourIndex", 0)
    players = cur.get("players") or [{}, {}]
    f = _side_feats(players[me]) + _side_feats(players[1 - me])
    f += [
        min(cur.get("turn", 0), 30) / 30.0,
        1.0 if cur.get("firstPlayer", -1) == me else 0.0,
        1.0 if cur.get("supporterPlayed") else 0.0,
        1.0 if cur.get("energyAttached") else 0.0,
        1.0 if cur.get("stadium") else 0.0,
        (len(players[1 - me].get("prize") or []) - len(players[me].get("prize") or [])) / 6.0,
        min(sel.get("maxCount", 1), 5) / 5.0,
    ]
    f += _onehot(sel.get("type", 0), N_SELECT_TYPE)
    f += _onehot(min(sel.get("context", 0), N_CONTEXT - 1), N_CONTEXT)
    return f


N_STATE = 13 * 2 + 7 + N_SELECT_TYPE + N_CONTEXT


def _resolve_card_id(sel: dict, cur: dict, opt: dict):
    area = opt.get("area")
    idx = opt.get("index")
    me = cur.get("yourIndex", 0)
    try:
        if area == 12:  # LOOKING
            c = (cur.get("looking") or [])[idx]
            return c.get("id") if c else None
        if area == 1:  # DECK
            deck = sel.get("deck")
            return deck[idx].get("id") if deck else None
        pl = (cur.get("players") or [])[opt.get("playerIndex", me)]
        if area == 2:
            hand = pl.get("hand")
            return hand[idx].get("id") if hand else None
        if area == 4:
            a = (pl.get("active") or [])[idx]
            return a.get("id") if a else None
        if area == 5:
            return (pl.get("bench") or [])[idx].get("id")
        if area == 3:
            return (pl.get("discard") or [])[idx].get("id")
    except (IndexError, TypeError, AttributeError):
        pass
    return None


def _target_pokemon(cur: dict, opt: dict):
    """ATTACH/EVOLVE等のinPlay対象、またはCARDの場ポケモン。"""
    me = cur.get("yourIndex", 0)
    area = opt.get("inPlayArea") or opt.get("area")
    idx = opt.get("inPlayIndex") if opt.get("inPlayArea") is not None else opt.get("index")
    pi = opt.get("playerIndex", me)
    try:
        pl = (cur.get("players") or [])[pi if opt.get("inPlayArea") is None else me]
        if area == 4:
            return (pl.get("active") or [None])[idx]
        if area == 5:
            return (pl.get("bench") or [])[idx]
    except (IndexError, TypeError, AttributeError):
        pass
    return None


def option_features(sel: dict, cur: dict, opt: dict, cards=None, attacks=None):
    """(数値特徴, 主カードID) を返す。カードIDは埋め込み用(Noneあり)。"""
    cards = cards or _CARDS
    attacks = attacks or _ATTACKS
    me = cur.get("yourIndex", 0)
    t = opt.get("type", 0)
    f = _onehot(t, N_OPTION_TYPE)
    f += _onehot(opt.get("area") or 0, N_AREA)
    f.append(1.0 if opt.get("playerIndex", me) == me else 0.0)
    f.append((opt.get("number") or 0) / 10.0)

    # ワザ
    dmg = cost = 0.0
    aid = opt.get("attackId")
    if aid is not None and aid in attacks:
        a = attacks[aid]
        dmg = (a.damage or 0) / 300.0
        cost = len(a.energies) / 5.0
    f += [dmg, cost]

    # 主カード(PLAY: 手札 / CARD系: 解決 / ATTACH: 付けるカード)
    cid = None
    if t == 7:  # PLAY
        try:
            cid = (cur["players"][me].get("hand") or [])[opt.get("index")].get("id")
        except (IndexError, TypeError, KeyError, AttributeError):
            cid = None
    elif t in (3, 8, 9):  # CARD / ATTACH / EVOLVE
        cid = _resolve_card_id(sel, cur, opt)
    elif t in (10, 11):  # ABILITY / DISCARD (場のカード)
        cid = _resolve_card_id(sel, cur, opt)

    c = cards.get(cid) if cid is not None else None
    if c is not None:
        f += _onehot(c.cardType, N_CARD_TYPE)
        f += [
            (c.hp or 0) / 300.0,
            1.0 if c.basic else 0.0,
            1.0 if c.ex else 0.0,
            1.0 if c.megaEx else 0.0,
        ]
    else:
        f += [0.0] * (N_CARD_TYPE + 4)

    # 対象ポケモンの状態(ATTACH先・CARD対象)
    tp = _target_pokemon(cur, opt)
    if tp:
        f += [tp.get("hp", 0) / 300.0, tp.get("maxHp", 0) / 300.0, len(tp.get("energies") or []) / 5.0]
    else:
        f += [0.0, 0.0, 0.0]
    return f, cid


N_OPTION = N_OPTION_TYPE + N_AREA + 2 + 2 + N_CARD_TYPE + 4 + 3
