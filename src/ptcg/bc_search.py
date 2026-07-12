"""BC×決定化探索 (v4.0, G3路線A)。

BC方策が候補を上位K件に絞り、決定化した世界で「BC同士のプレイ」により
終局までロールアウトして平均勝率最大の手を選ぶ。

v2.x探索(ヒューリスティックロールアウト)との違い:
- ロールアウトの両者がBC(トップ模倣)= 遥かに現実的な未来を見る
- 候補削減もBC = 無駄な枝を読まない
狙い: BC単体の戦術ミス(進化逃し・リーサル見逃し・逃げ判断)を先読みで修正する。
"""

import random
import time

import numpy as np

from cg.api import to_observation_class

from . import heuristics, policy
from .belief import sample_world
from .simx import search_begin_dict, search_step_dict, search_end

SEARCHABLE = {0, 6, 1}   # MAIN / ATTACK / 単数CARD
TOP_K = 5
MIN_WORLDS = 2
MAX_WORLDS = 24
ROLLOUT_MAX = 200


def _policy_act(od: dict) -> list[int]:
    act = policy.choose(od)
    if act is not None:
        return act
    try:
        return heuristics.choose(to_observation_class(od))
    except Exception:
        sel = od.get("select") or {}
        n = len(sel.get("option") or [])
        k = max(sel.get("minCount", 1), min(sel.get("maxCount", 1), n))
        return list(range(k))


def _terminal_value(cur: dict, my_index: int) -> float:
    r = cur.get("result", -1)
    if r == my_index:
        return 1.0
    if r == 1 - my_index:
        return 0.0
    if r >= 0:
        return 0.5
    players = cur["players"]
    diff = len(players[1 - my_index].get("prize") or []) - len(players[my_index].get("prize") or [])
    return max(0.0, min(1.0, 0.5 + diff * 0.08))


def _rollout(state: dict, my_index: int) -> float:
    steps = 0
    while state["observation"]["current"]["result"] < 0 and steps < ROLLOUT_MAX:
        state = search_step_dict(state["searchId"], _policy_act(state["observation"]))
        steps += 1
    return _terminal_value(state["observation"]["current"], my_index)


def decide(obs_dict: dict, obs_dc, my_deck: list[int], budget_sec: float,
           rng: random.Random | None = None) -> list[int] | None:
    """BC×探索。対象外・予算不足・世界不足ならNone(呼び手はBC単体へ)。"""
    sel = obs_dict.get("select") or {}
    opts = sel.get("option") or []
    if sel.get("maxCount") != 1 or sel.get("type") not in SEARCHABLE or len(opts) < 2:
        return None
    scores = policy.scores(obs_dict)
    if scores is None:
        return None
    order = np.argsort(-scores)
    cands = [[int(i)] for i in order[: min(TOP_K, len(opts))]]
    if len(cands) < 2:
        return None

    rng = rng or random
    my_index = obs_dict["current"]["yourIndex"]
    totals = [0.0] * len(cands)
    counts = [0] * len(cands)
    deadline = time.time() + budget_sec
    hard_stop = deadline + budget_sec * 0.5
    worlds = 0
    try:
        while time.time() < deadline and worlds < MAX_WORLDS:
            try:
                world = sample_world(obs_dc, my_deck, rng)
                root = search_begin_dict(obs_dict, *world)
            except Exception:
                break
            for ci, act in enumerate(cands):
                if time.time() > hard_stop:
                    break
                try:
                    child = search_step_dict(root["searchId"], act)
                    totals[ci] += _rollout(child, my_index)
                    counts[ci] += 1
                except Exception:
                    pass
            worlds += 1
    finally:
        try:
            search_end()
        except Exception:
            pass

    if worlds < MIN_WORLDS or not all(counts):
        return None  # 探索不十分: BC単体の判断に任せる
    best = max(range(len(cands)), key=lambda i: totals[i] / counts[i])
    return cands[best]
