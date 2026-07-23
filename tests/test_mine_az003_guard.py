import copy
import gzip
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from scripts import mine_az003_guard as mining  # noqa: E402


ALAKAZAM_DECK = [741] * 4 + [742] * 4 + [743] * 4 + [305] * 48


def pokemon(card_id, hp=100, energies=None, energy_cards=None):
    return {
        "id": card_id,
        "hp": hp,
        "maxHp": hp,
        "energies": list(energies or []),
        "energyCards": list(energy_cards or []),
        "preEvolution": [],
        "tools": [],
    }


def player(hand=None, active=None, bench=None):
    return {
        "hand": [{"id": card_id} for card_id in (hand or [])],
        "handCount": len(hand or []),
        "active": list(active or []),
        "bench": list(bench or []),
        "benchMax": 5,
        "deckCount": 20,
        "discard": [],
        "prize": [None] * 6,
        "asleep": False,
        "paralyzed": False,
        "confused": False,
    }


def exact_safe_episode():
    mine = player(
        hand=[1081, 1081],
        active=[pokemon(743, energies=[5], energy_cards=[{"id": 5}])],
    )
    mine["handCount"] = 20
    opponent = player(
        active=[pokemon(305, hp=300, energy_cards=[{"id": 11}])],
    )
    options = [
        {"type": 13, "attackId": 1072},
        {"type": 14},
        {"type": 14},
        {"type": 14},
        {"type": 14},
        {"type": 7, "area": 2, "index": 0},
        {"type": 7, "area": 2, "index": 1},
    ]
    observation = {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": options,
        },
        "current": {
            "yourIndex": 0,
            "players": [mine, opponent],
            "turn": 4,
            "turnActionCount": 2,
            "result": -1,
        },
    }
    return {
        "rewards": [1, -1],
        "info": {"TeamNames": ["winner", "loser"]},
        "steps": [
            [{}, {}],
            [
                {
                    "action": ALAKAZAM_DECK,
                    "status": "ACTIVE",
                    "observation": observation,
                },
                {},
            ],
            [{"action": [6]}, {}],
        ],
    }


class SemanticRankTests(unittest.TestCase):
    def test_all_hammer_copies_must_be_outside_top_five(self):
        scores = [9, 8, 7, 6, 5, 4, 3]
        self.assertEqual(
            mining.semantic_hammer_rank(scores, ((5,), (6,)), 7),
            6,
        )
        self.assertEqual(
            mining.semantic_hammer_rank(scores, ((3,), (6,)), 7),
            4,
        )

    def test_missing_and_nonfinite_scores_fail_closed(self):
        with self.assertRaises(mining.ScoreMissing):
            mining.semantic_hammer_rank(None, ((0,),), 1)
        with self.assertRaises(mining.ScoreMissing):
            mining.semantic_hammer_rank([], ((0,),), 1)
        with self.assertRaises(mining.ScoreNonFinite):
            mining.semantic_hammer_rank([np.nan], ((0,),), 1)
        with self.assertRaises(mining.HammerRankError):
            mining.semantic_hammer_rank([1.0], (), 1)


