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
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (updated main; LTC 60+0.6) | Inconclusive | Not established (deadline) | 146 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (updated main; STC only) | Passed | +68.00 +/- 16.54 | 802 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | Null-move pruning (R = 3 + depth/6, needs non-pawn pieces and static eval >= beta) | Passed | +157.1 ± 27.0 | 472 (13 concurrent) | Passed, 310 games, +107.5 ± 35.2 |
| 2026-10-22 | Claude Opus 5.5 | Known | Late move reductions (log table, quiet moves after the third, re-search on fail high) | Passed | +83.7 ± 19.4 | 732 (13 concurrent) | Passed, 284 games, +107.3 ± 32.2 |
| 2026-10-21 | Claude Opus 5.5 | Known | Killer moves | Passed | +43.5 ± 14.2 | 1,332 (18 concurrent, no adjudication) | Passed, 364 games, +76.6 ± 27.5 |
| 2026-10-21 | Claude Opus 5.5 | Known | History heuristic (gravity, bonus min(d², 1200), malus on earlier quiets) | Failed | −2.7 ± 4.7 | 11,690 (13 concurrent) | Inconclusive at 600-game cap, −23.8 ± 20.5 |

Baseline before the first idea: bench `20648203`.

The STC RFP row is an audited short-time result against `f801f8c519b0fe5b3d009b8f0664b049409a1188`: normalized SPRT `[0,5]` at `10+0.1`, explicit H1, nElo +101.49 +/- 24.05. All 802 saved games / 401 pairs and 41 reports reconciled; no completed unpaired games. Candidate bench is `609035`. Independent `60+0.6` confirmation ended Inconclusive at the fixed 2026-10-22 19:53 UTC deadline, without an SPRT decision; this branch remains an unpromoted candidate in [draft PR #4](https://github.com/LupeHiguera/ChessSI/pull/4). The complete research record preserves prior failed and separate-baseline trials in [draft PR #2](https://github.com/LupeHiguera/ChessSI/pull/2), including the [audited result](https://github.com/LupeHiguera/ChessSI/blob/9a225affadc45ee8c52019f89d46dceb4645472a/docs/research/codex-2026-10-22/rfp.md#final-result-on-updated-main).

The separate LTC run saved and counted 146 games / 73 complete pairs: 48 wins, 28 losses and 70 draws, with no completed unpaired games. Unfinished games 147-151 are excluded. Independent replay reconciled all 146 games, 17,375 legal plies and seven reports without issues. The guard sent SIGINT at 19:53:00.007678 UTC; the manager ended at 19:53:01.521443 UTC, with no binary drift. The last printed Elo estimate covered 138 games and is not assigned to the final 146-game count. Neither this deadline stop nor the earlier STC pass establishes LTC acceptance. [LTC terminal evidence](https://github.com/LupeHiguera/ChessSI/tree/astra/research-workflow/docs/research/codex-2026-10-22/evidence/rfp-current-main-ltc-terminal).

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
5. Reverse futility pruning (static null move) - *Astra / GPT-6 (Codex)*
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
