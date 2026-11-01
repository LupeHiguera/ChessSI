"""Deterministic search throughput of a gpu/ worktree: the same positions, each searched once from a cold start at a
fixed node count (score_step, as `datagen.py rescore`), timed on the GPU with CUDA events only (no host formatting,
no table clearing). The scores' MD5 doubles as a parity check: every exact variant must print the same one.

usage: python gpu/bench.py <gpu dir> <net> <positions file> <capacity> [nodes=5000]
"""
import hashlib
import sys

gdir, net, path, cap = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
cap = int(cap) if cap.isdigit() else cap  # kernels before claude/gpu-speed take only a number of games
nodes = int(sys.argv[5]) if len(sys.argv) > 5 else 5000
sys.path.insert(0, gdir)
import numpy as np  # noqa: E402
import cupy as cp  # noqa: E402
import datagen as D  # noqa: E402

dg = D.GpuDatagen(net, cap)
n = dg.capacity
fens = [l.split(" | ")[0].strip() for l in open(path) if l.strip()]
chunks = [fens[i:i + n] for i in range(0, len(fens) - n + 1, n)]
starts = [cp.asarray(np.stack([D.compact(f) for f in ch])) for ch in chunks]
net_args = (dg.ftw, dg.ftb, dg.outw, np.int32(dg.outb))
done, scores = cp.zeros(n, cp.int32), cp.zeros(n, cp.int32)
grid_t = ((n + 127) // 128,)
grid_w = dg.blocks(n) if hasattr(dg, "blocks") else ((n + 3) // 4,)  # one game per GS lanes, or per warp
e0, e1 = cp.cuda.Event(), cp.cuda.Event()
ms, launches, h = 0.0, 0, hashlib.md5()
for st in starts:
    dg.k["datagen_init"](grid_t, (128,), (dg.games, np.int32(n), st))
    dg.k["datagen_setup"](grid_w, (128,), (dg.games, np.int32(n)) + net_args + (dg.accs, dg.tables))
    e0.record()
    while True:
        dg.k["score_step"](grid_w, (128,), (dg.games, np.int32(n)) + net_args
                           + (dg.params, dg.accs, dg.tables, np.uint64(nodes), dg.budget, scores))
        launches += 1
        dg.k["datagen_done"](grid_t, (128,), (dg.games, np.int32(n), done))
        D.wait()
        if int(done.sum()) == n:
            break
    e1.record()
    e1.synchronize()
    ms += cp.cuda.get_elapsed_time(e0, e1)
    h.update(scores.get().tobytes())
k = dg.mod.get_function("score_step")
searches = len(chunks) * n
print(f"{searches} searches at {nodes} nodes, {n} at once, {launches} launches: {ms / 1000:.2f} s GPU, "
      f"{searches / ms * 1000:.0f} searches/s | score_step {k.num_regs} regs {k.local_size_bytes} B local | "
      f"md5 {h.hexdigest()[:12]}", flush=True)
