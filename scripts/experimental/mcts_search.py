"""決定化MCTS (v2.2)。

各世界(相手の隠れ情報のサンプル)ごとに木を構築し、根の行動価値を世界間で合算する。
- 木が分岐するのは「自分の探索可能な選択」(MAIN / ATTACK / 単数CARD)のみ
- 相手の手番・自分の非探索選択は方針(ヒューリスティック)で自動プレイ
- 子ノードは行動ごとにキャッシュ(チャンスノードは世界ごとに1決定化として折りたたむ)
- 時間管理は締切駆動: 実行環境の速度差(ローカルMac vs Kaggle)を自動吸収する

v2.0のフラットMCとの違い: 有望な手に反復を集中し、自分の連続手番(プレイ→ワザ選択など)を
木として先読みできる。
"""

import math
import random
import time

from cg.api import search_begin, search_step, search_end

from . import heuristics
from .belief import sample_world

ROLLOUT_MAX_STEPS = 400
ADVANCE_MAX_STEPS = 200
MAX_WORLDS = 32
TARGET_WORLDS = 14         # 予算をこの数の世界に均等配分(世界数>深さ: 2026-07-10実験)
MAX_ITERS_PER_WORLD = 120
UCB_C = 1.2
MAX_CANDIDATES = 16
SELECTION_MAX_DEPTH = 40

SEARCHABLE_SINGLE = {heuristics.ST_MAIN, heuristics.ST_ATTACK, heuristics.ST_CARD}


def _policy_act(obs) -> list[int]:
    try:
        return heuristics.choose(obs)
    except Exception:
        n = len(obs.select.option)
        k = max(obs.select.minCount, min(obs.select.maxCount, n))
        return list(range(k))


def _terminal_value(cur, my_index: int) -> float:
    r = cur.result
    if r == my_index:
        return 1.0
    if r == 1 - my_index:
        return 0.0
    if r >= 0:
        return 0.5
    diff = len(cur.players[1 - my_index].prize) - len(cur.players[my_index].prize)
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
        if sel.type == heuristics.ST_MAIN:
            idxs.sort(key=lambda i: heuristics.score_main(obs, sel.option[i]), reverse=True)
        elif sel.type == heuristics.ST_CARD:
            idxs.sort(key=lambda i: heuristics.score_card(obs, sel.option[i], sel.context), reverse=True)
        idxs = idxs[:MAX_CANDIDATES]
    return [[i] for i in idxs]


def _advance(state, action: list[int], my_index: int):
    """actionを適用し、次の「自分の探索可能な選択」まで方針で進める。

    Returns:
        (state, None)  次の分岐点に到達
        (None, value)  終局または打ち切り
    """
    st = search_step(state.searchId, action)
    for _ in range(ADVANCE_MAX_STEPS):
        obs = st.observation
        cur = obs.current
        if cur.result >= 0:
            return None, _terminal_value(cur, my_index)
        if cur.yourIndex == my_index and candidates_for(obs) is not None:
            return st, None
        st = search_step(st.searchId, _policy_act(obs))
    return None, _terminal_value(st.observation.current, my_index)


def _rollout(st, my_index: int) -> float:
    steps = 0
    while st.observation.current.result < 0 and steps < ROLLOUT_MAX_STEPS:
        st = search_step(st.searchId, _policy_act(st.observation))
        steps += 1
    return _terminal_value(st.observation.current, my_index)


class _Node:
    __slots__ = ("state", "cands", "children", "n", "w", "untried", "terminal_value")

    def __init__(self, state, my_index: int, terminal_value: float | None = None):
        self.state = state
        self.terminal_value = terminal_value
        self.children: dict[int, _Node] = {}
        self.n = 0
        self.w = 0.0
        if terminal_value is None:
            self.cands = candidates_for(state.observation)
            self.untried = list(range(len(self.cands)))
        else:
            self.cands = None
            self.untried = []


def _iterate(root: _Node, my_index: int, rng: random.Random) -> None:
    """MCTSの1反復: 選択→展開→ロールアウト→逆伝播。"""
    path = [root]
    node = root

    # 選択
    depth = 0
    while node.terminal_value is None and not node.untried and node.children and depth < SELECTION_MAX_DEPTH:
        log_n = math.log(max(node.n, 1))
        node = max(
            node.children.values(),
            key=lambda c: (c.w / c.n if c.n else 0.5) + UCB_C * math.sqrt(log_n / (c.n + 1e-9)) if c.n else float("inf"),
        )
        path.append(node)
        depth += 1

    # 展開 + 評価
    if node.terminal_value is not None:
        value = node.terminal_value
    elif node.untried:
        ci = node.untried.pop(rng.randrange(len(node.untried)))
        st, tv = _advance(node.state, node.cands[ci], my_index)
        child = _Node(st, my_index, terminal_value=tv)
        node.children[ci] = child
        path.append(child)
        value = tv if tv is not None else _rollout(child.state, my_index)
    else:
        value = _rollout(node.state, my_index) if node.state else 0.5

    # 逆伝播
    for nd in path:
        nd.n += 1
        nd.w += value


def decide(obs, my_deck: list[int], budget_sec: float, rng: random.Random | None = None) -> list[int] | None:
    """決定化MCTSで行動を決める。探索対象外・予算不足ならNone(呼び手がフォールバック)。"""
    cands = candidates_for(obs)
    if cands is None:
        return None
    rng = rng or random
    my_index = obs.current.yourIndex

    t0 = time.time()
    deadline = t0 + budget_sec
    totals_n = [0] * len(cands)
    totals_w = [0.0] * len(cands)
    worlds = 0
    try:
        while worlds < MAX_WORLDS:
            now = time.time()
            if now >= deadline:
                break
            # 残り予算を残り世界数で均等配分(最低でも数反復は回す)
            remain_worlds = max(1, TARGET_WORLDS - worlds)
            world_deadline = min(deadline, now + (deadline - now) / remain_worlds)
            try:
                world = sample_world(obs, my_deck, rng)
                root_state = search_begin(obs, *world)
            except Exception:
                break
            root = _Node(root_state, my_index)
            iters = 0
            while time.time() < world_deadline and iters < MAX_ITERS_PER_WORLD:
                _iterate(root, my_index, rng)
                iters += 1
            for ci, child in root.children.items():
                totals_n[ci] += child.n
                totals_w[ci] += child.w
            worlds += 1
    finally:
        try:
            search_end()
        except Exception:
            pass

    if worlds == 0 or sum(totals_n) == 0:
        return None
    # 世界間合算の平均価値が最大の手(未訪問は除外)
    best = max(
        (i for i in range(len(cands)) if totals_n[i] > 0),
        key=lambda i: totals_w[i] / totals_n[i],
    )
    return cands[best]
