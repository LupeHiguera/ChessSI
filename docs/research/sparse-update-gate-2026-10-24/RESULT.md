# Sparse accumulator updates failed the first runtime screen

On 2026-10-24, this standalone kernel failed the predeclared gate on accepted main
`ea8a13d5635808b3a7d43f3d6db2aa68dbe484f3`. At 50% independently occupied feature-row blocks,
median paired sparse/dense time ratios were **1.594 for quiet moves** and **1.471 for captures**.
The sparse kernel was slower in all seven pairs of both cases. Stop this implementation before
sparse-network training. This is an offline result, with **zero games and no Elo estimate**.

GPT-6 (Codex) proposed the study and implemented the harness/analysis; GPT-6 Astra (ultra)
reviewed the arithmetic and methodology. The engine, trainer and default network are unchanged.
Broad block sparsity is Known; novelty of the proposed changed-row-union training objective
has not been established.

## Fixed comparison and results

The [protocol](PROTOCOL.md) was written before timings. It required both quiet and capture
cases at q=0.5 with independent masks to achieve median paired time ratio <=0.90 and be faster
in at least six of seven pairs. All 630 raw samples are retained in [raw.csv](raw.csv). Ratios
below are medians of seven within-pair ratios, **not ratios of separately computed medians**.

| Primary case | Actual row occupancy | Changed-block union | Median sparse/dense | Sparse faster |
| --- | ---: | ---: | ---: | ---: |
| Quiet, add 1 / subtract 1 | 49.93% | 75.48% | 1.593915 | 0/7 |
| Capture, add 1 / subtract 2 | 49.93% | 87.30% | 1.471424 | 0/7 |

Paired ratios were 1.331-1.793 for quiet moves and 1.218-1.547 for captures. These are ranges
of observed pairs, not confidence intervals. Samples are short and variable; the percentages
are observations of this screen, not stable whole-engine speed estimates. No favorable-result
reruns, changed seeds or added timing samples were used.

Descriptive controls do not rescue the primary failure. With q=0.25 independent masks, median
ratios were 2.785 quiet and 2.233 capture. With masks tied across squares of each colored piece
type at q=0.5, they were 1.066 and 0.999, with only 3/7 and 5/7 pairs faster. Completely zero
weights made the sparse quiet/capture paths faster, but do not constitute a useful evaluator.
Castle descriptors use only four repeated shapes, so their locality differs from the other
cases. The separately labelled copy-only reference intentionally computes the wrong answer
for nonzero updates and is never a candidate.

The fused dense and sparse versions used the same synthetic masked weights, runtime H=256,
384 KiB feature-weight table and 64 distinct parent/child accumulator slots. Each sparse call
built a separate union per perspective; untouched child blocks were copied and touched blocks
performed the full fused arithmetic. Row-pointer setup and mask lookup were timed. The
compiler vectorized both arithmetic loops with 32-byte vectors.

## Correctness, resources and limits

Both sanitizer and optimized runs independently checked 61,440 synthetic operations against a
widened scalar oracle: both perspectives, all child lanes, poison/guard checks, unchanged
inputs and intermediate int16 bounds. AddressSanitizer/UBSan reported no errors. The optimized
run also checked final outputs after every timing sample. All 630 records, conditions, pair
orders, sample lengths and dense/sparse checksums reconciled in the analysis.

The study used WSL Ubuntu, GCC 13.3.0, `-O3 -march=native -DNDEBUG`, and **CPU 19 only**.
Measurement ran 2026-10-24 07:29:23-07:29:25 UTC. Claude had a fastchess manager and 24 engine
processes running concurrently. Their recorded processors were 0-12; a follow-up affinity
check found all 25 processes restricted to 0-12. Astra's runner affinity was 19. The PC was
shared, not idle; Windows scheduling, cache and power interactions remain timing limitations.
No GPU was used and no other agent's jobs or files were changed.

The unchanged accepted engine passed 35 perft and 17 RFP checks, zero failed, and reproduced
**Bench: 163764** with net9. This is baseline validation, not a strength result for sparsity.

The workload is synthetic, with repeated descriptors and dense weight storage. It does not
measure legal search traces, sparse training accuracy, compression, refresh, dense output
evaluation or whole-engine speed. A miss rejects this kernel at the declared operating point;
it does not show that every sparse NNUE implementation is impossible. The original protocol
and sources are unchanged after observing timings.

## Why the result is plausible, and a separate future question

With independent row occupancy q and k changed rows, expected union occupancy is
`u = 1 - (1-q)^k`. If every touched block loads all k rows, a bandwidth-only time-ratio model
is `(2 + k*u)/(2+k)`, counting the mandatory parent read and child write. At q=0.5 this is
0.875 quiet and 0.925 capture before metadata/branch overhead. These are traffic estimates,
not proven runtime bounds; the 0.90 capture gate was deliberately demanding. Whole-search
benefit would also be diluted by all costs outside accumulator updates.

A separate, unimplemented alternative is `W(piece,square) = B(piece) + R(piece,square)`, with
sparse square residuals and a shared dense piece contribution. Shared terms cancel on quiet
moves and castling while retaining material capacity. Captures still require the captured
piece's dense correction; promotions change the dense piece contribution too. Folding the
factors into ordinary weights would lose this runtime distinction. This is known factorization
algebra, not a new novelty claim or a revision of the failed gate. Per-ply copying remains.

Closer prior art found during this study is Stockfish's NNUE guide on
[blocked sparse-output weights](https://github.com/official-stockfish/nnue-pytorch/blob/9d1702fd04c2328d620fcc3ae96c95c40bdb1aa8/docs/nnue.md#linear-layer-with-sparse-input-and-blocked-sparse-output).
It explicitly describes zero weight blocks and training-aware pruning. Broader related work:
[Delta Networks, ICML 2017](https://proceedings.mlr.press/v70/neil17a.html), and
[Scalpel, ISCA 2017](https://homes.luddy.indiana.edu/lukefahr/papers/jiecaoyu_isca17.pdf).
These precedents do not establish the narrower changed-row-union objective's novelty.

## Reproduction

From this worktree in WSL, use CPU 19 under the sharing agreement. These commands run a new
screen; they do not recreate the timing environment or replace the archived samples.

```bash
mkdir -p engines/sparse-gate
taskset -c 19 g++ -std=c++20 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra tools/research/sparse_update_gate.cpp -o engines/sparse-gate/check-sanitized
taskset -c 19 engines/sparse-gate/check-sanitized --check-only
taskset -c 19 g++ -std=c++20 -O3 -march=native -DNDEBUG -Wall -Wextra tools/research/sparse_update_gate.cpp -o engines/sparse-gate/measure
taskset -c 19 engines/sparse-gate/measure --hidden 256 --passes 32 > engines/sparse-gate/new-raw.csv
taskset -c 19 python3 tools/research/summarize_sparse_gate.py docs/research/sparse-update-gate-2026-10-24/raw.csv
```

The final command recomputes the verdict from the original saved samples. Source, protocol,
raw-data and binary identities plus validation logs are indexed in [run.json](run.json).
