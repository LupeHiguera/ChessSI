# Research workflow for ChessSI

This project measures whether AI can do useful engine research. A stronger engine, a new method and evidence of general intelligence are different claims, with different evidence requirements. The immediate aim is to turn plausible ideas into reproducible decisions while the accepted engine steadily improves.

Prepared by GPT-6 (Codex), 2026-10-22 UTC. Follow `AGENTS.md` for current ownership, CPU allocation, testing and commit rules.

## What would count as progress?

| Claim | Evidence needed |
| --- | --- |
| The implementation is correct on specified cases | Targeted regression tests, move-generation tests, and appropriate runtime checks |
| A diagnostic predicts something useful | Untouched grouped test data, inexpensive controls, equal charged budgets, and uncertainty estimates |
| A change improves playing strength | Completed one-change SPRT against the accepted baseline, with exact build and run records |
| A gain survives more thinking time | Independent confirmation at the longer time control |
| A method is plausibly new | Precise mechanism, primary-source prior-art search, and a documented distinction from the closest methods |
| A method advances strong-engine research | Replication on a substantially stronger baseline, ultimately an independently tested Stockfish integration or comparable-strength match |
| AI can conduct autonomous research | An auditable record of hypotheses, implementation, failures, resource use, and human assistance |

A chess result alone cannot settle whether AGI exists. Beating a specialist at its task would be an important domain result; demonstrating broad competence requires independent tasks and transfer. Similarly, there is no defensible calendar estimate for matching Stockfish from the growth of general AI capability alone. Measure the current gap and the rate of verified progress first.

## The experiment cycle

1. **Freeze the question and budget.** State the proposed mechanism, predicted observation, rejection criterion, compute allowance and stopping rule. Record what came from the user, another agent, a paper or the proposing model. Keep model identity honest.
2. **Start from an accepted baseline.** Rebase onto current `main` before starting a new test. Record the full baseline SHA, candidate patch, build command, binary hashes, unchanged bench definition, book hash, CPU allocation and test options. Keep the source and binaries used by a running match immutable.
3. **Diagnose before inventing.** Find a concrete failure or cost: a wrong tactical score, wasted search after a deadline, labels that change unpredictably, or a measurement bottleneck. A small reproducible counterexample is more useful than a broad claim that uncertainty or a neural network should help.
4. **Check prior art before naming novelty.** Search the original papers, relevant engine source, fishtest records and original author discussions. Record the closest mechanism, not only identical terminology. Broad distillation, learned time allocation, uncertainty-guided search, ranking losses and subtree-work TT retention already have prior art. Use Known for established methods; describe an unresolved narrower distinction as a candidate in research notes until the evidence supports a novelty claim.
5. **Predeclare a cheap test with strong controls.** Keep related games, paired openings and transpositions together when splitting data. Freeze training, calibration and test roles. Include simple alternatives that could explain the apparent benefit. Use signed utility so a changed decision can be worse. Charge screening, failed probes, labels and training work as well as the selected examples. A deeper engine search is a reference, not chess truth.
6. **Implement one small change.** Claim the idea in `docs/IDEAS.md`. Keep unrelated pruning, evaluation, parameter tuning and infrastructure changes out of the engine comparison. Run `make test`; preserve the bench node count for changes that should leave search unchanged. Use meaningful regressions for changed behavior. Log the diagnostic outcome even if it stops the idea before a match.
7. **Measure strength under the repository protocol.** Use the prescribed SPRT and shared book, and record the actual Elo model as well as the displayed estimate. A prescreen is a diagnostic until its rejection accuracy is calibrated. Do not stop a full test merely because the estimate looks attractive. Check illegal moves, crashes and time forfeits separately; `-recover` does not make them acceptable. Confirm winners independently at the longer time control.
8. **Keep the evidence and challenge the result.** Add every completed test to the log, including failures and inconclusive runs. Revert failed engine changes while retaining the records. Commit accepted changes with the required Elo and bench fields, then use a PR. Replicate promising candidates on a new opening sample and a stronger baseline before claiming general value.

Concurrent development can move `main` while a match runs. Preserve the baseline actually tested. Rebase and perform a fresh comparison where needed before integrating an interacting change; never relabel the old result as a test against the new engine.

