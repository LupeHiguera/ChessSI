# 100 ranked research ideas for ChessSI

**Research snapshot: 2026-10-29. Base: `ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd`.** Prepared by Codex with three delegated Astra ultra reviews covering search, learning, and execution. Existing proposals retain their original attribution in the linked sources.

ChessSI has credible opportunities in both search and learned evaluation. My strongest broad bets are qsearch transposition reuse, singular extensions, properly controlled king-bucket features, capture ordering, and better own-search labels. The cheapest useful screens include IIR, quantized output refitting, illegal-move accumulator deferral, and compilation/inference specialization. These judgments require experiments; this report contains no new Elo result.

This is a ranked portfolio of **40 search, 40 learning/data, and 20 execution/measurement ideas**. It consolidates useful prior proposals and adds concrete experiments found during this review. It contains **64 known methods, 31 adaptations, and 5 hypotheses**, using the labels below. It is a backlog of 100 testable interventions, with dependencies and some shared controls; their gains must never be summed.

## How to read the ranking

Rank estimates useful progress toward playing strength over several research cycles, considering the size of a plausible missing capability, evidence for its mechanism, applicability to this code, and the full cost of finding out. It is an editorial judgment, not a fitted score, a probability of success, an Elo forecast, or the order in which the PC should run jobs. Adjacent ranks are weakly distinguished. A high-cost architecture can rank highly for upside while a lower-ranked speed change deserves an earlier cheap screen.

- **Known:** established engine/training technique; ChessSI benefit still unmeasured for this proposal.
- **Adaptation:** an established idea with a specific ChessSI representation, signal, or control.
- **Hypothesis:** a less-established mechanism worth falsifying; no global novelty claim. Prior-art checks and a reproducible comparison are still required before calling it novel.
- **Backlog/Draft:** already present in inspected project work. **Additional:** this concrete intervention was not found in the inspected backlog; that is not proof of worldwide novelty. **Retest:** an earlier failure requires a stated changed premise.
- **Cost low/medium/high:** relative implementation and decisive-pilot cost, including controls. Low does not mean a full SPRT is free. Large data creation, network training, and CPU inference changes are charged to the learning experiment.

**The czar's queue remains authoritative:** #59 → #60 → #66 → #67 with its dependency resolved → #64. #63 and #69 remain parked. #71 is the assigned network path. These research recommendations create no claim or permission to consume experimental cores. [Coordination decision](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6486478219)

The separate [Grok/Cursor review](GROK_REVIEW.md) explains five practical corrections: match warm starts in the bucket comparison; fix saturated bucket-transition fixtures; provide gradient flow for the residual head; use random-deep mining controls; and verify the actual loaded network before treating a completed network match as valid. The new runner draft #72 addresses the previously identified swallowed-error paths, subject to behavioral validation and merge.

## Where I would concentrate attention

| Question | Highest-priority candidates | Why |
| --- | --- | --- |
| Missing search capabilities | S01, S03, S04, S02, S06 | Concrete gaps, established mechanisms, and prepared drafts or clean decompositions. |
| Larger medium-term evaluator upside | L03, L04, L11, L16, L25, L26 | Better interactions or targets could change the engine's ceiling, provided inference cost and controls hold up. |
| Cheap falsification opportunities | S02, E01, L01, E03, E02 | Small pilots can resolve usefulness before long game tests. |
| Preserve CPU throughput while learning | L02, L07, L10 | Training/export changes can preserve the deployed architecture. |
| More unusual search research | S36, S38, S39, S40 | Explicit cost or falsification signals; first establish incremental information beyond simpler controls. |

E01's completed audit reported about 23% rejected accumulator updates in its measured workload. That is a count of updates, **not 23% of search time or a predicted speedup**. L05 needs evidence that retained data restores useful coverage, rather than duplicating recent data. L03 and L04 rank highly for plausible upside, not because their expensive controls have already passed. [Audit][AUDIT], [retention proposal][R27]

## Rules shared by every card

For search, freeze the accepted source/network/book, change one mechanism, and keep node-type, excluded-search, mate/draw and stop semantics correct. Diagnostic roots and shadow searches can establish coverage or failure modes; deeper selective search is not chess ground truth. Select thresholds on development games and assess them on untouched games. Only a proper timed match supports a strength claim.

For speed-only changes, require perft and exact bench-node parity, then alternating whole-search timings on held-out roots at fixed hash and threads. Microbenchmark speed alone is insufficient. A declared simplification uses the project's [-5, 0] test; a claimed gainer uses [0, 5]. All final acceptance follows AGENTS.md.

For learning, use only ChessSI positions, its own search labels, and permitted game results. Split by whole game/root family; freeze manifests and the assessment set. Match functional initialization, auxiliary heads, optimizer policy, row presentations and cost where the causal contrast requires it. Architecture identity does not follow from a shared RNG seed. Compare exported integer networks, include CPU timed tests, and validate the requested network actually loaded. External engines and papers here supply prior art, never labels, weights or datasets.

Keep the prescribed shared opening book read-only and the default search Threads=1. SMP proposals require their own recorded equal-thread tests. The inherited TT concurrency issue is a prerequisite to trustworthy SMP experiments even though its portfolio rank is lower than some dependent ideas. E19/E20 concern measurement efficiency, not direct engine Elo.

Dependencies matter: S11/S22 need useful continuation statistics; S23/S24 benefit from capture history; S35 follows single singular extensions; E09/E10 are defined against the accepted qs-TT behavior; E06 must show savings beyond E01. L06 supplies a control for L03 as well as a standalone fresh-versus-warm question. L19/L20 are alternative selection signals, not gains to assume stack. Test their additional value before combining.

A losing result is logged with its uncertainty and games. Retests need a new premise. Do not promote a patch from training loss, fixed-node results, a single game, or this ranking. A fair stronger-opponent gauntlet is still needed to quantify the overall Stockfish gap. Matching or beating one chess engine would demonstrate task-specific research progress; it would not by itself establish AGI.

## Complete ranked list

Each card specifies the intervention, the first distinguishing gate, and why it may fail. Linked evidence supports prior art, present code or proposal status; it does not establish a ChessSI Elo gain. Stop at a failed gate, or revise and record the hypothesis before spending more compute.

## Ranks 1–25

### 1. Quiescence transposition table (S01)

**Known · Draft #59 · Cost: low.**

Probe and store qsearch bounds with depth-aware retention.

