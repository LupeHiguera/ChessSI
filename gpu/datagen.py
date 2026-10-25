"""Self-play data generation on the GPU (issue #31, stage 2), with gpu/datagen.cu.

    python gpu/datagen.py run <net.nnue> <out.txt> <games> [nodes=5000] [capacity=1024] [seed=1] [random plies=8]
    python gpu/datagen.py <net.nnue> <file of start FENs> <nodes> [-v]

run: like `chesssi datagen`. Each game opens with random legal plies from the start position, then
plays at a fixed node count; lines are appended to out.txt as each game ends, and finished games are
replaced at once so the GPU stays full.

The second form plays one game from each given start position, for checking against gpu/ref.cpp:

Plays one game from each start position, the way src/datagen.cpp plays after its random opening,
and prints the same lines as gpu/ref.cpp ("<fen> | <score> | <result> | <eval>", then "# game <i>
result <r>"), so the two can be compared with diff. With -v it also prints each ply's search, as
"#ply <n> <best> <score> <nodes>" before each game's lines.
"""
import math
import os
import struct
import sys
import time

import cupy as cp
import numpy as np



def blocking_sync():
    """Wait for the GPU without spinning a CPU core: CU_CTX_SCHED_BLOCKING_SYNC on the primary
    context, set through the driver API before CuPy creates the context. Best effort."""
    try:
        import ctypes
        cuda = ctypes.CDLL("libcuda.so.1")
        dev = ctypes.c_int()
        if cuda.cuInit(0) == 0 and cuda.cuDeviceGet(ctypes.byref(dev), 0) == 0:
            cuda.cuDevicePrimaryCtxSetFlags_v2(dev, 4)
    except OSError:
        pass


blocking_sync()

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_SAMPLES, MAX_PLIES, MAX_PLY, TT_BITS, START_BYTES = 400, 400, 128, 16, 72
PIECES = "PNBRQKpnbrqk"
SAMPLE = np.dtype([("board", "u1", 64), ("stm", "u1"), ("castling", "u1"), ("ep", "u1"), ("pad", "u1"),
                   ("rule50", "<i2"), ("fullmove", "<i2"), ("score", "<i2"), ("eval", "<i2"), ("pad2", "<i4")])
assert SAMPLE.itemsize == 80


def zobrist():
    """Position::init's keys: an xorshift from seed 1070372, multiplied out, in the same order."""
    mask, s = (1 << 64) - 1, 1070372
    def rand64():
        nonlocal s
        s ^= s >> 12
        s ^= (s << 25) & mask
        s ^= s >> 27
        return (s * 2685821657736338717) & mask
    psq = [[rand64() for _ in range(64)] for _ in range(12)]
    castling = [rand64() for _ in range(16)]
    ep = [rand64() for _ in range(8)]
    side = rand64()
    return np.array(psq, np.uint64), np.array(castling, np.uint64), np.array(ep, np.uint64), np.array([side], np.uint64)


def reductions():
    r = np.zeros((64, 64), np.int32)
    for d in range(1, 64):
        for n in range(1, 64):
            r[d, n] = int(0.75 + math.log(d) * math.log(n) / 2.25)
    return r


