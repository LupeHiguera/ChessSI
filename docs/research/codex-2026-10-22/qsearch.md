# Quiescence check-evasion experiment

Proposer and implementer: GPT-6 (Codex). Kind: Known. Started 2026-10-21 at approximately 22:47 America/Phoenix (2026-10-22 UTC). Status: full short-time-control SPRT running; no Elo gain or acceptance is claimed.

## Hypothesis and minimal change

After a capture gives check, the baseline quiescence search can use static evaluation as stand-pat and omit every quiet legal evasion. Suppressing stand-pat in check, searching all evasions and returning mate when none are legal should correct those tactical scores. The strength test measures whether the additional search is worth its cost at the specified time control.

The patch retains the existing maximum-ply fallback and changes no evaluation constants, normal-search pruning, draw handling, time management, benchmark positions or benchmark depth. Quiescence draw handling remains a separate issue.

## Correctness evidence

The first compiled baseline regression run reproduced six failures and one passing quiet-position control. After the fix, all seven passed. A further narrow-window mate case was added to directly detect an incorrect stand-pat cutoff; all eight final cases passed. Each case also checks that the position FEN and Zobrist key are restored after search.

| Case | Required behavior |
| --- | --- |
| Already checkmated, root ply | Return `-32000` |
| Already checkmated, ply seven | Return `-31993` |
| Mate with beta below static evaluation | Still return mate, not a false stand-pat cutoff |
| Only legal evasion is `Kh8g8` | Search the quiet king move |
| Same evasion under a narrow window | Search it even when old static evaluation exceeds beta |
| `Rxh7+` followed by only `Kg8` | Include the quiet evasion below the normal horizon |
| `Qxh7#` in quiescence | Return `31999` |
| Quiet starting position | Preserve stand-pat and one-node behavior |

`make test` passed all 35 perft cases and the then-seven search cases. The final eighth case passed in `make test-search`. AddressSanitizer and UndefinedBehaviorSanitizer passed the seven-case suite before the eighth test-only addition. The engine code was unchanged by that test addition.

Baseline bench: `20648203`. Candidate bench: `22824107`. A changed search signature is expected for this change. The tested `./chesssi` executable and the match's `engines/new` executable have identical SHA-256 hashes.

## Frozen match identity

| Field | Value |
| --- | --- |
| Branch | `astra/qsearch-check-evasions` |
| Candidate starting HEAD | `90e172cc010f3ca6121e8f4c975138590729322b`, plus archived working-tree patch |
| Accepted baseline | `a8eebea2e6ec78d223745d7ee64fe8b0dd777325` |
| Candidate SHA-256 | `17415917fc9c0ddd8afd4df57b121a5eade929f7d2418b9269fab69e901d1563` |
| Baseline SHA-256 | `b55b4dac011664fe03f068b31ef7868e7413d064338b2d0b6eb3a0001e21520b` |
| Compiler | `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` |
| Release flags | `-std=c++20 -O3 -march=native -DNDEBUG -Wall -Wextra`, linked with `-pthread` |
| Manager SHA-256 | `3d0a8f3c8b837a96366ac838f3ddf6fe87b813abb4ad2852284c0ce409132566` |
| Book SHA-256 | `7a7f6470615a69c6cf23d565417701d38732876f480af90d67b42abade35644a` |
| Book size | `174889110` bytes |
| Random seed, exact decimal | `14069920903512239839` |
| Time control | `10+0.1` |
| SPRT | Normalized Elo model, `[0,5]`, alpha/beta `0.05`, boundaries approximately `[-2.94,+2.94]` |
| Concurrency / affinity | Five games, WSL guest CPUs `14-19`; manager and all ten engine processes verified |
| Engine options | Hash `16` MB, Threads `1` |
| Openings | Shared UHO book, randomized and paired with reversed colors |
| Resignation | Both engines agree, `400` cp for `3` moves |
| Draw adjudication | From move `40`, within `10` cp for `8` moves |
| Maximum | `100000` pairs; incomplete if the research window ends first |

The initial launcher failed before building engines or playing games because the Windows worktree `.git` pointer was not a Linux path. The successful launch supplied `GIT_DIR=/mnt/c/Users/Lupe/CLionProjects/ChessSI/.git/worktrees/ChessSI-astra` and `GIT_WORK_TREE=$PWD` to WSL Git. No shared metadata was rewritten.

