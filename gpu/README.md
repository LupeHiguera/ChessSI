# ChessSI on the GPU

Research into running ChessSI's CPU work on GPUs (issue #31). Everything here is CUDA C++ compiled
at run time with NVRTC through CuPy (`pip install cupy-cuda12x`), with Python as the host; no `nvcc`
is needed. The engine itself is unchanged.

| File | What it does |
| --- | --- |
| `chess.cu`, `perft.py` | Move generation and perft. Exact on `tests/perft.epd` to depth 5; Kiwipete depth 5 runs at 5.4 billion nodes per second on an RTX 5080 |
| `nnue.cu`, `nnue_check.py` | NNUE evaluation, one warp per position. Bit-exact with the engine on 100,000 positions |
| `datagen.cu`, `datagen.py` | Self-play data generation: an exact port of `src/search.cpp`, the move order of `src/movegen.cpp`, the Zobrist keys and the datagen game loop |
| `ref.cpp` | CPU reference: `Datagen::play_game` from given positions with a 1 MB TT, to check `datagen.py` line for line |
| `match.py` | Fixed-node matches between two networks, both sides on the GPU, of one size or two, with optional node odds |
| `sprt.py` | The same games as an SPRT: pairs streamed through the GPU until the LLR crosses a bound |
| `bench.py` | Deterministic search throughput (fixed positions, cold searches, GPU time); its score MD5 checks exactness |

## Data generation

```
python gpu/datagen.py run <net.nnue> <out.txt> <games> [nodes=5000] [capacity=1024] [seed=1] [random plies=8]
```

It writes the same lines as `chesssi datagen`: `<fen> | <score> | <result> | <eval>`. The kernel is compiled for
the network's hidden size, any multiple of 256: with net19b-h512 and with seeded synthetic 768- and 1024-unit
networks it plays the same 200 games as `ref.cpp` built with each (`claude-work/2026-11-01/parity-h.sh`). Every game opens
with random legal plies, then plays at a fixed node count, and a finished game's slot is refilled at
once. From the same start positions it writes byte-identical lines to `ref.cpp`, so its data is as good
as the CPU's. The one difference is a 1 MB TT per game instead of 16 MB, which makes little difference at
5,000 nodes. Each game's pawn correction history (64 KB) sits beside its TT, and both are cleared at the
start of a game, as `Search::clear()` clears them in the engine.

Design: one game per warp. All 32 lanes run the same scalar search on one copy of the game in global
memory. Same-address reads are broadcast, and every shared update goes snapshot, `__syncwarp`, write,
since a warp's lanes are not guaranteed to stay in lockstep. Each lane owns 8 of the network's 256
hidden units. The search is not recursive: it runs from an explicit stack of frames, one per game,
because a recursive call saves every lane's registers at each level. A kernel launch plays one ply of
every game, which keeps kernels well under the Windows GPU watchdog. For longer searches, `GPU_BUDGET`
caps the nodes a search runs per launch: it then pauses, with its state in the game, and carries on
in the next launch, with the same result.

Throughput with net10 at 5,000 nodes a move, measured before TT replacement, losing captures last, SEE
pruning in the main search and correction history reached the GPU search:

| GPU | Games in flight | Positions per second | Nodes per second |
| --- | --- | --- | --- |
| RTX 5080 | 3,072 | about 13,000 | 91M |
| RTX 5060 Ti (first, recursive search; not re-measured) | 1,536 | about 3,400 | 24M |
| ChessSI on 13 CPU cores, for comparison | | about 8,300 | 39M |

How the 5080 got from about 5,900 to about 13,000 positions per second, each step byte-identical:

| Change | Positions per second | Measured as |
| --- | --- | --- |
| First version: a recursive search | 5,868 and 5,897 | 200 s runs |
| An explicit stack of frames instead of recursion | 7,743 | 200 s run |
| `do_move`'s board copy and NNUE delta in registers, 16-byte NNUE rows, 168 registers | 8,800 | 150 s run |
| Finished games written while the next ply runs | about 12,500 | an hour of datagen, part of it beside a match |
| Legality before the NNUE update, 16-bit move-ordering scores | 13,038 | half an hour of datagen; +4.5% in paired 150 s runs |

### Since then, on an RTX 5060 Ti

`bench.py` measures the kernel without the noise of a datagen run: 103,680 positions of generation 10, one
cold 5,000-node search each, timed on the GPU with CUDA events. Every row writes the same scores (MD5
`011afff14107`), and `datagen.py` plays the same 200 games as `ref.cpp` built from da0d59c. Two rounds in
opposite orders agree within 0.03 s.

```
head -n 4000000 dg10/gpu1-1002.txt | awk 'NR % 37 == 0' | head -103680 | cut -d'|' -f1 > bench-positions.txt
python gpu/bench.py gpu <net.nnue> bench-positions.txt auto 5000
```

| Change | 3,456 games at once |
| --- | --- |
| da0d59c's search (singular extensions, IIR, continuation history, eval-scaled null move), 1,728 at once | 17.30 s |
| NNUE update one perspective at a time (spills 104 -> 16 bytes), 3,456 at once (capacity `auto`) | 16.46 s |
| Legality tested before `do_move`; a child's check status from its parent's move | 15.48 s |
| `generate` writes each bitboard of targets with every lane at once (`add_set`) | 13.51 s |
| Each piece's targets in its own lane; move picking and the eval sum as single warp reductions | **12.92 s** |

