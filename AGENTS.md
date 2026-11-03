# Agent guide

Instructions for any AI coding agent working on this repo (Claude Code, Astra, or another). Read this file
first, then `docs/PLAN.md` for the why and `docs/IDEAS.md` for what to try next.

ChessSI is a chess engine developed mostly with AI assistance, used to study AI-assisted research.
It builds on established computer-chess work; see `CREDITS.md`. The code matters, but so does the
record: **log every experiment, including failures, offline gates and tests stopped without a result.**

## Commands

| Command | What it does |
| --- | --- |
| `make` | Build `./chesssi` (C++20, `-O3 -march=native`) |
| `make test` | Perft suite: move generation vs known node counts. Must print `0 failed` |
| `./chesssi bench` | Fixed-depth search over 14 positions; last line is `<nodes> nodes <nps> nps` |
| `make debug` | `./chesssi-debug` with AddressSanitizer + UBSan, for crashes |
| `scripts/sprt.sh [base-ref]` | SPRT the working tree against a git ref (default `HEAD`) with fastchess |
| `scripts/run-idea.sh <name>` | The whole loop for one idea: perft, bench, pre-screen, then the full SPRT unless the pre-screen rejects it |
| `scripts/nnue-sprt.sh <new.nnue> <base.nnue>` | SPRT two networks in one binary built from `REF` (default `HEAD`); `NAME` lets several run at once |
| `scripts/datagen.sh <gen> "<cores>"` | Self-play training data, one process per core, from `REF`; `scripts/datagen.sh stop` stops it |
| `scripts/idea-queue.sh <queue-file>` | `run-idea.sh` for each `<branch> [base-ref]` line in turn, rebased onto the base in its own worktree, and `nnue-sprt.sh` for each `nnue <name> <new> <base>` line; re-reads the file between tests; summaries in `engines/queue.log` |
| `scripts/gauntlet.sh` | Rate `HEAD` against engines with known CCRL ratings |

The engine speaks UCI on stdin. Extra commands: `perft <depth>`, `d` (show board), `eval`, `bench [depth]`.

## Layout

| File | Contents |
| --- | --- |
| `src/types.h` | Colors, pieces, squares (a1 = 0), 16-bit move encoding, score constants |
| `src/bitboard.*` | Attack tables, magic bitboards (found at startup with a fixed seed) |
| `src/position.*` | Board, FEN, `do_move`/`undo_move`, Zobrist keys, draw detection |
| `src/movegen.*` | Pseudo-legal move generation; `do_move` returns false for illegal moves |
| `src/eval.*` | Evaluation entry point; PeSTO tables when no network is loaded |
| `src/nnue.*` | NNUE inference; `Position` keeps incrementally updated accumulators |
| `src/datagen.*` | Self-play training data (`chesssi datagen`) |
| `nnue/` | PyTorch trainer and inference check (`train.py`, `check_inference.py`) |
| `nets/` | Networks; the Makefile's `EVALFILE` picks the default, `nets/README.md` logs each one |
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
- Test search changes with `Threads` at 1, its default, so results stay comparable. Since 2026-10-24 more
  threads use Lazy SMP (owner's decision); test changes to it with several threads per engine and record
  the threads used.
- Prefer measured simplicity: if removing code passes a `[-5, 0]` test, remove it.
- Networks are trained only on ChessSI's own games and searches: no external datasets, networks or
  engine evaluations. Games ChessSI plays against other engines count, but only its own side of
  them: positions where ChessSI is to move, labelled with its own search score and the game result.
  The opponent's evaluations are never used (owner's decision, 2026-10-23). A new network is tested
  like any other change, by SPRT against the current default, and gets an entry in `nets/README.md`
  (data, training command, result).

## Attribution and public claims

- Read `CREDITS.md` and `docs/ATTRIBUTION_REVIEW.md` before adding externally sourced work.
- For each borrowed technique, record its source and authors. For copied or adapted code, tables,
  data or assets, also record the exact upstream revision/path, what changed, license and required
  notices. Add the credit beside the relevant code or documentation and to `CREDITS.md`.
- Distinguish an idea/reference from copied or adapted material. Renaming, translating or having
  an AI rewrite material does not establish independent authorship. Do not assume a permissive
  license because a source is public or another engine uses it. Record unresolved provenance.
- Model attribution records who proposed/wrote the ChessSI change. It does not replace credit to
  the original method's authors. Preserve other contributors' experiment rows and numerical results;
  add dated corrections when an interpretation or prior-art classification changes.
- “Novel” is provisional: record the precise proposed difference, sources searched, date and gaps.
  An SPRT proves neither priority nor transfer to other engines. Prefer “adaptation” when appropriate.
- Public strength claims must identify the tested revision/network, conditions, games and uncertainty.
  Do not add SPRT gains to infer a rating, label a local estimate an official CCRL result, or present
  the experiment log as a controlled comparison of AI models.

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

**One session per branch.** The same agent may also run elsewhere, such as Claude Code in a cloud
container. Each session pushes only to its own branch (for example `claude/cloud-<topic>`), so a push
from one never lands under a test running in another. Fetch `main` before each new test.

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
