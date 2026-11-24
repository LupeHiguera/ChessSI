# Accepted-result integration, 2026-11-04

The owner authorized merging ready changes. PRs #100/#102/#103 preserve their dependency order; #104 adds the independently passed TT buckets; #101 adds net24; #105 records historical results. Net25 subsequently passed and is the new default. All original PR heads are ancestors of this branch. Engine sources are byte-identical to #103 for search and #104 for the TT; other source is unchanged.

| Stage | Bench | Checks |
| --- | --- | --- |
| net24-101 | 44752 | 35 passed, 0 failed; 17 passed, 0 failed |
| net25 | 51917 | 35 passed, 0 failed; 17 passed, 0 failed |
| recovered-results-105 | 44752 | 35 passed, 0 failed; 17 passed, 0 failed |
| search-stack-100-102-103 | 43690 | 35 passed, 0 failed; 17 passed, 0 failed |
| tt-buckets-104 | 43654 | 35 passed, 0 failed; 17 passed, 0 failed |

Builds/checks borrowed PC1 cores 1–4 after the net25 match finished. Original PR CI checks passed. Only experiment-log conflicts were resolved, preserving all rows in date order. The complete combination has no new SPRT or gauntlet result. In particular, #103 includes #102 and their gains must not be added together.

Net25 terminal evidence and training launcher are saved alongside this file. Net26 is still under test on PC2; see its handoff. Running QS evasions, TT-eval and futility/LMR experiments were not merged.