class EpisodeScanTests(unittest.TestCase):
    def test_corpus_fingerprint_is_a_unique_raw_sha_set(self):
        raw = json.dumps({"fixed": True}, sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as directory:
            for name in ("a.json", "b.json"):
                with open(os.path.join(directory, name), "wb") as handle:
                    handle.write(raw)
            files, unique, fingerprint = mining.fingerprint_episode_corpus(
                directory,
            )
        digest = mining.hashlib.sha256(raw).hexdigest()
        self.assertEqual((files, unique), (2, 1))
        self.assertEqual(fingerprint, mining._fingerprint({digest}))

    def test_episode_scan_matches_alternate_hammer_and_exact_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "episode.json")
            with open(path, "w") as handle:
                json.dump(exact_safe_episode(), handle)
            state = mining.scan_episode_dir(
                directory,
                set(),
                score_fn=lambda _obs: [9, 8, 7, 6, 5, 4, 3],
            )

        self.assertEqual(state.technical, {})
        self.assertEqual(state.scan["alakazam_winner_episodes"], 1)
        self.assertEqual(state.scan["alakazam_winner_decisions"], 1)
        self.assertEqual(state.az003["broad_hits_audited"], 1)
        self.assertEqual(state.az003["semantic_outside_top5"], 1)
        self.assertEqual(state.exact_safe.events, 1)
        self.assertEqual(state.exact_safe.teacher_hammer_matches, 1)
        self.assertEqual(state.broad_only.events, 0)

    def test_normalized_exclusion_does_not_depend_on_team_name(self):
        episode = exact_safe_episode()
        obs = episode["steps"][1][0]["observation"]
        row = {
            "sel": obs["select"],
            "cur": obs["current"],
            "act": [6],
            "team": "old-name",
            "deck": ALAKAZAM_DECK,
        }
        duplicate = dict(row, team="new-name")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pairs.jsonl.gz")
            with gzip.open(path, "wt") as handle:
                handle.write(json.dumps(row) + "\n")
                handle.write(json.dumps(duplicate) + "\n")
            excluded, fingerprint = mining.load_excluded_decisions([path])

        self.assertEqual(len(excluded), 1)
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

    def test_score_failure_stays_a_schema_valid_invalid_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "episode.json")
            with open(path, "w") as handle:
                json.dump(exact_safe_episode(), handle)
            state = mining.scan_episode_dir(
                directory, set(), score_fn=lambda _obs: None,
            )

        report = mining.assemble_report(
            state,
            "daily-top-test",
            set(),
            mining._fingerprint(()),
            "build/test",
            "b" * 64,
            "c" * 64,
        )
        report["policy_enabled"] = True
        mining.validate_report_privacy(report)
        self.assertEqual(report["gate"]["decision"], "INVALID_RUN")
        self.assertEqual(report["az003"]["broad_hits_raw"], 1)
        self.assertEqual(report["az003"]["broad_hits_audited"], 0)


class GateTests(unittest.TestCase):
    @staticmethod
    def cohort(matches, events, team_count=2):
        cohort = mining.Cohort()
        for index in range(events):
            cohort.add(
                f"episode-{index}",
                f"team-{index % team_count}",
                index < matches,
            )
        return cohort

    def test_support_requires_alignment_advantage(self):
        exact = self.cohort(5, 5)
        broad = self.cohort(2, 5)
        decision, criteria = mining.classify_gate(exact, broad, 0)
        self.assertEqual(decision, "SUPPORT_NARROW_TO_FRESH_TRACE")
        self.assertEqual(criteria["observed_rate_advantage"], 0.6)

        broad = self.cohort(9, 10)
        exact = self.cohort(10, 10)
        decision, _ = mining.classify_gate(exact, broad, 0)
        self.assertEqual(decision, "INCONCLUSIVE_GUARD")

    def test_hold_reject_and_invalid_are_distinct(self):
        decision, _ = mining.classify_gate(
            self.cohort(3, 3), self.cohort(1, 3), 0,
        )
        self.assertEqual(decision, "HOLD_DATA")

        decision, _ = mining.classify_gate(
            self.cohort(2, 5), self.cohort(4, 5), 0,
        )
        self.assertEqual(decision, "REJECT_GUARD")

        decision, _ = mining.classify_gate(
            self.cohort(2, 5), self.cohort(0, 0), 0,
        )
        self.assertEqual(decision, "REJECT_GUARD")

        decision, _ = mining.classify_gate(
            self.cohort(5, 5, team_count=1), self.cohort(0, 5), 0,
        )
        self.assertEqual(decision, "HOLD_DATA")

        decision, _ = mining.classify_gate(
            self.cohort(5, 5), self.cohort(0, 5), 1,
        )
        self.assertEqual(decision, "INVALID_RUN")

    def test_frozen_input_contract_rejects_any_changed_component(self):
        fingerprint = {
            "sha256": mining.EXPECTED_POLICY_BUILD_SHA256,
            "model_sha256": mining.EXPECTED_POLICY_MODEL_SHA256,
        }
        values = [
            mining.EXPECTED_DATASET_LABEL,
            mining.EXPECTED_POLICY_BUILD,
            fingerprint,
            mining.EXPECTED_EXCLUDE_DECISIONS,
            mining.EXPECTED_EXCLUDE_FINGERPRINT,
            mining.EXPECTED_EPISODE_FILES,
            mining.EXPECTED_UNIQUE_RAW_EPISODES,
            mining.EXPECTED_DATASET_FINGERPRINT,
        ]
        with mock.patch.object(mining.policy, "ENABLED", True):
            mining.validate_frozen_inputs(*values)
        changed = list(values)
        changed[3] -= 1
        with mock.patch.object(mining.policy, "ENABLED", True):
            with self.assertRaisesRegex(ValueError, "exclude_count"):
                mining.validate_frozen_inputs(*changed)


