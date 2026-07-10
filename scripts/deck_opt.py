"""進化的デッキ最適化。

集団のデッキ同士をヒューリスティックagentで対戦させ、勝率上位を選抜・変異して回す。

使い方:
    .venv/bin/python scripts/deck_opt.py --gens 40 --pop 24 -j 8 [--resume]

出力:
    decks/best.csv         現在の最良デッキ
    decks/pop/deck_XX.csv  現世代の集団
    decks/log.txt          世代ごとのログ
"""

import argparse
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_lib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECKS_DIR = os.path.join(ROOT, "decks")
POP_DIR = os.path.join(DECKS_DIR, "pop")

_worker_ready = False


def _init_worker():
    global _worker_ready
    import logging

    logging.disable(logging.WARNING)
    sub = os.path.join(ROOT, "submission")
    if sub not in sys.path:
        sys.path.insert(0, sub)
    _worker_ready = True


def _play_pair(args):
    """デッキAとBを2戦(先後入替)し、Aのスコア(0..2)を返す。"""
    deck_a, deck_b = args
    from kaggle_environments import make
    from cg.api import to_observation_class
    from ptcg import heuristics

    def make_agent(deck):
        def agent(obs_dict):
            obs = to_observation_class(obs_dict)
            if obs.select is None:
                return list(deck)
            try:
                return heuristics.choose(obs)
            except Exception:
                n = len(obs.select.option)
                k = max(obs.select.minCount, min(obs.select.maxCount, n))
                return list(range(k))
        return agent

    score = 0.0
    for swap in (False, True):
        env = make("cabt")
        a, b = make_agent(deck_a), make_agent(deck_b)
        env.run([b, a] if swap else [a, b])
        r = env.state[1 if swap else 0].reward
        score += {1: 1.0, 0: 0.5, -1: 0.0}.get(r if r is not None else -1, 0.0)
    return score


def evaluate_population(pop, pairs_per_deck, pool, rng):
    """集団内ランダムマッチングで各デッキの勝率を出す。"""
    matchups = []
    for i in range(len(pop)):
        for _ in range(pairs_per_deck):
            j = rng.randrange(len(pop) - 1)
            j = j if j < i else j + 1
            matchups.append((i, j))
    tasks = [(pop[i], pop[j]) for i, j in matchups]
    results = list(pool.map(_play_pair, tasks, chunksize=2))
    score = defaultdict(float)
    games = defaultdict(int)
    for (i, j), s in zip(matchups, results):
        score[i] += s
        games[i] += 2
        score[j] += 2 - s
        games[j] += 2
    return [score[i] / max(games[i], 1) for i in range(len(pop))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=40)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--pairs", type=int, default=15, help="1デッキあたりのペア数/世代(1ペア=2戦)")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--resume", action="store_true", help="decks/pop/から再開")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(POP_DIR, exist_ok=True)
    sample_deck = deck_lib.load_deck(os.path.join(ROOT, "submission", "deck.csv"))

    if args.resume and os.path.exists(os.path.join(POP_DIR, "deck_00.csv")):
        pop = []
        for i in range(args.pop):
            p = os.path.join(POP_DIR, f"deck_{i:02d}.csv")
            if os.path.exists(p):
                pop.append(deck_lib.load_deck(p))
        print(f"resumed: {len(pop)} decks")
        while len(pop) < args.pop:
            pop.append(deck_lib.generate_deck(rng))
    else:
        pop = [list(sample_deck)]
        while len(pop) < args.pop:
            pop.append(deck_lib.generate_deck(rng))

    log_path = os.path.join(DECKS_DIR, "log.txt")
    with ProcessPoolExecutor(max_workers=args.j, initializer=_init_worker) as pool:
        for gen in range(args.gens):
            t0 = time.time()
            fitness = evaluate_population(pop, args.pairs, pool, rng)
            order = sorted(range(len(pop)), key=lambda i: fitness[i], reverse=True)
            elite = [pop[i] for i in order[: max(4, args.pop // 4)]]

            # 最良デッキ vs サンプルデッキのベンチ(20ペア=40戦)
            bench_tasks = [(elite[0], sample_deck)] * 20
            bench = sum(pool.map(_play_pair, bench_tasks)) / 40

            dt = time.time() - t0
            top_fit = fitness[order[0]]
            line = (f"gen {gen:03d} best_fit={top_fit:.3f} vs_sample={bench:.2f} "
                    f"({dt:.0f}s) {deck_lib.describe(elite[0])[:160]}")
            print(line, flush=True)
            with open(log_path, "a") as f:
                f.write(line + "\n")

            # 保存
            deck_lib.save_deck(elite[0], os.path.join(DECKS_DIR, "best.csv"))
            for i, d in enumerate(pop):
                deck_lib.save_deck(d, os.path.join(POP_DIR, f"deck_{i:02d}.csv"))

            # 次世代: エリート + 変異 + 交叉 + 新規
            nxt = list(elite)
            while len(nxt) < args.pop - 2:
                if rng.random() < 0.25 and len(elite) >= 2:
                    a, b = rng.sample(elite, 2)
                    child = deck_lib.crossover(a, b, rng)
                else:
                    child = deck_lib.mutate(rng.choice(elite), rng)
                nxt.append(child)
            while len(nxt) < args.pop:
                nxt.append(deck_lib.generate_deck(rng))  # 多様性の注入
            pop = nxt

    print("done. best -> decks/best.csv")


if __name__ == "__main__":
    main()
