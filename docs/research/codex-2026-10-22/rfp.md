# Shallow reverse futility pruning trial

Prepared by GPT-6 (Codex), 2026-10-22 UTC. **Status: STC Passed on the original baseline; unpromoted, with no LTC confirmation. A fresh STC comparison on updated main is now running.** See [the new run](#fresh-stc-comparison-on-updated-main). See the [audited final result](#final-result-on-the-original-baseline). Main advanced during this frozen comparison; see [baseline transition](#accepted-main-advanced-during-the-run). This is idea 5, classified Known. The separate check-evasion experiment ended with H0 accepted, was logged as Failed, and its engine changes were reverted before this trial began.

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

The original trial used `astra/rfp-shallow`, rebased on accepted `main` before implementation. The claim was committed before editing engine code. Baseline: `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`; branch claim HEAD: `6fa06567f47edb2eb5fed927c115a67744a1645b`. The candidate is that HEAD plus the archived working-tree patch and `tests/rfp.cpp`.

A forced `taskset -c 14-19 make -j6 -B test` passed all 35 perft cases and 15 RFP boundary cases. The latter cover positive eligibility, both colors, root PV preservation, wide windows, check evasions, pawn-only material, depth four, mate-band windows, insufficient static margin, the fifty-move horizon, both stalemate fixtures, draw priority and stop priority. All cases check restored position state. The same 15 cases passed with AddressSanitizer and UBSan. These are specified boundary checks, not a complete chess-correctness proof.

| Artifact | Value |
| --- | --- |
| Candidate bench | `11112214` |
| Baseline bench | `20648203` |
| Candidate binary SHA-256 | `5e4dd90efb98789bc90ceff0eda627332ab8abdb1f98ed5b41326fd72ea8a8d4` |
| Baseline binary SHA-256 | `b55b4dac011664fe03f068b31ef7868e7413d064338b2d0b6eb3a0001e21520b` |
| Candidate `src/search.cpp` SHA-256 | `ef411444d19350e8903f40069f2657acd8b4dca4a0b227ed12698af4f97cbeeb` |
| Fastchess SHA-256 | `3d0a8f3c8b837a96366ac838f3ddf6fe87b813abb4ad2852284c0ce409132566` |

The original runner used `scripts/sprt.sh` with `CPUS=14-19`, `CONCURRENCY=5`, the shared `BOOK=../ChessSI/books/UHO_Lichess_4852_v1.epd`, `MAKEFLAGS='-j6 -B'`, `TC=10+0.1`, `ELO0=0`, `ELO1=5`, alpha/beta 0.05, Hash 16 and Threads 1. This is the prescribed normalized-Elo SPRT; no prescreen was run. The unchanged resign/draw adjudication settings remain enabled. The opening book is shared and read-only; its previously verified SHA-256 is `7a7f6470615a69c6cf23d565417701d38732876f480af90d67b42abade35644a`.

The original match manager was PID 1850159, start ticks `3934763`, on CPUs 14-19. Its identity and executable were verified before attaching the existing pidfd-based guard at `2026-10-22T13:25:00.289568+00:00`. That guard was pinned to CPU 19 and configured to request one interrupt at **2026-10-22 19:53 UTC / 12:53 PM America/Phoenix**, then archive the run. The manager instead exited normally before the deadline; the guard archived it without sending a signal. A deadline interruption or exhausted game cap without a unique terminal decision is Inconclusive. A passed short-time-control test still needs independent `60+0.6` confirmation under the project plan.

## Final result on the original baseline

The frozen `10+0.1` comparison accepted **H1** at log line **3779**, after **1,568 counted games**. This is an audited **STC Passed** result only against `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`. It is not an accepted or promoted gain on the newer main, and no LTC confirmation has started.

| Terminal statistic | Value |
| --- | --- |
| Candidate wins / losses / draws | 653 / 476 / 439 |
| Completed pairs | 784 |
| Pentanomial, LL / LD / DD-or-WL / WD / WW | 60 / 134 / 281 / 187 / 122 |
| Logistic Elo estimate | +39.39 +/- 13.98 |
| Normalized Elo estimate | +48.89 +/- 17.20 |
| Printed LLR | 2.95, for normalized SPRT [0,5], alpha/beta 0.05 |
| Original candidate / baseline bench | 11112214 / 20648203 |

The independent audit legally replayed all **1,569 saved games and 156,543 plies**, reconciled all **79 statistics reports**, the final configuration and every saved game result, and found no report-count mismatches, missing cross-source games or suspect termination reasons. Completed game **1568** was unpaired and excluded from the SPRT counts. Games **1567, 1571, 1572 and 1573** had started but had no recorded finish; there were no late starts, finishes or statistics after the decision.

The runner and guard completed with exit code 0. The guard recorded normal manager exit at approximately 16:16:52 UTC, sent no signal and found no candidate/baseline binary drift. Archive verification checked 25 files with no integrity errors or unarchived artifacts. These integrity checks support the recorded result; they do not independently calibrate adjudication or establish longer-time strength.

Evidence under `engines/rfp-validation/`: `terminal-extraction.json`, `terminal-audit-01/result.json`, `live-watch-01/state.json`, `runner-exit.json` and `live-watch-01/terminal-snapshot/`. The terminal log SHA-256 is `be9cac475882b2c3dfba68c7591203b46db7128f150fbed40f65f39191eb8c7f`; PGN SHA-256 is `26439b23eb932e0c1b105e0538b2e1ed9ffc3efeeaf85070cbbe3b28a582cfca`. The original candidate, tests and result log are preserved in [commit e6fee6f](https://github.com/LupeHiguera/ChessSI/commit/e6fee6f) on `astra/rfp-shallow`, explicitly STC-only and unpromoted.

## Evidence and next decision

A [compact, reviewable evidence bundle](evidence/rfp/README.md) now includes complete candidate and isolated-optimization patches, the regression test, per-file hashes, six timing pairs, and the three move-disagreement histories/results. Both patches were applied in sequence to a separate copy of the accepted baseline and reconstructed all 22 listed source/build/test files byte for byte. They are stored as unapplied evidence artifacts; the research review branch engine remains the accepted baseline. Full local archives remain available as described below.

Local evidence is under ignored `engines/rfp-validation/`: `launch-plan.json`, `candidate.patch`, `release-tests-tail.txt`, `sanitizer-tests.txt`, `bench.txt`, `sprt-stc.log`, and the completed guard's `live-watch-01/`. The source archive `source-snapshot-01/` verified 34 files with no integrity errors or findings. It includes engine sources, tests, instructions, claim, launch settings, binaries and the observed manager executable. As with all snapshots, source capture itself does not prove source-to-binary correspondence; the forced builds, recorded commands and hashes provide the surrounding evidence.

The previous match's original `config.json`, PGN, binaries and baseline source were moved into `engines/qsearch-validation/original-run-files/` before the runner reused their paths. Its independent terminal snapshot and audit remain intact.

The terminal decision and independent audit are complete. The next strength test must use the then-current accepted main and fresh statistics; the old-baseline pass does not transfer to it. A fresh STC pass would still require independent longer-time confirmation. The original source, binaries and completed-run evidence remain preserved.

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

## Paired root-budget behavior and move references

A further predeclared diagnostic compared all 128 frozen development roots at `go nodes 131072`, preserving full game histories and clearing the TT before each independent search. Existing exact RFP traces were reused. The accepted baseline was run both unchanged and with a final-node counter; every completed iteration's score, bounds, node count, PV and best move matched between those builds, and the counter build retained bench `20648203`. All replayed histories, PVs and chosen moves were legal. Node caps are requested budgets, not equal CPU time.

| RFP completed depth versus baseline | Roots | Same chosen move | Different chosen move |
| --- | ---: | ---: | ---: |
| Lower | 1 | 1 | 0 |
| Equal | 104 | 103 | 1 |
| Higher | 23 | 21 | 2 |

RFP completed one extra ply on 22 roots and two extra plies on one; it completed one fewer ply on one. The median completed depth was five for both engines. Chosen moves agreed on 125/128 roots. Baseline visits totaled 16,777,278 versus 16,777,263 for RFP; the engine's existing polling behavior produced one-node overshoots on 62 and 47 roots respectively. The fraction of visits after the last completed iteration was 40.89% for baseline and 42.06% for RFP. These visits are not automatically wasted or recoverable by a different time policy, and a deeper completed iteration is not a move-quality measurement.

### Reference every differing move

All three move disagreements were selected before reference queries, with no score filter. Each alternative received independent Stockfish 19 forced-root searches at 262,144 and 1,048,576 requested nodes, fresh TT and the complete recorded game history. Choice order alternated by case and budget. The checksum-verified universal binary used its embedded `nn-1a298aa575a0.nnue`, Threads 1, Hash 16, MultiPV 1, `NumaPolicy=none`, no strength limit, and CPU 19. All process/thread affinities and PV legality checks passed. No root or chosen child had an automatic termination, twofold/threefold repetition or claimable repetition/fifty-move draw under the recorded history.

| Source game | Baseline choice | RFP choice | Extra completed depth | Reference difference at 262,144 nodes | At 1,048,576 nodes |
| --- | --- | --- | ---: | ---: | ---: |
| 1324 | `c3d5` | `c3b5` | +1 | -16 cp | -12 cp |
| 1487 | `f6g6` | `f6e5` | 0 | +10 cp | +64 cp |
| 1098 | `c7f4` | `a6b4` | +1 | -52 cp | -86 cp |

Differences are the reference score for RFP's choice minus the reference score for the baseline choice, from the root player's perspective. All pairs were CP comparisons; no mate-to-CP conversion was made. The two deeper RFP choices were less favored by this reference, while the equal-depth choice was more favored. The sign persisted across both budgets. This is a selected three-case diagnostic, not evidence of a general preference, causal attribution to a particular cutoff, or an Elo effect. Reference scores are the last unbounded operational UCI scores, not guaranteed completed-depth evaluations or chess truth.

The twelve reference queries requested 7,864,320 nodes and reported 7,866,947. No label-pilot data were added. The live match source, binaries and settings remained unchanged.

Evidence: `engines/rfp-validation/root-budget-01/` and `root-reference-01/`, including plans, complete transcripts, exact comparisons and all three histories. Collectors: `compare_root_budget.py`, SHA-256 `c09a748f95dfb9c0fd521764d845e8857cf6150ee29c8e42248658d75431ae9a`; `reference_root_choices.py`, SHA-256 `a97257feb0cecde16c4cb96c63c08466db6461065a79d35af32836b30857eb8f`. No candidate parameter or selection threshold was changed after seeing these outcomes.

### Matched-depth control for the three choices

A final mechanism check gave both engines enough budget to complete the larger of their previously observed depths in each of the same three cases, with a 1,048,576-node cap per call. Full histories and fresh TT were retained. All earlier completed iterations exactly reproduced their frozen traces, and all six queries completed the target depth with legal PVs.

| Source game | Matched depth | Baseline move | RFP move | Baseline nodes | RFP nodes |
| --- | ---: | --- | --- | ---: | ---: |
| 1324 | 6 | `c3b5` | `c3b5` | 182,324 | 97,300 |
| 1487 | 4 | `f6g6` | `f6e5` | 72,625 | 34,795 |
| 1098 | 5 | `a6b4` | `a6b4` | 140,467 | 129,596 |

For both cases with a deeper completed RFP iteration, the baseline selected the same move when it reached that depth. This supports an extra-completed-iteration explanation for those particular move changes. The equal-depth case retained its move disagreement. These observations separate two mechanisms behind a changed choice while leaving the strength question to the match. The earlier reference preferences still apply to the selected moves; reaching them through an additional iteration does not guarantee higher reference value.

The six calls reported 657,107 visits. Evidence: `engines/rfp-validation/choice-depth-control-01/`; collector `control_choice_depth.py`, SHA-256 `697037eec7ed48db2dc279339f8578218926309830c07d8c6149f85186b1226e`. This was a bounded follow-up on the same three development cases, with no candidate edits or parameter tuning.

## Isolated optimization: first-pawn legal witness

An implementation-only variant tries the generator's exact first ordinary pawn push before constructing the full move list in `first_legal_move()`. The bitboard expression, exclusion of promotion-rank pawns and least-significant-target ordering match the existing generator. A legal push is returned immediately; an illegal push is undone and the original routine runs. With no such push, the original routine runs directly. Thus the intended invariant is the exact first legal move, including the search's fallback choice, rather than only a legal-move existence test. This is a Known optimization technique, not a new search heuristic.

The variant lives only in `engines/rfp-validation/first-pawn-witness-01/`. It retains all RFP conditions and margins. The completed original match used the original candidate throughout.

Validation passed: 35 perft cases, 15 RFP boundary cases, the same 15 cases with AddressSanitizer/UBSan, and an additional sanitizer-enabled comparison on 2,203 positions. Those positions combine the existing check-evasion corpus, all 128 development roots, the RFP stalemate/escape controls and constructed pawn-edge fixtures with color mirrors. The fast routine returned exactly the same first move as complete generation, agreed with independent python-chess legality, and restored FEN, key and draw state. All 128 full-history search traces matched the frozen candidate's iteration scores, bounds, nodes, PVs and final move. Bench remained `11112214`.

After one warmup per binary, six paired benchmarks alternated execution order on CPU 19 while the five-game match continued:

| Pair | Original search time | Variant search time |
| --- | ---: | ---: |
| 1 | 1,194 ms | 1,189 ms |
| 2 | 1,193 ms | 1,135 ms |
| 3 | 1,241 ms | 1,158 ms |
| 4 | 1,213 ms | 1,128 ms |
| 5 | 1,258 ms | 1,146 ms |
| 6 | 1,196 ms | 1,183 ms |

The median changed from 1,204.5 to 1,152 ms, a 4.36% reduction, with the variant faster in all six pairs. This is a short local timing observation under concurrent load. It establishes neither an Elo gain nor a general speed guarantee. The implementation remains unpromoted and would require testing as part of the complete candidate under the repository protocol.

The first diagnostic attempt passed the engine tests, then python-chess rejected a constructed diagonal-pin fixture because its white rook on h1 also checked the black king on h8 while White was to move. Moving that king to a8 corrected the fixture while retaining the intended pin. The original generator, failure explanation and corrected inputs are preserved. The remaining checks resumed against the unchanged build; already completed tests were not needlessly repeated. `reproduction.json` distinguishes the corrected setup script from the initially executed generator and the successful resume script.

Variant source SHA-256: `c90b8528db3c61597054eb672cc5766405c73dce4ffb0ce1f0837437b784a26f`. Binary: `f8a903d6acda4b6ad860c4f2138151a9ab5274779380199a148800b32e7207be`. Successful continuation script `resume_first_pawn_witness.py`: `afc3a465c271ee8a1e500e9fc39862d1f04e9844da73a12f0fd6c7b8ee8132d3`. The archive retains the patch, plan, all test/build logs, input positions, exact search comparisons, warmups and raw timing pairs.

## Does the positive control change ordinary root search?

A follow-up kept both known one-legal-move fixtures and their legal predecessor positions, without an outcome filter. Baseline, frozen RFP and an isolated observer each searched all four full-history roots to depth 8 with a 262,144-node cap per call and fresh TT. The observer reused the validated shadow auditor, replacing its random gate with the two exact fixture keys and allowing at most 32 samples per root. No search window or node counter was forced in these ordinary searches.

All twelve calls completed depth 8. At every completed depth, baseline and RFP returned the same score; their final moves matched. The observer exactly matched the frozen candidate's iteration scores, bounds, nodes, PVs and final moves, and retained bench `11112214`.

| Root | Baseline depth-8 nodes | RFP depth-8 nodes | Final move | Final score, side to move |
| --- | ---: | ---: | --- | ---: |
| White fixture predecessor, Black to move | 167,005 | 65,790 | `c3e5` | +284 cp |
| White one-legal-move position | 34,091 | 15,511 | `a1a2` | -167 cp |
| Color-mirrored predecessor, White to move | 123,718 | 48,435 | `c6e4` | +284 cp |
| Black one-legal-move position | 20,765 | 10,108 | `a8a7` | -167 cp |

The observer encountered four target cutoffs naturally: depths 1 and 2 after `h7h8`, and the mirrored paths. Each used beta **-168**, static evaluation +182, and a completed RFP-disabled result of **-51**. That result still exceeds the operative threshold, so these four cutoffs were not contradictions. The earlier deliberately constructed beta **+1** call remains a valid contradiction. A large static-versus-search difference is therefore insufficient to label the pruning decision wrong; the actual window matters. This is a concrete development example for a future bound-aware diagnostic target, not evidence that a new controller improves play.

The tactical trace also clarifies the score gap. At the original white-to-move position there are no legal captures, so baseline qsearch returns its +182 stand-pat evaluation. The sole legal move `Ka2` gives Black a qsearch result of +51, or -51 for White. The legal `...Bxb2 Kxb2` exchange preserves that qsearch value; remaining bishop captures of pawns also contribute, so the entire drop should not be attributed to the rook exchange alone. The mirror reproduces the same scores. All traced positions are outside check, each move was independently validated, and FEN/key/draw state was restored. This traces the existing baseline's operational evaluation, not a proven chess value or a diagnosis that removes its other known limitations.

The twelve root calls used 625,267 visits, including the repeated observer runs. The four disabled/control pairs added 66/4 visits; eight qsearch trace calls added 32. The observer bench was an additional 11,112,214 visits. These constructed, selected cases cannot establish a population error rate, general safety or Elo. The live match and candidate remained unchanged.

Complete inputs, iterations, sampled windows, node accounting and exchange observations are in the [reviewable evidence bundle](evidence/rfp/README.md). Full local transcripts and builds are under `engines/rfp-validation/counterexample-root-01/` and `counterexample-qtrace-01/`. Collectors: `trace_counterexample_root.py`, SHA-256 `d37c7186c4d36677baefec8d4eb23aded03ebcfcfb022e23d2d5da9e4422c891`; `trace_counterexample_qsearch.py`, SHA-256 `3e31799c2b51bd4174c3eea2d5fe7db496f8d41dd40085613c79e5d5fa94a8e2`. GPT-6 (Codex) designed and ran these diagnostics on CPU 19.

## Stress the existing margin at its eligibility boundary

A second bounded audit manufactured null windows at `beta = staticEval - 150 * depth`, `alpha = beta - 1`, for depths 1-3 on every one of the same 128 development roots. This fixes threshold surplus to zero while leaving the candidate's margin unchanged. Each private non-root call used ply 1, full recorded game history and a fresh TT. These are counterfactual windows, not windows observed during ordinary play. The two existing constructed controls were included and counted separately.

| Depth | Development roots | Eligible / completed | Contradictions | Baseline visits |
| --- | ---: | ---: | ---: | ---: |
| 1 | 128 | 116 / 116 | 0 | 1,119 |
| 2 | 128 | 116 / 116 | 0 | 4,019 |
| 3 | 128 | 116 / 116 | 0 | 19,298 |

At every depth, twelve roots were excluded by existing gates: five in check, six with only pawns and king, and one drawn under the engine's rule. All excluded records were retained. The candidate returned its static score in exactly one visit for all 348 eligible development calls. The baseline completed every comparison within the 131,072-node allowance, and none returned below the manufactured beta. This is a bounded negative result on reused, deliberately selected development inputs, not a population failure-rate estimate or validation of the evaluation/search implementation.

Both constructed controls failed at depth 1 as expected: their static score +182 gives manufactured beta +32, while the accepted baseline returns below that threshold. They did not contradict the more permissive depth-2 or depth-3 windows. This verifies that the probe can detect the known failure mode without asserting that the development roots represent rare tactical cases. All legal witnesses were checked against python-chess, full-history replay matched the recorded FENs, both probes agreed on eligibility, and state restoration passed.

Across development cases and controls, baseline searches used 24,635 visits and candidate searches used 354. No threshold was swept or changed, and no learned guard was fitted. Together with the earlier sampled-node audits, this small reused corpus has not supplied naturally occurring contradictions from which to establish a useful predictor. Further controller claims need independently collected relevant cases and the previously specified controls; widening gates until an attractive signal appears would change the question.

Evidence: `engines/rfp-validation/threshold-stress-01/`, retaining the pre-query plan, all 130 complete inputs, all 780 probe records including exclusions, source copies, builds, outputs and summaries. Collector `stress_threshold.py`, SHA-256 `231b071c21788e61fe63d615506561f798e3ce52f728fb5cb734a96ceaa662b1`. GPT-6 (Codex) ran this audit on CPU 19 without changing the live candidate, its margin or the match.

## Conditional longer-time confirmation preparation

Before the STC decision, a read-only preflight recorded the intended independent confirmation: the exact same candidate and accepted baseline, `TC=60+0.6`, normalized SPRT `[0,5]`, alpha/beta 0.05, 100,000-pair cap, shared book, CPUs 14-19 and concurrency 5. The existing 19:53 UTC research deadline remains in force. A fresh manager invocation must use fresh statistics and record its newly generated opening seed; the isolated first-pawn optimization is excluded from this confirmation.

The preflight checked all 22 source/build/test inputs against the published candidate manifest, both engine binaries, Fastchess and the shared book. It also checked the Astra branch and ancestry against the unchanged accepted baseline. Its live-process observation correctly kept the launch gate closed while the STC manager was running. It neither starts matches nor moves files.

After an explicit H1 result, the terminal archive, candidate/baseline identities, protocol, normal runner exit and independent PGN/count audit must all reconcile before launch. Re-fetch current main and rerun the preflight into a new directory; if main moved, rebase and retest the changed comparison rather than relabeling the old result. Preserve the completed STC outputs before the standard runner writes fresh files, force a rebuild, verify binary/bench identities, then attach the existing identity-checked deadline guard to the new manager. A missing LTC decision at the deadline stays Inconclusive even if STC passed.

No LTC confirmation started. Versions `confirmation-preflight-01` through `-03` are retained as historical records. Manual review identified incomplete protocol/provenance bindings, corrected before use as described in the [terminal-check review](testing.md#review-of-terminal-audit-and-confirmation-readiness). After the audited H1 result, `confirmation-preflight-04/preflight.json` at 16:18 UTC found no active manager and no remaining terminal-evidence wait, but correctly refused launch because accepted main and its local tracking reference differed from the original baseline. It binds the earlier launch/process/config observations and the revised independent audit schema. Helper `prepare_confirmation.py` SHA-256: `b3010849d5271620f4498f2a071c839f7a429591bbf4336a39c1c948be74a5b9`. Nineteen focused regression checks passed. The actual post-H1 refusal path was exercised; no eligible LTC launch has been exercised.


## Accepted main advanced during the run

A fresh remote check at approximately 15:57 UTC found accepted main `f801f8c519b0fe5b3d009b8f0664b049409a1188`, merging Claude's killer moves, null-move pruning and late move reductions. The completed original RFP comparison remained frozen against `a8eebea`; its STC pass is attributed only to that comparison. The new main changes pruning and reduction contexts, so an old-baseline STC pass cannot substitute for a fresh test on it. [Accepted merge](https://github.com/LupeHiguera/ChessSI/commit/f801f8c519b0fe5b3d009b8f0664b049409a1188)

The read-only confirmation preflight first rejected the obsolete baseline while waiting for the manager, and continued to reject it after the terminal audit. Under `AGENTS.md`, the next strength test must rebase onto the then-current main and begin a new comparison, with its own validation, signatures and evidence. No old statistics will be carried over. The original experiment is now audited and logged as STC Passed on its original baseline; the 19:53 UTC deadline remains unchanged.

An isolated copy of the newly accepted main passed all 35 perft cases and reproduced bench `864538`. Compilation and bench were explicitly pinned to CPU 19; the perft recipe inherited the prescribed make affinity, CPUs 14-19. All stayed within the assigned allocation. Its binary SHA-256 is `819333c372d911c46c341091ed46f0872753b18d5dd39c094383139598e1f8da`. This only verifies the accepted baseline; it is not another RFP test or a strength claim. Evidence: `engines/rfp-validation/new-main-preparation-01/`, collector `prepare_new_main.py` SHA-256 `ef39de711210912dbc00ea92c23c8be2bbad40c9f4b6f06100b59ec1d3d0e1f6`.

The separate research review branch incorporates the new accepted main while preserving both agents' log rows and RFP queue ownership. Its engine files match main; the tested RFP patch remains an unapplied historical evidence artifact. The live worktree and binaries were not changed.

A second live-prefix integrity audit at 15:44 UTC legally replayed 1,272 saved games and 126,041 plies, reconciled all 63 statistics reports and every saved game result, and found no missing cross-source games or suspect terminations. `engines/rfp-validation/match-audit-02/` preserves the frozen snapshot and audit. This is a prefix integrity check, not the eventual terminal result.

### Isolated RFP preparation on the new accepted main

An isolated candidate on `f801f8c519b0fe5b3d009b8f0664b049409a1188` passed **35 perft cases, 17 boundary cases and the same 17 cases under AddressSanitizer/UBSan**. Candidate bench is **609035**, against the new baseline's **864538**. The RFP block retains the same predicates and 150-cp-per-ply margin, sits after TT exits and before null-move pruning, and allows eligible reduced-depth calls and null descendants. The two added boundary cases cover a real predecessor and a null-then-real predecessor with populated move-stack entries. No first-pawn shortcut, evaluation caching, NMP/LMR tuning or draw/position repair is bundled.

The isolated candidate binary SHA-256 is `b10c68c9870eb589b89ccab8d860cdeed91aeeddcff1618ecfa37aff35f6a6ab`; patch SHA-256 is `e914b1d4b932993238fb4a3c7112ab03b314dedafdd2a96c8c63d155f26c737e`. Source, plan, build/test logs and results are under `engines/rfp-validation/new-main-preparation-01/rfp-candidate/`. Remote main still matched `f801f8c` at **16:17:43 UTC**, recorded in `main-check.json`. The original live inputs and isolated baseline were unchanged.

This is preparation only: no new-baseline match has started in this record. Before launch, recheck accepted main, move to the properly rebased experiment branch, perform the required branch validation and freeze a new run identity. Fresh STC and any subsequent LTC are separate comparisons with no inherited games or statistics. The local checks establish the specified behavior, not pruning safety or a gain.


## Fresh STC comparison on updated main

After the original manager and deadline guard completed and its terminal result was audited, seven old output paths were moved into `engines/rfp-validation/original-run-files/`. Resolved source and destination paths were checked to remain inside the Astra workspace; files were rehashed after moving. The exact old candidate is also preserved in commit `e6fee6f` on `astra/rfp-shallow`. No old match statistics were reused.

The next experiment branch, `astra/rfp-current-main`, starts from accepted main `f801f8c519b0fe5b3d009b8f0664b049409a1188`. Commit `d1de9d0314cf9b18ae27bb3d61237dd1df57cb05` records the retained idea claim before applying the candidate. The branch's forced `taskset -c 14-19 make -j6 -B test` then passed all 35 perft and 17 boundary cases. Its release binary exactly matched the separately validated candidate; the unchanged isolated 17-case sanitizer result remains applicable to those identical inputs.

Remote main was rechecked at **16:26:36 UTC**. The fresh launcher recorded its plan at **16:26:41.927354 UTC**, and the standard `scripts/sprt.sh` runner rebuilt both sides and reproduced candidate/base benches **609035 / 864538**. This is another STC test, not LTC. It retains `10+0.1`, normalized SPRT `[0,5]`, alpha/beta 0.05, 100,000-pair cap, Hash 16, Threads 1, unchanged adjudication, the shared book, CPUs 14-19 and concurrency 5. No prescreen or first-pawn optimization is included.

| New-run identity | Value |
| --- | --- |
| Candidate binary SHA-256 | `b10c68c9870eb589b89ccab8d860cdeed91aeeddcff1618ecfa37aff35f6a6ab` |
| Baseline binary SHA-256 | `819333c372d911c46c341091ed46f0872753b18d5dd39c094383139598e1f8da` |
| Candidate search SHA-256 | `a13807cdfa9e1ced5d66f948ae70245386344634e88d1c7801603991d3f2cc84` |
| Manager PID / start ticks | `2319846` / `4928613` |
| New opening seed | `6676192773240996276` |
| Original-trial opening seed | `2695864851825789344` |

The verified deadline guard attached at **16:27:07.947761 UTC** and retains the fixed **19:53 UTC / 12:53 PM Arizona** cutoff. The manager and all ten engine processes were observed inside CPUs 14-19; the watcher uses CPU 19. The source/process snapshot verified all 34 archived files with no findings, including a near-launch book-path/digest observation. The first frozen configuration confirms the intended settings and distinct seed. Its independent PGN audit legally replayed 33 games and 3,321 plies, reconciled the first statistics report and every saved result, and found no missing cross-source games or suspect terminations.

All new-run evidence is separated under `engines/rfp-current-main-validation/`: launch/guard plans, source snapshot, process audit, first protocol/match audit, runner log and subsequent terminal records. The candidate and its test inputs are now frozen. No strength verdict exists for this comparison. An STC winner still needs independent 60+0.6 confirmation; no decision by the deadline remains Inconclusive.

The new-baseline confirmation preflight is prepared and passed 27 focused checks. Its actual live observation at 16:45 UTC correctly waits for this STC to finish and for a fresh accepted-main check. No eligible H1 launch path or LTC match has occurred. [Preparation and evidence](testing.md#updated-main-confirmation-preparation).

## Context-preserving shadow audit on updated main

A single frozen audit completed at **17:09:27 UTC on 2026-10-22**, using CPU 19 and the same **128 development roots** as the earlier audits. The candidate was the unchanged new-main RFP engine identified above, bench **609035**. Each parent search requested 131,072 nodes. The existing deterministic 1/256 hash gate selected at most eight legal static cutoffs per root; each selected node received an RFP-disabled subtree probe and an RFP-enabled control, with 131,072 requested additional nodes each. No replacement sample or wider gate was used.

The observer recorded **1,278,266 threshold-triggered returns**, including returns of zero when the legal-move check finds stalemate. These aggregate counters are not a count of sampled legal static cutoffs: 449,909 occurred on incoming LMR-reduced calls, 47,834 beneath a null move, and 13,681 in both contexts. Among legal cutoffs, 5,076 passed the hash gate; the per-root cap retained **979 samples from 126 roots and 99 openings**. Of the 128 roots, 119 reached the eight-sample cap.

| Selected context | Samples | Completed | Censored | Disabled score below original beta |
| --- | ---: | ---: | ---: | ---: |
| All selected legal static cutoffs | 979 | 979 | 0 | 0 |
| Incoming LMR-reduced call | 267 | 267 | 0 | 0 |
| Null descendant | 19 | 19 | 0 | 0 |
| Both reduced and null descendant | 4 | 4 | 0 | 0 |

The context rows overlap. Depths 1, 2 and 3 contributed 890, 68 and 21 samples respectively; the 19 null-descendant samples came from nine roots. There were 977 samples with nonzero killer payloads. All enabled controls reproduced the original static return in one visit. Both constructed contradiction controls still returned static +182 versus disabled -50; the predecessor control also distinguished preserved NMP state (score 545, two visits) from an erased predecessor (511, ten visits). These controls check that the observer can detect specified state loss and cross-beta behavior.

Separate Position-bound probes copied complete semantic board/history state, including the repetition boundary after null moves, killers, move-stack entries and initialized PV prefixes. They preserved the polling phase, restored the original TT before each control and parent continuation, and never reset the global stop flag. Incoming reduction tags were reset before full-depth re-searches. Typed path replay distinguished null edges from legal real moves and preserved ChessSI's fullmove-counter convention for null moves.

Independent read-only verification reconciled **all 384 transcripts** with the saved records and replayed **72,046 real plies plus 19 typed null edges** across the sample paths. Every root's completed iteration depths, scores, bounds, node counts, PVs and final move agreed across the frozen candidate, reference and observer; the reference and observer also matched final node counts, including interrupted iterations. Timing and NPS fields were excluded from this equivalence check. The frozen production UCI does not expose final partial-search counts. All archived validation-file/binary hashes and the 21 live launch-input hashes matched.

The reference and observer each used **16,777,305 parent visits**, 89 above their respective aggregate requested cap of 16,777,216; the largest per-root overshoot was three. Disabled probes used **4,844 visits** in total, at most 164 each; enabled controls used **979**. The three parent passes requested 50,331,648 nodes. Preparation controls and bench runs are additional work, and visit counts do not measure TT-copy or replay overhead.

The immutable plan's initial roots digest omitted one hexadecimal digit; a separate pre-query correction preserves that typo and binds the unchanged corpus. Before collection, review tightened the 21-input provenance binding, verified-byte helper loading, Python optimization rejection, monotonic per-root timeout, failed-transcript retention and source-versus-clone NMP control. Attempt 01 remains preserved. Attempt 02's first launch lacked the local dependency path and queried zero roots; its empty-launch record was retained before an authorized environment-only retry using the existing python-chess 1.11.2. The collector, binaries, corpus and gates were unchanged for that retry.

Evidence is retained under `engines/rfp-current-main-validation/shadow-context-01/attempt-02/`, including `validation.json`, `launch-retry-metadata.json`, `corpus-launch-failure-01/` and `corpus/` with all samples, transcripts and summaries. Identity checks:

| Artifact | SHA-256 |
| --- | --- |
| Collector | `496b5ad47703e6c6a41c98ce5e4eaccd100e809d70099bb9c27f61c63caf8f11` |
| Reused roots | `8a197269535824b8d6dedd978cec7988e7ec94ec3eaaa3bb3e2f7ba4ec9db505` |
| Observer binary | `dfffaa3245e3a9fd262b9a2720eb614d4922786417228fd7439deff277ed9d17` |
| Corpus result | `91fe93df2a354230cec4789ad98b4c88b4e1e0d6330a0c428052fb3a996f0b3c` |
| Selected samples | `d597725d98685a53bf221fd528b2342200fc870e69056a1581ada856f33ff362` |

This bounded audit found no cross-beta return among its completed selected probes. The inherited warm TT may contain RFP-influenced bounds, and NMP, LMR, evaluation, quiescence and draw handling remain approximate. Reused development roots, visit caps and sparse null-context coverage prevent a population error-rate or safety conclusion. The result supplies no Elo evidence and does not replace the separate strength test.
