# Testing efficiency for ChessSI: statistical and experimental-design methods to cut CPU per decision

Research notes, 2026-10-24, by a Claude Code research agent (Claude Opus 5.5). Scope: methods from statistics,
clinical trials, A/B testing and AutoML that could reduce the games (CPU) needed to decide whether a ChessSI
change helps, checked against computer-chess prior art.

How this was done, and its limits:
- Code read from read-only shallow clones (2026-10-24): fishtest `5a8a229` (2026-10-13), OpenBench `dd03aaf`
  (2026-10-21), fastchess `ebfd64c` (2026-10-11), chess-tuning-tools `a88f947` (2025-10-27), and an OpenBench
  fork (crippa1337, 2024-01-13).
- TalkChess, arXiv and hardy.uhasselt.be (Van den Bergh's papers) could not be fetched from this container (DNS
  blocked), so claims from them come from search-result snippets and are marked "(snippet)". Read them in full
  before citing them as settled.
- "Own simulation" and "own retrospective" numbers were computed for these notes. The simulations use the Brownian
  (Gaussian) approximation of fastchess's normalized pentanomial GSPRT. The per-pair standardized drift is
  t = sqrt(2) x nElo x ln(10)/800, as in fastchess `sprt.cpp`, with Wald bounds +/-2.944 (alpha = beta = 0.05).
  The retrospective analyses read the 3,661 games (1,027 colour-reversed pairs, 10+0.1, current adjudication) in
  this container's `engines/sprt.pgn`. That file holds the cloud runs, not the PC's 32,743-game file, so the
  results should be rerun on the larger file. Scripts are in
  `/tmp/claude-0/-home-user-ChessSI/5a391c4c-6f31-51d1-9398-4410992b43ba/scratchpad/sim/` (session scratchpad; the
  formulas are restated below so the numbers can be reproduced).

## 1. What is the state of the art in fishtest / OpenBench / fastchess statistics, and what is not used yet? ("Known" baseline)

### Takeaway
All three frameworks use the same core statistic: Van den Bergh's normalized-Elo GSPRT on pentanomial
colour-reversed game pairs. On top of it, fishtest adds STC/LTC presets, median-unbiased Elo after an SPRT, and
"classic" SPSA. ChessSI's `sprt.sh` already runs that statistic, since fastchess's default model is
"normalized" with pentanomial counts. What none of the tools implement is any decision-theoretic or Bayesian
stopping rule, the 2-SPRT, factorial designs, racing, engine-specific opening selection, debiased truncation, or
any SPSA variant beyond classic. Those gaps are where the candidates in section 7 come from.

### Cited Findings
- fishtest's SPRT supports three Elo models: BayesElo (legacy), logistic and normalized. The normalized model
  computes the LLR with a "t_value" statistic (a GSPRT) on the pentanomial pdf, with N = game pairs —
  [fishtest LLRcalc.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/stats/LLRcalc.py),
  [stat_util.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/stats/stat_util.py)
- Pentanomial results are the frequencies of the pair outcomes LL, LD+DL, LW+DD+WL, DW+WD and WW —
  [LLRcalc.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/stats/LLRcalc.py)
- After an SPRT stops, fishtest computes "median unbiased Elo estimates for SPRT tests, as well as the
  corresponding confidence intervals" from a Brownian-motion model. Its code warns: "The algorithms only work
  correctly for small Elo differences" —
  [fishtest sprt.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/stats/sprt.py),
  [brownian.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/stats/brownian.py)
- fishtest's preset bounds (normalized Elo) are Standard STC [0.0, 2.0], Standard LTC [0.5, 2.5], and
  Non-regression STC and LTC [-1.75, 0.25] —
  [tests_run.html.j2](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/templates/tests_run.html.j2)
