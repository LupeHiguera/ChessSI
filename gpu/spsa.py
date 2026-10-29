"""SPSA tuning of the search's constants at a fixed node count on the GPU (issue #31).

    python gpu/spsa.py <net.nnue> <pairs> [nodes=50000] [games at once=1000] [seed=1] [book]

The constants are the fields of Params in gpu/datagen.cu, starting from src/search.cpp's values. Each
game pair plays one opening twice, theta + c * delta against theta - c * delta with the colors swapped,
where delta is a random +1 or -1 per constant; both sides use the same network. When a pair finishes,
theta moves as in fishtest's SPSA, theta += a / c * (wins - losses) * delta, with fishtest's schedules
for a and c (alpha 0.602, gamma 0.101, A one tenth of the pairs, r_end 0.002). Many games play at
once, and a finished game's slot takes the next game at once; each pair keeps the theta of its start.
Prints theta every minute and at the end.

Keep each kernel launch well under the Windows GPU watchdog (2 s). A launch runs every game's search
for up to GPU_BUDGET nodes (unlimited by default, so one ply), and an RTX 5080 holds about 1,000 games
at a time, each searching about 54,000 nodes a second: 800 games at 50,000 nodes take 0.75 s a launch.
With GPU_BUDGET=20000, 2,000 games at once take about 0.75 s too, at any node count.

Fixed nodes leave speed out, which suits pruning and reduction constants. The games are much shorter
than a CPU test's, though, so tuned values still need a time-based SPRT.
"""
import collections
import json
import math
import os
import random
import sys
import time

import cupy as cp
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from datagen import DEFAULTS, PARAMS, GpuDatagen, compact, make_params, wait  # noqa: E402

# Each constant's lowest and highest value, and its step at the end of the run (c_end).
SPACE = {
    "rfpDepth": (1, 10, 1), "rfpMargin": (40, 400, 15),
    "nmpDepth": (1, 8, 1), "nmpBase": (1, 6, 1), "nmpDiv": (2, 12, 1),
    "lmpDepth": (1, 16, 1), "lmpBase": (0, 12, 1),
    "futDepth": (1, 12, 1), "futMargin": (40, 400, 12),
    "lmrDepth": (1, 8, 1), "lmrMoves": (0, 10, 1), "lmrBase": (-0.5, 2.5, 0.1), "lmrDiv": (1.0, 5.0, 0.15),
    "histMax": (200, 4000, 100), "aspDepth": (1, 12, 1), "aspDelta": (5, 100, 3), "qsSee": (-200, 200, 10),
    "seeDepth": (1, 12, 1), "seeQuiet": (10, 200, 6), "seeCapture": (5, 100, 3),
}
R_END, ALPHA, GAMMA = 0.002, 0.602, 0.101


def clip(name, x):
    return min(max(x, SPACE[name][0]), SPACE[name][1])


def show(theta):
    return " ".join(f"{name} {theta[name]:.2f}" for name in SPACE)


