"""GPU NNUE evaluation (issue #31, stage 1b): bit-exact against the CPU engine, then throughput.

    python gpu/nnue_check.py <net.nnue> <datagen files with a 4th field...>

Generation-6 datagen lines end with the static eval the CPU engine computed before each search,
from White's side ("<fen> | <score> | <result> | <eval>"), so they are the reference: the GPU must
reproduce every one with the network that made them (net9 for generation 6).
"""
import os
import struct
import sys
import time

import cupy as cp
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from perft import POS, WORDS, parse_fen  # noqa: E402  (also compiles chess.cu for perft)


def load_net(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CSNN"
        (h,) = struct.unpack("<i", f.read(4))
        ftw = np.frombuffer(f.read(768 * h * 2), dtype="<i2").copy()
        ftb = np.frombuffer(f.read(h * 2), dtype="<i2").copy()
        outw = np.frombuffer(f.read(2 * h * 2), dtype="<i2").copy()
        (outb,) = struct.unpack("<i", f.read(4))
    return h, ftw, ftb, outw, outb


def main():
    h, ftw, ftb, outw, outb = load_net(sys.argv[1])
    src = open(os.path.join(HERE, "chess.cu")).read() + open(os.path.join(HERE, "nnue.cu")).read()
    mod = cp.RawModule(code=src, options=("--std=c++17", f"-DH={h}"))
    eval_k, bench_k = mod.get_function("nnue_eval_kernel"), mod.get_function("nnue_update_bench")
    d_ftw, d_ftb, d_outw = cp.asarray(ftw), cp.asarray(ftb), cp.asarray(outw)

    fens, ref = [], []
    for path in sys.argv[2:]:
        with open(path) as f:
            for i, line in enumerate(f):
                if i >= 100_000:
                    break
                parts = line.split("|")
                if len(parts) >= 4:
                    fens.append(parts[0].strip())
                    ref.append(int(parts[3]))
    pos = np.zeros(len(fens), POS)
    for i, fen in enumerate(fens):
        pos[i] = parse_fen(fen)
    ref = np.array(ref)
    stm_sign = np.where(pos["stm"] == 0, 1, -1)
    d_pos = cp.asarray(pos.view(np.uint64).reshape(-1, WORDS))
    n = len(fens)
    out = cp.empty(n, dtype=cp.int32)
    grid = ((n + 3) // 4,)
    eval_k(grid, (128,), (d_pos, np.int32(n), d_ftw, d_ftb, d_outw, np.int32(outb), out))
    got = cp.asnumpy(out) * stm_sign
    bad = int((got != ref).sum())
    print(f"h{h}: {n:,} positions; GPU eval differs from the CPU engine's on {bad}" + ("  -> BIT-EXACT" if bad == 0 else ""))
    if bad:
        idx = np.flatnonzero(got != ref)[:5]
        for i in idx:
            print(f"  {fens[i]}  cpu {ref[i]}  gpu {got[i]}")

    # Throughput: evaluations from scratch, and incremental update + eval per node.
    for reps in (1, 20):
        cp.cuda.Device().synchronize()
        t = time.perf_counter()
        for _ in range(reps):
            eval_k(grid, (128,), (d_pos, np.int32(n), d_ftw, d_ftb, d_outw, np.int32(outb), out))
        cp.cuda.Device().synchronize()
    dt = time.perf_counter() - t
    print(f"full evaluation from scratch: {n * reps / dt / 1e6:,.0f} M positions/s")
    iters = 200
    for warps in (4096, 16384):
        m = min(warps, n)
        o = cp.empty(m, dtype=cp.int32)
        bench_k(((m + 3) // 4,), (128,), (d_pos, np.int32(m), d_ftw, d_ftb, d_outw, np.int32(outb), np.int32(iters), o))
        cp.cuda.Device().synchronize()
        t = time.perf_counter()
        bench_k(((m + 3) // 4,), (128,), (d_pos, np.int32(m), d_ftw, d_ftb, d_outw, np.int32(outb), np.int32(iters), o))
        cp.cuda.Device().synchronize()
        dt = time.perf_counter() - t
        print(f"incremental update + eval, {m:,} warps in flight: {m * iters / dt / 1e6:,.0f} M nodes/s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
