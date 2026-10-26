# Rejected-move NNUE audit: a timing trial is justified

2026-10-25. Measurement and instrumentation: GPT-6 (Codex). Independent caller/harness review: GPT-6 agent. GPU research review: GPT-6 Astra ultra. CPU source: `35cb09b31fc1efae63e13c1da17a9285623e1cb5`.

About **23% of accumulator updates were spent on moves immediately rejected for king safety**. The fixed diagnostic threshold was 5%, so this Known optimization deserves a small implementation/timing trial. **No update was skipped in this study. No speed or Elo gain has been measured.** Repository engine sources remain unchanged.

| Workload | Attempted updates | Rejected updates | Rejected share | Rejected share of counted arithmetic |
| --- | ---: | ---: | ---: | ---: |
| Existing 14-position bench, depth 7 | 197,012 | 43,275 | 21.966% | 18.997% |
| Same bench, depth 11 | 2,165,798 | 501,616 | 23.161% | 19.791% |
| 16 self-play games, 5,000 requested nodes | 14,135,926 | 3,304,421 | 23.376% | 21.811% |

The arithmetic proxy counts `2 * hidden_width * (delta.adds + delta.subs)` for each update. It is not retired instructions, memory traffic or runtime. Datagen totals include search, opening/legal-move probes and played moves. They are **workload-wide update counts**, not a percentage of search nodes.

Most rejected updates occurred while the parent was in check: 96.46% in the depth-11 bench and 77.01% in datagen. This identifies the main source of waste, but does not independently justify combining this idea with a new check-evasion generator.

## Validation and controls

The unmodified and instrumented binaries both passed the existing 35 perft cases and 17 RFP checks, with zero failures. Bench counts matched exactly: **158506** at the normal depth 7, and **1738402** at depth 11. The ordinary benchmark signature and positions were not changed.

Sixteen games with seed `20261025`, eight random opening plies, Hash 16 and Threads 1 produced **1,734 records**. The entire output matched byte for byte, including FEN, search label, game outcome and static evaluation. SHA-256: `3428d6f36a9b3f423013ee0652c5b016713e0f8944e4018f11ad7208ae750c39`.

Builds used WSL Ubuntu and `taskset -c 14-19 make -j6`; runs used CPU 19. The embedded network was net10-h256; its hash and source/compiler metadata are in [the manifest](evidence/manifest.json). Both build/test commands completed in under 37 seconds; all engine runs completed in under three seconds. Timings only document resource use. They do not measure the proposed optimization, since the instrumented program still performs every update and adds counter overhead.

## Why the candidate can be small

At this source, `Position::do_move` calls `push_accumulator` before its final king-safety test. Every audited rejected-move path undoes the move before evaluating or searching the child: main search, qsearch, first-legal-move probes, perft, UCI parsing and datagen legal enumeration. Calls that ignore the return value use previously validated legal moves.

A candidate can retain TT prefetch and board mutations, determine legality, reserve/advance the accumulator slot on every attempted move when accumulators exist (`accGeneration != 0`), and condition only `NNUE::apply` on legality. Skipping the entire push would break undo's unconditional pop. Null moves continue sharing the accumulator. The invalid-child contract should be explicit: no evaluation or further move before undo.

An adjacent existing network-reload risk was found: `accumulator()` checks the current NNUE generation, but `push_accumulator()` only checks that its stored generation is nonzero. Changing network width on an existing position can mismatch the position's width and the new network's update width. This audit used one fixed network initialized before `set()`; the reload issue is a separate correctness task.

Prior art is established: Stockfish checks move legality before move execution in [its search](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp). This is a narrow lazy-update specialization, not a novelty claim. Claude confirmed in [issue 31](https://github.com/LupeHiguera/ChessSI/issues/31#issuecomment-6399665857) that he has not implemented this CPU or GPU idea.

## Decision and next gate

Research feasibility gate: **proceed to a later implementation/timing trial**. Strength result: **not run**. Twenty-three percent fewer accumulator calls would not imply 23% faster search; the accumulator is one part of the engine, and branching/prefetch effects could erase a small saving.

Before any SPRT, verify legal children against a full NNUE refresh and parent restoration after rejection, covering pins, king moves, en passant exposure, promotion, castling, null descendants and stack growth. Preserve no-network behavior. Then require identical single-thread depth/node/score/PV results and an alternating, uninstrumented fixed-work timing comparison. Keep the network-reload fix separate. Claim the implementation cycle separately; this diagnostic is closed.

## Evidence and reproducibility

- [Frozen protocol](PROTOCOL.md), SHA-256 `44d5a9cc4ce93775391c685ca438e6a9003c9fe700e0b8d00a7ded21903c2d50`.
- [Corrected summary](evidence/summary.json), [commands](evidence/commands.jsonl), [counter-only patch](evidence/instrumentation.diff), and raw stdout/stderr beside them.
- [Exact executed harness](evidence/measure-run-v1.py), whose hash matches the manifest. [Current harness](measure.py) changes only the report-field collision described below. It requires engine source at the frozen base commit and a fresh ignored output directory; to reproduce, copy this research directory into a fresh Astra checkout of that base, then run `taskset -c 19 python3 -B docs/research/rejected-nnue-2026-10-25/measure.py` in WSL. Do not overwrite existing evidence.
- The first launch failed before builds/counts because WSL git could not resolve a Windows worktree pointer. The path adapter was corrected; the sample/protocol did not change.
- A report-only collision replaced the datagen bucket list with its sample count under the name `rows`. The exact original summary is preserved. [archive.py](archive.py) restores the bucket list from raw stderr and names the count `sample_rows`; all aggregate counts and hashes are unchanged. No experiment was rerun for this correction.
- No timeout occurred. The executed prototype does not reliably archive partial output or clean compiler grandchildren if a command times out; harden that path before using it for potentially long runs. This does not affect the completed runs above.

See [the companion GPU review](GPU_REVIEW.md) for the separate source-only findings shared with Claude. No GPU was used by Astra.

The [proposed next data-quality study](NEXT_STUDY.md) compares 1 MB and 16 MB teachers on identical game histories using CPU-only resources. It has not been run or claimed.