## Local evidence

These generated artifacts are intentionally under ignored `engines/` and remain in the Astra worktree:

- `engines/qsearch-validation/baseline-regressions.txt`
- `engines/qsearch-validation/fixed-tests.txt`
- `engines/qsearch-validation/fixed-search-tests.txt`
- `engines/qsearch-validation/sanitizers.txt`
- `engines/qsearch-validation/bench.txt`
- `engines/qsearch-validation/candidate.patch` and `search.cpp`
- `engines/qsearch-validation/launch-path-error.txt`
- `engines/qsearch-validation/sprt-stc.log`
- `engines/qsearch-validation/initial-snapshot/manifest.json`

The initial snapshot verified 37 archived files and recorded a whole-file hash for the shared book without copying it. The process executable hashes matched the frozen binary paths. Snapshot integrity establishes which bytes were captured; it does not establish a strength result. Preserve a final snapshot and the manager's completed verdict before filling the benchmark log.
## Cost diagnostic while the strength test runs

On 2026-10-22 UTC, a separate diagnostic used only WSL CPU 19 while the five-game match continued. The release binaries were hash-checked before and after. Each received one warm-up and six measured runs of the unchanged official depth-seven benchmark, alternating base/candidate and candidate/base order. These timings describe this shared-load environment; they are not a strength result or an isolated-machine speed estimate.

| Measure | Baseline | Candidate |
| --- | --- | --- |
| Nodes, every run | 20,648,203 | 22,824,107 |
| Median search time | 2,113.5 ms | 2,541.0 ms |
| Median nodes/second | 9,765,576.5 | 8,978,811.0 |

The candidate searched 10.54% more nodes, took 20.23% longer and had 8.06% lower median throughput. Both tree size and cost per node contribute. A separate instrumented executable retained the candidate bench signature `22824107` and counted:

- 20,130,872 quiescence nodes, of which 11,186,162 entered directly from normal search.
- 935,713 checked quiescence nodes (4.65% of quiescence nodes).
- 335,296 searched quiet evasions and 2,860 quiescence checkmates.
- Maximum quiescence ply 30; no maximum-ply fallbacks in these 14 positions.

Normal search computes check status before calling quiescence, which then computes it again. Thus 55.57% of these quiescence calls repeat an existing check-status query. A possible follow-up is to pass that known value into quiescence and compute it for recursive children. This is an untested implementation variant of the same correction, not an explanation established by the counts alone. Its fixed-depth nodes and scores must match the corrected engine, and the complete candidate still needs its own strength test. Do not assume the passed value is always false: future reductions can enter quiescence at negative depth while checked.

The instrumentation changed no match source or binary. Its timings are not used for the release comparison. Reproduction script: `engines/qsearch-validation/profile_current.py`; plan, raw outputs, compiler command, source/binary hashes and counter totals: `engines/qsearch-validation/profile-01/`. The active SPRT continues to its stopping condition regardless of these diagnostic observations.
## Unattended completion guard

At 2026-10-22 06:48 UTC, a validated local guard was attached to manager PID `300619`, Linux start tick `1370261`, using a pidfd. Guard PID `533502` is pinned to CPU 19; the manager remains on CPUs 14-19. Both were checked live after attachment. The guard's deadline is `2026-10-22T19:53:00+00:00`, corresponding to the user's 12:53 PM America/Phoenix deadline.

If the manager finishes first, the guard archives the terminal artifacts without sending a signal. Otherwise it verifies process identity, requests SIGINT at the deadline, waits up to 60 seconds for termination, and captures either a terminal or explicitly live snapshot. It neither resumes the test nor decides its statistical verdict. State and archives are under `engines/qsearch-validation/live-watch-01/`; the guard's output is `engines/qsearch-validation/live-watch-01.log`.

Before changing the binaries, PGN, configuration or source for a subsequent experiment, inspect this guard's final state and archive. An interrupted run without a completed SPRT decision is Inconclusive. See the lifecycle and resume fixtures in [testing research](testing.md) for the measured difference between completed PGN games and persisted paired-game counts.
## Prepared implementation variant: reuse known check status

