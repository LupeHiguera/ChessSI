# Ten additional experiments for ChessSI

Research date: 2026-10-28 UTC (2026-10-27 in Arizona). Proposed, unclaimed and untested.
Synthesis: GPT-6 (Codex), with three GPT-6 Astra ultra subagents covering search, systems and training.
No engine edits, builds, games, data scans, training or GPU jobs were run for this report.

## What this set is trying to accomplish

The project has two useful outputs: a stronger engine and evidence that AI can discover a useful method. Those require different claims. Known missing mechanisms belong in the strength track; an unusual proposal earns the research claim only after prior-art checking, controlled ablation and replication. None of these ten has an Elo result. Matching Stockfish would be an important engineering result, not by itself a general-intelligence test.

This review is pinned to [main 8c294a2](https://github.com/LupeHiguera/ChessSI/tree/8c294a2553d8d22335d4613e38cc16895672f3f3), using net12. The accepted bench signature is 69980; it was not rerun during the heat pause. The two stopped history experiments consumed 48,048 games with estimates near zero, while the log records gains from adding missing mechanisms. That motivates breadth across concrete omissions before another small history adjustment; it does not prove that every missing feature helps.

The [heat pause](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6461315242) remains in force. Claude's qs-TT test and the separate material-correction suggestion retain their existing priority on resume. This is a menu, not ten simultaneous jobs or implementation claims.

| Order for initial screening | Experiment | Classification | Reason to investigate |
| --- | --- | --- | --- |
| 1 | Threat-aware quiet ordering | Known | Give existing search more relevant quiet moves earlier |
| 2 | Pin-aware static exchange evaluation | Known | Stop treating illegal recaptures as available |
| 3 | Select a completed helper result | Known family; conservative election to test | Use information already computed in multithread play |
| 4 | Exact raw NNUE evaluation cache | Known | Avoid repeated readouts without changing the evaluator |
| 5 | Quiet defenses selected by an exchange witness | Partially known; exact selector potentially new | Recognize a defense of another piece before it is reduced away |
| 6 | Order captures by cutoff probability per search cost | Known principle; new local application | Spend fewer nodes finding a usable cutoff |
| 7 | Explicit castling-right inputs | Known | Supply legal-state information the current network cannot see |
| 8 | Small product residual preserving every SCReLU term | Known family; narrower new experiment | Add interactions without discarding current capacity |
| 9 | Upcoming repetition detection | Known | Recognize an available draw before rediscovering it down the tree |
| 10 | Reduce duplication among active hidden units | Known regularization; NNUE benefit unestablished | Test whether H256 can use its existing capacity better |

This order is a judgment about experiment cost, specificity and likely usefulness, not a numerical ranking of expected Elo. For the strongest research question, prioritize card 5 after its simpler controls. Cards 8 and 10 explore evaluator capacity without automatically buying a wider network.

## 1. Threat-aware quiet ordering

**Mechanism.** Current quiet ordering uses killers and history. At noncheck main-search nodes, compute enemy pawn/minor/rook attack masks once. Add a fixed ordering bonus for escaping an attack from a cheaper piece and a penalty for moving into one. Preserve TT-move, good-capture and killer precedence. Leave reductions, pruning thresholds and history-update formulas unchanged.

This supplies current-board information when the history table has little evidence. [Stockfish 17's move picker](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp#L112) provides direct prior art: this is Known, not a novel threat model.

**First gate.** Freeze 256 own-game roots, split by actual game into development and untouched assessment sets. Cap the screen at 20 core-minutes after resume. Compare baseline, changed ordering, and a control that computes the same attack masks but ignores them. Use 50,000-node diagnostics and equal-time searches; higher-budget ChessSI analysis is a comparison, not ground truth. Freeze bonuses before assessment.

**Reject if** gains disappear after charging for mask construction, or the ordering rewards passive retreats while demoting sound sacrifices. A reduction in nodes at fixed depth alone is insufficient: ordering changes also alter selective search.

## 2. Pin-aware static exchange evaluation

**Mechanism.** Current `Searcher::see_ge` repeatedly selects least-valuable attackers without enforcing absolute pins. Exclude an illegal recapturer while its pin persists. Re-evaluate pins as exchange occupancy changes. Moving along the king-pinner line or capturing the pinner can be legal, so a blanket ban on pinned pieces is wrong.

This affects the exchange estimates already used in capture ordering and pruning. It is distinct from the older check-evasion legality sieve, which dealt with generated moves. [Stockfish's SEE implementation](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/position.cpp#L1304) is direct Known prior art.

**First gate.** Use targeted pin, discovered-pin and pinner-capture fixtures, then at most 5,000 observed exchange cases against a slow legal exchange reference, capped at 15 core-minutes. Separate corrections to impossible recaptures from ordinary SEE approximation differences. Compare whole-search timing with a mask-computation-only control.

**Reject if** dynamic pin handling is incorrect or its broad per-call cost exceeds the benefit. SEE still ignores many tactical resources; making its recaptures legal does not turn it into a proof of a position's value.

## 3. Select a completed helper result

**Mechanism.** Helpers currently influence the shared TT, but `helper_search()` does not retain a durable completed result for final election; `think()` returns the main worker's result. Save each worker's move, score, depth and PV together only after an aspiration iteration finishes successfully. Read snapshots after the existing stop/join synchronization. Preserve root history in every worker.

[Stockfish's best-thread selection](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/thread.cpp) establishes the Known family. Copying its score-weighted formula blindly is unsuitable: ChessSI's main pawn correction persists while helpers start fresh, so their centipawn scores are not identically calibrated.

**Smallest election.** In a three-thread trial, retain the main result unless both helpers agree on a different legal root move and each completed at least the main worker's depth. Keep the main result in mate-score cases initially. Return one complete qualifying helper record, chosen by depth then fixed worker ID, rather than mixing a move from one worker with another's score/PV. Votes sharing a TT are correlated, not independent confidence estimates.

**First gate.** At most 128 own-game roots and 15 elapsed minutes on the assigned cores. Measure disagreement coverage and decision changes. Require unchanged one-thread behavior. A strength test must be three threads versus three threads, one game concurrent to fit six busy cores. The earlier four-versus-one scaling result cannot validate this election.

**Reject if** there is negligible useful disagreement or agreement amplifies the same search mistake.

## 4. Exact raw NNUE evaluation cache

**Mechanism.** A bounded private cache per worker stores the raw integer output of `NNUE::evaluate`, before correction history and search-specific clipping. It saves the readout, not accumulator updates. This is different from the rejected-move update audit and from cached search bounds. [YaneuraOu's NNUE evaluation hash](https://github.com/yaneurao/YaneuraOu/blob/master/source/eval/nnue/evaluate_nnue.cpp) is Known precedent.

Define identity from the deployed feature schema. For today's network, verify complete piece placement, side to move and network generation. Use a hash to index, then compare full identity if calling the cache exact; a hash tag alone is probabilistic. Do not infer the opposite side's score by negation. Bypass when NNUE is absent and invalidate on network load.

**First gate.** Start with 4,096 entries per worker. Measure at most two million evaluation requests or 15 core-minutes. Include lookup, identity verification and replacement cost. Verify identical evaluation, deterministic one-thread node counts and root results through make/undo, null moves, captures, promotions, en passant and network reload. Then alternate uninstrumented timing runs. Keep TT size fixed for exact parity checks. Account for the extra memory in a separate equal-total-memory strength/performance comparison; changing TT capacity can legitimately change node counts.

**Reject if** hit rates or complete-search speed gains are inadequate. Re-measure after qs-TT: it may remove many opportunities. If card 7 lands, rights become part of neural identity. Draw/repetition decisions never belong in this cache.

## 5. Quiet defenses selected by an exchange witness

**Mechanism.** At noncheck depth-5-to-9 nodes, after the TT move and good captures fail to cut off, inspect at most four hypothetical opponent captures, ordered by victim value. Select the first legal threat against a non-pawn piece with exchange profit at least a pawn. Record the exchange participants and slider dependencies.

Inspect at most four remaining quiet moves, in existing history order, that affect those dependencies. Include moves that add/remove attacks on the target or change a participant's pin/slider relationships, even when neither endpoint belongs to the original exchange. Recompute the affected exchange after each legal quiet move. Promote a move only if the same opponent capture becomes illegal or its estimated profit crosses from positive to nonpositive. The primary assessment excludes simply moving the victim away, separating this idea from card 1.

An example is blocking the line of a recapturing rook, defending a different attacked piece, or pinning a would-be recapturer. Static threat analysis does not imply that passing is a legal chess move; legality and king safety must be checked explicitly in each simulated position.

**Novelty.** SEE and threat-based ordering are established, including [Stockfish's threat ordering](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp#L112). The narrow intervention is using an explicit exchange sequence to select a quiet defense of another piece. No exact match was found in the checked sources; classify it Partially known, exact selector potentially novel. It is separate from [PR 56's search-refutation retry](https://github.com/LupeHiguera/ChessSI/pull/56): this changes ordering, adds no search extension and needs no repeated sibling refutation.

**First gate.** At most 256 roots, 512 triggered nodes and 30 core-minutes. Require 64 eligible cases across 32 games before an intervention screen. Compare against card 1 and a geometry-only control promoting the same number of moves at matched accounting cost. Use the latest accepted SEE semantics, including card 2 if it lands. Never turn a stale exchange witness into a pruning rule.

**Reject if** witnesses are sparse, ordinary attack ordering explains the benefit, or stopping one exchange usually loses to another threat. A SEE defense is a candidate to search, not proof of safety.

## 6. Capture ordering by cutoff probability per search cost

**Mechanism.** Within good-SEE captures at non-PV nodes, retain the TT move first and preserve the good/bad capture partition. For a small per-thread table keyed by moving piece, destination, victim and depth bucket, estimate cutoff probability and completed transaction cost. Rank by a shrunk estimate of probability divided by mean cost, using MVV-LVA to resolve ties. Charge reduced probes, confirmations and re-searches together.

[Fastest-cut-first research](https://ijcai.org/proceedings/2009/89) establishes the Known principle. Probability/cost has a clean interpretation in simplified independent search models; real chess violates those assumptions through TT reuse, ordering and reductions.

**First gate.** Freeze 512 sampled non-PV nodes from disjoint own games. Replay alternative orders in isolated search state, capped at 40 million nodes or 30 core-minutes. Compare MVV-LVA, ordinary capture-history ordering, and cost-aware ordering with matched bookkeeping/memory. Freeze smoothing and bucket choices before assessment. Interrupted attempts must not be recorded as cheap failures.

**Reject if** this only reproduces capture history, or local cutoff savings fail to improve whole-root equal-time decisions. This should not take over Claude's capture-history implementation claim: coordinate a separate cost-aware experiment after its baseline is available.

## 7. Explicit castling-right inputs

**Mechanism.** Add four binary castling-right feature rows to the H256 input, initialized to zero so the initial evaluator remains unchanged. Keep the original piece features and output. Encode the four rights relative to each accumulator's color, preserving the existing color/rank symmetry. The current network sees piece placement and perspective but cannot distinguish the same arrangement with different castling rights. [Lc0's encoder](https://github.com/LeelaChessZero/lc0/blob/fe412a9ffa246684880fff6bf8417f70342e39c7/src/neural/encoder.cc) explicitly represents rights: this is Known state encoding.

The trainer reads complete FENs but drops rights from the feature arrays. Its deduplication identity already includes rights; that is not a deduplication bug. Preserve the rights mask in a versioned cache field, separate from the full 32-piece storage. Runtime refresh and incremental updates must add/remove rights features after king moves, rook moves and rook captures. Network format/version checks must reject mismatches. A future raw-evaluation cache must include these inputs.

**First gate.** Use a fixed four-million-row own-data snapshot, two epochs and two seeds. Compare actual rights with unchanged inputs and a control inferring possible rights from king/rook placement, at identical rows, steps, targets and auxiliary-head settings. Copy the original input/output initialization across arms explicitly; a shared seed alone is insufficient when allocating extra feature rows changes random-number consumption. Assess whole-game holdouts, rights-bearing positions and placement-ambiguous positions separately. Do not require naturally repeated identical boards; that would repeat the failed aggregation coverage gate.

**Reject if** true rights supply no reproducible signal beyond the placement control, or timed strength rejects the new network. Search already handles castling correctly, and rights may usually be inferable in current games; upside is unestablished.

## 8. Add a small product residual while preserving SCReLU

**Mechanism.** With clamped hidden values `c_i`, today's readout uses terms `w_i*c_i^2`. Retain all of them and add 32 fixed cross-channel terms per perspective, `v_ij*c_i*c_j`, with every new coefficient initialized to zero. Keep H256 and the current input. Freeze one pairing map before any assessment.

Products are Known; [Stockfish's NNUE architecture documentation](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md#product-pooling) discusses product pooling. The older ChessSI proposal replaced representation with product pooling plus further layers. This narrower experiment preserves every original term and the starting function, isolating whether a few off-diagonal interactions justify their CPU cost. It is an extension of that family, not a claim of new mathematics.

**First gate.** Freeze net12's feature transform and fit only the added coefficients on a bounded own-data subset. Compare against refitting the existing output and adding the same number of linear clamped-activation coefficients, with matched rows/optimizer work. Use disjoint whole-game assessment. Only a survivor merits a matched full-network continuation.

Verify exact integer scaling, overflow limits and scalar/SIMD parity before testing games. A lower validation loss is insufficient if the added multiplies slow search too much.

**Reject if** the simpler output control explains the gain or equal-time play loses. Frozen-feature failure applies to this cheap screen, not every jointly trained product architecture; do not respond by repeatedly searching pair maps on the holdout.

## 9. Upcoming repetition detection

**Mechanism.** At a nonroot node with alpha below draw, identify a legal reversible move leading to a repetition recognized by the current draw policy. A reversible-move Zobrist-difference lookup can avoid searching the same cycle to discover the draw. [Stockfish's upcoming-repetition implementation](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/position.cpp#L1396) is direct Known prior art.

Preserve ChessSI's present history/plies-from-null/reversible-clock policy; this proposal does not replace its search repetition rule with a different FIDE adjudication rule. Verify blockers, pins, rights changes, en passant and null boundaries.

**Correctness trap.** Raising alpha alone is insufficient: current search subsequently initializes its best score to negative infinity and could return a loss after proving a draw option. Carry the witnessed draw through best-score and bound bookkeeping. Do not export this history-dependent result as a history-independent TT bound, including at affected ancestors. Direct alpha/cutoff use needs explicit dependency handling; fall back to move ordering if that cannot be ensured. A position reconstructed from FEN alone is not an adequate test input.

**First gate.** Compare the fast detector to enumerating legal reversible moves and calling the repetition portion of the existing draw detector. Its combined `is_draw()` also handles the fifty-move threshold; isolate repetition or exclude candidate children reaching that threshold so these do not count as detector agreement. Use adversarial fixtures plus 256 history-preserving roots, capped at 20 core-minutes. Any false positive blocks the trial.

**Reject if** trustworthy detections are too rare or lookup overhead costs more than saved search. This has more correctness work than the first cards and no established large upside.

## 10. Reduce duplication among active hidden units

**Mechanism.** Inspect hidden SCReLU activations on two independent own-game training cohorts. Identify active, variable neuron pairs with stable high correlation within material bands. Freeze a small list of pairs, then add a training-only normalized-correlation penalty for those pairs while retaining every original target, main loss and auxiliary head. Compute statistics on a bounded minibatch subset.

[DeCov](https://arxiv.org/abs/1511.06068) establishes decorrelation as Known regularization. The proposed normalized, fixed-pair screen is a local adaptation. Dead-unit recycling in the older backlog resets inactive units; this targets duplicated responses among active units without a reset. It changes neither the network format nor inference cost.

**First gate.** Require, before training, at least 16 disjoint active pairs with absolute correlation above 0.95 in both cohorts within the declared material bands. This is an engineering threshold, not an Elo-calibrated one. If absent, park the idea. Otherwise run a two-million-row, two-epoch matched continuation with two seeds, identical batches and steps, and reported GPU time. Select pairs and penalty weight only on development data.

**Reject if** ordinary held-out blend loss does not improve reproducibly across game groups, phase-specific errors worsen, or activation variance collapses. Lower correlation or higher effective rank alone is not success. Correlated neurons may encode useful complementary thresholds, so apparent duplication is a hypothesis rather than wasted capacity.

## Common acceptance rules and interactions

Each implementation starts only after the heat pause is lifted and a single idea is claimed in `docs/IDEAS.md`. Fetch/rebase onto accepted main, record source/network/data identities and fixed stopping rules, and preserve the assigned six-core share. All training labels remain ChessSI's own search scores and game outcomes. No opponent evaluations, external networks or datasets enter these experiments.

The trainer currently exports only `.nnue`, which loses floating training weights, optimizer state and the auxiliary head. For any continuation, use a future full checkpoint shared across arms, or explicitly initialize every arm from the same dequantized net12 with identically reset optimizer state and identically initialized auxiliary heads. The latter is a new continuation protocol, not recovery of net12's original training state. Extra parameter allocation must not change common initial weights or data order.

The caps above are proposed first-screen limits, not measurements. Preregister missing details, such as the product screen's exact row/step cap, before running it. Keep complete games out of development and assessment overlap. Higher-budget self-analysis is diagnostic evidence, never a substitute for games or a ground-truth label.

For code trials, run required correctness checks; speed-only changes must preserve bench nodes. Survivors use the project's capped SPRT [0,5] at 10+0.1 and long-time confirmation at 60+0.6. Reaching the game cap without a boundary is inconclusive. Search trials use Threads=1 except card 3's explicit matched multithread comparison. Log rejected screens and failures as carefully as successes.

Do not add predicted gains across these cards. Ordering changes alter later opportunity rates. Pin-aware SEE changes card 5's witnesses. qs-TT may reduce card 4's hit opportunities. Castling inputs change card 4's identity. Re-screen the next idea on the latest accepted engine.

## Duplicate and novelty audit

The initial same-game scalar-difference proposal was removed: the [October 25 covariance report](../research-sprint-2026-10-25/REPORT.md#deferred-hypothesis-same-game-covariance-weighting) already gives the same residual-difference algebra and controls. Adaptive output rounding was also left out because the earlier output-refit/QAT discussion already covers closely related work. ProbCut, broad threat inputs, policy heads, generic auxiliary heads, bigger widths/buckets, repeated-label aggregation, GPU label backup, selective confirmation depth and the two PR 56 proposals are not recounted as new items here.

Card 8 explicitly narrows a previously proposed architecture family; card 4 separates a raw-evaluation cache from already discussed static-eval storage in the TT. Neither is advertised as a newly invented family. Card 6 must beat ordinary capture history, which is already queued.

For a discovery claim, card 5 needs another adversarial prior-art review and successful ablations. A positive ChessSI result would establish usefulness here. Transfer to a stronger independent engine, with its own controlled match, would be much stronger evidence of a general contribution.
