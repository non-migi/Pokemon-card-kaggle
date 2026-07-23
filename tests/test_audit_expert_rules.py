import hashlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from ptcg import expert_rules as rules  # noqa: E402
from scripts import audit_expert_rules as audit  # noqa: E402


class AuditExpertRulesTests(unittest.TestCase):
    def test_injection_attribution_obeys_shared_two_slot_limit(self):
        proposals = [
            rules.RuleProposal("R6", (6,), 300, "candidate", "r6"),
            rules.RuleProposal("R7", (7,), 200, "candidate", "r7"),
            rules.RuleProposal("R5", (5,), 100, "candidate", "r5"),
        ]
        got = audit._injected_rule_actions(
            [8, 7, 6, 5, 4, 3, 2, 1], 8, proposals, "candidate",
        )
        self.assertEqual(got, {((6,), "R6"), ((7,), "R7")})

    def test_enforce_hard_bypasses_candidate_injection(self):
        proposals = [
            rules.RuleProposal("HARD", (6,), 300, "hard", "hard"),
            rules.RuleProposal("CAND", (7,), 200, "candidate", "candidate"),
        ]
        self.assertEqual(
            audit._injected_rule_actions(
                [8, 7, 6, 5, 4, 3, 2, 1], 8, proposals, "enforce",
            ),
            set(),
        )

    def test_example_keeps_exact_row_hash_and_rule_kind(self):
        row = {
            "sel": {"option": [{}, {}]},
            "cur": {"yourIndex": 0, "players": [{}, {}], "turn": 3},
            "team": "teacher",
        }
        raw = '{"minimal":true}\n'
        proposal = rules.RuleProposal("CAND", (1,), 10, "candidate", "why")
        got = audit._injected_example(
            "pairs.jsonl.gz", 7, hashlib.sha256(raw.encode()).hexdigest(),
            row, proposal, 6, (1,), True,
        )
        self.assertEqual(got["row_sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(got["rule_kind"], "candidate")


if __name__ == "__main__":
    unittest.main()
