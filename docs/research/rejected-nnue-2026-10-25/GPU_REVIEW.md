# GPU research review: exactness, throughput, and next measurements

2026-10-25. Independent source reviews by GPT-6 Astra ultra, consolidated and checked by GPT-6 (Codex). Reviewed `8521691` and explicit-stack update **`4c8ebad48860fd9e8e640c17e5727eabedd05a86`**. Findings are tied to that revision, not a claim that later revisions retain them. No GPU jobs were run by Astra.

## What has changed

Claude has a full GPU self-play search port, not just fast move generation. His [pinned README](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/README.md) reports 7,743 exported positions/s on a 5080 at 5,000 requested nodes and 3,072 games in flight, compared with 5,868-5,897 before replacing recursive calls with one explicit frame stack per game. These are author measurements, not independently reproduced results. The old recursive profile is stale after this change.

Inspection supports equivalence of the current move order/ties, TT index/replacement, completed-iteration search labels and datagen repetition logic to the matched CPU reference. Claude reports byte-identical output on 200 games. That is useful evidence, with finite coverage. In particular, a 1 MB GPU/reference comparison does not establish equivalence to the production 16 MB teacher; TT contents persist across plies.

Claude subsequently reported [GPU SPSA tuning](https://github.com/LupeHiguera/ChessSI/issues/31#issuecomment-6399665857) of 17 search constants, followed by a planned CPU time-based SPRT. That work belongs to Claude. The parameterized revision was not part of the initial search audit summarized here.

## Source-backed findings sent to Claude

Full handoff: [issue 31 comment](https://github.com/LupeHiguera/ChessSI/issues/31#issuecomment-6399663221).

| Finding at 4c8ebad | Scope and next check |
| --- | --- |
| All lanes concurrently store common board/state, TT and frame values | Source-level CUDA memory-model hazard; no observed label mismatch. Give common stores one writer while retaining warp synchronization. |
| Random openings of 130 or more plies can exceed the 130 accumulator slots | Conditional memory bug; default eight plies unaffected. Validate bounds or recycle each opening accumulator. |
| Adjudicating search omitted from node totals/verbose ply logs | Final search is logged before returning, but collectors stop at the unincremented ply count. Training sample remains; exported positions/s is unaffected by this issue. |
| Requested game count below capacity starts capacity attempts | Host boundary error. Initialize only the requested active slots and define successful games versus attempts. |
| Imported FENs preserve uncapturable EP/invalid castling rights | CPU normalizes these; ordinary generated start-position games avoid this discrepancy. Add normalized-FEN fixtures. |

Relevant source: [shared stores](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/datagen.cu#L355), [opening accumulator](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/datagen.cu#L1109), [adjudication](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/datagen.cu#L986), [host initialization](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/datagen.py#L200), [FEN import](https://github.com/LupeHiguera/ChessSI/blob/4c8ebad48860fd9e8e640c17e5727eabedd05a86/gpu/datagen.py#L86).

Barriers around snapshot/write phases do not order multiple writers inside a phase. CUDA's [data-race rules](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/cuda-cpp-memory-model.html#data-races) do not exempt equal-value writes. Predicate the common store, not cooperative work or private control state. For `g->frames[sp++] = f`, only lane 0 should store but every lane must increment its own `sp`. Preserve publication/read-before-overwrite barriers initially; do not combine ownership repair with barrier removal. A clean [Compute Sanitizer racecheck](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html#racecheck-tool) cannot certify these global-memory stores because racecheck targets shared-memory hazards.

Also retain launch seed/game-ID manifests. GPU runs restart IDs at zero, so identical seeds reproduce the same games across launches/capacities. This is a conditional duplication risk, not evidence that current datasets overlap. Differential checks should cover random-opening history and slot refill as well as supplied FENs.

## Prioritized throughput experiments

First establish explicit write ownership. Then profile the new explicit-stack version, selecting one change per comparison.

1. **NNUE access layout.** Current ownership is `lane*8+j`. For scalar short instructions, a warp instruction touches 16 32-byte sectors, versus two with `lane+32*j`. This is a source-derived access hypothesis, not an eightfold throughput prediction: neighboring iterations may reuse cache lines, and generated vector loads can remove the apparent advantage. Inspect SASS and per-source sectors before implementing interleaved ownership. Preserve integer casts/divisions and require exact evaluation/search parity. [NVIDIA memory triage](https://docs.nvidia.com/nsight-compute/ComputeTriage/).
2. **Remaining local-memory traffic.** Dynamically indexed `Board` and `Delta` arrays can still spill per lane after recursion removal. Measure local loads/stores, register count and stalls in `do_move` before choosing scalarized storage or one board mutation per warp. A one-writer board mutation must publish its delta to all cooperating NNUE lanes; added synchronization could offset savings. Occupancy alone is not the objective. [NVIDIA profiling guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html#memory).
3. **Host gaps.** The production loop synchronously reads completion status every ply, allocates collection buffers, reads samples, formats FENs and writes files before launching subsequent work. Measure a short host/device timeline. If those gaps matter, first reuse buffers and overlap completed-game formatting with independent GPU work. Preserve game IDs and output ordering: first-occurrence deduplication makes ordering consequential.

A bounded future comparison should freeze the network, seed/ID manifest, node budget, capacity and TT size. Require identical per-ply moves/scores/nodes and final records, then measure unprofiled end-to-end exported positions/s in alternating paired runs. A predeclared 3% repeatable improvement could be a practical engineering gate; it is not an Elo result. Do not run such profiling alongside an unrelated GPU trial without coordinating its ownership.

PC2's CPU-only role can be independent reference replay and timed strength tests. It need not have a GPU to remove validation work from the busy GPU machine. Extra generated positions help only if their data quality, diversity and training use survive measurement.

## Subsequent SPSA export review

A separate review of parameterized revision `ad69e7b2c8d55bfca89e033185edba0672154203` found no source-level fault in pair/color bookkeeping, the plus-side score sign or separate side TTs. It found two export discrepancies worth fixing before CPU transfer, [sent to Claude](https://github.com/LupeHiguera/ChessSI/issues/31#issuecomment-6399745016):

- [spsa.py](https://github.com/LupeHiguera/ChessSI/blob/ad69e7b2c8d55bfca89e033185edba0672154203/gpu/spsa.py#L153) prints integer settings with `int(theta + 0.5)`; [make_params](https://github.com/LupeHiguera/ChessSI/blob/ad69e7b2c8d55bfca89e033185edba0672154203/gpu/datagen.py#L84) executes `floor(theta + 0.5)`. For negative `qsSee`, theta -10 prints -9 but executes -10.
- Two-decimal LMR float output can change the realized table. At depth 3, move 4, `log(3)*log(4)/2.25` is approximately 0.676888898. Base 0.324 produces integer reduction 1; printed base 0.32 produces 0. This in-range arithmetic example is hypothetical, not a report of the actual final tuner state.

Export full-precision settings through the same realization routine, retain a realized-table hash, and compare non-default CPU/GPU behavior before the intended timed CPU SPRT. Default-setting parity alone does not validate arbitrary tuned tables. These findings do not invalidate the active tuning games.

Fixed-node search tuning can reward settings with a different cost per node, and CPU/GPU hardware costs differ. Treat GPU SPSA as candidate generation. Claude already plans the relevant timed CPU test; no additional claim of Elo follows from the GPU optimization objective.

The active tuner uses 50,000 nodes and 1 MB TT, while the intended CPU SPRT uses time limits and 16 MB. A small transfer check can verify the realized candidate at a matched 1 MB first, then measure candidate/default CPU elapsed time on identical fixed-node positions. The earlier 5,000-node datagen rationale does not by itself validate the 50,000-node tuning configuration.
