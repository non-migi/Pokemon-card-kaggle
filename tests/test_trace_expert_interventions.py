import gzip
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from ptcg import expert_rules  # noqa: E402
from scripts import trace_expert_interventions as trace  # noqa: E402


def q_row(action, q):
    return {"action": [action], "total": q * 2, "count": 2, "q": q}


def gate_event(selected=False, strict=False, dominated=False):
    return {
        "status": "complete",
        "legal_injection": True,
        "audit_match": True,
        "policy_selected_rule": selected,
        "gate_rule_not_dominated": not dominated,
        "gate_rule_strictly_better": strict,
    }


def valid_complete_event():
    policy_q = [
        q_row(0, 0.0),
        q_row(6, 1.0),
        q_row(1, 0.0),
        q_row(2, 0.0),
        q_row(3, 0.0),
    ]
    shadow_q = [
        q_row(0, 1.0),
        q_row(1, 0.0),
        q_row(2, 0.0),
        q_row(3, 0.0),
        q_row(4, 0.0),
        q_row(6, 0.5),
    ]
    return {
        "row_number": 1,
        "row_sha256": "a" * 64,
        "status": "complete",
        "reason_codes": [],
        "rule_id": "AZ003_HAMMER_BLOCKER_PLAY",
        "rule_action": [6],
        "legal_injection": True,
        "audit_match": True,
        "original_bc_top5": [
            {"rank": i + 1, "action": [i], "score": float(5 - i)}
            for i in range(5)
        ],
        "policy_candidates": [[0], [6], [1], [2], [3]],
        "dropped_bc_action": [4],
        "policy_q": policy_q,
        "policy_selected_action": [6],
        "policy_selected_rule": True,
        "counterfactual_candidates": [[0], [1], [2], [3], [4], [6]],
        "counterfactual_q": shadow_q,
        "counterfactual_rule_q": 0.5,
        "counterfactual_original_max_q": 1.0,
        "counterfactual_q_delta": -0.5,
        "counterfactual_rule_not_dominated": False,
        "counterfactual_rule_strictly_better": False,
        "policy_rule_q": 1.0,
        "policy_retained_original_max_q": 0.0,
        "gate_dropped_original_q": 0.0,
        "gate_original_max_q": 0.0,
        "gate_q_delta": 1.0,
        "gate_rule_not_dominated": True,
        "gate_rule_strictly_better": True,
        "world_count": 2,
    }


