"""探索API(search_begin/search_step)のプロトタイプ検証。

1. 対戦を回して中盤のMAIN選択のobsを捕獲
2. 自分デッキは既知として世界を1つサンプリング
3. search_beginで決定化 → 各合法手をsearch_stepで展開 → ロールアウト
4. 所要時間を計測(1手読みの予算設計のため)
"""

import random
import sys
import time

sys.path.insert(0, "submission")

from kaggle_environments import make
from cg.api import to_observation_class, search_begin, search_step, search_end
import main as my

DECK = my.read_deck_csv()

captured = []


def capture_agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is not None and obs.select.type == 0 and obs.current and obs.current.turn >= 3:
        captured.append(obs_dict)
    return my.agent(obs_dict)


def sample_world(obs):
    """自分視点の決定化: 見えていない自分のカードを山札/サイドに配り、相手はミラー仮定。"""
    cur = obs.current
    me = cur.yourIndex
    mine, opp = cur.players[me], cur.players[1 - me]

    # 自分: デッキリストから可視カードを除いた残り = 山札+裏サイドの候補
    pool = list(DECK)
    def remove_seen(card_id):
        if card_id in pool:
            pool.remove(card_id)
    for c in (mine.hand or []):
        remove_seen(c.id)
    for c in mine.discard:
        remove_seen(c.id)
    for p in (mine.active + mine.bench):
        if p:
            remove_seen(p.id)
            for e in p.energyCards:
                remove_seen(e.id)
            for t in p.tools:
                remove_seen(t.id)
            for pe in p.preEvolution:
                remove_seen(pe.id)
    for c in mine.prize:
        if c:
            remove_seen(c.id)
    for c in cur.stadium:
        if c.playerIndex == me:
            remove_seen(c.id)
    random.shuffle(pool)
    n_prize_hidden = sum(1 for c in mine.prize if c is None)
    my_prize = pool[:n_prize_hidden]
    my_deck = pool[n_prize_hidden:]

    # 相手: ミラー仮定(同じデッキリスト)から可視カードを除いて配る
    opool = list(DECK)
    def oremove(card_id):
        if card_id in opool:
            opool.remove(card_id)
    for c in opp.discard:
        oremove(c.id)
    for p in (opp.active + opp.bench):
        if p:
            oremove(p.id)
            for e in p.energyCards:
                oremove(e.id)
            for t in p.tools:
                oremove(t.id)
            for pe in p.preEvolution:
                oremove(pe.id)
    for c in opp.prize:
        if c:
            oremove(c.id)
    for c in cur.stadium:
        if c.playerIndex != me:
            oremove(c.id)
    random.shuffle(opool)
    n = opp.handCount
    opp_hand = opool[:n]
    opp_prize_hidden = sum(1 for c in opp.prize if c is None)
    opp_prize = opool[n:n + opp_prize_hidden]
    opp_deck = opool[n + opp_prize_hidden:]
    opp_active = []
    if len(opp.active) > 0 and opp.active[0] is None:
        basics = [cid for cid in opool if my.CARDS.get(cid) and my.CARDS[cid].basic]
        opp_active = [basics[0] if basics else opool[0]]
    return my_deck, my_prize, opp_deck, opp_prize, opp_hand, opp_active


def rollout(st, max_steps=200):
    """ヒューリスティック方針で両者をプレイして終局までロールアウト。"""
    steps = 0
    while st.observation.current.result < 0 and steps < max_steps:
        obs = st.observation
        sel = obs.select
        # ヒューリスティックの選択関数を使う(dictではなくdataclassベースで直接)
        act = my.agent_on_obs(obs) if hasattr(my, "agent_on_obs") else None
        if act is None:
            n = len(sel.option)
            k = max(sel.minCount, min(sel.maxCount, n))
            act = random.sample(range(n), k)
        st = search_step(st.searchId, act)
        steps += 1
    return st, steps


def main():
    print("=== 中盤obsを捕獲 ===")
    env = make("cabt")
    env.run([capture_agent, "first"])
    print(f"captured: {len(captured)} obs")
    obs_dict = captured[0]
    obs = to_observation_class(obs_dict)
    print(f"turn={obs.current.turn} options={len(obs.select.option)}")

    print("=== search_begin ===")
    t0 = time.time()
    world = sample_world(obs)
    st = search_begin(obs, *world)
    t1 = time.time()
    print(f"begin OK ({(t1 - t0) * 1000:.1f}ms) 仮想obs: turn={st.observation.current.turn} "
          f"yourIndex={st.observation.current.yourIndex} options={len(st.observation.select.option)}")

    print("=== 各合法手を展開 ===")
    root_id = st.searchId
    n_opts = len(st.observation.select.option)
    t0 = time.time()
    children = []
    for a in range(n_opts):
        c = search_step(root_id, [a])
        children.append(c)
    t1 = time.time()
    print(f"{n_opts}手を展開 ({(t1 - t0) / n_opts * 1000:.2f}ms/step)")

    print("=== ロールアウト速度 ===")
    t0 = time.time()
    total_steps = 0
    n_roll = 20
    for i in range(n_roll):
        w = sample_world(obs)
        s = search_begin(obs, *w)
        s, steps = rollout(s)
        total_steps += steps
        r = s.observation.current.result
    t1 = time.time()
    dt = t1 - t0
    print(f"{n_roll}ロールアウト: {dt:.2f}s ({dt / n_roll * 1000:.0f}ms/ロールアウト, "
          f"平均{total_steps / n_roll:.0f}steps, {dt / max(total_steps, 1) * 1000:.2f}ms/step)")
    search_end()


if __name__ == "__main__":
    main()
