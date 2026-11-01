"""An SPRT on the GPU (issue #31, testing): a change against its base at a fixed node count, game pairs streamed
through the GPU until the log-likelihood ratio crosses a bound.

    python gpu/sprt.py <netA.nnue> <netB.nnue> [nodes=50000] [elo0=0] [elo1=5] [max pairs=20000]
                       [games at once=2w] [seed=1] [book=books/UHO_Lichess_4852_v1.epd]

A is the change: network A with the search constants GPU_PARAMS (JSON, as gpu/spsa.py prints them); B is the
base: network B with GPU_PARAMS_B (A's if unset). nodes may be "<A>:<B>" for node odds, as in gpu/match.py, which
also lets networks of different sizes play (one kernel build per side).

Each opening is played twice, A with White and then with Black. A finished game's slot takes the next game at
once, so the GPU stays full. The test is a GSPRT on the pair scores (pentanomial, as gpu/match.py), alpha =
beta = 0.05, in logistic Elo. Games finish out of order (short decisive games first), so only the unbroken
prefix of pairs, in the order they started, counts: an early stop sees exactly the pairs a sequential test
would have seen.

Fixed nodes leave speed out: a change that makes the search slower per node is not charged for it here.
GPU_BUDGET (default 20,000 here) caps the nodes per launch to keep launches under the Windows watchdog.
"""
import collections
import math
import os
import random
import sys
import time

import cupy as cp
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("GPU_BUDGET", "20000")  # read by GpuDatagen
from datagen import compact, wait  # noqa: E402
from match import Sides, pentanomial_stats  # noqa: E402

ALPHA = BETA = 0.05
LOWER, UPPER = math.log(BETA / (1 - ALPHA)), math.log((1 - BETA) / ALPHA)


def main():
    a = sys.argv[1:]
    net_a, net_b = a[0], a[1]
    nodes = a[2] if len(a) > 2 else "50000"
    elo0 = float(a[3]) if len(a) > 3 else 0.0
    elo1 = float(a[4]) if len(a) > 4 else 5.0
    max_pairs = int(a[5]) if len(a) > 5 else 20000
    capacity = a[6] if len(a) > 6 else "2w"
    seed = int(a[7]) if len(a) > 7 else 1
    book = a[8] if len(a) > 8 else os.path.join(HERE, "..", "books", "UHO_Lichess_4852_v1.epd")
    lines = [l.strip() for l in open(book) if l.strip()]
    rng = random.Random(seed)

    sides = Sides(net_a, net_b, capacity, nodes)
    n = sides.n

    queue = collections.deque()  # games waiting for a slot: (pair, A's color, opening)
    slot_game = [None] * n       # (pair, A's color) of the game in each slot, None when idle
    points = {}                  # pair -> A's points in its finished games
    finished = {}                # pair -> A's points over the pair (0 to 2), until the prefix reaches it
    scores = []                  # pair scores of the unbroken prefix, in start order
    started, stopping = 0, False

    def fill(slots):
        nonlocal started
        used, fens, colors = [], [], []
        for s in slots:
            if not queue and not stopping and started < max_pairs:
                started += 1
                fen = " ".join(lines[rng.randrange(len(lines))].split()[:6])  # with move counters
                queue.extend([(started, 0, fen), (started, 1, fen)])
            if not queue:
                slot_game[s] = None
                continue
            pair, color, fen = queue.popleft()
            slot_game[s] = (pair, color)
            used.append(s)
            fens.append(fen)
            colors.append(color)
        if not used:
            return
        sides.start(cp.asarray(np.array(used, np.int32)), cp.asarray(np.stack([compact(f) for f in fens])),
                    cp.asarray(np.array(colors, np.int32)))

    def report(final=False):
        elo, half, llr = pentanomial_stats(scores, elo0, elo1) if len(scores) > 1 else (0.0, float("nan"), 0.0)
        x = np.asarray(scores)
        penta = [int((x == v).sum()) for v in (0, 0.5, 1, 1.5, 2)]
        secs = time.perf_counter() - t0
        print(f"{'final ' if final else ''}pairs {len(scores)} ({2 * len(scores) / secs:.1f} games/s, {secs:.0f} s) | "
              f"Elo {elo:+.1f} +/- {half:.1f} | LLR {llr:.2f} ({LOWER:.2f}, {UPPER:.2f}) [{elo0:g}, {elo1:g}] | "
              f"pairs {penta}", flush=True)
        return llr

    print(f"GPU SPRT [{elo0:g}, {elo1:g}]: {os.path.basename(net_a)} (A, GPU_PARAMS) vs {os.path.basename(net_b)} "
          f"(B, GPU_PARAMS_B), {sides.describe()}, {n} games at once, at most {max_pairs} pairs, seed {seed}",
          flush=True)
    print(f"A: {os.environ.get('GPU_PARAMS', '{}')}  B: {os.environ.get('GPU_PARAMS_B', os.environ.get('GPU_PARAMS', '{}'))}",
          flush=True)
    t0 = last = time.perf_counter()
    fill(range(n))
    res = cp.full(n, -1, cp.int32)
    verdict = "max pairs"
    while any(g is not None for g in slot_game):
        sides.step()
        sides.results(res)
        wait()
        r = res.get()  # 0 Black won, 1 draw, 2 White won
        free = [s for s in range(n) if slot_game[s] is not None and r[s] >= 0]
        for s in free:
            pair, color = slot_game[s]
            points.setdefault(pair, []).append(r[s] / 2 if color == 0 else 1 - r[s] / 2)
            if len(points[pair]) == 2:
                finished[pair] = sum(points.pop(pair))
        grew = False
        while len(scores) + 1 in finished:
            scores.append(finished.pop(len(scores) + 1))
            grew = True
        if grew and len(scores) >= 20:
            _, _, llr = pentanomial_stats(scores, elo0, elo1)
            if llr >= UPPER or llr <= LOWER or len(scores) >= max_pairs:
                verdict = "H1 accepted (the change gains)" if llr >= UPPER else (
                    "H0 accepted (no gain)" if llr <= LOWER else "max pairs, no verdict")
                break
        if free:
            fill(free)
        now = time.perf_counter()
        if now - last >= 60:
            last = now
            report()
    report(final=True)
    print(verdict, flush=True)


if __name__ == "__main__":
    main()
