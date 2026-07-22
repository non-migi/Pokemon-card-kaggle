import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from ptcglab import arena
from ptcglab import build as build_module


def _watchdog_test_rows(pair_index):
    rows = []
    swaps = (False, True) if pair_index % 2 == 0 else (True, False)
    for swap in swaps:
        rows.append({
            "a_seat": 1 if swap else 0,
            "reward": 1,
            "score": 1.0,
            "status_a": "DONE",
            "status_b": "DONE",
            "error_a": None,
            "error_b": None,
            "remaining_overage_sec_a": 600.0,
            "remaining_overage_sec_b": 600.0,
            "metrics_a": {},
            "metrics_b": {},
            "failures": [],
            "sec": 0.001,
            "pair_marker": pair_index,
        })
    return rows


def _watchdog_order_worker(send_conn, pair_index, _spec_a, _spec_b):
    try:
        if pair_index == 0:
            time.sleep(0.15)
        send_conn.send({"status": "ok", "rows": _watchdog_test_rows(pair_index)})
    finally:
        send_conn.close()


def _watchdog_timeout_worker(send_conn, _pair_index, _spec_a, _spec_b):
    try:
        time.sleep(5)
    finally:
        send_conn.close()


def _watchdog_crash_worker(_send_conn, _pair_index, _spec_a, _spec_b):
    os._exit(23)


def _watchdog_payload_then_hang_worker(send_conn, pair_index, _spec_a, _spec_b):
    send_conn.send({"status": "ok", "rows": _watchdog_test_rows(pair_index)})
    time.sleep(5)