The cost diagnostic motivated one isolated implementation variant of idea 9. It passes the existing `inCheck` value from normal search into quiescence, and computes child check status after each legal recursive quiescence move. It does not assume that normal-search entry is always unchecked. The live candidate source and match binaries were retained unchanged.

The plan was written before building or timing the variant. The first diagnostic build put the replacement translation unit last in the compiler command. Its correctness checks passed, but the link order could confound a small timing comparison. That build remains in `known-check-01/`; it was not used for the paired speed result. The controlled build in `known-check-02/` restored the original source order. A parent rebuild using that procedure was byte-identical to the live candidate, SHA-256 `17415917fc9c0ddd8afd4df57b121a5eade929f7d2418b9269fab69e901d1563`.

The controlled variant passed all eight quiescence regressions, all 35 perft cases, and the eight-case ASan/UBSan run. Its bench remained `22824107`. A UCI comparison with fresh TT state for each of the 14 original benchmark positions found identical scores, bounds, PVs, best moves and node counts at every completed iteration through depth seven. This establishes agreement on those searches, not a universal proof of equivalence.

Six alternating parent/variant timing pairs, following one warm-up per binary, ran on CPU 19 while the original match continued. Median search times were 2,559.5 ms for the parent and 2,525.0 ms for the variant, a 1.35% reduction. Median throughput was 8,913,953 and 9,035,694 nodes/second respectively. Individual paired speed ratios ranged from 0.9635 to 1.0353, including one tie. The small central difference is within the observed timing variation; no confirmed speedup or Elo gain is claimed. Reusing the query did not recover most of the previously measured overall cost.

The prepared variant is not promoted and has no strength-test result. If revisited, test the complete candidate against the then-current accepted baseline and retain this attempt separately. Do not substitute its binary into the running match.

| Artifact | Identity |
| --- | --- |
| Variant source SHA-256 | `fc5ece9eaa9c9d5f1d418c1812b629e2da5eb58e06ca037cd7874bf09fc8eec3` |
| Controlled variant binary SHA-256 | `fd5d3452be76e1bf2e1d448e03ab18aa959b14a285c9dc7f0c0d2043501e6f57` |
| Parent-relative patch | `engines/qsearch-validation/known-check-02/candidate-relative.patch` |
| Build, test and sanitizer records | `engines/qsearch-validation/known-check-02/` |
| Per-position transcripts and raw timings | `engines/qsearch-validation/known-check-02/equivalence-timing/` |

Reproduction scripts are `prepare_known_check_01.py` (initial build), `prepare_known_check.py` (controlled build), and `check_known_check.py` under `engines/qsearch-validation/`. Builds used `taskset -c 14-19 make -j6` with the compiler itself pinned to spare CPU 19. A small WSL filesystem clock-skew warning appeared in the first build; explicit phony targets executed the compiler, and fresh exclusive output directories prevented stale binary reuse.
## Prepared implementation variant: conservative evasion filtering

A second passive cost diagnostic counted 33,222,875 pseudo-legal moves generated at 935,713 checked quiescence nodes. The search attempted 5,990,776 of them: 4,805,338 were illegal and 1,185,438 were legal. Thus 80.21% of attempted evasions were rejected after make/unmake. Checked nodes averaged 6.40 attempted moves and 1.27 legal moves. These counts identify work; they do not assign a runtime cost to it. The instrumented bench remained `22824107`. Records: `engines/qsearch-validation/evasion-profile-01/`.

This motivated a separate implementation variant of idea 9, starting from the original live candidate. It is not combined with check-status reuse. At a checked node, a non-king, non-en-passant move must capture the sole checker or land between that slider and the king. With multiple checkers, such moves are rejected. King moves and en passant always retain the existing full legality test. En passant needs this exception because its destination differs from the captured pawn's square.

The filter runs after the existing selection-sort step. All generated moves, scores and swaps remain in place, preserving the order of surviving moves. Retained candidates still go through `do_move` and its complete king-safety test. The change skips only candidates proven unable to evade check; it does not prune legal evasions. The plan was saved before implementation and measurement.

Validation passed:

