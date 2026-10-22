# Shallow reverse futility pruning trial

Prepared by GPT-6 (Codex), 2026-10-22 UTC. **Status: running; no strength result.** This is idea 5, classified Known. The separate check-evasion experiment ended with H0 accepted, was logged as Failed, and its engine changes were reverted before this trial began.

## Question and frozen implementation

Can shallow reverse futility pruning improve ChessSI's playing strength against the accepted baseline? The existing static evaluation may already be far enough above a null-window threshold that searching the remaining shallow subtree costs more than it contributes.

The first implementation follows the [predeclared boundary contract](search.md#minimal-first-trial-contract), including its draw-clock amendment made before implementation:

- Only non-root, non-PV nodes outside check, at positive depths 1-3.
- A fixed margin of 150 centipawns per remaining ply; no tuning sweep.
- The side to move must have a piece other than a pawn or king.
- Both beta and static evaluation must be outside the mate-score band.
- `rule50 + depth < 100` must hold. This guards the nominal horizon, not every possible extension or quiescence continuation.
- Existing stop, draw, maximum-ply and applicable transposition-table exits run first.
- If `staticEval - 150 * depth >= beta`, require a legal-move witness. Return zero for stalemate; otherwise return the static evaluation. Every probe is paired with undo, including illegal moves.
- No transposition-table store is added on this new return path.

RFP is an established heuristic, not a certified lower bound. The previously constructed one-legal-move counterexample still shows why a legal witness alone cannot prove the pruning assumption. Existing draw-boundary and TT-history defects remain separate findings; this test does not bundle repairs for them. Prior art is recorded in the linked proposal, including pinned Ethereal and Stockfish source.

## Baseline, validation and match

The branch is `astra/rfp-shallow`, rebased on accepted `main` before implementation. The claim was committed before editing engine code. Baseline: `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`; branch claim HEAD: `6fa06567f47edb2eb5fed927c115a67744a1645b`. The candidate is that HEAD plus the archived working-tree patch and `tests/rfp.cpp`.

A forced `taskset -c 14-19 make -j6 -B test` passed all 35 perft cases and 15 RFP boundary cases. The latter cover positive eligibility, both colors, root PV preservation, wide windows, check evasions, pawn-only material, depth four, mate-band windows, insufficient static margin, the fifty-move horizon, both stalemate fixtures, draw priority and stop priority. All cases check restored position state. The same 15 cases passed with AddressSanitizer and UBSan. These are specified boundary checks, not a complete chess-correctness proof.

| Artifact | Value |
| --- | --- |
| Candidate bench | `11112214` |
| Baseline bench | `20648203` |
| Candidate binary SHA-256 | `5e4dd90efb98789bc90ceff0eda627332ab8abdb1f98ed5b41326fd72ea8a8d4` |
| Baseline binary SHA-256 | `b55b4dac011664fe03f068b31ef7868e7413d064338b2d0b6eb3a0001e21520b` |
| Candidate `src/search.cpp` SHA-256 | `ef411444d19350e8903f40069f2657acd8b4dca4a0b227ed12698af4f97cbeeb` |
| Fastchess SHA-256 | `3d0a8f3c8b837a96366ac838f3ddf6fe87b813abb4ad2852284c0ce409132566` |

The runner uses `scripts/sprt.sh` with `CPUS=14-19`, `CONCURRENCY=5`, the shared `BOOK=../ChessSI/books/UHO_Lichess_4852_v1.epd`, `MAKEFLAGS='-j6 -B'`, `TC=10+0.1`, `ELO0=0`, `ELO1=5`, alpha/beta 0.05, Hash 16 and Threads 1. This is the prescribed normalized-Elo SPRT; no prescreen was run. The unchanged resign/draw adjudication settings remain enabled. The opening book is shared and read-only; its previously verified SHA-256 is `7a7f6470615a69c6cf23d565417701d38732876f480af90d67b42abade35644a`.

The match manager is PID 1850159, start ticks `3934763`, on CPUs 14-19. Its identity and executable were verified before attaching the existing pidfd-based guard at `2026-10-22T13:25:00.289568+00:00`. That guard is pinned to CPU 19 and will request one interrupt at **2026-10-22 19:53 UTC / 12:53 PM America/Phoenix**, then archive the run. A deadline interruption or exhausted game cap without a unique terminal decision is Inconclusive. A passed short-time-control test still needs independent `60+0.6` confirmation under the project plan.

## Evidence and next decision

Local evidence is under ignored `engines/rfp-validation/`: `launch-plan.json`, `candidate.patch`, `release-tests-tail.txt`, `sanitizer-tests.txt`, `bench.txt`, `sprt-stc.log`, and the running guard's `live-watch-01/`. The source archive `source-snapshot-01/` verified 34 files with no integrity errors or findings. It includes engine sources, tests, instructions, claim, launch settings, binaries and the observed manager executable. As with all snapshots, source capture itself does not prove source-to-binary correspondence; the forced builds, recorded commands and hashes provide the surrounding evidence.

The previous match's original `config.json`, PGN, binaries and baseline source were moved into `engines/qsearch-validation/original-run-files/` before the runner reused their paths. Its independent terminal snapshot and audit remain intact.

After a terminal decision, replay the PGN legally, reconcile every reported count and paired result, inspect abnormal terminations, then log the actual result. Failed code is reverted; an unresolved deadline result is retained as Inconclusive. Interim estimates and the smaller benchmark node count are not evidence of an Elo gain. Engine sources and match binaries remain frozen while the match runs.
