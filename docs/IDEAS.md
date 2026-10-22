# Ideas

## Benchmark log

Every idea tested, newest first, pass or fail. **Model** is the AI that proposed and wrote the change.
**Result** is Passed, Failed or Inconclusive. **Elo** is the SPRT estimate with its error bar.

| Date | Model | Idea | Result | Elo | Games |
| --- | --- | --- | --- | --- | --- |

Baseline before the first idea: bench `20648203`.

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
