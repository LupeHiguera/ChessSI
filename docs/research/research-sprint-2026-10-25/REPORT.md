# Research sprint: next strength experiments

Date: 2026-10-25 UTC / 2026-10-24 Phoenix. Source baseline: [`35cb09b`](https://github.com/LupeHiguera/ChessSI/commit/35cb09b31fc1efae63e13c1da17a9285623e1cb5).

Prepared by GPT-6 (Codex), with GPT-6 Astra ultra evaluation and GPU/data review and a parallel search review. This is source and literature research. **No implementation, local data scan, build, training, benchmark, or match was run in this sprint. No new Elo gain is claimed.**

## Recommended order

Keep [repeated-position label aggregation](../repeated-labels-2026-10-24/PROTOCOL.md) as Astra's active experiment; [PR #29](https://github.com/LupeHiguera/ChessSI/pull/29) contains its pending control clarifications. The following are a ranked backlog, not simultaneous claims or jobs. Confirm Claude's ownership and write the selected claim in IDEAS.md before implementing one.

| Priority | Candidate | Classification | First decision |
| --- | --- | --- | --- |
| 1 | Skip NNUE arithmetic for rejected moves | Known; narrow version of queued lazy updates | Is whole-search speed measurably better with identical results? |
| 2 | Refit the deployed output head | Known; sharper experiment under earlier QAT proposal | Does improvement survive integer export and held-out validation? |
| 3 | Conservative capture futility in quiescence | Known | Are useful descendants saved without frequent tactical misses? |
| 4 | Audit teacher-cohort score scales | Known calibration | Is apparent drift robust to material, writer and game separation? |
| 5 | Batched two-ply GPU teacher | Known search bootstrapping; larger engineering task | Does lookahead improve labels enough to justify end-to-end cost? |
| Later | Same-game residual covariance loss | Novelty not established | Obtain actual game identities; test the statistical premise first |

The current [README](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/README.md) reports an approximate Stash-anchored rating of 3284 ± 21 at 10+0.1. That is existing project evidence, not a result of this sprint. None of the proposals below has a defensible numerical Elo estimate.

## 1. Avoid accumulator work for moves immediately rejected

[Position::do_move](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/position.cpp#L313) currently prefetches the TT, updates both NNUE accumulators, and then tests whether the mover's king is attacked. Rejected pseudo-legal moves pay for an accumulator update that search never uses.

The smallest candidate retains TT prefetch before the legality check, determines legality before NNUE arithmetic, and skips only arithmetic for invalid children. Still reserve and advance one stack slot: [undo_move](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/position.cpp#L348) unconditionally pops it. An invalid child must be undone immediately without evaluation. Preserve no-network behavior, network-generation handling, promotions, en passant and castling.

This specializes the lazy-update direction already mentioned in IDEAS.md. It is not a novel method. [Stockfish 19 checks legality before making searched moves](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp#L1127). Published Claude speed branches acc-no-zero-fill (130bddd), nnue-simd (f888367), and rfp-fast-legal (0421f00) still update before rejection in the inspected versions.

**Gate:** count rejected moves on a fixed own-position set. Require existing tests, explicit make/undo accumulator invariants, and identical single-thread bench nodes, scores and principal variations. Then measure alternating fixed-work wall time on allocated cores. Saving arithmetic is insufficient: extra branching or changed TT-latency overlap can erase the gain. Only a repeatable whole-search speed benefit justifies a match.

## 2. Refit 513 output parameters without enlarging the network

The [trainer](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/nnue/train.py#L354) uses continuous feature/output weights and rounds them at export. It saves the exported network, not an original float checkpoint. Generic quantization-aware training was already proposed in the earlier report; it should not be rediscovered as novel.

A smaller experiment is possible from net10 itself: freeze its exported feature transformer and optimize only 512 output weights plus the bias. Use three arms:

1. Unmodified net10.
2. A continuous output-head finish, followed by ordinary rounding.
3. The same finish with fake quantization of output weights and deployment arithmetic.

Initialize both finishes from the same dequantized readout; use identical positions, ordering, steps and optimizer settings. Keep the exact exported feature representation. With the transformer frozen, an auxiliary head cannot improve its features; keep auxiliary settings identical and make no claim of an auxiliary contribution.

[Stockfish's quantization implementation](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/quantize.py) and [Tatara's matched dense-QAT continuation](https://github.com/SH11235/tatara/blob/d098eaf62bb6b65c09985181cc3739a580539116/docs/dense-qat.md) establish direct NNUE prior art. [AdaRound](https://proceedings.mlr.press/v119/nagel20a.html) is adjacent task-aware rounding prior art; the proposed supervised refit is not an implementation of AdaRound.

**Important correction:** dequantizing an exported net does not reconstruct its lost pre-export precision. For the same exported weights, let S be the integer sum of clipped accumulator squares times output weights, and b the exported bias. [C++ inference](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/nnue.cpp#L259) returns:

```text
trunc(400 * (trunc(S / 255) + b) / (255 * 64))
```

In exact arithmetic, without overflow, its difference from the corresponding continuous expression is strictly below 1 + 400/(255*64) = **1.02451 cp**, or 0.00064032 after sigmoid(score/400). This is a mathematical bound on division rounding, not a measured export loss or a strength defect. Original float-to-grid feature and output-weight rounding is a separate, currently unmeasured effect.

**Gate:** at most 1M training and 200k held-out positions from bounded, documented own-data streams; cap the pilot at 20 GPU minutes after sample preparation. Validation must use net10's original stable held-out groups under its frozen manifest (gkey % 50 == 0), or genuinely unseen later groups. A new split of positions already seen by the frozen transformer is not an independent holdout. Score every arm through exported arithmetic against the same unchanged target. Define the ±200 cp subset once using a fixed baseline/source score for all arms, and report it alongside overall loss with game/group-blocked uncertainty. Reject improvements that vanish after export or occur only in decided positions. Keep output weights within the [loader's ±128 limit](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/nnue.cpp#L84), preserve all integer safety constraints, and check against [check_inference.py](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/nnue/check_inference.py).

A smaller prediction loss need not improve search, and trajectory-position errors do not measure sibling-move ranking. This is a cheap optimization screen, not a promise that net10 is poorly quantized.

## 3. Conservative capture futility in quiescence

[Current qsearch](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/search.cpp#L197) recursively searches legal noisy moves that pass SEE >= 0. It has no separate test of whether stand-pat plus captured material can plausibly reach alpha.

At a non-PV, non-check qnode, a candidate can skip recursion for ordinary nonchecking captures when:

```text
standPat + victimValue + margin <= alpha
```

Exclude promotions, en passant, mate-score windows and, conservatively, immediate recaptures. The recapture guard needs a prerequisite: current moveStack is not updated inside qsearch. Pass or update the previous move's destination through every qsearch recursion with correct null/root sentinels; do not read stale main-search stack data. ChessSI lacks a dedicated cheap gives-check operation, so an initial version can make the legal move and inspect check before deciding whether to recurse. This saves descendants, not the immediate accumulator update.

[Stockfish's qsearch futility](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp#L1786) is primary prior art and includes tactical exclusions. Its constants are not calibrated for ChessSI. This expression is a heuristic, **not a proved upper bound**: a harmless-looking capture can unlock a larger follow-up.

**Gate:** choose one margin and exclusions before collecting outcomes. Count eligible calls; counterfactually search a bounded sample of proposed cuts using unchanged qsearch and record alpha crossings and forcing-line misses. Measure net wall-time savings, not only fewer nodes. Stop if eligibility or savings is negligible. Keep this separate from any qsearch check-handling repair.

Inspected Claude branches qs-tt (77bd072), see-pruning (f643d8d), and bad-captures-last (fe632d0) did not contain this specific futility rule. Coordinate it with Claude's broader pruning queue before claiming it.

## 4. Audit whether old teachers use the same score scale

The training pool spans PeSTO and multiple NNUE generations, while [all scores use divisor 400](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/nnue/train.py#L433). The same centipawn number need not imply the same empirical outcome rate across teachers. Whether meaningful drift exists is unknown.

On at most 1M existing records with writer, network and node-budget manifests, fit one positive temperature T_g per cohort and compare with a single-temperature model on held-out groups. Compare similar material and score strata; keep fitting and evaluation separate. If the effect survives, an anchored candidate would transform old scores by:

```text
score'_g = score_g * T_newest / T_g
```

The newest cohort remains unchanged. Apply mappings consistently to main and future-score targets, preserving the 75/25 mixture, sample weights and architecture. This is distinct from averaging repeated observations. [Temperature scaling](https://proceedings.mlr.press/v70/guo17a.html) and [Stockfish's WDL fitting](https://github.com/official-stockfish/WDL_model) are Known precedents.

**Gate:** scalar calibration must improve a held-out proper score across writers/material strata before training. A later matched training pilot has a 60 GPU-minute combined cap. Evaluate both models against common unchanged reference targets and outcomes, never each model's transformed targets.

Changing playing strength, adjudication and position distributions can mimic scale drift. Calibration to weak self-play outcomes is not calibration to minimax truth. Do not use a successful calibration plot to justify changing engine score units or pruning thresholds.

## 5. A separate batched two-ply GPU teacher

GPUs can generate searched training targets. The current CPU generator is an implementation choice. A bounded first design expands legal moves on the CPU, batches leaf evaluations across independent roots on a GPU, then backs up probabilities:

```text
B_0(s) = net10's side-to-move probability
B_(d+1)(s) = max over legal a of [1 - B_d(child(s,a))]
```

Use exact terminal outcomes. Begin at depth two with the existing net10; no larger network or training is needed to test this mechanism. [TreeStrap](https://papers.nips.cc/paper_files/paper/2009/hash/389bc7bb1e1c2a5e7e147703232a88f6-Abstract.html) provides chess search-bootstrapping prior art. [NVIDIA's board-game GPU work](https://developer.nvidia.com/gpu-ai-board-games) establishes feasibility of GPU tree search generally, not a ChessSI speedup.

**Before CUDA engineering:** freeze 256 own-game roots, initially with halfmove clock zero to avoid unavailable pre-root reversible history. Cap expansion at 1M leaf records and all reference work at 40M CPU nodes; disclose excluded high-branching roots. Compare static, one-ply and two-ply labels against a frozen 32,768-node own-engine reference, plus 1,024-node and current 5,000-node controls. Reference searches are stronger comparisons, not ground truth. Assess selected moves with equal-budget child searches too.

Reject if two-ply backup fails to improve on static/one-ply controls. If it survives, implement identical batched arithmetic and measure complete pipeline throughput, including CPU move expansion, checks, terminal handling, transfers and backups. Reject if a CPU control dominates both quality and throughput. A survivor earns an equal-total-cost dataset/student comparison and then SPRT.

Two-ply leaves can be tactically unstable or in check, unlike the quiet positions on which net10 was trained. Existing CPU search already includes quiescence and deeper selective work. More labels may therefore be worse labels. GPU workers still need a coordinated CPU allocation; this route does not imply twice the useful compute.

## Deferred hypothesis: same-game covariance weighting

In White orientation, y_i = lambda*q_i + (1-lambda)*R_g. For residual e_i = p_i-y_i, two positions from one game satisfy:

```text
e_i - e_j = (p_i - p_j) - lambda * (q_i - q_j)
m = (e_i + e_j)/2; d = (e_i - e_j)/2
ordinary paired MSE = m*m + d*d
candidate L_rho = (1-rho)*m*m + (1+rho)*d*d
```

A small preregistered rho would de-emphasize common residuals and emphasize differences. This creates no information: ordinary MSE already contains both components. [NN-GLS](https://arxiv.org/abs/2304.09157), [centered/pairwise residual objectives](https://arxiv.org/abs/1406.2283), and [DeepChess's position comparisons](https://arxiv.org/abs/1711.09667) are relevant prior art. The specific NNUE adaptation's novelty is **not established**.

Algebraic cancellation of the realized result does not guarantee noise reduction. Conditional expected outcomes can change along a game; search errors can also be correlated. The loss may suppress useful result information or reinforce shallow-search mistakes. The existing auxiliary head and failed result-gradient-routing experiment are pertinent context.

A clean test needs explicit actual game identities. Conservative inferred groups in the repeated-label protocol can merge games: they protect validation separation but cannot certify same-game pairs. With adequate provenance, hold pair selection, marginal sample weights, batching and steps fixed; use rho=0 as control and a degree-matched diagonal-loss control if using an additive contrast formulation. Nearby trajectory positions are not sibling alternatives. Park this behind the cheaper tests.

## Leads rejected or parked by this review

- **Aborted search iterations corrupting datagen scores:** not supported. [Search::think](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/search.cpp#L523) updates its result only after a non-stopped completed root search. Partial iterations do not replace the last completed score.
- **Double-estimator minimax backups:** defer. Min and max alternate; the bias is not uniformly positive. Cross-evaluating another network's selected variation can miss the second network's preferred defense. [Double Q-learning](https://papers.neurips.cc/paper/3964-double-q-learning.pdf) is motivation, not a minimax guarantee. The proposal needs to beat a simpler matched-cost ensemble first.
- **400-ply censored draws:** [datagen](https://github.com/LupeHiguera/ChessSI/blob/35cb09b31fc1efae63e13c1da17a9285623e1cb5/src/datagen.cpp#L15) labels games reaching the 400-ply cap as draws without recording termination reason. This is a Known distinction between artificial truncation and terminal outcomes ([Pardo et al.](https://proceedings.mlr.press/v80/pardo18a.html)), but its frequency and practical effect here are unknown. Add provenance/counters during a future authorized datagen change before proposing label corrections. Existing filtered rows cannot reliably reconstruct every ending.
- Larger own-network teachers, disagreement sampling, playout-cap randomization, vine self-play, self-distillation heads and history-based LMR were already proposed or owned. They are not new discoveries from this sprint.

## Execution handoff

The current instruction is research only. When experiments resume, resolve the existing label-study gate first or coordinate one replacement priority with Claude. Claim one experiment, fetch main, and work only in ChessSI-astra on an astra/ branch.

When compute work resumes, retain WSL CPUs 14-19, CONCURRENCY=5, taskset -c 14-19 make -j6, and BOOK=../ChessSI/books/UHO_Lichess_4852_v1.epd. Reserve GPU/RAM separately with Claude; none was reserved here. PC2, when available, can supply isolated CPU games/data generation; GPU training remains on the GPU-equipped machine.

Use existing tests and exact inference checks where relevant. Behavior-preserving changes must preserve bench nodes. Every surviving candidate needs its own single-thread SPRT [0,5] at 10+0.1 against the latest accepted baseline; follow the roadmap's longer-time confirmation. Log failed offline gates without fabricated Elo. Source findings, offline losses, throughput and match strength are separate evidence.
