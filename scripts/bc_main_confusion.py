"""MAIN(行動選択)型の誤りを OptionType の混同行列に落とす。scratchpad常駐・リポジトリ非変更。
holdout限定(train_bc.py同一10%分離、非学習)。
"""
import argparse, gzip, json, os, sys
from collections import defaultdict, Counter
import numpy as np

ROOT = "/Users/non/git/Pokemon-card-kaggle"
MAX_OPTS = 24

OT_NAMES = {
    0: "NUMBER", 1: "YES", 2: "NO", 3: "CARD",
    7: "PLAY(手札を出す)", 8: "ATTACH(エネ付け)", 9: "EVOLVE(進化)", 10: "ABILITY(特性)",
    11: "DISCARD(トラッシュ)", 12: "RETREAT(にげる)", 13: "ATTACK(ワザ)", 14: "END(ターン終了)",
}


def load_model(name):
    mdir = os.path.join(ROOT, "models", name)
    sys.path.insert(0, mdir)
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import importlib
    vocab_mod = importlib.import_module("policy_vocab")
    P = dict(np.load(os.path.join(mdir, "policy_params.npz")))
    cid2idx = {int(c): i + 1 for i, c in enumerate(vocab_mod.CARD_VOCAB)}
    return P, cid2idx


def is_train_bc_single(sel, act, opts):
    if sel.get("maxCount") != 1 or len(opts) < 2 or not act or len(act) != 1:
        return False
    label = act[0]
    return 0 <= label < min(len(opts), MAX_OPTS)


