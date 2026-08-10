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
from ptcg import expert_rules
from ptcg import heuristics
from ptcg import ohko_guard
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

# ---- 専門家ルール(デフォルト無効) ----
EXPERT_RULE_PROFILE = CONFIG.get("expert_rules")
if EXPERT_RULE_PROFILE is not None and not isinstance(EXPERT_RULE_PROFILE, str):
    raise RuntimeError("expert_rulesはprofile名の文字列")
EXPERT_RULE_MODE = str(CONFIG.get("expert_rule_mode", "shadow"))
try:
    ENABLED_RULE_IDS = expert_rules.validate_config(
        EXPERT_RULE_PROFILE, EXPERT_RULE_MODE, CONFIG.get("enabled_rule_ids"),
    )
except (TypeError, ValueError) as exc:
    raise RuntimeError(f"expert rules設定不良: {exc}") from exc
CARD_ENERGY_TYPES = {
    int(card_id): int(card.energyType)
    for card_id, card in heuristics.CARDS.items()
}
CARD_TRAITS = expert_rules.build_card_traits(heuristics.CARDS)

# ---- 一撃死コミット回避(デフォルト無効。純BC経路でも効く軽量フック) ----
try:
    OHKO_GUARD = ohko_guard.from_config(CONFIG)
except (TypeError, ValueError) as exc:
    raise RuntimeError(f"ohko_guard設定不良: {exc}") from exc
CARD_INFO = ohko_guard.build_card_info(heuristics.CARDS) if OHKO_GUARD else {}

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

try:
    # 未決着ロールアウトの評価に山札枚数差を入れる。未指定(0)なら従来の評価と完全一致。
    _drw = float(CONFIG.get("deck_race_weight", 0.0))
    bc_search.DECK_RACE_WEIGHT = _drw if 0.0 <= _drw <= 0.05 else 0.0
except (TypeError, ValueError):
    bc_search.DECK_RACE_WEIGHT = 0.0

try:
    # ロールアウト内の行動をsoftmaxでサンプリングする温度。未指定(0)ならargmaxで従来と完全一致。
    # 実際に打つ手には影響しない(_policy_actはロールアウトからしか呼ばれない)。
    _rt = float(CONFIG.get("rollout_temperature", 0.0))
    bc_search.ROLLOUT_TEMPERATURE = (
        _rt if 0.0 <= _rt <= bc_search.ROLLOUT_TEMPERATURE_MAX else 0.0)
except (TypeError, ValueError):
    bc_search.ROLLOUT_TEMPERATURE = 0.0

