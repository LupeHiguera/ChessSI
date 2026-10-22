# Search research and controlled experiments

Research date: 2026-10-22. Proposer: GPT-6 (Codex). Status: research proposals; no strength result is claimed here.

The best immediate experiment is to keep a completed replacement move when a later root search is interrupted. The strongest research direction is to measure whether another iteration can finish a useful decision before the deadline, then allocate time from that evidence. Both start from a concrete weakness in the inspected engine: Search::think discards the whole interrupted iteration, while the time manager allocates remaining time divided by 25 plus three quarters of the increment.

This report complements the standard killer, history, null-move and late-move-reduction queue. Known means prior art establishes the broad method. Candidate means a specific variation is proposed for investigation; it does not establish novelty. Claims about novelty require additional engine-source and fishtest review after the variation has survived cheap falsification.

## Baseline and prerequisites

The inspected source has PVS, iterative deepening, a full-key single-entry always-replace TT, check extension and capture quiescence. Source in the shared Claude folder was changing during review, so every implementation must be based on a pinned accepted commit in the assigned worktree. The initial shared-folder inspection later reported HEAD 24e50aea386011a3a556206b1ba9c22ea21b654d with a modified search.cpp; that is an observation, not an experiment baseline.

Quiescence check evasions are a prerequisite to meaningful tactical diagnostics and are already claimed by the root agent. Draw and repetition handling also need review before training a controller from search labels: normal search tests for draws, while the inspected qsearch does not. Perft alone cannot validate either issue. Keep correctness changes separate from the ideas below.

Use WSL Ubuntu and the agent's assigned CPUs 14-19, with at most five concurrent games. Compilation also stays within that allocation. No measurements in this report authorize competing tests or modifications in the other agent's folder.

## Ranked shortlist

| Rank | Hypothesis | Kind | Earliest useful baseline | First decision |
| --- | --- | --- | --- | --- |
| 1 | Keep a completed challenger after a later root interruption | Known | Correct qsearch | Deterministic interruption replay |
| 2 | Allocate time from deadline-conditioned decision improvement | Candidate variation | Rank 1 assessed; root tracing available | Held-out improvement per node |
| 3 | Use conflicting TT bounds as a warning against one reduction | Candidate variation | Stable LMR or RFP and correct draw handling | Does the feature predict costly misses? |
| 4 | Use disagreement between reduced and full searches to adjust later siblings | Candidate variation | Accepted LMR with re-search | Conditional predictive value |
| 5 | Retain TT entries by measured work | Known | Depth-and-age replacement as a control | Saved work at equal table bytes |

### 1 Keep a completed challenger after a later root interruption

**Mechanism.** Suppose the last completed depth chose A. At the next depth, A finishes, then B finishes and beats A, then a search of C hits the deadline. The inspected engine returns A. A conservative variant returns B because its own search finished and its improvement over the current-depth A was confirmed.