- fishtest workers run fastchess with `-repeat -games 2`, `-report penta=true` and the book in `order=random`.
  With adjudication on, they add only draw adjudication (`movenumber=34 movecount=8 score=20`); there is no
  `-resign` flag. Each worker's time control is scaled to its measured speed —
  [fishtest worker/games.py](https://github.com/official-stockfish/fishtest/blob/master/worker/games.py)
- fishtest SPSA accepts a single algorithm, "classic". Per parameter, c_k = c_end x N^gamma / k^gamma and
  a_k = r_end x c_end^2 x (A+N)^alpha / (A+k)^alpha. Defaults are alpha 0.602, gamma 0.101 and
  A = 0.1 x (games/2). Each worker gets a random +/-1 flip per parameter and plays theta + c x flip against
  theta - c x flip; the iteration count advances by game pairs —
  [spsa_workflow.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/spsa_workflow.py),
  [spsa_handler.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/spsa_handler.py)
- OpenBench: `PentanomialSPRT` "is taken directly from Fishtest" and "Implements
  https://hardy.uhasselt.be/Fishtest/normalized_elo_practical.pdf"; `TrinomialSPRT` uses BayesElo. SPSA runs
  have BULK/BATCHED reporting, SINGLE/MULTIPLE distribution, and alpha, gamma, iterations, pairs_per and a_ratio
  fields — [OpenBench stats.py](https://github.com/AndyGrant/OpenBench/blob/master/OpenBench/stats.py),
  [models.py](https://github.com/AndyGrant/OpenBench/blob/master/OpenBench/models.py)
- fastchess offers the SPRT models "normalized" (the default, `model_ = "normalized"`), "logistic" and
  "bayesian". With `games=2` the default build sets `report_penta = true` and computes the LLR from pentanomial
  counts. The bayesian model cannot be used with pentanomial counts —
  [fastchess sprt.cpp](https://github.com/Disservin/fastchess/blob/master/app/src/matchmaking/sprt/sprt.cpp),
  [sprt.hpp](https://github.com/Disservin/fastchess/blob/master/app/src/matchmaking/sprt/sprt.hpp),
  [tournament.hpp](https://github.com/Disservin/fastchess/blob/master/app/src/types/tournament.hpp),
  [sanitize.cpp](https://github.com/Disservin/fastchess/blob/master/app/src/cli/sanitize.cpp)
- fastchess prints nElo +/- error from fixed-sample formulas. A grep of its `elo/` and `sprt/` code found no
  optional-stopping (median-unbiased) correction —
  [elo_pentanomial.cpp](https://github.com/Disservin/fastchess/blob/master/app/src/matchmaking/elo/elo_pentanomial.cpp)
- Normalized Elo is roughly logistic Elo / sqrt(1 - draw ratio) for small differences with a balanced book —
  [vdbergh/simul](https://github.com/vdbergh/simul) (README, via search)
- Common bounds include [0, 2] for Stockfish STC; "bounds are generally looser for weaker engines" —
  [chessprogramming.org SPRT](https://chessprogramming.org/SPRT) (snippet)
- An SPRT's expected length is largest when the true value sits midway between its bounds (Van den Bergh) —
  [TalkChess "SPRT questions"](https://talkchess.com/viewtopic.php?p=624619) (snippet)
- SPRT Elo estimates are unbiased only when all patches, passed and failed, are counted —
  [Fishtest FAQ](https://github.com/official-stockfish/fishtest/wiki/Fishtest-faq) (snippet)
- Tuning outside the frameworks: chess-tuning-tools does Gaussian-process Bayesian optimization (bayes-skopt)
  and "Scoring matches using a Bayesian-pentanomial model for paired openings" (a Dirichlet posterior on the
  counts) — [chess-tuning-tools README](https://github.com/kiudee/chess-tuning-tools),
  [tune/local.py](https://github.com/kiudee/chess-tuning-tools/blob/master/tune/local.py)
- ChessSI's `scripts/sprt.sh` passes `-sprt elo0 elo1 alpha beta` with no `model=`, and uses `-games 2 -repeat`,
  random UHO order, `-resign movecount=3 score=400 twosided=true` and `-draw movenumber=40 movecount=8 score=10`.
  Its defaults are ELO0=0, ELO1=5, ALPHA=BETA=0.05, and it suggests TC=60+0.6 to confirm winners —
  [scripts/sprt.sh @ claude/artifact-access-issue-ug96zp](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/scripts/sprt.sh)
- One ChessSI run reported both scales: RFP on `684badc` reached Elo +31.4 +/- 11.6 and nElo +44.6 +/- 16.4 over
  1,730 games —
  [docs/IDEAS.md @ claude/artifact-access-issue-ug96zp](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)

### Inferences
- ChessSI's SPRT is already the state-of-the-art statistic, so its bounds [0, 5] are in **nElo**. It differs
  from fishtest in four ways: wider bounds (reasonable for a weaker, fast-moving engine), resign adjudication
  (which fishtest does not use), LTC confirmation only on request, and plain rather than median-unbiased Elo in
  the log.
- **What a decision costs today** (own simulation, [0, 5] nElo, alpha = beta = 0.05), as expected game pairs by
  true effect: 0 nElo: 13,045. 1: 17,148. 2: 21,112. 2.5: 21,519 (the worst case). 3: 20,958. 4: 17,115.
  5: 13,050. 7.5: 7,135. 10: 4,790. 15: 2,880. A fixed-sample test with the same error rates needs 26,129 pairs.
  The single nElo/Elo ratio above (about 1.42) maps ChessSI's "+3 to +10 Elo" ideas to roughly 4.3-14 nElo,
  which is 15,000-3,000 pairs (30,000-6,000 games).
- Assuming 2,500 games/hour on 20 cores scales to about 1,600 games/hour on Claude Code's 13 cores, a null idea
  takes about 16 h, a +3 Elo idea about 20 h, and a +10 Elo idea about 4 h. That matches the brief's
  "1,000-10,000+ games" for today's mix.
- Consistency check: the SEE retest (+22.2 Elo, so about 31 nElo at that ratio) predicts about 1,100 pairs
  (2,200 games); the log shows 2,212 games.
- Where the CPU goes: as ideas shrink, most CPU goes to ideas near the middle of the bounds, which are the ones
  whose accept/reject decision matters least. That is the leverage for decision-theoretic stopping (section 3)
  and for sharing games across ideas (section 4).

### Gaps
- Van den Bergh's normalized-Elo papers (hardy.uhasselt.be) and the TalkChess threads were not readable here;
  they are cited via snippets only.
- fishtest's STC-then-LTC workflow rule was not checked in its wiki; only the presets were seen in code.
- The nElo/Elo ratio of 1.42 comes from one ChessSI test. It depends on the book and the draw rate, so read
  nElo straight from fastchess's output instead.

## 2. Which variance-reduction methods could apply (CUPED, stratification, importance sampling of openings, pairing)?

### Takeaway
Colour-reversed pairing already plays the role of CUPED for any pre-game covariate. By symmetry, such a
covariate cannot predict the pair outcome beyond the small variation of the treatment effect itself, so
CUPED-style regression or post-stratification on opening features should gain nearly nothing. What does vary by
opening is the **variance and sensitivity** of the pair outcome. The usable lever is therefore to select or
weight openings by information (importance sampling, Neyman-style allocation), which is the principled form of
ChessSI's "unbalanced openings" lead. Post-treatment covariates (in-game scores) bring bias, which is the lesson
of the truncation failure.

### Cited Findings
- CUPED (Deng, Xu, Kohavi, Walker, WSDM 2013) uses pre-experiment data to cut variance, about 50% at Bing.
  The covariate must be unaffected by the treatment, and for a boolean covariate CUPED is equivalent to
  stratification — [exp-platform.com CUPED](https://exp-platform.com/cuped/),
  [Statsig variance reduction docs](https://docs.statsig.com/stats-engine/variance_reduction),
  [Kameleoon summary](https://kameleoon.com/blog/accelerate-experiment-results-cuped)
- CUPED's gains are capped by how well pre-experiment data predicts the outcome; CUPAC uses ML predictions as
  covariates — [arXiv 2410.09027](https://www.arxiv.org/pdf/2410.09027) (snippet)
- The empirical variance of colour-reversed pairs is smaller than trinomial variance predicts, especially with
  unbalanced openings (Van den Bergh's pentanomial observation, discussed by Laskos) —
  [TalkChess "Properties of unbalanced openings using Bayeselo model"](https://talkchess.com/viewtopic.php?p=684227)
  (snippet)
- Laskos concluded that unbalanced openings are very useful only at very high draw rates (above 70-75%), and only
  with colour-reversed pairs scored with pentanomial variance —
  [TalkChess "Opening testing suites efficiency"](https://talkchess.com/viewtopic.php?p=720979) (snippet)
- In UHO, the eval window (part of each file name) sets the draw rate; Pohl suggests 45-60% draws. UHO 2024 was
  filtered with KomodoDragon 3.3 evals — [sp-cc.de anti-draw openings](https://www.sp-cc.de/anti-draw-openings.htm),
  [UHO 2024](https://www.sp-cc.de/uho_2024.htm)
- ChessSI binned 5,072 pairs by its own |eval| of the opening. Signal per pair, relative to its run, was 0.63x
  below 0.3 pawns, about 0.8-1.05x at 0.3-0.7, 1.29x at 0.7-0.8 and 1.46x at 0.8-1.0 (about +/-0.2 each). UHO
  openings never repeat across tests (2.6 million in the book) —
  [docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- Two-phase sampling with Neyman allocation uses a cheap first-phase variable to allocate the expensive second
  phase — [PracTools dub](https://search.r-project.org/CRAN/refmans/PracTools/html/dub.html),
  [optimall vignette](https://ftp.fau.de/cran/web/packages/optimall/vignettes/Multiwave-Estimation.html)
- Own retrospective (1,027 pairs, binned by the game's first reported |eval|): pair-score variance on the 0-2
  scale, with pair counts, was 0.305 (0-0.25 pawns, n=67), 0.308 (0.25-0.5, n=142), 0.277 (0.5-0.75, n=282),
  0.227 (0.75-1.0, n=331), 0.211 (1.0-1.25, n=168) and 0.285 (1.25-1.5, n=30). Mean CPU per pair was flat at
  56-60 s in every band. Overall: mean pair score 1.021, variance 0.256, 58.5 s CPU per pair.

### Inferences
- **Why CUPED does not transfer.** Let Y be the new engine's pair score minus 1, and X any feature of the
  opening fixed before the game (a reference eval, material, the ECO code). Swapping colours inside the pair
  removes the opening's colour bias, so E[Y | X] = effect(X). CUPED's variance reduction is the share of Var(Y)
  explained by E[Y | X], which is at most Var(effect(X)) / Var(Y). Effects of a few Elo are tiny against a pair
  variance of about 0.26 (score units), so the gain is negligible. Pairing has already removed the dominant
  pre-game covariate, the opening's main effect. Stratifying on X is equivalent (Deng et al.), so it gains
  nothing either.
- **What does work: heteroskedasticity.** Variance drops by about 30% from balanced to unbalanced bands (0.305
  to 0.211). If sensitivity were equal across bands, that alone would give about 1.45x signal per pair, close to
  ChessSI's measured 1.46x at 0.8-1.0. So much of the lead may be a variance effect, and variance can be
  measured *blind* (without knowing which engine won). Selecting high-information openings (importance
  sampling) saves games. Weighting pairs post hoc by stratum information is free (no new games), but it still
  pays for the low-information pairs, so it is mainly a retrospective check.
- **No CPU-per-pair bonus.** Unbalanced openings do not finish sooner under the current adjudication (56-60 s
  per pair in every band), so the saving per CPU second equals the saving per pair (1.3-1.5x).
- **Pairing.** No design that beats colour-reversed pairs for pre-game covariates was found.

### Gaps
- No chess-testing use of CUPED or regression adjustment was found; searches for it returned only general A/B
  material.
- Per-band *sensitivity* (the expected-score change per Elo) cannot be measured without changes of known
  strength. ChessSI's per-band signal estimates combine sensitivity and variance.
- The variance-by-band numbers come from 1,027 pairs with small extreme bins; rerun them on the PC's 32,743
  games.

## 3. Which sequential and adaptive designs could cut games per decision?

### Takeaway
Group-sequential designs and the 2-SPRT offer little for ChessSI. Under continuous monitoring the SPRT is
already near-optimal at its design points, and the 2-SPRT trades a 12% saving at the midpoint for 25-41% more
games on clear winners. The large lever is **decision-theoretic stopping**: stop once a wrong decision would
cost under some Elo threshold, using a prior fitted to ChessSI's own log. Even simply loosening beta from 0.05
to 0.2 raised nElo gained per CPU about 1.6x in simulation. A pre-screen used as a prior is weak, because the
gap between fidelities (about 24 Elo SD) exceeds today's effect sizes. Racing helps only for questions with
several variants.

### Cited Findings
- Lorden's 2-SPRT combines two one-sided SPRTs. It approximately minimizes the expected sample size at one point
  while controlling errors at two others, and "2-SPRT's have efficiencies greater than 99%" for the normal case;
  Huffman (1983) proved asymptotic optimality —
  [arXiv 2403.18782 (survey of Lorden's work)](https://arxiv.org/pdf/2403.18782),
  [Huffman 1980 thesis](https://thesis.caltech.edu/17611/1/Huffman_MD_1980.pdf) (snippets)
- Van den Bergh switched to the 2-SPRT on TalkChess and posted a Python script for its parameters, OC and ASN.
  He wrote that "the 2-SPRT optimizes the worst case behaviour ... when the real elo is precisely in the middle"
  and that it "has an absolute upper bound on its running time". A "~10% fewer games" figure in the thread was a
  recollection — [TalkChess p=606194](https://talkchess.com/viewtopic.php?p=606194) (snippet)
- No 2-SPRT mode was found in the fishtest, OpenBench or fastchess code read, nor in the crippa1337 OpenBench
  fork (grep for 2-SPRT, Lorden or Kiefer).
- Bayesian A/B "threshold of caring" rule (Stucchio, VWO): stop once the expected loss of picking either variant
  is below epsilon — [Stucchio 2014](https://www.chrisstucchio.com/blog/2014/bayesian_ab_decision_rule.html),
  [arXiv 2608.12949 overview](https://arxiv.org/pdf/2608.12949) (snippet)
- Daily peeking raised the frequentist switch rate of such a rule from 2.5% to 11.8% in one simulation —
  [R-bloggers 2015](https://www.r-bloggers.com/2015/08/is-bayesian-ab-testing-immune-to-peeking-not-exactly/amp/)
  (snippet). With a misspecified prior, realized loss exceeds the threshold —
  [arXiv 2302.10108](https://arxiv.org/pdf/2302.10108) (snippet)
- Chess discussions note that the choice of bounds implies a prior, and that "after 1000+ patches tested one
  could estimate the patch distribution" —
  [open-chess "How (not) to use SPRT?"](https://open-chess.org/viewtopic.php?p=19612). A TalkChess poster
  described computing the optimal stopping rule from the distribution of Elo increments, with no implementation —
  [TalkChess "Type I error in LOS based early stopping rule"](https://talkchess.com/viewtopic.php?p=530559)
  (snippets)
- "Multiple change testing": a developer limited by testing time can move faster by accepting an occasional
  bogus patch, and should retest after many patches because interactions are unpredictable —
  [TalkChess p=966650](https://talkchess.com/viewtopic.php?p=966650) (snippet)
- MAMS trials (Royston, Parmar) test several arms against one shared control with interim drops; four arms
  against one control needed 37% fewer patients than four two-arm trials —
  [RePEc chapter](https://ideas.repec.org/h/spr/sprchp/978-3-319-52636-2_110.html) (snippet)
- F-Race eliminates configurations with Friedman tests as soon as evidence suffices; it is best suited to few
  candidates — [F-Race overview](https://www.springerprofessional.de/en/f-race-and-iterated-f-race-an-overview/3124840),
  [IRIDIA TR 2007-011](https://www.cs.ubc.ca/~hutter/EARG.shtml/earg/papers07/IridiaTr2007-011r001.pdf)
- Hyperband (Li et al., JMLR 18(185), 2018) runs brackets of successive halving and reports more than 10x
  speedups in hyperparameter optimization — [JMLR](https://jmlr.org/papers/v18/16-558.html); BOHB adds Bayesian
  optimization — [arXiv 1807.01774](https://arxiv.org/pdf/1807.01774)
- ChessSI's pre-screen (2+0.02) vs full (10+0.1) results: LMP retest +12.2 +/- 21.0 vs +52.5 +/- 14.9; SEE in
  quiescence +30.8 vs +6.0; NMP +107.5 vs +157.1. The gate skips the full SPRT only on a negative pre-screen —
  [docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)

### Inferences
- **Group-sequential designs:** no gain. fastchess re-evaluates the LLR after every pair, and SPRT-type
  continuous monitoring beats any few-look design at its design points. Group-sequential designs pay off only
  when each look is expensive, which is not ChessSI's situation.
- **2-SPRT** (own simulation, symmetric tilt at 2.5 nElo; thresholds log A = log B = 2.299, calibrated to
  alpha = beta = 0.05). Expected pairs, 2-SPRT vs SPRT: 0 nElo 14,071 vs 13,045 (+8%); 2.5 nElo 18,837 vs
  21,519 (-12%); 5 nElo 14,060 vs 13,050 (+8%); 7.5 nElo 8,943 vs 7,135 (+25%); 10 nElo 6,393 vs 4,790 (+33%);
  15 nElo 4,060 vs 2,880 (+41%). The 12% worst-case saving matches the "~10%" recollection. Many of ChessSI's
  ideas are still clear winners, so it would cost CPU on net. It is worth considering only for a queue of
  known-small tweaks, or as a hard cap on test length.
- **Decision-theoretic stopping** (own simulation; Gaussian per-pair model; prior known exactly; stop when
  min(E[max(-theta, 0)], E[max(theta, 0)]) < epsilon, with at least 200 pairs). nElo gained per 10,000 pairs:

  | Prior on true effects (nElo) | SPRT [0,5], beta 0.05 | SPRT [0,5], beta 0.2 | Expected loss < 0.2 nElo |
  | --- | --- | --- | --- |
  | N(0, 6²) | 2.05 | 3.32 (1.62x) | 3.85 (1.88x) |
  | N(2, 8²) | 4.32 | 6.79 (1.57x) | 9.55 (2.21x) |
  | N(5, 15²) | 14.5 | 22.8 (1.57x) | 39.0 (2.69x) |

  The price is more harmful accepts: -0.09 to -0.11 nElo per idea with the expected-loss rule, against about
  -0.002 for the SPRT (already netted out of the gains above). An epsilon of 0.05 was *worse* than the SPRT
  (1.19 per 10k pairs under the first prior), so the threshold matters.
- **Multi-fidelity prior from the pre-screen.** Own fit on the 11 ideas with both results: r = 0.81,
  full = 9.5 + 0.90 x pre-screen. The residual SD is 27.4 Elo, against about 13.4 from sampling noise alone,
  which implies about 24 Elo SD of genuine disagreement between 2+0.02 and 10+0.1. That gap exceeds the
  +3-10 Elo effects now typical, so a pre-screen-based prior, or Hyperband-style ranking of ideas at low
  fidelity, would mis-rank small ideas. Keep the pre-screen only as a gate against large regressions. If the gap
  turns out proportional to the effect, which the data cannot tell, a prior could still help small ideas.
- **Racing / MAMS-style elimination** fits questions with several variants, such as the NNUE lambda sweeps or
  alternative formulas (see candidate 4).

### Gaps
- The 2-SPRT and expected-loss numbers are Brownian approximations, and the expected-loss rule used the true
  prior. With a prior estimated from about 30 logged tests, the gain will be smaller. That has not been
  quantified.
- No chess implementation of expected-loss stopping was found. Discord discussions could not be searched.

## 4. Can several independent changes be tested at once (factorial designs), and what are the interaction risks?

### Takeaway
Yes, and better than the known chess version. H.G. Muller's "orthogonal multi-testing" (2^k engines, each in
the same gauntlet) compares engines through a common opponent, which costs about 4x the games of head-to-head
play; at k = 4 it only breaks even with testing one change at a time. A **complementary-pair (foldover)
design** avoids that penalty. Every game pits a configuration against its exact complement, so every factor
differs in every game. Each factor then gets the precision of a solo head-to-head test, and 2-factor
interactions cancel out of the contrast. In simulation, four ideas were decided in 2.06x fewer pairs and seven
in 2.54x fewer, with error rates matching separate SPRTs. The risk is real interactions between overlapping
search techniques, which ChessSI's own log shows to be large.

### Cited Findings
- Orthogonal multi-testing (H.G. Muller, about 2009): all 2^4 = 16 on/off combinations of four changes, each
  playing the same 400-game gauntlet, so each change is judged from 3,200 games with it against 3,200 without.
  It assumes independent, additive changes. Hyatt objected that it effectively tests all the changes together
  and does not suit near-zero changes; Don said he had added it to his toolkit —
  [TalkChess "Orthogonal multi-testing" p=271592](https://talkchess.com/viewtopic.php?p=271592),
  [p=275127](https://talkchess.com/viewtopic.php?p=275127),
  [A poor man's testing environment p=501702](https://talkchess.com/viewtopic.php?p=501702) (snippets)
- "Patch combining": compare an engine with the patch against one with a known-good feature removed, chosen to
  be independent of the patch — [TalkChess p=225235](https://talkchess.com/viewtopic.php?p=225235) (snippet)
- Optimal designs for paired comparisons with factorial structure (Graßhoff, Großmann, Schwabe and coauthors):
  D-optimal designs for main effects, and later for interactions —
  [OVGU preprint list](https://math.ovgu.de/-p-1516),
  [arXiv 1811.10973](https://ar5iv.labs.arxiv.org/html/1811.10973),
  [arXiv 1912.01578](https://ar5iv.arxiv.org/html/1912.01578) (snippets)
- SPSA already uses the same simultaneous ±perturbation for continuous parameters: random flips, with
  theta + c x flip playing theta - c x flip —
  [fishtest spsa_handler.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/spsa_handler.py)
- ChessSI's log shows large interactions between overlapping search techniques. The history heuristic went from
  -2.7 +/- 4.7 to +60.4 +/- 16.1 once LMR was in. LMP went from -140 to +52.5 after the history heuristic. RFP
  went from +68 to +31.4 after futility pruning —
  [docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- "Interactions between patches are unpredictable", so retest after many patches —
  [TalkChess p=966650](https://talkchess.com/viewtopic.php?p=966650) (snippet)

### Inferences
- **Why the complement design is about 4x better than a gauntlet factorial (own algebra).** Let each game pair
  play configuration x against its complement -x (±1 coding, signs s_j), with the additive model
  Elo(x) = sum_j beta'_j s_j + sum_{j<l} gamma_jl s_j s_l. The pair's expected score difference is then
  2 sum_j beta'_j s_j. The interaction terms cancel, because s_j s_l = (-s_j)(-s_l): the foldover property.
  With sign vectors cycled through the rows of an orthogonal array (8 runs for up to 7 factors), the estimate
  mean(y x s_j) recovers each factor's full on-vs-off effect, beta_j = 2 beta'_j. Its variance is about
  sigma^2 / N, the same as N solo head-to-head games. In a gauntlet, an engine pair is compared through a third
  engine: two independent means of N/2 games each, so 2x the standard error and 4x the games.
- **Own simulation** (Brownian GSPRT per factor, [0, 5] nElo, balanced 8-run array, run until every factor is
  decided):
  - Effects (4.3, 7.1, 0, -2.8) nElo: 43,384 pairs as four separate SPRTs vs 21,025 factorial (2.06x). Pass
    rates (0.888, 0.995, 0.052, 0.002) vs (0.900, 0.996, 0.049, 0.002) separately.
  - Effects (10, 4.3, 7.1, 0): 2.01x.
  - Seven factors (4.3, 7.1, 0, -2.8, 14, 2, -5): 72,557 vs 28,511 pairs (2.54x), with matching pass rates
    (null factor 0.046 vs 0.054).
  - The saving is the sum of the separate lengths over the maximum, so it is capped by the slowest
    (near-midpoint) factor. It would multiply with decision-theoretic stopping.
- **Balance is critical.** A first simulation cycled the 8-run array over batches of 20 pairs, which is
  unbalanced, and effects leaked between factors: a 2-nElo factor's pass rate rose from 0.35 to 0.73. In
  practice, the 2^(k-1) fastchess processes (one per complementary pair) run at different speeds, so either stop
  every run at the same pair count or weight the runs equally in the per-factor statistics.
- **Estimand.** Each factor's estimate is its average effect over contexts where every other factor is on half
  the time. Main effects are aliased with 3-factor interactions. Restrict batches to changes in different
  subsystems (an eval/NNUE change, a time-management change, a move-ordering change, a pruning change), and
  confirm the accepted bundle with one SPRT against the base.

### Gaps
- No chess use of head-to-head complement designs with per-factor sequential tests was found. TalkChess
  snippets, fishtest, OpenBench and fastchess were searched; Discord could not be.
- No data on how often *unrelated* ChessSI changes interact. The log's interactions all involve overlapping
  pruning and ordering techniques.

## 5. What improvements on SPSA exist for parameter tuning, and what has been tried in chess?

### Takeaway
Chess tuning uses classic SPSA (fishtest, OpenBench), Gaussian-process Bayesian optimization with pentanomial
scoring (chess-tuning-tools), and nevergrad/Optuna-based tuners. Second-order SPSA (2SPSA, Spall 2000) is
standard in the optimization literature but absent from the chess frameworks, and no chess comparison of Adam- or
momentum-style SPSA was found. For ChessSI, the cheapest transfer is to give SPSA the same high-information
openings as SPRTs. The complementary-pair factorial (section 4) is, in effect, binary SPSA used for accept/reject
decisions.

### Cited Findings
- fishtest accepts only the "classic" SPSA algorithm, with defaults alpha 0.602, gamma 0.101 and A = 0.1 x
  (games/2) — [spsa_workflow.py](https://github.com/official-stockfish/fishtest/blob/master/server/fishtest/spsa_workflow.py)
- OpenBench's SPSA fields are reporting BULK/BATCHED, distribution SINGLE/MULTIPLE, alpha, gamma, iterations,
  pairs_per and a_ratio — [OpenBench models.py](https://github.com/AndyGrant/OpenBench/blob/master/OpenBench/models.py)
- chess-tuning-tools does Bayesian optimization via bayes-skopt with Bayesian-pentanomial match scoring. A 2021
  TalkChess thread compared it with Lakas (nevergrad) and an Optuna-based game parameter tuner —
  [chess-tuning-tools](https://github.com/kiudee/chess-tuning-tools),
  [TalkChess "Tuning search parameters" p=890249](https://talkchess.com/viewtopic.php?p=890249) (snippet).
  Its author's bayes-skopt was reportedly used to tune Leela Chess Zero —
  [chessprogramming.org Karlson Pfannschmidt](https://chessprogramming.org/Karlson_Pfannschmidt) (snippet)
- SPSA in chess: the Stockfish variant plays a pair of games between the two perturbed parameter sets per
  iteration and uses Spall's recommended gain exponents —
  [chessprogramming.org (SPSA page diff)](https://www.chessprogramming.org/Special:MobileDiff/26150...26392)
  (snippet). In "SPSA problems", SPSA needed hyperparameter tuning and a convergence check on a known function —
  [TalkChess p=710896](https://talkchess.com/viewtopic.php?p=710896). A hybrid adds per-parameter local search
  after SPSA — [TalkChess p=894774](https://talkchess.com/viewtopic.php?p=894774) (snippets)
- 2SPSA (Spall, IEEE TAC 45(10), 2000) estimates the Hessian alongside the parameters from a few measurements
  per iteration — [Spall TAC00](https://www.jhuapl.edu/spsa/PDF-SPSA/Spall_TAC00.pdf). M2SPSA (Zhu and Spall
  2002) fixes ill-conditioned Hessians — [zhu_spall_IJACSP](https://www.jhuapl.edu/spsa/PDF-SPSA/zhu_spall_IJACSP.pdf).
  Qiskit's SPSA offers a second-order mode —
  [Qiskit SPSA docs](https://docs.quantum-computing.ibm.com/api/qiskit/0.45/qiskit.algorithms.optimizers.SPSA)
  (snippets)

### Inferences
- Methods not used in fishtest or OpenBench: 2SPSA or any second-order step; per-parameter adaptive steps
  (Adam-like); multi-fidelity tuning (BOHB-style, with time control as the fidelity); and racing over discrete
  options. None has chess evidence, so each would be an experiment, not a known gain.
- **The cheapest ChessSI step:** SPSA iterations are colour-reversed pairs, so a higher-information book (the
  1.3-1.5x per pair from section 2) should carry over to gradient signal per iteration. That is untested.
- For at most about 10 search parameters, chess-tuning-tools' BO (Known) is a reasonable choice. For many
  parameters, classic SPSA (Known).
- Tuning is not ChessSI's main cost today; accept/reject testing is. So SPSA work ranks below sections 3 and 4.

### Gaps
- No TalkChess or fishtest comparison of Adam/momentum SPSA or 2SPSA in noisy game settings was found.
- CLOP was not checked in this session.

## 6. Better variants of, or principled alternatives to, truncated-game scoring and the self-filtered book

### Takeaway
Truncated scoring failed for a structural reason. A score at ply P is a surrogate whose "surrogacy assumption"
is violated, because the new engine keeps acting after P, and eval-scale shifts bias it. The principled fix is
to debias with fully played games (prediction-powered inference, AIPW, or two-phase sampling). But ChessSI's own
games show there is **no room**: two-phase sampling can only gain when the prefix's CPU share c is below the
squared pair-level correlation rho², and measured c exceeds rho² at every ply. Randomized adjudication below 4
pawns lost efficiency at every play-out probability tried. For openings, the principled version of the lead is
a **blinded, information-based selection**, using the base engine's eval and checked by cross-validation. Its
gain is 1.3-1.5x per pair, with no extra CPU advantage.

### Cited Findings
- ChessSI's truncated games judged by the base engine gave 0.18x signal per CPU second at P=10, 0.56x at 20,
  0.35x at 30, 0.59x at 40 and 0.85x at 60, relative to final results. It showed a false effect for the history
  heuristic (an eval-scale shift) and the wrong sign for SEE —
  [docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- The surrogate index (Athey, Chetty, Imbens, Kang) combines short-term proxies and relies on the Prentice
  surrogacy assumption, i.e. the treatment's effect on the outcome runs through the surrogates. The paper
  characterizes the bias when that fails, and reports 35% smaller standard errors in a job-training application
  — [NBER w26463](https://www.nber.org/papers/26463),
  [Opportunity Insights PDF](https://opportunityinsights.org/wp-content/uploads/2019/11/surrogates_paper.pdf)
- Prediction-powered inference (Angelopoulos, Bates, Fannjiang, Jordan, Zrnic) combines many model predictions
  with a few gold labels and gives valid inference with no assumptions on the model —
  [arXiv 2301.09633](https://arxiv.org/abs/2301.09633). PPI++ adds power tuning (lambda = 0 gives classical
  inference, lambda = 1 gives PPI) and is asymptotically never worse than classical —
  [arXiv 2311.01453](https://arxiv.org/abs/2311.01453), [ppi-py docs](https://ppi-py.readthedocs.io/en/latest/ppi.html).
  It can be worse in finite samples — [arXiv 2505.20178](https://arxiv.org/abs/2505.20178) (snippets)
- Active statistical inference (Zrnic and Candès 2024) labels the points a model is uncertain about and stays
  valid through an AIPW estimator — [arXiv 2403.03208](https://arxiv.org/html/2403.03208v1). Robust sampling
  (NeurIPS 2025) guarantees it is never worse than uniform sampling —
  [arXiv 2511.08991](https://arxiv.org/abs/2511.08991v1) (snippets)
- TalkChess discussions of adjudication describe wrong adjudications qualitatively (both engines agreeing on a
  win in a drawn KBP-KPP ending) but give no measured error rate —
  [TalkChess "Adjudication & engine testing?"](https://talkchess.com/viewtopic.php?p=716529),
  [Effect of adjudication and TC](https://talkchess.com/viewtopic.php?p=881818) (snippets)
- Own retrospective, two-phase design (truncate every pair at ply P, play a random subset out). Per ply, with
  CPU share c and pair-level correlation rho between the surrogate (the base engine's last eval, logistic) and
  the final pair score: P=20: c=0.41, rho=0.30. P=40: c=0.65, rho=0.57. P=60: c=0.80, rho=0.74. P=80: c=0.89,
  rho=0.87. P=100: c=0.94, rho=0.93. Using both engines' evals changed rho by at most 0.03.
- Own retrospective, randomized adjudication. A trigger fires once the last 6 plies all show the same side
  ahead by at least T pawns. Share of games triggering, the favoured side's final score, and the share of all
  CPU spent after the trigger:

  | T (pawns) | Games triggering | Favoured side's score | Draws | Reversals | CPU after trigger |
  | --- | --- | --- | --- | --- | --- |
  | 1.0 | 84.4% | 0.805 | 27.2% | 5.9% | 38.2% |
  | 1.5 | 74.7% | 0.889 | 17.7% | 2.2% | 19.7% |
  | 2.0 | 69.8% | 0.931 | 12.0% | 0.9% | 12.0% |
  | 3.0 | 63.2% | 0.985 | 2.9% | 0.1% | 3.9% |

  With a constant calibrated prediction f and AIPW scoring f + (Y - f)/pi, efficiency (variance x CPU,
  relative to today) was below 1 at every play-out probability: at T=2, 0.90 (pi=0.5), 0.70 (0.25) and 0.42
  (0.1); at T=3, 0.98, 0.92 and 0.77.

### Inferences
- **Why naive truncation fails.** The new engine's advantage accrues after ply P too, so the position at P is
  not a sufficient surrogate and Prentice surrogacy is violated by design. The engines' own evals also change
  scale with the patch. Only completed games can correct both biases.
- **Two-phase arithmetic.** With variance sigma^2[(1 - rho^2)/n + rho^2/N] and cost cN + (1 - c)n (N pairs
  truncated, n played out), the cost-optimal ratio is n/N = sqrt[(1 - rho^2) c / (rho^2 (1 - c))]. That ratio
  is below 1, so a gain is possible, only when **c < rho^2**. The gain factor is then
  [sqrt((1 - rho^2)(1 - c)) + rho sqrt(c)]^2: for example 0.74 at rho=0.9, c=0.3, and 0.88 at rho=0.8, c=0.3.
  On ChessSI's games c > rho^2 at every P (0.41 vs 0.09 at P=20; 0.80 vs 0.55 at P=60), so there is **no gain**.
  That fits ChessSI's 0.18-0.85x measurement.
- **Randomized (AIPW) adjudication:** no gain today. The existing 4-pawn resign rule already captures the cheap
  tail (only 3.9% of CPU follows a 3-pawn trigger). Lower thresholds have too many draws and reversals for the
  saved CPU to pay for the added variance. A per-game gain needs E[(Y - f)^2] x (triggered games per pair),
  relative to the pair variance, to be below the CPU share saved. At T=2 the ratio is 0.187 against 0.12. A
  better f (by eval magnitude, material, ply) might narrow that; the best case is a few percent.
- **The opening lead, done properly.** Rank bands by *blinded* information per pair: pair-outcome variance
  pooled over all past tests, plus a model of sensitivity, which needs no knowledge of who won. Compute the band
  with the **base** engine (or a frozen reference) at fixed depth before the test, never the new engine, so
  selection cannot depend on the treatment. Choose the band on half of the past tests and evaluate it on the
  other half. Hard filtering beats post-hoc weighting for CPU.

### Gaps
- The retrospective used 1,027 pairs from the cloud runs; rerun it on the PC's 32,743 games. The calibration
  f was constant per threshold; a model-based f was not tried.
- How often the current 4-pawn resign rule mis-scores games was not measured. The 1,332-game killer-moves test,
  played without adjudication, could answer it.

## 7. Ranked candidates: which testing and tuning efficiency ideas should ChessSI try, in order?

### Takeaway
Ranked by expected saving x confidence / cost for ChessSI:
1. Decision-theoretic stopping (start with beta 0.2).
2. Complementary-pair factorial screening.
3. Blinded information-optimal openings.
4. Racing among variants.
5. Median-unbiased logging.
6. 2-SPRT.
7. Pre-screen as a prior.
8. SPSA upgrades.
9. PPI/AIPW truncation and adjudication (novel, but retrospectively negative).
10. CUPED on opening covariates (rejected by argument).

Candidates 1 and 2 each promise roughly 1.6-2.5x more decisions or Elo per CPU, their savings multiply, and 2 is
the most novel.

### Cited Findings
- Sources for every claim below are cited in sections 1-6. The numeric estimates come from the own simulations
  and own retrospective analyses described there.

### Inferences

**1. Decision-theoretic (expected-loss) stopping with an empirical-Bayes prior; immediate step: beta = 0.2**
1. *Idea.* Stop a test once the posterior expected loss of the better decision falls below a threshold of
   caring epsilon, about 0.2 nElo, instead of when the LLR crosses +/-2.94. The prior on effects is fitted to
   ChessSI's own logged results (empirical Bayes: deconvolve the estimates using their standard errors). The
   zero-code first step is `BETA=0.2` in `sprt.sh`, with a rule to retest near-misses later. Fields: Bayesian
   A/B testing (Stucchio's VWO rule), Bayesian decision-theoretic trial design.
2. *Prior art: Partially known.* fastchess's "bayesian" model is a BayesElo SPRT (trinomial only) with
   error-rate stopping. Forum posts say bounds imply a prior and that an optimal rule could be computed from
   the distribution of patch effects. No implementation was found in fishtest, OpenBench or fastchess.
   Changing beta is a standard knob; quantifying it for ChessSI is new.
3. *Mechanism.* The SPRT spends the most pairs (21,500 at 2.5 nElo) on ideas whose decision matters least. An
   expected-loss rule ends those early and still decides big effects quickly.
4. *Expected saving.* Simulation: 1.57-1.62x nElo per CPU from beta 0.2 alone, with no measurable rise in
   harmful accepts; 1.9-2.7x with expected loss below 0.2 nElo, at about -0.1 nElo per idea from harmful
   accepts. Confidence: high for beta 0.2; medium for the expected-loss rule, whose prior was known exactly in
   simulation and must be estimated in practice.
5. *Cost.* About half a day: a monitor that reads fastchess's pentanomial counts (or the PGN) and stops the
   run, plus a prior fit from the log. No extra compute.
6. *Experiment.* Retrospective first. Replay each saved SPRT's game stream, in PGN order, through the rule;
   record when it would have stopped and what it would have decided, against the SPRT. Fit the prior on half
   the tests and evaluate on the other half. Then shadow-run the rule on the next ideas: it reads the same
   games, so it costs nothing.
7. *Risks.* Frequentist error rates are given up by design: peeking raises false switches, and with a
   misspecified prior, realized loss exceeds epsilon. Small regressions accumulate, so run a periodic
   non-regression SPRT against an older checkpoint. It also changes the benchmark's "hit rate" and "games per
   accepted change", so log the SPRT LLR alongside and get the owner's approval first.

**2. Complementary-pair (foldover) factorial screening of independent changes**
1. *Idea.* Put k (3-7) independent changes behind UCI booleans in one binary. Every game pair plays a
   configuration against its exact complement, with sign vectors cycled through an orthogonal array (L8). Each
   factor gets its own pentanomial GSPRT on the pair outcomes, seen from the engine that has the factor on.
   Accepted factors are confirmed as a bundle with one SPRT. Fields: 2^k factorial and foldover designs,
   orthogonal arrays, optimal paired-comparison designs (Graßhoff and Schwabe), SPSA's simultaneous
   perturbation.
2. *Prior art: Partially known.* Muller's orthogonal multi-testing (2009) used a gauntlet per configuration;
   SPSA uses the same ±perturbation for continuous parameters; ChessSI's own factorial proposal is untested.
   Not found: head-to-head complement designs with per-factor sequential tests for accept/reject decisions.
3. *Mechanism.* Every game informs every factor at full head-to-head weight, and 2-factor interactions cancel
   out of the contrast. A gauntlet factorial loses 4x through indirect comparison; the complement design does
   not.
4. *Expected saving.* Simulated 2.06x for 4 small ideas and 2.54x for 7, with per-factor error rates matching
   separate SPRTs; capped at k. Confidence: high for the arithmetic, medium in practice (additivity).
5. *Cost.* 1-2 days: UCI switches; 2^(k-1) fastchess processes, one per complementary pair, or a small runner;
   a PGN-to-per-factor-LLR script. Compute is that of one test.
6. *Experiment.* A positive-control run first. Toggle 3 already-accepted, unrelated features with known solo
   results, such as SEE pruning in quiescence (+22.2 +/- 9.1), plus a dummy option that changes nothing.
   Check that every factor's estimate matches its solo SPRT and the dummy reads about 0. Then run real batches
   of unrelated small ideas. Saved games cannot validate the design (it needs new games), but the analysis
   script can be checked on synthetic pentanomial data.
7. *Risks.* Interactions: ChessSI's own overlapping pruning and ordering changes interacted strongly, so batch
   only changes from different subsystems. Main effects are aliased with 3-factor interactions. Unbalanced
   schedules leak effects between factors (seen in simulation: 0.35 to 0.73 pass rate), so use equal pair
   counts per run. One test yields k log rows; record the design in the Games cell.

**3. Blinded, information-optimal opening selection by the base engine's eval**
1. *Idea.* Before each test, evaluate a large UHO subset with the base engine at fixed depth. Keep the bands
   with the highest blinded information per pair, i.e. lowest pair-outcome variance per unit sensitivity,
   pooled over past tests without regard to who won. Choose the band by cross-validation over past tests.
   Fields: importance sampling and Neyman allocation; blinded adaptation from clinical trials.
2. *Prior art: Partially known.* UHO selects by eval window using KomodoDragon or Stockfish evals; Laskos and
   Van den Bergh analysed unbalanced openings with pentanomial variance; ChessSI's 0.7+ band lead. Not found:
   selection by the tested engine's own base eval with blinded per-band information.
3. *Mechanism.* Pairing makes the pair outcome's mean independent of the opening, but not its variance or
   sensitivity. Measured variance falls about 30% from balanced to unbalanced bands.
4. *Expected saving.* 22-32% fewer pairs (1.29-1.46x signal per pair). There is no extra per-CPU gain, since
   CPU per pair is flat at 56-60 s across bands. Confidence: medium (bins are +/-0.2; selection on noisy bins
   overstates the gain).
5. *Cost.* Hours: an eval pass over a few hundred thousand openings and a filter script, repeated for each new
   network.
6. *Experiment.* Retrospective: re-bin the 5,072 pairs with cross-validation across tests, and add blinded
   variance per band from all 32,743 games. Prospective: test 2-3 patches with both books, alternating, and
   compare SPRT lengths and sign agreement.
7. *Risks.* The estimand drifts: ideas that pay off in balanced or drawish positions are undervalued. Never use
   the new engine's eval for selection. Recompute after an eval-scale change (a new network).

**4. Racing among variants of one idea, with direct variant-against-variant games**
1. *Idea.* For K discrete variants (formulas, margins, NNUE recipes such as lambda 0.6, 0.75 and 1.0), play a
   round robin among the variants and the base, fit Bradley-Terry ratings, eliminate variants at interim looks
   (F-Race or successive elimination, MAMS-style), and confirm the survivor with one SPRT against the base.
2. *Prior art: Partially known.* Continuous tuners (SPSA, Bayesian optimization, nevergrad/Optuna) exist;
   racing with elimination for discrete variants was not found in the frameworks. MAMS, F-Race and Hyperband
   are Known outside chess.
3. *Mechanism.* Elimination stops spending games on clear losers, and direct variant-vs-variant games rank
   variants about 4x more efficiently than comparisons through the base.
4. *Expected saving.* Roughly 30-50% for K = 3-5 variants (MAMS reference: 37% for four arms). Not simulated;
   low confidence.
5. *Cost.* About a day. fastchess has a round-robin tournament mode (`app/src/matchmaking/tournament/roundrobin`),
   but whether it can play only selected pairings was not checked.
6. *Experiment.* Simulate a race with the measured effects of ChessSI's lambda tests (-80.4 and +1.8 vs net7)
   and the output-bucket test (-0.7), and compare games with the separate tests. Then use it on the next
   multi-variant question.
7. *Risks.* Winner's curse, so the confirmation is mandatory. Multiplicity. Pool-dependent ratings.

**5. Median-unbiased Elo in the log, and an empirical-Bayes model of effects (enabler)**
- *Idea and prior art: Known* (fishtest's `sprt` class). ChessSI logs fastchess's fixed-sample estimates,
  which are biased away from zero for tests that stopped early. Port fishtest's `sprt.py` and recompute the
  logged results.
- *Saving.* None directly. It makes the log's "Elo per accepted idea" honest and feeds the prior in candidate 1.
- *Cost.* Hours.
- *Risk.* The correction is valid only for small Elo, per fishtest's own warning.

**6. Lorden's 2-SPRT** — *Known* (Van den Bergh, TalkChess, with a script; not in the tools). Simulated: 12%
fewer pairs at the midpoint, 8% more at the bounds, and 25-41% more at 7.5-15 nElo; it has a hard upper limit
on length. A net loss while many ideas are clear winners. Consider it only for queues of known-small tweaks.
The experiment is a replay of saved SPRT streams through both rules. Cost: small.

**7. Pre-screen as an informative prior, or Hyperband across ideas** — *Partially known* (fishtest's STC to LTC;
ChessSI's gate). Measured fidelity gap of about 24 Elo SD (11 ideas; r = 0.81; LMP +12 to +52, SEE +31 to
+6), larger than today's effects. Expected saving below 10% for small ideas; keep it as a gate only. Experiment:
keep logging pairs of results, refit at 30 or more, and test whether the gap scales with the effect.

**8. SPSA upgrades** — classic SPSA and Bayesian optimization are *Known*; 2SPSA and Adam-style steps are
*Partially known* (optimization literature, with no chess evidence). The ChessSI-specific step is running SPSA
on the high-information book (untested; up to 1.3-1.5x per iteration). Experiment: tune one known parameter set
with the standard and filtered books at equal games, then compare the results by SPRT.

**9. Debiased truncation and adjudication (PPI/AIPW, two-phase)** — *Novel* in chess as far as searched (no
chess testing use of PPI, AIPW or randomized adjudication was found). **Retrospective result: no gain on 1,027
pairs.** Two-phase sampling needs c < rho^2, and measured c > rho^2 at every ply from 20 to 100; randomized
adjudication at 1-3 pawns had efficiency 0.24-0.98 against today. It makes the rejected idea statistically
valid but not cheaper. Worth logging as a failed novel methodology idea. Rerun on the PC's 32,743 games before
closing it.

**10. CUPED or post-stratification on pre-game opening covariates** — *Rejected by argument*. Colour-reversed
pairs already remove the opening's main effect; any remaining correlation comes from variation in the treatment
effect, a few Elo against a pair variance of about 0.26. No experiment is needed beyond the free weighting check
in candidate 3.

### Gaps
- The savings for candidates 1 and 2 come from Brownian simulations with stated assumptions (an oracle prior;
  additivity). Real numbers need the retrospective replay (candidate 1) and the positive-control run
  (candidate 2).
- The prior-art checks could not read TalkChess, arXiv or Discord in full. A "Novel" or "Partially known"
  verdict means "not found in fishtest/OpenBench/fastchess code, chessprogramming or TalkChess search
  snippets", not proof of absence.
