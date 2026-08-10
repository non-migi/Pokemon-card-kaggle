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

CARD_INFO = guard.build_card_info(heuristics.CARDS, heuristics.ATTACKS)

IMPIDIMP, MORGREM, GRIMMSNARL = 646, 647, 648
SNORUNT, MUNKIDORI = 860, 112
OGERPON, LOPUNNY = 96, 849

ALL_RULES = guard.GuardConfig(guard.KNOWN_RULE_IDS)
ALL_RULES_DEFAULT = guard.GuardConfig(guard.DEFAULT_RULE_IDS)


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


class MetricsResetMixin:
    """モジュールカウンタは全テストで独立させる。"""

    def setUp(self):
        super().setUp()
        guard.reset_metrics()


class DamageModelTest(MetricsResetMixin, unittest.TestCase):
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


class SwitchGuardTest(MetricsResetMixin, unittest.TestCase):
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
        """(c) 相手にOgerpon/Lopunnyが居なければ完全にno-op。"""
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(MUNKIDORI, energies=5)])
        obs = observation(switch_select(2), mine, opp)
        metrics = {}
        self.assertEqual(run(obs, metrics=metrics), frozenset())
        # 「評価はした が 発火しなかった」ことが後から区別できること。
        self.assertEqual(metrics["ohko_guard_calls"], 1)
        self.assertEqual(metrics["ohko_guard_scanned.switch"], 1)
        self.assertNotIn("ohko_guard_fired", metrics)
        self.assertEqual(guard.METRICS["ohko_guard_calls"], 1)

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


class AllDeadAttackerTest(MetricsResetMixin, unittest.TestCase):
    """GR003: 全候補が一撃死圏なら、攻撃できる候補を優先する(ep 90471729)。"""

    def _board(self, impidimp_energies=0, munkidori_energies=2):
        mine = player(bench=[
            pokemon(IMPIDIMP, energies=impidimp_energies),
            pokemon(MUNKIDORI, energies=munkidori_energies, energy_type=5),
        ])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        return observation(switch_select(2), mine, opp)

    def test_forbids_the_unarmed_candidate_when_everyone_dies(self):
        metrics = {}
        # Impidimp 70 <- 240 / Munkidori 110 <- 180。両方死ぬ・両方サイド1枚。
        self.assertEqual(run(self._board(), metrics=metrics), frozenset({(0,)}))
        self.assertEqual(metrics[f"ohko_guard_hit.{guard.RULE_ATTACKER}"], 1)
        self.assertEqual(metrics["ohko_guard_options_forbidden"], 1)

    def test_no_fire_when_both_can_attack(self):
        # Impidimpに闘えるenergyが付いていれば介入しない。
        self.assertEqual(run(self._board(impidimp_energies=1)), frozenset())

    def test_no_fire_when_nobody_can_attack(self):
        self.assertEqual(run(self._board(munkidori_energies=1)), frozenset())

    def test_disabled_rule_leaves_the_choice_to_bc(self):
        only_switch = guard.GuardConfig((guard.RULE_SWITCH,))
        self.assertEqual(run(self._board(), cfg=only_switch), frozenset())

    def test_prize_beats_attack_capability(self):
        # 攻撃できるGrimmsnarl exより、攻撃できないSnoruntを出す(サイド優先)。
        mine = player(bench=[
            pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT),
        ])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        self.assertEqual(run(obs), frozenset({(0,)}))

    def test_all_dead_never_forbids_every_option(self):
        mine = player(bench=[
            pokemon(IMPIDIMP), pokemon(IMPIDIMP),
            pokemon(MUNKIDORI, energies=2, energy_type=5),
        ])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        got = run(observation(switch_select(3), mine, opp))
        self.assertEqual(got, frozenset({(0,), (1,)}))


GRIM_DECK = [int(line) for line in open(
    os.path.join(ROOT, "decks/meta/snapshot_20260723_grim_top8.csv"),
) if line.strip()][:60]
GRIM_LINE_BASES = guard.build_line_bases(GRIM_DECK, heuristics.CARDS)


class LineBaseTest(unittest.TestCase):
    def test_grim_deck_line_bases(self):
        # Morgrem/Grimmsnarl exの進化元と、Froslassの進化元だけが基点。
        self.assertEqual(sorted(GRIM_LINE_BASES), [IMPIDIMP, MORGREM, SNORUNT])
        self.assertNotIn(MUNKIDORI, GRIM_LINE_BASES)   # 余り駒
        self.assertNotIn(GRIMMSNARL, GRIM_LINE_BASES)  # 進化先が無い

    def test_alakazam_deck_line_bases(self):
        deck = [741] * 4 + [742] * 4 + [743] * 4 + [305] * 24 + [66] * 24
        self.assertEqual(
            sorted(guard.build_line_bases(deck, heuristics.CARDS)),
            [305, 741, 742],
        )

    def test_bad_deck_is_empty(self):
        self.assertEqual(guard.build_line_bases([], heuristics.CARDS), frozenset())
        self.assertEqual(
            guard.build_line_bases(["x"], heuristics.CARDS), frozenset(),
        )


