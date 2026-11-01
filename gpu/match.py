"""Fixed-node matches between two networks on the GPU (issue #31): ChessSI's exact search (gpu/datagen.cu)
playing both sides of thousands of games at once.

    python gpu/match.py <netA.nnue> <netB.nnue> <pairs> [nodes=20000] [seed=1] [book=books/UHO_Lichess_4852_v1.epd]

Each opening from the book is played twice, A with White and then with Black. Games end like our
fastchess SPRTs (see match_step). Prints A's score, Elo with a 95% interval from the game pairs
(pentanomial), and the SPRT [0, 5] log-likelihood ratio. The search's constants are src/search.cpp's, or
GPU_PARAMS for A and GPU_PARAMS_B for B (JSON, as gpu/spsa.py prints them; B takes A's if GPU_PARAMS_B is
unset), so A and B can also be one network with two sets of constants.

nodes is one count for both sides, or "<A>:<B>" for node odds. A fixed node count leaves out speed: a bigger
network searches fewer nodes in the same time, so give it fewer here, in the ratio of the two networks'
CPU nodes per second, as an estimate of a timed match. Networks of different sizes, or node odds, play
through match_side, one kernel build per side; GPU_MATCH_SPLIT=1 forces that path (the same games).
"""
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
from datagen import MAX_PLY, GpuDatagen, build_module, compact, feature_rows, load_net, make_params, module_sizes, wait  # noqa: E402



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


def parse_nodes(text):
    """A node count for both sides, or "<A>:<B>" for node odds."""
    a, _, b = str(text).partition(":")
    return int(a), int(b or a)


