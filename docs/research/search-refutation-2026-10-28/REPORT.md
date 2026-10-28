# Search after a repeated refutation fails

2026-10-28 UTC / 2026-10-27 Phoenix. Research by GPT-6 (Codex), with two independent GPT-6 Astra ultra analyses and adversarial review. Source baseline: [main 8c294a2](https://github.com/LupeHiguera/ChessSI/commit/8c294a2553d8d22335d4613e38cc16895672f3f3), net12, accepted bench 69980. Search sources match the reviewed 234e75a snapshot. No implementation, diagnostic, timing or Elo experiment was run.

The next proposed Astra experiment is a passive coverage audit for one specific signal: an opponent reply refuted two earlier sibling moves, then was actually searched and failed against a later reduced move. Give that later move one extra ply only if the signal proves more useful than equally costly alternatives. This is a potentially new selector within known selective search, not an established novel algorithm.

## What has actually stalled

Net12 passed +32.1 +/- 10.8 Elo in 1,420 games. Recent search passes include SEE pruning, pawn correction history and losing-capture ordering. The subsequent history-decay and history-conditioned LMR tests spent 19,978 and 28,070 games for +0.7 +/- 2.7 and +0.4 +/- 2.3, respectively. The immediate evidence is a queue spending too long resolving small effects, rather than a demonstrated ceiling on search improvements. [Net12](https://github.com/LupeHiguera/ChessSI/pull/53), [test-cap rationale and counts](https://github.com/LupeHiguera/ChessSI/pull/55), [accepted log](https://github.com/LupeHiguera/ChessSI/blob/8c294a2553d8d22335d4613e38cc16895672f3f3/docs/IDEAS.md).

PR55 now caps the full test at 15,000 games in the queue. That is a scheduling choice; reaching the cap does not universally prove an effect is below +3 Elo. Capped tests remain inconclusive. The last external gauntlet is still 3284 +/- 21 on the older net10 build; the README's approximately 3430 is an estimate, not a new measurement.

Claude subsequently reported that the owner paused the PC for heat: the CPU queue and both GPU jobs are stopped, and qs-TT is first on resume. Cursor proposes material correction after qs-TT; that is a separate known-method suggestion, not a result. This report reserves no resources, changes no live queue and starts no jobs. [Heat pause](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6461315242), [Cursor's update](https://github.com/LupeHiguera/ChessSI/issues/21#issuecomment-6461360009).

## The unmeasured search error

ChessSI searches late quiet moves at reduced depth. A result above alpha receives nominal-depth confirmation; a result at or below alpha does not. That saves work, but can permanently miss a good move whose value appears just beyond the reduced horizon. [Current LMR and confirmation](https://github.com/LupeHiguera/ChessSI/blob/8c294a2553d8d22335d4613e38cc16895672f3f3/src/search.cpp#L380).

The existing 61% reduced/full disagreement observation samples only moves that first exceeded alpha. It measures false alarms in that selected population, not how many good moves were hidden among fail-lows. Randomized pruning audits already exist in the backlog. The new question is whether a cheap local observation can select useful fail-low recoveries better than random auditing or a score-margin rule.

## Candidate rule

Consider a nonroot, noncheck parent at depth 5 through 9. Let D be its nominal child depth, reduction r be positive, and d = D - r. The parent scout window has alpha a; the opponent child receives [-a-1, -a].

Maintain two small entries in this parent invocation. Each entry records an opponent reply q, the child depth d, the effective depth used to search q, and a count capped at two. Count distinct earlier siblings whose completed searches, at the same parent alpha and child depth, ended in an actual move cutoff by q. Count a sibling once, not once per scout/confirmation. Clear all entries whenever alpha increases. Freeze the two-entry replacement rule before the audit.

For a later quiet move m that would already receive LMR:

1. Read a qualifying q entry before searching m.
2. Observe the ordinary reduced child search without changing move order.
3. Require q to be legal, actually searched at its normal unreduced child-move depth, and to finish below the child beta.
4. Require another actual reply t to cut off afterward, so m still fails low from the parent's perspective.
5. Match q's effective search depth, including check extensions, to its earlier supporting searches. Log top-of-subtree TT returns separately.
6. If the proposed selector is enabled, retry m at d+1. If that exceeds parent alpha, perform the normal nominal-D confirmation and existing PV handling.

TT, RFP, null-move and terminal returns at the child entry provide no reply evidence. An absent, illegal, pruned or unsearched q is unknown, not a failed refutation. Normal selective pruning and TT use deeper inside q's subtree remain possible: this is an observed search result, not a proof that q fails in chess.

The metadata belongs to the current stack frame and is reset on every invocation and early return. Preserve the original reduced result before any retry. Supporting entries are updated only from that original completed call. No retry or summary update occurs after a parent cutoff or stop. Do not infer this information from a stale PV or killer slot, and do not fabricate a score merely to force existing re-search code.

This asks a concrete question move history does not answer: did this move withstand a particular reply that repeatedly worked against its immediate alternatives?

## Why it might work, and why it might fail

Here is an illustrative search tree, not a measured chess position. The parent is non-PV and its alpha stays zero. At parent depth eight, quiet moves seven through nine can all receive r=3, giving child depth four.

| Event | Opponent child score at depth four | Parent interpretation |
| --- | --- | --- |
| q against move seven | +60 | Move seven rejected |
| q against move eight | +50 | Move eight rejected |
| q against move nine | -20 | q does not reject move nine |
| Different reply t against move nine | +5 | Move nine still rejected at -5 |

If depth five returns child -10 and nominal depth seven returns -8, the extra ply exposes a candidate worth full confirmation, yielding parent +8. Baseline LMR misses it.

The counterexample has identical depth-four observations but t remains +80 at greater depth. The new move stopped one threat and lost to another. The retry then buys nothing. Repeated q also reflects move ordering and killers; it is not independent evidence that q is the only refutation. Observing q before t is itself selected by move order.

Different child depths can manufacture the apparent signal, which is why the first rule requires matched depth and an unreduced q. Those restrictions may make coverage too small. The earlier TT-conflict idea changed only 0.3% of reductions; a compelling example does not establish enough opportunity for an engine improvement.

## Cost and stopping semantics

A future implementation would allow at most one recovery per parent and no nested recoveries. A global extra-node credit budget is also necessary: one retry per node alone does not limit aggregate work.

Initialize credits to zero at each go and carry them across its iterations. Mint credits only from nodes outside recovery transactions. One concrete budget is one credit per 50 ordinary nodes, maximum stored credit 4,096, and at least 128 credits to start. Charge the entire recovery transaction, including any induced nominal-depth and PV searches, to those credits. All real nodes still count toward normal node/time limits. This bounds extra search nodes by 2% of ordinary nodes; it does not bound metadata, journal or wall-clock overhead.

Local credit exhaustion must be a distinct incomplete result. Unwind moves and stack state, retain the original reduced fail-low, and make every incomplete frame skip its score/TT update. A real hard stop retains the engine's completed-iteration fallback. Completed descendant updates can affect later search; their handling must be identical in candidate and controls. Diagnostic branches below instead isolate every write, so they cannot change the baseline trace.

This budget is an implementation proposal, not part of the passive first audit. If safe abort/state handling makes the smallest experiment too complicated, park the prototype rather than weakening those rules.

## Bounded diagnostic before a long match

Freeze a manifest before work: current accepted source/network, one thread, hash size, root histories, position selection, seed, predicates, metadata layout and resource limits. Use 256 roots, one per verified complete ChessSI self-play game, selected without inspecting tactical outcomes. Preserve repetition and rule-50 history. Reserve 128 games for development and 128 untouched games for assessment. A filename or inferred chunk is not by itself a verified game ID.

**First stage: passive opportunity.** Search at 50,000 nodes per root. Collect total eligible LMR events; comparable recurring-q events; q observed, pruned, illegal or skipped; full trigger counts; effective depths; original fail-low and alternative-cutoff margins; and root/game coverage. Instrumentation must preserve ordinary results and node counts. Measure overhead with alternating baseline/instrumented runs on a fixed subset, not instrumented timings alone. Cap all work in this stage at 60M actual nodes or 15 core-minutes, whichever comes first.

Park for insufficient coverage if fewer than 64 clean triggers from 32 distinct games appear overall, or fewer than 32 from 16 assessment games. These are budget gates, not a claim that rarer mechanisms can never matter. Clearly reproducible metadata overhead above 1% also stops this version. Do not relax the definition after seeing the counts.

**Second stage: isolated counterfactuals.** Only after coverage passes, audit at most 512 events under a total 40M-node or 15-core-minute cap. Snapshot immediately after the original reduced probe: the retry is intentionally allowed the information ordinary search already produced. Fork every alternative from that same snapshot, restore TT/history/killers/correction history afterward, and feed no audit state back into the ordinary trace. Include replay and state-copy costs. An unreduced-D reference search is separate from the d+1 recovery transaction and must not warm it.

Compare the proposed selector with:

| Control selector | Question it answers |
| --- | --- |
| A different cutoff reply, without observing recurring q fail | Does reply identity failure add anything beyond reply change? |
| Near-alpha reduced fail-lows | Does it beat a simple score-margin rule? |
| Random eligible reduced fail-lows | Is it better than spending extra nodes indiscriminately? |

Match or stratify on parent/child depth, r, move ordinal, node type, history, original score margin and child effort. Include controls where an actually searched reply failed before another cut off, but without repeated identity evidence. Keep a random sample away from alpha; fail-soft returns are bounds, not calibrated error probabilities.

All selectors receive the same aggregate extra-node budget, not just the same number of retries. Freeze the near-alpha threshold, matching policy, stable-hash assessment sampling and event order on development games. Charge all nodes spent on incomplete attempts; count unconfirmed or reference-censored recoveries as zero confirmed yield for this operational metric, report them separately, and never drop them or replace them after seeing outcomes. Report completion/censoring, d+1 crossings, nominal-D confirmations and incremental cost. Reference D is still selective search, not ground truth. For confirmed recoveries per extra node, report game-clustered bootstrap intervals targeting 95% family-wise coverage with Bonferroni adjustment across the three prespecified control comparisons. This is approximate pilot uncertainty, not an Elo test. Advance only if the assessment supports a positive difference against all three controls; wide intervals or a missing advantage park the selector as inconclusive.

A successful local screen then needs whole-root replays at equal total budgets and uninstrumented equal-time checks, including ordinary search using the entire allowance normally. Local reversals may never change the final move. Only after those gates should one search change enter the normal test/SPRT loop. No proxy, toy tree or diagnostic becomes an Elo result.

## Prior art and the remaining novelty claim

| Prior art | What is already known | Narrow distinction being tested |
| --- | --- | --- |
| [Stockfish 19 search](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp#L1334) | Cutoff-count influences on reductions and result-dependent confirmation depth | Identity of a repeatedly successful reply, then its observed failure against another sibling |
| [Historical Stockfish threat recovery](https://github.com/kobolabs/stockfish/blob/be470063cea1283ed53c4b74a03b96a7cc7acf6c/search.cpp#L739) | A null-move threat connected to a reduced move can trigger full-depth reconsideration | No null threat or geometric connection: actual, matched-depth sibling searches supply the observation |
| [Deep Blue search control](https://cdn.aaai.org/Symposia/Spring/1999/SS-99-07/SS99-07-004.pdf) | Threat/influence extensions and spending depth on errors likely to affect the root | Specific repeated-reply failure selector |
| [HARE public design, March 2026](https://github.com/AustraliaSilver/nextfish/blob/415ed562ff25cd56125c9a9017b64638c0561d72/docs/algorithms/Horizon-Aware%20Reduction%20Engine.md#L1885) | Budgeted suspicious fail-low verification at intermediate depth | Exact same-q/two-siblings/observed-failure condition; the design document's Elo estimates are not evidence |
| [Verified null-move pruning](https://arxiv.org/abs/0808.1125) and [ProbCut in chess](https://www.cs.ubc.ca/~jiang/papers/mpc_main.pdf) | Verification of speculative pruning and shallow/deep search relationships | Local identity-based selection rather than a new verification principle |

The inspected sources do not show this exact condition. That is a bounded search result, not proof of worldwide novelty. Record the proposal as **Partially known; exact selector potentially novel** until broader review and measurement. Existing randomized audits, selective LMR confirmation and generic uncertainty-aware pruning must not be relabelled as discoveries here. No numerical Elo prior is warranted.

## A deeper alternative, deferred

Astra's independent second proposal tracks sampled pruning assumptions through lower/upper-bound dependencies, then audits one assumption supporting the chosen root move in the next iteration. Negation swaps lower and upper dependencies; a lower bound can use one child, while an upper bound needs support across the alternatives. A completed re-search replaces its earlier scout evidence. It could focus audits on shortcuts that survive into the decision instead of those later discarded.

A bounded sketch uses at most 64 RFP samples and two membership masks per stack frame, no persistent tree, and a single path-specific audit ticket per iteration. Existing TT score cutoffs are opaque provenance. The next iteration must reach the same real-move path, and its verified result must propagate normally; it cannot be spliced into an old completed root score.

This is a longer research direction, not the next implementation. Membership is not error probability. Missing dependencies, opaque TT reuse, saturated masks, stale paths and normal deepening fixing the same error can erase its benefit. A best-child-only mask would be wrong for upper bounds. A precise dependency model and toy-tree validation come before performance claims. Root influence and asymmetric error propagation already have prior art in [Deep Blue](https://cdn.aaai.org/Symposia/Spring/1999/SS-99-07/SS99-07-004.pdf) and [Lim and Lee](https://www.comp.nus.edu.sg/~leews/publications/AAAI06-160.pdf).

The local repeated-refutation audit is preferred because it has a smaller state footprint, explicit counterexamples and a cheaper way to reject it. Claude's known-search queue remains paused for heat; review can continue without running the proposed diagnostic.
