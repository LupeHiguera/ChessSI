# Ideas

## Benchmark log

Every idea tested, newest first, pass or fail. **Model** is the AI that proposed and wrote the change.
**Kind** is Known (an existing technique, reimplemented) or Novel (not found in prior art: the
chessprogramming wiki, TalkChess, Stockfish's fishtest). Novel ideas are the real benchmark signal.
**Pre-screen** is the verdict and game count from `scripts/prescreen.sh` (2+0.02, loose SPRT); logging
it next to the full result shows whether the pre-screen can be trusted to drop ideas on its own.
**Result** is Passed, Failed or Inconclusive. **Elo** is the SPRT estimate with its error bar.

| Date | Model | Kind | Idea | Result | Elo | Games | Pre-screen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-21 | Claude Opus 5.5 | Known | Killer moves | Passed | +43.5 ± 14.2 | 1,332 (18 concurrent, no adjudication) | Passed, 364 games, +76.6 ± 27.5 |

Baseline before the first idea: bench `20648203`.

What to watch over time:

- **Hit rate:** the share of ideas that pass. A rising hit rate means better judgment, not just faster code.
- **Elo per accepted idea** and **games per accepted change** show how efficient each model is.
- **New models:** when one ships, run the same loop and compare these numbers with earlier models.
- **Novel ideas:** how many are proposed, how many pass, and their Elo. This is the closest measure of
  research ability rather than implementation speed.

## Queue

Known techniques, roughly in order of expected gain for this baseline. Each is one experiment. An
*italic name* marks an idea claimed by that agent (see "Sharing the PC" in `AGENTS.md`). Take the
top one, test it, log it, then move on.

1. Killer moves (two quiet moves per ply that caused a beta cutoff) - *Claude Code*
2. History heuristic for quiet move ordering - *Claude Code*
3. Null-move pruning - *Claude Code*
4. Late move reductions - *Claude Code*
5. Reverse futility pruning (static null move)
6. Aspiration windows
7. Late move pruning and futility pruning
8. Static exchange evaluation (SEE) for capture ordering and quiescence pruning
9. Check evasions in quiescence search
10. TT replacement by depth and age, and TT cutoffs in quiescence
11. Internal iterative reductions when there is no TT move
12. Mate distance pruning; insufficient-material draws
13. Time management: stop early when the best move is stable
14. Phase 3: self-play data generation and a first NNUE network (trainer on the RTX 5080)

## Novel ideas

The goal is to find out whether AI can improve on the state of the art, not just reproduce it. Known
techniques raise the baseline that novel ideas must beat; novel ideas are what the benchmark is about.
Any part of the project counts: search, evaluation, training, data, or the testing method itself.

Before testing a novel idea, check the prior-art sources above. If it turns out to exist, log it as
Known and note where it was found. Proposals:

- **Cheaper testing (methodology).** CPU time for SPRTs is the bottleneck. Ways to get more decisions
  per CPU hour count as research too: early adjudication of decided games (in `sprt.sh`), cheap
  pre-screening at very fast time controls (`scripts/prescreen.sh`, being validated), and testing several independent changes at once with a factorial design that
  separates their effects (verified against single-idea SPRTs before it is trusted).
- **GPU teacher for data (phase 3).** Data generation is CPU-bound. Train a larger network on the GPUs
  from our own games and use it to relabel positions in large batches, so the CPU plays games and the
  GPU supplies the evaluation targets.
- **Uncertainty-aware evaluation.** Train the network to also predict how unsure it is, and use that to
  set pruning margins and time use instead of fixed values.

## Measurements

Rating checks, not ideas: they change no code, get no SPRT and don't count toward the hit rate. Log
each result here with the date, the commit and its bench.

- **Gauntlet against rated engines,** after ideas 1-4 are tested. Play a few hundred games against 3-4
  open-source engines with known CCRL Blitz ratings, picked to sit above and below ChessSI, using
  `fastchess -tournament gauntlet` with the same book and time control as SPRTs. Fitting the scores
  to the opponents' ratings turns the strength estimate into a measured rating. Repeat after major
  milestones (end of phase 2, first NNUE) to chart progress.

| Date | Commit | Bench | Opponents | Games | Rating |
| --- | --- | --- | --- | --- | --- |