class FrozenRowRecoveryTests(unittest.TestCase):
    def test_episode_row_hash_matches_bc_extract_serialization(self):
        deck = list(range(60))
        observation = {
            "select": {
                "type": 0,
                "minCount": 1,
                "maxCount": 1,
                "option": [{}, {}],
            },
            "current": {"yourIndex": 0},
            "search_begin_input": "token",
            "remainingOverageTime": 600,
        }
        episode = {
            "rewards": [1, 0],
            "info": {"TeamNames": ["winner", "loser"]},
            "steps": [
                [{}, {}],
                [
                    {
                        "status": "ACTIVE",
                        "observation": observation,
                        "action": deck,
                    },
                    {},
                ],
                [{"action": [1]}, {}],
            ],
        }
        expected_row = {
            "sel": observation["select"],
            "cur": observation["current"],
            "act": [1],
            "team": "winner",
            "deck": deck,
        }
        with tempfile.TemporaryDirectory() as directory:
            episode_path = os.path.join(directory, "public.json")
            with open(episode_path, "w") as f:
                json.dump(episode, f)
            rows = list(trace.iter_full_winner_rows(episode_path))

        self.assertEqual(len(rows), 1)
        row, recovered = rows[0]
        self.assertEqual(row, expected_row)
        self.assertEqual(
            trace._pair_sha256(row),
            trace._pair_sha256(expected_row),
        )
        self.assertEqual(recovered, observation)

    def test_pairs_are_pinned_by_row_number_and_raw_line_sha(self):
        row = {"sel": {}, "cur": {}, "act": [3], "team": "x", "deck": []}
        line = json.dumps(row, separators=(",", ":")) + "\n"
        target = {
            "row_number": 2,
            "row_sha256": trace.hashlib.sha256(line.encode()).hexdigest(),
            "rule_action": [3],
            "bc_rank": 6,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pairs.jsonl.gz")
            with gzip.open(path, "wt") as f:
                f.write('{"skip":true}\n')
                f.write(line)
            got = trace.load_frozen_pair_rows(path, [target])
        self.assertEqual(got[target["row_sha256"]], row)

    def test_audit_cannot_shrink_the_frozen_ten_event_gate(self):
        examples = [
            {
                "row_number": i + 1,
                "row_sha256": f"{i + 1:064x}",
                "rule_action": [3],
                "bc_rank": 6,
                "teacher_match": True,
            }
            for i in range(3)
        ]
        audit = {
            "rules": {
                trace.DEFAULT_RULE_ID: {"candidate_injected": len(examples)},
            },
            "candidate_injected_examples": examples,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "audit.json")
            with open(path, "w") as f:
                json.dump(audit, f)
            with self.assertRaisesRegex(
                trace.TraceFailure,
                "AUDIT_TARGET_COUNT_MISMATCH",
            ):
                trace.load_audit_targets(path, trace.DEFAULT_RULE_ID)


class CandidateTraceTests(unittest.TestCase):
    def test_layout_keeps_policy_at_five_and_shadow_restores_dropped_bc(self):
        proposal = expert_rules.RuleProposal(
            "AZ003_HAMMER_BLOCKER_PLAY",
            (6,),
            100,
            "candidate",
            "test",
        )
        observation = {
            "select": {
                "type": 0,
                "minCount": 1,
                "maxCount": 1,
                "option": [{} for _ in range(7)],
            },
            "current": {"yourIndex": 0},
        }
        target = {
            "row_number": 1,
            "row_sha256": "a" * 64,
            "rule_action": [6],
            "bc_rank": 7,
        }
        with mock.patch.object(
            trace.expert_rules, "evaluate", return_value=[proposal],
        ), mock.patch.object(
            trace.expert_rules, "legal_action", return_value=True,
        ), mock.patch.object(
            trace.expert_rules, "best_hard", return_value=None,
        ), mock.patch.object(
            trace.expert_rules, "forbidden_actions", return_value=set(),
        ), mock.patch.object(
            trace.policy, "scores", return_value=[7, 6, 5, 4, 3, 2, 1],
        ):
            got = trace.candidate_layout(
                observation,
                [],
                target,
                "alakazam_v1",
                ("AZ003_HAMMER_BLOCKER_PLAY",),
                "candidate",
                "AZ003_HAMMER_BLOCKER_PLAY",
            )

        self.assertEqual(got["policy_candidates"], [[0], [6], [1], [2], [3]])
        self.assertEqual(got["dropped_bc_action"], [4])
        self.assertEqual(
            got["counterfactual_candidates"],
            [[0], [1], [2], [3], [4], [6]],
        )

    def test_policy_selection_is_fixed_before_counterfactual_pass(self):
        proposal = SimpleNamespace(action=(6,))
        layout = {
            "proposal": proposal,
            "original_bc_top5": [
                {"rank": i + 1, "action": [i], "score": 5 - i}
                for i in range(5)
            ],
            "original_actions": [[i] for i in range(5)],
            "policy_candidates": [[0], [6], [1], [2], [3]],
            "dropped_bc_action": [4],
            "counterfactual_candidates": [[0], [1], [2], [3], [4], [6]],
        }
        policy_q = [
            q_row(0, 0.0),
            q_row(6, 1.0),
            q_row(1, 0.0),
            q_row(2, 0.0),
            q_row(3, 0.0),
        ]
        shadow_q = [
            q_row(0, 1.0),
            q_row(1, 0.0),
            q_row(2, 0.0),
            q_row(3, 0.0),
            q_row(4, 0.0),
            q_row(6, 0.5),
        ]
        payload = {
            "target": {
                "row_number": 1,
                "row_sha256": "b" * 64,
                "rule_action": [6],
                "bc_rank": 7,
            },
            "observation": {"current": {"yourIndex": 0}},
            "deck": [],
        }
        with mock.patch.object(
            trace.policy, "ENABLED", True,
        ), mock.patch.object(
            trace.expert_rules,
            "validate_config",
            return_value=("AZ003_HAMMER_BLOCKER_PLAY",),
        ), mock.patch.object(
            trace, "candidate_layout", return_value=layout,
        ), mock.patch.object(
            trace, "sample_frozen_worlds", return_value=[(), ()],
        ), mock.patch.object(
            trace,
            "evaluate_candidate_pool",
            side_effect=[policy_q, shadow_q],
        ) as evaluate:
            event = trace.run_trace_event(
                payload,
                "alakazam_v1",
                ("AZ003_HAMMER_BLOCKER_PLAY",),
                "candidate",
                "AZ003_HAMMER_BLOCKER_PLAY",
                2,
            )

        self.assertEqual(
            evaluate.call_args_list[0].args[1],
            layout["policy_candidates"],
        )
        self.assertEqual(
            evaluate.call_args_list[1].args[1],
            layout["counterfactual_candidates"],
        )
        self.assertEqual(event["policy_selected_action"], [6])
        self.assertTrue(event["policy_selected_rule"])
        self.assertFalse(event["counterfactual_rule_not_dominated"])
        self.assertTrue(event["gate_rule_not_dominated"])
        self.assertTrue(event["gate_rule_strictly_better"])
        self.assertEqual(event["policy_rule_q"], 1.0)
        self.assertEqual(event["gate_dropped_original_q"], 0.0)

    def test_pool_order_and_tie_break_match_bc_search_decide(self):
        candidates = [[0], [1], [2], [3], [4]]
        observation = {
            "select": {
                "type": next(iter(trace.bc_search.SEARCHABLE)),
                "maxCount": 1,
                "option": [{} for _ in candidates],
            },
            "current": {"yourIndex": 0},
        }
        worlds = [(10,), (20,)]

        def begin(_observation, world):
            return {"searchId": world}

        def step(search_id, action):
            return search_id, action[0]

        def rollout(child, _my_index):
            _, action = child
            return 1.0 if action in {0, 1} else 0.0

        with mock.patch.object(
            trace.bc_search.policy, "scores", return_value=[5, 4, 3, 2, 1],
        ), mock.patch.object(
            trace.bc_search, "_candidate_actions", return_value=candidates,
        ), mock.patch.object(
            trace.bc_search, "sample_world", side_effect=worlds,
        ), mock.patch.object(
            trace.bc_search, "search_begin_dict", side_effect=begin,
        ), mock.patch.object(
            trace.bc_search, "search_step_dict", side_effect=step,
        ), mock.patch.object(
            trace.bc_search, "_rollout", side_effect=rollout,
        ), mock.patch.object(
            trace.bc_search, "search_end",
        ):
            production_choice = trace.bc_search.decide(
                observation,
                object(),
                [],
                budget_sec=1.0,
                fixed_worlds=2,
            )
            trace_rows = trace.evaluate_candidate_pool(
                observation,
                candidates,
                worlds,
                "POLICY",
            )

        self.assertEqual(production_choice, [0])
        self.assertEqual(
            trace._selected_row(trace_rows)["action"],
            production_choice,
        )


class TraceGateTests(unittest.TestCase):
    def test_predeclared_safe_boundary(self):
        events = [
            gate_event(selected=True, strict=True),
            gate_event(selected=True, strict=True),
            gate_event(selected=True, strict=False),
        ] + [gate_event() for _ in range(7)]
        summary, gate = trace.classify_gate(events, 10)
        self.assertEqual(summary["policy_selected_rule_rows"], 3)
        self.assertEqual(summary["selected_rule_strict_rows"], 2)
        self.assertEqual(gate["outcome"], "TRACE_SAFE")

    def test_healthy_but_sparse_selection_holds(self):
        events = [
            gate_event(selected=True, strict=True),
            gate_event(selected=True, strict=True),
        ] + [gate_event() for _ in range(8)]
        _, gate = trace.classify_gate(events, 10)
        self.assertEqual(gate["outcome"], "TRACE_HOLD")
        self.assertIn(
            "INSUFFICIENT_SELECTED_RULE_ROWS",
            gate["reason_codes"],
        )

    def test_selected_dominated_rule_rejects(self):
        events = [gate_event(selected=True, dominated=True)] + [
            gate_event() for _ in range(9)
        ]
        summary, gate = trace.classify_gate(events, 10)
        self.assertEqual(summary["selected_rule_dominated_rows"], 1)
        self.assertEqual(gate["outcome"], "TRACE_REJECT")

    def test_technical_error_is_invalid_run_not_negative_evidence(self):
        events = [gate_event() for _ in range(9)] + [
            {
                "status": "error",
                "reason_codes": ["WORKER_TIMEOUT"],
            },
        ]
        _, gate = trace.classify_gate(events, 10)
        self.assertEqual(gate["outcome"], "INVALID_RUN")

    def test_expected_event_argument_cannot_weaken_frozen_gate(self):
        _, gate = trace.classify_gate([gate_event() for _ in range(3)], 3)
        self.assertEqual(gate["outcome"], "INVALID_RUN")
        self.assertIn(
            "AUDIT_TARGET_COUNT_MISMATCH",
            gate["reason_codes"],
        )


class TracePrivacyTests(unittest.TestCase):
    def test_event_schema_fails_closed_on_raw_observation(self):
        event = trace.error_event(
            {"row_number": 1, "row_sha256": "c" * 64},
            "TEST",
        )
        event["observation"] = {"private": True}
        with self.assertRaises(trace.TraceFailure):
            trace.validate_event_privacy(event)

    def test_error_event_contains_only_sanitized_provenance(self):
        event = trace.error_event(
            {"row_number": 9, "row_sha256": "d" * 64},
            "BELIEF_SAMPLE_FAILED",
        )
        trace.validate_event_privacy(event)
        self.assertEqual(
            set(event),
            {"row_number", "row_sha256", "status", "reason_codes"},
        )

    def test_valid_complete_event_passes_strict_schema(self):
        trace.validate_event_privacy(valid_complete_event())

    def test_allowed_field_cannot_hide_nested_raw_observation(self):
        event = valid_complete_event()
        event["policy_candidates"][0] = [
            {"current": {"yourIndex": 0}},
        ]
        with self.assertRaises(trace.TraceFailure):
            trace.validate_event_privacy(event)

    def test_nonfinite_q_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                event = valid_complete_event()
                event["policy_q"][0]["q"] = value
                with self.assertRaises(trace.TraceFailure):
                    trace.validate_event_privacy(event)

    def test_derived_gate_value_is_recomputed(self):
        event = valid_complete_event()
        event["gate_q_delta"] = 0.5
        with self.assertRaises(trace.TraceFailure):
            trace.validate_event_privacy(event)


class WorkerIsolationTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "target": {
                "row_number": 7,
                "row_sha256": "e" * 64,
            },
            "observation": {},
            "deck": [],
        }
        self.args = SimpleNamespace(
            policy_build="build/test",
            rule_id=trace.DEFAULT_RULE_ID,
            worlds=2,
            worker_timeout=1.0,
        )
        self.audit = {
            "profile": "alakazam_v1",
            "rule_mode": "candidate",
            "enabled_rule_ids": [trace.DEFAULT_RULE_ID],
        }

    def test_timeout_is_sanitized(self):
        with mock.patch.object(
            trace.subprocess,
            "run",
            side_effect=trace.subprocess.TimeoutExpired(["worker"], 1.0),
        ):
            event = trace.run_isolated_worker(
                self.payload,
                self.args,
                self.audit,
            )
        self.assertEqual(event["reason_codes"], ["WORKER_TIMEOUT"])
        trace.validate_event_privacy(event)

    def test_worker_target_mismatch_is_rejected(self):
        wrong = trace.error_event(
            {"row_number": 8, "row_sha256": "f" * 64},
            "BELIEF_SAMPLE_FAILED",
        )
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(wrong),
        )
        with mock.patch.object(
            trace.subprocess,
            "run",
            return_value=completed,
        ):
            event = trace.run_isolated_worker(
                self.payload,
                self.args,
                self.audit,
            )
        self.assertEqual(
            event["reason_codes"],
            ["WORKER_TARGET_MISMATCH"],
        )


if __name__ == "__main__":
    unittest.main()
