# The Ladder Is an Ecosystem: Deck-Policy Co-adaptation and a Two-Slot Portfolio

*(Title: 78 characters. Kaggle limit is 80.)*

**Subtitle (short, 135 chars, use this if the field is limited):** Five measured, non-obvious facts about the PTCG ladder, and how a 150 KB imitation policy used them to reach rank 429 / 6,807 (905.8).

**Subtitle (long, 272 chars):** Five measured, non-obvious facts about this ladder (rating-band ecology, search that hurts, an invisible long tail, one-deck policies, a max-of-two portfolio) and how a 150 KB imitation policy used them to reach rank 429 / 6,807 (905.8) with little Pokémon TCG experience.

**Track:** Strategy Category · Simulation result: rank 429 of 6,807 teams, final rating 905.8 (silver line 924.0, bronze 853.7)

---

## 1. What this report claims

Most of what we learned contradicts a reasonable prior. We state the five claims up front; each is backed by a production ladder experiment or a pre-registered A/B test, and the two final submissions were followed for 1,000 post-deadline games each so that every number below is measured, not projected.

1. **The ladder is stratified by archetype (Fig. 9).** Grimmsnarl is 59–64% of opponents in the 800–900 band but only 28–33% in 900–1000, where Ogerpon, Kangaskhan and Dragapult take over. An agent's equilibrium rating is set by whom it meets *one band above*, not by its average win rate.
2. **A behaviour-cloned policy is a policy for one deck.** The same deck scored 751 with a policy cloned from Alakazam players and 840 with one cloned from Grimmsnarl players.
3. **Search on top of imitation hurt by 88 rating points** in a same-deck, same-weights production A/B (Fig. 4).
4. **Rating is lost in the long tail, and the tail was literally invisible**: 43 opposing cards were mapped to the "unknown" token. Daily data refresh, not a better model, fixed it.
5. **Because the team score is max(two submissions), a specialist plus a generalist beats two safe copies.** The specialist (Ogerpon, 89.6% vs Grimmsnarl) won the team score; the generalist (Grimmsnarl) covered the specialist's holes.

## 2. Method in one paragraph (Fig. 6)

For each archetype we play, we download the official Daily Top replays, keep only the **winning side's** `(observation, chosen option)` pairs from teams whose deck has ≥4 copies of the key card, and train a two-tower ranker: a 94-feature state tower and a 48-feature option tower with a 16-d learned card embedding, 128 hidden units each, dot-product logits, softmax over the legal options, cross-entropy. The exported numpy weights are 150 KB, one decision takes under a millisecond, and the agent used a median of 3 s (max 9 s) of its 600 s per game with zero time-outs. The deck we ship is the modal 60-card list of those same winners, so deck and policy are one artefact. Fidelity, not capacity, was the lever: holdout top-1 rose 70.3% → 75.6% (Fig. 5) through more days of data, a larger card vocabulary and a 12-epoch schedule with learning-rate halving after epoch 7, while capacity growth (+0.2 pt), elite-only data (47.9% / 400) and weight averaging (44.4% / 400) were refuted and are off.

## 3. The five claims, with evidence

### 3.1 Rating-band ecology (Claim 1)

We joined the 2,000 final games to opponents' final leaderboard ratings (Fig. 9). Opponent composition is not stationary across bands: below 700 it is a zoo of rare decks and Lucario; 700–800 is Alakazam-heavy (43%); 800–900 is a Grimmsnarl monoculture (59–64%); 900–1000 diversifies into Ogerpon (13–16%), Kangaskhan (11–13%), Dragapult and Alakazam, with Grimmsnarl down to ~30%.

