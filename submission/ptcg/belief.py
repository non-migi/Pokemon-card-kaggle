"""隠れ情報のサンプリング(決定化)。

自分のデッキリストは既知なので、可視カードを除いた残りが山札+裏サイドの候補。
相手はミラー仮定(自分と同じデッキリスト)で埋める。
※ 相手デッキの推定精度向上(メタデッキ分布・ログからの絞り込み)は今後の課題。
"""

import random

from .heuristics import CARDS


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

    # 相手: ミラー仮定で残りプールを手札・裏サイド・山札に配る
    opool = list(my_deck)
    _remove_visible(opool, opp, cur.stadium, 1 - me)
    rng.shuffle(opool)
    n_hand = opp.handCount
    opp_hand = opool[:n_hand]
    n_oprize = sum(1 for c in opp.prize if c is None)
    opp_prize = opool[n_hand:n_hand + n_oprize]
    opp_deck = opool[n_hand + n_oprize:]

    # 相手のバトル場が裏向き(セットアップ中)なら、たねポケモンを1体推定
    opp_active: list[int] = []
    if len(opp.active) > 0 and opp.active[0] is None:
        basics = [cid for cid in opool if (c := CARDS.get(cid)) and c.basic]
        opp_active = [rng.choice(basics)] if basics else [opool[0]]

    return your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active
