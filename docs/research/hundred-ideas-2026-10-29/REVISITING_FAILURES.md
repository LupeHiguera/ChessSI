# Revisit old results: evidence quality, selective search and reusable supervision

**Snapshot: 2026-10-30 UTC / 2026-10-29 Phoenix.** Accepted main: `ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd`, default net12. Codex coordinated three Astra ultra reviews of search failures, learning failures and search allocation. This extends the [100-idea portfolio](REPORT.md) and [deep follow-up](DEEP_FOLLOWUP.md). Existing ideas retain their attribution; new mechanisms below are hypotheses or adaptations, not claims of worldwide novelty.

The most useful finding is that several old comparisons answered narrower questions than their summaries suggest. There are specific reasons to reconsider auxiliary-loss controls, the treatment of reduced-search failures, improving flags after correction history, and stale labels. Other heavily tested recipes have no convincing changed premise. Retesting everything would consume the same resources needed to investigate better mechanisms.

This pass made no engine changes and ran no build, bench, data scan, training, GPU job or match. No new strength measurement is claimed. Proposed diagnostic budgets are research designs, not scheduled jobs. The czar's queue and Claude's current work remain authoritative.

## Current evidence and a useful integration change

The latest inspected [operator report](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6506961218) still records qs-TT #59 at its 15,000-game cap: **+0.72 +/- 3.17, LLR -0.77, no verdict**. Net14-warm's CPU match was started, but no completed result was posted in the inspected thread. These observations are operator reports, not independently rerun measurements.