**Closest prior art.** Stockfish maintains root move results during an iteration, and its search contains rollback for aborted loss searches. Its time controls also use best-move changes, score trends and search effort. These establish prior art for using partial root work and adaptive time; they do not prove this particular small ChessSI variant helps. See [Stockfish search.cpp](https://raw.githubusercontent.com/official-stockfish/Stockfish/master/src/search.cpp).

**Smallest change.** Save an independent completed challenger snapshot. Enable it only when the first legal root move equals the previous completed best move and that move has finished a full-window search. Update it only after a later challenger finishes its required full-window re-search. Adopt it on a subsequent abort. Initially exclude all mate-band scores and keep the existing move order and time limits.

**Instrumentation and ablation.** Count interrupted iterations, eligible interrupted iterations, completed replacements, adopted replacements, and selected-move changes. Compare baseline, conservative replacement, and an intentionally broader diagnostic-only replacement policy to see whether the guard matters. Do not ship the broader policy as part of the same experiment.

**Failure mode.** A deeper but incomplete search can prefer a worse move because deeper heuristic evaluations are imperfect. A scout fail-high is only a bound, and must not be accepted as a confirmed replacement. Losing mate scores from incomplete root coverage are particularly unsafe.

**Cheap falsification.** Replay fixed node deadlines on a position set that was sampled before observing disagreements. Examine changed choices with a deeper, equal-budget reference search for both moves. If the guarded rule never changes a move, or changed choices are consistently worse, stop before a match. Surrogate reference quality screens the idea; only SPRT can establish a playing-strength gain.

A detailed implementation contract follows below.

### 2 Allocate time from deadline-conditioned decision improvement

**Mechanism.** Extra computation is useful only when it changes the eventual decision favorably. An iteration that cannot finish before the hard limit may yield little value under a completed-iteration policy, or may yield a useful completed challenger under idea 1. Predict that joint outcome directly from search traces.

**Closest prior art.** [Kocsis, Uiterwijk and van den Herik, 2001](https://cris.maastrichtuniversity.nl/en/publications/learning-time-allocation-using-neural-networks/) trained time allocation with temporal-difference and genetic methods in Lines of Action. [Hay and Russell, 2011](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2011/EECS-2011-119.pdf) formulate computation choice in terms of the eventual action's utility and computational cost. Learned time allocation and value of computation are therefore Known.

**Specific candidate difference.** Fit a small controller to the *joint* event of finishing a usable root decision within the remaining budget and improving the move, while preserving censored PVS results as bounds. Compare it against a best-move-stability controller and a simple next-iteration cost predictor. The novelty claim would concern this exact feature/target/policy combination, not using a neural network or uncertainty.

**Smallest change.** First add passive root trace events. Fit at most a shallow decision tree or a small table offline; no GPU and no per-node network call are required. In the first live experiment, consult it only after a completed iteration. Preserve the baseline hard limit. Its sole action is whether to start the next iteration or stop.

**Instrumentation and ablation.** Record root-child phase, bound type, nodes, completion, iteration, best-move changes and root elapsed time. Compare a stability-only model, a cost-only model, and the joint model on equal held-out total node budgets. Remove bound-aware features in one ablation. Do not count a move change as a benefit when the reference considers the new move worse.

**Failure mode.** Learned labels may merely reproduce the reference engine's bias. A controller can overfit to one time control, one engine version, or opening family. PVS fail-low values masquerading as exact runner-up scores create fictitious confidence. Overruns are informative censoring: omitting them produces an overoptimistic completion model.

**Cheap falsification.** Replay candidate stop policies on traces of unchanged search. If the joint model cannot improve reference decision quality per node over stability-only and cost-only controls on held-out games, reject it. This avoids paying for matches to test a controller with no diagnostic signal.

### 3 Use conflicting TT bounds as a warning against one reduction

**Mechanism.** Two recent searches of the same position can give nonoverlapping score intervals. The conflict may reveal horizon sensitivity that makes an additional reduction risky. A tiny stored warning could reduce LMR by one ply, or disable RFP once; these are alternative experiments, never a combined patch.

**Closest prior art.** Search instability is longstanding. Bob Hyatt explains how different-depth TT bounds can produce fail-high/fail-low inconsistency in [this original discussion](https://open-chess.org/viewtopic.php?t=2720). Modern Stockfish already adjusts reductions using TT/PV status, histories and local search feedback; see its search source above.

**Specific candidate difference.** Store a two-bit recent-conflict warning for the same full position key, based only on genuinely disjoint finite intervals at comparable depths. It is not an unsigned difference between two fail-soft scores. Its use as one narrowly scoped reduction guard is the candidate variation.

**Smallest change.** Diagnose first. On same-key stores, compare old and new depth, bound and finite score before replacement. For the initial definition require both depths at least four and absolute depth difference at most two. Mark a conflict only if intervals are separated by at least 64 internal centipawns. Treat 64 as a provisional, preregistered threshold, not a tuned constant. A production byte may fit existing TTEntry padding, but verify sizeof and table capacity before assuming zero memory cost.

**Instrumentation and ablation.** Measure frequency and future reduction failures after conflicts, conditioned on depth, move rank, static evaluation margin and TT bound type. Compare with a same-frequency random guard and with ordinary static-evaluation change. Store the entry fields by value before recursion; an entry pointer can be overwritten during the child search.

**Failure mode.** A conflict can be harmless horizon oscillation, graph-history interaction, or window-dependent search. Spending nodes on those cases could lower strength. Uncalibrated differences between depths can dominate the signal. A more complex key that encodes path history would be a different experiment.

**Cheap falsification.** If conflict adds no held-out predictive value beyond depth and bound type, do not implement the policy. If conflicts are too rare for useful measurement, stop rather than widening gates until a signal appears.

### 4 Use reduced versus full-search disagreement to adjust later siblings

**Mechanism.** At one parent, a reduced late-move search can fail high but its full-depth verification can fail low. That pair says the local reduction was overoptimistic. If such disagreements cluster among siblings, reduce later eligible siblings one ply less.

**Closest prior art.** Stockfish uses next-ply cutoff counts and history in reductions, and explicitly adjusts search after earlier reduction decisions; see its search source. [The original ROC analysis of LMR discussion](https://talkchess.com/viewtopic.php?t=47577) analyzes reduced-search decisions against full-search outcomes. The broad ideas of calibrated reductions and local feedback are Known.

**Specific candidate difference.** The feature is a paired contradiction between a particular reduced probe and its full verification at the same alpha, scoped to the current parent. An ordinary cutoff count is not this feature. Whether this distinction already appears in another engine is unresolved.

**Smallest change.** Begin with a per-parent diagnostic count. After the first confirmed reduced/full disagreement at that parent, an eventual trial subtracts one from subsequent quiet-move reductions, clamped to zero. No global history update, no added verification searches and no change to capture handling.

**Instrumentation and ablation.** Log reduced value, alpha, verified value, requested depths, move rank, cost and later sibling outcomes. Compare with a guard triggered by any re-search, and a guard triggered randomly at the same frequency. Group validation by root position because sibling samples are not independent.

**Failure mode.** Verification samples are selected by reduced fail-highs. They say little about the dangerous reduced fail-lows that are never checked. A high false-alarm rate need not imply a high missed-improvement rate. The feature could also be redundant with move order or alpha changes.

**Cheap falsification.** In a diagnostic build only, fully verify a deterministic hash-selected sample of reduced fail-lows using isolated search state. Test whether earlier paired disagreement predicts those misses after controlling for depth and rank. If it predicts only extra re-search cost, reject the proposed safety guard.

### 5 Retain TT entries by measured work

**Mechanism.** Remaining depth is only a proxy for the work an entry can save. A searched-subtree node count may distinguish expensive positions from cheap ones at equal depth.

**Closest prior art.** [Breuker, Uiterwijk and van den Herik, 1994](https://journals.sagepub.com/doi/10.3233/ICG-1994-17402) compare replacement schemes, including subtree-size criteria. Their abstract recommends a two-level scheme using searched subtree nodes for the positions tested. [Stockfish tt.cpp](https://raw.githubusercontent.com/official-stockfish/Stockfish/master/src/tt.cpp) supplies a modern depth/age replacement control.

**Smallest change.** After depth/age replacement has a measured baseline, replace only its value criterion with a coarse logarithm of nodes spent in the completed subtree, retaining age. Do not simultaneously change bucket size, signature width or table capacity.

**Instrumentation and ablation.** Record overwrite depth, age, work category and subsequent reuse in a diagnostic trace. Compare fixed byte budgets and measure both nodes and wall time. Avoid double-counting inherited subtree work from a TT hit unless the chosen policy explicitly calls for that estimate.

**Failure mode.** Expensive entries may never be reused. Counting overhead, altered cache packing and retention of obsolete entries can erase savings. This is useful engineering, not original research.

**Cheap falsification.** Run a trace-based shadow cache only as a screen, then a fixed-depth executable test if promising. Shadow-cache traffic is policy-dependent and cannot predict the final search tree exactly. If it does not beat the depth/age control even in the screen, stop.

## Rejected novelty claims and deferred directions

| Broad claim | Decision | Prior art or reason |
| --- | --- | --- |
| Learn when to stop searching | Known | Kocsis et al. 2001; Hay and Russell 2011 |
| Spend more time when the best move changes | Known | Stockfish's time-control code |
| Store subtree cost in the TT | Known | Breuker et al. 1994 |
| Audit pruning by comparing shallow and deep searches | Known | LMR ROC analysis, 2013 |
| Fit pruning probabilities from move order | Known | [RankCut, Lim and Lee, 2006](https://cdn.aaai.org/AAAI/2006/AAAI06-161.pdf) |
| Measure null-move precision, recall and node cost | Known | [Typhoon author commit 9b28080, 2026-09-25](https://git.acknak.org/cgit/typhoon.git/commit/?id=9b28080f8b3dca4588cb2aaaf748451f45e3c626) |
| Use a tactical refutation's squares to select defensive moves | Broad concept already old | Do not call a new square-mask encoding original without reviewing selective-search literature |
| Add cumulative reduction debt | Deferred | Mechanism is underspecified; close to extension budgets and modern reduction hindsight |

RankCut estimates the chance that a better move remains from offline move-order statistics and uses shallow searches when that chance is low. Typhoon's cited commit measures null-probe and real-search agreement together with node costs. These are direct precedents for cheap calibration; relabeling them as AI uncertainty would not establish novelty.

## Exact contract for the root interruption experiment

### Scope

One behavioral change: final move selection after an interrupted root iteration. Keep move generation, move ordering, qsearch, TT, stop polling and time allocation identical to the pinned baseline. Fixed-depth searches that finish must have identical nodes and results.

Use the accepted qsearch baseline. Keep all root windows full-width for this first experiment; aspiration support is deferred. No root move can enter the fallback snapshot until every required search for that move has returned normally.

### State

Maintain a snapshot of the last fully completed iteration, including best move and score. At the start of each new iteration clear a separate optional abortChoice. Store candidate move and selected-move score by value, and copy its PV if diagnostics require it.

Record whether the first legal root move was the previous completed best. If it was not, disable partial replacement for that entire iteration. This avoids changing move order or comparing an exact challenger against an incumbent known only through a bound.

A score is finite for this prototype when its absolute value is below VALUE_MATE_IN_MAX_PLY. Disable partial replacement if the previous completed score or freshly searched incumbent score is in the mate band. If a later alpha-raising root result enters the mate band, clear any saved abortChoice and disable partial replacement for that iteration.

### Pseudocode

    previous = lastFullyCompletedResult
    eligible = false
    abortChoice = none

    for each legal root move in the existing order:
        alphaBefore = alpha
        run the existing first-move or PVS search
        if necessary, finish the existing full-window re-search
        undo the root move

        if stopped:
            return ABORTED

        if this is the first legal root move:
            eligible = previous.best exists
                       and move == previous.best
                       and originalRootWindow is full-width
                       and this move completed a full-window search
                       and finite(previous.score)
                       and finite(score)

        if score > alphaBefore and not finite(score):
            eligible = false
            abortChoice = none

        run the existing alpha/PV update without changes

        if eligible
           and move != previous.best
           and score > alphaBefore
           and this move completed its required full-window search
           and finite(score):
            abortChoice = copy(move, score, current root PV)

    at the iterative-deepening caller:
        if iteration aborted:
            if abortChoice exists:
                selectedResult.best = abortChoice.move
                selectedResult.score = abortChoice.score
            break
        else:
            commit the ordinary completed result

An aborted return of zero is a control-flow placeholder, never a score. A scout result exceeding alpha is a lower bound until the necessary full-window search finishes. For the first implementation, fail-high mate results from a partial iteration are deliberately left to the existing completed-iteration path.

The candidate score describes that move's finished search. It does not make the incomplete root iteration an exact root result. Do not print an ordinary completed-depth UCI record for it. Either keep the normal completed-iteration info and output the final bestmove, or add a clearly marked diagnostic event.

### Required checks

1. With no interruption, per-position bench moves, scores and nodes equal the baseline; the official aggregate bench stays unchanged.
2. Stop before the first root child completes: return the previous completed best.
3. Stop during a challenger scout or re-search: do not adopt that unfinished move.
4. Stop after a challenger completes and while a later sibling is running: adopt the saved challenger if all guards hold.
5. A later interrupted search cannot overwrite the saved PV or score.
6. If first-root ordering differs from the previous completed best, retain the baseline fallback.
7. Preserve the previous result through all mate-band cases in the prototype.
8. Repeated deterministic node-limit runs produce the same selected move and leave position state intact.

Use deterministic node-limit interruption tests to exercise these cases. Test the actual 1024-node polling behavior; do not silently tighten stop polling in the behavioral patch.

### Cheap screen and statistical decision

Sample positions independently of disagreements, with original game history retained where available. An initial screen can use 64 positions and four node budgets, followed by deeper equal-budget evaluation of changed choices. The size is an engineering budget, not statistical evidence of Elo.

Report how many cases activate each guard and how often selection changes. If activation is negligible, the patch may be too rare to justify a long match. If a bug, illegal move, nondeterministic fixed-node result, or completed-search bench difference appears, stop and repair before any SPRT.

After the screen, use the repository's gainer SPRT [0, 5] against the latest accepted baseline, with the fixed book and assigned concurrency. Preserve a failed result and revert only this change. If accepted, confirm at the longer time control before claiming robustness. Do not combine it with a new time policy to make the result pass.

## Passive instrumentation for deadline research

### Events and ownership

Tracing is a separate diagnostic change. Buffer events in memory and write after the search; per-node formatting or I/O would distort timing. A disabled build should not alter search decisions. Root-child events are sufficient initially.

Each trace records source commit, bench, compiler flags, binary hash, engine options, clock settings, node limit, initial FEN, full played-move history when available, book/game identifier, and assigned CPU/concurrency. Never use a FEN alone as a substitute for known repetition history.

| Event | Required data |
| --- | --- |
| Search start | Root identity, side to move, limits, prior completed result |
| Iteration start | Iteration number, cumulative nodes and elapsed time |
| Root probe start | Move, rank, phase, requested depth, parent-oriented alpha/beta |
| Root probe complete | Returned score, bound kind, nodes spent, elapsed time, normal completion |
| Root decision update | Selected move, selected score, reason, completed or partial provenance |
| Iteration complete | Best move/score, cumulative nodes/time, all-root completion |
| Abort | Reason, nodes/time, unfinished probe phase, available fallback |
| Search end | Final chosen move, completed depth, source of final choice |

Distinguish full first-child search, zero-window scout, reduced scout if introduced, and full re-search. Retain both the initial scout event and its re-search event; they are two computations with different semantics.

### Bound semantics

Express all stored scores and windows from the root player's perspective after negation. A normally completed probe with score less than or equal to its original alpha supplies an upper bound. A score greater than or equal to original beta supplies a lower bound. A score strictly inside the full original window is exact for that search configuration. Exact does not mean game-theoretically solved.

For a lower bound L use interval [L, +infinity); for an upper bound U use (-infinity, U]; for an exact score v use [v, v]. Do not average these bounds as if they were unbiased move values. A PVS scout with integer window [a, a+1] normally supplies only a bound.

An interrupted probe supplies no score label. Record it as unfinished. Requested depth, any root reduction, bound type and whether a full re-search finished must remain separate. Selective search can violate simple cross-depth comparisons, so intervals from different depths are evidence features, not formal proofs about a shared true value.

### Dataset and labels

Split by games and opening families before fitting anything; keep positions and known transpositions from the same source game in one split. Hold out a second time scale as a transfer test. Regenerate or revalidate data after accepted search changes.

From each completed decision checkpoint x, replay continuation to several additional node budgets b. Let A(x, b) be the actual selected move under the chosen fallback rule when b expires. Let U_ref(m) be a deeper equal-budget reference evaluation of move m in the original root history. Use the signed target:

    gain(x, b) = U_ref(A(x, b)) - U_ref(A(x, 0))

Do not clamp negative gains to zero. Record a separate usable-decision-completion indicator, because extra work can finish a replacement even without completing the iteration. Reference comparisons require evaluation of both selected moves under the same protocol; deeper search is a surrogate rather than ground truth.

A completed full trace supports replay of earlier stopping times only if the policy does not alter search order or internal decisions. Replay cannot justify policies that add new probes, reorder moves, or change pruning. It also cannot model how saved clock time changes later moves in a complete game; that requires matches.

### First candidate controller

Fit a small table or shallow tree to expected signed gain conditional on remaining budget and currently observable features. Start with completed depth, recent iteration node ratios, best-move age, recent score changes, root incumbent effort, and the count of already completed challengers. Bound-aware features must be computed without assuming exact runner-up scores.

At an iteration boundary, estimate expected gain from continuing and expected node cost. Continue only when gain exceeds a fixed development-set opportunity-cost threshold times expected cost, subject to the unchanged hard limit. Keep a minimum-search rule and retain the baseline behavior for sparse or unseen feature bins.

Compare against two controls under equal aggregate node budgets: best-move stability alone, and estimated completion cost alone. A multiplication of independently fitted improvement and completion probabilities is only an ablation; those quantities may be correlated. Prefer fitting their joint target directly.

Reject the candidate before matches if held-out reference regret does not improve over both controls, if calibration collapses at the second time scale, or if a small sample of extreme tactical failures accounts for the apparent savings. If it passes, freeze the policy and conduct a single-idea SPRT, then longer-time confirmation. Log all rejected models and tested thresholds so the surviving controller is not presented as the only attempt.



## TT conflict prior art audit 2026 10 22

The broad idea is Known. Detecting inconsistent TT bounds, changing search from failed-bound information, and reducing LMR when earlier search disagrees with evaluation all have direct prior art. The remaining Candidate is narrower: a short-lived warning formed from two completed, comparable-depth results for the same full key, used later to reduce one otherwise eligible quiet-move LMR by one ply. This audit did not identify that exact combination in the inspected implementations. That absence is not evidence of proven novelty, and a two-bit encoding is an implementation choice rather than a research contribution.

### Closest primary sources

| Source and date | Existing mechanism | Difference from the candidate |
| --- | --- | --- |
| Stockfish, 9 December 2012: [dual-bound storage](https://github.com/official-stockfish/Stockfish/commit/feeafb0a50556654e345a09d16529a5eb7715dc0), [contradiction handling](https://github.com/official-stockfish/Stockfish/commit/da98a45bcb643addc52333ff29fcfb20aa6872ff) | Separate upper/lower values and depths. A new upper value below the stored lower value invalidates the old lower bound; the reverse conflict invalidates the upper bound. This directly anticipates comparing disjoint intervals. | It repairs stored bounds; it does not retain a recent-conflict warning to gate LMR. The conflict comparison itself must not be claimed as new. |
| Stockfish, 15 December 2012: [revert dual-bound storage](https://github.com/official-stockfish/Stockfish/commit/a2f46446cf1c91bc293a6acea9ce268e81534042) | The experiment was removed because its measured benefit did not justify the additional code. | A failed or reverted experiment remains prior art. Its result does not test our different warning policy. |
| Bob Hyatt, 14 September 2014: [TT-induced search instability](https://open-chess.org/viewtopic.php?t=2720) | Deep one-sided TT entries can cause a fail-high followed by fail-low when the window changes and the old bound no longer supplies a cutoff. | A conflict need not mean that a reduction was unsafe. Depth and window provenance are mandatory controls. |
| H. G. Muller, 15 January 2016: [original dual-bound discussion](https://www.talkchess.com/forum/viewtopic.php?p=656461) | Explicit example of a deeper lower bound exceeding a shallower upper bound, and discussion of storing both depths. | Even the specific observation of disjoint bounds across depths is Known. |
| Stockfish, 9 May 2024: [IIR from an upper TT bound](https://github.com/official-stockfish/Stockfish/commit/db147fe2586527a854516016699949af53dc5b17) | A retained TT move accompanied by an upper bound indicates an earlier fail-low; eligible cut nodes receive an internal reduction. | Uses one current bound as failed-search history, with a different direction and reduction location. |
| Stockfish, 22 December 2024: [LMR from correction history](https://github.com/official-stockfish/Stockfish/commit/e7e78aa09e190ea0fd7fed6fcff97d98c0cf5b5f) | Larger absolute correction history reduces LMR, with a compensating base adjustment. | This is already an error-sensitive reduction policy. Our candidate must beat this family of explanation, not just static move ordering. |
| Viridithas, 6 October 2025: [TT complexity weights correction updates](https://github.com/cosmobobak/viridithas/commit/755e29b81d0d0bfc1df2a2ad67e0c35d55944dac) | Bound-aware distance between static evaluation and the cached search value scales correction-history updates. | A current TT-versus-static discrepancy is a particularly close cheap control; it does not compare two historical TT search results. |
| Stockfish, 19 May 2026: [penalize unusable inexact TT entries](https://github.com/official-stockfish/Stockfish/commit/319d61effdad40ac633425d6504a98f6d2ad0cd2), [author's diagnostic trace](https://github.com/official-stockfish/Stockfish/issues/6742#issuecomment-4386174472) | When sufficient stored depth cannot cut because its one-sided bound faces the wrong direction for the current window, decrease stored depth. The original investigation links deep unusable entries to search explosions. | A window-bound mismatch is not a pair of disjoint intervals. The intervention alters TT retention/usefulness, not one quiet-move LMR. |
| [Stockfish search at effdc3fd](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/search.cpp) | Static-evaluation trends, previous reduction, next-ply cutoff counts, prior null-move fail-highs, TT/PV state and correction magnitude affect search. Some TT cutoffs also check the TT move's child value. | None of these inspected fields is the proposed same-position, recent disjoint-result warning. They establish extensive prior art for remembering search reliability. |
| [Viridithas search at 6b6160a7](https://github.com/cosmobobak/viridithas/blob/6b6160a774800d814cc5f16d9930f5401cbddd87/src/search.rs) | LMR includes correction magnitude, cached-score/PV state, improving evaluation and earlier alpha raises. Its search key also includes a halfmove-clock component. | The candidate cannot claim novelty for an uncertainty-sensitive LMR or history-sensitive key in general. |
| [Ethereal search](https://github.com/AndyGrant/Ethereal/blob/master/src/search.c), [Ethereal TT](https://github.com/AndyGrant/Ethereal/blob/master/src/transposition.c), [Berserk search](https://github.com/jhonnold/berserk/blob/master/src/search.c), [Berserk TT](https://github.com/jhonnold/berserk/blob/master/src/transposition.h) | Inspected search uses static-evaluation trends and bound/depth information in pruning or reductions; TT update paths use depth, age and bound type. | No explicit old/new score-interval conflict warning was found in these inspected paths. This is a bounded source audit, not a survey of every version or private experiment. |

The pinned Stockfish search blob was f89d4b661fb0dd3423b1ce144cc4498cfef1ad1c; the pinned Viridithas search blob was 4c37553c383a119c4d88cba4e9c086ceb7625c3f. Additional default-branch source snapshots inspected on this date were Ethereal search ceb7971c236e75bef665f7be48c9c44a65892a1a and TT 7ad8bb268378e16223710b6337134f03c118f617, and Berserk search dc1b2fa450a9d277866cfdca9495b36e9537844b and TT header 8d005bbf0206526be88b55d784815902eceba51a. Commit/PR searches also covered instability, bound conflicts, TT penalties and correction-based reductions. Unpublished tests and differently named mechanisms remain outside this audit.

### What the feature would actually mean

Use reported score intervals, not absolute differences between fail-soft scores:

- EXACT v represents [v, v].
- LOWER v supplies the finite lower endpoint v, with no finite upper endpoint.
- UPPER v supplies the finite upper endpoint v, with no finite lower endpoint.
- Two records conflict only when one available lower endpoint exceeds the other's available upper endpoint by at least the preregistered 64 internal centipawns.

For example, LOWER 100 and UPPER 20 conflict; LOWER 100 and LOWER 20 do not. EXACT 100 and UPPER 120 overlap. Never subtract infinity, missing values, mate-band values or tablebase categories. These intervals describe the engine's reported search results; selective search and different horizons do not make them certified bounds on one game-theoretic value.

The first diagnostic should make equal depth at least four its primary comparison. Preserve the original depth-difference-at-most-two proposal as a secondary stratum, separating equal parity from opposite parity. A signal appearing only at unequal or opposite-parity depths weakens the proposed mechanism. No threshold widening after seeing low event counts.

A warning must exist before the future reduction it is supposed to predict. At a store, copy the incumbent entry by value immediately before replacement; compare only a matching full key and valid provenance. At a later node entry, copy the warning before recursion. Do not let the current search's eventual contradiction label its own earlier reductions. TT collisions, overwrites, missing bounds and incompatible provenance are unknown observations, not confirmations of stability.

For a later minimal policy, choose LMR only. At an eligible non-root, non-PV, non-check node with warning greater than zero, subtract one from the first otherwise eligible quiet-move reduction, clamped at zero. Do not also change RFP, TT cutoffs, move ordering or verification. One possible preregistered two-bit lifetime is set to three after a conflict and decrement after an eligible overlapping comparison; clear on incompatible provenance or key replacement. This lifetime is a proposal, not a tuned finding. A passive diagnostic should compare binary last-conflict against the two-bit version before paying for persistent state.

### Draw history is a real confound

ChessSI's inspected position key contains pieces, side, castling rights and its canonical en-passant file. It omits the halfmove clock and reversible path. Its draw test uses both. The same full key can therefore represent different search states. Returning directly from a draw before a TT probe does not solve this: an ancestor can incorporate the draw into its result and then store that result. Excluding score zero also fails, because a draw can change which alternative wins and the bounds of a nonzero result. This is an instance of the established Graph History Interaction problem; [Kishimoto and Muller, AAAI 2004](https://cdn.aaai.org/AAAI/2004/AAAI04-102.pdf) give a general treatment with path-dependent verification.

A simple rule50 threshold such as less than 80 is not sufficient. Repetition can matter at small counters, and extensions can reach the draw boundary beyond nominal depth. Matching halfmove counts alone also leaves different reversible histories. Stockfish labels its high-rule50 TT restriction a partial workaround; Viridithas's halfmove key addresses one omitted variable, not the complete reversible path.

Use this cheap, conservative eligibility restriction for the first diagnostic:

1. Both the old stored result and the new result were produced at rule50 exactly zero. Record an explicit old-result eligibility bit; never infer its clock from the current position.
2. Require a legal, ordinary search context, completed results, matching full key, nonmate endpoints and the declared depth comparison. Exclude null-move and excluded-move search contexts if those features exist in the eventual baseline.
3. Use the warning only while the current node also has rule50 zero. Reset diagnostic metadata for each root search; preserve the production TT's behavior.
4. Record rejected comparisons by reason. If this restricted domain has too few events, report insufficient evidence instead of relaxing it after inspection.

For legal positions, a zero halfmove clock follows an irreversible pawn move or capture, so the earlier reversible path cannot supply a repetition of a future state. Matching full keys at that boundary removes the direct pre-node clock/path ambiguity. It does not remove TT contamination already propagated through descendant searches, nor differences caused by search context, move ordering or selective depth. Confirm sampled events with separately replayed fresh-TT references; fresh tables reduce inherited contamination but do not mathematically solve GHI inside those searches. A history-aware TT or a propagation scheme proving path independence would be a separate experiment.

The inspected qsearch still lacks general draw detection. Resolve and validate draw semantics separately before treating TT-conflict traces as evidence about reduction risk. A guard trained around that defect could merely compensate for it.

### Falsification before an engine patch

Freeze a corpus, event budget, baseline, comparison rules and holdout split before collecting events. Keep all positions from a game/opening component together. Record the current window, current and stored depths, bound types, gap, warning age, rule50 eligibility, static evaluation, current TT-to-static discrepancy, improving flag, move rank, reduction and any accepted correction-history feature. Match conflict and nonconflict events on these variables; count root groups, not correlated nodes, as the replication unit.

The important target is a future reduced fail-low that full-depth verification would overturn at the same alpha. Ordinary re-search logs reveal only reduced fail-highs and cannot establish this target. Sample otherwise unverified reduced fail-lows by a fixed score-independent hash, then evaluate paired reduced/full probes in isolated replay state with identical frozen context. Account for all added diagnostic work. If identical context cannot be reproduced, label the reference approximate and restrict the claim.

Compare the conflict feature against current bound/depth/window alone, static trend, bound-aware TT-to-static discrepancy, an available correction-history baseline, and a same-frequency random guard. Reject the policy if conflict adds no held-out predictive value, its signal disappears in the rule50-zero/equal-depth domain, or only the two-bit persistence wins after post-hoc tuning. A positive diagnostic still requires the ordinary single-idea correctness checks and SPRT; it establishes no Elo gain by itself.

Preserved rejections: generic TT disagreement is not novel; dual-bound storage is not novel; error-sensitive LMR is not novel; a full-key match is not full chess-state identity; low rule50 or nonzero scores do not establish path independence. The exact temporal warning remains Candidate, with a materially narrower domain than the initial shortlist.