- All eight quiescence regressions, all 35 perft cases, and the eight-case ASan/UBSan run.
- A diagnostic build made and unmade every filtered move during the entire original benchmark and asserted that it was illegal. No assertion fired; bench remained `22824107`.
- Independent legal-move comparison with python-chess 1.11.2 on 2,048 distinct checked positions generated by legal random play, plus nine explicit corners. These include mate, a quiet king evasion, rook/bishop interposition, double check, knight-check capture, en-passant capture of the checker, and promotion blocks/captures. Every legal move matched and every legal evasion survived. FEN and Zobrist restoration were checked after each make/unmake.
- Fresh-TT UCI searches agreed with the original candidate on scores, bounds, PVs, best moves and nodes at every completed iteration through depth seven on all 14 unchanged benchmark positions.

The random-position check used seed `20261022`, visited 36,213 positions, and retained the first 2,048 distinct checked board/side/rights/EP states. It is a legality diagnostic, not training data or a strength benchmark. Its independent-reference input digest is `ad2de9be40f1ba4c11aea59c5a87d3248db8fbd22d7521e325e03332f673e0ab`.

On CPU 19 under the existing shared load, six alternating timing pairs followed one warm-up per binary. The parent median was 2,545.5 ms and the filtered variant median was 2,483.0 ms, a 2.46% lower runtime. Median throughput was 8,962,959.5 versus 9,188,543.5 nodes/second. The variant was faster in each pair; paired speed ratios ranged from 1.0103 to 1.0490, with median 1.0330. This is a promising local speed observation, not an Elo result or a universal speed guarantee. It recovers only part of the correction's earlier measured total cost.

The variant remains unpromoted, and the original match continues on its original binary. Any strength claim requires a separately identified complete-candidate SPRT against the then-current accepted baseline.

| Artifact | Identity |
| --- | --- |
| Filtered source SHA-256 | `e7c85a64a41e4b9a7874d2c2b669203031b83466f77be087f7c19d935a0521ad` |
| Filtered binary SHA-256 | `1165243f300f96f3f045602e50357a0b933bcedf468c647805df2836fc83e6df` |
| Parent-relative patch | `engines/qsearch-validation/evasion-filter-01/candidate-relative.patch` |
| Build, regression and oracle-bench evidence | `engines/qsearch-validation/evasion-filter-01/` |
| Independent legality evidence | `engines/qsearch-validation/evasion-filter-01/legal-oracle/` |
| Exact search traces and timing pairs | `engines/qsearch-validation/evasion-filter-01/equivalence-timing/` |

Scripts under `engines/qsearch-validation/`: `profile_evasions.py`, `prepare_evasion_filter.py`, `check_evasion_filter.py`, and `time_evasion_filter.py`. The existing source and `engines/new` hash were checked before and after preparation. This is a Known evasion-generation technique applied as a conservative filter, not a novelty claim.

## Prepared implementation variant: skip the zero-scored tail

A third isolated implementation variant of idea 9 counts nonzero move scores at checked quiescence nodes. Once no nonzero scores remain, the original strict-greater selection loop must choose its current element, so the variant returns that element without rescanning the tail. The unchecked path keeps the original selection behavior. This starts from the original corrected candidate; it is not combined with either previous variant.

An exhaustive fixture compared the actual old and new selection methods on all 488,281 vectors of length zero through eight over scores `{-2,-1,0,1,2}`. It checked every intermediate move array, score array and remaining count, including the unchanged-path sentinel: 7,568,360 mode/prefix checks, zero failures. The variant also passed all eight quiescence regressions, 35 perft cases and eight ASan/UBSan cases. Its bench remained `22824107`; all 14 positions matched the parent at every completed search iteration through depth seven, including scores, bounds, PVs, best moves and nodes.

The speed screen did not justify promotion. Six alternating timing pairs on CPU 19, after one warm-up each, gave median search times of 2,474 ms for the parent and 2,542 ms for the variant: the variant median was 2.75% slower. Median throughput was 9,222,200 versus 8,980,101.5 nodes/second. Individual paired speed ratios ranged from 0.9100 to 1.0315. Their median was 1.0131, pointing in the opposite direction from the ratio of medians. Both summaries are retained: this small shared-load sample is inconsistent, and selecting its favorable summary would overstate the evidence. No reliable speed gain or Elo result is claimed.