def load_net(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CSNN"
        (h,) = struct.unpack("<i", f.read(4))
        ftw = np.frombuffer(f.read(768 * h * 2), dtype="<i2").copy()
        ftb = np.frombuffer(f.read(h * 2), dtype="<i2").copy()
        outw = np.frombuffer(f.read(2 * h * 2), dtype="<i2").copy()
        (outb,) = struct.unpack("<i", f.read(4))
    return h, ftw, ftb, outw, outb


def compact(fen):
    f = fen.split()
    out = np.zeros(START_BYTES, np.uint8)
    out[:64] = 12
    rank, file = 7, 0
    for ch in f[0]:
        if ch == "/":
            rank, file = rank - 1, 0
        elif ch.isdigit():
            file += int(ch)
        else:
            out[rank * 8 + file] = PIECES.index(ch)
            file += 1
    out[64] = f[1] == "b"
    out[65] = sum(v for k, v in (("K", 1), ("Q", 2), ("k", 4), ("q", 8)) if k in f[2])
    out[66] = 64 if f[3] == "-" else (int(f[3][1]) - 1) * 8 + "abcdefgh".index(f[3][0])
    out[67] = int(f[4]) if len(f) > 4 else 0
    full = int(f[5]) if len(f) > 5 else 1
    out[68], out[69] = full & 255, full >> 8
    return out


def to_fen(s):
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for file in range(8):
            p = s["board"][rank * 8 + file]
            if p == 12:
                empty += 1
            else:
                row += (str(empty) if empty else "") + PIECES[p]
                empty = 0
        rows.append(row + (str(empty) if empty else ""))
    c = int(s["castling"])
    castle = "".join(ch for bitv, ch in ((1, "K"), (2, "Q"), (4, "k"), (8, "q")) if c & bitv) or "-"
    ep = "-" if s["ep"] == 64 else "abcdefgh"[s["ep"] & 7] + str((s["ep"] >> 3) + 1)
    return f"{'/'.join(rows)} {'b' if s['stm'] else 'w'} {castle} {ep} {s['rule50']} {s['fullmove']}"


def move_uci(m):
    if m == 0:
        return "0000"
    sq = lambda x: "abcdefgh"[x & 7] + str((x >> 3) + 1)
    out = sq(m & 63) + sq((m >> 6) & 63)
    if (m >> 14) == 1:
        out += "nbrq"[(m >> 12) & 3]
    return out


class GpuDatagen:
    def __init__(self, net_path, capacity):
        self.h, ftw, ftb, outw, self.outb = load_net(net_path)
        src = open(os.path.join(HERE, "datagen.cu")).read()
        options = ("--std=c++17", f"-DH={self.h}")
        if os.environ.get("GPU_MAXRREG"):  # registers per thread: fewer let more warps (games) be resident
            options += (f"--maxrregcount={os.environ['GPU_MAXRREG']}",)
        self.mod = cp.RawModule(code=src, options=options)
        for name, arr in zip(("Z_PSQ", "Z_CASTLING", "Z_EP", "Z_SIDE"), zobrist()):
            cp.ndarray(arr.shape, arr.dtype, self.mod.get_global(name))[...] = cp.asarray(arr)
        r = reductions()
        cp.ndarray(r.shape, r.dtype, self.mod.get_global("REDUCTIONS"))[...] = cp.asarray(r)
        sizes = cp.zeros(3, cp.int32)
        self.mod.get_function("datagen_sizes")((1,), (1,), (sizes,))
        self.game_bytes, sample_bytes, tt_bytes = (int(x) for x in sizes.get())
        assert sample_bytes == SAMPLE.itemsize and tt_bytes == 16
        cp.cuda.runtime.deviceSetLimit(0, 32 * 1024)  # cudaLimitStackSize: the recursive search
        self.ftw, self.ftb, self.outw = cp.asarray(ftw), cp.asarray(ftb), cp.asarray(outw)
        self.capacity = capacity
        self.games = cp.zeros(capacity * self.game_bytes, cp.uint8)
        self.accs = cp.zeros(capacity * (MAX_PLY + 2) * 2 * self.h, cp.int16)
        self.tts = cp.zeros(capacity * (1 << TT_BITS) * 16, cp.uint8)
        self.k = {n: self.mod.get_function(n) for n in ("datagen_init", "datagen_setup", "datagen_step", "datagen_collect",
                                                         "datagen_done", "datagen_opening", "datagen_collect_slots")}

    def play(self, fens, nodes, verbose=False, out=sys.stdout):
        n = len(fens)
        assert n <= self.capacity
        start = cp.asarray(np.stack([compact(f) for f in fens]))
        threads, warps = ((n + 127) // 128,), ((n + 3) // 4,)
        net = (self.ftw, self.ftb, self.outw, np.int32(self.outb))
        self.k["datagen_init"](threads, (128,), (self.games, np.int32(n), start))
        self.k["datagen_setup"](warps, (128,), (self.games, np.int32(n)) + net + (self.accs, self.tts))
        done = cp.zeros(n, cp.int32)
        steps, t0 = 0, time.perf_counter()
        while True:
            self.k["datagen_step"](warps, (128,), (self.games, np.int32(n)) + net + (self.accs, self.tts, np.uint64(nodes)))
            steps += 1
            self.k["datagen_done"](threads, (128,), (self.games, np.int32(n), done))
            if int(done.sum()) == n:
                break
        cp.cuda.Device().synchronize()
        elapsed = time.perf_counter() - t0
        result, nsamples, plies = cp.zeros(n, cp.float32), cp.zeros(n, cp.int32), cp.zeros(n, cp.int32)
        samples = cp.zeros(n * MAX_SAMPLES * SAMPLE.itemsize, cp.uint8)
        plylog = cp.zeros(n * MAX_PLIES * 3, cp.int32)
        self.k["datagen_collect"](threads, (128,), (self.games, np.int32(n), done, result, nsamples, plies, samples, plylog))
        result, nsamples, plies = result.get(), nsamples.get(), plies.get()
        samples = samples.get().view(SAMPLE).reshape(n, MAX_SAMPLES)
        plylog = plylog.get().reshape(n, MAX_PLIES, 3)
        total_nodes = 0
        for i in range(n):
            text = "1.0" if result[i] == 1.0 else "0.0" if result[i] == 0.0 else "0.5"
            if verbose:
                for k in range(plies[i]):
                    out.write(f"#ply {k} {move_uci(int(plylog[i, k, 0]))} {plylog[i, k, 1]} {plylog[i, k, 2]}\n")
            total_nodes += int(plylog[i, :plies[i], 2].sum())
            for s in samples[i, :nsamples[i]]:
                out.write(f"{to_fen(s)} | {s['score']} | {text} | {s['eval']}\n")
            out.write(f"# game {i} result {text}\n")
        return {"games": n, "steps": steps, "seconds": elapsed, "nodes": total_nodes,
                "positions": int(nsamples.sum()), "plies": int(plies.sum())}


    def run(self, out_path, total_games, nodes, seed=1, random_plies=8, report_seconds=60):
        """Plays total_games games (openings that end in mate or stalemate are replaced) into out_path."""
        cap = self.capacity
        net = (self.ftw, self.ftb, self.outw, np.int32(self.outb))
        start = cp.asarray(compact("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"))
        next_id, started = 0, 0

        def reset(slots):
            nonlocal next_id
            k = len(slots)
            ids = cp.arange(next_id, next_id + k, dtype=cp.uint64)
            next_id += k
            self.k["datagen_opening"](((k + 3) // 4,), (128,), (self.games, cp.asarray(slots, cp.int32), np.int32(k), start, ids,
                                      np.uint64(seed), np.int32(random_plies)) + net + (self.accs, self.tts))

        reset(np.arange(cap, dtype=np.int32))
        started = cap
        active = np.ones(cap, bool)
        done = cp.zeros(cap, cp.int32)
        games = positions = total_nodes = 0
        t0 = last = time.perf_counter()
        with open(out_path, "a") as out:
            while active.any():
                self.k["datagen_step"](((cap + 3) // 4,), (128,), (self.games, np.int32(cap)) + net + (self.accs, self.tts, np.uint64(nodes)))
                self.k["datagen_done"](((cap + 127) // 128,), (128,), (self.games, np.int32(cap), done))
                fin = np.flatnonzero(done.get().astype(bool) & active).astype(np.int32)
                if len(fin):
                    k = len(fin)
                    res, ns, nd = cp.zeros(k, cp.float32), cp.zeros(k, cp.int32), cp.zeros(k, cp.int32)
                    smp = cp.zeros(k * MAX_SAMPLES * SAMPLE.itemsize, cp.uint8)
                    self.k["datagen_collect_slots"](((k + 127) // 128,), (128,), (self.games, cp.asarray(fin), np.int32(k), res, ns, smp, nd))
                    res, ns, nd = res.get(), ns.get(), nd.get()
                    smp = smp.get().view(SAMPLE).reshape(k, MAX_SAMPLES)
                    lines = []
                    for i in range(k):
                        if res[i] < 0:
                            continue  # the random opening ended the game
                        text = "1.0" if res[i] == 1.0 else "0.0" if res[i] == 0.0 else "0.5"
                        lines.extend(f"{to_fen(x)} | {x['score']} | {text} | {x['eval']}\n" for x in smp[i, :ns[i]])
                        games += 1
                        positions += int(ns[i])
                        total_nodes += int(nd[i])
                    out.write("".join(lines))
                    refill = fin[:max(0, min(len(fin), total_games - started))]
                    active[fin[len(refill):]] = False
                    if len(refill):
                        reset(refill)
                        started += len(refill)
                now = time.perf_counter()
                if now - last >= report_seconds or not active.any():
                    last = now
                    out.flush()
                    print(f"games {games} positions {positions} | {positions / (now - t0):.0f} positions/s, "
                          f"{total_nodes / (now - t0) / 1e6:.1f} M nodes/s", file=sys.stderr, flush=True)
        return games, positions


def main():
    if sys.argv[1] == "run":
        net, out, games = sys.argv[2], sys.argv[3], int(sys.argv[4])
        rest = [int(x) for x in sys.argv[5:9]]
        nodes, capacity, seed, plies = (rest + [5000, 1024, 1, 8][len(rest):])[:4]
        GpuDatagen(net, capacity).run(out, games, nodes, seed, plies)
        return
    net, fen_file, nodes = sys.argv[1], sys.argv[2], int(sys.argv[3])
    verbose = "-v" in sys.argv[4:]
    fens = [l.strip() for l in open(fen_file) if l.strip()]
    dg = GpuDatagen(net, len(fens))
    stats = dg.play(fens, nodes, verbose)
    s = stats
    print(f"# {s['games']} games, {s['plies']} plies in {s['steps']} steps, {s['seconds']:.2f} s: "
          f"{s['nodes'] / s['seconds'] / 1e6:.2f} M nodes/s, {s['positions'] / s['seconds']:.0f} positions/s", file=sys.stderr)


if __name__ == "__main__":
    main()