def describe_opt(sel, cur, opt, PF, cards, attacks):
    t = int(opt.get("type", 0))
    name = OT_NAMES.get(t, str(t))
    feats, cid = PF.option_features(sel, cur, opt, cards, attacks)
    extra = ""
    if cid is not None:
        c = cards.get(cid)
        extra = " card=" + (c.name if c else str(cid))
    aid = opt.get("attackId")
    if aid is not None and aid in attacks:
        a = attacks[aid]
        extra += " attack=" + str(getattr(a, "name", aid)) + " dmg=" + str(a.damage)
    return name + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--examples-per-cell", type=int, default=3)
    args = ap.parse_args()

    P, cid2idx = load_model(args.model)
    from ptcg import policy
    from ptcg import policy_features as PF
    from cg.api import all_card_data, all_attack
    cards = {c.cardId: c for c in all_card_data()}
    attacks = {a.attackId: a for a in all_attack()}

    n = 0
    with gzip.open(args.data, "rt") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            sel, act = r.get("sel"), r.get("act")
            if not sel:
                continue
            opts = sel.get("option") or []
            if is_train_bc_single(sel, act, opts):
                n += 1
    n_hold = n // 10
    perm = np.random.default_rng(0).permutation(n)
    hold_set = set(perm[:n_hold].tolist())
    print("n=%d holdout=%d" % (n, n_hold))

    confusion = Counter()
    total_main = 0
    correct_main = 0
    examples = defaultdict(list)
    single_idx = 0

    with gzip.open(args.data, "rt") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            sel, cur, act = r.get("sel"), r.get("cur"), r.get("act")
            if not sel or not cur or not act:
                continue
            opts = sel.get("option") or []
            if len(opts) < 2:
                continue
            if not is_train_bc_single(sel, act, opts):
                continue
            cur_idx = single_idx
            single_idx += 1
            if cur_idx not in hold_set:
                continue
            if int(sel.get("type", 0)) != 0:
                continue
            s = policy.raw_scores_with(P, cid2idx, sel, cur, opts)
            if s is None:
                continue
            pred_idx = int(np.argmax(s))
            true_idx = int(act[0])
            true_ot = int((opts[true_idx] or {}).get("type", 0))
            pred_ot = int((opts[pred_idx] or {}).get("type", 0))
            total_main += 1
            if true_ot == pred_ot:
                correct_main += 1
            confusion[(true_ot, pred_ot)] += 1
            key = (true_ot, pred_ot)
            if true_ot != pred_ot and len(examples[key]) < args.examples_per_cell:
                me = cur.get("yourIndex", 0)
                players = cur.get("players") or [{}, {}]
                my_active = (players[me].get("active") or [None])[0] if players[me].get("active") else None
                opp_active = (players[1 - me].get("active") or [None])[0] if players[1 - me].get("active") else None
                my_c = cards.get(my_active.get("id")) if my_active else None
                opp_c = cards.get(opp_active.get("id")) if opp_active else None
                my_name = my_c.name if my_c else (my_active.get("id") if my_active else None)
                opp_name = opp_c.name if opp_c else (opp_active.get("id") if opp_active else None)
                desc = {
                    "turn": cur.get("turn"),
                    "my_active": my_name, "my_hp": my_active.get("hp") if my_active else None,
                    "opp_active": opp_name, "opp_hp": opp_active.get("hp") if opp_active else None,
                    "true_choice": describe_opt(sel, cur, opts[true_idx], PF, cards, attacks),
                    "pred_choice": describe_opt(sel, cur, opts[pred_idx], PF, cards, attacks),
                    "n_options": len(opts),
                }
                examples[key].append(desc)

    print("")
    print("MAIN holdout件数=%d 正解=%d top-1=%.1f%%" % (total_main, correct_main, correct_main / max(1, total_main) * 100))
    print("")

    true_totals = Counter()
    for (tt, pt), c in confusion.items():
        true_totals[tt] += c

    print("--- 混同行列 上位20セル(誤りのみ、件数降順) ---")
    print("%-26s%-26s%8s%12s" % ("true_type", "pred_type", "n", "true内シェア"))
    err_cells = sorted(((k, c) for k, c in confusion.items() if k[0] != k[1]), key=lambda kv: -kv[1])
    for (tt, pt), c in err_cells[:20]:
        share = c / max(1, true_totals[tt]) * 100
        print("%-26s%-26s%8s%11.1f%%" % (OT_NAMES.get(tt, str(tt)), OT_NAMES.get(pt, str(pt)), format(c, ","), share))

    print("")
    print("--- true_typeごとの件数・正答率 ---")
    for tt in sorted(true_totals, key=lambda k: -true_totals[k]):
        c_ok = confusion.get((tt, tt), 0)
        print("%-26s%8s%9.1f%%" % (OT_NAMES.get(tt, str(tt)), format(true_totals[tt], ","), c_ok / true_totals[tt] * 100))

    print("")
    print("--- RETREAT/ATTACK/END に関わる全セル(順位に関わらず全件) ---")
    of_interest = {12, 13, 14}
    for (tt, pt), c in sorted(confusion.items(), key=lambda kv: -kv[1]):
        if tt == pt:
            continue
        if tt in of_interest or pt in of_interest:
            share = c / max(1, true_totals[tt]) * 100
            print("%-26s%-26s%8s%11.1f%%" % (OT_NAMES.get(tt, str(tt)), OT_NAMES.get(pt, str(pt)), format(c, ","), share))

    retreat_to_attack = confusion.get((12, 13), 0)
    attack_to_retreat = confusion.get((13, 12), 0)
    print("")
    print("RETREAT->ATTACK(にげるべきなのに攻撃扱い)件数=%d" % retreat_to_attack)
    print("ATTACK->RETREAT(攻撃すべきなのに退却扱い)件数=%d" % attack_to_retreat)

    print("")
    print("--- 上位誤りセルの代表例 ---")
    for (tt, pt), c in err_cells[:5]:
        print("")
        print("[%s -> %s] n=%d" % (OT_NAMES.get(tt, str(tt)), OT_NAMES.get(pt, str(pt)), c))
        for ex in examples[(tt, pt)]:
            print("  turn=%s 自分=%s(hp=%s) 相手=%s(hp=%s) n_opts=%s 正解=[%s] 予測=[%s]" % (
                ex["turn"], ex["my_active"], ex["my_hp"], ex["opp_active"], ex["opp_hp"],
                ex["n_options"], ex["true_choice"], ex["pred_choice"]))


if __name__ == "__main__":
    main()