_spent = 0.0
AGENT_METRICS = {
    "fixed_search_incomplete": 0,
    "fixed_search_errors": 0,
    "expert_rule_errors": 0,
    "expert_rule_invalid": 0,
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


def _metric_inc(key: str, amount: int = 1) -> None:
    AGENT_METRICS[key] = int(AGENT_METRICS.get(key, 0)) + amount


def _rule_proposals(obs_dict: dict):
    if not EXPERT_RULE_PROFILE:
        return []
    try:
        proposals = expert_rules.evaluate(
            obs_dict, DECK, EXPERT_RULE_PROFILE, ENABLED_RULE_IDS,
            card_energy_types=CARD_ENERGY_TYPES,
            card_traits=CARD_TRAITS,
        )
        for proposal in proposals:
            _metric_inc(f"expert_rule_hit.{proposal.rule_id}")
        return proposals
    except Exception:
        # 実行時の未知field/enum/ルール例外は従来BCSへ必ずフォールバックする。
        _metric_inc("expert_rule_errors")
        return []


def _record_rule_choice(proposals, act) -> None:
    if act is None:
        return
    try:
        chosen = tuple(act)
    except TypeError:
        return
    for proposal in proposals:
        if expert_rules.proposal_matches(proposal, chosen):
            label = "violation" if proposal.kind == "forbid" else "selected"
            _metric_inc(f"expert_rule_{label}.{proposal.rule_id}")


def _reject_forbidden(proposals, forbidden, act):
    if act is None or not forbidden:
        return act
    try:
        chosen = tuple(act)
    except TypeError:
        return act
    if chosen not in forbidden:
        return act
    for proposal in proposals:
        if proposal.kind == "forbid" and proposal.action == chosen:
            _metric_inc(f"expert_rule_guard_blocked.{proposal.rule_id}")
    return None


def _guard_forbidden(obs_dict: dict) -> frozenset:
    """一撃死圏へ主力を出す行動の禁止集合。無効時は空(=完全なno-op)。"""
    if OHKO_GUARD is None:
        return frozenset()
    try:
        return ohko_guard.forbidden_actions(
            OHKO_GUARD, obs_dict, CARD_INFO, AGENT_METRICS,
        )
    except Exception:
        # ルール内のいかなる例外でも試合を壊さない。必ずBC選択へ戻す。
        _metric_inc("ohko_guard_errors")
        return frozenset()


def _reject_guard(guard, act):
    if act is None or not guard:
        return act
    try:
        chosen = tuple(act)
    except TypeError:
        return act
    return None if chosen in guard else act


def _guard_redirect(obs_dict: dict, guard, act):
    """BCが禁止手を選んだときだけ、残りの選択肢からBCに選び直させる。"""
    if act is None or not guard:
        return act
    try:
        if tuple(act) not in guard:
            return act
    except TypeError:
        return act
    _metric_inc("ohko_guard_blocked")
    try:
        alt = policy.choose(obs_dict, exclude=guard)
    except Exception:
        return None
    if alt is None or tuple(alt) in guard:
        return None
    _metric_inc("ohko_guard_redirected")
    return alt


def _safe_fallback(obs_dict: dict, forbidden) -> list[int]:
    sel = obs_dict.get("select") or {}
    options = sel.get("option") or []
    try:
        lo = max(0, int(sel.get("minCount", 0)))
        hi = min(len(options), int(sel.get("maxCount", len(options))))
    except (TypeError, ValueError):
        lo = hi = 0
    if lo == hi == 1:
        for i in range(len(options)):
            if (i,) not in forbidden:
                return [i]
    action = list(range(max(lo, hi)))
    return action if tuple(action) not in forbidden else []


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
    proposals = _rule_proposals(obs_dict)
    guard = _guard_forbidden(obs_dict)
    forbidden = (
        expert_rules.forbidden_actions(proposals)
        if EXPERT_RULE_MODE == "enforce" else set()
    )
    if EXPERT_RULE_MODE == "enforce":
        hard_actions = {p.action for p in proposals if p.kind == "hard"}
        if len(hard_actions) > 1:
            _metric_inc("expert_rule_conflicts")
        hard = expert_rules.best_hard(proposals)
        if hard is not None and hard.action not in forbidden:
            act = list(hard.action)
            _metric_inc(f"expert_rule_enforced.{hard.rule_id}")
        elif hard is not None:
            _metric_inc("expert_rule_conflicts")
    if ALGO == "bcs":
        try:
            # fixed-worldsは比較用の計算量固定モード。remainingOverageTimeや
            # CPU競合で探索回数が変わらないよう、壁時計budget gateを通さない。
            budget = MAX_MOVE_SEC if FIXED_SEARCH_WORLDS is not None else _budget(obs_dict)
            if act is None and (FIXED_SEARCH_WORLDS is not None or budget > 0.3):
                act = bc_search.decide(
                    obs_dict, obs, DECK, budget,
                    fixed_worlds=FIXED_SEARCH_WORLDS,
                    rule_proposals=proposals,
                    rule_mode=EXPERT_RULE_MODE,
                    metrics=AGENT_METRICS,
                    forbidden_actions=forbidden,
                )
                act = _reject_forbidden(proposals, forbidden, act)
                act = _reject_guard(guard, act)
        except bc_search.FixedSearchIncomplete as exc:
            bc_search.record_fixed_search_incomplete(
                AGENT_METRICS, exc, proposals,
            )
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
                act = _reject_forbidden(proposals, forbidden, act)
                act = _reject_guard(guard, act)
        except Exception:
            act = None  # 探索の失敗は必ず下段で救済
        finally:
            _spent += time.time() - t0

    if act is None and "bc" in ALGO:
        try:
            act = policy.choose(obs_dict)
            act = _reject_forbidden(proposals, forbidden, act)
            act = _guard_redirect(obs_dict, guard, act)
        except Exception:
            act = None

    if act is None:
        try:
            act = heuristics.choose(obs)
        except Exception:
            act = None
        act = _reject_forbidden(proposals, forbidden, act)
        act = _reject_guard(guard, act)
    if act is None:
        act = _safe_fallback(obs_dict, forbidden | guard)
    _record_rule_choice(proposals, act)
    return act
