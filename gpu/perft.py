"""GPU perft (issue #31, stage 1a): exact node counts on tests/perft.epd, then nodes per second.

    python gpu/perft.py [max depth, default 5]

Needs CuPy (cupy-cuda12x); chess.cu is compiled at run time with NVRTC. Each position is first
expanded a few plies on the GPU, until there are enough positions to fill it, then every thread
counts one subtree.
"""
import os
import sys
import time

import cupy as cp
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
POS = np.dtype([("pc", "<u8", (2, 6)), ("occ", "<u8", 2), ("stm", "<i4"), ("castle", "<i4"), ("ep", "<i4"), ("pad", "<i4")])
assert POS.itemsize == 128  # matches struct Pos in chess.cu
WORDS = POS.itemsize // 8

module = cp.RawModule(code=open(os.path.join(HERE, "chess.cu")).read(), options=("--std=c++17",))
perft_kernel = module.get_function("perft_kernel")
expand_kernel = module.get_function("expand_kernel")
cp.cuda.runtime.deviceSetLimit(0, 8192)  # cudaLimitStackSize: recursive perft holds 256 moves a ply


def parse_fen(fen):
    f = fen.split()
    p = np.zeros((), POS)
    rank, file = 7, 0
    for ch in f[0]:
        if ch == "/":
            rank, file = rank - 1, 0
        elif ch.isdigit():
            file += int(ch)
        else:
            color, piece, sq = int(ch.islower()), "pnbrqk".index(ch.lower()), rank * 8 + file
            p["pc"][color, piece] |= np.uint64(1 << sq)
            p["occ"][color] |= np.uint64(1 << sq)
            file += 1
    p["stm"] = int(f[1] == "b")
    p["castle"] = sum(v for k, v in (("K", 1), ("Q", 2), ("k", 4), ("q", 8)) if k in f[2])
    p["ep"] = -1 if f[3] == "-" else (int(f[3][1]) - 1) * 8 + "abcdefgh".index(f[3][0])
    return p


def to_device(p):
    return cp.asarray(np.atleast_1d(p).view(np.uint64).reshape(-1, WORDS))


def expand(front):
    """All legal children of every position in front."""
    n = front.shape[0]
    out = cp.empty((n * 256, WORDS), dtype=cp.uint64)
    count = cp.empty(n, dtype=cp.int32)
    expand_kernel(((n + 127) // 128,), (128,), (front, np.int32(n), out, count))
    return out.reshape(n, 256, WORDS)[cp.arange(256)[None, :] < count[:, None]]


def gpu_perft(fen, depth, max_front=250_000, max_buffer=2 << 30):
    """Leaf nodes at depth; returns (nodes, plies expanded first, positions counted in parallel)."""
    front, k = to_device(parse_fen(fen)), 0
    while depth - k > 1 and front.shape[0] < max_front and front.shape[0] * 256 * POS.itemsize <= max_buffer:
        front, k = expand(front), k + 1
    n = front.shape[0]
    out = cp.empty(n, dtype=cp.uint64)
    perft_kernel(((n + 127) // 128,), (128,), (front, np.int32(n), np.int32(depth - k), out))
    return int(out.sum()), k, n


def main():
    max_depth = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    tests = []
    for line in open(os.path.join(HERE, "..", "tests", "perft.epd")):
        if line.startswith("#") or not line.strip():
            continue
        fen, *counts = line.split(";")
        tests.append((fen.strip(), {int(c.split()[0][1:]): int(c.split()[1]) for c in counts}))
    gpu_perft(tests[0][0], 3)  # compile and warm up
    failed, total_nodes, total_time = 0, 0, 0.0
    for fen, counts in tests:
        for d in sorted(counts):
            if d > max_depth:
                continue
            cp.cuda.Device().synchronize()
            t = time.perf_counter()
            nodes, k, n = gpu_perft(fen, d)
            cp.cuda.Device().synchronize()
            dt = time.perf_counter() - t
            ok = nodes == counts[d]
            failed += not ok
            total_nodes, total_time = total_nodes + nodes, total_time + dt
            print(f"{'ok  ' if ok else 'FAIL'} {fen[:40]:40s} d{d} {nodes:>12,} (expected {counts[d]:>12,}) "
                  f"{dt * 1000:8.1f} ms  {nodes / dt / 1e6:8.1f} M nodes/s  [{k} plies expanded, {n:,} subtrees]")
    print(f"{failed} failed; {total_nodes:,} nodes in {total_time:.2f} s, {total_nodes / total_time / 1e6:.1f} M nodes/s overall")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
