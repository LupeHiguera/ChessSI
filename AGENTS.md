# Agent guide

Instructions for any AI coding agent working on this repo (Claude Code, Astra, or another). Read this file
first, then `docs/PLAN.md` for the why and `docs/IDEAS.md` for what to try next.

ChessSI is a chess engine built mostly by AI, used as a benchmark of what AI can do in research. The
code matters, but so does the record: **every idea is measured and logged, including the failures.**

## Commands

| Command | What it does |
| --- | --- |
| `make` | Build `./chesssi` (C++20, `-O3 -march=native`) |
| `make test` | Perft suite: move generation vs known node counts. Must print `0 failed` |
| `./chesssi bench` | Fixed-depth search over 14 positions; last line is `<nodes> nodes <nps> nps` |
| `make debug` | `./chesssi-debug` with AddressSanitizer + UBSan, for crashes |
| `scripts/sprt.sh [base-ref]` | SPRT the working tree against a git ref (default `HEAD`) with fastchess |

The engine speaks UCI on stdin. Extra commands: `perft <depth>`, `d` (show board), `eval`, `bench [depth]`.

## Layout

| File | Contents |
| --- | --- |
| `src/types.h` | Colors, pieces, squares (a1 = 0), 16-bit move encoding, score constants |
| `src/bitboard.*` | Attack tables, magic bitboards (found at startup with a fixed seed) |
| `src/position.*` | Board, FEN, `do_move`/`undo_move`, Zobrist keys, draw detection |
| `src/movegen.*` | Pseudo-legal move generation; `do_move` returns false for illegal moves |
| `src/eval.*` | PeSTO tapered piece-square tables (placeholder until NNUE) |
| `src/search.*` | Iterative deepening, PVS, TT, check extension, quiescence, time management |
| `src/tt.*` | Transposition table |
| `src/uci.*` | UCI loop, `bench`, `perftsuite` |
| `tests/perft.epd` | Known perft counts |
| `tests/rfp.cpp` | Boundary tests for reverse futility pruning, run by `make test` |

## The development loop

One idea per cycle. Do not batch ideas: a combined result says nothing about each one.

1. Pick the top idea from the queue in `docs/IDEAS.md`, or propose a new one. The project's real
   question is whether AI can find genuinely novel improvements, so look for those too (see
   "Novel ideas" in `docs/IDEAS.md`), and check prior art before calling an idea novel.
2. Implement the smallest version of it.
3. `make test` must pass. If the change should not alter search (refactor, speedup), the bench node
   count must be unchanged.
4. Run `scripts/sprt.sh` against the last accepted commit. Gainers use `ELO0=0 ELO1=5`; simplifications
   use `ELO0=-5 ELO1=0`.
5. Add a row to the log in `docs/IDEAS.md`, pass or fail: date, model, kind (Known or Novel), idea,
   result, Elo with its error bar, games. The model column names the AI that proposed and wrote the
   change. That column is the benchmark data, so fill it in honestly.
6. Passed: commit with the format below. Failed: revert the code, keep the log row.

Commit message for an accepted change:

```
Add null-move pruning

Elo: +38.2 +/- 9.1, 2,840 games, SPRT [0, 5] at 10+0.1
Bench: 20648203
```

`Bench:` is the node count from `./chesssi bench` after the change. Every commit carries one, so anyone can
check that a binary matches its source.

## Rules

- Never claim an Elo gain without an SPRT result. One game, or a handful, proves nothing.
- Never commit with `make test` failing.
- Keep each test on one machine and, where the OS allows, one core type (P-cores vs E-cores, Apple vs
  Intel). Under WSL, Windows moves engines between core types anyway, so record the concurrency used.
- Don't change the bench positions or depth without saying so in the commit; it resets the signature.
- Keep the search single-threaded until the roadmap calls for more. `Threads` exists only for OpenBench.
- Prefer measured simplicity: if removing code passes a `[-5, 0]` test, remove it.

## Sharing the PC

Several agents (Claude Code, Astra) may work on the 265K at once. It has 20 cores and plenty of RAM,
so the rules are about not disturbing each other's tests, not about scarcity.

**Each agent has its own folder and branch.** `scripts/sprt.sh` builds the "new" engine from the
working tree it runs in, so an edit saved into another agent's folder silently changes that agent's
test. Never edit files in another agent's folder.

| Agent | Folder | Branch prefix |
| --- | --- | --- |
| Claude Code | `ChessSI` | `claude/` |
| Astra | `ChessSI-astra` (a git worktree of the same repo) | `astra/` |

Accepted changes reach `main` through pull requests. Rebase onto `main` before starting a new test,
so every SPRT runs against the latest accepted engine.

**Cores are split, not shared.** Run tests inside WSL Ubuntu, pinned to your own cores with `CPUS`:

| Agent | Cores | Test command |
| --- | --- | --- |
| Claude Code | 0-13 | `CPUS=0-13 CONCURRENCY=13 scripts/sprt.sh` |
| Astra | 14-19 | `CPUS=14-19 CONCURRENCY=5 scripts/sprt.sh` |

Builds and other work count against your share too (`taskset -c 14-19 make -j6`, for example). If you
work outside WSL, keep the same total: at most 6 busy cores for Astra. When an agent has nothing
running, the other may borrow its cores for one test, but must say so in the log row's Games cell
(for example "1,240 (18 concurrent)").

**One idea per agent at a time.** Claim an idea before starting it by writing your name next to it in
the queue in `docs/IDEAS.md`, so two agents never test the same thing. Novel ideas are open to
everyone; claim them the same way.

**The log is shared.** Add rows only for your own tests, with your own model name, and keep them in
date order when merging.

The opening book and fastchess are shared and read-only: use `BOOK=` to point at another folder's
`books/` rather than downloading a second copy.
