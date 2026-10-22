# Ideas

## Benchmark log

Every idea tested, newest first, pass or fail. **Model** is the AI that proposed and wrote the change.
**Kind** distinguishes Known techniques from Novel proposals with checked prior art.
**Result** is Passed, Failed or Inconclusive. **Elo** is the SPRT estimate with its error bar.

| Date | Model | Kind | Idea | Result | Elo | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-22 | GPT-6 (Codex) | Known | Check evasions in quiescence | Failed | -11.83 +/- 8.36 | 4,026 (5 concurrent, CPUs 14-19, adjudication) |

Baseline before the first idea: bench `20648203`.

The qsearch test used normalized SPRT `[0,5]` at `10+0.1` against `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`; H0 was accepted with nElo -15.19 +/- 10.73 and printed LLR -2.95. The table gives the manager's logistic Elo estimate. One unpaired completed game is excluded. The experimental code was reverted and baseline bench `20648203` reverified. [Audited result and preserved diagnostics](research/codex-2026-10-22/qsearch.md#final-result). No prescreen was run.

What to watch over time:

- **Hit rate:** the share of ideas that pass. A rising hit rate means better judgment, not just faster code.
- **Elo per accepted idea** and **games per accepted change** show how efficient each model is.
- **New models:** when one ships, run the same loop and compare these numbers with earlier models.

## Queue

Known techniques, roughly in order of expected gain for this baseline. Each is one experiment. Take the
top one, test it, log it, then move on.

1. Killer moves (two quiet moves per ply that caused a beta cutoff)
2. History heuristic for quiet move ordering
3. Null-move pruning
4. Late move reductions
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
