# Recent evidence relevant to ChessSI

Reviewed by GPT-6 (Codex), 2026-10-22 UTC. These are external findings and proposed implications, not ChessSI results. This note supplements the detailed search, evaluation and testing proposals without changing the active experiment or the queue's ownership.

## The current target keeps improving

Stockfish 19 was released on 2026-09-05. Its developers report up to 44 Elo over Stockfish 18. The release uses SFNNv16, adds pawn-pair inputs, removes redundant threat features and retires the secondary small network. Its training includes quantization-aware training and hundreds of billions of positions rescored with Leela. These are the project's claims under its testing conditions, not ratings measured on this PC. [Official release](https://stockfishchess.org/blog/2026/stockfish-19/)

**Implication for this project:** record an exact target version, network, hardware and time control when measuring the gap. A result against an older or node-limited Stockfish is a useful intermediate measurement, but cannot stand in for matching the current unrestricted release. Known improvements remain useful; a calendar forecast still needs a measured ChessSI learning curve.

## A small training run is encouraging, with a bounded claim

Braun's September 2026 preprint reports a 6.32-million-parameter player trained for 2.5 days on an eight-GPU node. Its reported 3,251 benchmark Elo comes from a fixed-node Stockfish 13 ladder, with 100 games per tested operating point, rather than unrestricted current Stockfish. The $43.20 quoted rental cost excludes development and evaluation. [Paper, sections 2 and 9](https://arxiv.org/html/2609.37447v1)

The same paper reports that a learned search allocator improved deep-policy agreement but its online training attempts trailed controls by roughly 60-100 ladder Elo. A separate stopper removed about 14% of nominal search yet improved generation cadence only about 3%, because search overlapped training. [Paper, section 4.1.3](https://arxiv.org/html/2609.37447v1#S4.SS1.SSS3)

**Implication for the proposed label pilot:** its signed reference-relative loss is an initial screen. If it passes, freeze the selector and compare two identical small evaluator training runs: selected deeper labels versus the best simple equal-budget control. Use identical initial weights, sample counts and optimizer schedules, and charge selector fitting and label generation. Evaluate on untouched grouped positions, then in games. Improvement in label agreement alone cannot accept the selector. Measure elapsed time for the entire data-to-trained-model cycle before claiming a practical saving.

## Harder self-play already has direct prior art

Joshi's 2025 search-contempt paper uses asymmetric MCTS to seek positions a shallow opponent can mishandle. Its regular-chess comparison reports 37 wins, 46 draws and 17 losses against a temperature-based control, at 1,000 visits per move and matched approximate decisiveness. The 100-game experiment compares game-generation policies. The suggested standard-chess training schedule is prospective; it does not establish a completed consumer-GPU training run matching current Stockfish. [Paper, sections 4.2.3-4.2.5](https://arxiv.org/html/2504.07757v1)

**Implication for novelty:** actively generating examples that exploit the current evaluator's weaknesses is a Known broad direction. A future ChessSI version would need a precise mechanism and comparison with temperature, random restarts and ordinary disagreement sampling. Greater tactical variety or a preferred win/draw/loss ratio is not itself proof of better learning. Defer implementation until the engine has a functioning training pipeline and a measured baseline.

## What these findings change now

1. Keep each active engine experiment and its strength test separate from speculative training work.
2. Retain the label pilot as an inexpensive rejection test, with downstream learning and playing-strength gates already required by the workflow.
3. Treat end-to-end throughput, data quality and the cost of failed development attempts as measurements, not incidental details.
4. Use these studies to narrow claims and improve experiments; do not extrapolate their hardware, costs or historical rating scales into a Stockfish-matching date for this repository.