The candidate is retained as a negative speed-screen result, not promoted or substituted into the original match. Reproduction scripts are `prepare_quiet_tail.py` and `time_quiet_tail.py` under `engines/qsearch-validation/`. The plan, parent-relative patch, exhaustive fixture, compiler/test logs and raw search/timing outputs are in `quiet-tail-01/`.

| Artifact | Identity |
| --- | --- |
| Variant source SHA-256 | `c6b9e73a5829f797b8c34b47ba30b295782e6d2f788daca7ca8995d13266badd` |
| Variant binary SHA-256 | `1b2f54f1be4518736c0dd4450b9f82dee28883cb1f6b9760555f6e008da7beda` |
| Exhaustive ordering result | `engines/qsearch-validation/quiet-tail-01/ordering.stdout` |
| Search equivalence and timing | `engines/qsearch-validation/quiet-tail-01/equivalence-timing/result.json` |

All three implementation variants were proposed and written by GPT-6 (Codex), are classified Known, and remain local diagnostics of the same claimed quiescence idea. None has a completed strength test. They are recorded separately here so a failed local screen cannot disappear from the research record or become an unearned Elo claim.

## Prepared implementation variant: quiet king escapes first

The evasion-cost profile also motivated a small ordering variant of idea 9. After the original scoring step at checked quiescence nodes, zero-scored king moves receive score 1. Captures and queen promotions retain their larger scores; other quiet moves retain zero. This tests whether searching king escapes before quiet interpositions finds cutoffs sooner. It starts from the original corrected candidate and is not combined with any other prepared variant. Move ordering is Known: Stockfish separately ranks capture and quiet evasions, using history for the latter. This fixed preference is not claimed as a novel method or as Stockfish's rule. [Stockfish move picker](https://github.com/official-stockfish/Stockfish/blob/master/src/movepick.cpp)

The variant passed all eight quiescence regressions, 35 perft cases and eight ASan/UBSan cases. Direct full-window quiescence probes agreed on every score across the existing 2,057 legal checked positions. All probes finished below their 131,072-node cap and restored FEN/key state. Aggregate direct-probe nodes fell from 225,101 to 194,982, a 13.38% reduction on this deliberately checked-position sample.

The full depth-seven benchmark changed from `22824107` to `22730941`, only 0.408% fewer nodes. Changed nodes are expected for a move-ordering change. Fresh-TT UCI traces on all 14 unchanged positions found 44 iterations with different node counts; scores, bounds, PVs and best moves remained identical throughout. This diagnostic shows agreement on those searches, not universal search equivalence. The checked-only sample's larger reduction does not describe general playing workloads.

Six alternating timing pairs on CPU 19 followed one warm-up per binary. Parent median time was 2,556 ms; variant median was 2,524 ms, 1.25% lower. Median throughput was 8,926,127 versus 9,002,387.5 nodes/second. Five pairs were faster and one slower; paired speed ratios ranged from 0.9779 to 1.0441, median 1.0095. The small runtime difference remains an uncertain observation under shared load. No strength test or promotion follows from it, and it recovers little of the original correction's measured overall cost.

A setup check in `king-first-01/` stopped before any build or search because the earlier oracle's input digest referred to the newline-separated FEN stream, not its JSONL wrapper. The controlled attempt in `king-first-02/` checked both scopes: JSONL SHA-256 `8e2dfd3b6ff7d3a44936ba12ac9e2ca68f273da40332ad1f86c1af235e062dc0`, FEN-stream SHA-256 `ad2de9be40f1ba4c11aea59c5a87d3248db8fbd22d7521e325e03332f673e0ab`. The input itself had not changed.

| Artifact | Identity |
| --- | --- |
| Variant source SHA-256 | `0a06fd936716314009e4230f94fafaace9b26cc5783c0b8bc1a3c59249ec2685` |
| Variant binary SHA-256 | `7e11ebb3993e1d0eddddce5cefc79b695561881ab70769d810318d1eb50593bb` |
| Parent-relative patch and validation | `engines/qsearch-validation/king-first-02/` |
| Direct quiescence score/node pairs | `engines/qsearch-validation/king-first-02/direct-q-comparison.json` |
| Root traces and all timing pairs | `engines/qsearch-validation/king-first-02/search-timing/` |
| Combined diagnostic record | `engines/qsearch-validation/king-first-02/final-diagnostic.json` |

