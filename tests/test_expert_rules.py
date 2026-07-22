import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ptcg import bc_search  # noqa: E402
from ptcg import expert_rules as rules  # noqa: E402


ALAKAZAM_DECK = [741] * 4 + [742] * 4 + [743] * 4 + [305] * 48


def pokemon(card_id, energies=None, energy_cards=None):
    return {
        "id": card_id,
        "hp": 100,
        "maxHp": 100,
        "energies": list(energies or []),
        "energyCards": list(energy_cards or []),
        "preEvolution": [],
        "tools": [],
    }


def player(hand=None, active=None, bench=None, deck_count=30):
    return {
        "hand": [{"id": cid} for cid in (hand or [])],
        "handCount": len(hand or []),
        "active": list(active or []),
        "bench": list(bench or []),
        "benchMax": 5,
        "deckCount": deck_count,
        "discard": [],
        "prize": [None] * 6,
    }


def observation(options, mine=None, opp=None, select_type=0, effect=None,
                min_count=1, max_count=1):
    return {
        "select": {
            "type": select_type,
            "context": 0,
            "minCount": min_count,
            "maxCount": max_count,
            "option": options,
            "effect": effect,
        },
        "current": {
            "yourIndex": 0,
            "players": [mine or player(), opp or player()],
            "turn": 3,
            "turnActionCount": 1,
            "result": -1,
        },
    }


