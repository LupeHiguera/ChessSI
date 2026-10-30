# Review of Grok and Cursor research

**Later research:** [Deep follow-up](DEEP_FOLLOWUP.md) incorporates the capped qs-TT result, GPU teacher cost, bucket optimizer analysis and new controlled experiments. The snapshot below records the earlier review.

Reviewed 2026-10-29 against main `ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd`. The associated [ranked backlog](REPORT.md) contains 100 proposed experiments. This review concerns the work posted through Cursor/Grok; commit authorship should remain with the actual proposing and implementing models in the project log.

## Current work and priority

The search drafts among #59 through #68 remain unmerged at the reviewed heads. A later operator note reports ongoing qs-TT games, without a completed acceptance result. The czar's search sequence remains qs-TT, singular extensions, IIR, capture history with its dependency resolved, then plumbing. Exchange-witness search #63 and the broader moonshot note #69 remain parked. [Coordination decision](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6486478219)

The newest draft is [#72](https://github.com/LupeHiguera/ChessSI/pull/72), responding to the previous review's runner failures. [#71](https://github.com/LupeHiguera/ChessSI/pull/71) implements the assigned king-bucket network path. Neither a prepared patch nor a bench signature establishes an Elo gain.

## The runner repair addresses the original failure paths

At #72 head `42706988e8aa04943027925c166dad94fc643e74`, the script explicitly checks test, bench and match statuses, requires match completion, and stops the queue with infrastructure failures still pending. This addresses the original swallowed-error paths in the inspected code. The PR reports shell syntax checks; behavioral stub tests should still demonstrate failure propagation before unattended use. Until it merges, main still contains the old runner.

There is a separate inherited network-test gap. An unsuccessful UCI `EvalFile` load reports an info string while retaining the previous network; process success and a completed match therefore do not prove the requested network played. A malformed candidate can produce a completed fallback-network comparison. Validate file format and the actual loaded network identity before starting a net match, and fail the job if either requested load fails. [Current loader](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/uci.cpp#L128), [network runner](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/scripts/nnue-sprt.sh#L21)

## The bucket architecture needs a matched starting point

The #69 architecture screen compares a fresh H256 control with K8/K16 initialized from trained net12. A win would combine architecture and pretraining. #71 currently rejects `--init` for the unbucketed control, so the matched warm control cannot be requested through that interface. [Screen specification](https://github.com/LupeHiguera/ChessSI/blob/636765f44cf43b13f42347dbc21d4e0c19f49577/docs/research/novel-elo-2026-10-28/SPECS.md#L20), [trainer restriction](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L565)

Use the same dequantized net12 initialization for the base and bucketed arms, the same reset optimizer policy, data order, steps and auxiliary-head weights. The original optimizer and training-only head were not saved in the exported file, so this is a declared continuation protocol, not recovery of the original training state.

A shared seed alone does not fix the auxiliary head: allocating the bucket embedding consumes random numbers before the head is constructed. Zeroing that embedding later does not undo those draws. Copy the common tensors or initialize the head with an independent generator. [Initialization order](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/train.py#L383)

Matching initial predictions also does not isolate representation from optimization: `W0+U` updates a shared table and bucket residuals, changing the effective gradient dynamics. Attribute a result to that complete parameterization unless an additional control separates it.

At the pinned PR description, #71 reported syntax checking for the Torch trainer and no GPU execution. A later operator note reports training runs, but supplies no new CPU/GPU parity evidence. The integer initialization check does not establish training forward/backward correctness or datagen parity. Require nontrivial bucket weights, trainer gradient checks and full CPU/GPU parity before using it as a teacher.

## The incremental bucket test can hide stale accumulators

The distinguished test network places `50 + 5 * bucket` in one unit of every piece feature. With six or more pieces, even the smallest bucket's sum exceeds the 255 clamp. The start-position, castling and en-passant sequences have many more pieces, so their output can remain identical even with an incorrect bucket refresh. The two-king fresh-position sweep is useful but does not validate those incremental paths. [Test weights](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/test_buckets.py#L73), [move-path comparison](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/nnue/test_buckets.py#L177)

Use unsaturated, feature-dependent sentinel weights and inspect both accumulator perspectives against a full refresh. Include king moves across bucket boundaries, undo, castling, captures, en passant and promotion. This is a coverage defect in the test, not proof that the runtime refresh implementation is wrong.

The current bucket definition uses Black's real-board rank while piece features are perspective-relative. That is consistent across the inspected design, not an implementation mismatch. Perspective-relative king-rank sharing is a separate representation experiment; it should not be bundled with horizontal mirroring, whose chess/castling assumptions and previous failed recipe need separate treatment.

## The detached residual head cannot train the exported evaluator

S5 specifies a training-only residual head reading a stopped-gradient accumulator, then drops that head at export. Under that computational graph its loss has zero gradient to the accumulator and main output. Training the head can measure predictability of deep-minus-shallow error, but it cannot improve the deployed evaluator through the proposed auxiliary objective. [S5 specification](https://github.com/LupeHiguera/ChessSI/blob/636765f44cf43b13f42347dbc21d4e0c19f49577/docs/research/novel-elo-2026-10-28/SPECS.md#L97)

Two distinct uses are possible. Keep detachment for a diagnostic of whether hidden features predict search error. For an auxiliary training experiment, allow a bounded gradient into the shared representation and compare it with a direct deep-score auxiliary target at matched gradient scale. Any eventual inference veto is another experiment with its own cost and decision-quality gate. A gradient-connectivity assertion should precede any long training job.

## Disagreement mining needs a random deep-label control

S4 compares disagreement-selected positions labeled at the deeper budget with random positions labeled at 5,000 nodes. That changes selection, label depth and labeling cost together; it cannot identify the value of disagreement mining. [S4 specification](https://github.com/LupeHiguera/ChessSI/blob/636765f44cf43b13f42347dbc21d4e0c19f49577/docs/research/novel-elo-2026-10-28/SPECS.md#L79)

Compare selected-deep against random-deep with the same teacher, node budget, row count and labeling budget. Keep original-row and target weighting identical. Use a separate shallow-versus-deep contrast to estimate the depth effect. Calibration changes between networks can inflate raw disagreement, so stratify or residualize by material/eval before interpreting the selector as uncertainty.

The proposed median shallow/deep score difference is a coverage diagnostic, not a quality guarantee. Rare move-changing cases can matter even when the median is small, and a large difference can be noise. Use held-out root decisions and stronger own-engine analysis as diagnostics, followed by matched training and timed games.

## Exchange witness implementation needs mechanism coverage

#63 follows the broad plan of selecting a threat and promoting a bounded number of quiet defenses. Its separate exchange simulation remains pin-unaware for later recapturers, and its promotion-capture valuation does not include the promotion gain. Later-recapturer pins remain outside both implementations' coverage. The promotion valuation differs from accepted `see_ge`, which treats special moves as even. A test that merely shows an ordering change cannot establish that the intended tactical witness is valid. [Draft implementation](https://github.com/LupeHiguera/ChessSI/blob/36061f63dcfbac527f610a819ac0aed5926dc3f0/src/search.cpp)

The four full quiet probes do not bound all cost: candidate collection and attack-map filtering can scan many more moves. Record total selector work, then run the originally proposed game-group coverage gate and matched-cost threat/geometry controls if the czar promotes it. First fixtures should cover adding a defender, blocking a recapturer, later-participant pins and promotion captures. Keep ordering changes separate from pruning or extensions.

## Later operator observations

Claude's [15:59 UTC log review](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6501709416) reports K8 epoch-20 training/validation losses of 0.00657/0.00691, compared with net12's 0.00672/0.00678 on substantially overlapping but different row sets. This supports concern about this recipe; it does not isolate bucket architecture or establish an Elo loss. The full-rate optimizer restart and additional training remain confounded. Score the frozen exported networks on the same rows, targets and verified unseen game groups, and compare a matched warm flat continuation before another architecture conclusion. K16's epoch-2 result is unfinished.

The same note reports qs-TT at 10,840 games, +3.4 +/- 3.8 Elo and LLR 1.54, still ongoing. It also records Claude's claim of the GPU teacher port and overlapping trainer/search CPU masks. These are attributed operator observations, not measurements repeated by this review; no job was changed. The ranked report incorporates them.

## What this changes in the research plan

Repair controls before comparing architectures; repair gradient connectivity before training residual supervision; and test actual accumulator transitions before trusting bucket parity. These changes improve what an eventual result would establish, without replacing the czar's active queue.

The 100 ranked ideas retain useful existing proposals, distinguish additional adaptations, and place higher-risk hypotheses behind bounded screens. No code, training data, engine tests or matches were changed by this research pass.
