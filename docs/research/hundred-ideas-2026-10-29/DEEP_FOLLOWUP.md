# Deep follow-up: search reuse, bucket optimization and teacher cost

**Research date: 2026-10-29 Phoenix / 2026-10-30 UTC.** Accepted main remains `ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd`. Codex coordinated three Astra ultra source-and-prior-art reviews. This follows the [100-idea portfolio](REPORT.md); it adds mechanism-level findings and experiments rather than another broad list.

The strongest new leads are a decomposition-dependent clipping operation in the bucket trainer, optimizer coupling hidden by identical starting predictions, and two ways to eliminate repeated work in the GPU teacher. The qs-TT result also needs a cleaner interpretation: its patch changes main-search replacement as well as quiescence reuse. These are source findings and derived hypotheses, not explanations established by the match.

## Current evidence and ownership

- The operator reports #59 ended at 15,000 games with **+0.72 +/- 3.17, LLR -0.77, no verdict**. It was not accepted, and #60 was held by the owner's scheduling decision.
- Net14-warm's timed CPU SPRT was started against net12. The inspected thread has no completed verdict. Its generation-9 data, warm initialization, lower learning rate and 16-epoch schedule form one continuation package.
- #74's teacher port reportedly matched the tested CPU play and rescore outputs. On the 5060 Ti, the operator measured 6,173 retained positions/s for main and 4,964 for the port, with 150 seconds per arm. That is meaningful preliminary cost evidence, with no published repeated-run uncertainty.
- #72 now has Claude's behavioral stub review; head `e34130e` treats test/bench failures as candidate verdicts and incomplete matches as infrastructure failures. The earlier request for such validation has received an answer.

