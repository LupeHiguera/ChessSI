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
| `match.py` | Fixed-node matches between two networks of the same size, both sides on the GPU |

## Data generation

```
python gpu/datagen.py run <net.nnue> <out.txt> <games> [nodes=5000] [capacity=1024] [seed=1] [random plies=8]
```

It writes the same lines as `chesssi datagen`: `<fen> | <score> | <result> | <eval>`. Every game opens
with random legal plies, then plays at a fixed node count, and a finished game's slot is refilled at
once. From the same start positions it writes byte-identical lines to `ref.cpp`, so its data is as good
as the CPU's. The one difference is a 1 MB TT per game instead of 16 MB, which makes little difference at
5,000 nodes.

Design: one game per warp. All 32 lanes run the same scalar search on one copy of the game in global
memory. Same-address reads are broadcast, and every shared update goes snapshot, `__syncwarp`, write,
since a warp's lanes are not guaranteed to stay in lockstep. Each lane owns 8 of the network's 256
hidden units. The search is not recursive: it runs from an explicit stack of frames, one per game,
because a recursive call saves every lane's registers at each level. A kernel launch plays one ply of
every game, which keeps kernels well under the Windows GPU watchdog.

Throughput with net10 at 5,000 nodes a move:

| GPU | Games in flight | Positions per second | Nodes per second |
| --- | --- | --- | --- |
| RTX 5080 | 3,072 | about 7,700 | 55M |
| RTX 5060 Ti (recursive search, not yet re-measured) | 1,536 | about 3,400 | 24M |
| ChessSI on 13 CPU cores, for comparison | | about 8,300 | 39M |

The frame stack made the search 32% faster than the first, recursive version (7,743 positions per
second against 5,868 and 5,897 on the 5080, 200-second runs). A GPU node still costs far more
instructions than a CPU node. With the recursive search, `-DPROFILE` timers put `do_move` at 32% of the
time and search control at 20%, and capping registers to raise occupancy changed little.

## Matches

```
python gpu/match.py <netA.nnue> <netB.nnue> <pairs> [nodes=20000] [seed=1] [book]
```

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
