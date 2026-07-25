"""探索の未決着評価に入れた山札レース項のテスト。

既定(重み0)で従来の評価と**完全一致**することを固定するのが主目的。
本番533戦の19.3%が山札切れ決着なのに、従来はサイド差しか見ていなかった。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ptcg import bc_search  # noqa: E402
from ptcglab import build  # noqa: E402


def state(my_prize, opp_prize, my_deck, opp_deck, my_index=0, result=-1):
    players = [None, None]
    players[my_index] = {"prize": [None] * my_prize, "deckCount": my_deck}
    players[1 - my_index] = {"prize": [None] * opp_prize, "deckCount": opp_deck}
    return {"result": result, "players": players}


class DeckRaceTermTest(unittest.TestCase):
    def setUp(self):
        self._saved = bc_search.DECK_RACE_WEIGHT
        self.addCleanup(setattr, bc_search, "DECK_RACE_WEIGHT", self._saved)

    def test_default_is_exactly_legacy(self):
        """既定(0)では山札を一切見ない = 旧実装と同値。"""
        bc_search.DECK_RACE_WEIGHT = 0.0
        for md, od in ((0, 40), (40, 0), (5, 5), (60, 60)):
            v = bc_search._terminal_value(state(3, 3, md, od), 0)
            self.assertAlmostEqual(v, 0.5, msg=f"deck {md}/{od} で既定値が動いた")

    def test_losing_deck_race_lowers_value(self):
        bc_search.DECK_RACE_WEIGHT = 0.01
        even = bc_search._terminal_value(state(3, 3, 10, 10), 0)
        behind = bc_search._terminal_value(state(3, 3, 3, 20), 0)   # 自分の山が薄い
        ahead = bc_search._terminal_value(state(3, 3, 20, 3), 0)
        self.assertLess(behind, even)
        self.assertGreater(ahead, even)

    def test_only_applies_in_danger_zone(self):
        """どちらも山札に余裕があるうちは効かせない(序盤のノイズ源にしない)。"""
        bc_search.DECK_RACE_WEIGHT = 0.01
        safe = bc_search._terminal_value(state(3, 3, 40, 20), 0)
        self.assertAlmostEqual(safe, 0.5)
        danger = bc_search._terminal_value(state(3, 3, 40, 10), 0)
        self.assertNotAlmostEqual(danger, 0.5)

    def test_capped(self):
        """山札差が極端でもサイド差を押し流さない。"""
        bc_search.DECK_RACE_WEIGHT = 0.01
        v = bc_search._terminal_value(state(3, 3, 0, 60), 0)
        self.assertGreaterEqual(v, 0.5 - bc_search.DECK_RACE_CAP - 1e-9)

    def test_terminal_results_unaffected(self):
        """決着済みの局面は山札項の影響を受けない。"""
        bc_search.DECK_RACE_WEIGHT = 0.05
        self.assertEqual(bc_search._terminal_value(state(3, 3, 0, 60, result=0), 0), 1.0)
        self.assertEqual(bc_search._terminal_value(state(3, 3, 60, 0, result=1), 0), 0.0)

    def test_seat_symmetry(self):
        bc_search.DECK_RACE_WEIGHT = 0.01
        a = bc_search._terminal_value(state(3, 3, 5, 15, my_index=0), 0)
        b = bc_search._terminal_value(state(3, 3, 5, 15, my_index=1), 1)
        self.assertAlmostEqual(a, b)

    def test_missing_deck_count_is_safe(self):
        bc_search.DECK_RACE_WEIGHT = 0.01
        s = state(3, 3, 5, 15)
        s["players"][0].pop("deckCount")
        self.assertAlmostEqual(bc_search._terminal_value(s, 0), 0.5)


class BuildValidationTest(unittest.TestCase):
    def _spec(self, **cfg):
        base = {"algo": "bcs"}
        base.update(cfg)
        return {"deck": "d.csv", "model": "bc_v2", "config": base}

    def test_valid_weight(self):
        build._validate_spec(self._spec(deck_race_weight=0.01), "x.json")

    def test_zero_allowed_on_pure_bc(self):
        build._validate_spec({"deck": "d.csv", "model": "bc_v2",
                              "config": {"algo": "bc", "deck_race_weight": 0.0}}, "x.json")

    def test_requires_bcs_when_nonzero(self):
        with self.assertRaises(ValueError):
            build._validate_spec({"deck": "d.csv", "model": "bc_v2",
                                  "config": {"algo": "bc", "deck_race_weight": 0.01}}, "x.json")

    def test_out_of_range(self):
        for bad in (-0.01, 0.5, "0.01", True):
            with self.assertRaises(ValueError):
                build._validate_spec(self._spec(deck_race_weight=bad), "x.json")


if __name__ == "__main__":
    unittest.main()
