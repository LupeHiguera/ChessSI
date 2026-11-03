# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Every idea is tested with thousands of games and logged, so the log measures
what each AI model can actually do in research.

## Status

Phase 4 of 5 (refinement: tuning, more data and bigger networks). The project started on
2026-10-22. Measured rating estimates, on the CCRL Blitz scale:

| Date | Engine | Rating | Games |
| --- | --- | --- | --- |
| 2026-10-22 | Classical search through late move reductions, PeSTO evaluation | 2440 ± 19 | 2,400 vs Stash 12-19 |
| 2026-10-23 | net7 and the full pruning set | 3150 ± 26 | 959 vs Stash 19-36 |
| 2026-10-23 | net8 and SEE pruning in quiescence | 3176 ± 29 | 600 vs Stash 27-36 |
| 2026-10-24 | net10 and a 21% faster search | 3284 ± 21 | 1,200 vs Stash 27-36 |
| 2026-10-30 | net14, singular extensions and internal iterative reductions | 3452 ± 24 | 1,200 vs Stash 27-36 |
| 2026-10-31 | Non-pawn correction history, continuation history, a null-move reduction that grows with eval − beta | 3499 ± 23 | 1,200 vs Stash 30-37 at 10+0.1 |
| 2026-11-01 | The same engine, under CCRL-style conditions | **3420 ± 21** | 1,260 vs seven engines rated 3375-3720 |
| 2026-11-03 | Main `014dd979`: net22-h768, RFP improving and speedups, under CCRL-style conditions | **3482 ± 21** | 1,260 against the same seven-engine pool, PC2 E-cores |

Until 2026-10-31, gauntlets were played at 10+0.1 against Stash versions with known CCRL ratings, the
strongest of them 3417, so the figures were extrapolations. The 2026-11-01 gauntlet copies CCRL Blitz's
conditions as far as one PC can: 2'+1" scaled to this machine by CCRL's Stockfish 10 benchmark (80.7 s
+ 0.67 s here), Hash 128, and single-CPU opponents with CCRL ratings above and below ChessSI (Stash 36
and 37, Stockfish 10, Viridithas 10, Koivisto 9, Stormphrax 6, Halogen 16). It is an estimate under
those conditions, not a CCRL rating: CCRL also gives its engines endgame tablebases, which ChessSI does
not use. The 2026-11-01 build rated 79 points lower at the longer time control than at 10+0.1.
On 2026-11-03, current main reached 3482 ± 21 against the same pool on PC2, at 80.65+0.672,
with no time forfeits. These runs estimate a 62-point improvement against outside engines. Details are in
[docs/IDEAS.md](docs/IDEAS.md).

Against the [original plan](docs/PLAN.md), which expected this level after six months to a year:

| Phase | Planned | Reached |
| --- | --- | --- |
| 1 · Working engine, ~2000 | Weeks 1-2 | 2026-10-22: 2440, measured |
| 2 · Classical engine, 2800-3000 | Months 1-2 | Its search work was done on 2026-10-22; the network replaced PeSTO on 2026-10-23, so this band was passed with NNUE |
| 3 · Neural evaluation, 3200-3400 | Months 2-5 | 2026-10-23: 3150, measured; 2026-10-24: 3284, measured |
| 4 · Refinement, 3400-3500+ | Months 6-12+ | 2026-10-30: 3452, measured; 2026-10-31: 3499, measured; CCRL-style estimates: 3420 on 2026-11-01, 3482 on 2026-11-03 |
| 5 · The final gap, Stockfish level | A year or more | Not started |

The plan expected compute to set the pace from phase 3 on. The GPU tools below expand training-data
generation and screen candidate networks. Search changes are tested by CPU SPRT; GPU SPSA is paused.

The engine:

- **Moves:** magic-bitboard move generation, verified against known perft counts.
- **Interface:** UCI, so it plays in any chess GUI. `Threads` runs Lazy SMP.
- **Search:** iterative deepening, principal variation search with aspiration windows, a
  transposition table (prefetched; entries replaced by depth and age), check extension, singular
  extensions with multi-cut, and quiescence search with SEE pruning. The time limit adapts to how
  stable the best move is.
- **Pruning and reductions:** null-move pruning (reduced more the further the eval is above beta),
  reverse futility pruning, futility pruning, late
  move pruning, late move reductions, internal iterative reductions and SEE pruning near the leaves,
  with constants tuned by SPSA.
- **Move ordering:** killer moves, a history heuristic with continuation history (how a move fared
  after the previous move and the one before), and losing captures after the quiet moves.
- **Evaluation:** NNUE, (768 → 768) × 2 → SCReLU → 1, compiled into the binary, plus correction
  history, which learns during a game how far the network is off for each pawn structure and for each
  side's non-pawn pieces.
  - The network is trained only on ChessSI's own games. The default, net22-h768, was trained for 20
    epochs on 977.1M unique generation-10 positions labelled by net14, using the streaming trainer
    and scattered shards; the history is in [nets/README.md](nets/README.md).
  - The output layer is vectorized by hand (AVX2 and AVX-VNNI).
  - PeSTO tables are the fallback.
- **GPU tools:** a CUDA search port (`gpu/`), checked against its CPU reference, generates self-play
  data and plays fixed-node matches between candidate networks. CPU SPRTs decide whether a network
  becomes the default. GPU search-change testing and SPSA were paused after calibration disagreed
  with CPU results; their earlier measurements remain in the benchmark log.
- **Bench:** `50868` nodes on main `014dd979`.

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
