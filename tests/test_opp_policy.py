"""ロールアウト内の相手専用モデル(opp_policy)の配線テスト。

設定なしの既存agentが完全にno-opであること(退行防止)と、
有効時に「相手が手番のときだけ」相手モデルを使うことを固定する。
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ptcg import bc_search  # noqa: E402


def obs(actor_index: int) -> dict:
    return {
        "select": {"type": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 14}, {"type": 14}]},
        "current": {"yourIndex": actor_index, "result": -1, "players": []},
    }


class PolicyActRoutingTest(unittest.TestCase):
    """_policy_act が誰の手番かでモデルを切り替える。"""

    def test_no_opp_model_is_noop(self):
        """opp_policy無効(既存agent) = 常に従来policy。my_indexを渡しても変わらない。"""
        with mock.patch.object(bc_search.opp_policy, "ENABLED", False), \
             mock.patch.object(bc_search.opp_policy, "choose") as opp, \
             mock.patch.object(bc_search.policy, "choose", return_value=[0]) as base:
            self.assertEqual(bc_search._policy_act(obs(1), my_index=0), [0])
            self.assertEqual(bc_search._policy_act(obs(0), my_index=0), [0])
            self.assertEqual(bc_search._policy_act(obs(1)), [0])
        opp.assert_not_called()
        self.assertEqual(base.call_count, 3)

    def test_opponent_turn_uses_opp_model(self):
        with mock.patch.object(bc_search.opp_policy, "ENABLED", True), \
             mock.patch.object(bc_search.opp_policy, "choose", return_value=[1]) as opp, \
             mock.patch.object(bc_search.policy, "choose", return_value=[0]) as base:
            self.assertEqual(bc_search._policy_act(obs(1), my_index=0), [1])
        opp.assert_called_once()
        base.assert_not_called()

    def test_own_turn_uses_base_model(self):
        with mock.patch.object(bc_search.opp_policy, "ENABLED", True), \
             mock.patch.object(bc_search.opp_policy, "choose", return_value=[1]) as opp, \
             mock.patch.object(bc_search.policy, "choose", return_value=[0]) as base:
            self.assertEqual(bc_search._policy_act(obs(0), my_index=0), [0])
        opp.assert_not_called()
        base.assert_called_once()

    def test_opp_model_none_falls_back(self):
        """相手モデルが対象外(None)を返したら従来policyへ落ちる。"""
        with mock.patch.object(bc_search.opp_policy, "ENABLED", True), \
             mock.patch.object(bc_search.opp_policy, "choose", return_value=None), \
             mock.patch.object(bc_search.policy, "choose", return_value=[0]) as base:
            self.assertEqual(bc_search._policy_act(obs(1), my_index=0), [0])
        base.assert_called_once()

    def test_missing_your_index_falls_back(self):
        bad = obs(1)
        bad["current"].pop("yourIndex")
        with mock.patch.object(bc_search.opp_policy, "ENABLED", True), \
             mock.patch.object(bc_search.opp_policy, "choose") as opp, \
             mock.patch.object(bc_search.policy, "choose", return_value=[0]) as base:
            self.assertEqual(bc_search._policy_act(bad, my_index=0), [0])
        opp.assert_not_called()
        base.assert_called_once()

    def test_rollout_passes_my_index(self):
        """_rolloutが手番判定用のmy_indexを必ず渡す(渡し忘れると常に自分モデルになる)。"""
        seen = []
        state = {"searchId": 1, "observation": obs(1)}

        def fake_step(_sid, _act):
            done = dict(obs(0))
            done["current"] = dict(done["current"], result=0)
            return {"searchId": 1, "observation": done}

        def spy(od, my_index=None):
            seen.append(my_index)
            return [0]

        with mock.patch.object(bc_search, "_policy_act", spy), \
             mock.patch.object(bc_search, "search_step_dict", fake_step), \
             mock.patch.object(bc_search.value, "ENABLED", False):
            bc_search._rollout(state, my_index=1)
        self.assertEqual(seen, [1])


class BuildSpecValidationTest(unittest.TestCase):
    """opp_modelの設定事故をビルド前に止める。"""

    def setUp(self):
        sys.path.insert(0, ROOT)
        from ptcglab import build
        self.build = build

    def _spec(self, **kw):
        spec = {"deck": "d.csv", "model": "bc_v2", "config": {"algo": "bcs"}}
        spec.update(kw)
        return spec

    def test_opp_model_requires_bcs(self):
        spec = self._spec(opp_model="bc_grim", config={"algo": "bc"})
        with self.assertRaises(ValueError):
            self.build._validate_spec(spec, "x.json")

    def test_missing_opp_model_assets(self):
        spec = self._spec(opp_model="__does_not_exist__")
        with self.assertRaises(ValueError):
            self.build._validate_spec(spec, "x.json")

    def test_valid_opp_model_passes(self):
        if not os.path.isdir(os.path.join(ROOT, "models", "bc_grim")):
            self.skipTest("models/bc_grim が無い")
        self.build._validate_spec(self._spec(opp_model="bc_grim"), "x.json")

    def test_no_opp_model_still_valid(self):
        self.build._validate_spec(self._spec(), "x.json")


class BuildInjectionTest(unittest.TestCase):
    """opp_modelを指定したときだけ ptcg/ に別名で2ファイルが入る。"""

    def test_injected_filenames(self):
        mdir = os.path.join(ROOT, "models", "bc_grim")
        if not os.path.isdir(mdir):
            self.skipTest("models/bc_grim が無い")
        with tempfile.TemporaryDirectory() as tmp:
            ptcg = os.path.join(tmp, "ptcg")
            os.makedirs(ptcg)
            import shutil
            for fn, dst in (("policy_params.npz", "opp_policy_params.npz"),
                            ("policy_vocab.py", "opp_policy_vocab.py")):
                shutil.copy(os.path.join(mdir, fn), os.path.join(ptcg, dst))
            self.assertTrue(os.path.isfile(os.path.join(ptcg, "opp_policy_params.npz")))
            self.assertTrue(os.path.isfile(os.path.join(ptcg, "opp_policy_vocab.py")))
            # 本体のpolicy資産を踏まないこと
            self.assertFalse(os.path.exists(os.path.join(ptcg, "policy_params.npz")))


if __name__ == "__main__":
    unittest.main()
