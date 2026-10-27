# Research priorities after the first GPU tune

Follow-up on 2026-10-27: [training capacity, net12 controls and current GPU teacher scope](../research-followup-2026-10-27/REPORT.md). PR42 fixed the default-value drift described in this historical snapshot; newer CPU search additions now require a separately pinned GPU teacher manifest.

2026-10-26 UTC / 2026-10-25 Phoenix. Source baseline: [main 4348bbb](https://github.com/LupeHiguera/ChessSI/commit/4348bbb0dce10ca3f6da03b4599450938b83384e). Prepared by GPT-6 (Codex), with GPT-6 Astra ultra research and independent cross-review. This sprint contains source and literature research, with no new engine, training, timing or Elo result. All experiments below are proposals, not simultaneous claims or resource reservations.

The smallest new strength experiment is **softening the score returned by reverse futility pruning**. The strongest new training proposal is **feature factorization that folds back into the unchanged deployed network**. The most interesting tuning-method proposal is **randomized orthogonal perturbation blocks**, tested against an equally batched IID control. The already measured rejected-update opportunity remains a strong CPU speed candidate from the previous sprint.

All eight additional candidates below have established prior art at the method level. Their particular effects in ChessSI are untested. Finding a useful application is valuable, but this review does not establish a genuinely novel chess algorithm or an Elo gain.

## Current baseline and ownership

The accepted CPU tune from [PR 40](https://github.com/LupeHiguera/ChessSI/pull/40) reported +40.4 +/- 11.7 Elo over 1,046 games at 10+0.1, bench 116503. That result belongs to the existing tune. Future trials must use the accepted main, not the older 35cb09b engine used in the previous feasibility audit.

Claude is currently testing pawn correction history on borrowed cores 14-19. No local engine jobs, data scans, builds or GPU experiments were launched by this sprint. Existing Claude claims on TT replacement, IIR, history, correction history and initial LMR behavior remain his. Coordinate the LMR-confirmation proposal before implementation.

The repeated-label pilot is closed for insufficient coverage in [PR 34](https://github.com/LupeHiguera/ChessSI/pull/34). Its archived protocol already contains PR 29's controls. [PR 38](https://github.com/LupeHiguera/ChessSI/pull/38) measured rejected NNUE updates but did not implement the CPU optimization. Current GPU code already skips the arithmetic for rejected moves; CPU `Position::do_move` still updates first. Do not claim the GPU version as new work. [GPU path](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/gpu/datagen.cu#L419), [CPU path](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/src/position.cpp#L315).

## Fix the experimental starting point

The GPU defaults still contain pre-tune RFP depth/margin 3/150, null-move divisor 6, and LMR 0.75/2.25. Accepted CPU search uses 5/77, divisor 4, and 0.82/1.72. Datagen can override defaults with `GPU_PARAMS`, but SPSA initializes `theta` directly from `DEFAULTS` and supplies per-game parameter arrays, so that environment variable does not seed the tuner. [Defaults and override](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/gpu/datagen.py#L75), [SPSA initialization](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/gpu/spsa.py#L65).

Freeze one explicit parameter manifest before another comparison: source, network, realized integers, full LMR table, TT size, seed, game IDs and budget. Intentionally restarting from old constants is valid if documented; accidentally treating them as accepted main is not. The discrepancy was [sent to Claude](https://github.com/LupeHiguera/ChessSI/issues/31#issuecomment-6409310803). It does not invalidate the completed accepted CPU tune or establish that existing data is mislabeled.

Common non-atomic state writes still run in all GPU lanes in this snapshot. Resolve that existing ownership issue and repeat CPU parity, including paused/resumed searches, before using new GPU changes as validated infrastructure. This is the previously documented source-level hazard, not a newly observed output failure. FEN normalization and precise SPSA export have already been fixed; do not reopen those old findings as current bugs.

## Ranked backlog

Priority reflects cost and how directly the screen answers the hypothesis, not a predicted Elo gain.

| Priority | Candidate | First useful measurement |
| --- | --- | --- |
| Existing first | Skip rejected CPU NNUE updates | Identical search plus uninstrumented whole-search timing on tuned main |
| 1 | Soften RFP return values | One fixed return rule, unchanged cutoff guards |
| 2 | Training-only piece feature factorization | Matched small training runs and an FT learning-rate control |
| 3 | Main-search check-evasion sieve | Every veto provably illegal; identical move order and search |
| 4 | Soft datagen node limit | Label quality against equal-cost uniform search |
| 5 | Randomized orthogonal SPSA blocks | Independent directional-response prediction and held-out update test |
| 6 | Scalar sibling-ranking supervision | Count stable quiet-sibling misorderings before training |
| 7 | Selective depth for LMR confirmation | Frequency and predictive value of small reduced-search overshoots |
| Conditional | Recover persistently inactive H256 units | Activation audit before any recycling |

## Soften reverse futility scores

Current RFP cuts eligible non-PV nodes through depth 5 when `staticEval - 77*depth >= beta`, then returns the full static evaluation. Test one fixed expression, `beta + (staticEval-beta)/2`, while retaining every eligibility check and the zero returned for stalemate. For an identical position/window the local cutoff condition is unchanged; the propagated score is different, so subsequent bounds, re-searches and total nodes may change. [Current source](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/src/search.cpp#L274).

This is Known: Stockfish softens the returned value toward beta, and PlentyChess uses a midpoint. [Stockfish](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp#L994), [PlentyChess](https://github.com/Yoshie2000/PlentyChess/blob/main/src/search.cpp).

The first diagnostic should count eligible cutoffs, overshoot sizes and affected returns on the tuned engine. If sufficiently frequent, implement only this expression and adapt RFP score expectations while preserving mate, rule50, root and stalemate checks. Use the existing one-idea strength loop; do not tune another margin or average several return rules into one result. A fixed-depth node signature is expected to change for this search change.

The strongest objection is that fail-soft values carry useful information and the accepted pruning margins were tuned with the current return. Lower score volatility is not a strength metric. Stop on correctness failures or rejection by the normal strength gate.

## Factor piece features during training

For each non-king piece/color group, parameterize its 64 feature-transformer rows as `W[p,s] = R[p,s] + U[p]/8`. Initialize `U=0` and `R` to the exact baseline effective weights. Ten groups at H256 add 2,560 training parameters. Fold the sum into the same 768 rows at export, leaving deployed size and inference operations unchanged.

This is an optimizer/reparameterization experiment, not additional expressive capacity. Under plain SGD without clipping, an effective row receives `-eta * (G_s + sum_t(G_t)/64)`: the across-square mean direction gets twice the update rate while contrast directions keep their rate. Independent Adam moments change that interpretation. Stockfish's official NNUE documentation describes feature factorization, folding, and its often transient early-training benefit. [Factorization](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md#feature-factorization), [serialization](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/features.html).

Implementation constraints for a later trial: add the shared factor per feature occurrence so material counts remain correct; exclude king codes 5 and 11 and the padding row. Use zero parameter-wise weight decay or regularize effective `W`. Retain `U` during projection and set `R = clamp(R+U/8)-U/8`; independently clipping the two terms is a different constraint. Fold once before quantization and verify integer inference.

Small screen: freeze 8M own positions, two initialization/order seeds, two epochs, identical pointwise targets and auxiliary heads. Compare baseline, factorized training, and baseline with twice the **feature-transformer** learning rate, keeping other parameter learning rates fixed. This is 96M position presentations in total. A proposed advancement gate is at least 0.2% relative held-out MSE improvement in both seeds, with no regression on a separate producer cohort. If the learning-rate control explains the gain, record that and prefer the simpler method. A short-run win earns a full-schedule comparison, not an engine promotion.

ChessSI's 768 inputs are already much denser than HalfKP features. Shared factors could merely accelerate early optimization or introduce an unhelpful material bias. Keep one trainer revision across all arms, including any PR 41 shuffle changes; do not compare old/main and new-trainer runs as if their batch order were controlled.

## Reject impossible evasions before making them

At a checked main-search node, keep the current generated list, scoring and selection swaps. Immediately after `pick_move`, reject ordinary nonking/non-EP moves whose destination can neither capture the single checker nor block its ray. In double check, reject those ordinary nonking moves. King, EP and ambiguous cases still pass through the existing legality code. Promotions must be handled as ordinary destination cases without losing their move identities. This is Known evasion-mask logic, with [Stockfish prior art](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/movegen.cpp#L215).

Applying the sieve after selection preserves tied-move ordering; filtering before scoring can reorder the remaining list. The benefit could exceed NNUE-only laziness by avoiding board mutation and undo as well, but mask computation has a cost. ChessSI needs checker and between-squares helpers first.

The first gate is main-search checked-node coverage, excluding king/EP moves. The older aggregate 23% rejected-update count includes other paths and cannot establish this frequency. Independently verify every veto against the existing `do_move`; compare legal move order, fixed-depth nodes, scores and PVs exactly. Only then time an uninstrumented candidate. Ray, pin, promotion and EP edge cases can discard legal moves if the mask is wrong. This remains separate from qsearch check handling and from the NNUE-only change because their savings overlap.

## Finish a datagen iteration within a safety limit

Current search correctly exports the last completed iteration when a node stop interrupts the next one. There is no evidence here of corrupted partial-iteration labels. The proposal is a 5,000-node soft limit, checked between iterations, with a 10,000-node hard limit inside search. The GPU's resumable search can finish an active iteration across launches. Viridithas already uses soft-node datagen with a larger hard ceiling, so this is Known. [Viridithas](https://github.com/cosmobobak/viridithas/blob/d82194945e1ab8d1bba0cc32c3a94ee772e2176c/src/datagen.rs#L471), [ChessSI completed-iteration handling](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/src/search.cpp#L523).

Compare three arms on frozen trajectories: hard-5k; soft-5k/hard-10k; and a uniform hard budget calibrated beforehand to equal the candidate's total GPU cost. Use 256 calibration positions and 1,024 untouched positions grouped by actual game identity, preserving warm history and TT. Record actual nodes, completed depth, exported-label change, overruns and end-to-end cost. Stop if target error against a higher-budget own-engine reference does not improve over the equal-cost uniform control.

Aborted work can populate the TT and help subsequent plies, so it is not all waste. Root-only cold-TT accounting would miss that benefit. Higher-budget agreement is a diagnostic, not proof of better students. A later student comparison keeps positions, game results and auxiliary targets identical; changing the teacher's played moves also changes the corpus and must be tested as a separate intervention.

## Balance GPU tuning perturbations

Current SPSA samples independent signs and updates its center as pairs finish. Test randomized Hadamard blocks with a fixed center, initially freezing the two LMR-table parameters and perturbing the remaining 15 integers with 16 orthogonal sign rows. Deterministic/Hadamard perturbations are established optimization methods. [Bhatnagar, Fu, Marcus and Wang](https://www.cs.jhu.edu/~ijwang/pub/p180-bhatnagar.pdf).

Use one opening throughout each block, with both colors for every direction. Give the IID control the same opening, fixed center, number of directions, budgets and update scale. Otherwise an apparent gain could come from batching or reduced staleness. Independently randomize the Hadamard columns' signs for each block; this gives each row the same marginal direction distribution as IID signs. Treat openings as independent units, not the correlated directions or colors inside a block.

In a local linear response model, `D^T D = 16 I` removes cross-parameter interference. It does not guarantee better estimates for discontinuous game outcomes. Log realized rounded/clipped endpoints, common midpoints, effective half-differences and duplicate configurations. Exclude zero-effective parameters. If LMR floats are later added, compare realized tables rather than different decimal values.

The [detailed 2,048-pair protocol](TUNING_PROTOCOL.md) uses 1,024 pairs for estimation, 512 on an independent IID-direction validation panel, and 512 for one untouched-opening update comparison. Advance only when the directional-response estimate improves on that independent panel and the resulting update has no material contradiction on untouched openings. A broad interval is inconclusive. This tests one update regime; a full tuning trajectory and CPU time-based SPRT still follow later.

The strongest objections are integer discontinuities, interactions that alias under a fixed design, uninformative perturbations and opening-specific responses. Repeating identical deterministic games adds no independent evidence. Randomized blocks and genuinely new openings provide the replication.

## Audit scalar sibling misordering before adding a loss

A separate from/to policy head failed previously. This proposal trains the existing scalar evaluator to rank two legal child positions from one root, using stronger ChessSI searches as labels. It adds no deployed head. Ranking supervision is Known; relevant primary precedents are [RankNet](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/) and [DeepChess](https://arxiv.org/abs/1711.09667). Their external datasets or evaluations would not be used.

First perform only an opportunity audit: 256 frozen roots, one per explicitly identified fresh game. Select the producer's quiet chosen move and the highest-static-evaluation quiet alternative before deeper labels are inspected. Freeze a precise quiet-child eligibility definition. Search both children at 8,192 nodes for eligibility, then 32,768 for confirmation, with identical cold-TT treatment, full history, completed-iteration results and scores converted to the root player's perspective. Cap the diagnostic at 30M actual nodes or 20 one-core minutes.

Count cases where the first teacher has a 32-200 cp preference opposite the current static evaluation, then report every confirmation, including vanished or reversed preferences. Fewer than 16 confirming roots is inconclusive and parks the idea; do not replace inconvenient roots or relax the threshold.

If coverage survives, use identical original rows and child labels for pointwise-only, pointwise-plus-ranking and pointwise-reweighting controls. Keep batches and optimizer steps fixed. Evaluate on disjoint roots/games and retain ordinary blended-target MSE as a guardrail. No shared-result-noise cancellation is claimed. Selective search can be wrong, and teaching tactical sibling rankings may distort the evaluator's calibration or consume scarce capacity. The audit measures a deliberately selected quiet-sibling subset, not overall ranking ability or Elo.

## Spend less on weak LMR confirmations

Current reduced fail-highs receive the same full-depth confirmation. A higher-risk candidate gives one-ply-shallower confirmation to a narrowly defined small overshoot, only where the original reduction leaves confirmation deeper than the first probe. Stockfish's result-dependent confirmation depth provides Known prior art; its thresholds are not ChessSI calibration. [Current confirmation](https://github.com/LupeHiguera/ChessSI/blob/4348bbb0dce10ca3f6da03b4599450938b83384e/src/search.cpp#L345), [Stockfish](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp#L1375).

A diagnostic can record reduced-score overshoot, reduction, confirmation outcome and confirmation node cost using searches already performed. Freeze a small-overshoot threshold on a calibration set; reject it if held-out games show no useful association with expensive false alarms. Do not optimize the threshold on the confirmation sample.

This differs from reducing later siblings less after contradictory results and from history-based initial reductions, but it overlaps Claude's broader LMR work and needs coordination. A move weak at two reduced depths can be best at full depth. This deliberately changes selectivity, so correctness and a favorable proxy cannot replace timed SPRT.

## Check unused capacity before widening the network

SCReLU has zero derivative outside its interior activation interval. A forward-only audit of two disjoint fixed 250k-position cohorts can count each unit's zero, interior and saturated fractions in both perspectives and by material phase. Stop unless at least 13 of 256 units are effectively inactive in both cohorts under a threshold frozen before inspection. Low mean activity alone is insufficient.

Only then consider a matched continuation trial recycling a few persistently zero units, with outgoing weights reset in every training head and optimizer state reset appropriately. Rarely active units may encode valuable rare motifs. An output-weight or export saturation problem is not the same diagnosis as zero activity. [ReDo](https://proceedings.mlr.press/v202/sokar23a.html) is primary prior art for recycling in deep reinforcement learning, not evidence that it helps this shallow supervised NNUE. Classification: Known recycling concept; NNUE benefit unestablished.

## Measure CPU cost before building a virtual clock

Fixed nodes do not imply fixed CPU work when parameters change the number of evaluations, legality probes, SEE calls and re-searches per node. Fishtest generally prefers normal time controls for search tuning and does not treat node-time tests as a substitute. [Fishtest guidance](https://github.com/official-stockfish/fishtest/wiki/Creating-my-first-test#spsa-tests). Hardware-aware optimization has broader precedent, including [MnasNet's measured latency objective](https://arxiv.org/abs/1807.11626).

The simplest next check is to freeze a small GPU finalist set and measure each candidate's paired CPU cost ratio against the baseline on the same own-game roots. Use identical TT initialization/cache preparation, uninstrumented ABBA timing and one assigned core. If noise is comparable to the apparent configuration effect, stop as inconclusive. No extra event-cost model is justified unless direct ratios show repeatable differences that materially reorder candidates.

A later, more ambitious screen could fit evaluation/move/SEE/TT event counts to CPU cost. Its target must be candidate/base time ratios, not total-time R-squared: root difficulty can explain total time while hiding parameter-induced differences. Hold out complete perturbation directions and games. A 50k-node fit also does not validate search prefixes stopped by a virtual clock, and a tuner can exploit underpriced model errors. Keep this lower priority than direct timing; a 1 MB calibration still leaves the production 16 MB transfer question unresolved.

## Execution order and stop rules

Claim one implementation experiment at a time. First choose between the existing rejected-NNUE CPU candidate and the one-expression RFP candidate. Then reserve a separate GPU slot for feature factorization or the bounded tuning-method test. No numerical Elo forecast is warranted for these proposals.

Every experiment must freeze source, network, realized parameters, data/opening identities, exclusion rules, metric and sample/resource cap before inspecting outcomes. Use a separate development/calibration population and untouched assessment population. Match trainer revisions and data order. Search candidates use the project test/SPRT loop; network candidates require export/C++ inference checks and CPU SPRT. Speed-only candidates need unchanged search semantics before timing. Log rejected and inconclusive screens as well as successes.

The ranked list intentionally excludes generic repeats of Claude's active TT, IIR, correction-history and history-decay work. It also leaves the existing output-head refit and qsearch capture-futility proposals in the earlier backlog, without presenting them as discoveries from this sprint.
