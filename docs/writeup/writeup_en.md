# Imitate the Winners of the Deck You Play: Deck–Policy Co-adaptation for the PTCG AI Battle Challenge

**Subtitle:** How a solo participant working with AI coding agents, and with little Pokémon TCG experience, reached rank 429 / 6,807 (rating 905.8) with a 150 KB behaviour-cloning policy, and what 1,000 post-deadline games per submission say about it.

**Track:** Strategy Category · Simulation result: rank 429 of 6,807 teams, final rating 905.8 (bronze zone; silver line 924.0)

---

## 1. Summary

Our final agent plays a Teal Mask Ogerpon ex deck with a pure behaviour-cloning (BC) policy trained only on the winner's decisions in official "Daily Top" replays of teams that played that same deck. Inference is a numpy two-tower ranker that scores each legal option in under a millisecond; median thinking time per game was 3 s out of a 600 s budget. The second final slot held a Grimmsnarl ex agent built the same way.

Three findings drove the design, each established with a pre-registered A/B test or a production ladder experiment:

1. **A BC policy is only strong on the deck it was trained on.** Deck and policy must be selected as a pair.
2. **Determinized search on top of BC hurt in production** (−88 rating points, same deck, same model).
3. **The long tail of out-of-distribution opponents, not the main matchups, is where rating is lost**, and it is fixed by refreshing training data daily so that new cards enter the vocabulary.

Post-deadline convergence over ~1,000 games per submission (Fig. 1) and independent re-runs of identical builds (905.8 / 902.8 for Ogerpon; 843.6 / 834.6 for Grimmsnarl) show the ratings are reproducible, not lucky draws.

## 2. Problem framing

Three properties of the environment shaped everything else.

- **Hidden information and long horizons.** A game has ~140 decisions per side (median 10 turns); one move is chosen from a variable set of typed legal options (play, attach, evolve, ability, attack, retreat, multi-select searches).
- **Ratings converge.** The ladder is a Gaussian rating system starting at 600 with self-similar matchmaking. Early scores are noise: our first Alakazam agent read 920.7 after 78 games and 795.7 after 315. We therefore never judged a submission before 80–100 games, and we measured how ratings behave after the deadline (Fig. 1).
- **The team score is the max over the two latest submissions.** This makes an uncorrelated pair (a specialist plus a generalist) worth more than two copies of the safest agent.

## 3. Approach and how it evolved

### 3.1 From search to imitation

We started with a hand-written heuristic agent and a determinized flat Monte-Carlo search (sample hidden cards, roll out with the heuristic). It plateaued around 750. The breakthrough was behaviour cloning from official replays: extract every `(observation, chosen option)` pair of the **winning side** of Daily Top episodes and train a ranker.

