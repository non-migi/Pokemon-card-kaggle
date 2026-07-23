"""公式top decision pairsに対する専門家ルールの発火・教師一致率を監査する。"""

import argparse
import gzip
import hashlib
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


def _injected_rule_actions(scores, option_count: int, proposals,
                           rule_mode: str) -> set[tuple[tuple[int, ...], str]]:
    """実行時と同じ全proposal・注入枠競合で、実注入の帰属を返す。"""
    if rule_mode == "shadow":
        return set()
    forbidden = (
        expert_rules.forbidden_actions(proposals)
        if rule_mode == "enforce" else set()
    )
    if rule_mode == "enforce":
        hard = expert_rules.best_hard(proposals)
        if hard is not None and hard.action not in forbidden:
            return set()  # main.agentと同じくhardを直接実行し、探索へ入らない。
    injected_actions = {}
    bc_search._candidate_actions(
        scores, option_count, proposals, rule_mode, {},
        forbidden_actions=forbidden,
        injected_actions=injected_actions,
    )
    return {
        (tuple(action), str(rule_id))
        for action, rule_ids in injected_actions.items()
        for rule_id in rule_ids
    }


def _injected_example(path: str, row_number: int, row_sha256: str, row: dict,
                      proposal, rank: int, teacher: tuple[int, ...],
                      matches: bool) -> dict:
    """非公開札を増やさず、注入局面を再発見できる最小provenanceを返す。"""
    cur = row.get("cur") or {}
    players = cur.get("players") or []
    your_index = int(cur.get("yourIndex", 0) or 0)
    opp = players[1 - your_index] if len(players) == 2 else {}
    field = (opp.get("active") or []) + (opp.get("bench") or [])
    visible = {"sel": row.get("sel"), "cur": cur}
    digest = hashlib.sha256(
        json.dumps(visible, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "source": path,
        "row_number": row_number,
        "row_sha256": row_sha256,
        "observation_sha256": digest,
        "rule_id": proposal.rule_id,
        "rule_kind": proposal.kind,
        "bc_rank": rank,
        "rule_action": list(proposal.action),
        "teacher_action": list(teacher),
        "teacher_match": bool(matches),
        "teacher_team": row.get("team"),
        "turn": cur.get("turn"),
        "your_index": your_index,
        "opponent_active_id": (
            (opp.get("active") or [{}])[0].get("id")
            if opp.get("active") else None
        ),
        "opponent_field_ids": [
            card.get("id") for card in field if isinstance(card, dict)
        ],
    }


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
    ap.add_argument(
        "--rule-mode", choices=("shadow", "candidate", "enforce"),
        default="candidate",
        help="実注入を再現する実行mode（default: candidate）",
    )
    ap.add_argument(
        "--injected-example-limit", type=int, default=0,
        help="実注入局面のprovenanceを最大N件出力（0=出力しない）",
    )
    args = ap.parse_args()
    if args.injected_example_limit < 0:
        ap.error("--injected-example-limitは0以上")

    if args.policy_build and not policy.ENABLED:
        raise RuntimeError(f"BCモデルをロードできない: {MODULE_ROOT}")

    enabled = expert_rules.validate_config(args.profile, "shadow", args.rules)
    exact_deck = _read_deck(args.exact_deck)
    totals = Counter()
    per_rule: dict[str, Counter] = {rule_id: Counter() for rule_id in enabled}
    injected_examples = []
    stop = False
    for path in args.pairs:
        with gzip.open(path, "rt") as f:
            for row_number, line in enumerate(f, start=1):
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
                option_count = len((obs.get("select") or {}).get("option") or [])
                injected_rule_actions = (
                    _injected_rule_actions(
                        scores, option_count, proposals, args.rule_mode,
                    )
                    if scores is not None else set()
                )
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
                        injected = int(
                            (tuple(proposal.action), str(proposal.rule_id))
                            in injected_rule_actions
                        )
                        bucket["candidate_injected"] += injected
                        if injected:
                            bucket[
                                "candidate_injected_teacher_match"
                                if matches else "candidate_injected_teacher_disagree"
                            ] += 1
                            if len(injected_examples) < args.injected_example_limit:
                                injected_examples.append(_injected_example(
                                    path, row_number,
                                    hashlib.sha256(line.encode()).hexdigest(),
                                    row, proposal, rank, teacher, matches,
                                ))
                if args.limit and totals["decisions_audited"] >= args.limit:
                    stop = True
                    break
        if stop:
            break

    result = {
        "profile": args.profile,
        "rule_mode": args.rule_mode,
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
    if args.injected_example_limit:
        result["candidate_injected_examples"] = injected_examples
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
