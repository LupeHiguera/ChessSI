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