class TransitionAndPrivacyTests(unittest.TestCase):
    def test_same_turn_transition_is_aggregate_only(self):
        events = [
            {
                "episode_token": "e1",
                "turn": 4,
                "step_index": 10,
                "exact_safe": False,
                "teacher_match": True,
            },
            {
                "episode_token": "e1",
                "turn": 4,
                "step_index": 12,
                "exact_safe": True,
                "teacher_match": False,
            },
            {
                "episode_token": "e1",
                "turn": 5,
                "step_index": 15,
                "exact_safe": True,
                "teacher_match": True,
            },
        ]
        got = mining.summarize_same_turn(events)
        self.assertEqual(got["broad_to_later_exact_turns"], 1)
        self.assertEqual(
            got["broad_teacher_hammer_to_later_exact_turns"], 1,
        )
        self.assertEqual(got["episodes_with_broad_to_later_exact"], 1)

    def test_report_allowlist_rejects_paths_and_extra_fields(self):
        state = mining.ScanState()
        state.raw_episode_digests.append("a" * 64)
        report = mining.assemble_report(
            state,
            "daily-top-20260722",
            set(),
            mining._fingerprint(()),
            "build/test",
            "b" * 64,
            "c" * 64,
        )
        report["policy_enabled"] = True
        mining.validate_report_privacy(report)
        with self.assertRaises(ValueError):
            mining.validate_frozen_report(report)

        frozen = copy.deepcopy(report)
        frozen.update({
            "dataset_label": mining.EXPECTED_DATASET_LABEL,
            "dataset_fingerprint_sha256":
                mining.EXPECTED_DATASET_FINGERPRINT,
            "exclude_decision_count": mining.EXPECTED_EXCLUDE_DECISIONS,
            "exclude_decision_set_sha256":
                mining.EXPECTED_EXCLUDE_FINGERPRINT,
            "policy_build": mining.EXPECTED_POLICY_BUILD,
            "policy_build_sha256": mining.EXPECTED_POLICY_BUILD_SHA256,
            "policy_model_sha256": mining.EXPECTED_POLICY_MODEL_SHA256,
        })
        frozen["scan"].update({
            "episode_files_seen": mining.EXPECTED_EPISODE_FILES,
            "unique_raw_episodes": mining.EXPECTED_UNIQUE_RAW_EPISODES,
            "duplicate_raw_episodes": 0,
        })
        mining.validate_frozen_report(frozen)

        absolute = copy.deepcopy(report)
        absolute["policy_build"] = "/tmp/build/test"
        with self.assertRaises(ValueError):
            mining.validate_report_privacy(absolute)

        extra = copy.deepcopy(report)
        extra["team"] = "secret"
        with self.assertRaises(ValueError):
            mining.validate_report_privacy(extra)


if __name__ == "__main__":
    unittest.main()