This explains both final ratings quantitatively. The Ogerpon agent wins 70% in 800–900 (where it beats Grimmsnarl 93% of the time, n=258) and 37% in 900–1000 (where it still beats Grimmsnarl 82%, n=101, but goes 0/49 against Kangaskhan mill, 18% against Alakazam and 31% in its own mirror). Its rating therefore oscillated in the 875–909 band for two weeks and froze at 905.8: the exact altitude where the Grimmsnarl supply thins out. The Grimmsnarl agent wins 63% in 700–800 and 49% in 800–900, pinning it near 835. A two-factor model separates the effects (Fig. 10). Multiplying each band's composition by the agent's band-agnostic per-archetype win rates, with no band-specific fitting, reproduces the non-monotonic bump: it predicts 68.6% for the Ogerpon agent in 800–900 (observed 69.8%) and a dip to 46.7% in 900–1000 (observed 36.9%). The residual is a smooth opponent-strength gradient of roughly −10 points per band. Composition, not skill alone, decides where a specialist parks. **The practical rule:** to rise from band B you must beat the composition of band B+1, so deck choice should be made against the *next* band's metagame, not the current one.

### 3.2 One deck, one policy (Claim 2)

Our first Grimmsnarl submission, steered by an Alakazam-trained policy, froze at 751; a Grimmsnarl deck steered by a Grimmsnarl-trained policy reached 840. Locally, an Alakazam policy piloting foreign decks beat a weak sparring wall 88.9% yet lost 74.3% of real games against the same archetype. Every "wall" we built afterwards was a (deck, policy) pair trained on winners of that deck, and no card was ever changed without retraining.

### 3.3 Search hurt (Claim 3)

Two submissions shared deck and `bc_grim2` weights and differed only in an 8-second determinized search that re-ranked the BC top-5 by rollouts. After 210 and 158 games: pure BC 840.0, search 751.6 (Fig. 4), same sign as the local wall (67.1% vs 46.0% / 400 and 200 games). Mechanism: sampled worlds varied only hidden cards while the opponent model was a deterministic argmax, so each world was one line to the end of the game, and 140-step rollouts without a value function compound policy error. Stochastic rollouts made it worse (temperature 0.5 / 1.0 → 50.0% / 34.3%) and a value network with AUC 0.851 still lost its A/B (47.8% / 400). We shipped pure imitation and treat "search helps" as a claim that must be re-earned with a real opponent model.

### 3.4 The invisible tail (Claim 4)

At 210 games our Grimmsnarl agent won its main matchups (mirror 55.7%, Alakazam 58.5%) but sat at 50% because 26 games against a dozen rare decks went 3–23. The cause was mechanical: the 143-card vocabulary mapped 43 opposing cards, 41 of them Pokémon, to index 0, so the policy could not distinguish them. Rebuilding on 20 days of replays (vocabulary 211) lifted the rare-deck bucket to 65% (Fig. 2, right). Data refresh is therefore a correctness requirement: **stop it and new decks become invisible.**

### 3.5 Portfolio under max-of-two (Claim 5)

The final pair is deliberately anti-correlated (Fig. 2): the Ogerpon specialist is 89.6% vs Grimmsnarl (n=394), 76% vs Garchomp, 59% vs rare decks, but 30% vs Alakazam, 12% vs Lopunny, 9% vs Kangaskhan; the Grimmsnarl generalist is 60% Alakazam, 72% Archaludon, 67% Dragapult, 65% rare, 51% mirror, with a single hole at Ogerpon (12%). Each covers the other's worst matchup, and the max operator lets the volatile specialist carry the score while the generalist bounds the downside. Identical builds re-submitted from a fresh 600 converged to the same neighbourhood (905.8 / 902.8 and 843.6 / 834.6), so the split is reproducible.

We also disclose the one decision the process got wrong: a pre-registered "swap if below 650 at the checkpoint" rule fired on a 31-game sample in which the Ogerpon agent had met **zero** Grimmsnarl opponents; the human overrode it, and that build finished at 905.8. Under band ecology a specialist's early games are not a sample of its equilibrium pool.

### 3.6 What did not work, briefly