class PreserveLineTest(MetricsResetMixin, unittest.TestCase):
    """GR004: 全候補が一撃死圏・サイド同値なら、ライン基点ではなく余り駒を出す。"""

    ONLY_LINE = guard.GuardConfig((guard.RULE_LINE,))

    def _run(self, obs, cfg=None):
        return guard.forbidden_actions(
            cfg or self.ONLY_LINE, obs, CARD_INFO, None, GRIM_LINE_BASES,
        )

    def _board(self, munkidori_hp=110):
        # ep 90471729 相当: 相手はエネ2のMega Lopunny ex(Spiky Hopper 160)。
        mine = player(bench=[
            pokemon(IMPIDIMP), pokemon(MUNKIDORI, hp=munkidori_hp),
        ])
        opp = player(active=[pokemon(LOPUNNY, energies=2, energy_type=0)])
        return observation(switch_select(2), mine, opp)

    def test_forbids_the_line_base_when_a_spare_exists(self):
        # Impidimp 70 も Munkidori 110 も 160 で落ちる。サイドはどちらも1枚。
        self.assertEqual(self._run(self._board()), frozenset({(0,)}))

    def test_no_fire_when_nobody_dies(self):
        mine = player(bench=[pokemon(IMPIDIMP), pokemon(MUNKIDORI)])
        opp = player(active=[pokemon(LOPUNNY, energies=1, energy_type=0)])
        self.assertEqual(self._run(observation(switch_select(2), mine, opp)),
                         frozenset())

    def test_no_fire_when_every_candidate_is_a_line_base(self):
        mine = player(bench=[pokemon(IMPIDIMP), pokemon(SNORUNT)])
        opp = player(active=[pokemon(LOPUNNY, energies=2, energy_type=0)])
        self.assertEqual(self._run(observation(switch_select(2), mine, opp)),
                         frozenset())

    def test_disabled_by_default(self):
        self.assertNotIn(guard.RULE_LINE, guard.DEFAULT_RULE_IDS)
        self.assertEqual(self._run(self._board(), cfg=ALL_RULES_DEFAULT),
                         frozenset())

    def test_line_bases_must_be_supplied(self):
        # main.py が LINE_BASES を渡し忘れたら発火しない(誤爆しない側に倒す)。
        self.assertEqual(
            guard.forbidden_actions(self.ONLY_LINE, self._board(), CARD_INFO),
            frozenset(),
        )

    def test_prize_takes_priority_over_line_preservation(self):
        # サイド2枚のGrimmsnarl exが死ぬなら、ライン基点のImpidimpを差し出す。
        mine = player(bench=[
            pokemon(GRIMMSNARL, hp=150), pokemon(IMPIDIMP),
        ])
        opp = player(active=[pokemon(LOPUNNY, energies=2, energy_type=0)])
        obs = observation(switch_select(2), mine, opp)
        both = guard.GuardConfig((guard.RULE_SWITCH, guard.RULE_LINE))
        self.assertEqual(self._run(obs, cfg=both), frozenset({(0,)}))

    def test_line_and_attacker_rules_do_not_deadlock(self):
        # ライン基点だが攻撃できるImpidimp vs 余り駒だが攻撃できないMunkidori。
        # 別々の比較なら相互に禁止し合って全滅するが、辞書式キーなので
        # 「ライン温存」が優先され、Munkidoriだけが残る。
        mine = player(bench=[
            pokemon(IMPIDIMP, energies=1),
            pokemon(MUNKIDORI, energies=2, energy_type=7),
        ])
        opp = player(active=[pokemon(LOPUNNY, energies=2, energy_type=0)])
        obs = observation(switch_select(2), mine, opp)
        both = guard.GuardConfig((guard.RULE_LINE, guard.RULE_ATTACKER))
        got = self._run(obs, cfg=both)
        self.assertEqual(got, frozenset({(0,)}))
        self.assertLess(len(got), 2)


