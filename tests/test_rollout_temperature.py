"""ロールアウトのsoftmaxサンプリングのテスト。

既定(温度0)で従来のargmaxと**完全一致**することを固定するのが主目的。

背景(2026-08-02): 世界(determinization)がサンプルするのは隠れ情報だけで、相手の行動は
argmaxで決まるため、世界を1つ決めると終局まで一本道になり相手の別ラインを探索しない。
同一壁に対し bc_grim2 は純BC 67.1%/400 に対し BCS fixed2 が 46.0%/200 と21pt悪化した。
"""

import os
import random
import sys
import unittest
import unittest.mock
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ptcg import bc_search, policy  # noqa: E402


def obs(n_opts=4, max_count=1):
    """_raw_scoresをスタブするので、optionの中身は個数だけ合っていればよい。"""
    return {
        "select": {"maxCount": max_count, "minCount": 1,
                   "option": [{"type": 1} for _ in range(n_opts)]},
        "current": {"yourIndex": 0},
    }


class RolloutTemperatureTest(unittest.TestCase):
    def setUp(self):
        self._saved_temp = bc_search.ROLLOUT_TEMPERATURE
        self.addCleanup(setattr, bc_search, "ROLLOUT_TEMPERATURE", self._saved_temp)
        self._saved_enabled = policy.ENABLED
        self.addCleanup(setattr, policy, "ENABLED", self._saved_enabled)
        self._saved_raw = policy._raw_scores
        self.addCleanup(setattr, policy, "_raw_scores", self._saved_raw)
        policy.ENABLED = True
        # option 0 が最良、以降単調に悪い固定スコア
        policy._raw_scores = lambda sel, cur, opts: np.array(
            [3.0, 1.0, 0.5, 0.0][:len(opts)], dtype=np.float32)

    # --- 既定は完全no-op ---

    def test_default_constant_is_zero(self):
        """モジュール既定は0でなければならない(既存agentがno-opであること)。"""
        self.assertEqual(self._saved_temp, 0.0)

    def test_temp_zero_is_exactly_argmax(self):
        """温度0は choose() と完全に同一。"""
        o = obs()
        for _ in range(50):
            self.assertEqual(policy.choose_sampled(o, 0.0, random.Random(1)),
                             policy.choose(o))

    def test_negative_temp_is_argmax(self):
        o = obs()
        self.assertEqual(policy.choose_sampled(o, -1.0, random.Random(1)),
                         policy.choose(o))

    # --- サンプリングの挙動 ---

    def test_sampling_reaches_non_argmax(self):
        """温度>0なら最良以外も選ばれる = 一本道でなくなる。"""
        rng = random.Random(0)
        picks = Counter(policy.choose_sampled(obs(), 1.0, rng)[0] for _ in range(400))
        self.assertGreater(picks[0], 0, "最良手が一度も選ばれていない")
        self.assertGreater(sum(v for k, v in picks.items() if k != 0), 0,
                           "温度>0なのにargmaxしか出ていない")

    def test_argmax_stays_most_likely(self):
        """バランスのための揺らぎであって、方策を壊してはいけない。"""
        rng = random.Random(0)
        picks = Counter(policy.choose_sampled(obs(), 1.0, rng)[0] for _ in range(400))
        self.assertEqual(picks.most_common(1)[0][0], 0)

    def test_lower_temperature_is_greedier(self):
        def argmax_rate(t):
            rng = random.Random(7)
            p = Counter(policy.choose_sampled(obs(), t, rng)[0] for _ in range(400))
            return p[0] / 400
        self.assertGreater(argmax_rate(0.25), argmax_rate(1.5))

    def test_same_seed_is_reproducible(self):
        a = [policy.choose_sampled(obs(), 1.0, random.Random(3))[0] for _ in range(20)]
        b = [policy.choose_sampled(obs(), 1.0, random.Random(3))[0] for _ in range(20)]
        self.assertEqual(a, b)

    # --- サンプル対象外の経路 ---

    def test_multi_select_is_not_sampled(self):
        """複数選択(maxCount>1)は従来どおり決定的。"""
        o = obs(max_count=2)
        for _ in range(20):
            self.assertEqual(policy.choose_sampled(o, 1.5, random.Random(9)),
                             policy.choose(o))

    def test_disabled_policy_returns_none(self):
        policy.ENABLED = False
        self.assertIsNone(policy.choose_sampled(obs(), 1.0, random.Random(1)))

    def test_single_option_returns_none(self):
        self.assertIsNone(policy.choose_sampled(obs(n_opts=1), 1.0, random.Random(1)))

    # --- 異常系はargmaxへフォールバック ---

    def test_non_finite_scores_fall_back_to_argmax(self):
        policy._raw_scores = lambda sel, cur, opts: np.array(
            [np.inf, np.nan, 0.0, 0.0], dtype=np.float32)
        got = policy.choose_sampled(obs(), 1.0, random.Random(1))
        self.assertIsNotNone(got)
        self.assertEqual(len(got), 1)
        self.assertTrue(0 <= got[0] < 4)

    def test_none_scores_returns_none(self):
        policy._raw_scores = lambda sel, cur, opts: None
        self.assertIsNone(policy.choose_sampled(obs(), 1.0, random.Random(1)))

    # --- _policy_act 経由 ---

    def test_policy_act_without_rng_stays_argmax(self):
        """rngが無い呼び出しは温度設定に関わらず決定的(安全側)。"""
        bc_search.ROLLOUT_TEMPERATURE = 1.5
        o = obs()
        self.assertEqual(bc_search._policy_act(o, 0, None), policy.choose(o))

    def test_policy_act_default_temp_is_argmax(self):
        bc_search.ROLLOUT_TEMPERATURE = 0.0
        o = obs()
        for _ in range(20):
            self.assertEqual(bc_search._policy_act(o, 0, random.Random(5)),
                             policy.choose(o))


