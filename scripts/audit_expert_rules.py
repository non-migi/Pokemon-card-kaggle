"""公式top decision pairsに対する専門家ルールの発火・教師一致率を監査する。"""

import argparse
import gzip
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ptcg import expert_rules, heuristics  # noqa: E402


CARD_ENERGY_TYPES = {
    int(card_id): int(card.energyType)
    for card_id, card in heuristics.CARDS.items()
}


def _read_deck(path: str | None) -> list[int] | None:
    if path is None:
        return None
    with open(path) as f:
        return [int(line.strip()) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+", help="pairs_YYYY.jsonl.gz")
    ap.add_argument("--profile", default="alakazam_v1")
    ap.add_argument("--rule", action="append", dest="rules",
                    help="監査するrule ID。複数指定可、未指定はprofile全件")
    ap.add_argument("--exact-deck", help="この60枚と完全一致するpairだけを対象にする")
    ap.add_argument("--limit", type=int, default=0, help="対象decision上限(0=無制限)")
    args = ap.parse_args()

    enabled = expert_rules.validate_config(args.profile, "shadow", args.rules)
    exact_deck = _read_deck(args.exact_deck)
    totals = Counter()
    per_rule: dict[str, Counter] = {rule_id: Counter() for rule_id in enabled}
    stop = False
    for path in args.pairs:
        with gzip.open(path, "rt") as f:
            for line in f:
                totals["rows_read"] += 1
                row = json.loads(line)
                deck = row.get("deck") or []
                if exact_deck is not None and deck != exact_deck:
                    continue
                totals["decisions_audited"] += 1
                obs = {"select": row.get("sel"), "current": row.get("cur")}
                proposals = expert_rules.evaluate(
                    obs, deck, args.profile, enabled,
                    card_energy_types=CARD_ENERGY_TYPES,
                )
                teacher = tuple(row.get("act") or [])
                for proposal in proposals:
                    bucket = per_rule.setdefault(proposal.rule_id, Counter())
                    bucket["hits"] += 1
                    matches = expert_rules.proposal_matches(proposal, teacher)
                    if proposal.kind == "forbid":
                        key = "teacher_violation" if matches else "teacher_avoided"
                    else:
                        key = "teacher_match" if matches else "teacher_disagree"
                    bucket[key] += 1
                    bucket[f"kind_{proposal.kind}"] += 1
                if args.limit and totals["decisions_audited"] >= args.limit:
                    stop = True
                    break
        if stop:
            break

    result = {
        "profile": args.profile,
        "enabled_rule_ids": list(enabled),
        "exact_deck": args.exact_deck,
        "totals": dict(totals),
        "rules": {},
    }
    for rule_id in enabled:
        bucket = per_rule.get(rule_id, Counter())
        hits = bucket.get("hits", 0)
        entry = dict(bucket)
        aligned = bucket.get("teacher_avoided", 0) + bucket.get("teacher_match", 0)
        entry["teacher_alignment_rate"] = round(aligned / hits, 4) if hits else None
        result["rules"][rule_id] = entry
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
