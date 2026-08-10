"""一撃死コミット回避(GR001/GR002)の合成盤面テスト。

発火 / 非発火 / 全禁止の安全網 / 設定 / BCマスクの5系統を確認する。
実カードデータ(cg)を使うので、打点式(Ogerpon エネ×30、弱点×2、Lopunny 230)が
実際のカードテキストとずれたらここで落ちる。
"""

import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ptcg import heuristics  # noqa: E402
from ptcg import ohko_guard as guard  # noqa: E402
from ptcg import policy  # noqa: E402

CARD_INFO = guard.build_card_info(heuristics.CARDS)

IMPIDIMP, MORGREM, GRIMMSNARL = 646, 647, 648
SNORUNT, MUNKIDORI = 860, 112
OGERPON, LOPUNNY = 96, 849

ALL_RULES = guard.GuardConfig(guard.KNOWN_RULE_IDS)


def pokemon(card_id, hp=None, energies=0, max_hp=None, energy_type=7):
    printed = int(CARD_INFO.get(card_id, {}).get("max_hp", 0))
    return {
        "id": card_id,
        "hp": printed if hp is None else hp,
        "maxHp": printed if max_hp is None else max_hp,
        "energies": [energy_type] * energies,
        "energyCards": [],
        "tools": [],
        "preEvolution": [],
    }


def player(active=None, bench=None, hand=None):
    return {
        "active": list(active or []),
        "bench": list(bench or []),
        "benchMax": 5,
        "deckCount": 30,
        "discard": [],
        "prize": [None] * 6,
        "hand": [{"id": cid} for cid in hand] if hand is not None else None,
        "handCount": len(hand or []),
        "asleep": False,
        "burned": False,
        "confused": False,
        "paralyzed": False,
        "poisoned": False,
    }


def observation(sel, mine, opp, your_index=0):
    players = [mine, opp] if your_index == 0 else [opp, mine]
    return {
        "select": sel,
        "current": {"yourIndex": your_index, "players": players, "turn": 5},
    }


def switch_select(bench_count, context=guard.CTX_TO_ACTIVE, player_index=0):
    return {
        "type": guard.ST_CARD,
        "context": context,
        "minCount": 1,
        "maxCount": 1,
        "option": [
            {"type": guard.OT_CARD, "area": guard.AR_BENCH,
             "playerIndex": player_index, "index": i}
            for i in range(bench_count)
        ],
    }


def main_select(options):
    return {
        "type": guard.ST_MAIN, "context": 0,
        "minCount": 1, "maxCount": 1, "option": list(options),
    }


def evolve_option(hand_index, in_play_area=guard.AR_ACTIVE, in_play_index=0):
    return {
        "type": guard.OT_EVOLVE, "area": guard.AR_HAND, "index": hand_index,
        "inPlayArea": in_play_area, "inPlayIndex": in_play_index,
    }


def run(obs, cfg=ALL_RULES, metrics=None):
    return guard.forbidden_actions(cfg, obs, CARD_INFO, metrics)