class Sides:
    """Both sides of a set of match games on the GPU: A is network A with GPU_PARAMS and its own tables, B network
    B with GPU_PARAMS_B (A's if unset). One match_step plays a ply of every game when the two have one hidden size
    and one node count; otherwise each side has a build of its own size and plays its plies through match_side."""

    def __init__(self, net_a, net_b, capacity, nodes):
        self.dg = dg = GpuDatagen(net_a, capacity, kernel="match_step")  # the games, and A's network and tables
        self.n = n = dg.capacity
        self.nodes_a, self.nodes_b = (np.uint64(x) for x in parse_nodes(nodes))
        hb, ftw, ftb, outw, outb = load_net(net_b)
        # Still to allocate: B's tables, and B's accumulators if the sides are split. Past free memory the driver
        # pages GPU memory out to system RAM, and a match crawls instead of failing.
        need = n * (dg.tables_bytes + (MAX_PLY + 2) * 2 * hb * 2)
        free = cp.cuda.runtime.memGetInfo()[0]
        if need > 0.95 * free:
            raise SystemExit(f"{n} games need {need / 2**30:.1f} GiB more GPU memory, {free / 2**30:.1f} GiB free: play fewer "
                             f"pairs at once (several seeds), or gpu/sprt.py, which refills a fixed number of slots")
        self.a = (dg.ftw, dg.ftb, dg.outw, np.int32(dg.outb))
        self.b = (feature_rows(ftw), cp.asarray(ftb), cp.asarray(outw), np.int32(outb))
        self.params_b = dg.params  # GPU_PARAMS, read by GpuDatagen
        if "GPU_PARAMS_B" in os.environ:
            self.params_b = cp.asarray(make_params(json.loads(os.environ["GPU_PARAMS_B"])).view(np.uint8))
        self.tables_b = cp.zeros(n * dg.tables_bytes, cp.uint8)  # B's TTs and histories
        self.k = {name: dg.mod.get_function(name)
                  for name in ("match_init", "match_setup", "match_step", "match_side", "match_results")}
        self.split = hb != dg.h or self.nodes_a != self.nodes_b or os.environ.get("GPU_MATCH_SPLIT") == "1"
        if self.split:
            mod_b = dg.mod if hb == dg.h else build_module(hb)
            assert module_sizes(mod_b) == module_sizes(dg.mod), "both builds must lay out a game the same way"
            self.side_b = mod_b.get_function("match_side")
            self.accs_b = cp.zeros(n * (MAX_PLY + 2) * 2 * hb, cp.int16)
        self.h_b = hb

    def describe(self):
        a, b = int(self.nodes_a), int(self.nodes_b)
        nodes = f"{a} nodes a move" if a == b else f"{a} nodes a move for A, {b} for B"
        return f"{nodes}, hidden {self.dg.h} vs {self.h_b}{' (one build per side)' if self.split else ''}"

    def start(self, slots, starts, a_colors):
        """Starts games in the given slots (cupy int32) from compact positions, with A playing a_colors."""
        m = len(slots)
        self.k["match_init"](((m + 127) // 128,), (128,), (self.dg.games, slots, np.int32(m), starts, a_colors))
        self.k["match_setup"](((m + 3) // 4,), (128,), (slots, np.int32(m), self.dg.tables, self.tables_b))

    def step(self):
        """One kernel launch's worth of every unfinished game."""
        dg, n = self.dg, np.int32(self.n)
        warps = ((self.n + 3) // 4,)
        if not self.split:
            self.k["match_step"](warps, (128,), (dg.games, n) + self.a + self.b
                                 + (dg.params, self.params_b, np.int32(0), dg.accs, dg.tables, self.tables_b,
                                    self.nodes_a, dg.budget))
        else:
            self.k["match_side"](warps, (128,), (dg.games, n) + self.a
                                 + (dg.params, np.int32(0), dg.accs, dg.tables, np.int32(0), self.nodes_a, dg.budget))
            self.side_b(warps, (128,), (dg.games, n) + self.b
                        + (self.params_b, np.int32(0), self.accs_b, self.tables_b, np.int32(1), self.nodes_b, dg.budget))

    def results(self, out):
        """Each game's result into out (cupy int32): -1 playing, 0 Black won, 1 draw, 2 White won."""
        self.k["match_results"](((self.n + 127) // 128,), (128,), (self.dg.games, np.int32(self.n), out))


def main():
    net_a, net_b, pairs = sys.argv[1], sys.argv[2], int(sys.argv[3])
    nodes = sys.argv[4] if len(sys.argv) > 4 else "20000"
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    book = sys.argv[6] if len(sys.argv) > 6 else os.path.join(HERE, "..", "books", "UHO_Lichess_4852_v1.epd")
    lines = [l.strip() for l in open(book) if l.strip()]
    rng = random.Random(seed)
    openings = [" ".join(lines[rng.randrange(len(lines))].split()[:6]) for _ in range(pairs)]  # with move counters
    n = 2 * pairs
    sides = Sides(net_a, net_b, n, nodes)
    start = cp.asarray(np.stack([compact(openings[i // 2]) for i in range(n)]))
    a_color = cp.asarray(np.array([i % 2 for i in range(n)], np.int32))  # A has White in even games
    sides.start(cp.arange(n, dtype=cp.int32), start, a_color)
    res = cp.full(n, -1, cp.int32)
    t0, steps = time.perf_counter(), 0
    while True:
        sides.step()
        steps += 1
        if steps % 8 == 0:
            sides.results(res)
            wait()
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
    print(f"{os.path.basename(net_a)} vs {os.path.basename(net_b)}, {sides.describe()}, {n} games ({pairs} pairs) "
          f"in {secs:.0f} s ({steps} steps)")
    if os.environ.get("GPU_MATCH_RESULTS"):  # every game's result, to compare runs game by game
        np.save(os.environ["GPU_MATCH_RESULTS"], r)
    print(f"A: +{wins} ={draws} -{losses}, score {a_score.mean():.3f}; pairs {penta}")
    print(f"Elo {elo:+.1f} +/- {half:.1f} (95%), LLR {llr:.2f} for SPRT [0, 5] (bounds -2.94, 2.94)")


if __name__ == "__main__":
    main()