def main():
    net_path, total = sys.argv[1], int(sys.argv[2])
    nodes = int(sys.argv[3]) if len(sys.argv) > 3 else 50000
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    book = sys.argv[6] if len(sys.argv) > 6 else os.path.join(HERE, "..", "books", "UHO_Lichess_4852_v1.epd")
    rng = random.Random(seed)
    lines = [l.strip() for l in open(book) if l.strip()]
    theta = {name: float(DEFAULTS[name]) for name in SPACE}
    big_a = 0.1 * total
    c0 = {x: c_end * total ** GAMMA for x, (_, _, c_end) in SPACE.items()}
    a0 = {x: R_END * c_end ** 2 * (big_a + total) ** ALPHA for x, (_, _, c_end) in SPACE.items()}

    dg = GpuDatagen(net_path, n)
    tables_b = cp.zeros(n * dg.tables_bytes, cp.uint8)  # side B's TTs and correction histories
    net = (dg.ftw, dg.ftb, dg.outw, np.int32(dg.outb))
    k = {name: dg.mod.get_function(name) for name in ("match_init", "match_setup", "match_step", "match_results")}
    pa, pb = np.zeros(n, PARAMS), np.zeros(n, PARAMS)
    pa_gpu, pb_gpu = cp.zeros(n * PARAMS.itemsize, cp.uint8), cp.zeros(n * PARAMS.itemsize, cp.uint8)
    pairs = {}                       # pair -> delta, step a / c, both sides' Params, and A's points so far
    queue = collections.deque()      # games waiting for a slot: (pair, A's color, opening)
    slot_game = [None] * n           # (pair, A's color) of the game in each slot, None when idle
    started = finished = 0
    points = 0.0

    def new_pair():
        nonlocal started
        started += 1
        c = {x: c0[x] / started ** GAMMA for x in SPACE}
        delta = {x: rng.choice((-1, 1)) for x in SPACE}
        pairs[started] = {
            "delta": delta,
            "step": {x: a0[x] / (big_a + started) ** ALPHA / c[x] for x in SPACE},
            "plus": make_params({x: clip(x, theta[x] + c[x] * delta[x]) for x in SPACE})[0],
            "minus": make_params({x: clip(x, theta[x] - c[x] * delta[x]) for x in SPACE})[0],
            "points": [],
        }
        fen = " ".join(lines[rng.randrange(len(lines))].split()[:6])
        queue.extend([(started, 0, fen), (started, 1, fen)])

    def fill(slots):
        """Starts the next games in the given free slots; theta + c * delta plays as side A."""
        used, fens, colors = [], [], []
        for s in slots:
            if not queue and started < total:
                new_pair()
            if not queue:
                slot_game[s] = None
                continue
            pair, color, fen = queue.popleft()
            pa[s], pb[s] = pairs[pair]["plus"], pairs[pair]["minus"]
            slot_game[s] = (pair, color)
            used.append(s)
            fens.append(fen)
            colors.append(color)
        if not used:
            return
        pa_gpu[...] = cp.asarray(pa.view(np.uint8))
        pb_gpu[...] = cp.asarray(pb.view(np.uint8))
        m = len(used)
        slots_gpu = cp.asarray(np.array(used, np.int32))
        positions = cp.asarray(np.stack([compact(f) for f in fens]))
        k["match_init"](((m + 127) // 128,), (128,), (dg.games, slots_gpu, np.int32(m), positions,
                                                      cp.asarray(np.array(colors, np.int32))))
        k["match_setup"](((m + 3) // 4,), (128,), (slots_gpu, np.int32(m), dg.tables, tables_b))

    print(f"SPSA of {len(SPACE)} constants: {total} pairs at {nodes} nodes a move, {n} games at once, "
          f"{os.path.basename(net_path)}, seed {seed}", flush=True)
    print(f"start: {show(theta)}", flush=True)
    fill(range(n))
    res = cp.full(n, -1, cp.int32)
    t0 = last = time.perf_counter()
    steps = 0
    while any(g is not None for g in slot_game):
        k["match_step"](((n + 3) // 4,), (128,), (dg.games, np.int32(n)) + net + net
                        + (pa_gpu, pb_gpu, np.int32(1), dg.accs, dg.tables, tables_b, np.uint64(nodes), dg.budget))
        k["match_results"](((n + 127) // 128,), (128,), (dg.games, np.int32(n), res))
        wait()
        r = res.get()  # 0 Black won, 1 draw, 2 White won
        steps += 1
        free = [s for s in range(n) if slot_game[s] is not None and r[s] >= 0]
        for s in free:
            pair, color = slot_game[s]
            p = pairs[pair]
            p["points"].append(r[s] / 2 if color == 0 else 1 - r[s] / 2)  # theta + c * delta's points
            if len(p["points"]) == 2:
                result = 2 * sum(p["points"]) - 2  # wins minus losses over the pair
                for x in SPACE:
                    theta[x] = clip(x, theta[x] + p["step"][x] * result * p["delta"][x])
                points += sum(p["points"])
                finished += 1
                del pairs[pair]
        if free:
            fill(free)
        now = time.perf_counter()
        if now - last >= 60 or not any(g is not None for g in slot_game):
            last = now
            print(f"pairs {finished}/{total} {now - t0:.0f} s ({finished / (now - t0):.2f}/s, {(now - t0) / steps:.2f} s a ply, "
                  f"plus side {points / max(1, 2 * finished):.3f}) | {show(theta)}", flush=True)
    print(f"final: {show(theta)}", flush=True)
    # The values the games used, as make_params realizes them: integers by floor(x + 0.5), the LMR
    # constants as they are (they only enter the reduction table). GPU_PARAMS takes this JSON.
    print("params: " + json.dumps({x: theta[x] if isinstance(DEFAULTS[x], float) else math.floor(theta[x] + 0.5)
                                   for x in SPACE}), flush=True)


if __name__ == "__main__":
    main()