New [PR #75](https://github.com/LupeHiguera/ChessSI/pull/75), head `c727e6711ed63e5dfc601c27642373e14e5df7aa`, adds `!excludedMove` to IIR on the singular branch `6337590f81e5e096e0b17cef86f74d1df1c2cd0d`. This implements the requested excluded-search guard. Its proposed comparison uses net14 on both arms and that singular branch as the baseline. Neither dependency is thereby accepted into main. The PR reports compilation and **depth-12 bench 1,491,853**, with no SPRT started; that is not comparable to the default-depth accepted signature **69,980**. This review confirmed the source change, not its runtime behavior.

## What the old results actually establish

Figures below are historical recorded estimates and errors, not new measurements. A stopped or capped match is not an SPRT acceptance or rejection. The [accepted-main experiment ledger](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/docs/IDEAS.md) supplies the results.

| Earlier idea | Evidence | Disposition and necessary change |
| --- | --- | --- |
| Check-aware quiescence | -11.83 +/- 8.36, 4,026 games; measured substantial runtime cost | Reconsider only with a demonstrated whole-search cost improvement or useful equal-time decisions |
| Continuation history | -2.9 +/- 18.1, 600-game pre-screen | Weak evidence; existing persistent-history draft deserves a controlled sequential-game diagnostic |
| Ordinary history decay | +0.7 +/- 2.7, 19,978 games, no decisive gain | Park unchanged recipe |
| History-scaled LMR | +0.4 +/- 2.3, 28,070 games, stopped | Park unchanged recipe; investigate quality of the evidence entering history |
| Improving in LMR | +6.7 +/- 13.9, 940 games, stopped for scheduling | Unresolved; accepted correction history creates a specific interaction worth isolating |
| TT-instability trigger | 47 flags / 117,804 same-key stores; 0.3% of reductions affected | Failed coverage gate, no Elo result; preserve original stop rule |
| H512 deployment | +3.4 +/- 4.8, 8,116 games, stopped; roughly 40% slower | Revisit teacher-to-H256 compression, not automatic wider deployment |
| Earlier self-distillation | No completed SPRT; early validation contamination, later small clean improvement | Old teacher head was discarded; direct exported-output distillation remains a different experiment |
| Policy auxiliary head | Four tested positive weights worsened validation | One repaired common-initialization screen; do not dismiss the consistent harmful trend |
| HL-Gauss auxiliary | -49.3 +/- 14.9, 1,014 games at weight 0.01 | Real negative result; claimed gradient-dominance explanation remains unproved |
| Horizontal mirroring | -18.2 +/- 9.2, 2,370 games | Only reopen after testing consistency of copied finite-search targets |
| Eight piece-count output heads | Later retest -0.5 +/- 2.8, 21,824 games on 537.6M positions | Retire this exact head unless a substantive new mechanism appears |
| Suppressing result gradients into the transformer | B=0.5 with auxiliary: -34.5 +/- 12.4; B=0 substantially worse validation | Retire blanket suppression; no discovered implementation error rescues it |

The singular-extension package is **untested**, not a historical failure. Its [current implementation](https://github.com/LupeHiguera/ChessSI/commit/6337590f81e5e096e0b17cef86f74d1df1c2cd0d) combines single extension and multi-cut and activates at depth eight. An unchanged depth-seven bench cannot establish activation. Separate extension from multi-cut when attributing a result; force exclusion, restoration and interrupted-verification paths in future behavioral checks. QS-TT is not a logical prerequisite for obtaining positive-depth TT bounds, although the owner's scheduling hold still governs this work.

## 1. Repair causal controls before changing auxiliary objectives

The historical trainer at [`2efdfb4`](https://github.com/LupeHiguera/ChessSI/blob/2efdfb4/nnue/train.py#L176) constructs an optional auxiliary `Linear` **before** reinitializing feature-transformer weights with `uniform_`. Allocating the head consumes random draws. Consequently, head and no-head models created with the same seed do not start with the same feature weights. The later [policy-head constructor](https://github.com/LupeHiguera/ChessSI/blob/861619845fc9b97a413675b61d91de7d06f8d642/nnue/train.py#L344) has the same issue.

This does **not** invalidate the measured +53.2 and +34.6 recipe wins, show that initialization caused them, or justify rolling back an accepted network. It means seed equality alone did not isolate the auxiliary loss in the documented original design. The exact trainer artifact used for every later replication was not independently established here. Nor does this CPU initialization observation establish changed CUDA shuffle order: those random streams can be separate.

The useful comparison allocates the same heads in both arms, copies every common starting tensor, and changes only the auxiliary loss weight from zero to the selected positive value. Fix batch order, main/future targets, optimizer settings and presentations. Repeat the paired contrast across at least two initializations before a broad causal claim. First compare gradients and exported unseen-game predictions; any strength claim still requires the normal network match.

For the policy failure, all four positive-weight runs use the same head configuration. Their worsening trend is evidence even though the no-head control was imperfect. Revisit one small weight with corrected controls, then stop if the penalty persists. Its original target was independent from-square and to-square classification of a played move, reconstructed from adjacent retained plies. That is not a legal joint distribution of search-supported alternatives. Changing to joint/search-margin targets would be a separate intervention overlapping existing L23, requiring actual ChessSI search evidence. [Lc0's joint masked policy architecture](https://arxiv.org/html/2409.12272v1#A3) is relevant prior art, not validation of independent-square imitation.

## 2. Weaken penalties only when the negative search evidence is weaker

Accepted [main search](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp#L390) gives earlier quiet moves the same depth-based history malus when a later quiet cuts off. Some earlier moves received only a reduced fail-low probe and no full-depth confirmation. They are penalized as strongly as moves that were searched to the ordinary requested depth.

**Hypothesis:** this teaches history to suppress some useful moves on weak negative evidence. This is not a correctness bug; [Stockfish 17](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp#L1568) also uses depth-based quiet maluses.

A minimal candidate holds cutoff rewards, full-depth maluses and all history consumers fixed. Only an unverified reduced fail-low gets a smaller penalty. With parent depth `d` and reduction `r`, a first heuristic is:

`ordinary penalty = min(d*d, 1239)`

`unverified reduced penalty = min(max(1, d-r)^2, 1239)`

This preserves the current parent-depth convention, adjusted by the reduction. Track the actual requested depth and whether normal confirmation completed. Requested depth is a confidence proxy, not a uniform leaf-depth guarantee. A TT return may carry evidence from a deeper search; audit provenance where available rather than labeling every nominally reduced result equally weak.

**First gate:** randomly sample penalized reduced fail-lows and independently audit a bounded subset. Judge any rescue against the alpha recorded for that move's original probe, with its original board and path/null context and controlled TT/correction/history state captured at that event. A later cutoff's alpha or mutated state asks a different question. Keep capped/incomplete references censored and prevent reference-state leakage. Condition on depth, rank and existing history. Ask whether this subgroup contains useful missed moves beyond those simple variables. The earlier observation that many reduced *fail-highs* were false positives cannot answer this fail-low question.

**Decisive control:** compare targeted weakening with uniformly weaker maluses matched for aggregate penalty magnitude on a preregistered calibration sample. Freeze settings before held-out assessment. Stop if the subgroup has no incremental signal, or if uniform weakening explains the benefit. This differs from existing S22's post-confirmation continuation updates and avoids restarting the near-zero history-LMR recipe unchanged.

## 3. Separate positional improvement from correction-table drift

Historical improving was interrupted, not statistically rejected. Since then, pawn correction history was accepted. The inspected [improving LMP draft](https://github.com/LupeHiguera/ChessSI/commit/cfafdac0e1e4388db53052d88e6b717166a47480) and [stack draft](https://github.com/LupeHiguera/ChessSI/commit/c1bf516759e18f3644e730da08fa7abde60d8ce9) compare corrected evaluations saved at different times.

For the same side to move and identical colored pawns, away from score clamps:

`stored trend = raw_now - raw_ancestor + correction_now - correction_then`

Earlier sibling searches can update the shared correction entry before the current comparison. Thus an improving flag can flip without an equivalent change in the raw positional trend. Assessing both positions under the current shared correction would cancel that correction. This is a direct source-level consequence, not evidence that the drift is harmful: newly learned correction information might help.

The narrow candidate stores raw evaluation and exact pawn identity beside the ancestor observation. For identical pawn states, compare raw evaluations; otherwise retain the existing corrected comparison. Preserve missing/in-check ancestor behavior and explicitly handle score clamps. A hash match alone is not exact pawn equality.

**First gate:** count eligible same-pawn comparisons, drift-only flag flips, and flips that actually change pruning or reduction. Use independent bounded verification to compare held-out predictive value after accounting for depth, move rank and static margin. Stop if flips are scarce or if correction drift predicts better decisions. Current accepted main has no improving rule, so this is an interaction in proposed changes, not a bug already affecting accepted main. [Current correction implementation](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp#L156), [Stockfish's corrected improving comparison](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp#L667).

## 4. Compress useful differences from a wider teacher

Basic H512-to-H256 distillation is already L11. The sharper extension is **local value-difference distillation on legal quiet edges actually visited by ChessSI search**. Align parent and child evaluations to the same player's perspective, then teach the student's difference to match the frozen wider teacher's difference. Retain the ordinary scalar blended objective to anchor absolute values.

This transfers the magnitude of a local value change, not just a preferred-sibling label as in L23. It adds no information absent from the teacher's endpoint predictions; it changes the geometry of the loss. [Sobolev training](https://papers.nips.cc/paper_files/paper/2017/hash/758a06618c69880a6cee5314ee42d52f-Abstract.html) supplies derivative-aware training prior art, while legal discrete edges avoid fractional or illegal board perturbations. [Born-again networks](https://proceedings.mlr.press/v80/furlanello18a.html) supplies related distillation precedent.

**First gate:** train or identify a current-data wider teacher that shows useful held-out endpoint and edge information beyond a matched H256 teacher. Old net10 being wider does not make it superior to net12. The old H512 result was inconclusive and costly, while the old self-distillation `--teacher` added a separate discarded head; neither settles direct exported-output compression.

**Controls:** compare edge loss with point distillation on the exact same endpoint multiset, teacher predictions, endpoint multiplicity, presentations and matched gradient budget. Include an equal-total-cost alternative that spends teacher training/inference resources on ordinary student training or additional own labels. Check calibration and integer export. Stop if the wider advantage is only calibration, fails to transfer, or disappears in the deployed network. All teachers and labels remain ChessSI-derived.

## 5. Distinguish obsolete labels from obsolete positions

The accepted recent-only net12 recipe changed several factors together. Existing L05 already proposes replay-mixture testing. A more informative refinement crosses **satellite cohort** with **main-score refresh**:

| Fixed-size satellite beside an identical recent core | Original main search labels | Rescored with one frozen current ChessSI teacher |
| --- | --- | --- |
| Recent rows | Recent/original | Recent/refreshed |
| Older rows | Old/original | Old/refreshed |

Hold positions and original permitted result/future labels fixed within each refresh pair. Use identical rescore budgets and matched training initialization. Record original outcomes as historical behavior outcomes: score refresh does not refresh the actual played continuation. The cohort factor therefore remains a position/outcome package, not a pure board-geometry intervention.

Old/refreshed beating old/original establishes a score-refresh benefit. Retaining older coverage additionally needs comparison with recent/refreshed and the corresponding original-label arms: interpret the cohort × refresh interaction, not just one favorable pair. No refresh benefit is a reason to park that mechanism, not sweep replay fractions indefinitely. Charge all relabeling work and include an equal-total-resource recent-data alternative. This refines L05/L08 and established replay research; it is not a new general learning algorithm. [Replay capacity and replay-ratio prior art](https://proceedings.mlr.press/v119/fedus20a.html).

## 6. Two failed learning ideas need better diagnoses, not immediate reruns

### HL-Gauss: loss size is not gradient size

The failed [histogram implementation](https://github.com/LupeHiguera/ChessSI/blob/861619845fc9b97a413675b61d91de7d06f8d642/nnue/train.py#L491) learns a smoothed 51-bin target of pure search probability in a discarded auxiliary head, while the exported scalar still learns the search/outcome blend. The reported -49.3 result is strong negative evidence for that recipe.

However, weighted cross-entropy exceeding main MSE does not establish that it dominates the shared representation. At `p = target`, cross-entropy equals positive target entropy while its logit gradient is zero. Shared-layer gradient norms and directions, not scalar loss magnitudes, address the claim.

A bounded diagnostic compares no extra head, an extra scalar head learning the same current search target, and the histogram head. Copy common initialization and preserve main/future losses. On a separate calibration slice, choose and freeze small coefficients matching added shared-layer gradient norms; also report alignment. Advance only if histogram structure helps exported unseen-game predictions beyond the scalar same-target control. [HL-Gauss](https://proceedings.mlr.press/v235/farebrother24a.html) primarily changes value regression into classification; ChessSI's discarded-head failure is a narrower result. [GradNorm](https://proceedings.mlr.press/v80/chen18a.html) is relevant balancing prior art.

### Mirroring: copied labels may not respect finite-search symmetry

[Original experimental augmentation code](https://github.com/LupeHiguera/ChessSI/blob/861619845fc9b97a413675b61d91de7d06f8d642/nnue/train.py#L456) mirrors features but retains original search, outcome and future labels. It uses a conservative castling filter inferred from piece placement because cached rows lack explicit rights. This review did not establish a legality bug.

Legal castling-free symmetry does not make a finite asymmetric evaluator/search policy's score exactly invariant. An outcome sampled under the original policy also is not a newly sampled mirrored-policy outcome. This is a plausible alternative to the existing capacity explanation, not a proven cause of the loss.

First compare isolated own-search evaluations of verified original/mirrored roots, preserving relevant castling, en-passant, halfmove and repetition/history semantics. If asymmetry is material, keep ordinary result-labelled training rows unchanged and add a fixed search-only sample with three arms: original duplicates/fresh original scores; mirrors/copies of those same freshly recomputed original scores; identical mirrors/fresh mirrored scores. Match budgets and presentations. Do not assign original-game outcomes or future targets to unplayed mirrored continuations. Stop unless corrected-label mirroring helps ordinary unmirrored held-out play.

## 7. Higher-upside research: learn which reduced fail-lows deserve one more ply

A more ambitious successor to failed TT instability is a small controller predicting the value of **one extra ply after an unsuccessful reduced search**. The information exists at each eligible event; it does not depend on rare conflicting TT stores.

Start narrowly: nonroot quiet LMR events, reduction at least one, parent depths 4–8. Reuse depth, reduction, move rank, reduced result relative to alpha, subtree cost, history, static margin and correction magnitude. Fit a depth-six decision tree with at most 64 leaves. It can request one additional ply; an alpha crossing follows the normal full-depth/PV escalation. When the original reduction is one ply, the retry already reaches ordinary full depth and must not duplicate that identical confirmation. No additional NNUE evaluation or new board features are needed for this first selector.

The objective is useful root decisions per added cost. A local alpha crossing is only a proxy. Randomly sample eligible events, then fork identical post-reduced state into baseline continuation and the intervention. Preserve board/history, windows, ply/null context, TT, correction/history tables, killers, PV/parent-loop state and remaining budget; keep audit branches isolated so deeper reference work cannot improve the baseline through shared state. Keep bounds as bounds and censor incomplete references. Split by game/root family.

A proposed first pilot ceiling is **2,048 events and 50 million total audit/replay nodes**, including follow-up references. Also account for state-copy and wall-time overhead. This is a proposed coverage pilot, not an authorization or a guaranteed sufficient dataset.

Use a retrospective perfect-choice selector as an **optimistic opportunity screen**, not a formal upper bound on a deployed sequential policy: isolated interventions interact through the TT, root ordering and later decisions. If even favorable sampled choices show little benefit, park the mechanism. If promising, require equal-total-budget root replays and held-out comparison with random retries, alpha-distance, history-only, correction-only and uniformly smaller reductions matched for actual work. Count inert feature/lookup overhead too. A suggested admission gate is below 1% whole-search cost for the inert selector; retry cost and search tails are separate.

Result-dependent depth for mandatory **fail-high** confirmation is already proposed in the Oct26 research and parked #65. It is an existing Known comparator, not a discovery of this pass. This new question concerns rescuing **fail-lows**. [Stockfish mandatory re-search](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp#L1051), [learning to select computations](https://arxiv.org/abs/1711.06892).

Fresh audits under the candidate are essential because its behavior changes the event distribution. Classification accuracy, additional alpha crossings and local oracle success do not establish Elo.

### Conditional alternative: a frozen-accumulator RFP veto

A lower-priority successor to the failed activation-sign hash is a tiny classifier that may veto selected depth-4/5 near-boundary RFP cuts. It keeps the scalar evaluator fixed and never uses the classifier output as a search or TT score. Ordinary search after a veto may return and store a different bound. A 512→8→1 head plus context uses about 4,100 multiply-accumulates and roughly 4 KiB of int8 weights; input extraction, quantization and cache access still cost time.

First establish useful root-level opportunities from independently audited actual static-evaluation RFP cuts, with a legal move established. Exclude the separate stalemate-zero return and preserve every existing RFP eligibility guard. Reference searches must bypass the audited pruning decision and any cached answer that simply reproduces it. Then test whether frozen activations add information beyond margin, depth, material and correction. Freeze the transformer to isolate this experiment from shared-gradient effects.

Required controls: scalar-only classifier, larger fixed RFP margin, random vetoes at matched work, an inert head, and the previous deep-follow-up output-refitting proposal on identical events. Reject the head if scalars explain the signal or conditional inference alone exceeds its proposed 1% whole-search budget. Charge all extra searches caused by false alarms. Stronger own searches remain fallible references.

This overlaps the earlier uncertainty-head idea and is its narrower successor, not an unrelated invention. Conditional evaluator cost has [Stockfish precedent](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/evaluate.cpp#L42). A general neural per-move controller or root portfolio remains premature: [Giraffe](https://arxiv.org/html/1509.01549) already documents the problem of allocation-network overhead near leaves, and differing move choices do not prove complementary errors.

## Preserve useful failures and choose the next information gain

The old check-aware-QS investigation already measured approximately 80% illegal attempted evasions, implemented a conservative evasion filter, and tried quiet-king-first ordering. The filter recovered only about 2.46% runtime in a small shared-load comparison; quiet-king ordering changed whole-bench nodes only 0.408%. These are not undiscovered optimizations. Current pruning changes the entry population, but a generic newer-baseline rerun still lacks a convincing cost premise. If the separate illegal-move accumulator-deferral idea is eventually accepted, it could create a concrete changed-cost premise; it has not done so yet. [Archived QS investigation](https://github.com/LupeHiguera/ChessSI/blob/dd717d73fa3b259170f972eb3e69461a836e32f8/docs/research/codex-2026-10-22/qsearch.md).

The [persistent continuation draft](https://github.com/LupeHiguera/ChessSI/commit/63285d8a185946df92020a813edfaec90c59fe4e) does not require ordinary history decay. Its reset/retain contrast should use sequential game positions with proper game resets, measuring useful retained hits and the cost of halving a roughly 2.4 MB table. “Reset caused the failure” is unproved.

The [original TT-instability stop rule](https://github.com/LupeHiguera/ChessSI/blob/770c662293a6471f7eb294ef6fc3f246de9e8de1/docs/research/codex-2026-10-22/search.md) should survive its sparse result. QS-TT depth-zero traffic does not satisfy its old depth-four trigger. Do not loosen definitions merely to make the trigger activate, or replace disjoint bound intervals with raw fail-soft score differences.

Likewise, more seeds or more data alone do not reopen the twice-tested piece-count output heads. Blanket result-gradient suppression already behaves as intended and has negative evidence. Conditional confidence routing would need a separately evidenced mechanism.

My ranking below is **research information value**, not an Elo forecast or an instruction to reorder the operator queue.

| Priority | Next question | First gate before a full experiment |
| --- | --- | --- |
| 1 | Does auxiliary supervision help under identical initial features? | Common-tensor, allocated-head control; gradients and exported held-out predictions |
| 2 | Are unverified reduced failures over-penalized? | Independent false-low sample; targeted versus magnitude-matched uniform weakening |
| 3 | Does correction drift distort improving decisions? | Drift-only active flips and conditional predictive value |
| 4 | Are older positions useful once search labels are refreshed? | Fixed-core cohort × score-refresh design with full label-cost accounting |
| 5 | Can a wider teacher transfer useful local value differences cheaply? | Current-teacher advantage; identical-endpoint point versus edge control |
| 6 | Can a tiny selector purchase useful fail-low rescues? | Bounded opportunity screen, then same-budget root replay and simple-rule controls |
| 7 | Do accumulator features identify useful RFP vetoes beyond scalars? | Incremental held-out signal and conditional cost before implementing a head |

Policy, histogram and mirroring diagnostics are conditional follow-ups, not three immediate training jobs. Existing continuation and mandatory re-search proposals retain their owners and identities. No proposed gain here is measured or additive. Progress toward a leading engine depends on converting one precise mechanism at a time into reproducible equal-resource strength.

**Validation of this research artifact:** source/history review, primary-source checks and delegated adversarial review. Engine tests were intentionally not run for documentation. Accepted bench **69,980** is inherited from main, not rerun.
