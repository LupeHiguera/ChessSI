# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Every idea is tested with thousands of games and logged, so the log measures
what each AI model can actually do in research.

## Status

Phase 3 of 5 (neural evaluation), with phase 4's tuning and data work under way. Measured rating, on
the CCRL Blitz scale:

| Date | Engine | Rating | Games |
| --- | --- | --- | --- |
| 2026-10-22 | Classical search through late move reductions, PeSTO evaluation | 2440 ± 19 | 2,400 vs Stash 12-19 |
| 2026-10-23 | net7 and the full pruning set | 3150 ± 26 | 959 vs Stash 19-36 |
| 2026-10-23 | net8 and SEE pruning in quiescence | 3176 ± 29 | 600 vs Stash 27-36 |
| 2026-10-24 | net10 and a 21% faster search | **3284 ± 21** | 1,200 vs Stash 27-36 |

Gauntlets are played at 10+0.1 against Stash versions with known CCRL ratings, so the figure is
approximate. Details are in [docs/IDEAS.md](docs/IDEAS.md).

Since that gauntlet, eight changes passed their SPRTs, worth +216 Elo in self-play together: net12
(+32.1), net11 (+50.7), search constants tuned on the GPU (+40.4), losing captures last (+30.4), SEE
pruning in the main search (+24.2), pawn correction history (+18.5), time management (+15.1) and TT
replacement by depth and age (+5.0). Past gauntlets kept 55-81% of self-play gains against other
engines, so the engine is estimated at **about 3430 (3400-3460)**, not yet measured: the next gauntlet
needs opponents above 3400.

The engine:

- **Moves:** magic-bitboard move generation, verified against known perft counts.
- **Interface:** UCI, so it plays in any chess GUI. `Threads` runs Lazy SMP.
- **Search:** iterative deepening, principal variation search with aspiration windows, a
  transposition table (prefetched; entries replaced by depth and age), check extension, and
  quiescence search with SEE pruning. The time limit adapts to how stable the best move is.
- **Pruning and reductions:** null-move pruning, reverse futility pruning, futility pruning, late
  move pruning, late move reductions and SEE pruning near the leaves, with constants tuned by SPSA.
- **Move ordering:** killer moves, a history heuristic, and losing captures after the quiet moves.
- **Evaluation:** NNUE, (768 → 256) × 2 → SCReLU → 1, compiled into the binary, plus pawn correction
  history, which learns during a game how far the network is off for each pawn structure.
  - The network is trained only on ChessSI's own games. The default, net12, saw 436.4M positions, all from net11's self-play; the
    history is in [nets/README.md](nets/README.md).
  - The output layer is vectorized by hand (AVX2 and AVX-VNNI).
  - PeSTO tables are the fallback.
- **GPU tools:** a CUDA port of the search (`gpu/`) plays thousands of self-play games at once for
  training data, about 15,000 positions a second on an RTX 5080, and tunes search constants by SPSA.
- **Bench:** `69980` nodes.

Research so far:

- **A novel idea passed.** A training-only auxiliary head, dropped when the network is exported,
  gained **+53.2 ± 15.6** Elo and **+34.6 ± 12.2** on a second data snapshot. Ablations show it works
  as an extra low-noise target for the network (the search score), not as lookahead.
- **Search tuning on the GPU.** SPSA on the CUDA search port tuned 17 search constants in 90 minutes
  of games at 50,000 nodes a move, worth **+40.4 ± 11.7** Elo in CPU games at 10+0.1.
- **Fresher data beat more data.** net12 trained only on net11's games, on 19% fewer positions than
  net11, and still gained **+32.1 ± 10.8** Elo over it.
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
