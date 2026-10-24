# Networks

Every network ChessSI has used as its default, newest first. All are trained only on ChessSI's own
games and searches (see the rules in `AGENTS.md`). The default is the Makefile's `EVALFILE`; any file
here can also be loaded with `setoption name EvalFile value <path>`.

Architecture so far: (768 → H) × 2 perspectives → SCReLU → 1, quantised with QA = 255, QB = 64, eval
scale 400 (format in `nnue/train.py`).

## net9-h256.nnue

- **SHA-256:** `98971f10c9c6dff1c4370c1014766a3a0ea664b831897988e20f5f7208ee0f61`
- **Data:** 119,776,920 unique positions from 1,438,775 games, all self-play (no games against other
  engines):
  - 37.2M generation-1 positions: `chesssi datagen` at `d574e70` (PeSTO), 5,000 nodes a move.
  - 12.4M generation-2 positions: `chesssi datagen` at `fb4d163` (net4), same settings.
  - 26.8M generation-3 positions: `chesssi datagen` at `d243d1c` (net6), same settings.
  - 49.9M generation-4 positions: `chesssi datagen` at `d2ac8e0` (net7), same settings.
  - 4.1M generation-5 positions: `chesssi datagen` at `d2b1e25` (net8), same settings.
  - 2.6M positions from SPRT games, as for net4.
- **Training:** net8's recipe: `train.py <data files> net9-h256.nnue --hidden 256 --epochs 20 --seed 1
  --cache-dir <dir> --frozen --aux-weight 1.0 --future-plies 4 --gpu-data-gb 12` at `e525275`. That
  is the first network with deterministic deduplication keys and the stable validation split (2% of
  games, chosen by game key). Validation loss is 0.00684 on that split. It took 27 minutes on an
  RTX 5080.
- **Result:** replaced net8, +48.4 ± 14.3 Elo, SPRT [0, 5] at 10+0.1, H1 after 1,062 games (both
  networks loaded in the same binary, 12 concurrent).

## net8-h256.nnue

- **SHA-256:** `9a758cab4248b12f619401bff1b483eba1326dbd4ed0ef9f3f175abb8c36d536`
- **Data:** 91,302,005 unique positions from 1,088,953 games, all self-play (no games against other
  engines):
  - 37.2M generation-1 positions: `chesssi datagen` at `d574e70` (PeSTO), 5,000 nodes a move.
  - 12.4M generation-2 positions: `chesssi datagen` at `fb4d163` (net4), same settings.
  - 26.8M generation-3 positions: `chesssi datagen` at `d243d1c` (net6), same settings.
  - 20.3M generation-4 positions: `chesssi datagen` at `d2ac8e0` (net7), same settings.
  - 2.6M positions from SPRT games, as for net4.
- **Training:** net7's recipe on all of it: `train.py <data files> net8-h256.nnue --hidden 256
  --epochs 20 --seed 1 --cache-dir <dir> --frozen --aux-weight 1.0 --future-plies 4` at `a74d12b`.
  The data files were cached once first, so every net8 variant saw the same snapshot. Validation
  loss is 0.00674 on 2% of games. It is not comparable with net7's 0.00653, because the validation
  games now include generation 4. It took 27 minutes on an RTX 5080.
- **Result:** replaced net7, +43.1 ± 13.2 Elo, SPRT [0, 5] at 10+0.1, H1 after 1,208 games (both
  networks loaded in the same binary).

## net7-h256-aux4.nnue

- **SHA-256:** `5dba29c15af3c59d34e6576f5c12e578fcc49de31de3fb2e010764b46198d89a`
- **Data:** 64,580,897 unique positions from 780,804 games, all the data so far:
  - 37.2M generation-1 positions: `chesssi datagen` at `d574e70` (PeSTO), 5,000 nodes a move.
  - 12.4M generation-2 positions: `chesssi datagen` at `fb4d163` (net4), same settings.
  - About 18.6M generation-3 positions: `chesssi datagen` at `d243d1c` (net6), same settings.
  - 2.6M positions from SPRT games, as for net4.
- **Training:** `train.py <data files> net7-h256-aux4.nnue --hidden 256 --epochs 20 --seed 1
  --cache-dir <dir> --aux-weight 1.0 --future-plies 4` at `cd3fafd`. As for net6, but the auxiliary
  head predicts the win probability 4 plies ahead, the best horizon in the sweep logged in
  `docs/IDEAS.md`. Validation holds out 2% of games, with loss 0.00653. It took 12 minutes on an
  RTX 5080.
- **Result:** replaced net6, +103.7 ± 21.8 Elo, SPRT [0, 5] at 10+0.1, H1 after 628 games (both
  networks loaded in the same binary).

## net6-h256-aux.nnue

- **SHA-256:** `2f100aa621e4a8e109e6c36cb7068fbcc3a3f0352921292a5bdcf4e3762bf7ea`
- **Data:** 38,539,931 unique positions from 475,769 games, out of 42.5M raw:
  - 37.2M generation-1 positions: `chesssi datagen` at `d574e70` (PeSTO), 5,000 nodes a move.
  - 2.7M generation-2 positions: `chesssi datagen` at `fb4d163` (net4), same settings.
  - 2.6M positions from SPRT games, as for net4.
- **Training:** `train.py <data files> net6-h256-aux.nnue --hidden 256 --epochs 20 --seed 1
  --cache-dir <dir> --aux-weight 1.0` at `2efdfb4`. Training adds an auxiliary head, which isn't
  exported: it predicts the win probability 8 plies later in the same game. Validation holds out 2%
  of games, with loss 0.00661. It took 6 minutes on an RTX 5080.
- **Result:** replaced net4, +138.6 ± 24.7 Elo, SPRT [0, 5] at 10+0.1, H1 after 496 games (both
  networks loaded in the same binary).

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