class CallShapeTest(unittest.TestCase):
    """温度0では**呼び出しの引数の数まで**従来と同一であることを固定する。

    既存テスト(test_opp_policy / test_bc_search / test_trace_expert_interventions)は
    `_rollout(state, my_index)` / `_policy_act(od, my_index)` の2引数でモックしている。
    既定でno-opと言う以上、余分な引数を渡してはならない。
    """

    def setUp(self):
        self._saved = bc_search.ROLLOUT_TEMPERATURE
        self.addCleanup(setattr, bc_search, "ROLLOUT_TEMPERATURE", self._saved)

    def _run_rollout(self, temp):
        seen = []
        live = dict(obs())
        live["current"] = {"yourIndex": 0, "result": -1,
                           "players": [{"prize": []}, {"prize": []}]}
        state = {"searchId": 1, "observation": live}

        def fake_step(_sid, _act):
            done = dict(obs())
            done["current"] = {"yourIndex": 0, "result": 0,
                               "players": [{"prize": []}, {"prize": []}]}
            return {"searchId": 1, "observation": done}

        def spy(*args, **kwargs):
            seen.append(len(args) + len(kwargs))
            return [0]

        bc_search.ROLLOUT_TEMPERATURE = temp
        with unittest.mock.patch.object(bc_search, "_policy_act", spy), \
             unittest.mock.patch.object(bc_search, "search_step_dict", fake_step), \
             unittest.mock.patch.object(bc_search.value, "ENABLED", False):
            bc_search._rollout(state, 0, random.Random(1))
        return seen

    def test_zero_temperature_calls_policy_act_with_two_args(self):
        self.assertEqual(self._run_rollout(0.0), [2])

    def test_positive_temperature_calls_policy_act_with_three_args(self):
        self.assertEqual(self._run_rollout(1.0), [3])


class ConfigClampTest(unittest.TestCase):
    """main.pyのクランプ規則(0..MAX、範囲外と不正値は0)を仕様として固定する。"""

    def clamp(self, raw):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return 0.0
        return v if 0.0 <= v <= bc_search.ROLLOUT_TEMPERATURE_MAX else 0.0

    def test_valid_values_pass_through(self):
        for v in (0.0, 0.5, 1.0, bc_search.ROLLOUT_TEMPERATURE_MAX):
            self.assertEqual(self.clamp(v), v)

    def test_out_of_range_becomes_zero(self):
        for v in (-0.1, bc_search.ROLLOUT_TEMPERATURE_MAX + 0.1, 1e9):
            self.assertEqual(self.clamp(v), 0.0)

    def test_garbage_becomes_zero(self):
        for v in ("abc", None, {}, []):
            self.assertEqual(self.clamp(v), 0.0)


if __name__ == "__main__":
    unittest.main()
