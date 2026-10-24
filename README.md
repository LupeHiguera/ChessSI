# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Every idea is tested with thousands of games and logged, so the log measures
what each AI model can actually do in research.

## Status

Phase 3 of 5 (neural evaluation). Measured rating, on the CCRL Blitz scale:

| Date | Engine | Rating | Games |
| --- | --- | --- | --- |
| 2026-10-22 | Classical search through late move reductions, PeSTO evaluation | 2440 ± 19 | 2,400 vs Stash 12-19 |
| 2026-10-23 | net7 and the full pruning set | 3150 ± 26 | 959 vs Stash 19-36 |
| 2026-10-23 | net8 and SEE pruning in quiescence | 3176 ± 29 | 600 vs Stash 27-36 |
| 2026-10-24 | net10 and a 21% faster search | **3284 ± 21** | 1,200 vs Stash 27-36 |

Gauntlets are played at 10+0.1 against Stash versions with known CCRL ratings, so the figure is
approximate. Details are in [docs/IDEAS.md](docs/IDEAS.md).

The engine:

- **Moves:** magic-bitboard move generation, verified against known perft counts.
- **Interface:** UCI, so it plays in any chess GUI.
- **Search:** iterative deepening, principal variation search with aspiration windows, a
  transposition table (prefetched), check extension, and quiescence search with SEE pruning.
- **Pruning and reductions:** null-move pruning, reverse futility pruning, futility pruning, late
  move pruning and late move reductions.
- **Move ordering:** killer moves and a history heuristic.
- **Evaluation:** NNUE, (768 → 256) × 2 → SCReLU → 1, compiled into the binary.
  - The network is trained only on ChessSI's own games. The default, net10, saw 233.7M positions; the
    history is in [nets/README.md](nets/README.md).
  - The output layer is vectorized by hand (AVX2 and AVX-VNNI).
  - PeSTO tables are the fallback.
- **Bench:** `158506` nodes.

Research so far:

- **A novel idea passed.** A training-only auxiliary head, dropped when the network is exported,
  gained **+53.2 ± 15.6** Elo and **+34.6 ± 12.2** on a second data snapshot. Ablations show it works
  as an extra low-noise target for the network (the search score), not as lookahead.
- **Every idea is logged, pass or fail,** with the AI model that proposed it. Claude Code and Astra
  (GPT-6) have tested ideas side by side on the same PC.

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