**Model** (Fig. 6). A state tower (94 features: both players' hand, bench, prizes, energies, deck and discard sizes, prompt type and turn context) and an option tower (48 features: option type, area, card type, attack cost/damage, target HP, plus a 16-dimensional learned card embedding) each map to a 128-unit hidden layer; the dot product gives a logit and a softmax over the legal options is trained with cross-entropy. Multi-select prompts use top-N. The exported weights are 150 KB and run in numpy, so the agent is immune to time-outs.

**Fidelity is the constraint.** Holdout top-1 accuracy rose from 70.3% to 75.6% across the model family (Fig. 5) as we added days of data, expanded the card vocabulary and adopted a 12-epoch schedule with learning-rate halving after epoch 7. The final Grimmsnarl model beat its 13-day predecessor 56.9% / 400 [52.0–61.6] in a same-deck mirror, the first daily refresh whose confidence interval cleared 50%.

### 3.2 Deck × policy co-adaptation (the central claim)

Our first Grimmsnarl submission, steered by an Alakazam-trained policy, froze at 751; a Grimmsnarl deck steered by a Grimmsnarl-trained policy reached 840. Locally, an Alakazam policy piloting other decks won 88.9% against a weak wall but 25.7% against real opponents. The lesson generalised: **a BC policy is a policy for one deck**, so every sparring "wall" we built was a (deck, policy) pair trained on winners of that deck, and deck choice was made by asking "which archetype's winners can we imitate best, and whom does it beat in the band we will be matched in?"

### 3.3 Search hurts: a production A/B test

Two submissions with identical deck and identical `bc_grim2` weights differed only in whether an 8-second determinized search re-ranked the BC top-5. After 210 and 158 games the pure-BC agent sat at 840.0 and the search agent at 751.6 (Fig. 4), matching the sign of the local wall result (67.1% vs 46.0%). Diagnosis: worlds sampled only hidden cards while the opponent model was a deterministic argmax, so each world was a single line to game end; with no value network, 140-step rollouts compound policy error. Softmax-temperature rollouts (0.5 / 1.0) made it worse (50.0% / 34.3%), and a value network with AUC 0.851 still lost its A/B (47.8% / 400). We shipped pure BC.

### 3.4 The long tail is where rating is lost

At 210 games our Grimmsnarl agent won its main matchups (mirror 55.7%, Alakazam 58.5%) yet sat at 50% overall because 26 games against a dozen rare decks went 3–23. Cause: the 143-card vocabulary mapped 43 opposing cards (41 of them Pokémon) to the "unknown" index, so the policy literally could not see them. Rebuilding with 20 days of replays raised the vocabulary to 211 and the same bucket recovered to 65% (Fig. 2, right). Daily data refresh is therefore not a nicety; **stopping it makes new decks invisible.**

### 3.5 An explicit guard, and why it stayed switched on

Reading every loss against Lopunny and Ogerpon showed that in 12 of 13 losses our agent promoted or evolved a key Pokémon into a one-hit-KO range computable from the opponent's visible energy. We added two rules (GR001 promotion/switch, GR002 evolution) that veto such options before the BC argmax. Pre-registered tests were inconclusive (Δ +0.25 / −1.50 / −4.25 pt under a floor effect; intervention rate 0.022%), and the same pattern occurred at equal rates in won games, so we report it as a hypothesis that survived only as harmless. Two further rules (attacker priority, evolution-line preservation) were refuted (−4.0 pt) and are off.

### 3.6 Archetype switch

Tracking the official Daily Top (Fig. 7), Grimmsnarl's share of winning teams went 33.6% → 62.7% → 41.9%, while Teal Mask Ogerpon appeared at 0% and rose to ~9–12%. We trained `bc_ogerpon` on 391k winner decisions from 86 teams as a *sparring wall*, and it beat our strongest Grimmsnarl agents 90–99% over six 400-game arms. We submitted it as a ladder trial on Aug 15, where it went 35–19 (64.8%) and reached our best rating to date. It became the final slot 1.

## 4. Evidence of consistency and robustness

**Repeatability.** Identical builds re-submitted from a fresh 600 rating converged to the same neighbourhood: Ogerpon 905.8 and 902.8; Grimmsnarl 843.6 and 834.6. Fig. 1 shows both final submissions over 15 days of post-deadline play: swings of ±100 inside the first 50 games, then a band of roughly 70 points as the opponent pool itself re-sorted, and a stable ordering between the two agents throughout.

**Matchup profile, disclosed honestly** (Fig. 2, 1,000 games each). The Ogerpon agent is a specialist: 89.6% against Grimmsnarl (n=394, 39% of its games), 76% against Garchomp, 59% against rare decks, but 30% against Alakazam, 12% against Lopunny and 9% against Kangaskhan mill. The Grimmsnarl agent is a generalist: 60% Alakazam, 72% Archaludon, 67% Dragapult, 65% rare decks, 51% mirror, with a single hole at Ogerpon (12%). The pair is deliberately anti-correlated: each covers the other's worst matchup.

**Why the specialist scored higher.** The rating band around 850–950 was ~40% Grimmsnarl in our sample, so a 90% edge on that slice outweighs sub-40% results elsewhere. This is a metagame bet, not a claim of universal strength, and it is exactly why we kept the generalist in the other slot. The Kangaskhan mill matchup (we decked out in 23 of 43 losses) is the clearest remaining target: the imitated winners rarely faced it, so the policy never learned to ration draws.

**Stability under time and failure.** Median 3 s and maximum 9 s of the 600 s budget per game across the 2,000 final games, no time-outs, and every layer of the runtime falls back to the next on exception (Fig. 6).

## 5. Deck concept (Fig. 8, CSVs attached)

**Deck A — Teal Mask Ogerpon ex (final slot 1).** The modal 60 of the 86 winning teams that ran four copies of Ogerpon: 4 Ogerpon ex, 18 Basic Grass Energy, 2 Grow Grass Energy, and an engine of Bug Catching Set ×4, Energy Search ×4, Energy Retrieval ×2, Judge ×4, Lillie's Determination ×4, Boss's Orders ×3, Lively Stadium ×2. The plan is single-minded: Ogerpon's ability attaches a Grass energy from hand each turn and draws a card, and Myriad Leaf Shower does 30 plus 30 per energy on both Active Pokémon, so every trainer either finds energy, recovers energy, or disrupts the opponent's hand while we accelerate. A "≥4 copies" filter mattered: a naive "contains Ogerpon" query pulled in Kangaskhan/Crustle mill lists that splash one Ogerpon, which would have trained the wrong policy. Against Grimmsnarl the matchup is structural: Grimmsnarl ex's Punk Up loads up to five Darkness energies onto the board, and every energy on their Active Pokémon adds 30 to our attack, so a Basic 210-HP attacker punishes exactly the acceleration that makes the Stage-2 deck strong. The 89.6% figure reflects that.

**Deck B — Marnie's Grimmsnarl ex / Froslass (final slot 2).** The consensus list of the Top-8 Grimmsnarl teams on Jul 23 (82 of 111 Grimmsnarl teams ran the identical 60): 4-3-3 Impidimp/Morgrem/Grimmsnarl ex, 4 Munkidori, 2-2 Snorunt/Froslass, Spikemuth Gym ×4, Rare Candy ×3, Buddy-Buddy Poffin ×4, Poké Pad ×4, Petrel ×4. Its game plan: evolve early with Rare Candy, let Punk Up fetch five Darkness energies at once, spread damage counters with Froslass's Freezing Shroud and relocate them with Munkidori, and close with Shadow Bullet (180 plus 30 to the bench) from a 320-HP body. The plan has no bad matchup except a faster energy-scaling attacker, which explains the broad but unspectacular profile.

**How decks were chosen.** Not by our card knowledge, which is thin, but by (a) share of winning teams in the target band, (b) how much clean training data exists for that exact list, and (c) local wall results against our own strongest agents. Deck lists were frozen together with the policy; we never edited a card without re-training.

## 6. What we would do differently

- **BC has a ceiling at its teachers' level.** The training centroid was rating ~1,050 and gold required 1,131; we spent the last days raising fidelity by 1.6 pt inside that ceiling. Expert iteration or self-play (we reached 59k distilled decisions before stopping) was the route above it.
- **A wall that beats you is a candidate, not a wall.** The Ogerpon policy dominated our best agents five days before we submitted it.
- **Do not act on 31 games.** A pre-registered "swap if below 650" rule fired on 31 games and would have removed the eventual best agent; the human overrode it, and the build later reached 905.8.
- **Measure only what the design can resolve.** 400-game A/Bs have ±5 pt intervals; we ran too many experiments that could not distinguish 2-pt effects.

## 7. Reproducibility

Code, agent definitions, model registry with training metadata, every A/B result (`results/arena.jsonl`) and the full experiment log are public under MIT at the linked repository. `python -m ptcglab.build v6.0o` rebuilds the exact submission; `scripts/bc_extract.py → bc_filter_deck.py --key Ogerpon --min-copies 4 → train_bc.py` reproduces the model. Competition-provided data and the simulator are not redistributed.

*Word count target: ≤ 1,950 (body only; figures, tables and deck lists excluded per host guidance).*
