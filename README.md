# ChessSI
An experimental UCI chess engine developed mostly with AI assistance, with a public record of
experiments, including failures. The aim is to build a stronger engine and study what AI-assisted
development can contribute to computer-chess research.

ChessSI implements established methods developed by the computer-chess community. Its NNUE networks
are trained on ChessSI's own games and search labels under the project's data policy; its fallback
uses Ronald Friederich's published PeSTO tables. See [credits and provenance](CREDITS.md) for the
people, engines, research and tools behind this work, including unresolved attribution/license items.

Ideas may stop at an offline gate or a screen; accepted strength changes require the recorded SPRT.
The log attributes work to the models involved, but differing tasks, baselines, compute and human
guidance prevent a controlled comparison between models. This project does not establish AGI.

## Status

Snapshot: 2026-11-02, main `014dd979`. The default is **net22-h768**; the recorded default-depth
bench is **50868** (merge validation in `3bbb99d6`). This newer build has no gauntlet rating recorded
below. The latest local estimate, **3420 ± 21**, belongs to the older build `8912405` with net14.
These are local estimates anchored to CCRL Blitz opponent ratings, not ratings issued by CCRL:

| Date | Engine | Rating | Games |
| --- | --- | --- | --- |
| 2026-10-22 | Classical search through late move reductions, PeSTO evaluation | 2440 ± 19 | 2,400 vs Stash 12-19 |
| 2026-10-23 | net7 and the full pruning set | 3150 ± 26 | 959 vs Stash 19-36 |
| 2026-10-23 | net8 and SEE pruning in quiescence | 3176 ± 29 | 600 vs Stash 27-36 |
| 2026-10-24 | net10 and a 21% faster search | 3284 ± 21 | 1,200 vs Stash 27-36 |
| 2026-10-30 | net14, singular extensions and internal iterative reductions | 3452 ± 24 | 1,200 vs Stash 27-36 |
| 2026-10-31 | Non-pawn correction history, continuation history, a null-move reduction that grows with eval − beta | 3499 ± 23 | 1,200 vs Stash 30-37 at 10+0.1 |
| 2026-11-01 | The same engine, under CCRL-style conditions | **3420 ± 21** | 1,260 vs seven engines rated 3375-3720 |

Until 2026-10-31, gauntlets were played at 10+0.1 against Stash versions with known CCRL ratings, the
strongest of them 3417, so the figures were extrapolations. The 2026-11-01 gauntlet copies CCRL Blitz's
conditions as far as one PC can: 2'+1" scaled to this machine by CCRL's Stockfish 10 benchmark (80.7 s
+ 0.67 s here), Hash 128, and single-CPU opponents with CCRL ratings above and below ChessSI (Stash 36
and 37, Stockfish 10, Viridithas 10, Koivisto 9, Stormphrax 6, Halogen 16). It is an estimate under
those conditions, not a CCRL rating: CCRL also gives its engines endgame tablebases, which ChessSI does
not use. The two estimates differ by 79 points, but both time control and opponent pool changed, so this
is not an isolated measurement of time-control scaling. Details are in
[docs/IDEAS.md](docs/IDEAS.md).

Progress against the [original plan](docs/PLAN.md). Its timelines were speculative planning estimates,
not a measured human-development baseline or evidence of a particular AI speedup:

| Phase | Planned | Reached |
| --- | --- | --- |
| 1 · Working engine, ~2000 | Weeks 1-2 | 2026-10-22: 2440, measured |
| 2 · Classical engine, 2800-3000 | Months 1-2 | Its search work was done on 2026-10-22; the network replaced PeSTO on 2026-10-23, so this band was passed with NNUE |
| 3 · Neural evaluation, 3200-3400 | Months 2-5 | 2026-10-23: 3150, measured; 2026-10-24: 3284, measured |
| 4 · Refinement, 3400-3500+ | Months 6-12+ | 2026-10-30: 3452, measured; 2026-10-31: 3499, measured; 2026-11-01: 3420 under CCRL-style conditions |
| 5 · The final gap, Stockfish level | A year or more | Not started |