Reproduction scripts are `prepare_king_first.py` and `time_king_first.py` under `engines/qsearch-validation/`; the initial setup script is retained as `prepare_king_first_01.py`. Proposer/implementer is GPT-6 (Codex). The active source and binary hashes remained unchanged. These four local variants remain separate attempts with no completed Elo result; none is substituted into the ongoing test.

## Passive profile on ordinary game positions

To check whether the 14-position benchmark hid a different workload, a passive instrumented build searched 128 positions from the independently audited live-game snapshot. The sampling plan was recorded before extraction: use game numbers above 1,000, the ply grid 12+8k, at most two roots per game by deterministic hash, then 128 roots globally, seed `20261022`. No result or evaluation filter was used. The selected roots cover 118 games and 101 initial openings.

Whole games were excluded if their opening or any recorded board/side state overlapped a start or sampled root in the frozen label-pilot corpus; no such overlap was found. Terminal grid roots and official benchmark roots were excluded. This is a separate development diagnostic, not a held-out labeling experiment. The pilot corpus and its source hash remained unchanged.

Both the unchanged candidate and the passive build received 131,072 requested nodes per root with fresh TT and complete history replay. Every completed iteration's score, bound, PV and node count, and every final best move, matched. The passive build also retained bench `22824107`. Its elapsed times are not used as speed measurements.

| Passive counter | Observed value |
| --- | --- |
| Total nodes | 16,777,279 |
| Quiescence nodes | 13,397,267 |
| Checked quiescence nodes | 570,054 |
| Attempted check evasions | 4,178,219 |
| Rejected illegal evasions | 3,267,465 (78.20% of attempts) |
| Searched quiet evasions | 470,619 |
| Quiescence checkmates | 3,752 |
| Maximum quiescence ply | 28 |
| Maximum-ply fallbacks | 0 |

The high rejected-evasion fraction also appears in these sampled game positions. The finite node cap and development sampling prevent a claim about all game workloads or the absence of deeper pathologies.

A passive call to the existing `Position::is_draw()` predicate found 12,138 quiescence-node hits: 5,831 fifty-move-clock hits in one sampled root's search and 6,307 repetition hits across 102 root searches. In total, 102 of 128 root searches had at least one hit. Every hit entered quiescence directly from normal search; none occurred at a checked or recursively entered quiescence node in this sample. The predicate treats a previous matching key as a search repetition; these are not all formal threefold claims. These counts expose the already-noted draw-check omission at the normal-search/quiescence boundary, but do not measure how many final root scores it changes or its Elo effect. They do not support blaming recursive checking cycles for the observed cost. Draw handling remains a separate correction, outside the running patch.

The profile also checked node accounting. Sixty-three searches used one visit beyond their 131,072-node request; the others matched it. Thus multiples of the 1,024-node polling interval are not an exact final-node guarantee. The last completed UCI iterations reported only 9,883,132 nodes in total, about 58.91% of the passive build's actual visits, omitting work in interrupted iterations. Requested caps remain the declared accounting proxy for the label pilot; exact final visits are reported here only because this diagnostic emits them.

The diagnostic charged 33,554,432 requested nodes across its two binaries, plus the separate unchanged-benchmark validation. The root JSONL SHA-256 is `8a197269535824b8d6dedd978cec7988e7ec94ec3eaaa3bb3e2f7ba4ec9db505`. Instrumented source SHA-256 is `472120bc32c96d91579c2cb358b4f441aec3d5be2ef98572ff09e6522c04d3ed`; binary SHA-256 is `2c923197f20dd5dae6c5889d0572b164cbd2d85826e5c2cadb227b6ffde0ba72`. The plan, selection record, per-root histories/transcripts, complete trace comparison, counters and accounting are under `engines/qsearch-validation/game-profile-01/`. Reproduce with `profile_game_roots.py` one directory above. GPT-6 (Codex) wrote and ran this diagnostic using CPU 19; no live source or match binary changed.

## Prepared implementation variant: compact evasions before ordering

The earlier conservative filter rejected impossible evasions after each selection-sort step. A separate implementation variant applies that same gate immediately after generating checked-quiescence moves, compacts the surviving candidates, then performs the original scoring, selection and full legality checks. This avoids scoring and sorting impossible evasions as well as their make/unmake attempts. Unchecked quiescence is unchanged. The variant starts from the original correction and is not combined with known-check reuse, quiet-tail selection or king-first ordering.