Tried and dropped, all exact: prefetching the child's TT entry and history rows (4-11% slower), a
16-byte-aligned frame (+3%), lane-parallel pawn captures (+2%), and several games per warp (`GPU_GS`, branch
`claude/gpu-multigame`: 10 to 21% fewer searches a second). With 4, 8 and 12 warps per SM giving 14.1, 24.0 and 29.6M nodes a
second, the SMs are limited by the instructions they issue, not by memory latency: what helps is fewer
instructions per node, above all fewer serial loops that every lane runs together.

Short runs read lower than long ones, since all their games start together. A GPU node still costs
far more instructions than a CPU node: before the last row's changes, `-DPROFILE` timers put `do_move`
at about 40% of the time (the NNUE update 22%, the board 14%), `undo_move` at 12% and search control
at 20%.

## Matches

```
python gpu/match.py <netA.nnue> <netB.nnue> <pairs> [nodes=20000 or <A>:<B>] [seed=1] [book]
```

All pairs play at once, so a 16 GB card holds about 1,024 pairs (two sets of tables per game); play more
as several seeds. Networks of different sizes play through `match_side`: one kernel build per hidden size,
each playing the plies its side is to move, on the same games (`GPU_MATCH_SPLIT=1` forces that path for one
size, and gives the same games as `match_step`, game by game). `nodes` as `<A>:<B>` gives node odds: a bigger
network searches fewer nodes in the same time, so giving it fewer here, in the ratio of the two networks' CPU
nodes per second, estimates a timed match. net19b-h512 against net14 (two seeds of 1,024 pairs each, about
3 minutes each on a 5060 Ti):

| Nodes (net19b : net14) | Seed 1 | Seed 2 |
| --- | --- | --- |
| 20,000 : 20,000 | +70.2 ± 11.4 | +76.4 ± 11.1 |
| 17,000 : 20,000 (CPU speed 2.43M : 2.86M nps) | +34.4 ± 11.3 | +39.9 ± 11.0 |

It plays each UHO opening with both colors. Games end as in our fastchess SPRTs: mate, stalemate,
threefold repetition, fifty moves, insufficient material, or adjudication. It prints Elo from the game
pairs and the SPRT [0, 5] LLR. Fixed nodes leave speed out, so it compares networks of one size;
anything that changes speed still needs a time-based SPRT.

Validation against CPU SPRTs at 10+0.1, with 512 games at 20,000 nodes a move on an RTX 5060 Ti:

| Match | GPU | CPU SPRT |
| --- | --- | --- |
| net10 vs net10 | 0.500 exactly, every pair 1-1 | |
| net10 vs net9 | +58.9 ± 34.9 (256 games) | +56.8 ± 14.5 |
| mirror vs net9 | −22.4 ± 23.5 | −18.2 ± 9.2 |
| rg05 vs net9 | −45.7 ± 24.9 | −34.5 ± 12.4 |
| hl01 vs net9 | −58.9 ± 24.4 | −49.3 ± 14.9 |

A 512-game match takes about two minutes on a 5060 Ti that is also generating data.

```
python gpu/sprt.py <netA.nnue> <netB.nnue> [nodes=50000] [elo0=0] [elo1=5] [max pairs=20000] [games at once=2w] [seed=1] [book]
```

The same games as an SPRT (alpha = beta = 0.05, pentanomial): a finished game's slot takes the next one at
once, and only the unbroken prefix of pairs, in the order they started, counts, so an early stop sees
what a sequential test would. `GPU_PARAMS` and `GPU_PARAMS_B` give the two sides their constants. Check:
continuation history on against off passed H1 at +27.0 +/- 10.7 after 1,038 pairs at 20,000 nodes, in 4.5
minutes.

**Networks only, not search changes.** A calibration on the 5060 Ti (2,048 games each, at 50,000 and
200,000 nodes) against CPU SPRTs at 10+0.1 agreed for move ordering and evaluation (continuation history
+30.1 vs +22.5, IIR +13.9 vs +15.6, singular extensions +47.1 vs +56.0 at 200,000 nodes), but not for
pruning and extensions (eval-scaled null move +3.4 vs +7.9, negative extension -7.0 vs +3.2) nor for
constants tuned by `spsa.py` (+26.7 vs -0.3: a fixed-node GPU match is the very objective they were tuned
on). So, by the owner's decision of 2026-10-31, search changes are tested on the CPU only.

## Tuning the search's constants

Paused (owner's decision, 2026-10-31): values tuned here did not hold up in CPU SPRTs (see Matches).

```
python gpu/spsa.py <net.nnue> <pairs> [nodes=50000] [games at once=1000] [seed=1] [book]
```

The 20 constants that `src/search.cpp` writes inline are fields of `Params` in `datagen.cu`. They
cover the pruning margins and depths, the null-move reduction, the LMR table, the history bonus cap,
the aspiration windows, and the SEE thresholds in quiescence and in the main search. A match can give each side its own set, per
game. `spsa.py` runs fishtest's SPSA with them. Each game pair plays one opening twice, theta + c*delta
against theta - c*delta, and theta moves as each pair ends. A finished game's slot takes the next
game at once. On an RTX 5080, 800 games at once at 50,000 nodes play about 5.8 pairs a second.

At the end it prints the values the games used as JSON. `GPU_PARAMS` takes that JSON for `datagen.py`,
`match.py` and `spsa.py`. To move tuned values to the engine, write them into `src/search.cpp`, then
check parity: `ref.cpp` built from that source and `datagen.py` with the same `GPU_PARAMS` must write
identical lines. Then run the CPU SPRT.

Two settings keep kernel launches under the Windows GPU watchdog (2 s). Keep games at once within
what the GPU holds at a time (about 1,000 warps on a 5080). `GPU_BUDGET` caps the nodes a search runs
per launch: it pauses with its state in the game and goes on in the next launch, with the same
result, so any node count works.
