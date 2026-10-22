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