The GPU tools generate training data and screen networks. GPU search tuning is paused after later
settings failed to transfer to CPU time-based tests; see [gpu/README.md](gpu/README.md).

The engine:

- **Moves:** magic-bitboard move generation, verified against known perft counts.
- **Interface:** UCI, for compatible chess GUIs. `Threads` runs Lazy SMP.
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
  - The default, net22-h768, was trained on 977.1M unique generation-10 positions from net14's
    GPU self-play. Training commands, hashes and results are in [nets/README.md](nets/README.md).
    External opening books are testing/start-position resources, not imported evaluation labels;
    the own-data policy does not claim independence from established evaluation methods.
  - The output layer is vectorized by hand (AVX2 and AVX-VNNI).
  - Ronald Friederich's PeSTO tables are the fallback; see [CREDITS.md](CREDITS.md).
- **GPU tools:** a CUDA port plays many independent games and generates training data. CPU/GPU
  output parity has been checked for particular revisions, networks and configurations; it is not
  a permanent guarantee that the two searches match. Historical throughput and calibration results
  are in [gpu/README.md](gpu/README.md). Fixed-node network screens still require CPU confirmation.
- **Bench:** `50868` nodes for the default build at the snapshot above. Match the source revision,
  network and bench settings when using this signature.

Research so far:

- **GPU SPSA produced one successful set of search constants.** The 2026-10-25 experiment tuned
  17 constants in 90 minutes at 50,000 nodes a move; the resulting settings passed a CPU SPRT at
  10+0.1, **+40.4 ± 11.7** Elo in 1,046 games. SPSA, its chess adaptation and fishtest's schedules
  are prior work. The log's historical “Novel” label refers to a candidate GPU workflow whose
  priority is unproven. This test does not establish an advantage over equal-cost CPU tuning or
  a gain in another engine. Later tuning did not transfer, and this path was paused on 2026-10-31.
- **An idea from Go transferred.** A training-only auxiliary head, dropped when the network is
  exported, gained **+53.2 ± 15.6** Elo and **+34.6 ± 12.2** on a second data snapshot. Ablations
  support the interpretation that an additional pure-search-score target helps; they do not
  establish a lookahead benefit. Originally labelled Novel, this was reclassified Partially known:
  KataGo and Lc0 provide auxiliary-learning precedents, including training-only Lc0 heads.
  The [research notes](docs/IDEAS.md#novel-ideas) describe the narrower proposed NNUE distinction
  and the limits of the prior-art search.
- **Newer data beat more data.** net12 trained only on net11's games, on 19% fewer positions than
  net11, and still gained **+32.1 ± 10.8** Elo over it. It changed both the data's age and its
  teacher, so it does not isolate recency.
- **The experiment log records passes, failures and inconclusive work,** with model attribution. Claude Code and Astra
  (GPT-6) have tested ideas side by side on the same PC, and Grok 4.7 (via Cursor) reviews plans
  on the coordination issue.

## Quick start

```
make              # build ./chesssi
make test         # move generation correctness
./chesssi bench   # speed and node-count signature
./chesssi         # UCI mode
```

## Credits and license

Read [CREDITS.md](CREDITS.md) for specific upstream contributions and
[the attribution review](docs/ATTRIBUTION_REVIEW.md) for unresolved provenance questions.
The project has an [MIT license](LICENSE); third-party material and dependencies retain their own
terms. The PeSTO source/license trail still needs resolution before claiming the whole distribution
is covered solely by MIT.

## Docs

- [AGENTS.md](AGENTS.md): how AI agents work on this repo (commands, layout, the test-and-log loop)
- [docs/PLAN.md](docs/PLAN.md): goals, roadmap, hardware, testing method
- [docs/IDEAS.md](docs/IDEAS.md): the benchmark log and the queue of ideas to try
- [docs/SETUP.md](docs/SETUP.md): setting up a machine to build, test and play