class CanAttackTest(unittest.TestCase):
    def test_cost_payment(self):
        # Munkidori Mind Bend {P}{C}
        info = CARD_INFO[MUNKIDORI]
        self.assertEqual(info["attack_costs"], ((5, 0),))
        self.assertFalse(guard.can_attack({"energies": [5]}, info))
        self.assertTrue(guard.can_attack({"energies": [5, 7]}, info))
        self.assertFalse(guard.can_attack({"energies": [7, 7]}, info))

    def test_zero_damage_attack_does_not_count(self):
        # Impidimp: Filch(0ダメージ,{C}) は数えず、Corkscrew Punch({D})だけ。
        info = CARD_INFO[IMPIDIMP]
        self.assertEqual(info["attack_costs"], ((7,),))
        self.assertFalse(guard.can_attack({"energies": [0]}, info))
        self.assertTrue(guard.can_attack({"energies": [7]}, info))

    def test_wildcard_energy_pays_any_cost(self):
        info = CARD_INFO[MUNKIDORI]
        self.assertTrue(guard.can_attack({"energies": [10, 10]}, info))

    def test_missing_attack_data_defaults_to_attackable(self):
        self.assertTrue(guard.can_attack({"energies": []}, {}))


class EvolveGuardTest(MetricsResetMixin, unittest.TestCase):
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


class ConfigTest(MetricsResetMixin, unittest.TestCase):
    def test_absent_config_is_disabled(self):
        self.assertIsNone(guard.from_config({}))
        self.assertIsNone(guard.from_config({"algo": "bc"}))
        self.assertIsNone(guard.from_config({"ohko_guard": False}))
        self.assertIsNone(guard.from_config({"ohko_guard": {"enabled": False}}))

    def test_true_enables_the_default_rules_only(self):
        # GR003/GR004はどちらも反証済みで恒久的に既定外(docstring参照)。
        # 特にGR004は壁A/Bで-4.0pt(唯一CIが分離した差)。ここが赤くなったら
        # 「反証済みruleが既定へ戻された」ということなので、根拠を確認すること。
        for raw in (True, {"enabled": True}):
            cfg = guard.from_config({"ohko_guard": raw})
            self.assertEqual(cfg.rule_ids, guard.DEFAULT_RULE_IDS)
            self.assertFalse(cfg.enabled(guard.RULE_ATTACKER))
        self.assertEqual(
            guard.DEFAULT_RULE_IDS, (guard.RULE_SWITCH, guard.RULE_EVOLVE),
        )

    def test_gr003_is_opt_in(self):
        cfg = guard.from_config(
            {"ohko_guard": {"rules": [guard.RULE_ATTACKER]}},
        )
        self.assertTrue(cfg.enabled(guard.RULE_ATTACKER))
        self.assertFalse(cfg.enabled(guard.RULE_SWITCH))

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
        """(e) ガード未指定なら評価すらせず、カウンタも1つも動かない。"""
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        obs = observation(switch_select(2), mine, opp)
        metrics = {}
        self.assertEqual(
            guard.forbidden_actions(None, obs, CARD_INFO, metrics), frozenset(),
        )
        self.assertEqual(metrics, {})
        self.assertEqual(guard.METRICS, {})


class FailureFallbackTest(MetricsResetMixin, unittest.TestCase):
    """(d) ルール内のどんな例外もBC選択へ落とし、カウンタに残す。"""

    def _obs(self):
        mine = player(bench=[pokemon(GRIMMSNARL, energies=5), pokemon(SNORUNT)])
        opp = player(active=[pokemon(OGERPON, energies=3, energy_type=1)])
        return observation(switch_select(2), mine, opp)

    def test_broken_card_info_falls_back(self):
        class Exploding(dict):
            def get(self, *_args, **_kwargs):
                raise RuntimeError("boom")

        metrics = {}
        got = guard.forbidden_actions(
            ALL_RULES, self._obs(), Exploding(), metrics,
        )
        self.assertEqual(got, frozenset())
        self.assertEqual(metrics["ohko_guard_errors"], 1)
        self.assertEqual(metrics["ohko_guard_calls"], 1)
        self.assertEqual(guard.METRICS["ohko_guard_errors"], 1)

    def test_malformed_observation_is_not_fatal(self):
        for bad in ({}, {"select": None}, {"select": {"option": None}},
                    {"select": {"maxCount": 1, "minCount": 1,
                                "option": [{}, {}], "type": guard.ST_CARD,
                                "context": guard.CTX_TO_ACTIVE}}):
            self.assertEqual(
                guard.forbidden_actions(ALL_RULES, bad, CARD_INFO, {}),
                frozenset(),
            )
        self.assertNotIn("ohko_guard_fired", guard.METRICS)

    def test_metrics_accumulate_across_calls(self):
        for _ in range(3):
            run(self._obs())
        self.assertEqual(guard.METRICS["ohko_guard_calls"], 3)
        self.assertEqual(guard.METRICS["ohko_guard_fired"], 3)
        guard.reset_metrics()
        self.assertEqual(guard.METRICS, {})


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