[Latest operator status](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6506961218), [net14 recipe and scheduling](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6502787570), [Claude's runner validation](https://github.com/LupeHiguera/ChessSI/pull/72#issuecomment-6502145316).

These observations are attributed to their operators; this pass did not rerun them. Claude owns the GPU teacher port. No queue, claim, affinity, running job, engine source, dataset or network was changed here. The held #60 is a scheduling decision; this research does not override it.

## 1. The qs-TT result combines more than quiescence caching

At #59, the new same-key guard rejects any current-generation, non-exact store when `newDepth + 2 < oldDepth`. It is not restricted to incoming depth zero. Thus a depth-3 main-search upper bound can be rejected behind an existing depth-6 main-search lower bound, whereas accepted main overwrites it. This is a second search policy inside the tested package. [Exact guard](https://github.com/LupeHiguera/ChessSI/blob/093b5f850be780224229ca878202a09004e1c5a7/src/tt.cpp#L18)

| Component | Actual behavior | Distinguishing observation |
| --- | --- | --- |
| Score lookup | Every QS entry probes; only width-one nodes use bound cutoffs | Separate useful cutoffs from wide-window and incompatible-bound hits |
| Capture ordering | A TT move matters only when it appears in the noisy list and survives SEE/legality | Count changes from the original first capture, not all TT-move hits |
| Population | Immediate stand-pat fail-high returns do not store a QS result | Count this cost-only lookup population separately |
| Replacement | New guard affects main-to-main and QS-to-main stores | Count rejected incoming positive-depth stores |
| Cross-move reuse | Older-generation entries can be replaced by shallow QS results | Sample overwritten entries that would later have served a request |
| Main search | Depth-zero bounds cannot cut off positive-depth search, but their moves can order it | Measure changed main-search ordering too |

[Pinned qsearch](https://github.com/LupeHiguera/ChessSI/blob/093b5f850be780224229ca878202a09004e1c5a7/src/search.cpp#L232), [main-search probe](https://github.com/LupeHiguera/ChessSI/blob/093b5f850be780224229ca878202a09004e1c5a7/src/search.cpp#L295). Existing accepted `do_move()` already prefetches the child TT address before accumulator work, so the older reported 26% no-prefetch slowdown is not an established explanation for this run.

Two narrow follow-ups have clearer causal interpretations than another broad retune:

1. **Restrict the new guard to depth-zero writes.** Compare full #59 with the same code except that its added same-key retention applies only when incoming `depth == 0`. First require that blocked main-to-main writes actually occur. A replacement-only arm on main is a separate useful diagnostic. This differs from E09, which protects against exact QS overwrites.
2. **Remove only QS TT-move promotion.** Keep probes, score cutoffs, stores, stored moves and replacement unchanged; pass `MOVE_NONE` to the QS move scorer. First require meaningful TT capture reorderings that survive SEE and legality. This isolates ordering from bounds and still lets stored QS moves order the main search.

These are adaptations of established choices. Ethereal's inspected QS uses cached bounds while giving its noisy picker `NONE_MOVE`; Stockfish 17 separately handles raw static eval and search bounds. Neither establishes a gain for ChessSI. [Ethereal](https://github.com/AndyGrant/Ethereal/blob/master/src/search.c#L732), [Stockfish 17](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp#L1263).

The first instrumentation should aggregate node/window class, compatible bound cutoffs, order-changing legal captures, stand-pat exits, attempted/accepted stores, producer/victim depth and generation, raw evaluations avoided, and main-search cutoffs. Bound the sampled event log. Use uninstrumented alternating complete-search timing for performance conclusions; counter overhead and fewer nodes do not establish strength.

### What is inherited, and what is not a discovered bug

The inspected #59 stop checks precede probing and follow recursive children before storing; ordinary bound classification is consistent with its searched QS tree. Its recursive stand-pat-in-check and absent QS draw check are inherited limitations already represented by S28/S31, not new findings to relabel.

One proposed draw fixture illustrates the inherited gap without relying on NNUE scores: position `4k3/8/2K5/8/8/8/8/R7 w - - 100 1`, a seeded depth-zero exact TT score of 123, and nonroot `search(0,1,0,1)`. The source delegates to QS before draw detection, so the cached value can return; positive-depth search checks the draw first. This fixture was derived, not executed.

QS bounds also contain the current pawn correction, which can change while the board key stays the same. Main-search bounds already have related selective/context dependence; this alone is not proof of a new cache defect. E04's existing raw-evaluation cache is a useful negative control because it reapplies current correction rather than memoizing a corrected search result.

## 2. Bucket clipping can change an already valid folded weight

Write the effective bucket weight as `W_b = S + U_b`. The deployed network depends on the sum. Moving an arbitrary amount from `U_b` into shared `S` leaves the represented function unchanged. Yet #71's `clip()` first clips `S` to [-1.98, 1.98], then clips the newly formed sum. [Pinned implementation](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L432)

| Equivalent initial representation | Initial effective weight | Effective weight after current clipping |
| --- | ---: | ---: |
| S = 2.10, U = -0.20 | 1.90 | 1.78 |
| S = 1.90, U = 0 | 1.90 | 1.90 |

This is a source-provable dependence on an arbitrary decomposition. It is not evidence that this condition occurred often, or caused K8's validation result. A tiny future scalar fixture can verify it before any training.

The minimal proposed correction is to project the **folded** weights into the permitted range, then reconstruct an equivalent shared/residual representation without a further function-changing shared clamp. Instrument shared-boundary hits, folded-boundary hits and effective changes caused solely by the shared clamp. If such events are absent in a bounded continuation, this mechanism cannot explain that continuation's behavior.

Export itself adds `S+U_b` before rounding, so separate rounding of shared and residual parts is **not** the problem. With QA=255, half an integer quantization step is about 0.001961 in these weight units. Movement near that scale deserves exported-network checks; floating-point loss alone can miss threshold crossings. [Export](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L462)

## 3. Identical initial predictions do not imply matched optimization

The bucket residual bank is a full table per bucket, without an explicit residual penalty in the checked objective. `S+U` is a redundant parameterization of full bucket capacity, not a low-rank constraint or a guarantee of small deviations from net12. Shared factors can help sparse-feature learning; this is established NNUE prior art. Starting from an already trained transformer changes the reason to expect that benefit. [Actual parameters](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L383), [Stockfish factorization explanation](https://github.com/official-stockfish/nnue-pytorch/blob/b26145006e54e6461cb4b51944ab05cc4850c580/docs/nnue.md#L745), [regularized shared/task-specific prior art](https://flora.insead.edu/fichiersti_wp/inseadwp2004/2004-11.pdf).

Let `g_b = dL/dW_b` include both perspectives and all active losses, and `G = sum_b g_b`. For ordinary SGD with equal parameter learning rates:

```text
shared update:           delta S   = -eta G
private update:          delta U_b = -eta g_b
folded update:           delta W_b = -eta (G + g_b)
bucket-space metric:     I + 11^T
common / contrast eigenvalues: K+1 / 1
```

The `K+1` comparison is against independent dense-bucket SGD. It is not a claim that K8 learns nine times faster than a flat network. Under balanced gradients `g_b = G/K`, its common SGD step is only `1+1/K` times the tied flat step.

Actual training uses Adam. Let `A_t(h)` be its bias-corrected moment-normalized update for gradient history h. Before clipping, the folded update is:

```text
delta W_b = -eta [ A_t(G) + A_t(g_b) ]
```

If a bucket's gradient history is a fixed positive multiple of the common history and epsilon is negligible, the two normalized directions coincide. The folded step approaches twice a flat Adam step fed the same G history; this does not assert that independently evolving flat and bucket runs keep matching histories. Intermittent or opposing gradients behave differently; there is no universal scalar correction. Dividing a private gradient by K largely cancels inside Adam's moment ratio and therefore does not reliably fix this coupling. This is a mathematical deduction under stated assumptions, not a measurement of the real K8 trajectory. [Checked optimizer](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L664), [Adam paper](https://arxiv.org/abs/1412.6980).

### The identifiable experiment

After making clipping depend on folded weights in both arms, or demonstrating clipping is inactive, compare:

- Trainable S plus trainable U, as in the present parameterization.
- S frozen at net12 with every U trainable, identical initial folded tables, output and auxiliary tensors, optimizer restart, row order and schedule.

Freezing S preserves the same representable set of bucket tables: unrestricted U can still realize any W. It removes the shared optimizer path. In real arithmetic, with matched folded clipping and optimizer state, the frozen-S arm is equivalent to training a dense bucket bank. Without the clipping control, this comparison changes both optimizer coupling and decomposition-dependent clipping, so it cannot isolate either.

First verify aligned/opposing/zero/intermittent synthetic gradient cases and frozen-S versus dense one-step equivalence. Only then consider a short, fixed own-data screen with per-bucket exposure, common/contrast update norms, and exported held-out loss. Keep a matched warm flat arm for the practical architecture comparison.

Simply recentering `S += mean(U); U -= mean(U)` does not remove the duplicated common Adam update. A later distinct optimizer experiment can use `W_b = S + V_b - mean(V)`: private gradients become `g_b-G/K`, and the forward centering removes the mean private update after Adam. Starting from zero private optimizer moments, identical bucket gradient histories produce no private contrast update. This is an additional controlled optimization proposal, not a demonstrated strength improvement.

## 4. The GPU teacher has an explicit quality-versus-throughput tradeoff

The reported record-rate ratio is `4964/6173 = 0.80415`. At those rates, the port produces 19.59% fewer retained records in the same generation time, or takes 24.36% longer for the same count. It does **not** follow that it needs 24.36% more Elo or a particular percentage improvement in labels. Learning curves, correlation and training cost are unknown. [Operator throughput report](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6506961218)

The metric is retained training records, not all searched positions. The generator filters checked positions, noisy chosen moves and mate scores. Around 6,966 old / 7,031 port nodes per retained record is compatible with a 5,000-node search setting; it is not evidence that every search used 7,000 nodes. Track searched plies, emitted records, unique rows, completed games and nodes separately. [Filter](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L1197), [reporting](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.py#L260)

The source suggests SEE and correction work as plausible costs. Ordering now calls SEE for different lane-local captures, which can diverge; main-search SEE can repeat work on a warp-uniform move. Correction adds hashing and dependent reads, with synchronized updates. TT entries remain 16 bytes; the extra per-game correction storage is 64 KiB plus 16 bytes, about 96.02 MiB at capacity 1,536. Allocation size alone does not prove a bandwidth bottleneck. Claude reported no new `datagen_step` spills in the sm_120 compile, so spills should not be presented as the leading explanation. [Scoring/correction](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L638), [compile report](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6502462335), [NVIDIA guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#occupancy)

Existing profiling labels matter: ordering SEE belongs to `P_SCORE`, while `P_SEE` covers the search calls. Correction lookup/hash costs fall under `P_EVAL`; correction updates are outside those timers. Summed warp cycles are not directly wall-time percentages. A report showing a small `P_SEE` share would not rule out substantial ordering SEE cost. [Instrumentation](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L54)

### Two additional exact-behavior speed candidates

**Reuse a successful SEE certificate.** For the same parent position, `SEE >= 0` implies `SEE >= t` for any nonpositive t. At this pinned head, normal non-TT captures that passed the ordering test occupy scores from 20,000 up to but excluding the TT score 32,000. `pick_move` swaps scores with moves, and the selected score remains at `scores[f.i-1]`. A conservative proposal uses that certificate only for normal captures with a nonpositive actual pruning threshold, leaving TT moves, specials and unknown cases on the existing path. No new flag array is needed in this version. [Score bands and swaps](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L638), [consumer](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L887)

Require exact parent-state restoration and freeze the band contract in a semantic fixture. Count avoided exchange walks, not merely skipped calls: many SEE calls exit cheaply, and the extra score read/branch might cost more than it saves. If viable, compare full move/score/node parity and uninstrumented throughput. This removes redundant computation; it changes no proposed chess heuristic.

**Reuse the pawn-correction index, not its value.** Preserve the exact index while both colored pawn bitboards are unchanged. Pawn moves, pawn captures and promotions invalidate it; null moves do not. Undo must restore the matching index. Descendants can update the correction table, so caching its value would be wrong. Extra state/register traffic may exceed saved hashing; measure first. [Index computation](https://github.com/LupeHiguera/ChessSI/blob/340e420bfa26c8af11977779dafdcba384ebc304/gpu/datagen.cu#L668)

These two concrete execution mechanisms were not separately present in the 100 cards. They have straightforward prior-art roots in memoization and redundant-work elimination; no worldwide novelty is claimed. Claude retains implementation ownership of the teacher port.

### A teacher comparison that can answer the resource question

First use identical frozen own-game rows and result labels, changing only old-versus-ported search targets. Match student initialization, auxiliaries, presentations and export checks. This asks whether label source helps on fixed positions. Then compare complete equal-budget cycles:

| Arm | Purpose |
| --- | --- |
| Old teacher at 5k, more records | Equal-generation-time baseline |
| Port at 5k, fewer records | Whether search quality offsets lower volume |
| Port near 4k, calibrated throughput | Whether stronger search permits a smaller budget |
| Cheap coverage plus a budgeted deeper subset | Existing mixed-fidelity hypothesis, with selector and relabel cost charged |

The NPS ratio suggests roughly 4,058 nodes only as an initial approximation for the third arm. Polling is quantized at 1,024 nodes, and filtering/tree behavior changes, so choose the budget from a separate calibration set. Count all generation, deduplication, storage and training cost when judging full-cycle value. Mixed depth needs random-deep controls and is a refinement of existing ideas, not a new label-mining discovery.

Before extrapolating the 20% figure, inspect exact timing revisions/settings and run a small authorized alternating timing window with one warmup policy. The public note gives two measurements, not a confidence interval. Do not transfer the percentage automatically to the 5080. Reported parity is useful implementation evidence under tested conditions, not proof of better teaching: correlated game lines and symmetric selfmatches do not cover every state/reset/pause boundary. [Parity report](https://github.com/LupeHiguera/ChessSI/pull/74#issuecomment-6502791125)

## 5. Keep evaluation diagnostics out of the training intervention

Net14 versus net12 can establish whether the whole continuation package plays better. It cannot isolate warm initialization from new gen9 data, learning rate and training duration. The minimum causal follow-up is fresh versus net12-initialized flat H256 on one frozen gen9 manifest at the same declared schedule, optimizer restart, auxiliary initialization and row order. A later 2x2 initialization-by-learning-rate design separates schedule interaction. Reuse net14 as an arm only if its exact code, manifest and stochastic setup are recoverable.

A concrete trap in the checked trainer: `--teacher net12.nnue` prints net12's validation loss, **and also enables a training-only teacher head**. Its default `teacher_weight=1` contributes a new gradient to the backbone. Adding the flag solely to obtain a comparison number changes subsequent training. Use evaluation-only scoring on identical rows and targets instead. There is no evidence here that net14 actually used this flag. [Main trainer flag definition](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/nnue/train.py#L442), [#71 teacher loss and backward pass](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L659)

## 6. A more speculative search-learning experiment

**Refit the output head against verified pruning mistakes.** This combines existing L01 output refitting and S40 shadow audits, with a new decision-specific objective. The general principle of training for downstream decisions is established; the proposed RFP use is a ChessSI-specific hypothesis whose global novelty is unverified. [Decision-focused learning prior art](https://arxiv.org/abs/2112.03609)

At an otherwise eligible current-main RFP node, away from score clamping, the condition is `raw_eval + correction - 77*depth >= beta`. Record the actual integer correction and define `t = beta + 77*depth - correction`. For an audited event that actually returned staticEval after has_legal_move() succeeded, and whose controlled higher-budget own searches stay below beta, add a one-sided penalty alongside the unchanged blended target loss. Exclude the distinct stalemate-return branch. The proposed penalty is:

```text
penalty = weight * max(0, raw_eval_theta - t + 1)^2
```

The one-centipawn margin expresses the deployed integer boundary: avoiding this cutoff requires raw eval <= t-1. Convert the learned output into deployed score units and check exported networks. The transformer stays frozen, so inference architecture and work need not increase. [Actual RFP predicate](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp#L307)

Do not label every reference fail-high as a mandatory pruning opportunity. RFP is a sufficient heuristic, not a requirement to prune all winning nodes. An event label means that a particular decision looked unsafe under a recorded context; it is not the board's true evaluation.

The audit must bypass the audited node's TT cutoff as well as its RFP test, with explicit private-TT state and depth/window/ply/null/correction history. Otherwise the supposed independent reference may just return the same cached answer. Stability across additional budgets and controlled contexts is useful; repeating one deterministic search is not independent corroboration. Selective own search remains fallible.

Use one frozen event set for all controls, keep board/game families in one split, and cap repeated-board weight. The same board can carry conflicting thresholds in different contexts. Compare ordinary refitting, hard-example MSE on the same events, and simple calibration or an RFP-margin adjustment matched for overall pruning rate. The MSE arm needs valid point targets: use available original point targets or separately resolved wider-window own-search scores, charging that extra labeling cost equally. Do not treat a shadow fail-low upper bound as an exact point score. A new head must beat those simpler explanations, including lost useful cutoffs, full search cost and effects outside RFP. Fresh audits under each resulting engine are necessary because node visitation and learned correction change.

Stop if the signal is too sparse, if export removes the effect, or if improvement is explained by simply pruning less. Lower hinge loss or fewer unsafe cuts alone is not success. Only the eventual timed SPRT can establish strength. This is lower priority than the source-provable clipping checks and the inexpensive redundancy audits.

## Recommended research order and limits

1. Validate folded-clipping invariance with scalar fixtures; establish whether it activates on any future bounded training screen.
2. Decompose #59's global replacement and QS move-ordering effects with counters before another match proposal.
3. Pass the exact SEE-reuse opportunity to Claude for consideration within the existing GPU-port ownership.
4. Run matched optimizer or teacher-quality screens only after the czar grants a resource window; keep one changed mechanism per comparison.
5. Park the decision-focused head until its event-coverage and simpler-control gates justify training.

All gates above are proposed future work. This pass used source inspection, primary literature, symbolic reasoning and arithmetic; it ran no engine, training, data scan, compiler, profiler or match. No new Elo gain is claimed. Accepted bench remains 69980 from the unchanged base and was not rerun.

Reviewed heads: #59 `093b5f85`; #71 `5f758cbc`; #72 `e34130e0`; #74 `340e420b`. Recheck current heads before implementation. Preserve own-game/search-only training provenance, the shared read-only book, and the operator's live lane assignments.
