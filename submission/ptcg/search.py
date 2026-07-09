"""決定化フラットモンテカルロ探索 (v2.0)。

各候補手について、サンプリングした複数の世界で終局までロールアウトし、
平均勝率が最大の手を選ぶ。世界は候補間で共有する(共通乱数で分散低減)。

世界w: root_w = search_begin(世界w)
        候補a: child = search_step(root_w, a) → ヒューリスティック両者プレイで終局まで
勝敗(勝ち1/分け0.5/負け0)を候補ごとに平均。
"""

import random
import time

from cg.api import search_begin, search_step, search_end

from . import heuristics
from .belief import sample_world

ROLLOUT_MAX_STEPS = 400
MIN_WORLDS = 2
MAX_WORLDS = 24
EST_ROLLOUT_SEC = 0.010  # 実測8ms/ロールアウト + Pythonオーバーヘッド
MAX_CANDIDATES = 16

# 探索対象の選択タイプ: メイン行動 / ワザ選択 / 単数のカード選択
SEARCHABLE_SINGLE = {heuristics.ST_MAIN, heuristics.ST_ATTACK, heuristics.ST_CARD}


def _rollout_value(st, my_real_index: int) -> float:
    """終局までヒューリスティックで両者をプレイし、自分視点の価値を返す。"""
    steps = 0
    while st.observation.current.result < 0 and steps < ROLLOUT_MAX_STEPS:
        obs = st.observation
        try:
            act = heuristics.choose(obs)
        except Exception:
            n = len(obs.select.option)
            k = max(obs.select.minCount, min(obs.select.maxCount, n))
            act = list(range(k))
        st = search_step(st.searchId, act)
        steps += 1
    r = st.observation.current.result
    if r == my_real_index:
        return 1.0
    if r == 1 - my_real_index:
        return 0.0
    if r >= 0:  # 引き分け
        return 0.5
    # 打ち切り: サイド差で概算
    cur = st.observation.current
    diff = len(cur.players[1 - my_real_index].prize) - len(cur.players[my_real_index].prize)
    return max(0.0, min(1.0, 0.5 + diff * 0.08))


def candidates_for(obs) -> list[list[int]] | None:
    """探索する候補手のリスト。探索対象外ならNone。"""
    sel = obs.select
    n = len(sel.option)
    if sel.maxCount != 1 or sel.type not in SEARCHABLE_SINGLE:
        return None
    if n <= 1:
        return None
    idxs = list(range(n))
    if n > MAX_CANDIDATES:
        # ヒューリスティックスコア上位に絞る
        if sel.type == heuristics.ST_MAIN:
            idxs.sort(key=lambda i: heuristics.score_main(obs, sel.option[i]), reverse=True)
        elif sel.type == heuristics.ST_CARD:
            idxs.sort(key=lambda i: heuristics.score_card(obs, sel.option[i], sel.context), reverse=True)
        idxs = idxs[:MAX_CANDIDATES]
    return [[i] for i in idxs]


def decide(obs, my_deck: list[int], budget_sec: float, rng: random.Random | None = None) -> list[int] | None:
    """決定化探索で行動を決める。探索対象外・予算不足ならNone(呼び手がフォールバック)。"""
    cands = candidates_for(obs)
    if cands is None:
        return None

    n_worlds = int(budget_sec / (EST_ROLLOUT_SEC * len(cands)))
    if n_worlds < MIN_WORLDS:
        return None
    n_worlds = min(n_worlds, MAX_WORLDS)

    my_index = obs.current.yourIndex
    totals = [0.0] * len(cands)
    deadline = time.time() + budget_sec * 1.5  # 見積り誤差の保険
    done_worlds = 0
    try:
        for _ in range(n_worlds):
            if time.time() > deadline:
                break
            world = sample_world(obs, my_deck, rng)
            root = search_begin(obs, *world)
            for ci, act in enumerate(cands):
                child = search_step(root.searchId, act)
                totals[ci] += _rollout_value(child, my_index)
            done_worlds += 1
    finally:
        try:
            search_end()
        except Exception:
            pass

    if done_worlds == 0:
        return None
    best = max(range(len(cands)), key=lambda i: totals[i])
    return cands[best]
