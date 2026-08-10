"""main.agent() まで通した配線テスト(ビルド済みagentを別プロセスで読む)。

`policy.ENABLED` を assert したうえで、同じ合成局面に対し

- ガード未指定のagent(v5.4g-bc): 禁止集合は空・カウンタは1つも動かず、
  `agent()` の返り値が `policy.choose()` と**完全に一致**する
- ガード有効のagent(v5.6g-bc=bc_grim3 / v5.8g-bc=bc_grim5): 発火し、
  BCが選んだ禁止手が別の手へ差し替わる

ことを確認する。build/ はgit管理外なので、未ビルドならskipする
(`.venv/bin/python -m ptcglab.build v5.6g-bc` などで作れる)。
別プロセスで走らせるのは、1プロセスに読み込めるptcgパッケージが1つだけのため。
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")

PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from ptcg import policy
assert policy.ENABLED, "BCモデルが載っていない(ptcgのimport順を疑う)"
import main
assert main.policy is policy

def pk(cid, hp, mx, energies):
    return {"id": cid, "serial": cid * 10, "hp": hp, "maxHp": mx,
            "appearThisTurn": False, "energies": list(energies),
            "energyCards": [], "tools": [], "preEvolution": []}

def side(active, bench, hand):
    return {"active": active, "bench": bench, "benchMax": 5, "deckCount": 30,
            "discard": [], "prize": [None] * 6, "hand": hand,
            "handCount": len(hand or []), "poisoned": False, "burned": False,
            "asleep": False, "paralyzed": False, "confused": False}

# KO後の昇格: エネ5のGrimmsnarl ex(320) と 素のSnorunt(70)。
# 相手はエネ3のTeal Mask Ogerpon ex -> Grimmsnarlには540、Snoruntには120。
OBS = {
    "select": {"type": 1, "context": 4, "minCount": 1, "maxCount": 1,
               "remainDamageCounter": 0, "remainEnergyCost": 0, "deck": None,
               "contextCard": None, "effect": None,
               "option": [{"type": 3, "area": 5, "playerIndex": 0, "index": 0},
                          {"type": 3, "area": 5, "playerIndex": 0, "index": 1}]},
    "current": {"yourIndex": 0, "turn": 6, "firstPlayer": 0, "looking": [],
                "result": None, "retreated": False, "stadium": None,
                "stadiumPlayed": False, "supporterPlayed": False,
                "energyAttached": False, "turnActionCount": 0,
                "players": [
                    side([], [pk(648, 320, 320, [7] * 5), pk(860, 70, 70, [])], []),
                    side([pk(96, 210, 210, [1, 1, 1])], [], None)]},
    "logs": [],
    "remainingOverageTime": 600.0,
}

before = dict(main.AGENT_METRICS)
bc = policy.choose(OBS)
act = main.agent(OBS)
delta = {k: v for k, v in main.AGENT_METRICS.items() if v != before.get(k, 0)}
print(json.dumps({
    "guard_on": main.OHKO_GUARD is not None,
    "rules": list(main.OHKO_GUARD.rule_ids) if main.OHKO_GUARD else [],
    "forbidden": sorted(list(a) for a in main._guard_forbidden(OBS)),
    "bc": bc, "act": act, "delta": delta,
}))
'''


def probe(agent_name):
    agent_dir = os.path.join(BUILD, agent_name)
    if not os.path.isdir(agent_dir):
        raise unittest.SkipTest(f"未ビルド: build/{agent_name}")
    out = subprocess.run(
        [sys.executable, "-c", PROBE, agent_dir],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    if out.returncode != 0:
        raise AssertionError(f"probe失敗:\n{out.stdout}\n{out.stderr}")
    return json.loads(out.stdout.strip().splitlines()[-1])


class AgentWiringTest(unittest.TestCase):
    def test_guard_absent_agent_is_unchanged(self):
        got = probe("v5.4g-bc")
        self.assertFalse(got["guard_on"])
        self.assertEqual(got["forbidden"], [])
        # BCの選択がそのまま返る = choose の呼び出し経路が従来どおり。
        self.assertEqual(got["act"], got["bc"])
        self.assertEqual(
            [k for k in got["delta"] if k.startswith("ohko_guard")], [],
        )

    def test_guard_enabled_agent_redirects_the_forbidden_move(self):
        # bc_grim3(v5.6g) / bc_grim5(v5.8g、最終提出の本命候補) の両方で確認する。
        for name in ("v5.6g-bc", "v5.8g-bc"):
            with self.subTest(agent=name):
                self._assert_redirects(probe(name))

    def _assert_redirects(self, got):
        self.assertTrue(got["guard_on"])
        # 既定ルールはGR001+GR002のみ(GR003は明示指定制)。
        self.assertEqual(got["rules"], [
            "GR001_OHKO_COMMIT_AVOID", "GR002_OHKO_EVOLVE_AVOID",
        ])
        self.assertEqual(got["forbidden"], [[0]])  # エネ5のGrimmsnarl ex
        self.assertEqual(got["bc"], [0], "この局面でBCが禁止手を選ばないと検証にならない")
        self.assertEqual(got["act"], [1])          # 身代わりのSnorunt
        self.assertEqual(got["delta"]["ohko_guard_blocked"], 1)
        self.assertEqual(got["delta"]["ohko_guard_redirected"], 1)
        self.assertEqual(
            got["delta"]["ohko_guard_hit.GR001_OHKO_COMMIT_AVOID"], 1,
        )


if __name__ == "__main__":
    unittest.main()
