"""エージェントのエントリポイント。

意思決定カスケード(agent_config.jsonの"algo"で構成): search → bc → heuristics
構成は ptcg/ パッケージ参照(docs/architecture.md)。

注意:
- Kaggleローダーは exec(code, {}) でロードする(__file__無し)。
  このファイルの最後に定義されるcallableが agent として使われる。
- 設定は同梱の agent_config.json から読む。環境変数は使わない —
  ローカルA/Bで同一プロセスの対戦相手に設定が漏れる事故を防ぐため。
"""

import json
import os
import time

from cg.api import to_observation_class
from ptcg import bc_search
from ptcg import heuristics
from ptcg import policy
from ptcg import search as ptcg_search


def _agent_dir() -> str:
    # cgパッケージの位置からエージェントディレクトリを特定(__file__は使えない)
    import cg

    return os.path.dirname(os.path.dirname(os.path.abspath(cg.__file__)))


def _load_config() -> dict:
    for base in (_agent_dir(), ".", "/kaggle_simulations/agent"):
        p = os.path.join(base, "agent_config.json")
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


CONFIG = _load_config()
# bc(BC方策のみ) / search(探索のみ) / bc_search(探索→BC→ヒューリスティック)
ALGO = str(CONFIG.get("algo", "bc"))
if "bc" in ALGO and not policy.ENABLED:
    # BC入りagentが黙ってheuristicへ化けると、A/Bも提出検証も無意味になる。
    # 実行中の一時的な探索失敗は下段へフォールバックするが、構成不良は起動時に止める。
    raise RuntimeError("BCモデルをロードできない: policy.ENABLED=False")

# ---- 時間管理(探索使用時のみ意味を持つ) ----
TOTAL_OVERAGE_SEC = 600.0
RESERVE_SEC = 60.0
BUDGET_DIVISOR = 50.0
MAX_MOVE_SEC = float(CONFIG.get("max_move_sec", 8.0))
try:
    # ローカルA/B専用: 壁時計ではなく各決定の決定化world数を揃える。
    # 提出版は未指定のままなので、従来どおり時間予算を最大限使う。
    FIXED_SEARCH_WORLDS = int(CONFIG["fixed_search_worlds"])
    if not 2 <= FIXED_SEARCH_WORLDS <= 24:
        FIXED_SEARCH_WORLDS = None
except (KeyError, TypeError, ValueError):
    FIXED_SEARCH_WORLDS = None

_spent = 0.0
AGENT_METRICS = {
    "fixed_search_incomplete": 0,
    "fixed_search_errors": 0,
}


def read_deck_csv() -> list[int]:
    candidates = [
        os.path.join(_agent_dir(), "deck.csv"),
        "deck.csv",
        "/kaggle_simulations/agent/deck.csv",
    ]
    file_path = next((p for p in candidates if os.path.exists(p)), candidates[-1])
    with open(file_path, "r") as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


DECK = read_deck_csv()


def _budget(obs_dict) -> float:
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
        # arena workerは複数試合でcallableを再利用する。Kaggle本番の1 episodeごとの
        # 時間管理と揃えるため、デッキ提出(各試合の先頭)で必ず状態を初期化する。
        _spent = 0.0
        return list(DECK)

    t0 = time.time()
    act = None
    if ALGO == "bcs":
        try:
            # fixed-worldsは比較用の計算量固定モード。remainingOverageTimeや
            # CPU競合で探索回数が変わらないよう、壁時計budget gateを通さない。
            budget = MAX_MOVE_SEC if FIXED_SEARCH_WORLDS is not None else _budget(obs_dict)
            if FIXED_SEARCH_WORLDS is not None or budget > 0.3:
                act = bc_search.decide(
                    obs_dict, obs, DECK, budget,
                    fixed_worlds=FIXED_SEARCH_WORLDS,
                )
        except bc_search.FixedSearchIncomplete:
            AGENT_METRICS["fixed_search_incomplete"] += 1
            act = None
        except Exception:
            if FIXED_SEARCH_WORLDS is not None:
                AGENT_METRICS["fixed_search_errors"] += 1
            act = None
        finally:
            if FIXED_SEARCH_WORLDS is None:
                _spent += time.time() - t0

    if act is None and "search" in ALGO and ALGO != "bcs":
        try:
            budget = _budget(obs_dict)
            if budget > 0:
                act = ptcg_search.decide(obs, DECK, budget)
        except Exception:
            act = None  # 探索の失敗は必ず下段で救済
        finally:
            _spent += time.time() - t0

    if act is None and "bc" in ALGO:
        try:
            act = policy.choose(obs_dict)
        except Exception:
            act = None

    if act is None:
        try:
            act = heuristics.choose(obs)
        except Exception:
            n = len(obs.select.option)
            k = max(obs.select.minCount, min(obs.select.maxCount, n))
            act = list(range(k))
    return act