## A compact experiment card

Write this before examining the final test outcomes:

```text
ID / proposer / model:
Kind: Known, or candidate distinction pending prior-art audit
Baseline SHA / candidate patch / bench / binary hashes:
Observed weakness:
Mechanism and predicted observation:
Closest prior art and precise difference:
Smallest implementation:
Cheap falsification test:
Controls and ablations:
Dataset grouping / frozen splits / exclusions:
Charged compute and stopping rule:
Correctness gates:
Match protocol and independent confirmation:
Outcome, uncertainty, artifacts and next decision:
```

Use separate rows for revised hypotheses. A failed experiment followed by a tuned replacement is two attempts. Repeated adjustment against the same held-out data turns it into development data; obtain another test sample.

## First research lane: selective deeper labels

The immediate candidate asks whether cheap iterative-deepening diagnostics can choose positions worth more analysis. It needs no NNUE and changes no playing code. The detailed specification is in [evaluation research](research/codex-2026-10-22/evaluation.md).

Use one frozen correct engine with fresh TT state at each requested budget. Preserve the initial position and move history. Compare a learned selector against uniform selection, raw score volatility and volatility after the same bounded score transform used by the objective. Include a depth/phase control or an ablation of parity-aware features so ordinary depth effects do not masquerade as a new signal.

For cheap score `s0`, replacement score `s1` and larger-budget reference `s2`, measure replacement utility as:

`loss(s0, s2) - loss(s1, s2)`

Negative utility is a loss. Freeze selections before looking at audit scores; do not replace inconvenient selected roots after a mate or invalid result appears. Report coverage and charged costs. Winning this pilot establishes a reference-relative labeling advantage only. It must subsequently improve a fixed evaluator and survive a playing-strength test.

## Next research lanes

| Lane | Immediate diagnostic | Main confound |
| --- | --- | --- |
| Deadline-aware thinking | Can another iteration finish a useful root decision before the hard limit? | Simple move stability or next-iteration cost may explain the benefit |
| TT-bound conflict | Do genuinely disjoint score intervals predict costly reduction errors? | Different-depth oscillation and history-dependent positions |
| Reduced/full disagreement | Does a verified contradiction predict later sibling misses? | Only fail-high reductions receive routine verification |
| Evaluation-call data | Does a controlled mixture of actual search leaves improve a fixed evaluator? | Different position difficulty, teacher cost and model capacity |
| Test efficiency | How much time does adjudication save without changing paired results? | Mixed PGN sessions and unvalidated resignation thresholds |

See [search research](research/codex-2026-10-22/search.md) and [testing research](research/codex-2026-10-22/testing.md) for prior art, falsification gates and implementation details. These are hypotheses, not measured improvements. A [recent-evidence review](research/codex-2026-10-22/recent-evidence.md) checks the current Stockfish target and newer self-play results, including cases where better search labels did not improve learning.

## Preserve runs without mixing them

Use a unique archive per observation and a fresh match output set per experiment. The read-only `scripts/research/snapshot_run.py` tool captures bounded file snapshots and records whether each hash covers the whole initial file or only a prefix. Its `verify` command checks archived bytes; it does not certify experimental validity or calculate Elo.

For a live run, capture the manager and engine process executables separately from the current binary paths. Save the fastchess configuration so its 64-bit random seed remains an exact decimal string. Do not treat a PGN containing several reused `new`/`base` sessions as one match. Archive incomplete tails explicitly and wait for final results before logging a verdict.

For Windows-created worktrees, WSL Git may need explicit `GIT_DIR` and `GIT_WORK_TREE` environment variables because the `.git` pointer uses a Windows path. Set those for the command rather than rewriting the shared worktree metadata.

## Compare models fairly

The development queue should always improve the latest accepted engine. A model-comparison study needs a separate lane: the same frozen starting engine, resources, task information and acceptance rules for each model. Otherwise later models inherit a different difficulty level and their hit rates are not directly comparable.

Record research candidates attempted, cheap rejections, full tests, accepted gains, total compute and human interventions. Preserve useful negative results. A small repeatable improvement with a clear mechanism is stronger evidence than a large unreplicated claim.
