"""凍結した専門家rule注入局面を、提出方策を変えずに再評価する。

このCLIは提出コードから独立したローカル診断専用である。

1. auditに保存したrow SHAをpairsと公式episodeの双方で照合する。
2. 現行と同じ5候補を、row SHA由来の2決定化worldで先に評価・選択する。
3. 選択確定後、元BC top-5 + rule手の6候補を同じ決定化worldで影評価する。
4. raw observation・非公開札・episode IDを一切出力せず、事前登録gateを判定する。

native engine内の乱数状態は公式episodeに保存されない。このため結果は歴史的な
bit-exact replayではなく、現在のengine/buildによるcounterfactual screenである。
各判断はfresh processへ隔離し、影評価が実選択へ逆流しないようにする。
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# モデル同梱buildのptcgを、repo側のptcglab等より必ず先にimportする。
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument("--policy-build")
_known, _ = _bootstrap.parse_known_args()
MODULE_ROOT = os.path.abspath(
    os.path.join(ROOT, _known.policy_build) if _known.policy_build
    else os.path.join(ROOT, "src")
)
sys.path.insert(0, MODULE_ROOT)
sys.path.insert(1, ROOT)

from cg.api import to_observation_class  # noqa: E402
from ptcg import bc_search, expert_rules, heuristics, policy  # noqa: E402
from ptcglab.arena import agent_fingerprint  # noqa: E402


DEFAULT_RULE_ID = "AZ003_HAMMER_BLOCKER_PLAY"
TRACE_SCHEMA = 1
FROZEN_EVENT_COUNT = 10
Q_EPSILON = 1e-12

CARD_ENERGY_TYPES = {
    int(card_id): int(card.energyType)
    for card_id, card in heuristics.CARDS.items()
}
CARD_TRAITS = expert_rules.build_card_traits(heuristics.CARDS)

REPORT_KEYS = frozenset({
    "schema", "generated_at_jst", "experiment", "rule_id", "policy_build",
    "policy_build_sha256", "audit_sha256", "world_count",
    "event_isolation", "historical_replay", "native_rng_controlled",
    "hidden_world_pairing", "events", "summary", "gate", "limitations",
})
EVENT_KEYS = frozenset({
    "row_number", "row_sha256", "status", "reason_codes", "rule_id",
    "rule_action", "legal_injection", "audit_match", "original_bc_top5",
    "policy_candidates", "dropped_bc_action", "policy_q",
    "policy_selected_action", "policy_selected_rule",
    "counterfactual_candidates", "counterfactual_q",
    "counterfactual_rule_q", "counterfactual_original_max_q",
    "counterfactual_q_delta", "counterfactual_rule_not_dominated",
    "counterfactual_rule_strictly_better", "policy_rule_q",
    "policy_retained_original_max_q", "gate_dropped_original_q",
    "gate_original_max_q", "gate_q_delta",
    "gate_rule_not_dominated", "gate_rule_strictly_better",
    "world_count",
})
ERROR_EVENT_KEYS = frozenset({
    "row_number", "row_sha256", "status", "reason_codes",
})
BC_ROW_KEYS = frozenset({"rank", "action", "score"})
Q_ROW_KEYS = frozenset({"action", "total", "count", "q"})
SUMMARY_KEYS = frozenset({
    "expected_events", "completed_events", "legal_injections",
    "audit_matches", "technical_errors", "policy_selected_rule_rows",
    "selected_rule_not_dominated_rows", "selected_rule_strict_rows",
    "selected_rule_dominated_rows",
})
GATE_KEYS = frozenset({"outcome", "reason_codes", "criteria"})
CRITERIA_KEYS = frozenset({
    "required_events", "required_selected_rule_rows",
    "required_selected_rule_strict_rows", "q_epsilon",
})
DENIED_KEYS = frozenset({
    "observation", "current", "players", "hand", "deck", "logs",
    "search_begin_input", "team", "teacher_team", "episode", "source", "path",
    "option", "options", "world", "worlds",
})
ERROR_REASON_CODES = frozenset({
    "POLICY_DISABLED",
    "WORLD_COUNT_INVALID",
    "RULE_PROPOSAL_MISSING",
    "RULE_KIND_UNEXPECTED",
    "HARD_RULE_BYPASSES_SEARCH",
    "RULE_ACTION_ILLEGAL",
    "AUDIT_RULE_ACTION_MISMATCH",
    "BC_SCORES_MISSING",
    "BC_RANKING_INCOMPLETE",
    "RULE_ACTION_NOT_RANKED",
    "AUDIT_BC_RANK_MISMATCH",
    "RULE_NOT_INJECTED",
    "POLICY_CANDIDATE_COUNT_MISMATCH",
    "DROPPED_BC_CANDIDATE_MISMATCH",
    "COUNTERFACTUAL_CANDIDATE_COUNT_MISMATCH",
    "OBSERVATION_CONVERSION_FAILED",
    "BELIEF_SAMPLE_FAILED",
    "POLICY_WORLD_BEGIN_FAILED",
    "POLICY_CANDIDATE_STEP_FAILED",
    "POLICY_ROLLOUT_FAILED",
    "POLICY_SEARCH_END_FAILED",
    "POLICY_INCOMPLETE",
    "COUNTERFACTUAL_WORLD_BEGIN_FAILED",
    "COUNTERFACTUAL_CANDIDATE_STEP_FAILED",
    "COUNTERFACTUAL_ROLLOUT_FAILED",
    "COUNTERFACTUAL_SEARCH_END_FAILED",
    "COUNTERFACTUAL_INCOMPLETE",
    "POLICY_Q_EMPTY",
    "COUNTERFACTUAL_Q_LAYOUT_MISMATCH",
    "POLICY_Q_LAYOUT_MISMATCH",
    "GATE_Q_LAYOUT_MISMATCH",
    "PRIVACY_EVENT_SCHEMA_VIOLATION",
    "PRIVACY_BC_SCHEMA_VIOLATION",
    "PRIVACY_Q_SCHEMA_VIOLATION",
    "PRIVACY_DENIED_KEY",
    "WORKER_TIMEOUT",
    "WORKER_START_FAILED",
    "WORKER_PROCESS_FAILED",
    "WORKER_OUTPUT_INVALID",
    "WORKER_PRIVACY_INVALID",
    "WORKER_TARGET_MISMATCH",
    "UNEXPECTED_WORKER_ERROR",
})


class TraceFailure(RuntimeError):
    """raw dataや例外文を外へ出さない、安定した診断code。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = str(code)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pair_sha256(row: dict) -> str:
    raw = json.dumps(row, separators=(",", ":")) + "\n"
    return hashlib.sha256(raw.encode()).hexdigest()