An explicit one-hit-KO guard (veto promotions/evolutions into a computable KO range, found in 12 of 13 losses vs Lopunny/Ogerpon) survived only as harmless: the same pattern occurred at equal rates in won games and its effect was inconclusive (Δ +0.25 / −1.50 / −4.25 pt). Two further hand rules were refuted (−4.0 pt). The remaining weakness is Kangaskhan mill (we decked out in 23 of 43 losses): the imitated winners rarely faced it, so the policy never learned to ration draws.

## 4. Deck concept (Fig. 8, CSVs attached)

**Deck A — Teal Mask Ogerpon ex (final slot 1, 905.8).** The modal 60 of the 86 winning teams running four Ogerpon: 4 Ogerpon ex, 18 Basic Grass, 2 Grow Grass Energy, Bug Catching Set ×4, Energy Search ×4, Energy Retrieval ×2, Judge ×4, Lillie's Determination ×4, Boss's Orders ×3, Lively Stadium ×2. Ogerpon's ability attaches a Grass energy from hand each turn and draws; Myriad Leaf Shower does 30 plus 30 per energy on **both** Active Pokémon. Every trainer therefore finds energy, recovers energy or disrupts the opponent's hand while we accelerate. The matchup logic is structural: Grimmsnarl ex's Punk Up loads up to five Darkness energies at once, and each energy on their Active adds 30 to our attack, so a 210-HP Basic punishes exactly the acceleration that makes the Stage-2 deck strong. That is the 89.6%. The "≥4 copies" filter was essential: a naive "contains Ogerpon" query pulled in Kangaskhan/Crustle mill lists splashing one Ogerpon and would have trained a mill policy.

**Deck B — Marnie's Grimmsnarl ex / Froslass (final slot 2, 834.6).** The consensus list of the Jul-23 Top-8 Grimmsnarl teams (82 of 111 Grimmsnarl teams ran the identical 60): 4-3-3 Impidimp/Morgrem/Grimmsnarl ex, 4 Munkidori, 2-2 Snorunt/Froslass, Spikemuth Gym ×4, Rare Candy ×3, Buddy-Buddy Poffin ×4, Poké Pad ×4, Petrel ×4. Rare Candy into Punk Up for five energies, Froslass's Freezing Shroud to spread counters and Munkidori to move them, Shadow Bullet (180 + 30 bench) from a 320-HP body. No bad matchup except a faster energy-scaling attacker, hence the flat profile.

**Selection rule.** Not card intuition, which we lack, but (a) share of winning teams in the band we need to beat next (Fig. 7, 9), (b) volume of clean winner data for that exact list, (c) wall results against our own strongest agents. The Ogerpon policy beat our best Grimmsnarl agents 90–99% over six 400-game arms five days before we submitted it; the lesson is that **a sparring partner that beats you is a candidate, not a wall.**

## 5. Process and what we would change

The project was run by one participant directing AI coding agents, with every decision pre-registered in a shared status file (threshold fixed before results, 400-game A/Bs with a "reject only ≤45%" rule) and all results appended to a ledger. This discipline kept five plausible improvements out of the final build. Its cost was scope: imitation cannot exceed its teachers (training centroid ≈ 1,050; gold required 1,131), and we spent the final days raising fidelity by 1.6 pt inside that ceiling instead of finishing the expert-iteration loop (59k distilled decisions, stopped). The band-ecology result suggests the better path: pick the archetype that beats the 1,000+ composition (Dragapult/Kangaskhan/Alakazam-heavy), clone its winners, and only then invest in search with a learned opponent model.

## 6. Reproducibility

Code, agent definitions, the model registry with training metadata, every A/B result (`results/arena.jsonl`), the per-game band analysis (`results/ladder_band_final_20260906.csv`) and the full experiment log are public under MIT at the linked repository. `python -m ptcglab.build v6.0o` rebuilds the exact submission; `bc_extract.py → bc_filter_deck.py --key Ogerpon --min-copies 4 → train_bc.py` reproduces the model. Competition-provided data and the simulator are not redistributed.

*Body ≤ 2,000 words; figures, tables and deck lists excluded per host guidance.*
