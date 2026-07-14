import json
import os
import tempfile
import unittest
from unittest import mock

from ptcglab import arena
from ptcglab import build as build_module


class ArenaUnitTests(unittest.TestCase):
    def test_match_count_must_be_positive_and_even(self):
        for n in (0, -2, 1, 3):
            with self.subTest(n=n), self.assertRaises(ValueError):
                arena.run_match_series("random", "first", n=n)

    def test_summary_keeps_separate_wins_draws_losses_and_unscored(self):
        rows = [
            {"reward": 1, "score": 1.0},
            {"reward": 0, "score": 0.5},
            {"reward": -1, "score": 0.0},
            {"reward": None, "score": 0.0},
        ]
        got = arena._summarize(rows)
        self.assertEqual((got["wins"], got["draws"], got["losses"], got["unscored"]),
                         (1, 1, 1, 1))
        self.assertEqual(got["score_rate"], 0.375)

    def test_production_search_rejects_parallel_jobs(self):
        meta = {"config": {"algo": "bcs", "max_move_sec": 8.0}}
        with self.assertRaises(ValueError):
            arena._resolve_profile(meta, {"config": {}}, jobs=2, requested="auto")
        self.assertEqual(arena._resolve_profile(meta, {"config": {}}, jobs=1,
                                                requested="auto"), "production")

    def test_profile_cannot_override_agent_configuration(self):
        production = {"config": {"algo": "bcs", "max_move_sec": 8.0}}
        fixed = {"config": {"algo": "bcs", "fixed_search_worlds": 2}}
        plain = {"config": {"algo": "bc"}}
        with self.assertRaises(ValueError):
            arena._resolve_profile(production, plain, jobs=8, requested="standard")
        with self.assertRaises(ValueError):
            arena._resolve_profile(fixed, plain, jobs=1, requested="production")
        with self.assertRaises(ValueError):
            arena._resolve_profile(production, fixed, jobs=1, requested="auto")

    def test_fixed_worlds_requires_matching_values(self):
        a = {"config": {"algo": "bcs", "fixed_search_worlds": 4}}
        b = {"config": {"algo": "bcs", "fixed_search_worlds": 8}}
        with self.assertRaises(ValueError):
            arena._resolve_profile(a, b, jobs=2, requested="fixed-worlds")

    def test_seat_pair_alternates_execution_order(self):
        with mock.patch.object(arena, "_play", side_effect=lambda swap: swap):
            self.assertEqual(arena._play_seat_pair(0), [False, True])
            self.assertEqual(arena._play_seat_pair(1), [True, False])

    def test_fingerprint_ignores_pycache_but_covers_config(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "main.py"), "w") as f:
                f.write("def agent(obs): return []\n")
            with open(os.path.join(d, "agent_config.json"), "w") as f:
                json.dump({"algo": "bc"}, f)
            before = arena.agent_fingerprint(d)["sha256"]
            os.makedirs(os.path.join(d, "__pycache__"))
            with open(os.path.join(d, "__pycache__", "main.pyc"), "wb") as f:
                f.write(b"ignored")
            self.assertEqual(before, arena.agent_fingerprint(d)["sha256"])
            with open(os.path.join(d, "agent_config.json"), "w") as f:
                json.dump({"algo": "bcs"}, f)
            self.assertNotEqual(before, arena.agent_fingerprint(d)["sha256"])

    def test_gauntlet_dry_run_does_not_start_games(self):
        got = arena.run_gauntlet(
            "random", ["first"], n=2, jobs=1, profile="standard", dry_run=True,
        )
        self.assertEqual(got["status"], "dry-run")
        self.assertEqual(got["total_games"], 2)

    def test_build_removes_host_bytecode_before_packaging(self):
        with tempfile.TemporaryDirectory() as d:
            cache = os.path.join(d, "pkg", "__pycache__")
            os.makedirs(cache)
            with open(os.path.join(cache, "mod.cpython-312.pyc"), "wb") as f:
                f.write(b"host bytecode")
            with open(os.path.join(d, "keep.py"), "w") as f:
                f.write("pass\n")
            build_module._remove_bytecode(d)
            self.assertFalse(os.path.exists(cache))
            self.assertTrue(os.path.isfile(os.path.join(d, "keep.py")))


if __name__ == "__main__":
    unittest.main()
