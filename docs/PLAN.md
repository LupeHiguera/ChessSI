# Plan of attack

**Updated interpretation and owner constraints, 2026-11-02:** the roadmap and original hardware
estimates below are historical planning assumptions, not measured forecasts. Current scope is two
PCs with two GPUs total. The owner is deferring promotional outreach until a reproducible 3700+
estimate on a stated rating scale; this is not a CCRL entry requirement. See the current
[README](../README.md), [experiment log](IDEAS.md) and [credits](../CREDITS.md).

Repo copy of the "Chess Engine Plan of Attack" doc (2026-10-21), so every agent can read it.

## Goal and success criteria

Build a chess engine with AI doing most of the development, and use it as a personal benchmark of what AI
can actually do in research.

- **Reproducing the state of the art:** getting close to top engines with known techniques (neural
  evaluation, modern search pruning). This shows AI can implement known methods quickly, not that it found
  new ones.
- **A research contribution:** identify a precise difference from prior work, document the search for
  precedents, and test the mechanism with appropriate controls. A gain in another strong engine would
  support transfer, but would not by itself prove novelty. Outscoring Stockfish is a separate strength goal.
- **Evidence:** use the documented SPRT for strength changes and report its conditions and uncertainty.
  Single wins and short match anecdotes do not establish a reliable advantage.

Stockfish is a comparison target and an important source of prior work, alongside other engines.
Credit the developers and researchers whose methods make this project possible; implementation
speed does not establish independent invention or general AI capability.

## Roadmap

| Phase | When | Work | Rough rating |
| --- | --- | --- | --- |
| 1 · Working engine | Weeks 1–2 | Move generation, UCI, basic search | ~2000 |
| 2 · Classical engine | Months 1–2 | Caching, move ordering, pruning, tuned evaluation | ~2800–3000 |
| 3 · Neural evaluation | Months 2–5 | Self-play data, networks trained on the RTX 5080 | ~3200–3400 |
| 4 · Refinement | Months 6–12+ | Parameter tuning, bigger networks, more data | ~3400–3500+ |
| 5 · The final gap | 1 year+ | The last 100–200 Elo, where strong engines stall | Stockfish level |

AI speeds up the coding in phases 1–2; from phase 3 on, compute sets the pace. Ratings are rating-list Elo
and ballpark only.

## Hardware

| Machine | Role |
| --- | --- |
| Core Ultra 7 265K (20 cores) | Test matches and training-data games, ~2,000–3,000 fast games an hour |
| RTX 5080 | Main network trainer |
| RTX 5060 Ti | Second training run or experiments |
| MacBook Pro M2 Max | Extra test capacity, about half a 265K |
| Second 265K (optional) | Build only once tests sit queued for days |

At 60 hours a week the 265K plays about 100,000–150,000 fast games (10+0.1) or 15,000–25,000 long games
(60+0.6). Resolution: 1,000 games ≈ ±20 Elo, 10,000 ≈ ±7, 100,000 ≈ ±2.

## Testing method

- **Self-play SPRT** of each change against the previous version at 10+0.1; confirm winners at 60+0.6.
- **OpenBench** to pool every machine once more than one is testing.
- **Consistent hardware:** one machine and core type per test, or fixed node counts.
- **Paired openings:** play each opening with colors reversed. UHO deliberately uses unbalanced
  positions; color pairing does not make the positions themselves balanced. The rating gauntlet
  uses the separate 8moves_v3 book. Record the book and settings for each test.
- **Right opponents:** engines near our level, or Stockfish with limited strength, until we are close.

## Next steps

- [x] Set up the engine repository
- [x] Write move generation and verify it against known position counts (`make test`)
- [x] Add UCI and a basic search
- [ ] Set up Claude Code (and Astra) on the 265K; build and play the first games
- [ ] Install fastchess and the opening book; run the first SPRT (`scripts/sprt.sh`)
- [ ] Install OpenBench and connect the PC, then the MacBook
- [ ] Start the benchmark log and record every idea from the first change (`docs/IDEAS.md`)
- [ ] Revisit the second PC once tests sit queued for days
