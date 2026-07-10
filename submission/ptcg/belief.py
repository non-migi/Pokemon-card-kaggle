"""隠れ情報のサンプリング(決定化)。

自分のデッキリストは既知なので、可視カードを除いた残りが山札+裏サイドの候補。
相手は「観測カードとの一致度」でメタデッキライブラリ(meta_decks.py)から推定し、
どれとも合わなければミラー仮定(自分と同じデッキリスト)にフォールバックする。
"""

import random
from collections import Counter

from .heuristics import CARDS
from .meta_decks import META_DECKS

# 観測カードのうちこの割合以上をメタデッキで説明できれば採用
MATCH_THRESHOLD = 0.7


def _remove_visible(pool: list[int], player, stadium, player_index: int) -> None:
    """poolから、そのプレイヤーの可視カードを取り除く(見つからないIDは無視)。"""

    def rm(card_id):
        try:
            pool.remove(card_id)
        except ValueError:
            pass

    for c in (player.hand or []):
        rm(c.id)
    for c in player.discard:
        rm(c.id)
    for p in list(player.active) + list(player.bench):
        if p:
            rm(p.id)
            for e in p.energyCards:
                rm(e.id)
            for t in p.tools:
                rm(t.id)
            for pe in p.preEvolution:
                rm(pe.id)
    for c in player.prize:
        if c:
            rm(c.id)
    for c in stadium:
        if c.playerIndex == player_index:
            rm(c.id)


def observed_cards(player, stadium, player_index: int) -> list[int]:
    """そのプレイヤーの可視カードID一覧(付属カード・進化元も含む)。"""
    seen: list[int] = []
    for c in (player.hand or []):
        seen.append(c.id)
    for c in player.discard:
        seen.append(c.id)
    for p in list(player.active) + list(player.bench):
        if p:
            seen.append(p.id)
            seen.extend(e.id for e in p.energyCards)
            seen.extend(t.id for t in p.tools)
            seen.extend(pe.id for pe in p.preEvolution)
    for c in player.prize:
        if c:
            seen.append(c.id)
    for c in stadium:
        if c.playerIndex == player_index:
            seen.append(c.id)
    return seen


def infer_opponent_deck(obs, my_deck: list[int]) -> list[int]:
    """相手の可視カードに最も整合するデッキリストを推定する。"""
    cur = obs.current
    me = cur.yourIndex
    opp = cur.players[1 - me]
    seen = Counter(observed_cards(opp, cur.stadium, 1 - me))
    n_seen = sum(seen.values())
    if n_seen == 0:
        return list(my_deck)  # 情報なし: ミラー仮定

    best_deck, best_cover = None, -1
    for deck in META_DECKS + [my_deck]:
        dc = Counter(deck)
        cover = sum(min(k, dc.get(cid, 0)) for cid, k in seen.items())
        if cover > best_cover:
            best_cover, best_deck = cover, deck

    if best_cover / n_seen >= MATCH_THRESHOLD:
        return list(best_deck)
    return list(my_deck)


def sample_world(obs, my_deck: list[int], rng: random.Random | None = None):
    """search_begin に渡す世界を1つサンプリングする。

    Returns:
        (your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active)
    """
    rng = rng or random
    cur = obs.current
    me = cur.yourIndex
    mine, opp = cur.players[me], cur.players[1 - me]

    # 自分: 残りプールを山札と裏サイドに配る
    pool = list(my_deck)
    _remove_visible(pool, mine, cur.stadium, me)
    rng.shuffle(pool)
    n_prize_hidden = sum(1 for c in mine.prize if c is None)
    your_prize = pool[:n_prize_hidden]
    your_deck = pool[n_prize_hidden:]

    # 相手: 推定デッキ(メタ照合、失敗時ミラー)から残りプールを手札・裏サイド・山札に配る
    opool = infer_opponent_deck(obs, my_deck)
    _remove_visible(opool, opp, cur.stadium, 1 - me)
    n_hand = opp.handCount
    n_oprize = sum(1 for c in opp.prize if c is None)
    needed = n_hand + n_oprize + opp.deckCount
    if len(opool) < needed:
        # 推定デッキと観測の不整合: 汎用カードでパディング
        filler = next((cid for cid in opool if CARDS[cid].cardType == 5), None)
        basics = [cid for cid in opool if (c := CARDS.get(cid)) and c.cardType == 0 and c.basic]
        pad = filler if filler is not None else (basics[0] if basics else opool[0] if opool else 3)
        opool += [pad] * (needed - len(opool))
    rng.shuffle(opool)
    opp_hand = opool[:n_hand]
    opp_prize = opool[n_hand:n_hand + n_oprize]
    opp_deck = opool[n_hand + n_oprize:]

    # 相手のバトル場が裏向き(セットアップ中)なら、たねポケモンを1体推定
    opp_active: list[int] = []
    if len(opp.active) > 0 and opp.active[0] is None:
        basics = [cid for cid in opool if (c := CARDS.get(cid)) and c.basic]
        opp_active = [rng.choice(basics)] if basics else [opool[0]]

    return your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active
