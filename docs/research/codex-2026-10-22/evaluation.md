# Evaluation and training experiments for ChessSI

Author: GPT-6 Codex. Research date: 2026-10-22. Source baseline: `90e172cc010f3ca6121e8f4c975138590729322b`; working-tree changes are separate. Status: hypotheses and experiment specifications, with no measured Elo claims.

The best first research experiment is to test whether cheap search diagnostics can identify positions that benefit from expensive relabeling. This can be falsified before building an NNUE trainer. A small, conventional NNUE is the next useful foundation; larger teachers and uncertainty heads should follow only when their added labels or predictions beat inexpensive controls.

ChessSI currently evaluates positions with PeSTO material and piece-square tables, recomputing the sums over occupied squares. There is no NNUE training pipeline in the inspected baseline. Its existing UCI interface already supplies completed iterative-deepening scores, best moves, depth and cumulative nodes, enough for an initial data-selection experiment. Check-evasion correctness in quiescence must be settled before relying on the engine as a teacher.

## What prior art rules out

- **A GPU network teaching a smaller network is known.** Knowledge distillation transfers predictions from larger models or ensembles into a smaller deployed model. Chess engines also rescore training positions. The interesting question is the quality obtained for the total labeling and training cost, not whether the labels came from a GPU. [Hinton, Vinyals and Dean](https://arxiv.org/abs/1503.02531), [Minic source and training history](https://github.com/tryingsomestuff/Minic).
- **An uncertainty head guiding search is known broadly.** ProbCut models the relationship between shallow and deeper searches. Lc0 has explored policy uncertainty; CrazyAra research studied value-versus-search error prediction. The latter thesis reports deterioration for its tested variance allocation approach and leaves the error-head search experiment untested, so it supplies prior art rather than an effectiveness guarantee. [Jiang and Buro](https://www.cs.ubc.ca/~jiang/papers/mpc_main.pdf), [Lc0 uncertainty proposal](https://github.com/LeelaChessZero/lczero-training/pull/168), [Ruzicka thesis](https://ml-research.github.io/papers/ruzicka2023utilizing.pdf).
- **Filtering, resampling and outcome/evaluation mixing are known.** Stockfish's trainer includes position filtering and piece-count sampling parameters, and blends evaluation and game-result targets. [Loader configuration](https://github.com/official-stockfish/nnue-pytorch/blob/master/data_loader/config.py), [NNUE training explanation](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md?plain=1).
- **Learning relative position order is known.** Ordinal-correlation work explicitly trains chess evaluation around ordering quality. [Gomboc, Marsland and Buro](https://skatgame.net/mburo/ps/ordinal.pdf).

The five cards below are ranked by usefulness to this project. "Candidate distinction" means a precise variation worth investigating; it is not a verified novelty claim. Until the stronger audit and tests are complete, use Known in the benchmark log and describe the candidate distinction separately. Unsuccessful prior work still counts as prior art.

## 1 Allocate deeper labels using cheap search diagnostics

**Hypothesis.** At a fixed relabeling budget, cheap iterative-deepening diagnostics can select positions whose replacement labels reduce error against an independent, more expensive reference better than uniform selection, raw and bounded score volatility, and a context-only selector.

**Prior art and distinction.** Cost-sensitive active learning already treats labeling cost as part of the objective. Minic already rescores data. The candidate distinction is an evaluator-independent selector based on parity-aware search instability, evaluated by the improvement of replacement labels against a third search budget. It explicitly permits deeper replacement labels to be worse. Generic uncertainty divided by cost is not new. [Cost-sensitive active learning](https://burrsettles.com/pub/settles.nips08ws.pdf), [Minic](https://github.com/tryingsomestuff/Minic).

**Minimal prototype.** Use the existing UCI interface and a small ridge regression. No neural network or search modification is required. Predict the magnitude of a cheap-to-moderate search-score change from cheap-search features. Spend the same number of moderate labels under the learned policy, uniform sampling, raw and bounded volatility policies, and a context-only ridge selector. Evaluate all three against a larger independent search budget.

**Data and cost.** The pilot below uses 1,024 positions, two label budgets on all positions and one audit budget on the 256 test positions. Its planned node-cap total is 52,428,800. This is a count of requested search budgets, not a measured runtime or exact node consumption. One process, one assigned CPU, fixed binary/hash and fresh TT for each search are sufficient.

**Failure modes.** Score changes can be noisy, odd/even effects can masquerade as learning value, and selected positions may be tactical cases a small evaluator cannot represent. A better label is not automatically a better training example. Cheap screening and selector training costs can erase savings.

**Cheap falsification.** Reject the pilot if the selected labels do not improve held-out reference error more than all four allocation controls at equal budget, and if it does not beat retaining the cheap labels. If that gate passes, compare identically sized evaluation models trained with the selected versus uniform labels before any match claim. The full protocol follows the cards.

## 2 Establish a small NNUE with a strict inference contract

**Hypothesis.** A small quantized network trained on searched positions can improve this baseline's evaluation enough to offset inference cost.

**Status and prior art.** Known. NNUE, sparse accumulators, quantized inference and evaluation/result losses are established. Bullet and Stockfish's trainer provide original implementations and explanations. [Bullet](https://github.com/jw1912/bullet), [Stockfish NNUE explanation](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md?plain=1).

**Minimal prototype.** Start with a shared 768-input piece-square feature transformer of width 128, calculated from both color perspectives, then a 256-to-1 output. Fix the feature transform, activation bounds, scaling, rounding and overflow behavior in a versioned format. This is a proposed starting size, not an architecture claim. Do not introduce king buckets, additional heads and an expanded network in the same experiment.

**Data and cost.** First use a small pilot such as 100,000 sampled quiet positions to verify parsing, training, export and inference. Preserve searched score, score type, side to move, outcome, source engine and search budget. A self-generated dataset measures an independent bootstrap; an external-engine teacher measures knowledge transfer and must be labeled accordingly. The proposed transformer has 98,304 input weights before biases and output weights; actual training memory, throughput and sufficient data volume must be measured.

**Failure modes.** Wrong perspective, feature indexing or quantization can silently ruin an apparently converged model. Correlated game positions leak across splits. Training on this baseline's mistakes can preserve them. Better validation loss can coexist with weaker play or slower search.

**Cheap falsification and test.** Require exact agreement between a quantized reference evaluator and C++ inference on legal moves, undo, castling, en passant, promotions and king moves. Compare incremental and full accumulator recomputation. Then run correctness, bench and same-core timing checks, and the standard [0,5] SPRT against the accepted engine. Record changed bench nodes; a different evaluator is expected to change search. Do not call pipeline success an Elo result.

## 3 Match training positions to where static evaluation is actually used

**Hypothesis.** A controlled mix of sampled search leaves and played-game positions trains a fixed-size evaluator more efficiently than played positions alone.

**Prior art and distinction.** Known in broad form. Minic documents generation inside the search tree, and dataset aggregation addresses the learner's visited-state distribution in other settings. Quiet-position filtering has also been studied, including a Xiangqi experiment that should not be presented as direct Western-chess evidence. [Minic](https://github.com/tryingsomestuff/Minic), [DAgger](https://arxiv.org/abs/1011.0686), [NNUE dataset study](https://arxiv.org/html/2412.17948v1).

**Minimal prototype.** Freeze one accepted search binary and uniformly reservoir-sample positions at actual non-check static-evaluation calls. Compare a fixed 25% leaf / 75% played-position training mix to a 100% played-position control. Hold total labels, teacher budget, network, seed set, optimizer and training steps constant. The mix is a proposed experiment setting, not an optimized choice.

**Data and cost.** Record source root, game, ply, node role and sampling probability. Sample at most a fixed number of leaves per root so a single expensive search cannot dominate. Relabel sampled positions with a fixed teacher protocol. This adds instrumentation and teacher work but requires no larger network.

**Failure modes.** Captures and transient tactical states may degrade static evaluation learning. Search pruning changes the distribution after deployment. Raw leaf frequency overweights repeated structures; saving every leaf overwhelms storage. DAgger's general guarantees do not establish a chess-engine gain.

**Cheap falsification and test.** Compare loss separately on held-out played roots and held-out evaluation-call positions. Reject a mixture that merely transfers error between the two without improving fixed-node root decisions. A promising model still requires the normal SPRT and a fresh longer-time-control confirmation. Change only the data distribution for this cycle.

## 4 Predict the risk that a proposed cutoff is wrong

**Hypothesis.** A small predictor of one specific event, "this shallow cutoff would fail under the frozen reference search," can allocate conservative pruning margins better than a fixed depth margin or an uncalibrated uncertainty score.

**Prior art and distinction.** ProbCut already uses learned shallow/deep relationships. Value-error heads and uncertainty-guided search also predate this project. The candidate distinction is conditioning on the actual cutoff margin and node context, calibrating false-cut rates on untouched positions, and testing only one pruning decision at a time. [Chess ProbCut](https://www.cs.ubc.ca/~jiang/papers/mpc_main.pdf), [CrazyAra uncertainty research](https://ml-research.github.io/papers/ruzicka2023utilizing.pdf).

**Minimal prototype.** Begin with a binned table or logistic model, not an NNUE head. At nodes where a fixed candidate reverse-futility rule would prune, record depth, static-eval-minus-beta, phase, in-check state, previous score change and TT-bound category. In an instrumented frozen reference build, suppress only that candidate cutoff and search the same node with a fresh reference context. Target the binary result `reference_score < beta`. Use a fixed eligible domain such as non-PV, not in check, shallow depth; leave every other pruning rule unchanged.

**Data and cost.** Proposed pilot: 10,000 shadow candidates with capped extra search work. Every shadow probe must carry a label-valid flag and its cost; aborted probes are unlabeled. Training features contain only information available before the decision. This requires internal instrumentation and a settled search baseline, making it less immediate than card 1.

**Failure modes.** A fail-soft score is a bound, not a regression target. Reduced-depth values are not full-depth labels. Shared TT state can leak the shadow result back into the original decision. Rare false cuts require far more observations than ordinary calibration bins suggest. Good calibration on one frozen policy may break after a pruning or NNUE change.

**Cheap falsification and test.** First replay frozen decisions offline. Compare work saved at the same measured false-cut rate against fixed margins and a depth-only table. No implementation proceeds if it misses obvious tactical safeguards or fails this control. A later C++ implementation tests one pruning gate via SPRT. A calibrated probability is a property of the sampled reference distribution, never a proof that a branch is safe.

## 5 Add sibling ranking while retaining absolute score calibration

**Hypothesis.** A small ranking loss on positions reached by sibling candidate moves can correct move-order mistakes more efficiently than absolute evaluation loss alone.

**Status and prior art.** Known in broad form. Ordinal-correlation research and DeepChess both address relative position quality. A narrowly specified sibling selection and weighting rule could become a candidate distinction, but attaching a pairwise loss is not itself novel. [Ordinal correlation](https://skatgame.net/mburo/ps/ordinal.pdf), [DeepChess](https://arxiv.org/abs/1711.09667).

**Minimal prototype.** Keep architecture, absolute target loss and data fixed. Add a pairwise term only for sibling quiet positions with a reliable teacher gap. Convert both scores to the same player's perspective before forming the pair. Use the same searched budget per candidate move. The existing UCI does not support `searchmoves` or MultiPV, so correct sibling labeling needs a separate adapter that searches child positions with preserved history or an explicitly documented engine extension.

**Data and cost.** Save parent ID, both moves, both child states, teacher score types/bounds and search costs. Construct pairs only within the training split. Count two searched child positions as two labels; apparent pair reuse does not create free independent observations.

**Failure modes.** Small teacher gaps may be unstable; many siblings share a parent and are strongly correlated. Pairwise ranking alone leaves the numerical scale underdetermined, which can break pruning and aspiration margins. The selected teacher move can contain its own search biases.

**Cheap falsification and test.** Require a held-out improvement in sibling ranking with no material degradation in absolute-score error or scale. Then compare fixed-node root decisions and finally the prescribed SPRT. Discard ranking-only training if the scale changes unpredictably; do not tune pruning constants in the same cycle.

## Relabeling pilot without an NNUE prerequisite

### Question and frozen choices

Does spending moderate search on a selected quarter of positions improve the resulting label table more than uniform selection, at the same charged search budget?

Freeze all choices before viewing test labels:

- A single accepted engine source revision, executable SHA-256, compiler/build flags and hash size. Resolve search correctness fixes before freezing it.
- 1,024 valid roots, split by groups into approximately 512 training, 256 calibration and 256 test roots. Whole groups take precedence over exact counts; recompute budgets if counts differ.
- Cheap budget `N0 = 2,048`, replacement budget `N1 = 16,384`, audit budget `N2 = 131,072` nodes. These are proposed initial budgets.
- Score transform `f(s) = 1 / (1 + exp(-s / 400))`. This is a bounded diagnostic transform, not a calibrated win probability for ChessSI.
- Replacement fraction `q = 0.25`. Neither q nor the transform scale is tuned on the test set.
- Ridge regression with training-only standardized features; select one regularization value from `{0.01, 1, 100}` on the calibration split. Include uniform, raw-volatility, bounded-volatility and context-only controls regardless of the fitted result.
- Require at least 20 independent test groups for the screening gate. Report the largest group fraction; 20 groups is a pragmatic minimum for this pilot, not a theorem about bootstrap accuracy.
- Freeze the analysis script SHA-256 and configuration in the collection manifest before any labels. Analysis rejects a changed script. The implementation deterministically replays selection after collection without reading audit values; it does not write selection IDs before N2 collection.

The audit reference is a larger search by the same frozen engine. It is an operational target, not ground-truth chess. A successful result warrants a second held-out dataset and stronger-reference audit before training-policy claims.

### Dataset record

| Field group | Required fields |
| --- | --- |
| Identity | schema version, record ID, source corpus ID/hash, source game ID, sampled ply, paired-game ID if applicable |
| Position and history | initial FEN, full legal UCI move prefix, resulting FEN, side to move, halfmove clock, repetition history representation |
| Leakage grouping | explicit group, optional game/opening IDs, SHA-256 of expanded board plus side to move, connected component, assigned split |
| Teacher identity | source revision/build flags in experiment provenance; executable and analysis-script SHA-256, options, hash MB, Threads=1, recorded CPU affinity and concurrency |
| Search request | budget tier, requested node cap, search order, fresh-TT flag, command transcript |
| Observations | every completed info line: depth, score type, score value, reported bound flags, cumulative nodes, elapsed ms, PV; final bestmove |
| Validity | completed-iteration count, stopped/timeout/error flags, mate/nonmate category, illegal-move flag, validity reason |
| Accounting | charged requested nodes, last-completed reported nodes, wall time, process CPU time if measured, start/end timestamps |
| Features and labels | cheap-only feature vector and missing flags; replacement score; audit score kept inaccessible to training |

A FEN alone does not encode repetition history. Preserve and replay the move prefix; do not silently manufacture a history-free training state from a game position. Standardize the start-FEN and move serialization so equivalent records can be audited. A book containing only FENs may be used as an explicitly history-free root corpus, with an empty move prefix and that assumption recorded; it does not reconstruct the history of an actual game. Keep the 14 benchmark positions out of the training and held-out research samples.

### Splits that prevent leakage

Assign related games, reversed-color opening pairs and opening families together. After initially sampling beyond the common opening prefix, connect records sharing canonical position/transposition identities and assign the whole connected component to one split. Group membership uses position metadata, never scores or outcomes. The implemented key hashes expanded piece placement and side to move with SHA-256. Omitting castling, en-passant and history from this leakage key deliberately merges more states than strict position equality; the replayed search still preserves those fields. This conservative key catches board transpositions but does not detect every near-duplicate. Supplied group, game and opening IDs must cover broader relatedness.

If common positions produce one giant component, narrow the extraction region or purge duplicated/transposed roots before splitting. Do not split the component to obtain convenient sample counts. Reject exact or near duplicate test roots found in training after the split. Reserve a second corpus or independently sampled opening set for confirmation; repeated retuning against the first test set turns it into training data.

### Label collection and bounds

For each root and budget, send `ucinewgame`, then `isready`, and wait for `readyok`. Replay the root's position/history, send the ChessSI-specific `d` command followed by `isready`, and require the returned `Fen:` line to match all six supplied `position_fen` fields before `go nodes N`. Wait for `bestmove` before another position change. `position` alone does not clear this engine's TT.

Use trusted book positions or legally replayed games. Syntax validation does not establish position legality. The supplied final FEN must use ChessSI's canonical pseudo-capturable en-passant field: for a python-chess extraction pipeline this corresponds to `fen(en_passant="xfen")`, or an explicitly normalized corpus. After an ordinary initial e2e4 with no adjacent enemy pawn, ChessSI records `-`, not `e3`. Legal-only en-passant filtering can also differ in pinned-pawn cases. The collector rejects any mismatch rather than ignoring it. Arbitrary UCI engines without the ChessSI `d` diagnostic are unsupported. The external corpus extractor should check `is_valid()` and use legality-checking move parsing; `Board.push()` alone does not check legality. [python-chess FEN and move documentation](https://python-chess.readthedocs.io/en/latest/core.html#chess.Board.fen).

Use the last **completed** root iteration's centipawn score. In the inspected baseline, the root search begins with a full window and an info line is emitted only after the iteration returns without `stopped`. Never use an interrupted iteration's provisional value. Future aspiration-search builds must reject unresolved `lowerbound` or `upperbound` outputs and preserve a completed exact score instead. A completed root score is exact for that search procedure and depth; selective search does not make it game-theoretically exact.

Keep mates as a separate categorical audit. Do not convert mate-in-N to arbitrary centipawns or feed it through the regression. A test root lacking a cheap centipawn score is outside the selection domain, but its screening cost remains charged. Later mate or missing-score results remain in the fixed candidate count and selected quota; exclude them only from explicitly conditional centipawn-loss summaries and bound their unknown utility in the primary comparison. Report exclusions and auditable selections by policy. Promotion, checkmate, stalemate and repetition roots should be represented in protocol validation before sampling the main pilot.

The search checks limits every 1,024 visited nodes. A general node cap can overshoot by up to 1,023 visits before the next check in this implementation; the proposed caps are multiples of 1,024 and ordinarily align with its check. Verify that behavior on the frozen binary rather than assuming it survives later code changes. An early termination can consume fewer than the cap.

The final UCI response currently omits `SearchResult.nodes`; the last completed info line can undercount work from the aborted next iteration. Charge the requested cap for every search and save last-completed nodes as a lower-information measurement. Do not label it exact consumed nodes. A later instrumentation-only extension may emit final nodes, but it should be validated independently and must preserve bench nodes.

### Cheap-only features and learning target

For the cheap search, retain the last three completed iterations and calculate:

1. Absolute score drift between the last two iterations.
2. Absolute same-parity drift between the last and the iteration two depths earlier.
3. Count of best-move switches across those iterations.
4. Last completed depth.
5. Absolute last completed score.
6. Material phase using the baseline's piece phase increments.
7. Missing-history indicators for roots with fewer than three completed iterations.

All features come from `N0` and the input position. No replacement-depth score, replacement runtime, audit best move, game outcome or future iteration may enter the selector.

Train the selector on `y = abs(f(s1) - f(s0))`, where `s0` and `s1` are completed cheap and replacement scores. This target predicts label change, not guaranteed label improvement. The separate audit below tests whether predicted change corresponds to useful correction.

### Controls and audit metric

For each test root with centipawn scores at all tiers, define `L(a,b) = (f(a) - f(b))^2` and realized replacement utility `g = L(s0,s2) - L(s1,s2)`. Negative g means the replacement moved away from the audit reference; preserve it. Because the transformed losses lie in [0,1], an unavailable g can conservatively lie anywhere in [-1,1].

Let M be the number of test roots with a valid cheap centipawn score. Select exactly `k = floor(q * M)` roots under every policy, using only cheap information. The effective fraction is `k/M`. Freeze those index sets within analysis before reading replacement or audit values for the test roots. Never refill or rerank after later exclusions.

Compare these policies:

- Uniform selection: deterministic seeded SHA-256 ordering of root IDs. Also report its analytical expected improvement using the effective fraction k/M.
- Raw volatility: absolute same-parity centipawn drift, falling back to adjacent drift; score-independent hash ties.
- Bounded volatility: the same drift measured after f(s). This prevents a learned model from winning merely by rediscovering score saturation.
- Context-only ridge: depth, absolute score, material phase and missing-history indicators, excluding drift and move-switch features. Fit its regularization separately on the calibration split.
- Full learned ridge: the predeclared cheap feature vector. It must beat all four allocation controls and the retention control for the pilot gate.

Report conditional centipawn mean loss over the common audited CP subset for diagnostics, with policy coverage. The primary comparisons retain the denominator M. For learned versus control, a known root contributes `(I_learn - I_control) * g / M`; for uniform expectation replace I_control with k/M. An unknown root has a worst-case contribution bounded by `abs(I_learn - I_control) / M`. Sum that missing coefficient mass and report the resulting sensitivity interval. Do not treat unknown mate utility as zero or claim that a complete-case result describes all candidates.

Bootstrap whole connected groups, including roots with unknown utility. For each replicate calculate the pessimistic and optimistic endpoint means; report the 2.5th percentile of pessimistic means and the 97.5th percentile of optimistic means. Record the number and largest share of independent groups. This is a screening diagnostic under the frozen corpus, conditional on the fitted selector; it does not quantify retraining variance, new-corpus uncertainty or out-of-distribution calibration. Budget tiers can finish at different depths and parity. Inspect achieved-depth and parity strata in the saved transcripts before claiming generalization; independent confirmation should preserve the direction across those strata. The initial context-only control has depth but no explicit depth-parity term, which remains a limitation.

The retention control selects no replacements and retains every cheap label. It spends only the common cheap-screening budget, so it is a lower-cost reference rather than a cost-matched allocation policy. Its comparison uses I_control=0, including the same worst-case bounds for unknown selected utilities. This prevents a selector from passing merely because it causes less damage than other selectors.

The stage gate requires at least 20 independent candidate groups and positive lower endpoints for both the deterministic missing-utility interval and the sensitivity bootstrap interval against all four allocation controls and the retention control. Otherwise report not passed or inconclusive. Never weaken the gate after viewing results. Passing supplies no Elo claim and does not yet show that a neural evaluator learns better from selected labels.

### Implemented sequence

The standard-library harness is [label_budget.py](../../../scripts/research/label_budget.py). It requires JSONL input containing id, group, startfen and moves; moved roots also require position_fen. Optional game_id and opening_id expand the leakage grouping. It launches one supplied frozen executable, never downloads software, and writes to a new collection directory. Fake-protocol and numerical fixtures are in [test_label_budget.py](../../../tests/test_label_budget.py).

```text
freeze input, engine hash, analysis source hash and configuration
extract legal roots with complete histories and canonical final FENs
build connected leakage groups and deterministic train/calibration/test splits

for tier in [N0, N1]:
    for every root:
        collect this tier with fresh TT and verified replay
for every test root:
    collect audit N2 with the same protocol
finish manifest with all charged budgets and failures

in a separate analyze command:
    require the preregistered analysis source hash
    fit standardization on cheap training features only
    fit full and context-only ridge candidates on training labels
    select regularization on calibration labels only
    form all test selections from cheap features without accessing test N1/N2 values
    then read test replacement/audit values, preserve selections and missing roots
    compare utility, grouped uncertainty and worst-case missing contributions
    apply the predeclared stage gate
```

The source/configuration preregistration is durable; a selector/selection file before N2 is not currently materialized. Test labels are inaccessible to fitting and selection by the frozen analysis code, rather than by physical file separation. Any revision after seeing results requires a new preregistration and fresh confirmation corpus. A source hash is an audit aid, not a tamper-proof ledger.

All N1 test labels are collected to compare policies offline, and all N2 test labels are audit expense. Include these costs even though a deployed policy would purchase only selected replacement labels. The collector verifies the executable hash again at completion, preserves errors and transcripts, and terminates the child on protocol timeout.

### Resource accounting and stopping

With exactly 1,024 roots and 256 test roots, the planned audit caps are:

- Cheap searches: `1,024 * 2,048 = 2,097,152`.
- Replacement searches: `1,024 * 16,384 = 16,777,216`.
- Test audit searches: `256 * 131,072 = 33,554,432`.
- Total: `52,428,800` requested nodes, plus feature extraction and fitting.

For a hypothetical 256-root deployment batch with all roots in the cheap-CP domain and 64 selected, charge `256 * N0 + 64 * N1 = 1,572,864` requested nodes. In general charge **all test roots** times N0, including those excluded after cheap screening, plus k times N1. Charge the same budget to all selection controls; include screening, I/O and selector cost in measured CPU time. Compare deployment savings separately from the one-time pilot's complete audit cost. These figures imply no runtime forecast on the 265K, M2 Max or GPUs.

Run only within the assigned worktree and CPU allocation, after the live match owner releases a slot. Stop on malformed protocol, illegal moves, missing provenance, leakage, unreliable score types or repeated timeouts. Do not launch GPU training merely to occupy hardware; this pilot's purpose is to decide whether that later work is justified.

## Directions to postpone or reject

- **A larger teacher trained on the same data as the student.** It may generalize or smooth labels better, but adds no independent evidence by itself. First compare its predictions with a frozen stronger-search audit and count teacher training, inference and student training costs. Then compare against directly buying more CPU search labels. Lc0-to-NNUE data conversion is also established. [Lc0 data export](https://lczero.org/blog/2021/04/joking-ftw-seriously/).
- **Outcome entropy as pruning risk.** A balanced position can be difficult to forecast as a game outcome while its current score is stable; a forced-looking result can conceal a tactical error. Define the exact error event before choosing an uncertainty target.
- **Uncertainty heads everywhere.** The first deployment should affect one gate. Changing pruning, extensions, time use and training selection simultaneously makes the result uninterpretable.
- **Novel architecture plus novel data plus novel search.** Keep these separate. Otherwise an improvement supplies no evidence for the proposed mechanism.
- **A one-run loss improvement as proof of stronger play.** Use grouped held-out metrics for screening, multiple fixed training seeds for a training-method claim, then the repository's matched SPRT protocol. Record failed and inconclusive attempts.
- **A label selector as an AGI conclusion.** A successful, independently repeated selector would show a concrete research contribution under the recorded assistance and resource budget. The result should carry that precise claim.

## Research record to preserve

Save the proposal before labels are viewed; source URLs and exact source revisions where available; model identity; human hints; dataset and executable hashes; complete commands and raw transcripts; all settings tried; elapsed CPU/GPU time; exclusions; grouped metrics; negative results; and subsequent match results. Keep infrastructure validation, offline diagnostic success and confirmed Elo results in separate fields. None of the above cards has passed an experiment yet.




## Follow up on 21 October 2026 about signed utility and sparse audits

**Proposed follow-up only.** The magnitude-based screen uses the explicit version-2 retention-control amendment below. Its selector and collection budgets remain unchanged; its acceptance gate is stricter. The next experiment should test whether predicting beneficial label replacement works better than predicting label change. It requires a separate preregistration and fresh test groups.

### Why a large label change can be harmful

Let a=f(s0), b=f(s1), c=f(s2), and delta=b-a. The existing audit utility has the exact identity:

```text
g = (a-c)^2 - (b-c)^2
  = 2 * delta * (c-a) - delta^2
```

The magnitude target abs(delta) removes the direction of improvement and its relationship to the later reference. For example, a=0.5, b=0.9, c=0.5 gives abs(delta)=0.4 and g=-0.16. A second root with a=0.5, b=0.6, c=0.65 gives abs(delta)=0.1 and g=+0.02. A perfect magnitude predictor ranks the harmful replacement first.

The failure can be systematic. Conditional on cheap features x, if the change delta has zero expected alignment with c-a, expected utility is minus E[delta^2|x]. Ranking the most unstable roots then concentrates negative utility. Conversely, if c=b, utility is delta^2 and large changes are useful. The magnitude alone cannot distinguish these cases. Alternating search scores, a temporary tactical horizon, and selective-search instability are plausible sources of reversals; their frequency in ChessSI remains an empirical question.

Train a separate predictor u(x) of the **signed** g on a randomized set of roots with all three budgets. Keep negative targets. With the same replacement cost for every root, selecting the k largest conditional expected utilities maximizes expected total replacement utility among policies using x. This is an objective alignment argument, not a guarantee that a small ridge model estimates those expectations well. For the first comparison retain the fixed k quota. A policy that refuses all predicted negative replacements changes the budget and needs its own experiment.

Even perfectly predicted g measures closeness to this frozen N2 reference. It does not establish closeness to perfect chess, improvement of a trained NNUE, or playing strength.

### Prior art narrows the possible contribution

| Primary source | What already exists | Remaining distinction to test |
| --- | --- | --- |
| [Roy and McCallum, 2001](https://groups.csail.mit.edu/rrg/papers/icml01.pdf) | Active query selection based on expected future error reduction. | Here the immediate decision replaces an existing search label, with signed change in reference loss; it does not directly estimate a student's generalization improvement. |
| [Yang and Carbonell, 2009](https://www.cs.cmu.edu/~jgc/publication/PublicationPDF/Cost_Complexity_Of_Proactive_Learning_Via_A_Reduction_To_Realizable_Active_Learning.pdf) | Proactive learning selects instances and oracles with different costs and reliability. Its introduction explicitly uses chess look-ahead depth versus computational cost as an example. | A chess application of choosing expensive labels is already anticipated. Only a specific mechanism and measured result could add something. The paper's bounded-noise classification assumptions do not automatically hold for deterministic chess search scores. |
| [Li, Wang, Kirby and Zhe, 2022](https://proceedings.mlr.press/v151/li22b.html) | Deep multi-fidelity active learning jointly selects inputs and fidelity using information gained per cost. | A tiny model fitted to completed chess-search transcripts would be a simpler domain-specific method, not a new multi-fidelity learning principle. |
| [Jiang and Buro, First Experimental Results of ProbCut Applied to Chess](https://www.cs.ubc.ca/~jiang/papers/mpc_main.pdf) | Shallow/deep score regressions vary by phase and depth pair. Their MPC implementation uses (2,6), (3,7), (4,8), (3,9), and (4,10). | These are already same-parity pairs. The paper uses them for pruning, not the proposed replacement utility. Inferring that all parity-aware shallow/deep prediction is new would be incorrect. |
| [Minic original README](https://raw.githubusercontent.com/tryingsomestuff/Minic/master/README.md) | NNUE data generation includes search-tree, self-play, multi-PV and random approaches; some Lc0 data are rescored with an earlier Minic version. | Rescoring data with a teacher is established. The inspected material does not establish the exact signed-utility selector proposed here. |
| [Angelopoulos and colleagues, Prediction-Powered Inference, 2023](https://arxiv.org/abs/2301.09633) | Predictions can be combined with a smaller trusted labeled sample to correct inference. | A model-assisted sparse audit belongs to established statistical methodology. Its guarantees must match the actual sampling design. |

The bounded search found no exact match for this complete target, feature set and sparse-audit protocol. That is insufficient evidence of novelty. The most defensible classification is **a domain-specific combination of known methods, with an unvalidated narrow hypothesis**. The same-parity feature earns a distinct mechanism claim only if a predeclared ablation supports it.

### Next experiment

Use a new corpus and the same verified history, FEN, grouping and completed-score rules as the frozen pilot. Keep N0=2,048, N1=16,384 and N2=131,072 requested nodes. Before reading search labels, allocate disjoint connected groups to 256 training anchors, 128 calibration anchors and a 2,048-root test pool. Counts are planning targets subordinate to preserving groups. Select anchors independently of volatility and predicted utility, record their sampling rule, and do not replace later mate or missing-score anchors.

1. Collect N0 on all roots and N1/N2 on the 384 anchors. Fit only anchors with all required centipawn scores; record exclusions and all charged caps. Require at least 128 complete training anchors, 64 complete calibration anchors, and at least 20 connected groups in each usable split; otherwise this design is inconclusive.
2. Fit full signed-utility and magnitude models on exactly the same complete training anchors. Give both the same features, standardization, ridge candidates {0.01, 1, 100} and calibration split. Use the initial cheap feature vector, plus explicit completed-depth parity and bounded adjacent/same-parity drift. Pick each model's regularization using calibration mean squared error against its own declared target. No hyperparameter is chosen from test utility.
3. Fit a signed context-only model using depth, parity, absolute score, phase and missing-history flags. Fit a signed parity ablation that removes same-parity drift and the explicit parity bit, retaining adjacent drift and other features. This separates the target change from the claimed parity contribution.
4. For the M test roots with cheap CP scores, compute k=floor(0.25*M). Freeze exactly k selected IDs for each fitted policy and for the bounded-volatility control. Freeze the analytical uniform comparator q_effective=k/M. Write model coefficients, hashes, configurations, all selections and the candidate denominator to a durable artifact **before** collecting any test N1/N2.
5. Independently sample B=min(256,M) candidate roots uniformly without replacement for the test audit, using a recorded fresh random seed and an explicit sampling algorithm. Each candidate has known inclusion probability pi=B/M. Save the audit IDs and probabilities before searching them. Collect N1 and N2 only for these audit roots. Selections stay unchanged after mate results or other exclusions.
6. Compare full signed utility with six controls: full magnitude, bounded volatility, signed context-only, signed parity ablation, expected uniform selection, and retention of the cheap labels. The retention control has an empty selection and lower cost; it checks that the selected work has positive value at all. Report individual utility signs, pairwise means, sampling uncertainty, missing-utility sensitivity, achieved depths/parity, coverage and complete cap costs. Raw CP volatility may remain a descriptive diagnostic.

The magnitude model receives the same N2-annotated anchors in this mechanistic comparison, although it does not need N2 to fit. That isolates the target change. A subsequent cost comparison must let the cheaper magnitude method spend the saved labeling budget elsewhere; equal input data alone does not establish economic superiority.

A protocol error, invalid replay or timeout stops collection and preserves the failure record. A legitimate completed mate result is a different score type, not a protocol error. It stays in the frozen quota and uncertainty accounting.

### Estimating utility from a random audit

For a comparison with a deterministic control, define c_i=I_signed(i)-I_control(i). Against expected uniform selection, use c_i=I_signed(i)-k/M. The finite-pool contrast is theta=(1/M)*sum_i c_i*g_i. For audit sample A with known inclusion probabilities, the Horvitz-Thompson estimate is:

```text
theta_hat = (1/M) * sum_{i in A} c_i*g_i/pi_i

# Under the proposed simple random sample:
theta_hat = mean_{i in A}(c_i*g_i)
estimated_variance = (1-B/M) * sample_variance(c_i*g_i) / B
```

The variance expression concerns audit randomization over this fixed pool. Chess positions need not be statistically independent for that finite-population design argument: their values are held fixed while the audited indices are randomized. It supplies no guarantee about a new population of games or retraining the selector. Keep the group-disjoint design and report group concentration; confirmation on fresh games remains necessary.

For later mates or unavailable g, define per-root endpoints. An available root has z_lower=z_upper=c_i*g_i. An unavailable root has z_lower=-abs(c_i), z_upper=+abs(c_i), retaining the same sampled weight and denominator. Estimate the population mean of each endpoint with the same sampling design. Do not set unavailable utilities to zero or bootstrap only complete CP roots. The two endpoint means bound the contrast under arbitrary g in [-1,1], while audit uncertainty remains an additional source of uncertainty.

Predeclare a one-sided familywise level of 0.05 across the six contrasts. A normal approximation using the design variance and a Bonferroni critical value is only an approximate screening interval; report it explicitly as such. Report the sampled nonzero-coefficient count for every contrast. Rare large contributions, only a few sampled policy disagreements, small effective sample sizes or a few dominant groups can make this approximation unreliable. A distribution-free finite-pool check is available: for values in [-1,1], a simultaneous one-sided Hoeffding radius sqrt(2*log(6/0.05)/B) is conservative for simple random sampling without replacement. Use the lower-endpoint sample mean minus this radius for a conservative lower bound; use zero sampling radius if the pool is fully audited. At B=256 the general bound is about 0.193, so it will often be too wide to resolve realistic utility differences. Only positive conservative lower bounds against all six controls pass this follow-up's reference-utility gate. Report lack of precision rather than treating an approximate interval as a finite-sample guarantee. This uses Hoeffding's finite-population inequality as stated in [Bardenet and Maillard, 2015, Proposition 1.2](https://arxiv.org/pdf/1309.4029).

Before test audits, use only calibration anchors to forecast the uncertainty needed for a useful effect size and record that forecast. If the available audit budget cannot resolve that scale, the sparse experiment remains a cheap falsification screen. A favorable approximate result can justify a separately preregistered confirmation budget; it cannot be relabeled a confirmed improvement.

A later variance-reduction option is the model-assisted difference estimator:

```text
theta_hat =
    mean_{all candidates}(c_i * u_frozen(x_i))
    + (1/M) * sum_{i in A} c_i * (g_i-u_frozen(x_i)) / pi_i
```

With a predictor frozen independently of the test audit and known positive sampling probabilities, its design expectation is theta. Good predictions may reduce residual variance; bad predictions may increase it. Keep this estimator secondary in the first follow-up and never choose between estimators because one gives a favorable result. This is an application of established model-assisted estimation, not a proposed novel algorithm.

Auditing only disagreements is a separate possible optimization. For two realized fixed policies, roots with identical decisions have c_i=0 and need no utility label for that pairwise contrast. One can sample the disagreement set with known probabilities, multiplying its sample mean by its size divided by M. However, against **expected** uniform selection c_i is generally nonzero throughout the pool. A disagreement-only audit cannot estimate that comparison unless every nonzero-coefficient root retains a positive audit probability. The proposed first follow-up uses uniform auditing of the entire candidate pool to avoid this complication.

### Complete cost and rejection criteria

With the nominal counts and every planned search issued, the requested caps are:

| Work | Requested nodes |
| --- | ---: |
| N0 on 2,432 roots | 4,980,736 |
| N1 on 384 anchors plus 256 test audits | 10,485,760 |
| N2 on the same 640 roots | 83,886,080 |
| Total mechanism experiment | 99,352,576 |

For comparison, N2 alone on all 2,048 test roots costs 268,435,456 requested nodes; all three tiers on all 2,432 roots cost 363,593,728. The sparse design buys fewer reference searches, but is larger than the original 1,024-root pilot and is not claimed to be cheaper than that different experiment. If the selected policy is actually deployed on all test roots, collecting the remaining selected N1 labels adds at most 512*16,384=8,388,608 requested nodes; count audit overlap once.

The 384 anchor N2 searches alone cost 50,331,648 nodes, equivalent to 3,072 N1 labels. Startup cost is therefore substantial compared with this test pool. It must be amortized across later data generation, or the selector must improve quality enough to justify it. Measure elapsed CPU time including feature extraction, fitting and I/O. Requested caps remain budget accounting rather than exact consumed nodes; keep the already documented stopped-iteration and limit-check semantics.

Reject the proposed mechanism for this configuration if signed utility does not improve the predeclared paired audit contrasts over magnitude and bounded volatility, or if selected replacements remain systematically harmful against N2. If signed context-only performs as well, reject the claim that transcript instability adds useful information. If the parity ablation performs as well, reject the parity-specific contribution. A wide interval, excessive missing-utility mass or too few usable groups is inconclusive, not evidence of equality.

A favorable screen must survive independent groups, achieved-depth/parity diagnostics and a later stronger reference before a general label-quality claim. It must also survive a cost-matched baseline that spends the anchor/search budget on ordinary labels. Improvement of student validation loss under fixed data/training budgets and then the repository's SPRT are separate later tests. None is implied by success against the N2 self-teacher.

## Pre-label amendment: require useful replacements

On 2026-10-22 UTC, before any real pilot search labels were collected, a synthetic audit exposed a gap in the initial gate. A fixture with 37 test groups passed all four relative allocation comparisons while every replacement had negative utility against the larger-budget reference. The learned selector chose replacements with smaller damage; that is a valid relative advantage but does not establish that buying those replacements improves the label table. Its conditional mean gain over keeping the cheap labels was approximately `-9.50e-8`, and its original stage status was `passed_screen_only`.

Version 2, protocol `magnitude-selector-v2-retention-control`, adds an empty-selection retention control and requires a positive conservative lower bound against it as well as the original four allocation controls. Both deterministic missing-utility bounds and the existing grouped-bootstrap bound apply. The output reports the retention policy's lower node-cap cost separately. Selection, features, model fitting, group assignments, input corpus, search caps and the four allocation controls are unchanged. The same harmful synthetic fixture is now rejected.

This is an explicit pre-label amendment, not a change justified by a real held-out result. The original source SHA-256 was `a27e03bd05f2f7fb1b383d312600d8875e00dc3184733177ad1f8a11b001fed2`; its bytes and the amendment plan are preserved in `engines/qsearch-validation/label-gate-amendment-01/`. The first diagnostic fixture did not expose the gap because its learned and bounded-volatility selections were identical; it is retained in `label-gate-audit-01/`. The second fixture used an independent PV-switch signal and exposed it; its original manifest, labels and report remain in `label-gate-audit-02/`. Both fixtures are synthetic and ran no chess engines.

The amended analysis uses schema 2 and requires its protocol identifier and matching source hash. Earlier manifests are not silently reinterpreted. A regression test reproduces the old four-control success and requires the new gate to reject it. The held-out-label invariance check now perturbs both replacement and audit results, including a selected mate, and confirms that neither changes fitted models, any selection, or charged policy budgets. This extends the earlier audit-only check. The stronger-reference and subsequent evaluator/playing-strength requirements remain in place; positive reference utility alone is still only an offline screen.

The exact review-branch files passed all 64 research-tool tests on WSL CPU 19. Reanalysis of the same preserved synthetic data confirmed that the fitted models, selections, original four comparisons and charged search totals were identical; only the extra retention comparison changed the gate. The version-2 source SHA-256 is `12bd0bc6ac1cc3ba584f71236ad1671842db34625d563a7206e5f8a6a05ba90b`. Validation details and the new frozen source copy are in `label-gate-amendment-01/validation.json` and `label_budget.v2.py`. The real corpus and active match source/binary hashes were verified unchanged.
