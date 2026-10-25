"""Fixed-node matches between two networks on the GPU (issue #31): ChessSI's exact search (gpu/datagen.cu)
playing both sides of thousands of games at once.

    python gpu/match.py <netA.nnue> <netB.nnue> <pairs> [nodes=20000] [seed=1] [book=books/UHO_Lichess_4852_v1.epd]

Each opening from the book is played twice, A with White and then with Black. Games end like our
fastchess SPRTs (see match_step). Prints A's score, Elo with a 95% interval from the game pairs
(pentanomial), and the SPRT [0, 5] log-likelihood ratio. Both networks must have the same hidden size.
A fixed node count leaves out speed, so this suits networks of one size; time-based SPRTs remain the
test for anything that changes speed.
"""
import math
import os
import random
import sys
import time

import cupy as cp
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from datagen import GpuDatagen, compact, load_net  # noqa: E402

TT_BITS = 16


def elo_from_score(s):
    s = min(max(s, 1e-6), 1 - 1e-6)
    return -400 * math.log10(1 / s - 1)


def score_from_elo(e):
    return 1 / (1 + 10 ** (-e / 400))


def pentanomial_stats(pair_scores, elo0=0.0, elo1=5.0):
    """Elo, its 95% half-width and the GSPRT log-likelihood ratio, from pair scores in {0, .5, 1, 1.5, 2}."""
    x = np.asarray(pair_scores) / 2  # mean game score of each pair
    n = len(x)
    mu, var = x.mean(), x.var(ddof=0)
    se = math.sqrt(var / n) if n > 1 else float("nan")
    elo = elo_from_score(mu)
    # Delta method: d(elo)/d(score) = 400 / (ln 10 * s * (1 - s)).
    half = 1.96 * se * 400 / (math.log(10) * mu * (1 - mu)) if 0 < mu < 1 else float("nan")
    s0, s1 = score_from_elo(elo0), score_from_elo(elo1)
    llr = n * ((mu - s0) ** 2 - (mu - s1) ** 2) / (2 * var) if var > 0 else float("nan")
    return elo, half, llr


def main():
    net_a, net_b, pairs = sys.argv[1], sys.argv[2], int(sys.argv[3])
    nodes = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    book = sys.argv[6] if len(sys.argv) > 6 else os.path.join(HERE, "..", "books", "UHO_Lichess_4852_v1.epd")
    ha, hb = load_net(net_a)[0], load_net(net_b)[0]
    assert ha == hb, "both networks need the same hidden size"
    lines = [l.strip() for l in open(book) if l.strip()]
    rng = random.Random(seed)
    openings = [" ".join(lines[rng.randrange(len(lines))].split()[:6]) for _ in range(pairs)]  # with move counters
    n = 2 * pairs
    dg = GpuDatagen(net_a, n)  # compiles the kernels and allocates games; its TTs serve network A
    _, ftw, ftb, outw, outb = load_net(net_b)
    b = (cp.asarray(ftw), cp.asarray(ftb), cp.asarray(outw), np.int32(outb))
    a = (dg.ftw, dg.ftb, dg.outw, np.int32(dg.outb))
    tts_b = cp.zeros(n * (1 << TT_BITS) * 16, cp.uint8)
    k = {name: dg.mod.get_function(name) for name in ("match_init", "match_setup", "match_step", "match_results")}
    start = cp.asarray(np.stack([compact(openings[i // 2]) for i in range(n)]))
    a_color = cp.asarray(np.array([i % 2 for i in range(n)], np.int32))  # A has White in even games
    threads, warps = ((n + 127) // 128,), ((n + 3) // 4,)
    slots = cp.arange(n, dtype=cp.int32)
    k["match_init"](threads, (128,), (dg.games, slots, np.int32(n), start, a_color))
    k["match_setup"](warps, (128,), (slots, np.int32(n), dg.tts, tts_b))
    res = cp.full(n, -1, cp.int32)
    t0, steps = time.perf_counter(), 0
    while True:
        k["match_step"](warps, (128,), (dg.games, np.int32(n)) + a + b + (dg.params, dg.params, np.int32(0), dg.accs, dg.tts, tts_b,
                                                                          np.uint64(nodes), dg.budget))
        steps += 1
        if steps % 8 == 0:
            k["match_results"](threads, (128,), (dg.games, np.int32(n), res))
            if int((res >= 0).sum()) == n:
                break
    secs = time.perf_counter() - t0
    r = res.get()  # 0 Black won, 1 draw, 2 White won
    white_score = r / 2.0
    a_score = np.where(np.arange(n) % 2 == 0, white_score, 1 - white_score)
    pair_scores = a_score[0::2] + a_score[1::2]
    wins, draws, losses = int((a_score == 1).sum()), int((a_score == 0.5).sum()), int((a_score == 0).sum())
    penta = [int((pair_scores == v).sum()) for v in (0, 0.5, 1, 1.5, 2)]
    elo, half, llr = pentanomial_stats(pair_scores)
    print(f"{os.path.basename(net_a)} vs {os.path.basename(net_b)}, {nodes} nodes a move, {n} games ({pairs} pairs) "
          f"in {secs:.0f} s ({steps} steps)")
    print(f"A: +{wins} ={draws} -{losses}, score {a_score.mean():.3f}; pairs {penta}")
    print(f"Elo {elo:+.1f} +/- {half:.1f} (95%), LLR {llr:.2f} for SPRT [0, 5] (bounds -2.94, 2.94)")


if __name__ == "__main__":
    main()
