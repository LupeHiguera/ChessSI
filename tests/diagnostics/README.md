# Reporting diagnostics

These probes expose search behavior for research. They are separate from `make test`, do not modify engine source, and do not establish playing strength.

## TT draw-clock context

`tt_clock_context.cpp` includes the current private search implementation and reports depth-three non-root searches on a rook-versus-king position and its color mirror. Full-window calls populate the table; `[0,1]` calls compare reuse across fifty-move clocks against fresh-table controls. It uses no book, network, external engine or Python dependency.

From the repository root, build and run inside WSL using the assigned CPU allocation. While five Astra games are active, keep the compiler and probe on CPU 19:

```sh
taskset -c 14-19 make -j6 -f tests/diagnostics/Makefile CXX='taskset -c 19 g++'
taskset -c 19 engines/tt-clock-context
```

The executable defaults to an ignored path, and each search is capped at 131,072 nodes. Exit zero means all calls completed without hitting that cap and restored FEN, key and draw state. It does **not** mean the reported scores are correct. Bound names and values come from `src/tt.h`; at the recorded baseline, `3` means exact.

At baseline `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`, clock 98 reuses a +562 score from clock 0 in one visit, while the fresh null-window clock-98 call returns 0. Conversely, clock 0 reuses a cached 0 from clock 98, while its fresh null-window result exceeds beta. The clock-100 control returns 0 before the table cutoff. All eighteen calls together use 3,332 visits. These observations can change as search changes; they are documented results, not assertions that the bug must persist.

The fresh and reused null-window calls, rather than arbitrary equality between full-window and null-window scores, establish the mismatch. Synthetic cache contexts do not establish live-match frequency. See the [full audit and independent legal oracle record](../../docs/research/codex-2026-10-22/search.md#draw-clock-context-can-mimic-a-transposition-table-contradiction) for interpretation and limitations.

A separate ordinary-UCI follow-up found no final score or move change in sixteen constructed cases with fresh, same-context warm and cross-clock warm controls. The private bound mismatch therefore does not by itself demonstrate a changed root decision or a playing-strength loss; the full audit records that negative result too.