def _display_build(path: str) -> str:
    absolute = os.path.abspath(path)
    try:
        common = os.path.commonpath((ROOT, absolute))
    except ValueError as exc:
        raise TraceFailure("POLICY_BUILD_OUTSIDE_REPO") from exc
    if common != ROOT:
        raise TraceFailure("POLICY_BUILD_OUTSIDE_REPO")
    relative = os.path.relpath(absolute, ROOT)
    if relative.startswith("..") or os.path.isabs(relative):
        raise TraceFailure("POLICY_BUILD_OUTSIDE_REPO")
    return relative


def load_audit_targets(path: str, rule_id: str) -> tuple[dict, list[dict]]:
    try:
        with open(path) as f:
            audit = json.load(f)
    except (OSError, ValueError) as exc:
        raise TraceFailure("AUDIT_READ_FAILED") from exc

    rule = (audit.get("rules") or {}).get(rule_id) or {}
    examples = audit.get("candidate_injected_examples")
    if not isinstance(examples, list) or not examples:
        raise TraceFailure("AUDIT_TARGETS_MISSING")
    expected = rule.get("candidate_injected")
    if (
        not isinstance(expected, int)
        or expected != FROZEN_EVENT_COUNT
        or expected != len(examples)
    ):
        raise TraceFailure("AUDIT_TARGET_COUNT_MISMATCH")

    targets = []
    seen_rows: set[int] = set()
    seen_hashes: set[str] = set()
    for example in examples:
        try:
            row_number = int(example["row_number"])
            row_sha256 = str(example["row_sha256"])
            rule_action = [int(x) for x in example["rule_action"]]
            bc_rank = int(example["bc_rank"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TraceFailure("AUDIT_TARGET_SCHEMA_INVALID") from exc
        if (
            row_number <= 0
            or len(row_sha256) != 64
            or any(c not in "0123456789abcdef" for c in row_sha256)
            or len(rule_action) != 1
            or bc_rank <= bc_search.TOP_K
            or not bool(example.get("teacher_match"))
            or row_number in seen_rows
            or row_sha256 in seen_hashes
        ):
            raise TraceFailure("AUDIT_TARGET_SCHEMA_INVALID")
        seen_rows.add(row_number)
        seen_hashes.add(row_sha256)
        targets.append({
            "row_number": row_number,
            "row_sha256": row_sha256,
            "rule_action": rule_action,
            "bc_rank": bc_rank,
        })
    targets.sort(key=lambda item: item["row_number"])
    return audit, targets


def load_frozen_pair_rows(path: str, targets: list[dict]) -> dict[str, dict]:
    by_number = {target["row_number"]: target for target in targets}
    found: dict[str, dict] = {}
    try:
        with gzip.open(path, "rt") as f:
            for row_number, line in enumerate(f, start=1):
                target = by_number.get(row_number)
                if target is None:
                    continue
                digest = hashlib.sha256(line.encode()).hexdigest()
                if digest != target["row_sha256"]:
                    raise TraceFailure("PAIR_ROW_SHA_MISMATCH")
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise TraceFailure("PAIR_ROW_JSON_INVALID") from exc
                if list(row.get("act") or []) != target["rule_action"]:
                    raise TraceFailure("PAIR_TEACHER_ACTION_MISMATCH")
                found[digest] = row
                if len(found) == len(targets):
                    break
    except OSError as exc:
        raise TraceFailure("PAIRS_READ_FAILED") from exc
    if len(found) != len(targets):
        raise TraceFailure("PAIR_ROW_MISSING")
    return found


def iter_full_winner_rows(path: str):
    """bc_extractと同じrowを、対応する完全observationと共にmemory内だけで返す。"""
    try:
        with open(path) as f:
            episode = json.load(f)
    except (OSError, ValueError):
        return
    rewards = episode.get("rewards") or [None, None]
    if 1 not in rewards:
        return
    winner = rewards.index(1)
    names = episode.get("info", {}).get("TeamNames", ["?", "?"])
    steps = episode.get("steps") or []
    if len(steps) < 3:
        return
    try:
        deck = steps[1][winner].get("action")
    except (IndexError, AttributeError, TypeError):
        return
    if not isinstance(deck, list) or len(deck) != 60:
        return
    for turn_index in range(1, len(steps) - 1):
        try:
            state = steps[turn_index][winner]
            following = steps[turn_index + 1][winner]
        except (IndexError, TypeError):
            continue
        if state.get("status") != "ACTIVE":
            continue
        observation = state.get("observation") or {}
        select = observation.get("select")
        current = observation.get("current")
        action = following.get("action")
        if select is None or current is None or not isinstance(action, list):
            continue
        row = {
            "sel": select,
            "cur": current,
            "act": action,
            "team": names[winner],
            "deck": deck,
        }
        yield row, observation


def find_full_observations(
    episodes_dir: str, pair_rows: dict[str, dict],
) -> dict[str, dict]:
    wanted = set(pair_rows)
    found: dict[str, dict] = {}
    paths = sorted(glob.glob(os.path.join(episodes_dir, "*.json")))
    if not paths:
        raise TraceFailure("EPISODE_FILES_MISSING")
    for path in paths:
        for row, observation in iter_full_winner_rows(path) or ():
            digest = _pair_sha256(row)
            if digest not in wanted:
                continue
            if row != pair_rows[digest]:
                raise TraceFailure("EPISODE_PAIR_CONTENT_MISMATCH")
            if digest in found:
                raise TraceFailure("FULL_OBSERVATION_DUPLICATE")
            if (
                not observation.get("search_begin_input")
                or "remainingOverageTime" not in observation
            ):
                raise TraceFailure("FULL_OBSERVATION_INCOMPLETE")
            found[digest] = {
                "observation": observation,
                "deck": list(row["deck"]),
            }
    if len(found) != len(wanted):
        raise TraceFailure("FULL_OBSERVATION_MISSING")
    return found


def candidate_layout(
    observation: dict,
    deck: list[int],
    target: dict,
    profile: str,
    enabled_rule_ids: tuple[str, ...],
    rule_mode: str,
    rule_id: str,
) -> dict:
    proposals = expert_rules.evaluate(
        observation,
        deck,
        profile,
        enabled_rule_ids,
        card_energy_types=CARD_ENERGY_TYPES,
        card_traits=CARD_TRAITS,
    )
    rule_proposals = [
        proposal for proposal in proposals if proposal.rule_id == rule_id
    ]
    if len(rule_proposals) != 1:
        raise TraceFailure("RULE_PROPOSAL_MISSING")
    proposal = rule_proposals[0]
    if proposal.kind == "hard":
        raise TraceFailure("RULE_KIND_UNEXPECTED")
    if expert_rules.best_hard(proposals) is not None:
        raise TraceFailure("HARD_RULE_BYPASSES_SEARCH")
    if not expert_rules.legal_action(observation, proposal.action):
        raise TraceFailure("RULE_ACTION_ILLEGAL")
    if list(proposal.action) != target["rule_action"]:
        raise TraceFailure("AUDIT_RULE_ACTION_MISMATCH")

    scores = policy.scores(observation)
    if scores is None:
        raise TraceFailure("BC_SCORES_MISSING")
    values = np.asarray(scores)
    option_count = len((observation.get("select") or {}).get("option") or [])
    order = [
        int(index) for index in np.argsort(-values)
        if 0 <= int(index) < option_count
    ]
    if len(order) < min(option_count, bc_search.TOP_K):
        raise TraceFailure("BC_RANKING_INCOMPLETE")
    try:
        observed_rank = order.index(int(proposal.action[0])) + 1
    except ValueError as exc:
        raise TraceFailure("RULE_ACTION_NOT_RANKED") from exc
    if observed_rank != target["bc_rank"]:
        raise TraceFailure("AUDIT_BC_RANK_MISMATCH")

    original = [[index] for index in order[:bc_search.TOP_K]]
    forbidden = expert_rules.forbidden_actions(proposals)
    metrics: dict[str, int] = {}
    injected_actions: dict[tuple[int, ...], set[str]] = {}
    policy_candidates = bc_search._candidate_actions(
        scores,
        option_count,
        proposals,
        rule_mode,
        metrics,
        forbidden_actions=forbidden,
        injected_actions=injected_actions,
    )
    rule_action = tuple(proposal.action)
    if rule_id not in injected_actions.get(rule_action, set()):
        raise TraceFailure("RULE_NOT_INJECTED")
    if len(policy_candidates) != bc_search.TOP_K:
        raise TraceFailure("POLICY_CANDIDATE_COUNT_MISMATCH")

    policy_keys = {tuple(action) for action in policy_candidates}
    dropped = [action for action in original if tuple(action) not in policy_keys]
    if len(dropped) != 1:
        raise TraceFailure("DROPPED_BC_CANDIDATE_MISMATCH")
    counterfactual = list(original)
    if rule_action not in {tuple(action) for action in counterfactual}:
        counterfactual.append(list(rule_action))
    if len(counterfactual) != bc_search.TOP_K + 1:
        raise TraceFailure("COUNTERFACTUAL_CANDIDATE_COUNT_MISMATCH")

    bc_rows = [
        {
            "rank": rank,
            "action": [action[0]],
            "score": round(float(values[action[0]]), 8),
        }
        for rank, action in enumerate(original, start=1)
    ]
    return {
        "proposal": proposal,
        "original_bc_top5": bc_rows,
        "original_actions": original,
        "policy_candidates": policy_candidates,
        "dropped_bc_action": dropped[0],
        "counterfactual_candidates": counterfactual,
    }


def sample_frozen_worlds(
    observation: dict, deck: list[int], row_sha256: str, world_count: int,
) -> list[tuple]:
    seed = int(row_sha256[:16], 16)
    rng = random.Random(seed)
    try:
        obs_dc = to_observation_class(observation)
    except Exception as exc:
        raise TraceFailure("OBSERVATION_CONVERSION_FAILED") from exc
    worlds = []
    for _ in range(world_count):
        try:
            worlds.append(bc_search.sample_world(obs_dc, deck, rng))
        except Exception as exc:
            raise TraceFailure("BELIEF_SAMPLE_FAILED") from exc
    return worlds


def evaluate_candidate_pool(
    observation: dict,
    candidates: list[list[int]],
    worlds: list[tuple],
    label: str,
) -> list[dict]:
    """現行decideと同じworld→candidate順でQを測る。"""
    totals = [0.0] * len(candidates)
    counts = [0] * len(candidates)
    my_index = int(observation["current"]["yourIndex"])
    pending: TraceFailure | None = None
    try:
        for world in worlds:
            try:
                root = bc_search.search_begin_dict(observation, *world)
            except Exception as exc:
                raise TraceFailure(f"{label}_WORLD_BEGIN_FAILED") from exc
            for candidate_index, action in enumerate(candidates):
                try:
                    child = bc_search.search_step_dict(
                        root["searchId"], action,
                    )
                except Exception as exc:
                    raise TraceFailure(f"{label}_CANDIDATE_STEP_FAILED") from exc
                try:
                    score = bc_search._rollout(child, my_index)
                except Exception as exc:
                    raise TraceFailure(f"{label}_ROLLOUT_FAILED") from exc
                totals[candidate_index] += float(score)
                counts[candidate_index] += 1
    except TraceFailure as exc:
        pending = exc
    finally:
        try:
            bc_search.search_end()
        except Exception as exc:
            if pending is None:
                pending = TraceFailure(f"{label}_SEARCH_END_FAILED")
                pending.__cause__ = exc
    if pending is not None:
        raise pending
    if any(count != len(worlds) for count in counts):
        raise TraceFailure(f"{label}_INCOMPLETE")
    return [
        {
            "action": list(action),
            "total": float(totals[index]),
            "count": int(counts[index]),
            "q": float(totals[index] / counts[index]),
        }
        for index, action in enumerate(candidates)
    ]


def _selected_row(rows: list[dict]) -> dict:
    if not rows:
        raise TraceFailure("POLICY_Q_EMPTY")
    # maxは同率時に先頭を返す。現行bc_search.decideと同じtie-break。
    index = max(range(len(rows)), key=lambda i: rows[i]["q"])
    return rows[index]


def run_trace_event(
    payload: dict,
    profile: str,
    enabled_rule_ids: tuple[str, ...],
    rule_mode: str,
    rule_id: str,
    world_count: int,
) -> dict:
    target = payload["target"]
    observation = payload["observation"]
    deck = payload["deck"]
    if not policy.ENABLED:
        raise TraceFailure("POLICY_DISABLED")
    if world_count < bc_search.MIN_WORLDS or world_count > bc_search.MAX_WORLDS:
        raise TraceFailure("WORLD_COUNT_INVALID")

    enabled = expert_rules.validate_config(
        profile, rule_mode, enabled_rule_ids,
    )
    layout = candidate_layout(
        observation, deck, target, profile, enabled, rule_mode, rule_id,
    )
    worlds = sample_frozen_worlds(
        observation, deck, target["row_sha256"], world_count,
    )

    # 必ず現行5候補を先に評価・選択し、その後だけ6候補の影評価を行う。
    policy_q = evaluate_candidate_pool(
        observation, layout["policy_candidates"], worlds, "POLICY",
    )
    selected = _selected_row(policy_q)
    counterfactual_q = evaluate_candidate_pool(
        observation,
        layout["counterfactual_candidates"],
        worlds,
        "COUNTERFACTUAL",
    )

    rule_action = list(layout["proposal"].action)
    rule_key = tuple(rule_action)
    original_keys = {
        tuple(action) for action in layout["original_actions"]
    }
    rule_rows = [
        row for row in counterfactual_q
        if tuple(row["action"]) == rule_key
    ]
    original_rows = [
        row for row in counterfactual_q
        if tuple(row["action"]) in original_keys
    ]
    if len(rule_rows) != 1 or len(original_rows) != bc_search.TOP_K:
        raise TraceFailure("COUNTERFACTUAL_Q_LAYOUT_MISMATCH")
    rule_q = float(rule_rows[0]["q"])
    original_max_q = max(float(row["q"]) for row in original_rows)
    delta = rule_q - original_max_q
    selected_rule = tuple(selected["action"]) == rule_key

    # gateは実際に選択へ使った5候補passのQを優先する。そこで評価されない
    # dropped BC #5だけを後段shadow passから補い、元候補側に有利なmaxを取る。
    policy_rule_rows = [
        row for row in policy_q if tuple(row["action"]) == rule_key
    ]
    policy_retained_original_rows = [
        row for row in policy_q if tuple(row["action"]) in original_keys
    ]
    dropped_key = tuple(layout["dropped_bc_action"])
    dropped_shadow_rows = [
        row for row in counterfactual_q
        if tuple(row["action"]) == dropped_key
    ]
    if (
        len(policy_rule_rows) != 1
        or len(policy_retained_original_rows) != bc_search.TOP_K - 1
    ):
        raise TraceFailure("POLICY_Q_LAYOUT_MISMATCH")
    if len(dropped_shadow_rows) != 1:
        raise TraceFailure("GATE_Q_LAYOUT_MISMATCH")
    policy_rule_q = float(policy_rule_rows[0]["q"])
    retained_original_max_q = max(
        float(row["q"]) for row in policy_retained_original_rows
    )
    dropped_original_q = float(dropped_shadow_rows[0]["q"])
    gate_original_max_q = max(
        retained_original_max_q,
        dropped_original_q,
    )
    gate_delta = policy_rule_q - gate_original_max_q

    event = {
        "row_number": int(target["row_number"]),
        "row_sha256": str(target["row_sha256"]),
        "status": "complete",
        "reason_codes": [],
        "rule_id": rule_id,
        "rule_action": rule_action,
        "legal_injection": True,
        "audit_match": True,
        "original_bc_top5": layout["original_bc_top5"],
        "policy_candidates": [
            list(action) for action in layout["policy_candidates"]
        ],
        "dropped_bc_action": list(layout["dropped_bc_action"]),
        "policy_q": policy_q,
        "policy_selected_action": list(selected["action"]),
        "policy_selected_rule": selected_rule,
        "counterfactual_candidates": [
            list(action) for action in layout["counterfactual_candidates"]
        ],
        "counterfactual_q": counterfactual_q,
        "counterfactual_rule_q": rule_q,
        "counterfactual_original_max_q": original_max_q,
        "counterfactual_q_delta": delta,
        "counterfactual_rule_not_dominated": delta >= -Q_EPSILON,
        "counterfactual_rule_strictly_better": delta > Q_EPSILON,
        "policy_rule_q": policy_rule_q,
        "policy_retained_original_max_q": retained_original_max_q,
        "gate_dropped_original_q": dropped_original_q,
        "gate_original_max_q": gate_original_max_q,
        "gate_q_delta": gate_delta,
        "gate_rule_not_dominated": gate_delta >= -Q_EPSILON,
        "gate_rule_strictly_better": gate_delta > Q_EPSILON,
        "world_count": int(world_count),
    }
    validate_event_privacy(event)
    return event


def error_event(target: dict, code: str) -> dict:
    return {
        "row_number": int(target.get("row_number", 0)),
        "row_sha256": str(target.get("row_sha256", "")),
        "status": "error",
        "reason_codes": [str(code)],
    }


def classify_gate(events: list[dict], expected_events: int) -> tuple[dict, dict]:
    complete = [event for event in events if event.get("status") == "complete"]
    selected = [
        event for event in complete if event.get("policy_selected_rule")
    ]
    selected_not_dominated = [
        event for event in selected
        if event.get("gate_rule_not_dominated")
    ]
    selected_strict = [
        event for event in selected
        if event.get("gate_rule_strictly_better")
    ]
    selected_dominated = [
        event for event in selected
        if not event.get("gate_rule_not_dominated")
    ]
    summary = {
        "expected_events": FROZEN_EVENT_COUNT,
        "completed_events": len(complete),
        "legal_injections": sum(
            bool(event.get("legal_injection")) for event in complete
        ),
        "audit_matches": sum(
            bool(event.get("audit_match")) for event in complete
        ),
        "technical_errors": len(events) - len(complete),
        "policy_selected_rule_rows": len(selected),
        "selected_rule_not_dominated_rows": len(selected_not_dominated),
        "selected_rule_strict_rows": len(selected_strict),
        "selected_rule_dominated_rows": len(selected_dominated),
    }
    reasons: list[str] = []
    if expected_events != FROZEN_EVENT_COUNT:
        outcome = "INVALID_RUN"
        reasons.append("AUDIT_TARGET_COUNT_MISMATCH")
    elif (
        len(events) != FROZEN_EVENT_COUNT
        or len(complete) != FROZEN_EVENT_COUNT
    ):
        outcome = "INVALID_RUN"
        reasons.append("TECHNICAL_OR_COUNT_ERROR")
    elif (
        summary["legal_injections"] != FROZEN_EVENT_COUNT
        or summary["audit_matches"] != FROZEN_EVENT_COUNT
    ):
        outcome = "TRACE_REJECT"
        reasons.append("ILLEGAL_OR_AUDIT_MISMATCH")
    elif selected_dominated:
        outcome = "TRACE_REJECT"
        reasons.append("SELECTED_RULE_Q_DOMINATED")
    elif len(selected) >= 3 and len(selected_strict) >= 2:
        outcome = "TRACE_SAFE"
        reasons.append("PREDECLARED_SAFE_CRITERIA_MET")
    else:
        outcome = "TRACE_HOLD"
        if len(selected) < 3:
            reasons.append("INSUFFICIENT_SELECTED_RULE_ROWS")
        if len(selected_strict) < 2:
            reasons.append("INSUFFICIENT_STRICT_ADVANTAGE_ROWS")
    gate = {
        "outcome": outcome,
        "reason_codes": reasons,
        "criteria": {
            "required_events": FROZEN_EVENT_COUNT,
            "required_selected_rule_rows": 3,
            "required_selected_rule_strict_rows": 2,
            "q_epsilon": Q_EPSILON,
        },
    }
    return summary, gate


def _check_keys(value: dict, allowed: frozenset[str], code: str) -> None:
    if not isinstance(value, dict) or not set(value).issubset(allowed):
        raise TraceFailure(code)


def _check_exact_keys(value: dict, expected: frozenset[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise TraceFailure(code)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_action(value, code: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not _is_int(value[0])
        or value[0] < 0
    ):
        raise TraceFailure(code)


def _validate_provenance(event: dict) -> None:
    row_number = event.get("row_number")
    digest = event.get("row_sha256")
    if not _is_int(row_number) or row_number <= 0:
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")


def validate_event_privacy(event: dict) -> None:
    _check_keys(event, EVENT_KEYS, "PRIVACY_EVENT_SCHEMA_VIOLATION")
    for key in event:
        if key in DENIED_KEYS:
            raise TraceFailure("PRIVACY_DENIED_KEY")
    _validate_provenance(event)

    status = event.get("status")
    reasons = event.get("reason_codes")
    if status == "error":
        _check_exact_keys(
            event,
            ERROR_EVENT_KEYS,
            "PRIVACY_EVENT_SCHEMA_VIOLATION",
        )
        if (
            not isinstance(reasons, list)
            or len(reasons) != 1
            or reasons[0] not in ERROR_REASON_CODES
        ):
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
        return
    if status != "complete":
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    _check_exact_keys(
        event,
        EVENT_KEYS,
        "PRIVACY_EVENT_SCHEMA_VIOLATION",
    )
    if reasons != []:
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    rule_id = event.get("rule_id")
    if (
        not isinstance(rule_id, str)
        or re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", rule_id) is None
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    for key in (
        "rule_action",
        "dropped_bc_action",
        "policy_selected_action",
    ):
        _validate_action(event.get(key), "PRIVACY_EVENT_SCHEMA_VIOLATION")
    for key in ("legal_injection", "audit_match", "policy_selected_rule"):
        if not isinstance(event.get(key), bool):
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    world_count = event.get("world_count")
    if (
        not _is_int(world_count)
        or world_count < bc_search.MIN_WORLDS
        or world_count > bc_search.MAX_WORLDS
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    original = event.get("original_bc_top5")
    if not isinstance(original, list) or len(original) != bc_search.TOP_K:
        raise TraceFailure("PRIVACY_BC_SCHEMA_VIOLATION")
    for expected_rank, row in enumerate(original, start=1):
        _check_exact_keys(row, BC_ROW_KEYS, "PRIVACY_BC_SCHEMA_VIOLATION")
        if row.get("rank") != expected_rank or not _is_finite_number(
            row.get("score"),
        ):
            raise TraceFailure("PRIVACY_BC_SCHEMA_VIOLATION")
        _validate_action(row.get("action"), "PRIVACY_BC_SCHEMA_VIOLATION")

    candidate_specs = (
        ("policy_candidates", bc_search.TOP_K),
        ("counterfactual_candidates", bc_search.TOP_K + 1),
    )
    for collection, size in candidate_specs:
        candidates = event.get(collection)
        if not isinstance(candidates, list) or len(candidates) != size:
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
        for action in candidates:
            _validate_action(action, "PRIVACY_EVENT_SCHEMA_VIOLATION")
        if len({tuple(action) for action in candidates}) != size:
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    q_specs = (
        ("policy_q", "policy_candidates", bc_search.TOP_K),
        (
            "counterfactual_q",
            "counterfactual_candidates",
            bc_search.TOP_K + 1,
        ),
    )
    for collection, candidates_key, size in q_specs:
        rows = event.get(collection)
        if not isinstance(rows, list) or len(rows) != size:
            raise TraceFailure("PRIVACY_Q_SCHEMA_VIOLATION")
        if [row.get("action") for row in rows] != event[candidates_key]:
            raise TraceFailure("PRIVACY_Q_SCHEMA_VIOLATION")
        for row in rows:
            _check_exact_keys(row, Q_ROW_KEYS, "PRIVACY_Q_SCHEMA_VIOLATION")
            _validate_action(row.get("action"), "PRIVACY_Q_SCHEMA_VIOLATION")
            if (
                not _is_finite_number(row.get("total"))
                or not _is_finite_number(row.get("q"))
                or row.get("count") != world_count
                or not math.isclose(
                    float(row["total"]) / row["count"],
                    float(row["q"]),
                    rel_tol=0.0,
                    abs_tol=Q_EPSILON,
                )
            ):
                raise TraceFailure("PRIVACY_Q_SCHEMA_VIOLATION")

    for key in (
        "counterfactual_rule_q",
        "counterfactual_original_max_q",
        "counterfactual_q_delta",
        "policy_rule_q",
        "policy_retained_original_max_q",
        "gate_dropped_original_q",
        "gate_original_max_q",
        "gate_q_delta",
    ):
        if not _is_finite_number(event.get(key)):
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    for key in (
        "counterfactual_rule_not_dominated",
        "counterfactual_rule_strictly_better",
        "gate_rule_not_dominated",
        "gate_rule_strictly_better",
    ):
        if not isinstance(event.get(key), bool):
            raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    rule_action = event["rule_action"]
    if (
        rule_action not in event["policy_candidates"]
        or rule_action not in event["counterfactual_candidates"]
        or event["policy_selected_action"] not in event["policy_candidates"]
        or event["policy_selected_rule"]
        != (event["policy_selected_action"] == rule_action)
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    original_actions = [row["action"] for row in original]
    original_keys = {tuple(action) for action in original_actions}
    rule_key = tuple(rule_action)
    dropped_key = tuple(event["dropped_bc_action"])
    policy_keys = {tuple(action) for action in event["policy_candidates"]}
    counterfactual_keys = {
        tuple(action) for action in event["counterfactual_candidates"]
    }
    if (
        len(original_keys) != bc_search.TOP_K
        or dropped_key not in original_keys
        or rule_key in original_keys
        or policy_keys != (original_keys - {dropped_key}) | {rule_key}
        or counterfactual_keys != original_keys | {rule_key}
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")

    policy_q_by_action = {
        tuple(row["action"]): float(row["q"]) for row in event["policy_q"]
    }
    counterfactual_q_by_action = {
        tuple(row["action"]): float(row["q"])
        for row in event["counterfactual_q"]
    }
    expected_counterfactual_rule_q = counterfactual_q_by_action[rule_key]
    expected_counterfactual_original_max_q = max(
        counterfactual_q_by_action[key] for key in original_keys
    )
    expected_counterfactual_delta = (
        expected_counterfactual_rule_q
        - expected_counterfactual_original_max_q
    )
    expected_policy_rule_q = policy_q_by_action[rule_key]
    expected_retained_original_max_q = max(
        policy_q_by_action[key]
        for key in original_keys - {dropped_key}
    )
    expected_dropped_original_q = counterfactual_q_by_action[dropped_key]
    expected_gate_original_max_q = max(
        expected_retained_original_max_q,
        expected_dropped_original_q,
    )
    expected_gate_delta = (
        expected_policy_rule_q - expected_gate_original_max_q
    )
    numeric_expectations = {
        "counterfactual_rule_q": expected_counterfactual_rule_q,
        "counterfactual_original_max_q":
            expected_counterfactual_original_max_q,
        "counterfactual_q_delta": expected_counterfactual_delta,
        "policy_rule_q": expected_policy_rule_q,
        "policy_retained_original_max_q":
            expected_retained_original_max_q,
        "gate_dropped_original_q": expected_dropped_original_q,
        "gate_original_max_q": expected_gate_original_max_q,
        "gate_q_delta": expected_gate_delta,
    }
    if any(
        not math.isclose(
            float(event[key]),
            expected,
            rel_tol=0.0,
            abs_tol=Q_EPSILON,
        )
        for key, expected in numeric_expectations.items()
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")
    boolean_expectations = {
        "counterfactual_rule_not_dominated":
            expected_counterfactual_delta >= -Q_EPSILON,
        "counterfactual_rule_strictly_better":
            expected_counterfactual_delta > Q_EPSILON,
        "gate_rule_not_dominated": expected_gate_delta >= -Q_EPSILON,
        "gate_rule_strictly_better": expected_gate_delta > Q_EPSILON,
    }
    if any(
        event[key] is not expected
        for key, expected in boolean_expectations.items()
    ):
        raise TraceFailure("PRIVACY_EVENT_SCHEMA_VIOLATION")


def validate_report_privacy(report: dict) -> None:
    _check_exact_keys(
        report,
        REPORT_KEYS,
        "PRIVACY_REPORT_SCHEMA_VIOLATION",
    )

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in DENIED_KEYS:
                    raise TraceFailure("PRIVACY_DENIED_KEY")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(report)
    for event in report.get("events") or []:
        validate_event_privacy(event)
    _check_exact_keys(
        report.get("summary") or {},
        SUMMARY_KEYS,
        "PRIVACY_SUMMARY_SCHEMA_VIOLATION",
    )
    gate = report.get("gate") or {}
    _check_exact_keys(gate, GATE_KEYS, "PRIVACY_GATE_SCHEMA_VIOLATION")
    _check_exact_keys(
        gate.get("criteria") or {},
        CRITERIA_KEYS,
        "PRIVACY_CRITERIA_SCHEMA_VIOLATION",
    )
    build = str(report.get("policy_build") or "")
    if os.path.isabs(build) or build.startswith(".."):
        raise TraceFailure("PRIVACY_ABSOLUTE_PATH")


def _worker_command(args, audit: dict) -> list[str]:
    command = [
        sys.executable,
        os.path.abspath(__file__),
        "--worker",
        "--policy-build",
        os.path.abspath(args.policy_build),
        "--profile",
        str(audit["profile"]),
        "--rule-mode",
        str(audit["rule_mode"]),
        "--rule-id",
        args.rule_id,
        "--worlds",
        str(args.worlds),
    ]
    for rule_id in audit["enabled_rule_ids"]:
        command.extend(("--enabled-rule", str(rule_id)))
    return command


def run_isolated_worker(payload: dict, args, audit: dict) -> dict:
    try:
        completed = subprocess.run(
            _worker_command(args, audit),
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            capture_output=True,
            timeout=float(args.worker_timeout),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return error_event(payload["target"], "WORKER_TIMEOUT")
    except OSError:
        return error_event(payload["target"], "WORKER_START_FAILED")
    if completed.returncode != 0:
        return error_event(payload["target"], "WORKER_PROCESS_FAILED")
    try:
        event = json.loads(completed.stdout)
    except ValueError:
        return error_event(payload["target"], "WORKER_OUTPUT_INVALID")
    try:
        validate_event_privacy(event)
    except TraceFailure:
        return error_event(payload["target"], "WORKER_PRIVACY_INVALID")
    if (
        event.get("row_number") != payload["target"]["row_number"]
        or event.get("row_sha256") != payload["target"]["row_sha256"]
    ):
        return error_event(payload["target"], "WORKER_TARGET_MISMATCH")
    return event


def build_report(args) -> dict:
    audit, targets = load_audit_targets(args.audit, args.rule_id)
    if (
        audit.get("profile") is None
        or audit.get("rule_mode") not in {"candidate", "enforce"}
        or args.rule_id not in (audit.get("enabled_rule_ids") or [])
    ):
        raise TraceFailure("AUDIT_CONFIG_INVALID")

    display_build = _display_build(args.policy_build)
    fingerprint = agent_fingerprint(args.policy_build)
    if fingerprint["sha256"] != audit.get("policy_build_sha256"):
        raise TraceFailure("POLICY_BUILD_FINGERPRINT_MISMATCH")
    config = fingerprint.get("config") or {}
    if (
        config.get("expert_rules") != audit.get("profile")
        or config.get("expert_rule_mode") != audit.get("rule_mode")
        or list(config.get("enabled_rule_ids") or [])
        != list(audit.get("enabled_rule_ids") or [])
        or int(config.get("fixed_search_worlds", -1)) != int(args.worlds)
    ):
        raise TraceFailure("POLICY_BUILD_CONFIG_MISMATCH")

    pair_rows = load_frozen_pair_rows(args.pairs, targets)
    full = find_full_observations(args.episodes_dir, pair_rows)
    events = []
    for target in targets:
        item = full[target["row_sha256"]]
        payload = {
            "target": target,
            "observation": item["observation"],
            "deck": item["deck"],
        }
        events.append(run_isolated_worker(payload, args, audit))

    summary, gate = classify_gate(events, FROZEN_EVENT_COUNT)
    report = {
        "schema": TRACE_SCHEMA,
        "generated_at_jst": datetime.now(
            ZoneInfo("Asia/Tokyo"),
        ).isoformat(timespec="seconds"),
        "experiment": "frozen_expert_rule_intervention_trace",
        "rule_id": args.rule_id,
        "policy_build": display_build,
        "policy_build_sha256": fingerprint["sha256"],
        "audit_sha256": _sha256_file(args.audit),
        "world_count": int(args.worlds),
        "event_isolation": "fresh_process_per_row",
        "historical_replay": False,
        "native_rng_controlled": False,
        "hidden_world_pairing": (
            "same row-sha-seeded determinizations; policy pass precedes shadow pass"
        ),
        "events": events,
        "summary": summary,
        "gate": gate,
        "limitations": [
            (
                "official episodes do not preserve native branch RNG; this is a "
                "current counterfactual screen, not a bit-exact historical replay"
            ),
            (
                "the two passes reuse hidden-world contents, but native chance "
                "streams are neither seeded nor paired across passes"
            ),
        ],
    }
    validate_report_privacy(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit")
    parser.add_argument("--pairs")
    parser.add_argument("--episodes-dir")
    parser.add_argument("--policy-build", required=True)
    parser.add_argument("--rule-id", default=DEFAULT_RULE_ID)
    parser.add_argument("--worlds", type=int, default=2)
    parser.add_argument("--worker-timeout", type=float, default=300.0)
    parser.add_argument("--output", help="sanitized trace JSONの保存先")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", help=argparse.SUPPRESS)
    parser.add_argument("--enabled-rule", action="append", default=[],
                        help=argparse.SUPPRESS)
    parser.add_argument("--rule-mode", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.worker:
        try:
            payload = json.load(sys.stdin)
            event = run_trace_event(
                payload,
                args.profile,
                tuple(args.enabled_rule),
                args.rule_mode,
                args.rule_id,
                args.worlds,
            )
        except TraceFailure as exc:
            target = (
                payload.get("target", {})
                if isinstance(locals().get("payload"), dict) else {}
            )
            event = error_event(target, exc.code)
        except Exception:
            target = (
                payload.get("target", {})
                if isinstance(locals().get("payload"), dict) else {}
            )
            event = error_event(target, "UNEXPECTED_WORKER_ERROR")
        print(json.dumps(event, separators=(",", ":"), sort_keys=True))
        return

    if not args.audit or not args.pairs or not args.episodes_dir:
        raise SystemExit("--audit, --pairs, --episodes-dir は必須")
    try:
        report = build_report(args)
    except TraceFailure as exc:
        report = {
            "schema": TRACE_SCHEMA,
            "experiment": "frozen_expert_rule_intervention_trace",
            "gate": {
                "outcome": "INVALID_RUN",
                "reason_codes": [exc.code],
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(2)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w") as f:
            f.write(rendered)
        print(json.dumps({
            "gate": report["gate"]["outcome"],
            "summary": report["summary"],
        }, sort_keys=True))
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
