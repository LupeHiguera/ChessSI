# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Every idea is tested with thousands of games and logged, so the log measures
what each AI model can actually do in research.

## Status

Phase 4 of 5 (refinement: tuning, more data and bigger networks), less than a week after the project
started on 2026-10-22. Measured rating, on the CCRL Blitz scale:

| Date | Engine | Rating | Games |
| --- | --- | --- | --- |
| 2026-10-22 | Classical search through late move reductions, PeSTO evaluation | 2440 ± 19 | 2,400 vs Stash 12-19 |
| 2026-10-23 | net7 and the full pruning set | 3150 ± 26 | 959 vs Stash 19-36 |
| 2026-10-23 | net8 and SEE pruning in quiescence | 3176 ± 29 | 600 vs Stash 27-36 |
| 2026-10-24 | net10 and a 21% faster search | 3284 ± 21 | 1,200 vs Stash 27-36 |
| 2026-10-30 | net14, singular extensions and internal iterative reductions | **3452 ± 24** | 1,200 vs Stash 27-36 |

Gauntlets are played at 10+0.1 against Stash versions with known CCRL ratings, so the figure is
approximate. Details are in [docs/IDEAS.md](docs/IDEAS.md). The strongest opponent, Stash 36 (3375),
scored 43% against ChessSI, so the next gauntlet needs stronger ones.

Since that gauntlet, non-pawn correction history passed its SPRT (+16.7 in self-play), so the default
build is somewhat stronger than the last measurement.

Against the [original plan](docs/PLAN.md), which expected this level after six months to a year:

| Phase | Planned | Reached |
| --- | --- | --- |
| 1 · Working engine, ~2000 | Weeks 1-2 | 2026-10-22: 2440, measured |
| 2 · Classical engine, 2800-3000 | Months 1-2 | Its search work was done on 2026-10-22; the network replaced PeSTO on 2026-10-23, so this band was passed with NNUE |
| 3 · Neural evaluation, 3200-3400 | Months 2-5 | 2026-10-23: 3150, measured; 2026-10-24: 3284, measured |
| 4 · Refinement, 3400-3500+ | Months 6-12+ | 2026-10-30: 3452, measured |
| 5 · The final gap, Stockfish level | A year or more | Not started |

The plan expected compute to set the pace from phase 3 on. The GPU tools below changed how much there
is: the GPUs now generate the training data and play the tuning games.

The engine:

- **Moves:** magic-bitboard move generation, verified against known perft counts.
- **Interface:** UCI, so it plays in any chess GUI. `Threads` runs Lazy SMP.
- **Search:** iterative deepening, principal variation search with aspiration windows, a
  transposition table (prefetched; entries replaced by depth and age), check extension, singular
  extensions with multi-cut, and quiescence search with SEE pruning. The time limit adapts to how
  stable the best move is.
- **Pruning and reductions:** null-move pruning, reverse futility pruning, futility pruning, late
  move pruning, late move reductions, internal iterative reductions and SEE pruning near the leaves,
  with constants tuned by SPSA.
- **Move ordering:** killer moves, a history heuristic, and losing captures after the quiet moves.
- **Evaluation:** NNUE, (768 → 256) × 2 → SCReLU → 1, compiled into the binary, plus correction
  history, which learns during a game how far the network is off for each pawn structure and for each
  side's non-pawn pieces.
  - The network is trained only on ChessSI's own games. The default, net14, is net12 trained further
    on 402.3M positions of net12's self-play on the GPUs; the history is in [nets/README.md](nets/README.md).
  - The output layer is vectorized by hand (AVX2 and AVX-VNNI).
  - PeSTO tables are the fallback.
- **GPU tools:** a CUDA port of an earlier version of the search (`gpu/`, byte-identical to that
  version on the CPU; draft PR #74 brings it up to 2026-10-28's search) plays thousands of games at
  once. It generates training data at about 13,000 positions a second on an RTX 5080, 1.6×
  the 13 CPU cores ([gpu/README.md](gpu/README.md)); it made all of net12's data. It also plays
  fixed-node matches between networks and tunes search constants by SPSA.
- **Bench:** `59755` nodes.

Research so far:

- **A novel method passed: search tuning on the GPU.** SPSA on the CUDA search port tuned 17 search
  constants in 90 minutes of games at 50,000 nodes a move, worth **+40.4 ± 11.7** Elo in CPU games
  at 10+0.1. Logged as Novel: the prior-art check found no tuning games run on a GPU, and no GPU port
  of an engine's search checked byte for byte against the CPU.
- **An idea from Go transferred.** A training-only auxiliary head, dropped when the network is
  exported, gained **+53.2 ± 15.6** Elo and **+34.6 ± 12.2** on a second data snapshot. Ablations
  show it works as an extra low-noise target for the network (the search score), not as lookahead.
  First logged as Novel, it was relabelled Partially known on 2026-10-25: KataGo has trained
  auxiliary value heads since 2020, though no strong chess engine was found using one.
- **Newer data beat more data.** net12 trained only on net11's games, on 19% fewer positions than
  net11, and still gained **+32.1 ± 10.8** Elo over it. It changed both the data's age and its
  teacher, so it does not isolate recency.
- **Every idea is logged, pass or fail,** with the AI model that proposed it. Claude Code and Astra
  (GPT-6) have tested ideas side by side on the same PC, and Grok 4.7 (via Cursor) reviews plans
  on the coordination issue.

## Quick start

```
make              # build ./chesssi
make test         # move generation correctness
./chesssi bench   # speed and node-count signature
./chesssi         # UCI mode
```

## Docs

- [AGENTS.md](AGENTS.md): how AI agents work on this repo (commands, layout, the test-and-log loop)
- [docs/PLAN.md](docs/PLAN.md): goals, roadmap, hardware, testing method
- [docs/IDEAS.md](docs/IDEAS.md): the benchmark log and the queue of ideas to try
- [docs/SETUP.md](docs/SETUP.md): setting up a machine to build, test and play