Stable compaction preserves generation order among survivors, but does not necessarily preserve their eventual search order: selection-sort swaps depend on the original array slots, including removed illegal moves. The plan recorded that caveat before building. This is therefore a Known implementation variant with possible search changes, not a search-preserving refactor.

All eight quiescence regressions, 35 perft cases and eight ASan/UBSan regressions passed. The instrumented benchmark made and undid every discarded move, confirming none was legal. Its node count matched the release variant. The existing 2,057 checked-position oracle retained every legal evasion and agreed with python-chess's complete legal move sets. Direct full-window qsearch agreed with the original corrected candidate on all 2,057 scores; every probe completed under its 131,072-node cap and restored FEN/key state. Aggregate direct-probe nodes changed from 225,101 to 224,785, about 0.14% fewer.

The official depth-seven bench changed from `22824107` to `22820573`, about 0.0155% fewer nodes. Across all 14 fresh-TT root searches, 28 completed iterations had different node counts. Every iteration's score, bound and PV, every final best move, and all completed-iteration counts matched. These are measured agreements on the diagnostic set, not a proof of universal search equivalence.

After one warm-up per binary, six alternating timing pairs ran on CPU 19 while the unchanged five-game SPRT continued. Median parent time was 2,537.5 ms; variant time was 2,419.5 ms, 4.65% lower. Median throughput was 8,991,513 versus 9,428,060 nodes/second. Every pair was faster; paired speed ratios ranged from 1.0048 to 1.1018, median 1.0473. This is a promising descriptive runtime result under shared load. It neither establishes an Elo gain nor proves that the full correction's playing-strength cost has been recovered.

| Artifact | Identity |
| --- | --- |
| Variant source SHA-256 | `9d3ac72e21e1d1c9f2535f40fe3db0838c50695f4f3a97e230b7419b0d4f77e4` |
| Variant binary SHA-256 | `d693d6ef264c76cf0c4d05e87d27e62f899be32ad964c9bab7cfb16992aa4065` |
| Plan, parent-relative patch, correctness outputs | `engines/qsearch-validation/evasion-compaction-01/` |
| All direct qsearch comparisons | `engines/qsearch-validation/evasion-compaction-01/direct-q-comparison.json` |
| Every root trace and timing pair | `engines/qsearch-validation/evasion-compaction-01/search-timing/` |
| Combined record | `engines/qsearch-validation/evasion-compaction-01/final-diagnostic.json` |

Reproduction scripts are `prepare_evasion_compaction.py` and `time_evasion_compaction.py` in `engines/qsearch-validation/`. GPT-6 (Codex) proposed and wrote this fifth local variant of idea 9. Builds used `taskset -c 14-19 make -j6` with the compiler itself pinned to CPU 19; probes and timing also used CPU 19. The active source and match-binary hashes remained unchanged. No local variant has replaced the candidate in the running match or received a completed strength result.

## Matched opening searches and an independent reference audit

A descriptive follow-up used the frozen, independently audited 1,613-game snapshot. It retained complete color-swapped pairs with game IDs above 1,000, excluding a whole pair if either game shared a pilot opening or any recorded board/side state with a reserved labeling root or initial state. There were 306 eligible pairs, all with distinct opening FENs, and one unpaired game. No pilot overlap or unparseable first-move annotation was found. No game outcome or evaluation was used to select these pairs.

Both engines start each pair from the same six-field FEN, with the same clock setting and side to move. The PGN contains each first move's reported depth and elapsed move time, but no node count. The match binaries clear TT on `ucinewgame`. This makes first moves a useful matched diagnostic; reported move time still includes environment overhead, and completed-game snapshots can censor games still in flight.

| First-search observation | Count or value |
| --- | --- |
| Correction reached lower / equal / higher reported depth | 27 / 278 / 1 pairs |
| Same first move | 292 / 306 pairs |
| Median reported depth, correction / baseline | 7 / 7 |
| Median reported move time, correction / baseline | 1.2395 / 1.2025 seconds |
| Median within-pair correction/baseline time ratio | 1.0834 |
| Equal-depth pairs choosing the same move | 273 / 278 |
| Median time ratio within the equal-depth subset | 1.0809 |

