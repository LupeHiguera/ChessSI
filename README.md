# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Every idea is tested with thousands of games and logged, so the log measures
what each AI model can actually do in research.

## Status

Phase 1 of 5 (working engine). Done so far:

- Move generation with magic bitboards, verified against known perft counts
- UCI protocol, so it plays in any chess GUI
- Baseline search: iterative deepening, principal variation search, transposition table, quiescence
- NNUE evaluation trained only on ChessSI's own self-play (`nets/`), with PeSTO tables as the fallback
- Bench: `151950` nodes

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
