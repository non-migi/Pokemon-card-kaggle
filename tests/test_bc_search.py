import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ptcg import bc_search  # noqa: E402


def searchable_observation():
    return {
        "select": {
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 14}, {"type": 13, "attackId": 1072}],
        },
        "current": {"yourIndex": 0},
    }


class FixedSearchDiagnosticTests(unittest.TestCase):
    def test_missing_bc_scores_has_explicit_stage(self):
        with mock.patch.object(bc_search.policy, "scores", return_value=None):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"bc_scores": 1})

    def test_world_setup_stages_are_distinguished(self):
        world = ([], [], [], [], [], [])
        common = mock.patch.object(bc_search.policy, "scores", return_value=[1, 0])
        with common, mock.patch.object(
            bc_search, "sample_world", side_effect=RuntimeError("belief"),
        ), mock.patch.object(bc_search, "search_end"):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"belief_sample": 1})

        with mock.patch.object(
            bc_search.policy, "scores", return_value=[1, 0],
        ), mock.patch.object(
            bc_search, "sample_world", return_value=world,
        ), mock.patch.object(
            bc_search, "search_begin_dict", side_effect=RuntimeError("begin"),
        ), mock.patch.object(bc_search, "search_end"):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"world_begin": 1})

    def test_candidate_step_and_rollout_stages_are_distinguished(self):
        world = ([], [], [], [], [], [])
        patches = (
            mock.patch.object(bc_search.policy, "scores", return_value=[1, 0]),
            mock.patch.object(bc_search, "sample_world", return_value=world),
            mock.patch.object(
                bc_search, "search_begin_dict", return_value={"searchId": "s"},
            ),
            mock.patch.object(bc_search, "search_end"),
        )
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            bc_search, "search_step_dict", side_effect=RuntimeError("step"),
        ):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"candidate_step": 4})

        with mock.patch.object(
            bc_search.policy, "scores", return_value=[1, 0],
        ), mock.patch.object(
            bc_search, "sample_world", return_value=world,
        ), mock.patch.object(
            bc_search, "search_begin_dict", return_value={"searchId": "s"},
        ), mock.patch.object(
            bc_search, "search_step_dict", return_value={"observation": {}},
        ), mock.patch.object(
            bc_search, "_rollout", side_effect=RuntimeError("rollout"),
        ), mock.patch.object(bc_search, "search_end"):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"candidate_rollout": 4})

    def test_hard_stop_stage_is_recorded(self):
        world = ([], [], [], [], [], [])
        with mock.patch.object(
            bc_search.policy, "scores", return_value=[1, 0],
        ), mock.patch.object(
            bc_search, "sample_world", return_value=world,
        ), mock.patch.object(
            bc_search, "search_begin_dict", return_value={"searchId": "s"},
        ), mock.patch.object(
            bc_search.time, "monotonic", side_effect=[0.0, 31.0, 31.0],
        ), mock.patch.object(bc_search, "search_end"):
            with self.assertRaises(bc_search.FixedSearchIncomplete) as caught:
                bc_search.decide(
                    searchable_observation(), object(), [], 1.0,
                    fixed_worlds=2,
                )
        self.assertEqual(caught.exception.stage_counts, {"hard_stop": 2})

    def test_recording_includes_stage_and_active_rule_context(self):
        metrics = {}
        exc = bc_search.FixedSearchIncomplete(
            "incomplete", {"candidate_rollout": 2},
        )
        proposal = SimpleNamespace(rule_id="AZ008_DRAW_TO_EXACT_KO")
        bc_search.record_fixed_search_incomplete(metrics, exc, [proposal])
        self.assertEqual(metrics, {
            "fixed_search_incomplete": 1,
            "fixed_search_incomplete_stage.candidate_rollout": 2,
            "fixed_search_incomplete_rule_context.AZ008_DRAW_TO_EXACT_KO": 1,
        })

        no_rule_metrics = {}
        bc_search.record_fixed_search_incomplete(no_rule_metrics, exc, [])
        self.assertEqual(
            no_rule_metrics["fixed_search_incomplete_rule_context.none"], 1,
        )

    def test_only_selected_outside_top5_rule_is_injected_selection(self):
        metrics = {}
        bc_search._record_injected_selection(
            {(6,): {"AZ008_DRAW_TO_EXACT_KO"}}, [6], metrics,
        )
        self.assertEqual(
            metrics["expert_rule_injected_selected.AZ008_DRAW_TO_EXACT_KO"], 1,
        )

        not_injected_metrics = {}
        bc_search._record_injected_selection(
            {(6,): {"AZ008_DRAW_TO_EXACT_KO"}}, [4], not_injected_metrics,
        )
        self.assertEqual(not_injected_metrics, {})

    def test_candidate_builder_reports_only_actions_it_really_injected(self):
        proposal = SimpleNamespace(
            rule_id="AZ008_DRAW_TO_EXACT_KO", action=(6,), kind="candidate",
        )
        scores = [7, 6, 5, 4, 3, 2, 1]
        injected = {}
        bc_search._candidate_actions(
            scores, 7, [proposal], "candidate", {},
            injected_actions=injected,
        )
        self.assertEqual(injected, {(6,): {"AZ008_DRAW_TO_EXACT_KO"}})

        shadow_injected = {}
        bc_search._candidate_actions(
            scores, 7, [proposal], "shadow", {},
            forbidden_actions=[(0,)],
            injected_actions=shadow_injected,
        )
        self.assertEqual(shadow_injected, {})

    def test_candidate_builder_excludes_rules_beyond_injection_slots(self):
        proposals = [
            SimpleNamespace(rule_id=f"AZ_TEST_{i}", action=(i,), kind="candidate")
            for i in (5, 6, 7)
        ]
        injected = {}
        bc_search._candidate_actions(
            [8, 7, 6, 5, 4, 3, 2, 1], 8, proposals, "candidate", {},
            injected_actions=injected,
        )
        self.assertEqual(set(injected), {(5,), (6,)})
        metrics = {}
        bc_search._record_injected_selection(injected, [7], metrics)
        self.assertEqual(metrics, {})

    def test_decide_records_selected_injected_action_end_to_end(self):
        obs = searchable_observation()
        obs["select"]["option"] = [{"type": 14} for _ in range(7)]
        proposal = SimpleNamespace(
            rule_id="AZ008_DRAW_TO_EXACT_KO", action=(6,), kind="candidate",
        )
        metrics = {}
        world = ([], [], [], [], [], [])

        def step(_search_id, action):
            return {"chosen": tuple(action)}

        def rollout(child, _my_index):
            return float(child["chosen"] == (6,))

        with mock.patch.object(
            bc_search.policy, "scores", return_value=[7, 6, 5, 4, 3, 2, 1],
        ), mock.patch.object(
            bc_search, "sample_world", return_value=world,
        ), mock.patch.object(
            bc_search, "search_begin_dict", return_value={"searchId": "s"},
        ), mock.patch.object(
            bc_search, "search_step_dict", side_effect=step,
        ), mock.patch.object(
            bc_search, "_rollout", side_effect=rollout,
        ), mock.patch.object(
            bc_search.time, "time",
            side_effect=AssertionError("wall clock must not gate search"),
        ), mock.patch.object(bc_search, "search_end"):
            selected = bc_search.decide(
                obs, object(), [], 1.0, fixed_worlds=2,
                rule_proposals=[proposal], rule_mode="candidate",
                metrics=metrics,
            )

        self.assertEqual(selected, [6])
        injected = metrics["expert_rule_injected.AZ008_DRAW_TO_EXACT_KO"]
        selected_injected = metrics[
            "expert_rule_injected_selected.AZ008_DRAW_TO_EXACT_KO"
        ]
        self.assertEqual((injected, selected_injected), (1, 1))
        self.assertLessEqual(selected_injected, injected)


if __name__ == "__main__":
    unittest.main()
