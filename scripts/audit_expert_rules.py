"""公式top decision pairsに対する専門家ルールの発火・教師一致率を監査する。"""

import argparse
import gzip
import json
import os
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# BC順位も監査する場合は、モデル同梱buildのptcgを他のrepo importより先に読む。
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument("--policy-build")
_known, _ = _bootstrap.parse_known_args()
MODULE_ROOT = os.path.abspath(
    os.path.join(ROOT, _known.policy_build) if _known.policy_build
    else os.path.join(ROOT, "src")
)
sys.path.insert(0, MODULE_ROOT)
# scripts/直実行でもrepo側ptcglabを読めるようにする。build側ptcgは常に先頭。
sys.path.insert(1, ROOT)

from ptcg import bc_search, expert_rules, heuristics, policy  # noqa: E402
from ptcglab.arena import agent_fingerprint  # noqa: E402


CARD_ENERGY_TYPES = {
    int(card_id): int(card.energyType)
    for card_id, card in heuristics.CARDS.items()
}
CARD_TRAITS = expert_rules.build_card_traits(heuristics.CARDS)


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
    ap.add_argument(
        "--policy-build",
        help="BC順位/top-5外注入も測るモデル同梱build（例: build/v4.5a-r8-fixed2）",
    )
    args = ap.parse_args()

    if args.policy_build and not policy.ENABLED:
        raise RuntimeError(f"BCモデルをロードできない: {MODULE_ROOT}")

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
                    card_traits=CARD_TRAITS,
                )
                teacher = tuple(row.get("act") or [])
                scores = policy.scores(obs) if args.policy_build and proposals else None
                if args.policy_build and proposals and scores is None:
                    totals["policy_score_missing"] += 1
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
                    if (scores is not None and len(proposal.action) == 1
                            and isinstance(proposal.action[0], int)):
                        option_count = len((obs.get("select") or {}).get("option") or [])
                        order = [
                            int(i) for i in np.argsort(-np.asarray(scores))
                            if 0 <= int(i) < option_count
                        ]
                        try:
                            rank = order.index(proposal.action[0]) + 1
                        except ValueError:
                            rank = 0
                        if rank:
                            bucket[f"bc_rank_{rank}"] += 1
                            bucket["bc_top1"] += int(rank == 1)
                            bucket["bc_top5"] += int(rank <= bc_search.TOP_K)
                            bucket["bc_outside_top5"] += int(rank > bc_search.TOP_K)
                        candidate_metrics = {}
                        bc_search._candidate_actions(
                            scores, option_count, [proposal], "candidate",
                            candidate_metrics,
                        )
                        injected = candidate_metrics.get(
                            f"expert_rule_injected.{proposal.rule_id}", 0,
                        )
                        bucket["candidate_injected"] += injected
                        if injected:
                            bucket[
                                "candidate_injected_teacher_match"
                                if matches else "candidate_injected_teacher_disagree"
                            ] += 1
                if args.limit and totals["decisions_audited"] >= args.limit:
                    stop = True
                    break
        if stop:
            break

    result = {
        "profile": args.profile,
        "enabled_rule_ids": list(enabled),
        "exact_deck": args.exact_deck,
        "policy_build": args.policy_build,
        "policy_enabled": bool(policy.ENABLED),
        "totals": dict(totals),
        "rules": {},
    }
    if args.policy_build:
        result["policy_build_sha256"] = agent_fingerprint(
            args.policy_build,
        )["sha256"]
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
