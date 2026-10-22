# Research status and next decisions

Prepared by GPT-6 (Codex). Snapshot: 2026-10-22 16:31 UTC. The research window ends at 19:53 UTC (12:53 PM Arizona). This page summarizes evidence; [IDEAS.md](../../IDEAS.md) remains the strength-test log and claim queue.

**No playing-strength gain has been accepted from this worker yet.** The check-evasion experiment failed; RFP passed STC against its original baseline. Main has advanced, and a fresh RFP comparison against it is now running. No LTC confirmation has started. Research tools and reports are available in [draft PR #2](https://github.com/LupeHiguera/ChessSI/pull/2). That PR leaves the accepted engine unchanged, with bench `864538` after incorporating accepted main `f801f8c`; its candidate patches are unapplied evidence artifacts.

| Work | Current evidence | Next decision |
| --- | --- | --- |
| Check evasions in quiescence, Known | Failed: H0 accepted after 4,026 counted games, logistic Elo -11.83 +/- 8.36 at 10+0.1. Code reverted; 4,027 saved games legally replayed, one unpaired game excluded. | Any revised implementation is a new trial against the then-accepted baseline. [Result](qsearch.md#final-result) |
| Shallow reverse futility pruning, Known | STC Passed against original `a8eebea`: H1 after 1,568 counted games, logistic Elo +39.39 +/- 13.98 at 10+0.1, concurrency 5. All 1,569 saved games legally replayed; unpaired game 1568 excluded. Original candidate bench `11112214`. | Unpromoted. Main advanced to `f801f8c`; the completed pass does not establish a gain there. The old-baseline LTC preflight correctly refused launch. [Audited result](rfp.md#final-result-on-the-original-baseline) |
| RFP on updated accepted main | Running from 16:26 UTC against `f801f8c`, five concurrent games on CPUs 14-19. Candidate/base bench `609035` / `864538`; 35 perft, 17 boundary and 17 sanitizer checks passed. Fresh seed and protocol verified; 33-game prefix legally replayed. | Wait for the declared SPRT or fixed deadline, then audit. A winner still needs independent 60+0.6 confirmation. [New run](rfp.md#fresh-stc-comparison-on-updated-main) |
| Cheaper implementation of the RFP legal witness | Isolated first-pawn shortcut preserves tested moves/search traces and bench. Six paired timings showed a 4.36% lower median, under concurrent load. | Unpromoted. Test the complete final candidate separately before a strength claim. [Details](rfp.md#isolated-optimization-first-pawn-legal-witness) |
| Cheaper qsearch evasions | Several isolated implementations and legality checks retained. Direct generation was faster than its compaction control in a short paired benchmark. | No variant has passed SPRT. Timing gains from different comparisons cannot be combined. [Diagnostics](qsearch.md) |
| Selective deeper labeling | Version-2 harness, frozen corpus and acceptance controls are ready; no real pilot labels collected. | Settle teacher correctness and freeze its identity before collection. [Protocol](evaluation.md) |
| Deadline-conditioned decision value | Development studies found both helpful and harmful move changes, reference-budget sensitivity and incomplete-iteration costs. | Needs fresh grouped evidence against move-stability and cost-only controls before a policy or novelty claim. [Research](search.md) |
| Predict cutoff risk | A forced contradiction is reproducible, but sampled and boundary-stress development cases supplied no natural contradictions for a useful predictor. The operative search window changes the conclusion. | Do not fit or claim a calibrated guard from this corpus. [Counterexample](rfp.md#does-the-positive-control-change-ordinary-root-search) |
| Tactical proof reuse | Broad method has prior art; a naive board mask was rejected by a remote-defense counterexample. | No implementation proposed for promotion. Any successor needs complete defense/history validation and a cost advantage. [Audit](proof-reuse.md) |

## What is ready to use

The [research workflow](../../RESEARCH_WORKFLOW.md) turns a proposed mechanism into one controlled experiment: freeze the question, check primary prior art, specify a cheap falsification test, implement one change, measure it, and preserve failures. The research tools currently pass **98 deterministic tests**:

- `snapshot_run.py`: capture and verify bounded evidence archives.
- `extract_result.py`: extract explicit terminal decisions and reconstruct paired counts; it never assigns benchmark acceptance.
- `prepare_corpus.py`: replay PGNs, preserve move history and group related positions.
- `label_budget.py`: collect from an explicitly frozen engine and evaluate the label-selection screen with missing-data sensitivity and a retention control.

The frozen labeling corpus has 1,024 roots: **507 train / 248 calibration / 269 test**, with **88 / 42 / 49 connected groups**. Planned caps total **54,132,736 nodes**. These are plans, not consumed search or successful labels. Protocol `magnitude-selector-v2-retention-control` requires positive conservative comparisons against all four allocation controls and keeping the cheap labels. The implemented model predicts change magnitude; the later signed-utility selector is a separate proposal requiring its own preregistration and fresh test groups.

## What to do next

1. Finish and audit the frozen RFP comparison on `f801f8c`, preserving the separately audited old-baseline pass and its evidence. The old-baseline LTC preflight remains closed because main moved. A fresh short-time pass still needs independent 60+0.6 confirmation; an unfinished test at the deadline stays Inconclusive.
2. Follow `AGENTS.md`: check the latest accepted main and queue ownership before another strength test, work only on `astra/` branches in the assigned worktree, and keep one idea per cycle. Claude's claims are not this worker's tasks.
3. Resolve the teacher prerequisites in separate, explicitly claimed changes. Existing diagnostics expose check-evasion, draw-clock/mate-priority and TT-history limitations; perft does not settle those semantics. Choosing an external teacher would instead measure transferred knowledge and needs an explicit adapter/protocol, not an unnoticed replacement.
4. Run the frozen label screen only when its prerequisites are met. A favorable reference-relative result must then improve a fixed evaluator under matched training costs and survive games. If it fails, preserve it and move on without weakening its gate.

Stockfish is a useful external target, but the current evidence supplies neither a date for matching it nor an AGI conclusion. Broad ideas such as uncertainty-guided search, learned time allocation, distillation and depth voting already have prior art. A research contribution needs a precise difference, controlled evidence and replication on a stronger engine. The [recent-evidence review](recent-evidence.md) records relevant external results and their limits.
