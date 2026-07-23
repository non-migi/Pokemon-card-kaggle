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

from . import heuristics, policy, value
from .belief import sample_world
from .simx import search_begin_dict, search_step_dict, search_end

SEARCHABLE = {0, 6, 1}   # MAIN / ATTACK / 単数CARD
TOP_K = 5
RULE_SLOTS = 2
MIN_WORLDS = 2
ROLLOUT_MAX = 200
# 価値網(route B)が有効なら: ロールアウトを短く打ち切り価値網でブートストラップ。
# 1ロールアウトが安くなるので、同じ予算で桁違いに多くの世界を回せる(imperfect info下の律速=世界数)。
VALUE_TRUNC = 20        # 価値網有効時のロールアウト打ち切り手数
MAX_WORLDS = 96 if value.ENABLED else 24


class FixedSearchIncomplete(RuntimeError):
    """固定計算量を完遂できず、比較用測定に採用できない。"""

    def __init__(self, message: str, stage_counts: dict[str, int] | None = None):
        super().__init__(message)
        self.stage_counts = {
            str(stage): int(count)
            for stage, count in (stage_counts or {}).items()
            if int(count) > 0
        }


def _metric_inc(metrics: dict | None, key: str, amount: int = 1) -> None:
    if metrics is not None:
        metrics[key] = int(metrics.get(key, 0)) + amount


def record_fixed_search_incomplete(
    metrics: dict | None, exc: FixedSearchIncomplete, rule_proposals=(),
) -> None:
    """fixed-worlds failureの段階と、その判断で発火中のruleを台帳へ残す。"""
    _metric_inc(metrics, "fixed_search_incomplete")
    for stage, count in sorted(exc.stage_counts.items()):
        _metric_inc(metrics, f"fixed_search_incomplete_stage.{stage}", count)
    rule_ids = sorted({
        str(proposal.rule_id)
        for proposal in rule_proposals
        if getattr(proposal, "rule_id", None)
    })
    if not rule_ids:
        rule_ids = ["none"]
    for rule_id in rule_ids:
        _metric_inc(metrics, f"fixed_search_incomplete_rule_context.{rule_id}")


def _candidate_actions(scores, option_count: int, rule_proposals=(),
                       rule_mode: str = "shadow", metrics: dict | None = None,
                       forbidden_actions=(), injected_actions=None,
                       ) -> list[list[int]]:
    """BC順位と専門家ルールから、計算量を変えず最大TOP_K候補を作る。

    BC top-1は常に保持し、BC top-k外のrule候補を最大RULE_SLOTSだけ入れる。
    shadow/off時は従来のBC top-kと完全に同じ。
    """
    order = [int(i) for i in np.argsort(-np.asarray(scores))]
    order = [i for i in order if 0 <= i < option_count]
    raw_baseline = [[i] for i in order[: min(TOP_K, option_count)]]
    baseline_keys = {tuple(action) for action in raw_baseline}
    forbidden = {tuple(action) for action in forbidden_actions or ()}
    allowed_order = [i for i in order if (i,) not in forbidden]
    baseline = [[i] for i in allowed_order[: min(TOP_K, len(allowed_order))]]

    extras = []
    seen = set()
    for proposal in rule_proposals or ():
        try:
            action = tuple(proposal.action)
            rule_id = str(proposal.rule_id)
        except (AttributeError, TypeError):
            _metric_inc(metrics, "expert_rule_invalid")
            continue
        if (len(action) != 1 or not isinstance(action[0], int)
                or isinstance(action[0], bool) or not 0 <= action[0] < option_count):
            _metric_inc(metrics, "expert_rule_invalid")
            continue
        if action not in baseline_keys:
            _metric_inc(metrics, f"expert_rule_outside_topk.{rule_id}")
        if action not in seen and action not in forbidden and proposal.kind != "forbid":
            extras.append((action, rule_id))
            seen.add(action)

    if rule_mode not in {"candidate", "enforce"} or not baseline:
        return baseline

    result = [baseline[0]]
    result_keys = {tuple(baseline[0])}
    injected = 0
    for action, rule_id in extras:
        if action in baseline_keys or action in result_keys:
            continue
        if injected >= RULE_SLOTS or len(result) >= TOP_K:
            break
        result.append(list(action))
        result_keys.add(action)
        injected += 1
        _metric_inc(metrics, f"expert_rule_injected.{rule_id}")
        if injected_actions is not None:
            injected_actions.setdefault(action, set()).add(rule_id)
    for action in baseline:
        key = tuple(action)
        if key not in result_keys and len(result) < TOP_K:
            result.append(action)
            result_keys.add(key)
    return result


