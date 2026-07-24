"""AZ003 Exact-safe guardを独立Daily Top episodeで一度だけ監査する。

flat BC pairsでは失われるepisode/turn順序を保持しつつ、成果物には集計値と
集合fingerprintだけを残す。個別team・episode・row・観測・actionは出力しない。
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# BC入りbuildのptcgをrepo srcより先にimportする。
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument("--policy-build")
_known, _ = _bootstrap.parse_known_args()
MODULE_ROOT = os.path.abspath(
    os.path.join(ROOT, _known.policy_build)
    if _known.policy_build
    else os.path.join(ROOT, "src")
)
sys.path.insert(0, MODULE_ROOT)
sys.path.insert(1, ROOT)

from ptcg import bc_search, expert_rules, heuristics, policy  # noqa: E402
from ptcglab.arena import agent_fingerprint  # noqa: E402


ANALYSIS_VERSION = 2
PROFILE = "alakazam_v1"
RULE_ID = "AZ003_HAMMER_BLOCKER_PLAY"
RECOVERY_BASELINE = "results/az003_guard_holdout_20260722.json"
RECOVERY_BASELINE_SHA256 = (
    "ded767a1dcc59006569eb26c56c1d56a03d3e2c1c18c7d41727d6d5f960984fc"
)
EXPECTED_OUTPUT = "results/az003_guard_holdout_20260722_r2.json"
EXPECTED_DATASET_LABEL = "daily-top-20260722"
EXPECTED_EPISODE_FILES = 4639
EXPECTED_UNIQUE_RAW_EPISODES = 4639
EXPECTED_DATASET_FINGERPRINT = (
    "9ff468f2ce5600da44d82468dd36807f0e4a603654b2b7d9fbc83e020200a0ed"
)
EXPECTED_EXCLUDE_DECISIONS = 366457
EXPECTED_EXCLUDE_FINGERPRINT = (
    "66b15e69eedddd602ae746095197f89f870ea5de8bc317c20086cd0bb3fa6f03"
)
EXPECTED_POLICY_BUILD = "build/v4.5a-r34-guard-audit"
EXPECTED_POLICY_BUILD_SHA256 = (
    "0ca440e31908463009f2c4eab490a80c75a33f8ec4b878d71254630f6e00ef1c"
)
EXPECTED_POLICY_MODEL_SHA256 = (
    "be8146d75f0cfe813a8728084614a3e168fc821fd2f7dece717feb0c2b8c70da"
)
HEX64 = re.compile(r"[0-9a-f]{64}")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")

CARD_ENERGY_TYPES = {
    int(card_id): int(card.energyType)
    for card_id, card in heuristics.CARDS.items()
}
CARD_TRAITS = expert_rules.build_card_traits(heuristics.CARDS)

TECHNICAL_KEYS = {
    "json_parse_errors",
    "episode_schema_errors",
    "rule_evaluation_errors",
    "policy_score_errors",
    "policy_score_missing",
    "policy_score_nonfinite",
    "hammer_rank_errors",
}
SCAN_KEYS = {
    "episode_files_seen",
    "unique_raw_episodes",
    "duplicate_raw_episodes",
    "valid_winner_episodes",
    "non_alakazam_winner_episodes",
    "no_unique_winner_episodes",
    "alakazam_winner_episodes",
    "alakazam_winner_decisions",
}
AZ003_KEYS = {
    "broad_hits_raw",
    "overlap_excluded",
    "broad_hits_audited",
    "broad_teacher_matches",
    "broad_teacher_rate",
    "multiple_hammer_hits",
    "semantic_top5_present",
    "semantic_outside_top5",
    "semantic_teacher_matches",
    "semantic_teacher_rate",
}
COHORT_KEYS = {
    "events",
    "teacher_hammer_matches",
    "teacher_hammer_rate",
    "unique_episodes",
    "unique_winner_teams",
}
TRANSITION_KEYS = {
    "semantic_outside_events",
    "broad_to_later_exact_turns",
    "broad_teacher_hammer_to_later_exact_turns",
    "episodes_with_broad_to_later_exact",
}
REPORT_KEYS = {
    "analysis",
    "analysis_version",
    "aggregate_only",
    "dataset_label",
    "dataset_fingerprint_sha256",
    "exclude_decision_count",
    "exclude_decision_set_sha256",
    "policy_build",
    "policy_build_sha256",
    "policy_model_sha256",
    "recovery_baseline_sha256",
    "policy_enabled",
    "profile",
    "rule_id",
    "scan",
    "technical",
    "az003",
    "cohorts",
    "same_turn_diagnostic",
    "gate",
}
GATE_KEYS = {"decision", "criteria"}
CRITERIA_KEYS = {
    "technical_error_count",
    "min_events_each",
    "min_unique_episodes_each",
    "min_exact_safe_unique_winner_teams",
    "support_exact_safe_teacher_rate_min",
    "support_rate_advantage_min",
    "reject_exact_safe_teacher_rate_below",
    "observed_exact_safe_teacher_rate",
    "observed_broad_only_teacher_rate",
    "observed_rate_advantage",
}
DENIED_KEYS = {
    "action",
    "actions",
    "card_id",
    "card_ids",
    "deck",
    "episode_id",
    "episodes",
    "file",
    "filename",
    "observation",
    "observations",
    "path",
    "row",
    "row_sha256",
    "source",
    "team",
    "team_name",
    "teams",
}


class ScoreMissing(ValueError):
    pass


class NoUniqueWinnerEpisode(ValueError):
    pass


class ScoreNonFinite(ValueError):
    pass


class HammerRankError(ValueError):
    pass


@dataclass
class Cohort:
    events: int = 0
    teacher_hammer_matches: int = 0
    episode_tokens: set[str] = field(default_factory=set)
    team_tokens: set[str] = field(default_factory=set)

    def add(self, episode_token: str, team_token: str, teacher_match: bool) -> None:
        self.events += 1
        self.teacher_hammer_matches += int(teacher_match)
        self.episode_tokens.add(episode_token)
        self.team_tokens.add(team_token)

    def report(self) -> dict:
        return {
            "events": self.events,
            "teacher_hammer_matches": self.teacher_hammer_matches,
            "teacher_hammer_rate": _rate(
                self.teacher_hammer_matches, self.events,
            ),
            "unique_episodes": len(self.episode_tokens),
            "unique_winner_teams": len(self.team_tokens),
        }


@dataclass
class ScanState:
    scan: Counter = field(default_factory=Counter)
    technical: Counter = field(default_factory=Counter)
    az003: Counter = field(default_factory=Counter)
    broad: Cohort = field(default_factory=Cohort)
    exact_safe: Cohort = field(default_factory=Cohort)
    broad_only: Cohort = field(default_factory=Cohort)
    transition_events: list[dict] = field(default_factory=list)
    raw_episode_digests: list[str] = field(default_factory=list)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _fingerprint(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def decision_digest(sel: dict, cur: dict, act: list, deck: list) -> str:
    """team名に依存しない、同一decision除外用の正規化SHA。"""
    payload = {"sel": sel, "cur": cur, "act": act, "deck": deck}
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_excluded_decisions(paths: Iterable[str]) -> tuple[set[str], str]:
    decisions: set[str] = set()
    for path in paths:
        with gzip.open(path, "rt") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    row = json.loads(line)
                    decisions.add(decision_digest(
                        row["sel"], row["cur"], row["act"], row["deck"],
                    ))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"exclude pairs schema error at line {line_number}",
                    ) from exc
    return decisions, _fingerprint(decisions)


def fingerprint_episode_corpus(
    episode_dir: str,
) -> tuple[int, int, str]:
    """局面をparseせず、固定holdoutのraw集合だけを先に照合する。"""
    paths = sorted(glob.glob(os.path.join(episode_dir, "*.json")))
    raw_digests = set()
    for path in paths:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        raw_digests.add(digest.hexdigest())
    return len(paths), len(raw_digests), _fingerprint(raw_digests)


def validate_frozen_inputs(
    dataset_label: str,
    policy_build_label: str,
    policy_fingerprint: dict,
    exclude_count: int,
    exclude_fingerprint: str,
    episode_file_count: int,
    unique_episode_count: int,
    dataset_fingerprint: str,
) -> None:
    """結果を見る前に固定した入力・方策・top-k契約をfail-closed照合する。"""
    observed = {
        "dataset_label": dataset_label,
        "policy_build": policy_build_label,
        "policy_build_sha256": policy_fingerprint.get("sha256"),
        "policy_model_sha256": policy_fingerprint.get("model_sha256"),
        "exclude_count": exclude_count,
        "exclude_fingerprint": exclude_fingerprint,
        "episode_file_count": episode_file_count,
        "unique_episode_count": unique_episode_count,
        "dataset_fingerprint": dataset_fingerprint,
        "top_k": bc_search.TOP_K,
        "policy_enabled": bool(policy.ENABLED),
        "hammer_action_helper": hasattr(
            expert_rules, "enhanced_hammer_play_actions",
        ),
        "exact_safe_helper": hasattr(
            expert_rules, "is_hammer_safe_conversion",
        ),
    }
    expected = {
        "dataset_label": EXPECTED_DATASET_LABEL,
        "policy_build": EXPECTED_POLICY_BUILD,
        "policy_build_sha256": EXPECTED_POLICY_BUILD_SHA256,
        "policy_model_sha256": EXPECTED_POLICY_MODEL_SHA256,
        "exclude_count": EXPECTED_EXCLUDE_DECISIONS,
        "exclude_fingerprint": EXPECTED_EXCLUDE_FINGERPRINT,
        "episode_file_count": EXPECTED_EPISODE_FILES,
        "unique_episode_count": EXPECTED_UNIQUE_RAW_EPISODES,
        "dataset_fingerprint": EXPECTED_DATASET_FINGERPRINT,
        "top_k": 5,
        "policy_enabled": True,
        "hammer_action_helper": True,
        "exact_safe_helper": True,
    }
    mismatches = [
        key for key in expected if observed.get(key) != expected[key]
    ]
    if mismatches:
        raise ValueError(
            "frozen input mismatch: " + ",".join(sorted(mismatches)),
        )


def semantic_hammer_rank(
    scores, hammer_actions: tuple[tuple[int, ...], ...], option_count: int,
) -> int:
    if scores is None:
        raise ScoreMissing("policy.scores returned None")
    try:
        values = np.asarray(scores, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise HammerRankError("scores are not numeric") from exc
    if len(values) < option_count:
        raise ScoreMissing("scores shorter than option count")
    relevant = values[:option_count]
    if not np.isfinite(relevant).all():
        raise ScoreNonFinite("non-finite policy score")
    order = [
        int(i) for i in np.argsort(-relevant)
        if 0 <= int(i) < option_count
    ]
    ranks = {option_index: rank for rank, option_index in enumerate(order, 1)}
    try:
        action_indices = [
            int(action[0])
            for action in hammer_actions
            if len(action) == 1
        ]
    except (TypeError, ValueError, IndexError) as exc:
        raise HammerRankError("malformed Hammer action") from exc
    if (
        len(action_indices) != len(hammer_actions)
        or not action_indices
        or len(set(action_indices)) != len(action_indices)
        or any(i not in ranks for i in action_indices)
    ):
        raise HammerRankError("Hammer option missing from policy rank")
    return min(ranks[i] for i in action_indices)


def summarize_same_turn(events: list[dict]) -> dict:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for event in events:
        grouped[(event["episode_token"], event["turn"])].append(event)
    transitions = 0
    teacher_transitions = 0
    transition_episodes = set()
    for (episode_token, _turn), rows in grouped.items():
        ordered = sorted(rows, key=lambda row: row["step_index"])
        found = False
        teacher_found = False
        for index, row in enumerate(ordered):
            if not row["exact_safe"]:
                continue
            earlier = [
                previous for previous in ordered[:index]
                if not previous["exact_safe"]
            ]
            if earlier:
                found = True
            if any(previous["teacher_match"] for previous in earlier):
                teacher_found = True
        transitions += int(found)
        teacher_transitions += int(teacher_found)
        if found:
            transition_episodes.add(episode_token)
    return {
        "semantic_outside_events": len(events),
        "broad_to_later_exact_turns": transitions,
        "broad_teacher_hammer_to_later_exact_turns": teacher_transitions,
        "episodes_with_broad_to_later_exact": len(transition_episodes),
    }


def _episode_header(data: dict) -> tuple[int, list, str, list]:
    rewards = data.get("rewards")
    steps = data.get("steps")
    names = (data.get("info") or {}).get("TeamNames")
    if (
        not isinstance(rewards, list)
        or len(rewards) != 2
        or any(value not in (-1, 0, 1, None) for value in rewards)
    ):
        raise ValueError("rewards schema")
    if not isinstance(steps, list) or len(steps) < 3:
        raise ValueError("steps schema")
    winner_count = rewards.count(1)
    if winner_count == 0:
        if any(
            not isinstance(step, list) or len(step) < 2
            for step in steps
        ):
            raise ValueError("draw steps schema")
        raise NoUniqueWinnerEpisode("no unique winner")
    if winner_count != 1:
        raise ValueError("winner/steps schema")
    winner = rewards.index(1)
    if (
        winner not in (0, 1)
        or not isinstance(steps[1], list)
        or len(steps[1]) <= winner
        or not isinstance(steps[1][winner], dict)
    ):
        raise ValueError("winner step schema")
    deck = steps[1][winner].get("action")
    if not isinstance(deck, list) or len(deck) != 60:
        raise ValueError("winner deck schema")
    if (
        not isinstance(names, list)
        or len(names) <= winner
        or not isinstance(names[winner], str)
        or not names[winner]
    ):
        raise ValueError("winner team schema")
    team_token = hashlib.sha256(
        ("winner-team:" + names[winner]).encode(),
    ).hexdigest()
    return winner, deck, team_token, steps


def scan_episode_dir(
    episode_dir: str,
    excluded_decisions: set[str],
    score_fn: Callable[[dict], object] | None = None,
) -> ScanState:
    state = ScanState()
    score_fn = score_fn or policy.scores
    paths = sorted(glob.glob(os.path.join(episode_dir, "*.json")))
    state.scan["episode_files_seen"] = len(paths)
    if not paths:
        state.technical["episode_schema_errors"] += 1
        return state

    seen_raw: set[str] = set()
    for path in paths:
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            state.technical["json_parse_errors"] += 1
            continue
        episode_token = hashlib.sha256(raw).hexdigest()
        if episode_token in seen_raw:
            state.scan["duplicate_raw_episodes"] += 1
            continue
        seen_raw.add(episode_token)
        state.raw_episode_digests.append(episode_token)
        state.scan["unique_raw_episodes"] += 1
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            state.technical["json_parse_errors"] += 1
            continue
        try:
            winner, deck, team_token, steps = _episode_header(data)
        except NoUniqueWinnerEpisode:
            state.scan["no_unique_winner_episodes"] += 1
            continue
        except (AttributeError, TypeError, ValueError):
            state.technical["episode_schema_errors"] += 1
            continue
        state.scan["valid_winner_episodes"] += 1
        if not expert_rules._is_alakazam_deck(deck):
            state.scan["non_alakazam_winner_episodes"] += 1
            continue
        state.scan["alakazam_winner_episodes"] += 1

        for step_index in range(1, len(steps) - 1):
            try:
                current_step = steps[step_index][winner]
                next_step = steps[step_index + 1][winner]
            except (IndexError, TypeError):
                state.technical["episode_schema_errors"] += 1
                break
            if (
                not isinstance(current_step, dict)
                or not isinstance(next_step, dict)
                or current_step.get("status") != "ACTIVE"
            ):
                continue
            observation = current_step.get("observation") or {}
            sel = observation.get("select")
            cur = observation.get("current")
            action = next_step.get("action")
            if (
                not isinstance(sel, dict)
                or not isinstance(cur, dict)
                or not isinstance(action, list)
            ):
                continue
            state.scan["alakazam_winner_decisions"] += 1
            obs = {"select": sel, "current": cur}
            try:
                proposals = expert_rules.evaluate(
                    obs, deck, PROFILE, [RULE_ID],
                    card_energy_types=CARD_ENERGY_TYPES,
                    card_traits=CARD_TRAITS,
                )
            except Exception:
                state.technical["rule_evaluation_errors"] += 1
                continue
            if not proposals:
                continue
            proposal = proposals[0]
            state.az003["broad_hits_raw"] += 1
            row_digest = decision_digest(sel, cur, action, deck)
            if row_digest in excluded_decisions:
                state.az003["overlap_excluded"] += 1
                continue

            hammer_actions = expert_rules.enhanced_hammer_play_actions(obs)
            if not hammer_actions:
                state.technical["rule_evaluation_errors"] += 1
                continue
            teacher_match = tuple(action) in hammer_actions
            exact_safe = expert_rules.is_hammer_safe_conversion(
                obs, CARD_ENERGY_TYPES, CARD_TRAITS,
            )

            try:
                scores = score_fn(obs)
                rank = semantic_hammer_rank(
                    scores, hammer_actions, len(sel.get("option") or []),
                )
            except ScoreMissing:
                state.technical["policy_score_missing"] += 1
                continue
            except ScoreNonFinite:
                state.technical["policy_score_nonfinite"] += 1
                continue
            except HammerRankError:
                state.technical["hammer_rank_errors"] += 1
                continue
            except Exception:
                state.technical["policy_score_errors"] += 1
                continue

            state.az003["broad_hits_audited"] += 1
            state.az003["broad_teacher_matches"] += int(teacher_match)
            state.az003["multiple_hammer_hits"] += int(len(hammer_actions) > 1)
            state.broad.add(episode_token, team_token, teacher_match)
            if rank <= bc_search.TOP_K:
                state.az003["semantic_top5_present"] += 1
                continue
            state.az003["semantic_outside_top5"] += 1
            state.az003["semantic_teacher_matches"] += int(teacher_match)
            cohort = state.exact_safe if exact_safe else state.broad_only
            cohort.add(episode_token, team_token, teacher_match)
            turn = cur.get("turn")
            if not isinstance(turn, int) or isinstance(turn, bool):
                state.technical["episode_schema_errors"] += 1
                continue
            state.transition_events.append({
                "episode_token": episode_token,
                "turn": turn,
                "step_index": step_index,
                "exact_safe": exact_safe,
                "teacher_match": teacher_match,
            })
    return state


def classify_gate(
    exact_safe: Cohort,
    broad_only: Cohort,
    technical_error_count: int,
) -> tuple[str, dict]:
    exact_rate = _rate(
        exact_safe.teacher_hammer_matches, exact_safe.events,
    )
    broad_rate = _rate(
        broad_only.teacher_hammer_matches, broad_only.events,
    )
    advantage = (
        round(exact_rate - broad_rate, 6)
        if exact_rate is not None and broad_rate is not None else None
    )
    criteria = {
        "technical_error_count": technical_error_count,
        "min_events_each": 5,
        "min_unique_episodes_each": 4,
        "min_exact_safe_unique_winner_teams": 2,
        "support_exact_safe_teacher_rate_min": 0.8,
        "support_rate_advantage_min": 0.2,
        "reject_exact_safe_teacher_rate_below": 0.6,
        "observed_exact_safe_teacher_rate": exact_rate,
        "observed_broad_only_teacher_rate": broad_rate,
        "observed_rate_advantage": advantage,
    }
    if technical_error_count:
        return "INVALID_RUN", criteria
    reject_ready = (
        exact_safe.events >= 5
        and len(exact_safe.episode_tokens) >= 4
    )
    if reject_ready and exact_rate is not None and exact_rate < 0.6:
        return "REJECT_GUARD", criteria
    enough_data = (
        exact_safe.events >= 5
        and broad_only.events >= 5
        and len(exact_safe.episode_tokens) >= 4
        and len(broad_only.episode_tokens) >= 4
        and len(exact_safe.team_tokens) >= 2
    )
    if not enough_data:
        return "HOLD_DATA", criteria
    if (
        exact_rate is not None
        and broad_rate is not None
        and exact_rate >= 0.8
        and exact_rate - broad_rate >= 0.2
    ):
        return "SUPPORT_NARROW_TO_FRESH_TRACE", criteria
    return "INCONCLUSIVE_GUARD", criteria


def assemble_report(
    state: ScanState,
    dataset_label: str,
    excluded_decisions: set[str],
    exclude_fingerprint: str,
    policy_build_label: str,
    policy_build_sha256: str,
    policy_model_sha256: str,
) -> dict:
    technical = {
        key: int(state.technical.get(key, 0))
        for key in sorted(TECHNICAL_KEYS)
    }
    technical_error_count = sum(technical.values())
    decision, criteria = classify_gate(
        state.exact_safe, state.broad_only, technical_error_count,
    )
    broad_hits = int(state.az003.get("broad_hits_audited", 0))
    semantic_hits = int(state.az003.get("semantic_outside_top5", 0))
    az003 = {
        "broad_hits_raw": int(state.az003.get("broad_hits_raw", 0)),
        "overlap_excluded": int(state.az003.get("overlap_excluded", 0)),
        "broad_hits_audited": broad_hits,
        "broad_teacher_matches": int(
            state.az003.get("broad_teacher_matches", 0)
        ),
        "broad_teacher_rate": _rate(
            int(state.az003.get("broad_teacher_matches", 0)), broad_hits,
        ),
        "multiple_hammer_hits": int(
            state.az003.get("multiple_hammer_hits", 0)
        ),
        "semantic_top5_present": int(
            state.az003.get("semantic_top5_present", 0)
        ),
        "semantic_outside_top5": semantic_hits,
        "semantic_teacher_matches": int(
            state.az003.get("semantic_teacher_matches", 0)
        ),
        "semantic_teacher_rate": _rate(
            int(state.az003.get("semantic_teacher_matches", 0)),
            semantic_hits,
        ),
    }
    return {
        "analysis": "az003_exact_safe_independent_holdout",
        "analysis_version": ANALYSIS_VERSION,
        "aggregate_only": True,
        "dataset_label": dataset_label,
        "dataset_fingerprint_sha256": _fingerprint(
            state.raw_episode_digests,
        ),
        "exclude_decision_count": len(excluded_decisions),
        "exclude_decision_set_sha256": exclude_fingerprint,
        "policy_build": policy_build_label,
        "policy_build_sha256": policy_build_sha256,
        "policy_model_sha256": policy_model_sha256,
        "recovery_baseline_sha256": RECOVERY_BASELINE_SHA256,
        "policy_enabled": bool(policy.ENABLED),
        "profile": PROFILE,
        "rule_id": RULE_ID,
        "scan": {
            key: int(state.scan.get(key, 0))
            for key in sorted(SCAN_KEYS)
        },
        "technical": technical,
        "az003": az003,
        "cohorts": {
            "exact_safe": state.exact_safe.report(),
            "broad_only": state.broad_only.report(),
        },
        "same_turn_diagnostic": summarize_same_turn(
            state.transition_events,
        ),
        "gate": {"decision": decision, "criteria": criteria},
    }


def _check_exact_keys(value: dict, expected: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(code)


def validate_report_privacy(report: dict) -> None:
    """aggregate allowlistと相互整合を満たさない成果物を拒否する。"""
    _check_exact_keys(report, REPORT_KEYS, "REPORT_SCHEMA")
    _check_exact_keys(report["scan"], SCAN_KEYS, "SCAN_SCHEMA")
    _check_exact_keys(report["technical"], TECHNICAL_KEYS, "TECHNICAL_SCHEMA")
    _check_exact_keys(report["az003"], AZ003_KEYS, "AZ003_SCHEMA")
    _check_exact_keys(
        report["cohorts"], {"exact_safe", "broad_only"}, "COHORT_SCHEMA",
    )
    for cohort in report["cohorts"].values():
        _check_exact_keys(cohort, COHORT_KEYS, "COHORT_SCHEMA")
    _check_exact_keys(
        report["same_turn_diagnostic"], TRANSITION_KEYS, "TRANSITION_SCHEMA",
    )
    _check_exact_keys(report["gate"], GATE_KEYS, "GATE_SCHEMA")
    _check_exact_keys(
        report["gate"]["criteria"], CRITERIA_KEYS, "CRITERIA_SCHEMA",
    )
    if (
        report["analysis"] != "az003_exact_safe_independent_holdout"
        or report["analysis_version"] != ANALYSIS_VERSION
        or report["aggregate_only"] is not True
        or report["profile"] != PROFILE
        or report["rule_id"] != RULE_ID
        or report["policy_enabled"] is not True
    ):
        raise ValueError("REPORT_IDENTITY")
    if LABEL.fullmatch(str(report["dataset_label"])) is None:
        raise ValueError("DATASET_LABEL")
    build = str(report["policy_build"])
    if (
        os.path.isabs(build)
        or build.startswith("..")
        or "/../" in build
        or not build.startswith("build/")
    ):
        raise ValueError("POLICY_BUILD_PATH")
    for key in (
        "dataset_fingerprint_sha256",
        "exclude_decision_set_sha256",
        "policy_build_sha256",
        "policy_model_sha256",
        "recovery_baseline_sha256",
    ):
        if HEX64.fullmatch(str(report[key])) is None:
            raise ValueError("FINGERPRINT_SCHEMA")

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in DENIED_KEYS:
                    raise ValueError("PRIVACY_DENIED_KEY")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        elif isinstance(value, str) and os.path.isabs(value):
            raise ValueError("PRIVACY_ABSOLUTE_PATH")

    walk(report)
    for section in (
        report["scan"],
        report["technical"],
        {
            key: value for key, value in report["az003"].items()
            if not key.endswith("_rate")
        },
        {
            key: value
            for cohort in report["cohorts"].values()
            for key, value in cohort.items()
            if not key.endswith("_rate")
        },
        report["same_turn_diagnostic"],
    ):
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in section.values()
        ):
            raise ValueError("NONNEGATIVE_COUNT_SCHEMA")
    if sum(report["technical"].values()) != report["gate"]["criteria"][
        "technical_error_count"
    ]:
        raise ValueError("TECHNICAL_COUNT_MISMATCH")
    exact = report["cohorts"]["exact_safe"]
    broad = report["cohorts"]["broad_only"]
    if (
        exact["events"] + broad["events"]
        != report["az003"]["semantic_outside_top5"]
        or report["az003"]["semantic_top5_present"]
        + report["az003"]["semantic_outside_top5"]
        != report["az003"]["broad_hits_audited"]
        or exact["teacher_hammer_matches"] + broad["teacher_hammer_matches"]
        != report["az003"]["semantic_teacher_matches"]
    ):
        raise ValueError("COHORT_TOTAL_MISMATCH")
    rate_checks = [
        (
            report["az003"]["broad_teacher_rate"],
            report["az003"]["broad_teacher_matches"],
            report["az003"]["broad_hits_audited"],
        ),
        (
            report["az003"]["semantic_teacher_rate"],
            report["az003"]["semantic_teacher_matches"],
            report["az003"]["semantic_outside_top5"],
        ),
        (
            exact["teacher_hammer_rate"],
            exact["teacher_hammer_matches"],
            exact["events"],
        ),
        (
            broad["teacher_hammer_rate"],
            broad["teacher_hammer_matches"],
            broad["events"],
        ),
    ]
    if any(actual != _rate(matches, events)
           for actual, matches, events in rate_checks):
        raise ValueError("RATE_MISMATCH")


def validate_frozen_report(report: dict) -> None:
    """preflight後の再読込でも固定corpus・policy・除外集合が不変か確認する。"""
    expected = {
        "dataset_label": EXPECTED_DATASET_LABEL,
        "dataset_fingerprint_sha256": EXPECTED_DATASET_FINGERPRINT,
        "exclude_decision_count": EXPECTED_EXCLUDE_DECISIONS,
        "exclude_decision_set_sha256": EXPECTED_EXCLUDE_FINGERPRINT,
        "policy_build": EXPECTED_POLICY_BUILD,
        "policy_build_sha256": EXPECTED_POLICY_BUILD_SHA256,
        "policy_model_sha256": EXPECTED_POLICY_MODEL_SHA256,
        "recovery_baseline_sha256": RECOVERY_BASELINE_SHA256,
    }
    mismatches = [
        key for key, value in expected.items()
        if report.get(key) != value
    ]
    scan_expected = {
        "episode_files_seen": EXPECTED_EPISODE_FILES,
        "unique_raw_episodes": EXPECTED_UNIQUE_RAW_EPISODES,
        "duplicate_raw_episodes": 0,
        "no_unique_winner_episodes": 4,
    }
    mismatches.extend(
        f"scan.{key}"
        for key, value in scan_expected.items()
        if (report.get("scan") or {}).get(key) != value
    )
    if mismatches:
        raise ValueError(
            "frozen report mismatch: " + ",".join(sorted(mismatches)),
        )


def load_recovery_baseline() -> dict:
    path = os.path.join(ROOT, RECOVERY_BASELINE)
    with open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != RECOVERY_BASELINE_SHA256:
        raise ValueError("recovery baseline SHA mismatch")
    baseline = json.loads(raw)
    if (
        baseline.get("analysis") != "az003_exact_safe_independent_holdout"
        or baseline.get("analysis_version") != 1
        or (baseline.get("gate") or {}).get("decision") != "INVALID_RUN"
        or (baseline.get("technical") or {}).get("episode_schema_errors") != 4
        or sum((baseline.get("technical") or {}).values()) != 4
    ):
        raise ValueError("recovery baseline schema mismatch")
    return baseline


def validate_recovery_invariance(baseline: dict, recovered: dict) -> None:
    """引分skip以外が初回INVALIDから1 bitでも変われば回復判定を拒否する。"""
    exact_sections = ("az003", "cohorts", "same_turn_diagnostic")
    mismatches = [
        section for section in exact_sections
        if baseline.get(section) != recovered.get(section)
    ]
    immutable_fields = (
        "aggregate_only",
        "analysis",
        "dataset_label",
        "dataset_fingerprint_sha256",
        "exclude_decision_count",
        "exclude_decision_set_sha256",
        "policy_build",
        "policy_build_sha256",
        "policy_enabled",
        "policy_model_sha256",
        "profile",
        "rule_id",
    )
    mismatches.extend(
        key for key in immutable_fields
        if baseline.get(key) != recovered.get(key)
    )
    initial_scan = baseline.get("scan") or {}
    recovered_scan = recovered.get("scan") or {}
    for key, value in initial_scan.items():
        if recovered_scan.get(key) != value:
            mismatches.append(f"scan.{key}")
    if recovered_scan.get("no_unique_winner_episodes") != 4:
        mismatches.append("scan.no_unique_winner_episodes")

    initial_technical = baseline.get("technical") or {}
    recovered_technical = recovered.get("technical") or {}
    if (
        initial_technical.get("episode_schema_errors") != 4
        or sum(initial_technical.values()) != 4
        or any(recovered_technical.values())
    ):
        mismatches.append("technical")

    initial_criteria = dict((baseline.get("gate") or {}).get("criteria") or {})
    recovered_criteria = dict(
        (recovered.get("gate") or {}).get("criteria") or {}
    )
    initial_criteria.pop("technical_error_count", None)
    recovered_criteria.pop("technical_error_count", None)
    if initial_criteria != recovered_criteria:
        mismatches.append("gate.criteria")
    if (
        (recovered.get("gate") or {}).get("criteria", {}).get(
            "technical_error_count"
        ) != 0
        or (recovered.get("gate") or {}).get("decision")
        != "INCONCLUSIVE_GUARD"
        or recovered.get("analysis_version") != ANALYSIS_VERSION
        or recovered.get("recovery_baseline_sha256")
        != RECOVERY_BASELINE_SHA256
    ):
        mismatches.append("recovery_identity")
    if mismatches:
        raise ValueError(
            "recovery invariance mismatch: "
            + ",".join(sorted(set(mismatches))),
        )


def _policy_build_label() -> str:
    label = os.path.relpath(MODULE_ROOT, ROOT)
    if label.startswith("..") or os.path.isabs(label):
        raise ValueError("--policy-build must be inside repository")
    return label


def _write_new_json(path: str, report: dict) -> None:
    if os.path.exists(path):
        raise FileExistsError(f"refusing to overwrite holdout result: {path}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_dir")
    parser.add_argument("--policy-build", required=True)
    parser.add_argument(
        "--exclude-pairs", action="append", required=True,
        help="開発日に含まれるdecisionを除外するpairs JSONL.gz（複数可）",
    )
    parser.add_argument("--dataset-label", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.dataset_label != EXPECTED_DATASET_LABEL:
        parser.error(
            f"--dataset-labelは固定値{EXPECTED_DATASET_LABEL}",
        )
    output_label = os.path.relpath(os.path.abspath(args.output), ROOT)
    if output_label != EXPECTED_OUTPUT:
        parser.error(f"--outputは固定値{EXPECTED_OUTPUT}")
    if os.path.exists(args.output):
        parser.error(f"--outputは新規pathを指定する: {args.output}")
    baseline = load_recovery_baseline()
    build_label = _policy_build_label()
    policy_fingerprint = agent_fingerprint(MODULE_ROOT)
    excluded, exclude_fingerprint = load_excluded_decisions(
        args.exclude_pairs,
    )
    file_count, unique_count, dataset_fingerprint = (
        fingerprint_episode_corpus(args.episode_dir)
    )
    validate_frozen_inputs(
        args.dataset_label,
        build_label,
        policy_fingerprint,
        len(excluded),
        exclude_fingerprint,
        file_count,
        unique_count,
        dataset_fingerprint,
    )
    state = scan_episode_dir(args.episode_dir, excluded)
    report = assemble_report(
        state,
        args.dataset_label,
        excluded,
        exclude_fingerprint,
        build_label,
        policy_fingerprint["sha256"],
        policy_fingerprint["model_sha256"],
    )
    validate_report_privacy(report)
    validate_frozen_report(report)
    validate_recovery_invariance(baseline, report)
    _write_new_json(args.output, report)
    print(json.dumps({
        "output": os.path.relpath(args.output, ROOT),
        "gate": report["gate"]["decision"],
        "broad_hits": report["az003"]["broad_hits_audited"],
        "semantic_outside_top5": report["az003"][
            "semantic_outside_top5"
        ],
        "exact_safe_events": report["cohorts"]["exact_safe"]["events"],
        "broad_only_events": report["cohorts"]["broad_only"]["events"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