class ExpertRuleTests(unittest.TestCase):
    def test_legal_action_rejects_invalid_indices_and_shapes(self):
        obs = observation([{}, {}, {}], min_count=1, max_count=2)
        self.assertTrue(rules.legal_action(obs, (0,)))
        self.assertTrue(rules.legal_action(obs, (0, 2)))
        for action in ((), (0, 1, 2), (0, 0), (-1,), (3,), (True,), ("0",)):
            with self.subTest(action=action):
                self.assertFalse(rules.legal_action(obs, action))

    def test_empty_bench_rule_proposes_missing_non_ex_basic(self):
        mine = player(hand=[305], active=[pokemon(741)], bench=[])
        obs = observation([
            {"type": 14},
            {"type": 7, "area": 2, "index": 0},
        ], mine=mine)
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ001_EMPTY_BENCH_BASIC"],
        )
        self.assertEqual([(p.rule_id, p.action, p.kind) for p in got], [
            ("AZ001_EMPTY_BENCH_BASIC", (1,), "candidate"),
        ])

        obs["current"]["players"][0]["bench"] = [pokemon(343)]
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ001_EMPTY_BENCH_BASIC"],
        ), [])

    def test_draw_evolution_rule_skips_low_deck(self):
        mine = player(hand=[742], active=[pokemon(741)], deck_count=20)
        obs = observation([
            {"type": 14},
            {"type": 9, "area": 2, "index": 0, "inPlayArea": 4,
             "inPlayIndex": 0},
        ], mine=mine)
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ002_DRAW_EVOLUTION"],
        )
        self.assertEqual(got[0].action, (1,))
        obs["current"]["players"][0]["deckCount"] = 3
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ002_DRAW_EVOLUTION"],
        ), [])

    def test_hammer_play_and_target_rules_cover_effect_blocker(self):
        mine = player(
            hand=[1081], active=[pokemon(743, energies=[5], energy_cards=[{"id": 19}])],
        )
        opp = player(
            active=[pokemon(305, energies=[0], energy_cards=[{"id": 11}])],
        )
        play_obs = observation([
            {"type": 14},
            {"type": 7, "area": 2, "index": 0},
        ], mine=mine, opp=opp)
        play = rules.evaluate(
            play_obs, ALAKAZAM_DECK, "alakazam_v1",
            ["AZ003_HAMMER_BLOCKER_PLAY"],
        )
        self.assertEqual((play[0].action, play[0].kind), ((1,), "candidate"))

        # Hammer解決中には別Pokemonがactiveでも、妨害energyを正しく選ぶ。
        target_mine = player(active=[pokemon(140)])
        target_obs = observation([
            {"type": 6, "area": 4, "index": 0, "playerIndex": 1,
             "energyIndex": 0},
        ], mine=target_mine, opp=opp, select_type=4, effect={"id": 1081})
        target = rules.evaluate(
            target_obs, ALAKAZAM_DECK, "alakazam_v1",
            ["AZ004_HAMMER_BLOCKER_TARGET"],
        )
        self.assertEqual((target[0].action, target[0].kind), ((0,), "hard"))
        self.assertEqual(rules.best_hard(target), target[0])

        opp["active"][0]["energyCards"][0]["id"] = 13
        self.assertEqual(rules.evaluate(
            target_obs, ALAKAZAM_DECK, "alakazam_v1",
            ["AZ004_HAMMER_BLOCKER_TARGET"],
        ), [])

    def test_rock_fighting_energy_blocks_only_on_fighting_pokemon(self):
        mine = player(
            hand=[1081], active=[pokemon(743, energies=[5], energy_cards=[{"id": 19}])],
        )
        opp = player(active=[pokemon(58, energy_cards=[{"id": 20}])])
        obs = observation([
            {"type": 14},
            {"type": 7, "area": 2, "index": 0},
        ], mine=mine, opp=opp)
        enabled = ["AZ003_HAMMER_BLOCKER_PLAY"]
        self.assertEqual(
            len(rules.evaluate(
                obs, ALAKAZAM_DECK, "alakazam_v1", enabled,
                card_energy_types={58: 6, 345: 1},
            )),
            1,
        )
        opp["active"][0]["id"] = 345
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", enabled,
            card_energy_types={58: 6, 345: 1},
        ), [])

    def test_empty_enabled_rule_list_is_rejected(self):
        with self.assertRaises(ValueError):
            rules.validate_config("alakazam_v1", "shadow", [])
        with self.assertRaises(ValueError):
            rules.validate_config("alakazam_v1", "candidate", None)

    def test_hammer_equivalent_blocker_targets_both_match(self):
        mine = player(active=[pokemon(140)])
        opp = player(active=[pokemon(
            879, energy_cards=[{"id": 11}, {"id": 11}, {"id": 19}],
        )])
        obs = observation([
            {"type": 6, "area": 4, "index": 0, "playerIndex": 1,
             "energyIndex": 0},
            {"type": 6, "area": 4, "index": 0, "playerIndex": 1,
             "energyIndex": 1},
            {"type": 6, "area": 4, "index": 0, "playerIndex": 1,
             "energyIndex": 2},
        ], mine=mine, opp=opp, select_type=4, effect={"id": 1081})
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1",
            ["AZ004_HAMMER_BLOCKER_TARGET"],
        )[0]
        self.assertTrue(rules.proposal_matches(got, [0]))
        self.assertTrue(rules.proposal_matches(got, [1]))
        self.assertFalse(rules.proposal_matches(got, [2]))

    def test_sole_dudunsparce_ability_is_a_negative_guard(self):
        mine = player(active=[pokemon(66)], bench=[])
        obs = observation([
            {"type": 7, "index": 0},
            {"type": 7, "index": 2},
            {"type": 7, "index": 3},
            {"type": 7, "index": 6},
            {"type": 7, "index": 7},
            {"type": 10, "area": 4, "index": 0},
            {"type": 14},
        ], mine=mine)
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ005_SOLE_DUDUN_GUARD"],
        )
        self.assertEqual((got[0].action, got[0].kind), ((5,), "forbid"))
        self.assertEqual(rules.forbidden_actions(got), {(5,)})

        # enforce時はBC top-1が自滅能力でも候補から除き、次点以降で埋める。
        scores = [6, 5, 4, 3, 2, 7, 1]
        self.assertEqual(
            bc_search._candidate_actions(
                scores, 7, got, "enforce", {}, forbidden_actions={(5,)},
            ),
            [[0], [1], [2], [3], [4]],
        )
        self.assertEqual(
            bc_search._candidate_actions(scores, 7, got, "shadow", {}),
            [[5], [0], [1], [2], [3]],
        )

        mine["bench"] = [pokemon(305)]
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ005_SOLE_DUDUN_GUARD"],
        ), [])

    def test_sole_dudunsparce_guard_requires_cards_to_draw(self):
        mine = player(active=[pokemon(66)], bench=[], deck_count=0)
        obs = observation([
            {"type": 10, "area": 4, "index": 0},
            {"type": 14},
        ], mine=mine)
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ005_SOLE_DUDUN_GUARD"],
        ), [])

    def test_sole_dudunsparce_guard_requires_a_legal_end_action(self):
        mine = player(active=[pokemon(66)], bench=[], deck_count=1)
        ability = {"type": 10, "area": 4, "index": 0}
        obs = observation([ability], mine=mine)
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ005_SOLE_DUDUN_GUARD"],
        ), [])

        obs["select"]["option"].append({"type": 14})
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ005_SOLE_DUDUN_GUARD"],
        )
        self.assertEqual((got[0].action, got[0].kind), ((0,), "forbid"))

    def test_multiple_blockers_with_enough_hammers_propose_exact_ko_chain(self):
        mine = player(
            hand=[1081, 1081],
            active=[pokemon(743, energies=[5], energy_cards=[{"id": 19}])],
        )
        mine["handCount"] = 20
        opp = player(active=[pokemon(
            879, energy_cards=[{"id": 11}, {"id": 11}, {"id": 19}],
        )])
        opp["active"][0]["hp"] = 140
        obs = observation([
            {"type": 7, "area": 2, "index": 0},
            {"type": 7, "area": 2, "index": 1},
            {"type": 13, "attackId": 1072},
        ], mine=mine, opp=opp)
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ006_UNBLOCK_EXACT_KO"],
        )
        self.assertEqual((got[0].action, got[0].kind), ((0,), "candidate"))

        # Hammerが1枚しかなければMist2枚を全て剥がせず、証明条件を満たさない。
        obs["select"]["option"].pop(1)
        mine["hand"] = mine["hand"][:1]
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ006_UNBLOCK_EXACT_KO"],
        ), [])

    def test_zero_deck_sacred_ash_proposes_all_eligible_cards(self):
        mine = player(active=[pokemon(742)], deck_count=0)
        options = [
            {"type": 3, "area": 3, "index": 8, "playerIndex": 0},
            {"type": 3, "area": 3, "index": 16, "playerIndex": 0},
            {"type": 3, "area": 3, "index": 24, "playerIndex": 0},
        ]
        obs = observation(
            options, mine=mine, select_type=1, effect={"id": 1129}, max_count=3,
        )
        obs["select"]["context"] = 9
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ007_ASH_ZERO_DECK_MAX"],
        )
        self.assertEqual((got[0].action, got[0].kind), ((0, 1, 2), "hard"))

        obs["select"]["option"].append(
            {"type": 3, "area": 3, "index": 25, "playerIndex": 0},
        )
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ007_ASH_ZERO_DECK_MAX"],
        ), [])

    def test_dudunsparce_draw_that_reaches_exact_ko_is_candidate(self):
        mine = player(
            active=[pokemon(743, energies=[5])],
            bench=[pokemon(66), pokemon(66), pokemon(305)],
            deck_count=18,
        )
        mine["handCount"] = 13
        opp = player(active=[pokemon(121)])
        opp["active"][0]["hp"] = 320
        obs = observation([
            {"type": 10, "area": 5, "index": 0},
            {"type": 10, "area": 5, "index": 1},
            {"type": 13, "attackId": 1072},
        ], mine=mine, opp=opp)
        got = rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ008_DRAW_TO_EXACT_KO"],
        )
        self.assertEqual((got[0].action, got[0].kind), ((0,), "candidate"))

        opp["active"][0]["energyCards"] = [{"id": 11}]
        self.assertEqual(rules.evaluate(
            obs, ALAKAZAM_DECK, "alakazam_v1", ["AZ008_DRAW_TO_EXACT_KO"],
        ), [])

    def test_wrong_profile_or_deck_is_non_firing(self):
        obs = observation([{"type": 14}])
        self.assertEqual(rules.evaluate(obs, ALAKAZAM_DECK, "unknown", ()), [])
        self.assertEqual(rules.evaluate(obs, [1] * 60, "alakazam_v1", ()), [])

    def test_hard_conflict_falls_back(self):
        a = rules.RuleProposal("a", (0,), 10, "hard", "a")
        b = rules.RuleProposal("b", (1,), 20, "hard", "b")
        self.assertIsNone(rules.best_hard([a, b]))
        same = rules.RuleProposal("c", (0,), 20, "hard", "c")
        self.assertEqual(rules.best_hard([a, same]), same)

    def test_candidate_pool_keeps_top1_and_constant_size(self):
        proposal = rules.RuleProposal("AZ_TEST", (6,), 100, "candidate", "test")
        metrics = {}
        got = bc_search._candidate_actions(
            [7, 6, 5, 4, 3, 2, 1], 7, [proposal], "candidate", metrics,
        )
        self.assertEqual(got, [[0], [6], [1], [2], [3]])
        self.assertEqual(metrics["expert_rule_outside_topk.AZ_TEST"], 1)
        self.assertEqual(metrics["expert_rule_injected.AZ_TEST"], 1)
        self.assertEqual(
            bc_search._candidate_actions(
                [7, 6, 5, 4, 3, 2, 1], 7, [proposal], "shadow", {},
            ),
            [[0], [1], [2], [3], [4]],
        )

    def test_candidate_pool_rejects_invalid_rule_action(self):
        proposal = rules.RuleProposal("BAD", (-1,), 100, "candidate", "bad")
        metrics = {}
        got = bc_search._candidate_actions([3, 2, 1], 3, [proposal], "candidate", metrics)
        self.assertEqual(got, [[0], [1], [2]])
        self.assertEqual(metrics["expert_rule_invalid"], 1)


if __name__ == "__main__":
    unittest.main()