class DamageModelTest(unittest.TestCase):
    def test_ogerpon_counts_both_actives_and_weakness(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        # 30 + 30*(3+5) = 270、Grimmsnarlは草弱点なので×2
        self.assertEqual(
            guard.max_incoming_damage(opp, 1, 5, CARD_INFO), 540,
        )
        # 弱点なし(鋼弱点のSnorunt)は等倍
        self.assertEqual(
            guard.max_incoming_damage(opp, 8, 0, CARD_INFO), 120,
        )

    def test_ogerpon_without_attack_cost_is_no_threat(self):
        opp = player(active=[pokemon(OGERPON, energies=2, energy_type=1)])
        self.assertEqual(guard.max_incoming_damage(opp, 1, 5, CARD_INFO), 0)

    def test_lopunny_bench_is_230_active_is_capped(self):
        bench = player(
            active=[pokemon(MUNKIDORI)],
            bench=[pokemon(LOPUNNY, energies=1, energy_type=0)],
        )
        self.assertEqual(guard.max_incoming_damage(bench, 1, 0, CARD_INFO), 230)
        active2 = player(active=[pokemon(LOPUNNY, energies=2, energy_type=0)])
        self.assertEqual(guard.max_incoming_damage(active2, 1, 0, CARD_INFO), 160)
        active1 = player(active=[pokemon(LOPUNNY, energies=1, energy_type=0)])
        self.assertEqual(guard.max_incoming_damage(active1, 1, 0, CARD_INFO), 60)
        active0 = player(active=[pokemon(LOPUNNY, energies=0, energy_type=0)])
        self.assertEqual(guard.max_incoming_damage(active0, 1, 0, CARD_INFO), 0)

    def test_unknown_opponent_pokemon_is_no_threat(self):
        opp = player(active=[pokemon(MUNKIDORI, energies=5)])
        self.assertEqual(guard.max_incoming_damage(opp, 1, 5, CARD_INFO), 0)


class SwitchGuardTest(unittest.TestCase):
    def test_forbids_dying_ex_when_cheaper_sacrifice_exists(self):
        mine = player(
            bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)],
        )
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        metrics = {}
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs, metrics=metrics), frozenset({(0,)}))
        self.assertEqual(metrics[f"ohko_guard_hit.{guard.RULE_SWITCH}"], 1)

    def test_forbids_dying_ex_against_benched_lopunny(self):
        mine = player(
            bench=[pokemon(GRIMMSNARL, hp=200), pokemon(SNORUNT)],
        )
        opp = player(
            active=[pokemon(MUNKIDORI)],
            bench=[pokemon(LOPUNNY, energies=1, energy_type=0)],
        )
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset({(0,)}))

    def test_switch_context_also_guarded(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2, context=guard.CTX_SWITCH), mine, opp)
        self.assertEqual(run(obs), frozenset({(0,)}))

    def test_no_fire_when_only_cheap_pokemon_dies(self):
        # Snorunt(1枚)が死に、生き残るのは2枚取られるGrimmsnarl。最小介入としてBCに任せる。
        mine = player(bench=[pokemon(GRIMMSNARL), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset())

    def test_no_fire_when_all_candidates_are_equally_cheap(self):
        mine = player(bench=[pokemon(IMPIDIMP), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset())

    def test_no_fire_without_known_threat(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(MUNKIDORI, energies=5)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset())

    def test_opponent_bench_target_is_non_firing(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(
            active=[pokemon(OGERPON, energies=3, energy_type=1)],
            bench=[pokemon(MUNKIDORI), pokemon(SNORUNT)],
        )
        obs = observation(switch_select(2, player_index=1), mine, opp)
        self.assertEqual(run(obs), frozenset())

    def test_unknown_card_on_bench_is_non_firing(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        mine["bench"][1]["id"] = 10 ** 7
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset())

    def test_seat_one_is_handled(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2, player_index=1), mine, opp, your_index=1)
        self.assertEqual(run(obs), frozenset({(0,)}))

    def test_never_forbids_every_option(self):
        # 3体とも死ぬ状況でも、最も安い候補は必ず残る。
        mine = player(bench=[
            pokemon(GRIMMSNARL, energies=5), pokemon(GRIMMSNARL, energies=5),
            pokemon(SNORUNT),
        ])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(3), mine, opp)
        got = run(obs)
        self.assertEqual(got, frozenset({(0,), (1,)}))
        self.assertLess(len(got), 3)

    def test_multi_select_is_non_firing(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        sel = switch_select(2)
        sel["maxCount"] = 2
        self.assertEqual(run(observation(sel, mine, opp)), frozenset())


class EvolveGuardTest(unittest.TestCase):
    def _obs(self, active, hand, opp, options=None):
        mine = player(active=[active], bench=[pokemon(SNORUNT)], hand=hand)
        sel = main_select(options or [evolve_option(0), {"type": 14}])
        return observation(sel, mine, opp)

    def test_forbids_evolving_active_into_ohko_range(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = self._obs(pokemon(MORGREM, energies=2), [GRIMMSNARL], opp)
        metrics = {}
        self.assertEqual(run(obs, metrics=metrics), frozenset({(0,)}))
        self.assertEqual(metrics[f"ohko_guard_hit.{guard.RULE_EVOLVE}"], 1)

    def test_no_fire_when_evolution_survives(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = self._obs(pokemon(MORGREM, energies=0), [GRIMMSNARL], opp)
        self.assertEqual(run(obs), frozenset())

    def test_carries_existing_damage_into_the_estimate(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        # 被ダメ240。320-60=260 は耐える / 320-80=240 は一撃死。
        survives = self._obs(pokemon(MORGREM, hp=40), [GRIMMSNARL], opp)
        self.assertEqual(run(survives), frozenset())
        dies = self._obs(pokemon(MORGREM, hp=20), [GRIMMSNARL], opp)
        self.assertEqual(run(dies), frozenset({(0,)}))

    def test_bench_evolution_is_never_forbidden(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = self._obs(
            pokemon(MORGREM, energies=2), [GRIMMSNARL],
            opp, options=[
                evolve_option(0, in_play_area=guard.AR_BENCH), {"type": 14},
            ],
        )
        self.assertEqual(run(obs), frozenset())

    def test_same_prize_evolution_is_not_forbidden(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = self._obs(pokemon(IMPIDIMP, energies=2), [MORGREM], opp)
        self.assertEqual(run(obs), frozenset())

    def test_forced_evolve_select_is_guarded(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        mine = player(
            active=[pokemon(MORGREM, energies=2)],
            bench=[pokemon(IMPIDIMP)], hand=[GRIMMSNARL],
        )
        sel = {
            "type": guard.ST_EVOLVE, "context": guard.CTX_EVOLVE,
            "minCount": 1, "maxCount": 1,
            "option": [
                evolve_option(0),
                evolve_option(0, in_play_area=guard.AR_BENCH),
            ],
        }
        self.assertEqual(run(observation(sel, mine, opp)), frozenset({(0,)}))

    def test_suppressed_when_every_option_would_be_forbidden(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        mine = player(
            active=[pokemon(MORGREM, energies=2)], bench=[],
            hand=[GRIMMSNARL, GRIMMSNARL],
        )
        sel = {
            "type": guard.ST_EVOLVE, "context": guard.CTX_EVOLVE,
            "minCount": 1, "maxCount": 1,
            "option": [evolve_option(0), evolve_option(1)],
        }
        metrics = {}
        self.assertEqual(
            run(observation(sel, mine, opp), metrics=metrics), frozenset(),
        )
        self.assertEqual(metrics["ohko_guard_suppressed"], 1)

    def test_hidden_hand_is_non_firing(self):
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        mine = player(active=[pokemon(MORGREM, energies=2)], hand=None)
        sel = main_select([evolve_option(0), {"type": 14}])
        self.assertEqual(run(observation(sel, mine, opp)), frozenset())


class ConfigTest(unittest.TestCase):
    def test_absent_config_is_disabled(self):
        self.assertIsNone(guard.from_config({}))
        self.assertIsNone(guard.from_config({"algo": "bc"}))
        self.assertIsNone(guard.from_config({"ohko_guard": False}))
        self.assertIsNone(guard.from_config({"ohko_guard": {"enabled": False}}))

    def test_true_enables_every_rule(self):
        cfg = guard.from_config({"ohko_guard": True})
        self.assertEqual(cfg.rule_ids, guard.KNOWN_RULE_IDS)

    def test_rule_subset(self):
        cfg = guard.from_config(
            {"ohko_guard": {"rules": [guard.RULE_SWITCH]}},
        )
        self.assertTrue(cfg.enabled(guard.RULE_SWITCH))
        self.assertFalse(cfg.enabled(guard.RULE_EVOLVE))

    def test_bad_config_raises(self):
        for bad in (
            {"ohko_guard": 1},
            {"ohko_guard": {"rules": "GR001_OHKO_COMMIT_AVOID"}},
            {"ohko_guard": {"rules": []}},
            {"ohko_guard": {"rules": ["NOPE"]}},
            {"ohko_guard": {"rules": [guard.RULE_SWITCH, guard.RULE_SWITCH]}},
        ):
            with self.assertRaises(ValueError):
                guard.from_config(bad)

    def test_disabled_rule_does_not_fire(self):
        only_evolve = guard.GuardConfig((guard.RULE_EVOLVE,))
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs, cfg=only_evolve), frozenset())

        only_switch = guard.GuardConfig((guard.RULE_SWITCH,))
        opp2 = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        mine2 = player(
            active=[pokemon(MORGREM, energies=2)],
            bench=[pokemon(SNORUNT)], hand=[GRIMMSNARL],
        )
        obs2 = observation(
            main_select([evolve_option(0), {"type": 14}]), mine2, opp2,
        )
        self.assertEqual(run(obs2, cfg=only_switch), frozenset())

    def test_none_config_is_total_no_op(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(
            guard.forbidden_actions(None, obs, CARD_INFO, {}), frozenset(),
        )


class PolicyExcludeTest(unittest.TestCase):
    """policy.choose(exclude=...)。空なら従来と完全に同一であること。"""

    def setUp(self):
        self._enabled, self._scores = policy.ENABLED, policy._raw_scores
        self.obs = {
            "select": {"minCount": 1, "maxCount": 1, "option": [{}, {}, {}]},
            "current": {"yourIndex": 0},
        }
        policy.ENABLED = True
        policy._raw_scores = lambda sel, cur, opts: np.array([0.1, 0.9, 0.5])

    def tearDown(self):
        policy.ENABLED, policy._raw_scores = self._enabled, self._scores

    def test_empty_exclude_matches_argmax(self):
        self.assertEqual(policy.choose(self.obs), [1])
        self.assertEqual(policy.choose(self.obs, exclude=()), [1])
        self.assertEqual(policy.choose(self.obs, exclude=frozenset()), [1])

    def test_exclude_picks_next_best(self):
        self.assertEqual(policy.choose(self.obs, exclude={(1,)}), [2])
        self.assertEqual(policy.choose(self.obs, exclude={(1,), (2,)}), [0])

    def test_all_excluded_returns_none(self):
        self.assertIsNone(
            policy.choose(self.obs, exclude={(0,), (1,), (2,)}),
        )

    def test_multi_select_ignores_exclude(self):
        self.obs["select"]["maxCount"] = 2
        self.obs["select"]["minCount"] = 2
        self.assertEqual(policy.choose(self.obs, exclude={(1,)}), [1, 2])


if __name__ == "__main__":
    unittest.main()
