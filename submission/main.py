"""エージェント v2.0: 決定化フラットモンテカルロ探索 + ヒューリスティックフォールバック。

構成は ptcg/ パッケージ参照(docs/architecture.md)。
注意: Kaggleローダーは exec(code, {}) でロードする(__file__無し)。
      このファイルの最後に定義されるcallableが agent として使われる。
"""

import os
import time

from cg.api import to_observation_class
from ptcg import heuristics
from ptcg import search as ptcg_search

# ---- 時間管理 ----
# エピソード実測(2026-07-10)で1試合10〜75秒しか使っていなかったため大幅増強。
# 残り時間を線形に配分: budget = usable/50(上限8秒)。usableが減るほど自然に絞られる
TOTAL_OVERAGE_SEC = 600.0
RESERVE_SEC = 60.0            # 終盤・非常用に残す
BUDGET_DIVISOR = 50.0
MAX_MOVE_SEC = float(os.environ.get("PTCG_MAX_MOVE_SEC", "8.0"))

_spent = 0.0


def read_deck_csv() -> list[int]:
    # cgパッケージの位置から提出ディレクトリを特定(__file__は使えない)
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


DECK = read_deck_csv()


def _budget(obs_dict) -> float:
    """この1手に使う探索予算(秒)。"""
    reported = obs_dict.get("remainingOverageTime", TOTAL_OVERAGE_SEC)
    remaining = min(float(reported), TOTAL_OVERAGE_SEC - _spent)
    usable = remaining - RESERVE_SEC
    if usable <= 0:
        return 0.0
    return max(0.0, min(MAX_MOVE_SEC, usable / BUDGET_DIVISOR))


def agent(obs_dict: dict) -> list[int]:
    global _spent
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return list(DECK)

    t0 = time.time()
    act = None
    try:
        budget = _budget(obs_dict)
        if budget > 0:
            act = ptcg_search.decide(obs, DECK, budget)
    except Exception:
        act = None  # 探索の失敗は必ずヒューリスティックで救済
    finally:
        _spent += time.time() - t0

    if act is None:
        try:
            act = heuristics.choose(obs)
        except Exception:
            n = len(obs.select.option)
            k = max(obs.select.minCount, min(obs.select.maxCount, n))
            act = list(range(k))
    return act