- **First gate:** Measure hit/cutoff rates and equal-time search; test bound/stop semantics.
- **Failure mode:** Lookup traffic and shallow replacement can erase savings.
- **Evidence:** [ChessSI PR #59][PR59].

### 2. Singular extensions (S03)

**Known · Draft #60 · Cost: medium.**

Use an exclusion search to deepen uniquely necessary TT moves.

- **First gate:** Assert exclusion restoration and activation; measure verification cost and tree tails.
- **Failure mode:** Verification and extension chains may cost too much.
- **Evidence:** [ChessSI PR #60][PR60].

### 3. King-bucket feature transformer (L03)

**Known · Draft #71; controls need repair · Cost: high.**

Train a net12-initialized shared transformer plus king-bucket residuals, exporting dense bucket tables.

- **First gate:** Fix unsaturated transition tests and use a warm flat control with copied auxiliary weights; screen one bucket family.
- **Failure mode:** Sparse buckets, refresh work and cache traffic can exceed representation benefits.
- **Evidence:** [King-bucket trainer, pinned #71][P71]; [Grok experiment specifications, pinned #69][E69]; [Stockfish NNUE architecture and training methods][H].

### 4. Independent capture history (S04)

**Known · Draft #67; simplify first · Cost: low.**

Learn capture ordering within existing SEE bands, initially from own cutoffs and earlier-capture penalties.

- **First gate:** Unstack from continuation history; compare cutoff rank and equal-time roots.
- **Failure mode:** Incorrect or noisy reward updates can teach bad ordering.
- **Evidence:** [ChessSI PR #67][PR67].

### 5. Internal iterative reduction (S02)

**Known · Draft #66 · Cost: low.**

Reduce one ply at deep nonroot nodes lacking a TT move.

- **First gate:** Measure activation after qs-TT; guard excluded verification; assess equal-time decisions.
- **Failure mode:** First encounters may contain the important move.
- **Evidence:** [ChessSI PR #66][PR66].

### 6. Uniform deeper own-search labels (L04)

**Known · Backlog #69 · Cost: high.**

Replace shallow scores on a fixed position set with deeper ChessSI search targets.

- **First gate:** Separate same-row shallow/deep quality from equal-total-cost shallow-volume/deep-quality comparisons.
- **Failure mode:** Deeper selective search still makes errors and buys fewer positions per hour.
- **Evidence:** [Grok experiment specifications, pinned #69][E69]; [Bootstrapping from search][TREE].

### 7. Skip accumulator updates for illegal moves (E01)

**Known · Audit done; implementation pending · Cost: low.**

Check post-move king safety before applying NNUE deltas; track undo state explicitly.

- **First gate:** Use completed audit fixtures, exact-node parity and alternating whole-search timing.
- **Failure mode:** Undo/null bookkeeping or lost prefetch overlap can erase savings.
- **Evidence:** [Completed rejected-update audit][AUDIT].

### 8. Folded feature factorization (L02)

**Known · Backlog · Cost: medium.**

Train shared piece/type/file/rank components plus residual rows, then fold them into the existing feature table.

- **First gate:** Match the initial folded matrix, data order and effective gradient scale against ordinary training.
- **Failure mode:** Different optimization dynamics or overregularization can masquerade as better features.
- **Evidence:** [October 26 research][R26]; [Stockfish NNUE architecture and training methods][H].

### 9. Refit the quantized output head (L01)

**Known · Backlog · Cost: low.**

Freeze net12's exported transformer and optimize its 513 readout parameters with deployment-aware rounding.

- **First gate:** Use at most 1M training rows; compare unchanged, continuous-refit and quantized-refit exports on untouched games.
- **Failure mode:** Rounding or score calibration may erase apparent loss gains.
- **Evidence:** [October 25 research][R25]; [Stockfish NNUE quantization implementation][Q].

### 10. Persistent continuation history (S06)

**Known · Draft #61 · Cost: medium.**

Retain and decay one-/two-ply quiet context statistics across moves.

- **First gate:** Test alone with fixed ordinary-history reset policy; measure cutoff ranks.
- **Failure mode:** Sparse/aliased context may add cost without signal.
- **Evidence:** [ChessSI PR #61][PR61].

### 11. Null reduction from evaluation margin (S05)

**Known · Backlog · Cost: low.**

Add a bounded static-eval-minus-beta term to null reduction.

- **First gate:** Shadow-verify null cuts by margin/depth/material against equal-cost baseline.
- **Failure mode:** Misestimated static advantage can create false cutoffs.
- **Evidence:** [Stockfish 17 search][SF17].

### 12. Nonpawn placement correction (S09)

**Known · Backlog · Cost: low.**

Learn bounded residual corrections keyed by nonpawn locations.

- **First gate:** Game-held-out residual prediction versus equal-memory pawn-only control.
- **Failure mode:** Additional keys may double-count correlated errors.
- **Evidence:** [Stockfish 19 search][SF19].

### 13. Specialized H256 inference (E03)

**Known · Backlog · Cost: low.**

Dispatch to constant-size H256 kernels while retaining a dynamic fallback.

- **First gate:** Check every output and fallback load; time full search.
- **Failure mode:** Extra unrolling can harm instruction-cache behavior.
- **Evidence:** [ChessSI current NNUE implementation][NNUE].

### 14. Link-time optimization (E02)

**Known · Additional · Cost: low.**

Compile unchanged sources with LTO, holding compiler and other flags fixed.

- **First gate:** Require node parity and held-out alternating complete-search timings.
- **Failure mode:** Code growth or toolchain effects may regress performance.
- **Evidence:** [GCC optimization documentation][GCC].

### 15. Recent data plus replay (L05)

**Known · Backlog · Cost: medium.**

Retain a fixed old-generation fraction in each new training dataset.

- **First gate:** Compare 32M recent rows with 24M shared recent plus 8M old at fixed updates; assess recent and old holdouts.
- **Failure mode:** Old teacher errors may dilute improvements on current play.
- **Evidence:** [Training/data follow-up][R27]; [Experience replay research][REPLAY].

### 16. Threat-aware quiet ordering (S21)

**Known · Backlog #57 · Cost: low.**

Reward escaping cheaper attackers and penalize entering their attacks.

- **First gate:** Compare with attack-mask-computation-only control at equal time.
- **Failure mode:** May reward passivity or penalize sound sacrifices.
- **Evidence:** [Stockfish 17 move ordering][MP17].

### 17. Warm-start ordinary H256 (L06)

**Known · Additional; control for L03 · Cost: medium.**

Continue net12 on new own data with a declared optimizer restart.

- **First gate:** Fresh versus dequantized warm initialization at fixed architecture/data; distinguish fixed-update and fixed-time outcomes.
- **Failure mode:** Old-data bias and reduced plasticity can hinder learning.
- **Evidence:** [ChessSI current trainer][T]; [Training/data follow-up][R27].

### 18. Quantization-aware finishing (L10)

**Known · Backlog · Cost: medium.**

Fake-quantize transformer and output during a short continuation.

- **First gate:** Start from one checkpoint; compare ordinary continuation and QAT at matched work, then integer errors and timed games.
- **Failure mode:** Coarse or biased gradients can prevent useful learning.
- **Evidence:** [Stockfish NNUE quantization implementation][Q]; [Existing NNUE training proposals][M].

### 19. Material-count correction (S29)

**Adaptation · Backlog · Cost: low.**

Pool evaluation residuals by piece counts and side to move.

- **First gate:** Replicate material-key signal on held-out games against equal-memory correction.
- **Failure mode:** Coarse classes can average opposite positional errors.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 20. Exact raw-evaluation cache (E04)

**Known · Backlog #57 · Cost: low.**

Cache raw NNUE outputs using verified full feature identity and network generation.

- **First gate:** Bound entries; charge lookup costs; preserve nodes at fixed TT size.
- **Failure mode:** Identity verification and cache traffic may dominate hits.
- **Evidence:** [ChessSI PR #57][PR57].

### 21. Root node-fraction time allocation (S25)

**Known · Backlog · Cost: low.**

Scale soft time using how much work supports the final best root move.

- **First gate:** Replay game clock traces at matched total time.
- **Failure mode:** Root work share can reflect ordering bias rather than difficulty.
- **Evidence:** [Stockfish 17 search][SF17].

### 22. Average late weights at export (L07)

**Known · Backlog · Cost: low.**

Use one predetermined EMA or SWA schedule during ordinary training.

- **First gate:** Compare last and averaged checkpoints from the same trajectory on an untouched holdout and integer exports.
- **Failure mode:** Averaging incompatible regions may degrade quantized predictions.
- **Evidence:** [Weight averaging paper][SWA]; [Existing NNUE training proposals][M].

### 23. Distill a larger own-data teacher (L11)

**Adaptation · Backlog; H512 slowdown, strength inconclusive · Cost: high.**

Transfer a wider ChessSI network's predictions into the fast H256 model.

- **First gate:** Compare one teacher target with existing targets; include equal-total-training-cost controls and disjoint teacher holdout.
- **Failure mode:** Teacher errors may not transfer usefully, despite higher capacity.
- **Evidence:** [Existing NNUE training proposals][M]; [ChessSI measured log and backlog][IDEAS].

### 24. Cut-node-aware reductions (S07)

**Known · Part of parked #65 · Cost: low.**

Add only the cut-node reduction term under the existing LMR gate.

- **First gate:** Audit reduced fail-lows at matched work; verify node-type propagation.
- **Failure mode:** Wrong node classification magnifies tactical misses.
- **Evidence:** [ChessSI PR #65][PR65].

### 25. Softer reverse-futility return (S13)

**Known · Backlog · Cost: low.**

Keep the prune decision but return a bounded value between beta and static evaluation.

- **First gate:** Isolate changed return values; inspect ancestor re-searches and root decisions.
- **Failure mode:** Excessive softening can weaken useful bounds.
- **Evidence:** [Stockfish 19 search][SF19].

## Ranks 26–50

### 26. Deferred legal-node accumulators (E06)

**Known · Backlog · Cost: medium.**

Materialize stored dirty deltas only when an evaluation needs the accumulator.

- **First gate:** Compare against illegal-move-only deferral with separate legal-node savings.
- **Failure mode:** Long delta chains and repeated reconstruction can cost more.
- **Evidence:** [Stockfish accumulator update design][SFACC].

### 27. Small residual hidden layer (L16)

**Known · Backlog #69 · Cost: high.**

Keep the flat output path and add a zero-output-initialized 32-unit nonlinear residual.

- **First gate:** Verify identical initial predictions; compare matched warm-start controls, integer export and full-search cost.
- **Failure mode:** Extra dense arithmetic may cost more strength than the learned interactions add.
- **Evidence:** [Grok experiment specifications, pinned #69][E69]; [Stockfish NNUE architecture and training methods][H].

### 28. Clustered TT buckets (E05)

**Known · Backlog · Cost: medium.**

Use four full-key entries per cache-line bucket at unchanged total memory.

- **First gate:** Compare useful retained bounds and equal-time roots with replacement policy fixed.
- **Failure mode:** More comparisons or altered collisions can outweigh retention.
- **Evidence:** [Stockfish TT implementation][SFTT].

### 29. Continuation-informed reductions (S11)

**Known · Parked #68 · Cost: low.**

Use the combined quiet/continuation ordering score in LMR.

- **First gate:** Seed threshold boundaries and measure activation at realistic depths.
- **Failure mode:** Quantization may make the term inert or too abrupt.
- **Evidence:** [ChessSI PR #68][PR68].

### 30. Continuation correction (S18)

**Known · Backlog · Cost: medium.**

Learn evaluation residuals from preceding move contexts rather than ordering outcomes.

- **First gate:** Measure game-held-out signal beyond existing corrections at equal memory.
- **Failure mode:** Contextual residuals can overfit correlated games.
- **Evidence:** [Stockfish 19 search][SF19].

### 31. Refresh the CUDA search teacher (L12)

**Known · Backlog #69 · Cost: high.**

Bring accepted CPU TT, SEE, ordering and correction behavior into the own-data teacher.

- **First gate:** Establish CPU/GPU semantic parity, then compare old/new teacher datasets at matched complete cost.
- **Failure mode:** CPU search gains need not transfer to the trained student; a port can add bugs.
- **Evidence:** [Grok experiment specifications, pinned #69][E69]; [Training/data follow-up][R27].

### 32. Pin-aware static exchange evaluation (S20)

**Known · Backlog #57 · Cost: medium.**

Exclude illegal recapturers as exchange occupancy and pins change.

- **First gate:** Use a slow legal-exchange reference and a compute-only cost control.
- **Failure mode:** Dynamic pin handling is complex and paid at many nodes.
- **Evidence:** [Stockfish 19 position and SEE implementation][POS19].

### 33. Calibrate teacher-cohort scores (L08)

**Known · Backlog · Cost: medium.**

Fit cohort temperatures to anchor mixed-generation labels to the current teacher's scale.

- **First gate:** Transform versus retain targets on identical rows; assess held-out writer/material strata and common outcome metrics.
- **Failure mode:** Distribution or strength differences can look like mere calibration drift.
- **Evidence:** [October 25 research][R25]; [Temperature scaling paper][CAL].

### 34. Protect checking quiets (S17)

**Known · Backlog · Cost: low.**

Exempt direct/discovered checking moves from futility and LMP.

- **First gate:** Compare check detection with make/check reference and sample avoided prunes.
- **Failure mode:** Check detection may be costly or incomplete.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 35. Improving-sensitive late-move pruning (S10)

**Known · Backlog · Cost: low.**

Adjust the quiet move-count limit using same-side evaluation improvement.

- **First gate:** Shadow-search pruned quiets by flag, depth and rank.
- **Failure mode:** A noisy improving flag can prune necessary defenses.
- **Evidence:** [Stockfish 17 search][SF17].

### 36. Phase-balanced sampling (L09)

**Known · Backlog · Cost: medium.**

Reweight presentations by piece count toward a preregistered evaluation-use distribution.

- **First gate:** Hold row pool and updates fixed; compare uniform and fixed phase weights with phase-specific guardrails.
- **Failure mode:** Overweighting rare endgames can weaken common middlegames.
- **Evidence:** [Stockfish training loader configuration][FILTER].

### 37. Sample non-PV search positions (L13)

**Known · Backlog · Cost: high.**

Collect quiet evaluated side positions and relabel them with ChessSI search.

- **First gate:** Add equal-size/equal-cost trajectory or non-PV data; group holdouts by originating game and root.
- **Failure mode:** Correlated and unreliable tree nodes can swamp useful trajectory data.
- **Evidence:** [Stockfish non-PV data generation][NONPV].

### 38. ProbCut (S16)

**Known · Backlog · Cost: medium.**

Use raised-beta tactical probes and reduced confirmation to prune selected non-PV nodes.

- **First gate:** Shadow-confirm proposed cuts, including sacrifice and mate-bound cases.
- **Failure mode:** Extra probes or false confidence can lose time and tactics.
- **Evidence:** [Stockfish 17 search][SF17].

### 39. Pawn-conditioned quiet history (S12)

**Known · Additional · Cost: medium.**

Condition quiet ordering statistics on pawn structure as well as piece and destination.

- **First gate:** Compare cutoff rank with equal memory and no new pruning.
- **Failure mode:** Sparsity can overwhelm structural specificity.
- **Evidence:** [Stockfish 17 move ordering][MP17].

### 40. Profile-guided compilation (E08)

**Known · Additional · Cost: low.**

Compile using a frozen profile from diverse own-game search roots.

- **First gate:** Hold LTO/source/compiler fixed and assess on disjoint roots.
- **Failure mode:** Training-profile overfit may not transfer to real play.
- **Evidence:** [GCC optimization documentation][GCC].

### 41. Surprise versus agreement weighting (L15)

**Adaptation · Backlog · Cost: medium.**

Use capped weights based on static/search disagreement for existing rows.

- **First gate:** Uniform, agreement-favored and disagreement-favored arms use identical rows, updates and assessment games.
- **Failure mode:** High disagreement may identify irreducible tactical noise.
- **Evidence:** [ChessSI measured log and backlog][IDEAS]; [KataGo methods][KATA].

### 42. Recycle dormant hidden units (L18)

**Adaptation · Backlog · Cost: medium.**

Reinitialize persistently inactive units and all their outgoing heads.

- **First gate:** Require two independent activation audits; compare recycling with untouched continuation and matched optimizer resets.
- **Failure mode:** Rare useful specialists can appear dormant in a small sample.
- **Evidence:** [October 26 research][R26]; [Dormant neuron recycling research][REDO].

### 43. History updates after reduced probes (S22)

**Known · Backlog · Cost: low.**

Learn continuation statistics from confirmation or overturning of LMR probes.

- **First gate:** Measure future ordering value beyond ordinary cutoff updates.
- **Failure mode:** Selected probes and double rewards can bias learning.
- **Evidence:** [Stockfish 17 search][SF17].

### 44. Castling-right feature rows (L17)

**Adaptation · Backlog #57 · Cost: high.**

Add explicit castling-right indicators to the accumulator.

- **First gate:** First audit own-search residual differences by rights; train with zero-initialized new rows and matched controls.
- **Failure mode:** The signal may be too rare to justify feature maintenance.
- **Evidence:** [Previous ten research cards][G57]; [ChessSI current trainer][T].

### 45. Correction-sensitive pruning margin (S14)

**Adaptation · Backlog · Cost: low.**

Widen only RFP's margin when correction magnitude suggests uncertainty.

- **First gate:** Compare false-prune rates with an equal-average-margin control.
- **Failure mode:** Large correction may be stable useful bias, not uncertainty.
- **Evidence:** [Stockfish 19 search][SF19].

### 46. Mate-distance pruning (S30)

**Known · Backlog · Cost: low.**

Clamp search windows to mate scores attainable at the current ply.

- **First gate:** Verify bound endpoints and TT mate-score conversion.
- **Failure mode:** Incorrect score normalization can corrupt mate bounds.
- **Evidence:** [Stockfish 17 search][SF17].

### 47. Instability-driven deep labeling (L19)

**Adaptation · Backlog · Cost: high.**

Spend extra teacher nodes where successive completed iterations disagree.

- **First gate:** Selected-deep versus random-deep at equal labeling cost, with identical base data and untouched assessment roots.
- **Failure mode:** Instability may identify positions that remain unreliable at any practical budget.
- **Evidence:** [Existing self-play/data proposals][D].

### 48. Own-network disagreement mining (L20)

**Adaptation · Backlog #69; revise control · Cost: high.**

Deep-label positions where two independently useful ChessSI networks disagree.

- **First gate:** Use random-deep controls, shared shallow base and matched phase mix; charge both selection and labeling costs.
- **Failure mode:** Score scale or material bias can inflate disagreement without identifying blind spots.
- **Evidence:** [Grok experiment specifications, pinned #69][E69].

### 49. Independent NNUE dot-product sums (E12)

**Known · Additional · Cost: low.**

Use several independent SIMD accumulation chains before final reduction.

- **First gate:** Prove overflow bounds, exact outputs and full-search improvement.
- **Failure mode:** Register pressure can outweigh shorter dependency chains.
- **Evidence:** [ChessSI current NNUE implementation][NNUE].

### 50. Qsearch delta pruning (S08)

**Known · Additional · Cost: low.**

Skip captures whose stand-pat plus plausible material gain cannot reach alpha.

- **First gate:** Search sampled rejects fully; exempt checks/promotions and inspect tactical tails.
- **Failure mode:** Compensation and sacrifices defeat crude gain bounds.
- **Evidence:** [Stockfish 10 search][SF10].

## Ranks 51–75

### 51. Static-evaluation history updates (S15)

**Known · Additional · Cost: low.**

Update preceding quiet-move history from static-evaluation changes.

- **First gate:** Test added prediction of later cutoffs against matched update-count control.
- **Failure mode:** Tactical transients can reward misleading static swings.
- **Evidence:** [Stockfish 17 search][SF17].

### 52. Randomize playout caps (L14)

**Adaptation · Backlog · Cost: high.**

Play many self-play moves cheaply but retain only designated full-search positions.

- **First gate:** Compare fixed and randomized budgets at equal total nodes while holding recorded-label quality fixed.
- **Failure mode:** Weaker unrecorded play can corrupt game-outcome targets.
- **Evidence:** [KataGo methods][KATA]; [Existing self-play/data proposals][D].

### 53. Select completed helper results (E07)

**Known · Backlog #57; SMP only · Cost: low.**

Use coherent completed helper records with conservative agreement/depth election.

- **First gate:** Measure coverage, then equal-three-thread matches; avoid uncalibrated score voting.
- **Failure mode:** Correlated helpers can reinforce the same mistake.
- **Evidence:** [ChessSI PR #57][PR57].

### 54. Prioritize own-game start replay (L21)

**Adaptation · Backlog · Cost: high.**

Begin some new games from difficult archived ChessSI positions.

- **First gate:** Compare prioritized versus uniform starts from the same pool at equal search work and root-separated validation.
- **Failure mode:** Repeated hard starts can collapse diversity and distort results.
- **Evidence:** [Existing self-play/data proposals][D]; [Experience replay research][REPLAY].

### 55. BMI2 PEXT sliding attacks (E11)

**Known · Additional · Cost: low.**

Use PEXT attack indices on suitable CPUs with a magic fallback.

- **First gate:** Exhaustive attack equivalence and whole-search timing on the actual machine.
- **Failure mode:** Processor-specific latency can reverse the result elsewhere.
- **Evidence:** [Stockfish sliding-attack implementation][SFBB].

### 56. Compact attacked-piece features (L25)

**Adaptation · Backlog #69 · Cost: high.**

Add sparse inputs indicating which occupied pieces are attacked.

- **First gate:** Screen representation offline before incremental implementation; compare matched training and timed CPU search.
- **Failure mode:** Attack semantics and incremental update work may erase the gain.
- **Evidence:** [Grok experiment specifications, pinned #69][E69]; [Viridithas threat-feature experiment][THREAT].

### 57. Low-rank cross-perspective products (L26)

**Adaptation · Backlog #57 · Cost: high.**

Add a small set of products between learned friendly/enemy activation projections.

- **First gate:** Compare a product branch with a similarly sized ordinary residual branch at matched initialization and work.
- **Failure mode:** The added interaction capacity may duplicate existing SCReLU effects.
- **Evidence:** [Previous ten research cards][G57].

### 58. Late capture reductions (S23)

**Known · Backlog · Cost: medium.**

Reduce selected late captures using established history and tactical safeguards.

- **First gate:** Capture-specific false-low audit and sacrifice/recapture fixtures.
- **Failure mode:** Captures can be forcing even when ordered late.
- **Evidence:** [Stockfish 19 search][SF19].

### 59. History-based quiet pruning (S19)

**Known · Additional · Cost: low.**

Prune very negative-history quiets at shallow non-PV nodes, with forcing-move exemptions.

- **First gate:** Audit rejects against equal-count ordinary LMP.
- **Failure mode:** New tactical resources have little positive history.
- **Evidence:** [Stockfish 17 search][SF17].

### 60. Quiet-sibling ranking loss (L23)

**Adaptation · Backlog · Cost: high.**

Add a pairwise objective for independently searched alternative quiet children.

- **First gate:** Pointwise, pointwise-plus-ranking and degree-matched reweighting arms share roots and labels.
- **Failure mode:** Noisy sibling ordering can damage absolute score calibration.
- **Evidence:** [October 26 research][R26]; [DeepChess position comparisons][DEEPCHESS].

### 61. Distill an own-teacher ensemble (L22)

**Adaptation · Backlog · Cost: high.**

Average probabilities from independently trained ChessSI teachers into one student.

- **First gate:** Compare with one teacher at fixed student budget and equal-total-cost teacher/data alternatives.
- **Failure mode:** Correlated teachers and extra inference expense may buy little signal.
- **Evidence:** [Existing NNUE training proposals][M].

### 62. Capture futility (S24)

**Known · Additional · Cost: low.**

Use evaluation, victim value, depth and capture history to reject insufficient captures.

- **First gate:** Compare sampled rejects against equal-count SEE pruning.
- **Failure mode:** Material bounds miss compensation and follow-up checks.
- **Evidence:** [Stockfish 17 search][SF17].

### 63. Draw-clock-safe TT cutoffs (S31)

**Known · Backlog · Cost: low.**

Restrict incompatible score reuse near the fifty-move boundary, preserving move ordering.

- **First gate:** Reuse clock-context fixtures and complete-history roots.
- **Failure mode:** Useful decision changes may be rare despite a real context issue.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 64. Mask artificially censored outcomes (L29)

**Known · Backlog · Cost: medium.**

Record termination reasons and mask only the result component of maximum-ply truncations.

- **First gate:** Compare unchanged and masked cap outcomes on the same rows while retaining search-score supervision.
- **Failure mode:** Few truncations or selection bias may make this ineffective.
- **Evidence:** [October 25 research][R25]; [Time limits and censored returns][TIME].

### 65. Atomic TT access with validated snapshots (E18)

**Known · Additional; SMP correctness · Cost: medium.**

Replace concurrent plain-field accesses with atomics and local checked records.

- **First gate:** Check one-thread parity, snapshot consistency and equal-thread performance.
- **Failure mode:** Atomic fields alone do not guarantee a coherent multi-field record.
- **Evidence:** [Stockfish TT implementation][SFTT].

### 66. Score-responsive aspiration width (S26)

**Adaptation · Additional · Cost: low.**

Set initial aspiration width from recent root-score variation; this is an adaptation of score-statistic-based width policies.

- **First gate:** Compare completed-root quality and re-search cost on untouched roots.
- **Failure mode:** Wide windows may waste more than they save.
- **Evidence:** [Stockfish 19 search][SF19].

### 67. Game-balanced training weights (L31)

**Known · Additional · Cost: medium.**

Bound each game's total loss weight instead of weighting every row equally.

- **First gate:** Keep rows and updates fixed; compare uniform-row and uniform-game weighting by game length and phase.
- **Failure mode:** Uniform games need not match the evaluator's real usage distribution.
- **Evidence:** [ChessSI current trainer][T].

### 68. Aligned NNUE buffers (E13)

**Known · Additional · Cost: low.**

Guarantee cache-line alignment for parsed weight rows and accumulators.

- **First gate:** Keep kernel and weights identical; measure real address alignment and search time.
- **Failure mode:** Modern unaligned loads may already be inexpensive.
- **Evidence:** [Stockfish affine-transform implementation][SFNNUE].

### 69. Result weight by distance to game end (L28)

**Adaptation · Backlog · Cost: medium.**

Allocate more outcome weight near actual termination while preserving average weight.

- **First gate:** Use identical targets otherwise; include shuffled-distance weights to separate structure from generic reweighting.
- **Failure mode:** Post-hoc distance can introduce selection bias.
- **Evidence:** [Existing self-play/data proposals][D].

### 70. Verify selected null cutoffs (S27)

**Known · Additional · Cost: medium.**

Confirm selected deep null fail-highs with null pruning disabled.

- **First gate:** Measure falsification rates and cost by material/depth.
- **Failure mode:** Verification may duplicate almost every successful probe.
- **Evidence:** [Stockfish 17 search][SF17].

### 71. Temporal lambda-return targets (L27)

**Adaptation · Backlog · Cost: high.**

Replace part of terminal-result supervision with a fixed mixture of later own-search values.

- **First gate:** Freeze the outer blend and lambda-return definition; disclose effective terminal-result weight and include a constant-result-weight control.
- **Failure mode:** Bootstrapping can reinforce the teacher's own errors.
- **Evidence:** [Existing NNUE training proposals][M]; [KataGo methods][KATA].

### 72. Huge-page TT allocation (E14)

**Known · Additional · Cost: low.**

Request huge pages for the same TT bytes with normal-page fallback.

- **First gate:** Verify effective page size and time both current and larger hash settings.
- **Failure mode:** May offer little at 16 MiB or fail to obtain huge pages.
- **Evidence:** [Stockfish memory allocation][SFMEM].

### 73. Forecast iteration completion (S33)

**Adaptation · Additional · Cost: medium.**

Predict next-iteration cost and avoid iterations unlikely to finish in usable time; the exact predictor is proposed beyond the cited adaptive-time baseline.

- **First gate:** Calibrate on game traces; compare equal-total-time decisions.
- **Failure mode:** Bad forecasts can abandon a decisive search.
- **Evidence:** [Stockfish 17 search][SF17].

### 74. Deployment-density weighting (L32)

**Adaptation · Backlog · Cost: high.**

Estimate a capped ratio between search-evaluated states and training trajectories.

- **First gate:** Require held-out discriminator signal; compare uniform, ratio and phase-only weighting at equal full cost.
- **Failure mode:** Unstable density estimates can overemphasize rare states.
- **Evidence:** [Existing self-play/data proposals][D]; [Stockfish non-PV data generation][NONPV].

### 75. Halfmove-clock evaluator input (L24)

**Adaptation · Additional · Cost: high.**

Add a compact clock embedding while keeping draw adjudication separate.

- **First gate:** Audit naturally repeated boards across clocks; make data identity/cache clock-aware before zero-row matched training.
- **Failure mode:** Sparse clock variation may not support the extra representation.
- **Evidence:** [ChessSI current trainer][T].

## Ranks 76–100

### 76. Countermove ordering (S32)

**Known · Additional · Cost: low.**

Try one successful reply keyed by previous piece/destination before ordinary quiets.

- **First gate:** Measure unique hits after killer/TT deduplication.
- **Failure mode:** May duplicate continuation history with no net benefit.
- **Evidence:** [Stockfish 10 search][SF10].

### 77. Protect deep entries from exact qsearch overwrites (E09)

**Adaptation · Additional; conditional on #59 · Cost: low.**

After qs-TT, retain same-key current-generation entries at depth >=3 against incoming depth-0 exact writes only.

- **First gate:** First count eligible overwrites and subsequent useful deep hits; compare unchanged #59 at fixed memory and full keys.
- **Failure mode:** Mostly wide-window opportunities may be rare; fresh exact qsearch information is also useful.
- **Evidence:** [ChessSI PR #59][PR59].

### 78. Bounded double singular extension (S35)

**Known · Backlog #69; split bundle · Cost: medium.**

Give a second ply only for stronger singular evidence, with a separate double-extension budget.

- **First gate:** After #60 passes, measure tactical recovery and tail growth; hold check policy fixed.
- **Failure mode:** Extra depth can lose badly at short controls.
- **Evidence:** [Stockfish 19 search][SF19].

### 79. Residual auxiliary head with gradient flow (L33)

**Hypothesis · Backlog #69; repaired mechanism · Cost: high.**

Train a deep-minus-shallow residual head with bounded gradients into the shared representation.

- **First gate:** Compare no head, detached head and attached head; assert gradient connectivity before training and match gradient scale.
- **Failure mode:** It competes for H256 capacity and may repeat previous auxiliary-head losses.
- **Evidence:** [Grok experiment specifications, pinned #69][E69].

### 80. Early-learning regularization (L30)

**Adaptation · Existing local research note · Cost: medium.**

Use an early prediction average as a weak late-training regularizer.

- **First gate:** Match continuation work; include a shuffled-reference control and two seeds before a long run.
- **Failure mode:** It can freeze early mistakes and needs per-row state.
- **Evidence:** [Early-learning regularization paper][ELR].

### 81. Calibrate one pruning margin from shadow searches (S40)

**Adaptation · Backlog · Cost: medium.**

Audit sampled proposed prunes and fit a simple depth/material margin.

- **First gate:** Separate development games and equal-average-margin controls.
- **Failure mode:** Selective verification scores may not predict game value.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 82. One-sided search-bound supervision (L35)

**Adaptation · Backlog · Cost: high.**

Train hinge losses on valid fail-low/fail-high bounds without calling them exact scores.

- **First gate:** Audit sampled bounds against deeper own search; compare exact-only and added-bound training on the same roots.
- **Failure mode:** Selective shallow bounds are not guaranteed minimax bounds.
- **Evidence:** [Bootstrapping from search][TREE]; [Existing NNUE training proposals][M].

### 83. Capture cutoff probability per cost (S36)

**Adaptation · Backlog #57 · Cost: medium.**

Order good captures by shrunk cutoff probability divided by full search cost.

- **First gate:** Replay against ordinary capture history with matched bookkeeping.
- **Failure mode:** Costs depend on ordering, TT warmth and censored work.
- **Evidence:** [Minimum Proof Graphs and Fastest-Cut-First Search Heuristics][FCF].

### 84. Prefetch only legal child positions (E10)

**Known · Additional; conditional · Cost: low.**

Move TT prefetch after child legality is known, holding NNUE and accepted qs-TT behavior fixed.

- **First gate:** Compare with current unconditional prefetch at several hash sizes; count avoided fetches and lost overlap, requiring node parity.
- **Failure mode:** Later prefetch can lose latency overlap; exclude this from E01 to preserve a distinct contrast.
- **Evidence:** [ChessSI current position implementation][POSITION].

### 85. Sharpness-aware finishing (L38)

**Adaptation · Backlog · Cost: medium.**

Use SAM for a short predetermined final training phase.

- **First gate:** Compare ordinary continuation and SAM from one checkpoint at equal total compute, then integer exports.
- **Failure mode:** Two gradient passes may simply underfit relative to cheaper extra updates.
- **Evidence:** [Sharpness-aware minimization][SAM]; [Existing NNUE training proposals][M].

### 86. Check-aware qsearch on modern baseline (S28)

**Known · Retest; changed baseline · Cost: medium.**

Retest legal check evasions and no stand-pat in check on current NNUE/search.

- **First gate:** Use forced-check fixtures and tree-tail limits before games.
- **Failure mode:** The older version lost; extra evasion search may still be expensive.
- **Evidence:** [Stockfish 17 search][SF17].

### 87. Persistent helper threads (E15)

**Known · Additional; SMP only · Cost: medium.**

Park helper workers between moves while preserving current reset semantics.

- **First gate:** Measure launch latency and equal-thread full searches across many moves.
- **Failure mode:** Synchronization complexity may exceed tiny launch savings.
- **Evidence:** [Stockfish thread lifecycle][SFTHREAD].

### 88. Diversified helper depths (E16)

**Known · Additional; SMP only · Cost: medium.**

Use a fixed worker-dependent iteration-skipping schedule.

- **First gate:** Hold thread count/election fixed; measure duplicate work and equal-time decisions.
- **Failure mode:** Skipped depths can weaken move ordering and waste deeper work.
- **Evidence:** [Stockfish 8 search and worker diversification][SF8].

### 89. Reducible-loss data selection (L34)

**Adaptation · Backlog · Cost: high.**

Use own-data cross-fitted reference models to estimate which examples remain learnable.

- **First gate:** Compare uniform, raw-loss and reducible-loss sampling at equal complete compute and disjoint fitting/assessment games.
- **Failure mode:** Reference training and scoring may cost more than the saved updates.
- **Evidence:** [Reducible-loss data selection][RHO]; [Existing self-play/data proposals][D].

### 90. Upcoming repetition (S37)

**Known · Backlog #57 · Cost: medium.**

Recognize a legal reversible move that secures a qualifying repetition.

- **First gate:** Compare with legal enumeration using full history; track TT provenance.
- **Failure mode:** False positives or history-independent bounds are dangerous.
- **Evidence:** [Stockfish 19 position and SEE implementation][POS19].

### 91. Seed helper correction history (E17)

**Adaptation · Additional; SMP only · Cost: low.**

Copy main pawn-correction state at search start, then update privately.

- **First gate:** Compare zero versus copied initialization with identical election/lifecycle.
- **Failure mode:** Copies cost time and shared bias reduces diversity.
- **Evidence:** [ChessSI current search implementation][SEARCH].

### 92. One-layer quiet checks in qsearch (S34)

**Known · Additional · Cost: medium.**

Search safe quiet checks only at qsearch entry, with distinct TT semantics.

- **First gate:** Measure added tactical coverage and worst-case node tails.
- **Failure mode:** Check trees can expand much faster than expected.
- **Evidence:** [Stockfish 10 search][SF10].

### 93. Nested-width evaluation (L37)

**Adaptation · Backlog #69 · Cost: high.**

Train a useful narrow prefix and full evaluator, then deploy a fixed node-dependent width rule.

- **First gate:** First verify prefix quality; hold pruning margins fixed and compare flat-width controls in timed games.
- **Failure mode:** Inconsistent score functions can destabilize pruning and search.
- **Evidence:** [Grok experiment specifications, pinned #69][E69]; [Matryoshka representation learning][MRL].

### 94. Exchange-witness quiet defenses (S38)

**Hypothesis · Parked #63 · Cost: medium.**

Promote quiet moves that invalidate one concrete profitable exchange.

- **First gate:** Repair SEE semantics; run game-group coverage and matched threat/geometry controls.
- **Failure mode:** Selector may be sparse, pin-blind or expensive.
- **Evidence:** [ChessSI PR #63][PR63].

### 95. Sibling-refutation retry (S39)

**Hypothesis · Parked #56 · Cost: medium.**

Retry a reduced fail-low when a repeated sibling refutation actually fails against it.

- **First gate:** Coverage first, then matched-budget random/margin/reply-change controls.
- **Failure mode:** The trigger may be rare or duplicate simpler signals.
- **Evidence:** [ChessSI PR #56][PR56].

### 96. Branched self-play prefix targets (L36)

**Hypothesis · Backlog · Cost: high.**

Fork own games and average continuation outcomes for the shared prefix.

- **First gate:** Require outcome divergence; compare averaged and unaveraged targets from the identical branched games.
- **Failure mode:** Expensive correlated branches may provide almost no variance reduction.
- **Evidence:** [Existing self-play/data proposals][D].

### 97. Same-game residual covariance loss (L39)

**Hypothesis · Backlog · Cost: medium.**

Reweight common and difference components of paired residuals with fixed coefficients.

- **First gate:** Use actual game IDs; compare paired MSE and degree-matched diagonal controls on identical pairs.
- **Failure mode:** Suppressing shared residuals may remove useful result information.
- **Evidence:** [October 25 research][R25].

### 98. Own-side data against stronger opponents (L40)

**Known · Backlog; owner-approved provenance · Cost: high.**

Add only ChessSI-to-move positions, its own search labels and game outcomes.

- **First gate:** Compare equal-volume self-play additions and own-side opponent-game additions at the same ChessSI search budget.
- **Failure mode:** Opponent-induced distribution changes may harm self-play calibration.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 99. Calibrate prescreen routing (E19)

**Adaptation · Backlog methodology · Cost: medium.**

Use held-out historical evidence to decide which patch classes bypass ultra-short screening.

- **First gate:** Account for missing outcomes and missed winners in prospective validation.
- **Failure mode:** Retrospective selection can make routing look better than it is.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

### 100. Opening-set information study (E20)

**Adaptation · Backlog methodology · Cost: medium.**

Study a preregistered own-evaluation imbalance band as a separate test-design experiment.

- **First gate:** Compare held-out patch decisions and CPU cost; keep standard promotion book unchanged.
- **Failure mode:** A specialized book can reorder patch rankings or inflate effects.
- **Evidence:** [ChessSI measured log and backlog][IDEAS].

## Review record and boundaries

This pass read source, drafts, coordination comments and primary prior art. No engine source, queue entry, training data, network, test settings or shared book was changed. No build, perft, bench, training, datagen, GPU operation or game match was run. The accepted bench signature is recorded as 69980 from the base; it was not rerun for this documentation change.

Snapshot heads: #59 `093b5f85`, #60 `6337590f`, #61 `63285d8a`, #63 `36061f63`, #64 `c1bf5167`, #65 `147629ce`, #66 `c3824bcb`, #67 `f7be5c19`, #68 `de00ee1f`, #69 `636765f4`, #71 `5f758cbc`, #72 `42706988`. Recheck their heads and main before implementation; later edits can invalidate a specific finding. Runtime behavior of unexecuted drafts remains unverified.

## Source index

L30 also appeared in the owner-provided local note `C:/Users/Lupe/CLionProjects/ChessSI/docs/research/research_notes/Novel ideas beyond known gaps/novel-training.md`, read on 2026-10-29. That note is absent from the pinned main tree, so its origin is recorded here without inventing a remote link.

Project links are pinned where a stable reviewed head is available. External branch links describe the primary implementation consulted; later versions can differ. Research references establish precedent, not transferability to this engine.

- **AUDIT:** [Completed rejected-update audit](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/rejected-nnue-2026-10-25/RESULT.md)
- **CAL:** [Temperature scaling paper](https://proceedings.mlr.press/v70/guo17a.html)
- **D:** [Existing self-play/data proposals](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/novel-elo-ideas-2026-10-24/notes/selfplay_data_generation.md)
- **DEEPCHESS:** [DeepChess position comparisons](https://arxiv.org/abs/1711.09667)
- **E69:** [Grok experiment specifications, pinned #69](https://github.com/LupeHiguera/ChessSI/blob/636765f44cf43b13f42347dbc21d4e0c19f49577/docs/research/novel-elo-2026-10-28/SPECS.md)
- **ELR:** [Early-learning regularization paper](https://proceedings.neurips.cc/paper/2020/hash/ea89621bee7c88b2c5be6681c8ef4906-Abstract.html)
- **FCF:** [Minimum Proof Graphs and Fastest-Cut-First Search Heuristics](https://ijcai.org/proceedings/2009/89)
- **FILTER:** [Stockfish training loader configuration](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/data_loader/config.py)
- **G57:** [Previous ten research cards](https://github.com/LupeHiguera/ChessSI/blob/184208679d74ce7bf272df0748bebbc7b79e6dac/docs/research/ten-ideas-2026-10-28/REPORT.md)
- **GCC:** [GCC optimization documentation](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)
- **H:** [Stockfish NNUE architecture and training methods](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md)
- **IDEAS:** [ChessSI measured log and backlog](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/IDEAS.md)
- **KATA:** [KataGo methods](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)
- **M:** [Existing NNUE training proposals](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/novel-elo-ideas-2026-10-24/notes/nnue_training_methods.md)
- **MP17:** [Stockfish 17 move ordering](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp)
- **MRL:** [Matryoshka representation learning](https://arxiv.org/abs/2205.13147)
- **NNUE:** [ChessSI current NNUE implementation](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/nnue.cpp)
- **NONPV:** [Stockfish non-PV data generation](https://github.com/official-stockfish/Stockfish/blob/tools/docs/generate_training_data_nonpv.md)
- **P71:** [King-bucket trainer, pinned #71](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py)
- **POS19:** [Stockfish 19 position and SEE implementation](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/position.cpp)
- **POSITION:** [ChessSI current position implementation](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/position.cpp)
- **PR56:** [ChessSI PR #56](https://github.com/LupeHiguera/ChessSI/pull/56)
- **PR57:** [ChessSI PR #57](https://github.com/LupeHiguera/ChessSI/pull/57)
- **PR59:** [ChessSI PR #59](https://github.com/LupeHiguera/ChessSI/pull/59)
- **PR60:** [ChessSI PR #60](https://github.com/LupeHiguera/ChessSI/pull/60)
- **PR61:** [ChessSI PR #61](https://github.com/LupeHiguera/ChessSI/pull/61)
- **PR63:** [ChessSI PR #63](https://github.com/LupeHiguera/ChessSI/pull/63)
- **PR65:** [ChessSI PR #65](https://github.com/LupeHiguera/ChessSI/pull/65)
- **PR66:** [ChessSI PR #66](https://github.com/LupeHiguera/ChessSI/pull/66)
- **PR67:** [ChessSI PR #67](https://github.com/LupeHiguera/ChessSI/pull/67)
- **PR68:** [ChessSI PR #68](https://github.com/LupeHiguera/ChessSI/pull/68)
- **Q:** [Stockfish NNUE quantization implementation](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/quantize.py)
- **R25:** [October 25 research](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-sprint-2026-10-25/REPORT.md)
- **R26:** [October 26 research](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-sprint-2026-10-26/REPORT.md)
- **R27:** [Training/data follow-up](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-followup-2026-10-27/REPORT.md)
- **REDO:** [Dormant neuron recycling research](https://proceedings.mlr.press/v202/sokar23a.html)
- **REPLAY:** [Experience replay research](https://proceedings.mlr.press/v119/fedus20a.html)
- **RHO:** [Reducible-loss data selection](https://proceedings.mlr.press/v162/mindermann22a.html)
- **SAM:** [Sharpness-aware minimization](https://arxiv.org/abs/2010.01412)
- **SEARCH:** [ChessSI current search implementation](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp)
- **SF10:** [Stockfish 10 search](https://github.com/official-stockfish/Stockfish/blob/sf_10/src/search.cpp)
- **SF17:** [Stockfish 17 search](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp)
- **SF19:** [Stockfish 19 search](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp)
- **SF8:** [Stockfish 8 search and worker diversification](https://github.com/official-stockfish/Stockfish/blob/sf_8/src/search.cpp)
- **SFACC:** [Stockfish accumulator update design](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/nnue/nnue_accumulator.cpp)
- **SFBB:** [Stockfish sliding-attack implementation](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/bitboard.h)
- **SFMEM:** [Stockfish memory allocation](https://github.com/official-stockfish/Stockfish/blob/master/src/memory.cpp)
- **SFNNUE:** [Stockfish affine-transform implementation](https://github.com/official-stockfish/Stockfish/blob/master/src/nnue/layers/affine_transform.h)
- **SFTHREAD:** [Stockfish thread lifecycle](https://github.com/official-stockfish/Stockfish/blob/master/src/thread.cpp)
- **SFTT:** [Stockfish TT implementation](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/tt.cpp)
- **SWA:** [Weight averaging paper](https://arxiv.org/abs/1803.05407)
- **T:** [ChessSI current trainer](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/nnue/train.py)
- **THREAT:** [Viridithas threat-feature experiment](https://github.com/cosmobobak/viridithas/pull/425)
- **TIME:** [Time limits and censored returns](https://proceedings.mlr.press/v80/pardo18a.html)
- **TREE:** [Bootstrapping from search](https://papers.nips.cc/paper_files/paper/2009/hash/389bc7bb1e1c2a5e7e147703232a88f6-Abstract.html)

[AUDIT]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/rejected-nnue-2026-10-25/RESULT.md
[CAL]: https://proceedings.mlr.press/v70/guo17a.html
[D]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/novel-elo-ideas-2026-10-24/notes/selfplay_data_generation.md
[DEEPCHESS]: https://arxiv.org/abs/1711.09667
[E69]: https://github.com/LupeHiguera/ChessSI/blob/636765f44cf43b13f42347dbc21d4e0c19f49577/docs/research/novel-elo-2026-10-28/SPECS.md
[ELR]: https://proceedings.neurips.cc/paper/2020/hash/ea89621bee7c88b2c5be6681c8ef4906-Abstract.html
[FCF]: https://ijcai.org/proceedings/2009/89
[FILTER]: https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/data_loader/config.py
[G57]: https://github.com/LupeHiguera/ChessSI/blob/184208679d74ce7bf272df0748bebbc7b79e6dac/docs/research/ten-ideas-2026-10-28/REPORT.md
[GCC]: https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html
[H]: https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md
[IDEAS]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/IDEAS.md
[KATA]: https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md
[M]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/novel-elo-ideas-2026-10-24/notes/nnue_training_methods.md
[MP17]: https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp
[MRL]: https://arxiv.org/abs/2205.13147
[NNUE]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/nnue.cpp
[NONPV]: https://github.com/official-stockfish/Stockfish/blob/tools/docs/generate_training_data_nonpv.md
[P71]: https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py
[POS19]: https://github.com/official-stockfish/Stockfish/blob/sf_19/src/position.cpp
[POSITION]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/position.cpp
[Q]: https://github.com/official-stockfish/nnue-pytorch/blob/master/model/quantize.py
[R25]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-sprint-2026-10-25/REPORT.md
[R26]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-sprint-2026-10-26/REPORT.md
[R27]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/research/research-followup-2026-10-27/REPORT.md
[REDO]: https://proceedings.mlr.press/v202/sokar23a.html
[REPLAY]: https://proceedings.mlr.press/v119/fedus20a.html
[RHO]: https://proceedings.mlr.press/v162/mindermann22a.html
[SAM]: https://arxiv.org/abs/2010.01412
[SEARCH]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp
[SF10]: https://github.com/official-stockfish/Stockfish/blob/sf_10/src/search.cpp
[SF17]: https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp
[SF19]: https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp
[SF8]: https://github.com/official-stockfish/Stockfish/blob/sf_8/src/search.cpp
[SFACC]: https://github.com/official-stockfish/Stockfish/blob/sf_19/src/nnue/nnue_accumulator.cpp
[SFBB]: https://github.com/official-stockfish/Stockfish/blob/sf_17/src/bitboard.h
[SFMEM]: https://github.com/official-stockfish/Stockfish/blob/master/src/memory.cpp
[SFNNUE]: https://github.com/official-stockfish/Stockfish/blob/master/src/nnue/layers/affine_transform.h
[SFTHREAD]: https://github.com/official-stockfish/Stockfish/blob/master/src/thread.cpp
[SFTT]: https://github.com/official-stockfish/Stockfish/blob/sf_19/src/tt.cpp
[SWA]: https://arxiv.org/abs/1803.05407
[T]: https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/nnue/train.py
[THREAT]: https://github.com/cosmobobak/viridithas/pull/425
[TIME]: https://proceedings.mlr.press/v80/pardo18a.html
[TREE]: https://papers.nips.cc/paper_files/paper/2009/hash/389bc7bb1e1c2a5e7e147703232a88f6-Abstract.html
[PR56]: https://github.com/LupeHiguera/ChessSI/pull/56
[PR57]: https://github.com/LupeHiguera/ChessSI/pull/57
[PR59]: https://github.com/LupeHiguera/ChessSI/pull/59
[PR60]: https://github.com/LupeHiguera/ChessSI/pull/60
[PR61]: https://github.com/LupeHiguera/ChessSI/pull/61
[PR63]: https://github.com/LupeHiguera/ChessSI/pull/63
[PR65]: https://github.com/LupeHiguera/ChessSI/pull/65
[PR66]: https://github.com/LupeHiguera/ChessSI/pull/66
[PR67]: https://github.com/LupeHiguera/ChessSI/pull/67
[PR68]: https://github.com/LupeHiguera/ChessSI/pull/68