The median of paired ratios is not the ratio of the two marginal medians. Equal nominal depth also does not mean equal trees: the correction extends tactical work within quiescence. These observations describe cost and choice differences; they do not attribute the current match score to a particular mechanism. Conditioning on equal depth is an exploratory case selection, not a randomized comparison.

### Five equal-depth disagreements

All five first-move disagreements at equal reported depth were frozen for a stronger-reference audit before collecting reference scores. The reference was the [official Stockfish 19 Linux universal release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19), published 2026-09-05. Its 81,388,977-byte archive matched the release API's SHA-256 `9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f`. Executable SHA-256 was `0f83d24cc46d2c66c60f16001af5444873bc112b7d028594513426894c12da19`; its default embedded network was `nn-1a298aa575a0.nnue`.

Each alternative received separate searches at 262,144 and 1,048,576 requested nodes, with fresh TT/history tables, Hash 16 MB, Threads 1, MultiPV 1, full strength and no pondering. `NumaPolicy=none` disabled internal NUMA rebinding; every checked process-thread affinity was CPU 19. The forced move was supplied through Stockfish's `searchmoves` at the same original root FEN, keeping both alternatives in the same root-player perspective and score-normalization context. This exactly reproduces the match's FEN-only initial history, rather than inventing an earlier opening sequence.

Two constructed sanity checks verified forced-root handling: Qxh7 is mate in the proof-mask counterexample A, but has a legal rook defense in B. All reported reference PVs were independently replayed for legality. The comparison uses each search's last unbounded UCI score, an operational bounded-budget estimate, not a proven game value or a claim that the reported final depth finished completely.

| Opening pair | Corrected choice | Baseline choice | Reference difference at 262,144 nodes | Difference at 1,048,576 nodes |
| --- | --- | --- | --- | --- |
| 506 | `c1b2` | `g1f3` | -32 cp | -18 cp |
| 602 | `f3e5` | `f1b5` | +21 cp | +6 cp |
| 715 | `b1c3` | `d2d4` | +52 cp | +60 cp |
| 755 | `c1e3` | `c1f4` | +14 cp | -2 cp |
| 798 | `g8f6` | `c8b7` | -127 cp | -94 cp |

Differences are Stockfish's corrected-choice score minus its baseline-choice score from the root player's perspective. Positive favors the correction's move under that reference. The results are mixed, and pair 755 changes sign between the predeclared budgets. No aggregate quality or Elo gain is inferred from five selected disagreements. Stockfish's normalized scores are not interchangeable with ChessSI's internal evaluation scale.

A separate fixed-depth replay then ran both unchanged match binaries on all five FENs at their recorded depth seven, with fresh TT and the same Hash setting. All ten first moves reproduced exactly, and all returned PVs were legal. The disagreements therefore persist without wall-clock stopping in these cases. This establishes reproducibility of the choices, not their game-theoretic quality or the source of the whole-match result.

The reference comparison charged 13,107,200 requested nodes; its largest reported node counts summed to 13,111,929, showing small cap overshoots. The two sanity probes reported six nodes in total. The ten completed ChessSI reproductions used 54,497,865 reported nodes. All work ran on CPU 19 while the original five-game test continued with unchanged binaries. These development diagnostics neither collect reserved pilot labels nor alter its protocol.

| Evidence | Local artifact |
| --- | --- |
| Paired selection, exclusions, first-move records and summaries | `engines/qsearch-validation/opening-pair-profile-01/` |
| Official release provenance and verified executable | `engines/dependencies/stockfish-19/` |
| Frozen reference plan, five cases, all UCI transcripts and scores | `engines/qsearch-validation/opening-reference-01/` |
| Fixed-depth reproduction plan, traces and comparisons | `engines/qsearch-validation/opening-reproduction-01/` |

Reproduction scripts are `profile_opening_pairs.py`, `fetch_stockfish_reference.py`, `reference_opening_disagreements.py` and `reproduce_opening_choices.py` under `engines/qsearch-validation/`. Their records include source/input hashes. GPT-6 (Codex) designed and performed this audit. It supplies a more specific diagnosis than assuming all corrected choices are better or that every loss is caused only by runtime overhead; the original SPRT remains the strength decision.
