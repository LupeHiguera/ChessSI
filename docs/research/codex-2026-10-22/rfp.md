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

## Shadow audit of sampled cutoff assumptions

A separate instrumented copy examined the frozen RFP candidate on all 128 previously selected game-profile roots. These are reused development positions, not new held-out evidence. Each parent search had a 131,072-node cap. At a legal RFP cutoff, a fixed hash gate selected an event with probability-like density 1/256, capped at the first eight selected events per root. The deterministic gate and visit-order cap do not constitute a representative random sample of game play.

For each selected event, the auditor copied the complete `Position` history and current transposition table, searched with RFP disabled throughout that shadow subtree, restored the table, and repeated the same call with RFP enabled as a control. It restored the original table before continuing the parent search. Both searches used the original null window, depth and ply, with a 131,072-node cap. A completed disabled return below beta is a contradiction of the proposed cutoff under that search context. It is not a solved chess value: the inherited table can already contain bounds produced by RFP, and the same evaluation, quiescence and draw logic remain in use.

The instrumented benchmark stayed `11112214`. Across all 128 roots, every completed parent iteration's score, bounds, node count, PV and final best move matched the release candidate exactly. Every selected path replayed legally from the full recorded game history to its six-field FEN. All shadow and control calls restored position state.

| Remaining depth | Selected and completed shadows | Returns below beta |
| --- | ---: | ---: |
| 1 | 818 | 0 |
| 2 | 122 | 0 |
| 3 | 11 | 0 |
| Total | 951 | 0 |

The instrumented parents visited 16,777,263 nodes and encountered 1,132,034 RFP returns, none a stalemate. The sampler gate fired 4,337 times; 110 roots reached the eight-sample cap. The 951 retained observations covered 99 openings. Disabled shadows used 8,995 visits total (median four, maximum 2,373); enabled controls used one visit each. These local work counts do not predict net speed or Elo when the whole search tree changes.

Coverage is narrow: only 64 samples were within 25 cp of the pruning inequality, none at depth three, and the maximum sampled halfmove clock was 12. No shadow hit its node cap. Zero observed contradictions here does not establish that RFP is safe, supply a game-level error rate, or justify reducing its margin.

### Positive controls and harness corrections

The auditor was also tested on the previously constructed one-legal-move counterexample and its color mirror, with legal predecessor moves `h7h8` / `h2h1` to supply an actual search path. At depth one and beta 1, both RFP controls returned +182 cp; both disabled shadows returned -50 in five visits. An independently compiled accepted-baseline probe reproduced -50/five visits with the same null window, and -51/nine visits with a full window. The differing negative returns illustrate why a null-window bound should not be asserted equal to a full-window score. Both contradict the +182 cutoff in this context.

These two deliberately forced controls are excluded from the 951 sampled observations. The first control-build attempt failed because a template replacement also replaced part of `ALL_MOVES`; the second executed correctly but failed an overstrict -51 assertion inherited from the full-window diagnostic. Both attempts and their outputs are retained. The third attempt corrected the check to require a completed return below beta and independently verified the bound and node count against the baseline.

Evidence: `engines/rfp-validation/shadow-audit-01/` contains the pre-query plan, source copy, transcripts, exact trace comparisons, sampled histories and descriptive statistics. Collector `audit_shadow.py` SHA-256: `92f0ca7c28964fea71f91f46776c4d296414e286e9264777aa4514ec0cdb216c`. Positive-control attempts are `shadow-positive-control-01/` through `-03/`; final validator `validate_shadow.py` SHA-256: `ab2eac200010a33dc6cb4dd03ec66b57f8dbc6af446f3d48268fcc5ea2ab61a9`. All work ran on CPU 19; live engine files and match settings were unchanged.

### Targeted depth-three and fresh-cache follow-ups

The first sample contained no depth-three events within 25 cp of the cutoff threshold. A follow-up plan, frozen before its queries, therefore selected the first four such events per root from the same 128 development positions. It examined all eligible events for selection rather than applying the original hash gate. This was an explicitly targeted response to a coverage gap, not an independent confirmation sample.

Of 1,335 qualifying events, 228 were retained across 54 openings; 50 roots reached the four-event cap. All 228 disabled shadows completed and returned at least beta, using 14,155 visits in total. All enabled controls returned the original static score in one visit. The instrumented benchmark and all 128 parent traces again matched the frozen release exactly. No margin, depth limit, eligibility guard or live match artifact changed.

Because a shadow can inherit TT entries produced by RFP, a second follow-up replayed **every one of those 228 contexts** in the independently compiled accepted baseline with an empty TT. It preserved the starting FEN, full game history, search path, null window, remaining depth and ply. All calls completed and restored state; all still returned at least beta, using 16,066 visits. There were 29 different fail-soft returns between warm and fresh TT, but zero changes in which side of beta the result fell on. Unequal bounds are not automatically unequal position values.

These checks narrow the cache caveat for these selected cases; they do not certify pruning, measure game-level errors, or replace the match. The retained data still come from reused roots and deliberately capped event selection. The baseline search also shares the engine's existing evaluation, quiescence and draw limitations.

Artifacts: `engines/rfp-validation/shadow-depth3-01/` and `shadow-fresh-tt-01/`. Collectors: `audit_shadow_depth3.py`, SHA-256 `56b3d608911b79893e19c64c05f7503d52b358b06d20e7a9546aeb5c147ee666`; `audit_fresh_tt.py`, SHA-256 `3bc0454cc7da093fb12bae143e470424e6d948dafc05d67d74d1e0e5b3db35fc`. Each retains its pre-query plan, exact input and output, and node accounting. All diagnostics used CPU 19.

### First live match integrity audit

At `2026-10-22T13:50:19.870416+00:00`, a frozen prefix contained 232 completed games. All 23,184 plies replayed legally. Every PGN result agreed with the log, all eleven statistics reports reconciled to completed pairs, and no crash, illegal-move or time-forfeit termination was recorded. The autosave represented an earlier 220-game report and matched that event boundary; it was not mistaken for the newer PGN count. The 26-file archive verified without integrity errors or missing copied artifacts.

This is an integrity check of a live prefix, not an SPRT decision or an adjudication-accuracy estimate. The unique run's source, binary and process records remain the basis for the eventual terminal audit. Evidence: `engines/rfp-validation/match-audit-01/`, using the previously validated `audit_match.py` collector with SHA-256 `567fc6c868f9df7bfa8da871815f75d046c6b17f4eee93bfc83098fa2101bdac`.