def _watchdog_bad_payload_worker(send_conn, _pair_index, _spec_a, _spec_b):
    try:
        send_conn.send({"status": "ok", "rows": [{"a_seat": 0}]})
    finally:
        send_conn.close()


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

    def test_watchdog_preserves_pair_index_order_when_children_finish_out_of_order(self):
        paired, _events, run_failures = arena._run_fresh_seat_pairs(
            "random", "first", pair_count=2, jobs=2, pair_timeout_sec=5,
            worker_target=_watchdog_order_worker, exit_grace_sec=0.1,
        )
        rows = arena._flatten_annotated_pairs(paired)
        self.assertEqual([row["pair_marker"] for row in rows], [0, 0, 1, 1])
        self.assertEqual([row["pair_index"] for row in rows], [0, 0, 1, 1])
        self.assertEqual([row["game_index"] for row in rows], [0, 1, 0, 1])
        self.assertEqual([row["a_seat"] for row in rows], [0, 1, 1, 0])
        self.assertEqual(run_failures, [])

    def test_watchdog_timeout_returns_two_schema_compatible_failure_rows(self):
        t0 = time.monotonic()
        paired, events, run_failures = arena._run_fresh_seat_pairs(
            "random", "first", pair_count=1, jobs=1, pair_timeout_sec=0.05,
            worker_target=_watchdog_timeout_worker, exit_grace_sec=0.01,
            terminate_grace_sec=0.2, kill_grace_sec=0.2,
        )
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(len(paired[0]), 2)
        self.assertEqual([row["a_seat"] for row in paired[0]], [0, 1])
        self.assertTrue(all(set(row) == arena._RESULT_KEYS for row in paired[0]))
        rows = arena._flatten_annotated_pairs(paired)
        self.assertEqual([row["pair_index"] for row in rows], [0, 0])
        self.assertEqual([row["game_index"] for row in rows], [0, 1])
        self.assertTrue(all(row["reward"] is None for row in paired[0]))
        self.assertTrue(all(row["status_a"] == "ERROR" for row in paired[0]))
        self.assertEqual([event["kind"] for event in events], ["timeout"])
        self.assertEqual(run_failures, [])

    def test_watchdog_child_crash_becomes_failure_rows(self):
        paired, events, run_failures = arena._run_fresh_seat_pairs(
            "random", "first", pair_count=1, jobs=1, pair_timeout_sec=5,
            worker_target=_watchdog_crash_worker, exit_grace_sec=0.01,
        )
        self.assertEqual(len(paired[0]), 2)
        self.assertTrue(all("worker_crash" in row["failures"][0]
                            for row in paired[0]))
        self.assertEqual([event["kind"] for event in events], ["worker_crash"])
        self.assertEqual(run_failures, [])

    def test_watchdog_forces_cleanup_after_valid_payload_without_failing_rows(self):
        t0 = time.monotonic()
        paired, events, run_failures = arena._run_fresh_seat_pairs(
            "random", "first", pair_count=1, jobs=1, pair_timeout_sec=5,
            worker_target=_watchdog_payload_then_hang_worker, exit_grace_sec=0.01,
            terminate_grace_sec=0.2, kill_grace_sec=0.2,
        )
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertTrue(all(not row["failures"] for row in paired[0]))
        self.assertEqual([event["kind"] for event in events],
                         ["forced_cleanup_after_payload"])
        self.assertEqual(run_failures, [])

    def test_watchdog_rejects_malformed_payload_as_protocol_failure(self):
        paired, events, run_failures = arena._run_fresh_seat_pairs(
            "random", "first", pair_count=1, jobs=1, pair_timeout_sec=5,
            worker_target=_watchdog_bad_payload_worker, exit_grace_sec=0.1,
        )
        self.assertTrue(all("protocol_error" in row["failures"][0]
                            for row in paired[0]))
        self.assertEqual([event["kind"] for event in events], ["protocol_error"])
        self.assertEqual(run_failures, [])

    def test_watchdog_failure_is_written_before_strict_error(self):
        failed_pair = arena._synthetic_failed_pair(0, "timeout", "test timeout", 0.1)
        private_marker = "private replay content must not enter ledger"
        failed_pair[0][arena._PRIVATE_FAILURE_REPLAY] = {
            "steps": [{"marker": private_marker}, {"status": "TIMEOUT"}],
        }
        failed_pair[0][arena._PRIVATE_FAILURE_LOGS] = [{"duration": 600.021}]
        event = {"pair_index": 0, "kind": "timeout"}
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "arena.jsonl")
            replay_dir = os.path.join(d, "replays", "arena-failures")
            with mock.patch.object(arena, "LEDGER", ledger), \
                    mock.patch.object(arena, "FAILURE_REPLAY_DIRECTORY", replay_dir), \
                    mock.patch.object(
                        arena, "_run_fresh_seat_pairs",
                        return_value=([failed_pair], [event], []),
                    ):
                with self.assertRaises(arena.ArenaRunError) as raised:
                    arena.run_match_series(
                        "random", "first", n=2, jobs=1, profile="standard",
                        pair_timeout_sec=1, run_id="diagnostic-test",
                    )
            with open(ledger) as f:
                raw_ledger = f.readline()
                saved = json.loads(raw_ledger)
            diagnostic = saved["failures"][0]["diagnostic"]
            sidecar_path = os.path.join(replay_dir, os.path.basename(diagnostic["path"]))
            with open(sidecar_path) as f:
                sidecar = json.load(f)
            self.assertEqual(diagnostic["sha256"], arena._sha256_file(sidecar_path))
        self.assertEqual(saved["schema"], 2)
        self.assertEqual(saved["n"], 2)
        self.assertEqual(saved["failure_count"], 2)
        self.assertEqual(saved["overall"]["unscored"], 2)
        self.assertEqual(saved["statuses_a"], {"ERROR": 2})
        self.assertEqual(saved["watchdog"]["event_count"], 1)
        self.assertEqual(
            [(row["pair_index"], row["game_index"]) for row in saved["failures"]],
            [(0, 0), (0, 1)],
        )
        self.assertEqual(
            diagnostic["path"],
            f"replays/arena-failures/diagnostic-test-i{saved['invocation_id']}"
            "-p00-g0.json",
        )
        self.assertEqual(diagnostic["invocation_id"], saved["invocation_id"])
        self.assertEqual((diagnostic["step_count"], diagnostic["log_count"]), (2, 1))
        self.assertIsNone(diagnostic["native_seed"])
        self.assertFalse(diagnostic["exact_rerun_supported"])
        self.assertEqual(sidecar["environment"]["steps"][0]["marker"], private_marker)
        self.assertEqual(sidecar["logs"], [{"duration": 600.021}])
        self.assertEqual(sidecar["invocation_id"], saved["invocation_id"])
        self.assertIsNone(sidecar["reproducibility"]["native_seed"])
        self.assertFalse(sidecar["reproducibility"]["exact_rerun_supported"])
        self.assertNotIn(private_marker, raw_ledger)
        self.assertNotIn(arena._PRIVATE_FAILURE_REPLAY, raw_ledger)
        self.assertNotIn(arena._PRIVATE_FAILURE_LOGS, raw_ledger)
        self.assertEqual(raised.exception.record["run_id"], saved["run_id"])

    def test_failure_sidecar_write_error_preserves_result_and_is_run_failure(self):
        failed_pair = arena._synthetic_failed_pair(0, "timeout", "keep me", 0.1)
        failed_pair[0][arena._PRIVATE_FAILURE_REPLAY] = {
            "steps": [{"marker": "private-sidecar-only"}],
        }
        failed_pair[0][arena._PRIVATE_FAILURE_LOGS] = [{"duration": 1.0}]
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "arena.jsonl")
            with mock.patch.object(arena, "LEDGER", ledger), \
                    mock.patch.object(
                        arena, "_run_fresh_seat_pairs",
                        return_value=([failed_pair], [], []),
                    ), mock.patch.object(
                        arena, "_write_failure_sidecar",
                        side_effect=OSError("disk full"),
                    ):
                record = arena.run_match_series(
                    "random", "first", n=2, jobs=1, profile="standard",
                    pair_timeout_sec=1, run_id="save-error-test", strict=False,
                )
            with open(ledger) as f:
                raw_ledger = f.readline()
        self.assertEqual(record["failure_count"], 2)
        self.assertIn("arena_pair_timeout: keep me",
                      record["failures"][0]["failures"][0])
        self.assertEqual((record["failures"][0]["pair_index"],
                          record["failures"][0]["game_index"]), (0, 0))
        self.assertIn("OSError: disk full",
                      record["failures"][0]["diagnostic"]["save_error"])
        self.assertTrue(any("failure diagnostic save failed (pair=0 game=0)" in error
                            for error in record["run_failures"]))
        self.assertNotIn("private-sidecar-only", raw_ledger)
        self.assertNotIn(arena._PRIVATE_FAILURE_REPLAY, raw_ledger)

    def test_same_run_id_reused_by_gauntlet_gets_distinct_failure_sidecars(self):
        def failed_result(marker):
            pair = arena._synthetic_failed_pair(0, "timeout", marker, 0.1)
            pair[0][arena._PRIVATE_FAILURE_REPLAY] = {
                "steps": [{"marker": marker}],
            }
            pair[0][arena._PRIVATE_FAILURE_LOGS] = [{"duration": 1.0}]
            return ([pair], [], [])

        responses = [failed_result("opponent-a"), failed_result("opponent-b")]
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "arena.jsonl")
            replay_dir = os.path.join(d, "replays", "arena-failures")
            with mock.patch.object(arena, "LEDGER", ledger), \
                    mock.patch.object(arena, "FAILURE_REPLAY_DIRECTORY", replay_dir), \
                    mock.patch.object(
                        arena, "_run_fresh_seat_pairs", side_effect=responses,
                    ):
                records = [
                    arena.run_match_series(
                        "random", "first", n=2, jobs=1, profile="standard",
                        pair_timeout_sec=1, run_id="shared-gauntlet-run", strict=False,
                    )
                    for _ in range(2)
                ]
            with open(ledger) as f:
                saved_records = [json.loads(line) for line in f]

            self.assertNotEqual(records[0]["invocation_id"],
                                records[1]["invocation_id"])
            paths = [record["failures"][0]["diagnostic"]["path"]
                     for record in records]
            self.assertEqual(2, len(set(paths)))
            self.assertEqual(2, len(os.listdir(replay_dir)))
            for marker, record, saved, relative_path in zip(
                    ("opponent-a", "opponent-b"), records, saved_records, paths):
                diagnostic = record["failures"][0]["diagnostic"]
                sidecar_path = os.path.join(replay_dir, os.path.basename(relative_path))
                with open(sidecar_path) as f:
                    sidecar = json.load(f)
                self.assertEqual("shared-gauntlet-run", sidecar["run_id"])
                self.assertEqual(record["invocation_id"], sidecar["invocation_id"])
                self.assertEqual(record["invocation_id"], diagnostic["invocation_id"])
                self.assertEqual(marker, sidecar["environment"]["steps"][0]["marker"])
                self.assertEqual(diagnostic["sha256"], arena._sha256_file(sidecar_path))
                self.assertEqual(relative_path,
                                 saved["failures"][0]["diagnostic"]["path"])

    def test_reuse_path_assigns_deterministic_pair_and_game_indices(self):
        rows = _watchdog_test_rows(0) + _watchdog_test_rows(0)
        rows[2]["failures"] = ["reuse failure"]
        executor = mock.MagicMock()
        executor.__enter__.return_value = executor
        executor.map.return_value = rows
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(arena, "LEDGER", os.path.join(d, "arena.jsonl")), \
                mock.patch.object(arena, "ProcessPoolExecutor", return_value=executor), \
                mock.patch.object(arena, "_write_failure_sidecar") as writer:
            record = arena.run_match_series(
                "random", "first", n=4, jobs=2, profile="standard",
                fresh_process_per_pair=False, strict=False,
            )
        self.assertEqual(record["failure_count"], 1)
        self.assertEqual((record["failures"][0]["pair_index"],
                          record["failures"][0]["game_index"]), (1, 0))
        writer.assert_not_called()

    def test_forced_cleanup_metadata_is_nonfatal(self):
        valid_pair = _watchdog_test_rows(0)
        event = {"pair_index": 0, "kind": "forced_cleanup_after_payload"}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(arena, "LEDGER", os.path.join(d, "arena.jsonl")), \
                    mock.patch.object(arena, "_write_failure_sidecar") as writer, \
                    mock.patch.object(
                        arena, "_run_fresh_seat_pairs",
                        return_value=([valid_pair], [event], []),
                    ):
                record = arena.run_match_series(
                    "random", "first", n=2, jobs=1, profile="standard",
                    pair_timeout_sec=1,
                )
        self.assertEqual(record["failure_count"], 0)
        self.assertEqual(record["run_failures"], [])
        self.assertEqual(record["watchdog"]["event_count"], 1)
        writer.assert_not_called()

    def test_worker_attaches_raw_replay_and_logs_only_to_failure(self):
        replay = {"steps": [{"status": "TIMEOUT"}]}
        logs = [{"duration": 600.1}]
        env = SimpleNamespace(toJSON=lambda: replay, logs=logs)

        success = {"failures": []}
        arena._attach_failure_diagnostic(success, env)
        self.assertNotIn(arena._PRIVATE_FAILURE_REPLAY, success)
        self.assertNotIn(arena._PRIVATE_FAILURE_LOGS, success)

        failure = {"failures": ["a_status=TIMEOUT"]}
        arena._attach_failure_diagnostic(failure, env)
        self.assertEqual(failure[arena._PRIVATE_FAILURE_REPLAY], replay)
        self.assertEqual(failure[arena._PRIVATE_FAILURE_LOGS], logs)

    def test_pair_timeout_must_be_finite_and_positive(self):
        for value in (0, -1, float("nan"), float("inf"), True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                arena.run_match_series("random", "first", n=2, pair_timeout_sec=value)

    def test_remaining_overage_min_ignores_missing_and_invalid_values(self):
        env = SimpleNamespace(steps=[
            [{"observation": {"remainingOverageTime": 600}}, {}],
            [{"observation": {}}, {"observation": {"remainingOverageTime": 500}}],
            [{"observation": {"remainingOverageTime": 123.45678}},
             {"observation": {"remainingOverageTime": True}}],
            [{"observation": {"remainingOverageTime": float("nan")}},
             {"observation": {"remainingOverageTime": float("inf")}}],
        ])
        self.assertEqual(arena._remaining_overage_min(env, 0), 123.4568)
        self.assertEqual(arena._remaining_overage_min(env, 1), 500.0)
        self.assertIsNone(arena._remaining_overage_min(SimpleNamespace(steps=[]), 0))
        self.assertIsNone(arena._remaining_overage_min(SimpleNamespace(steps=None), 0))

    def test_min_present_ignores_missing_values(self):
        rows = [{"x": None}, {}, {"x": 4.5}, {"x": 2.25}]
        self.assertEqual(arena._min_present(rows, "x"), 2.25)
        self.assertIsNone(arena._min_present(rows[:2], "x"))

    def test_agent_metrics_are_summed_by_agent_and_seat(self):
        rows = [
            {"a_seat": 0,
             "metrics_a": {"expert_rule_hit.AZ001": 2, "ignored": "x"},
             "metrics_b": {"expert_rule_hit.AZ001": 3}},
            {"a_seat": 1,
             "metrics_a": {"expert_rule_hit.AZ001": 5},
             "metrics_b": {"expert_rule_hit.AZ001": 7}},
        ]
        self.assertEqual(
            arena._sum_agent_metrics(rows, "a"),
            {"expert_rule_hit.AZ001": 7},
        )
        self.assertEqual(
            arena._sum_agent_metrics(rows, "a", 0),
            {"expert_rule_hit.AZ001": 2},
        )
        self.assertEqual(
            arena._sum_agent_metrics(rows, "b", 0),
            {"expert_rule_hit.AZ001": 7},
        )

    def test_rule_conflict_and_forbidden_violation_are_strict_failures(self):
        metrics = {
            "expert_rule_hit.AZ005": 3,
            "expert_rule_guard_blocked.AZ005": 1,
            "expert_rule_conflicts": 1,
            "expert_rule_violation.AZ005": 1,
        }
        self.assertEqual(
            arena._strict_agent_metric_failures("a", metrics),
            [
                "a_expert_rule_conflicts=1",
                "a_expert_rule_violation.AZ005=1",
            ],
        )

    def test_build_validates_expert_rule_config_shape(self):
        valid = {
            "model": "bc_v2",
            "config": {
                "algo": "bcs",
                "expert_rules": "alakazam_v1",
                "expert_rule_mode": "candidate",
                "enabled_rule_ids": ["AZ001_EMPTY_BENCH_BASIC"],
            },
        }
        with mock.patch.object(os.path, "isfile", return_value=True):
            build_module._validate_spec(valid, "valid.json")
        for config in (
            {"algo": "bc", "expert_rules": "alakazam_v1",
             "expert_rule_mode": "candidate"},
            {"algo": "bcs", "expert_rules": "alakazam_v1",
             "expert_rule_mode": "bad"},
            {"algo": "bcs", "expert_rule_mode": "shadow"},
            {"algo": "bcs", "expert_rules": "alakazam_v1",
             "expert_rule_mode": "candidate"},
            {"algo": "bcs", "expert_rules": "alakazam_v1",
             "enabled_rule_ids": ["x", "x"]},
            {"algo": "bcs", "expert_rules": "alakazam_v1",
             "enabled_rule_ids": []},
        ):
            spec = {"model": "bc_v2", "config": config}
            with self.subTest(config=config), mock.patch.object(
                os.path, "isfile", return_value=True,
            ), self.assertRaises(ValueError):
                build_module._validate_spec(spec, "bad.json")

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