def _record_injected_selection(
    injected_actions, action, metrics: dict | None,
) -> None:
    """候補生成時に実注入したrule actionを探索が選んだ時だけ記録する。"""
    try:
        chosen = tuple(action)
    except TypeError:
        return
    for rule_id in sorted((injected_actions or {}).get(chosen, ())):
        _metric_inc(metrics, f"expert_rule_injected_selected.{rule_id}")


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
    """終局まで(価値網有効時はVALUE_TRUNC手で打ち切り価値網でブートストラップ)。"""
    limit = VALUE_TRUNC if value.ENABLED else ROLLOUT_MAX
    steps = 0
    while state["observation"]["current"]["result"] < 0 and steps < limit:
        state = search_step_dict(state["searchId"], _policy_act(state["observation"]))
        steps += 1
    cur = state["observation"]["current"]
    if cur["result"] >= 0:
        return _terminal_value(cur, my_index)          # 決着したら真の結果
    if value.ENABLED:                                   # 未決着は価値網で評価
        try:
            v = value.win_prob(to_observation_class(state["observation"]).current, my_index)
            if v is not None:
                return v
        except Exception:
            pass
    return _terminal_value(cur, my_index)               # フォールバック(サイド差)


def decide(obs_dict: dict, obs_dc, my_deck: list[int], budget_sec: float,
           rng: random.Random | None = None,
           fixed_worlds: int | None = None,
           rule_proposals=(), rule_mode: str = "shadow",
           metrics: dict | None = None, forbidden_actions=()) -> list[int] | None:
    """BC×探索。対象外・予算不足・世界不足ならNone(呼び手はBC単体へ)。

    fixed_worldsはローカルA/B用。同じworld数を必ず処理してCPU負荷による
    壁時計confoundを避ける。未指定の提出版は従来どおりbudget_secまで探索する。
    """
    sel = obs_dict.get("select") or {}
    opts = sel.get("option") or []
    if sel.get("maxCount") != 1 or sel.get("type") not in SEARCHABLE or len(opts) < 2:
        return None
    scores = policy.scores(obs_dict)
    if scores is None:
        if fixed_worlds is not None:
            raise FixedSearchIncomplete(
                "searchableな選択でBC scoreを取得できない",
                {"bc_scores": 1},
            )
        return None
    injected_actions = {}
    cands = _candidate_actions(
        scores, len(opts), rule_proposals=rule_proposals,
        rule_mode=rule_mode, metrics=metrics,
        forbidden_actions=forbidden_actions,
        injected_actions=injected_actions,
    )
    if len(cands) < 2:
        return None

    rng = rng or random
    my_index = obs_dict["current"]["yourIndex"]
    totals = [0.0] * len(cands)
    counts = [0] * len(cands)
    # fixed評価はMacのsleepを跨いでも期限判定が跳ばない経過時間clockを使う。
    # 提出版のwall-clock挙動はこの測定品質修正では変えない。
    clock = time.monotonic if fixed_worlds is not None else time.time
    start = clock()
    deadline = start + budget_sec
    world_limit = MAX_WORLDS
    if fixed_worlds is not None:
        world_limit = int(fixed_worlds)
        if not MIN_WORLDS <= world_limit <= MAX_WORLDS:
            raise ValueError(f"fixed_worldsは{MIN_WORLDS}..{MAX_WORLDS}: {world_limit}")
        # 固定計算モードでも異常時に試合全体を固めないための安全弁。
        # 通常の数worldなら数百msで終わるため、この上限には到達しない。
        hard_stop = start + max(30.0, budget_sec * 4.0)
    else:
        hard_stop = deadline + budget_sec * 0.5
    worlds = 0
    incomplete_stages: dict[str, int] = {}

    def mark_incomplete(stage: str) -> None:
        incomplete_stages[stage] = incomplete_stages.get(stage, 0) + 1

    try:
        while worlds < world_limit and (
            fixed_worlds is not None or clock() < deadline
        ):
            try:
                world = sample_world(obs_dc, my_deck, rng)
            except Exception:
                mark_incomplete("belief_sample")
                break
            try:
                root = search_begin_dict(obs_dict, *world)
            except Exception:
                mark_incomplete("world_begin")
                break
            for ci, act in enumerate(cands):
                if clock() > hard_stop:
                    mark_incomplete("hard_stop")
                    break
                try:
                    child = search_step_dict(root["searchId"], act)
                except Exception:
                    mark_incomplete("candidate_step")
                    continue
                try:
                    totals[ci] += _rollout(child, my_index)
                    counts[ci] += 1
                except Exception:
                    mark_incomplete("candidate_rollout")
            worlds += 1
    finally:
        try:
            search_end()
        except Exception:
            pass

    if fixed_worlds is not None and (
        worlds != world_limit or not all(c == world_limit for c in counts)
    ):
        raise FixedSearchIncomplete(
            f"固定world未完遂: worlds={worlds}/{world_limit}, counts={counts}",
            incomplete_stages,
        )
    if worlds < MIN_WORLDS or not all(counts):
        return None  # 探索不十分: BC単体の判断に任せる
    best = max(range(len(cands)), key=lambda i: totals[i] / counts[i])
    selected = cands[best]
    _record_injected_selection(
        injected_actions, selected, metrics,
    )
    return selected
