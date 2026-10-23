# Networks

Every network ChessSI has used as its default, newest first. All are trained only on ChessSI's own
games and searches (see the rules in `AGENTS.md`). The default is the Makefile's `EVALFILE`; any file
here can also be loaded with `setoption name EvalFile value <path>`.

Architecture so far: (768 → H) × 2 perspectives → SCReLU → 1, quantised with QA = 255, QB = 64, eval
scale 400 (format in `nnue/train.py`).

## net4-h256.nnue

- **SHA-256:** `9d8d6c3a10f973573fe3f7d4b98c6691717f5baf5af3b24d8af1ab00d9f29e50`
- **Data:** 17,487,612 unique positions.
  - 2.5M from the PGNs of 32,743 SPRT and pre-screen games between ChessSI development versions, with
    each move's search score (`nnue/extract_pgn.py`).
  - 15M from `chesssi datagen` built at `d574e70`, run on 8 cores. That is fixed-node self-play at
    5,000 nodes a move, after 8 random plies, using PeSTO. It skips positions in check, positions
    with a noisy best move and mate scores.
- **Training:** `train.py <data files> net4-h256.nnue --hidden 256 --epochs 30` at `90f3abe`. That
  means λ = 0.75 (search score) and 0.25 (game result), Adam at lr 0.001 with a cosine schedule,
  batch 16,384 and seed 1. Validation is a random 2% of positions, with loss 0.00605. It took 13
  minutes on an RTX 5080.
- **Result:** replaced PeSTO, +203.3 ± 33.2 Elo, SPRT [0, 5] at 10+0.1, H1 after 416 games (same
  binary, network loaded vs not).
