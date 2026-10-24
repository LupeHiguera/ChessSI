# Novel Elo ideas for ChessSI (research, 2026-10-24)

A deep-research pass made in a cloud Claude Code session: five research agents covered NNUE training
methods, self-play data, search, testing efficiency and network architecture, and a sixth wrote the
combined report. It proposes experiments; nothing here has been tested in games.

| Path | Contents |
| --- | --- |
| `report.md` | The ranked report: prior-art verdicts, expected Elo and cost per idea, the Known gaps to close first, six suggested relabels for the log's Kind column, and a 24-step plan for the main PC |
| `notes/` | The five topic notes the report draws on, with the per-idea cards (mechanism, cost, minimal experiment, risks) and links to the exact commits checked |
| `sim/` | The simulation and retrospective scripts behind the testing-efficiency numbers |

How to read it:

- **"Novel" means not found in the sources the agents could reach**: the source of nnue-pytorch, bullet,
  the Lc0 and KataGo trainers and about ten open engines, plus web searches. TalkChess, arXiv and most
  chessprogramming wiki pages were blocked and seen only through search snippets; Discord and fishtest's
  history were not searched. Check those before logging an idea as Novel.
- **Every Elo figure is a prior, not a measurement.** Ideas still go through the loop in `AGENTS.md`:
  claim, test, log.
- **The testing-efficiency figures come from Gaussian simulations** and a retrospective on 1,027 game
  pairs, not the PC's full set of saved games.
- **Two suggestions need the owner's approval:** raising SPRT beta to 0.2 (or an expected-loss stopping
  rule), and adding a "Partially known" value to the Kind column.

Running the scripts (Python 3 with NumPy):

```
python3 sim/more_sims.py                          # SPRT vs beta 0.2 vs expected-loss stopping; factorial check
python3 sim/fact_ppi.py                           # complementary-pair factorial vs separate SPRTs
python3 sim/sprt_vs_2sprt.py                      # SPRT vs Lorden's 2-SPRT
python3 sim/retro_adjudication.py <games.pgn>     # opening bands, nearly-decided games (fastchess PGN, 10+0.1)
python3 sim/retro_twophase.py <games.pgn>         # truncate-and-subsample retrospective
```
