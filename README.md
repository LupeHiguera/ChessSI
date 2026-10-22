# ChessSI
My own personal benchmark of AGI, building the best possible chess engine.

AI writes most of the code. Ideas are tested in controlled matches and logged, so the log measures
what each AI model can actually do in research.

## Status

Working engine, with classical search improvements underway. Accepted main `f801f8c` includes:

- Move generation with magic bitboards, verified against known perft counts
- UCI protocol, so it plays in any chess GUI
- Search: iterative deepening, principal variation search, transposition table, quiescence
- Killer moves, null-move pruning and late move reductions
- PeSTO piece-square evaluation (to be replaced by a neural network in phase 3)
- Accepted-main bench: `864538` nodes

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
- [Research status](docs/research/codex-2026-10-22/STATUS.md): measured outcomes, prepared tools and next decisions
- [docs/RESEARCH_WORKFLOW.md](docs/RESEARCH_WORKFLOW.md): turning ideas into controlled, reproducible research
- [docs/SETUP.md](docs/SETUP.md): setting up a machine to build, test and play
