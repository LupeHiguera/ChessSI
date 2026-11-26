"""Train ChessSI's NNUE on positions in the datagen text format.

    python train.py <data.txt>... <out.nnue> [--hidden 128] [--epochs 20] [--lambda 0.75] [--cache-dir dir]
                    [--aux-weight 0] [--future-plies 8] [--policy-weight 0] [--mirror]
    python train.py --shards <dir> <out.nnue> [same options] [--group 8] [--val-max N] [--resume]

With --shards, positions stream from binary shards on disk (made by shards.cpp and shards.py), so the
data can be far larger than RAM; see train_streaming. Train on shards that went through `shards.py
scatter`: on shards in file order, the --group shuffle keeps each game's positions close together, and
validation loss came out 0.0003 worse than in-memory training on the same data (0.00918 vs 0.00886 after
one epoch); scattered, 0.00891.

Network: (768 -> H) x 2 perspectives -> SCReLU -> 1, the usual first NNUE. Input features are
(piece colour relative to the perspective, piece type, square), with squares mirrored vertically for
Black's perspective. With --mirror, a perspective's squares are also mirrored left to right while its own
king stands on files e-h, so each side sees its king on files a-d only. The output, times SCALE, is
centipawns for the side to move.

--ft picks how the first layer is computed. dense (the default, needs CuPy) multiplies a one-hot
matrix by the weights; bag is torch's EmbeddingBag, the only path before 2026-11-25 and the slower
one. They are the same function: trained in float64 they export the same file. In float32 the order
of additions differs, so the two exports differ slightly and a printed loss can differ in its last
digit.

Loss: mean squared error between sigmoid(output) and a blend of sigmoid(score / SCALE) and the game
result, both from the side to move: target = lambda * score + (1 - lambda) * result. With
--aux-weight, a second head (training only, not exported) also learns the win probability
--future-plies later in the game. With --policy-weight, a third training-only head learns the
from and to squares of the move played (cross-entropy), where the next recorded position shows it.
With --teacher <net.nnue>, a training-only head learns that network's evaluation of each position
(self-distillation from an earlier ChessSI network), weighted by --teacher-weight.

Export (little-endian, see src/nnue.cpp): magic "CSNN" ("CSNM" with --mirror), hidden size (int32), feature
weights int16[768][H] and biases int16[H] scaled by QA, output weights int16[2H] scaled by QB, output bias
int32 scaled by QA * QB.
"""
import argparse
import functools
import glob
import hashlib
import os
import math
import random
import struct
from array import array
import time

import numpy as np
import torch

SCALE = 400
QA, QB = 255, 64
PIECES = {"P": 0, "N": 1, "B": 2, "R": 3, "Q": 4, "K": 5}
PAD = 768


def features(board_field, mirror=False):
    """Feature indices from White's and Black's perspective for one FEN board field; with mirror, each
    perspective's squares are flipped left to right while its own king stands on files e-h."""
    pieces = []
    rank = 7
    file = 0
    for ch in board_field:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            pieces.append((ch.isupper(), PIECES[ch.upper()], rank * 8 + file))
            file += 1
    flip = {c: 7 if mirror and sq % 8 >= 4 else 0 for c, pt, sq in pieces if pt == PIECES["K"]}
    white = [(0 if is_white else 384) + pt * 64 + (sq ^ flip[True]) for is_white, pt, sq in pieces]
    black = [(0 if not is_white else 384) + pt * 64 + (sq ^ 56 ^ flip[False]) for is_white, pt, sq in pieces]
    return white, black


# FLIP[f] is feature f seen from the other side: colours swap, squares mirror vertically. So one
# White-perspective list per position is enough; the Black one is FLIP applied to it.
FLIP = np.array([((f + 384) % 768) ^ 56 for f in range(PAD)] + [PAD], dtype=np.int64)


def mirror_files(f):
    """One perspective's feature lists (b, 32), flipped left to right (square ^ 7) in the rows where that
    perspective's own king, the one feature in [320, 384), stands on files e-h. Bit 2 of a feature is bit 2
    of its square, the high bit of the file."""
    king_east = ((f >= 5 * 64) & (f < 6 * 64) & ((f & 4) != 0)).any(1, keepdim=True)
    return torch.where(king_east & (f != PAD), f ^ 7, f)


def views(feats_w, white, flip_t, mirror):
    """The network's two inputs, side to move first, from White-perspective feature lists and whether White is
    to move (bool, b); see mirror_files for mirror."""
    feats_b = flip_t[feats_w]
    if mirror:
        feats_w, feats_b = mirror_files(feats_w), mirror_files(feats_b)
    wt = white.unsqueeze(1)
    return torch.where(wt, feats_w, feats_b), torch.where(wt, feats_b, feats_w)


def white_features(board_field):
    """White-perspective feature indices for one FEN board field (the Black ones are FLIP of these)."""
    out = []
    rank, file = 7, 0
    for ch in board_field:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            out.append((0 if ch.isupper() else 384) + PIECES[ch.upper()] * 64 + rank * 8 + file)
            file += 1
    return out


# Positions are kept in memory as an occupancy mask (one bit per square, a1 = bit 0) and a 4-bit
# piece code (feature // 64: 0-5 White, 6-11 Black) per occupied square in ascending square order,
# 24 bytes instead of the 64 of the padded feature list. decode() rebuilds that list exactly, in
# FEN order with PAD at the end, so training sees the same tensors.


def encode(feats, chunk=1 << 20):
    """(n, 32) White-perspective feature lists padded with PAD -> occupancy uint64[n], pieces uint8[n, 16]."""
    n = len(feats)
    occ, pcs = np.empty(n, dtype=np.uint64), np.empty((n, 16), dtype=np.uint8)
    for s in range(0, n, chunk):
        f = feats[s:s + chunk].astype(np.int64)
        valid = f != PAD
        sq = np.where(valid, f % 64, 64)
        order = np.argsort(sq, axis=1, kind="stable")
        sq, pc = np.take_along_axis(sq, order, 1), np.take_along_axis(np.where(valid, f // 64, 0), order, 1)
        bits = np.where(sq < 64, np.left_shift(np.uint64(1), np.minimum(sq, 63).astype(np.uint64)), np.uint64(0))
        occ[s:s + chunk] = np.bitwise_or.reduce(bits, axis=1)
        pcs[s:s + chunk] = (pc[:, 0::2] | (pc[:, 1::2] << 4)).astype(np.uint8)
    return occ, pcs


def decode(occ, pcs):
    """occupancy int64[b] (the uint64 bits) and pieces uint8[b, 16] (torch, same device) -> the
    (b, 32) feature lists encode() started from."""
    dev = occ.device
    asc = torch.arange(64, device=dev)
    bits = (occ.unsqueeze(1) >> asc) & 1
    nib = torch.stack((pcs & 15, pcs >> 4), 2).reshape(-1, 32).long()
    piece = torch.gather(nib, 1, (torch.cumsum(bits, 1) - 1).clamp(0, 31))
    # asc ^ 56 is FEN order, rank 8 first. Built on the device: a copy from host memory here made every
    # step wait for the GPU to finish all queued work.
    f = torch.where(bits.bool(), piece * 64 + asc, PAD)[:, asc ^ 56]
    order = torch.sort((f == PAD).to(torch.int8), dim=1, stable=True).indices[:, :32]
    return torch.gather(f, 1, order)


FIELDS = ("feats", "white", "scores", "results", "keys", "ply")
# Cache files are named <data file>.<fingerprint>.v<CACHE_VERSION>.<byte offset>.npz (see
# cache_stem). Version 2: deterministic position keys (version 1 used Python's hash(), which differs
# between processes, so duplicates in chunks cached by different runs were never found).
CACHE_VERSION = 2


def cache_stem(path, cache_dir):
    """Where one data file's parsed chunks are cached. The fingerprint hashes the file's first
    megabyte, which appending lines never changes. Without it, two data files with the same name (the
    20M-line pieces of different datagen files, say) shared cached chunks: the second file was read as
    the first one's positions plus whatever followed at the first one's length."""
    with open(path, "rb") as f:
        tag = hashlib.blake2b(f.read(1 << 20), digest_size=6).hexdigest()
    return os.path.join(cache_dir, f"{os.path.basename(path)}.{tag}.v{CACHE_VERSION}")


def position_key(fields):
    """64-bit key of a position from its first four FEN fields (board, side, castling, en passant;
    not the move counters). The same in every process, unlike Python's hash()."""
    digest = hashlib.blake2b(fields.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") & 0x7FFFFFFFFFFFFFFF


def parse_lines(lines):
    """Raw arrays (no deduplication) for datagen text lines; returns them and the malformed count."""
    feats, white, scores, results, keys, ply = array("h"), array("b"), array("f"), array("f"), array("q"), array("h")
    bad = 0
    for line in lines:
        try:
            fen, score, result = (x.strip() for x in line.split("|")[:3])  # a 4th field, the static eval, is unused
            parts = fen.split()
            w = white_features(parts[0])
            cp, res = int(score), float(result)
            p = 2 * (int(parts[5]) - 1) + (parts[1] == "b")
        except (ValueError, KeyError, IndexError):
            bad += 1  # e.g. a line cut short by stopping datagen
            continue
        keys.append(position_key(" ".join(parts[:4])))  # ignore move counters
        feats.extend(w + [PAD] * (32 - len(w)))
        white.append(parts[1] == "w")
        scores.append(cp)
        results.append(res)
        ply.append(min(p, 4095))
    out = {"feats": np.frombuffer(feats, dtype=np.int16).reshape(-1, 32), "white": np.frombuffer(white, dtype=np.int8),
           "scores": np.frombuffer(scores, dtype=np.float32), "results": np.frombuffer(results, dtype=np.float32),
           "keys": np.frombuffer(keys, dtype=np.int64), "ply": np.frombuffer(ply, dtype=np.int16)}
    return out, bad


def forget_pages(path):
    """Asks the OS to drop a file's pages from its cache once read. Under WSL the page cache is RAM
    that Windows does not get back, and a training run reads its data cache, hundreds of GB, once."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
    except (AttributeError, OSError):
        pass


def load_file(path, cache_dir, frozen=False, fields=FIELDS):
    """Raw arrays for one file, only `fields` of them. With cache_dir, each parsed byte range is kept
    as an .npz and only lines appended since the last run are parsed (datagen files grow while it
    runs). frozen: use only what is cached, so runs compared with each other see the same data."""
    chunks, start = [], 0
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        stem = cache_stem(path, cache_dir)
        while os.path.exists(f"{stem}.{start}.npz"):
            with np.load(f"{stem}.{start}.npz") as z:
                chunks.append({k: z[k] for k in fields})
                end = int(z["end"])
            forget_pages(f"{stem}.{start}.npz")
            start = end
    if frozen:  # files with nothing cached yet are left out
        return {k: np.concatenate([c[k] for c in chunks]) for k in fields} if chunks else None
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    forget_pages(path)
    end = start + data.rfind(b"\n") + 1  # only complete lines
    if end > start:
        chunk, bad = parse_lines(data[:end - start].decode().splitlines())
        if bad:
            print(f"{path}: skipped {bad} malformed lines")
        if cache_dir:
            np.savez(f"{stem}.{start}.npz", end=end, **chunk)
        chunks.append({k: chunk[k] for k in fields})
    return {k: np.concatenate([c[k] for c in chunks]) for k in fields} if chunks else None


def count_games(game):
    """Distinct game numbers in a non-decreasing array (the games with a position kept)."""
    return int(len(game) > 0) + int(np.count_nonzero(game[1:] != game[:-1]))


def per_file(d, game_base, future_plies):
    """Game numbers (from game_base), the win probability future_plies later and each game's stable
    key, for one file's raw arrays. Games never span files, so this is the same per file as over
    all of them at once."""
    n = len(d["ply"])
    ply = d["ply"].astype(np.int64)
    new_game = np.ones(n, dtype=bool)
    new_game[1:] = (ply[1:] <= ply[:-1]) | (d["results"][1:] != d["results"][:-1])
    game = game_base + np.cumsum(new_game) - 1
    # Win probability future_plies later: the first recorded position at least that far ahead.
    order_key = game * 4096 + ply
    j = np.searchsorted(order_key, order_key + future_plies)
    jc = np.minimum(j, n - 1)
    valid = (j < n) & (game[jc] == game)
    future = np.where(valid, 1 / (1 + np.exp(-d["scores"][jc] / SCALE)), d["results"]).astype(np.float32)
    # A stable identity for each game, for the validation split: the key of its first recorded
    # position. Unlike the game number, it does not change when files grow or are added.
    starts = np.flatnonzero(np.r_[True, game[1:] != game[:-1]])
    gkey = d["keys"][starts][game - game[0]]
    return game, future, gkey


def first_occurrences(keys, parts=8):
    """np.unique(keys, return_index=True)[1], sorted: the index of each key's first occurrence. Equal
    keys share their top bits, so the keys are split into `parts` ranges by those bits and each range
    is deduplicated alone, which needs a fraction of the memory of one np.unique over everything."""
    shift = np.uint64(64 - int(math.log2(parts)))
    top = (keys.view(np.uint64) >> shift).astype(np.uint8)
    firsts = []
    for part in range(parts):
        idx = np.flatnonzero(top == part)
        _, f = np.unique(keys[idx], return_index=True)
        firsts.append(idx[f])
    del top
    first = np.concatenate(firsts)
    first.sort()
    return first


def load(paths, cache_dir=None, future_plies=8, frozen=False, moves=False):
    """Unique positions from datagen text files: White-perspective features int16[n, 32] padded
    with PAD, side to move (1 for White), White-relative score and result, a game number, and the
    White-relative win probability `future_plies` later in the same game (the game result if it
    ends first). With `moves`, also the played move's squares (see played_moves), which takes
    several minutes on tens of millions of positions. Games are contiguous in each file; a new one
    starts where the ply goes back or the result changes.

    With a cache, the files are read twice so the memory peak stays near one copy of the result:
    first everything but the features, to find the unique positions, then the features of the
    positions kept, one file at a time. Without one, or with `moves`, everything is loaded at once."""
    if moves or not cache_dir:
        return load_at_once(paths, cache_dir, future_plies, frozen, moves)
    small, used, game_base = [], [], 0
    for path in paths:
        d = load_file(path, cache_dir, frozen, fields=("keys", "white", "scores", "results", "ply"))
        if d is None:
            continue
        game, future, gkey = per_file(d, game_base, future_plies)
        game_base = int(game[-1]) + 1
        small.append({"keys": d["keys"], "white": d["white"], "scores": d["scores"], "results": d["results"],
                      "game": game.astype(np.int32), "future": future, "is_val": gkey % 50 == 0})
        used.append((path, len(game)))
        del d, game, gkey  # the features are read again below, file by file
    d = {k: np.concatenate([p.pop(k) for p in small]) for k in ("keys", "white", "scores", "results", "game", "future", "is_val")}
    first = first_occurrences(d.pop("keys")).astype(np.int32)  # 32 bits hold up to 2^31 positions
    out = {k: d.pop(k)[first] for k in ("white", "scores", "results", "future", "is_val")}
    out["ngames"] = count_games(d.pop("game")[first])

    # Every file is cached by now, so frozen reads return exactly what was just used. The kept
    # positions are stored compactly (see encode) as each file is read.
    occ, pcs = np.empty(len(first), dtype=np.uint64), np.empty((len(first), 16), dtype=np.uint8)
    offset = filled = 0
    for path, n in used:
        f = load_file(path, cache_dir, frozen=True, fields=("feats",))["feats"]
        if len(f) != n:
            raise RuntimeError(f"{path} changed while loading ({n} then {len(f)} positions)")
        lo, hi = np.searchsorted(first, (offset, offset + n))
        for s in range(lo, hi, 1 << 22):  # the kept rows' features, 4M at a time
            e = min(s + (1 << 22), hi)
            occ[filled + s - lo:filled + e - lo], pcs[filled + s - lo:filled + e - lo] = encode(f[first[s:e] - offset])
        del f
        filled, offset = filled + hi - lo, offset + n
    out["occ"], out["pcs"] = occ, pcs
    return out


def load_at_once(paths, cache_dir=None, future_plies=8, frozen=False, moves=False):
    """load() with every file in memory at once; peaks at about twice the raw data."""
    parts, game_base = [], 0
    for path in paths:
        d = load_file(path, cache_dir, frozen)
        if d is None:
            continue
        d["game"], d["future"], d["gkey"] = per_file(d, game_base, future_plies)
        game_base = int(d["game"][-1]) + 1
        parts.append(d)
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

    first = first_occurrences(d["keys"]).astype(np.int32)
    out = {"feats": d["feats"][first], "white": d["white"][first], "scores": d["scores"][first],
           "results": d["results"][first], "future": d["future"][first], "is_val": d["gkey"][first] % 50 == 0,
           "ngames": count_games(d["game"][first])}
    if moves:
        pfrom, pto = played_moves(d)
        out["pfrom"], out["pto"] = pfrom[first], pto[first]
    return out


def played_moves(d, chunk=1 << 18):
    """From and to squares of the move played in each position, from the side to move's view
    (mirrored for Black, as the network sees the board), or -1 where the next recorded position is
    not the very next ply. Datagen plays the search's best move, so this is the move it chose. The
    move is the difference between the two positions: the mover's piece that left a square and the
    one that arrived (the king's, when castling moves a rook too)."""
    n = len(d["ply"])
    ply = d["ply"].astype(np.int64)
    valid = np.zeros(n, dtype=bool)
    valid[:-1] = (d["game"][1:] == d["game"][:-1]) & (ply[1:] == ply[:-1] + 1)
    nxt = np.minimum(np.arange(1, n + 1), n - 1)
    pfrom, pto = np.full(n, -1, dtype=np.int8), np.full(n, -1, dtype=np.int8)

    def moved(x, y, mover):
        # Squares of the mover's pieces in x that are not in y; the highest piece type wins.
        gone = (x != PAD) & ((x // 384) == mover) & ~(x[:, :, None] == y[:, None, :]).any(2)
        rank = np.where(gone, (x % 384) // 64, -1)
        sq = x[np.arange(len(x)), rank.argmax(1)] % 64
        return np.where(rank.max(1) >= 0, sq, -1)

    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        a, b = d["feats"][s:e].astype(np.int32), d["feats"][nxt[s:e]].astype(np.int32)
        white = d["white"][s:e] == 1
        mover = np.where(white, 0, 1)[:, None]
        f, t = moved(a, b, mover), moved(b, a, mover)
        ok = valid[s:e] & (f >= 0) & (t >= 0)
        flip = np.where(white, 0, 56)
        pfrom[s:e] = np.where(ok, f ^ flip, -1)
        pto[s:e] = np.where(ok, t ^ flip, -1)
    return pfrom, pto


def teacher_predictions(path, inputs, n, dev, data_dev, chunk=1 << 18):
    """Win probability, from the side to move's view, that an exported one-bucket network gives
    each of the n positions (`inputs` maps position indices on data_dev, and whether to mirror, to
    feature tensors on dev, as in main), kept on data_dev. The weights are dequantised back to floats,
    so this matches the engine's eval up to rounding."""
    with open(path, "rb") as f:
        magic = f.read(4)
        assert magic in (b"CSNN", b"CSNM"), "the teacher must be a one-bucket (CSNN or CSNM) network"
        (h,) = struct.unpack("<i", f.read(4))
        ft_w = np.frombuffer(f.read(PAD * h * 2), dtype="<i2").reshape(PAD, h)
        ft_b = np.frombuffer(f.read(h * 2), dtype="<i2")
        out_w = np.frombuffer(f.read(2 * h * 2), dtype="<i2")
        (out_b,) = struct.unpack("<i", f.read(4))
    w = torch.zeros(PAD + 1, h, device=dev)  # the PAD row stays zero
    w[:PAD] = torch.from_numpy(ft_w.astype(np.float32)).to(dev) / QA
    b = torch.from_numpy(ft_b.astype(np.float32)).to(dev) / QA
    ow = torch.from_numpy(out_w.astype(np.float32)).to(dev) / QB
    out = torch.empty(n, device=data_dev)
    with torch.no_grad():
        for s in range(0, n, chunk):
            idx = torch.arange(s, min(s + chunk, n), device=data_dev)
            stm, nstm = inputs(idx, magic == b"CSNM")
            a = torch.clamp(torch.nn.functional.embedding_bag(stm, w, mode="sum") + b, 0, 1) ** 2
            c = torch.clamp(torch.nn.functional.embedding_bag(nstm, w, mode="sum") + b, 0, 1) ** 2
            out[s:s + len(idx)] = torch.sigmoid(a @ ow[:h] + c @ ow[h:] + out_b / (QA * QB)).to(data_dev)
    return out


@functools.cache
def screlu_kernels():
    import cupy  # only the dense path needs it, so the CPU tools that import this file do not
    return (cupy.asarray,
            cupy.ElementwiseKernel("T a", "T x", "T c = min(max(a, (T)0), (T)1); x = c * c", "screlu"),
            cupy.ElementwiseKernel("T g, T a", "T d", "d = a >= (T)0 && a <= (T)1 ? g * ((T)2 * a) : (T)0", "screlu_grad"))


class SCReLU(torch.autograd.Function):
    """clamp(a, 0, 1) ** 2 with the gradient PyTorch gives that expression, as one CUDA kernel each way.
    The hidden layer of a batch is 200 MB at 1536 units and these operations cost what it costs to move
    that through memory, so separate clamp and power kernels, forward and backward, pay for it several
    times over."""

    @staticmethod
    def forward(ctx, a):
        view, fwd, _ = screlu_kernels()
        ctx.save_for_backward(a)
        x = torch.empty_like(a)
        fwd(view(a.detach()), view(x))
        return x

    @staticmethod
    def backward(ctx, g):
        view, _, bwd = screlu_kernels()
        (a,) = ctx.saved_tensors
        d = torch.empty_like(a)
        bwd(view(g.detach().contiguous()), view(a.detach()), view(d))
        return d


class Net(torch.nn.Module):
    def __init__(self, hidden, aux=False, policy=False, teacher=False, dense=True):
        super().__init__()
        self.dense = dense
        self.ft = torch.nn.EmbeddingBag(PAD + 1, hidden, mode="sum", padding_idx=PAD)
        self.ft_bias = torch.nn.Parameter(torch.zeros(hidden))
        self.out = torch.nn.Linear(2 * hidden, 1)
        # Auxiliary head, used only in training and not exported: predicts the outcome a few plies
        # later from the same hidden layer, as extra signal for the shared first layer.
        self.aux = torch.nn.Linear(2 * hidden, 1) if aux else None
        # Policy head, also training only: logits for the played move's from square (first 64)
        # and to square (last 64).
        self.policy = torch.nn.Linear(2 * hidden, 128) if policy else None
        with torch.no_grad():
            self.ft.weight.uniform_(-0.05, 0.05)
            self.ft.weight[PAD].zero_()
        # Teacher head, also training only: predicts an earlier network's evaluation. Made after
        # the first layer's initialisation, so a run with a teacher starts from the same weights
        # as one without.
        self.teach = torch.nn.Linear(2 * hidden, 1) if teacher else None

    def forward(self, stm, nstm):
        if self.dense:
            return self.forward_dense(stm, nstm)
        a = torch.clamp(self.ft(stm) + self.ft_bias, 0, 1) ** 2
        b = torch.clamp(self.ft(nstm) + self.ft_bias, 0, 1) ** 2
        x = torch.cat([a, b], dim=1)
        return (self.out(x).squeeze(1), self.aux(x).squeeze(1) if self.aux is not None else None,
                self.policy(x) if self.policy is not None else None,
                self.teach(x).squeeze(1) if self.teach is not None else None)

    def forward_dense(self, stm, nstm):
        """forward() as matrix products, the same function of the same parameters. Both perspectives
        are the rows of one 0/1 matrix, (2 * batch, 769): a 1 for each feature present, and a last
        column of ones that multiplies the bias, appended to the weights as row 768. EmbeddingBag's
        backward sorts every index and re-reads each position's gradient row once per piece; here the
        weight gradient is one more product. This works while there are only 768 features: the cost
        grows with the number of feature rows, not with the pieces on the board."""
        n, w = stm.shape[0], self.ft.weight
        x = torch.zeros(2 * n, PAD + 1, dtype=w.dtype, device=w.device)
        x.scatter_(1, torch.cat([stm, nstm]), 1.0)
        x[:, PAD] = 1.0
        hidden = SCReLU.apply(x @ torch.cat([w[:PAD], self.ft_bias[None]])).view(2, n, -1)
        slots = (self.out, self.aux, self.policy, self.teach)
        heads = [h for h in slots if h is not None]
        # Each head's weights as (perspective, hidden, output), so no (batch, 2 * hidden) copy is needed.
        hw = torch.cat([h.weight for h in heads]).view(-1, 2, hidden.shape[2]).permute(1, 2, 0)
        y = (hidden @ hw).sum(0) + torch.cat([h.bias for h in heads])
        parts = iter(y.split([h.out_features for h in heads], dim=1))
        return tuple(next(parts).squeeze(1) if h is not None else None for h in slots)

    def clip(self):
        # Keeps quantised values in range: QA * w and QB * w must fit int16, and the int32
        # output sum must not overflow (see src/nnue.cpp).
        with torch.no_grad():
            self.ft.weight.clamp_(-1.98, 1.98)
            self.out.weight.clamp_(-1.98, 1.98)


def export(net, path, mirror):
    hidden = net.ft_bias.shape[0]
    ft_w = torch.round(net.ft.weight[:PAD] * QA).to(torch.int16).cpu().numpy()
    ft_b = torch.round(net.ft_bias * QA).to(torch.int16).cpu().numpy()
    out_w = torch.round(net.out.weight[0] * QB).to(torch.int16).cpu().numpy()
    out_b = int(round(net.out.bias.item() * QA * QB))
    with open(path, "wb") as f:
        f.write(b"CSNM" if mirror else b"CSNN")
        f.write(struct.pack("<i", hidden))
        f.write(ft_w.astype("<i2").tobytes())
        f.write(ft_b.astype("<i2").tobytes())
        f.write(out_w.astype("<i2").tobytes())
        f.write(struct.pack("<i", out_b))


SHARD_COLS = {"occ": np.uint64, "pcs": np.uint8, "white": np.int8, "scores": np.float32, "results": np.float32,
              "future": np.float32, "isval": np.uint8, "keep": np.uint8}


def shard_items(dirs):
    """(path stem, positions) of every shard in the directories, in manifest order (see shards.py)."""
    out = []
    for d in dirs:
        for m in sorted(glob.glob(os.path.join(d, "*.manifest"))):
            with open(m) as f:
                out.extend((os.path.join(d, line.split()[0]), int(line.split()[1])) for line in f if line.strip())
    return out


def shard_rows(stem, n, val):
    """The kept training (val=False) or validation (val=True) rows of one shard, as a dict of arrays."""
    def col(c):
        a = np.fromfile(f"{stem}.{c}", dtype=SHARD_COLS[c])
        a = a.reshape(-1, 16) if c == "pcs" else a
        if len(a) != n:
            raise RuntimeError(f"{stem}.{c}: {len(a)} rows, the manifest says {n}")
        return a
    held = col("isval").astype(bool)
    idx = np.flatnonzero(col("keep").astype(bool) & (held if val else ~held))
    return {c: col(c)[idx] for c in ("occ", "pcs", "white", "scores", "results", "future")}


def concat_shuffled(parts, rng):
    n = sum(len(p["white"]) for p in parts)
    perm = rng.permutation(n)
    return {c: np.concatenate([p[c] for p in parts])[perm] for c in parts[0]}


def train_streaming(args):
    """Training from shards on disk, so the data can be far larger than RAM. Each epoch reads every shard
    once, in a fresh random order, --group shards at a time: their kept training rows are loaded,
    shuffled together and trained on, while a background thread loads the next group. Validation is the
    first --val-max kept validation rows. The targets are the in-memory trainer's, computed per batch.
    After every epoch the network is exported to <out>.eNN and the run's state saved to <out>.pt, which
    --resume continues from."""
    import queue
    import threading

    t0 = time.time()
    torch.manual_seed(args.seed)
    items = shard_items(args.shards)
    for d in args.shards:
        with open(os.path.join(d, "FUTURE_PLIES")) as f:
            if int(f.read()) != args.future_plies:
                raise SystemExit(f"{d} holds future targets for another --future-plies")
    ntrain = nval = 0
    for stem, n in items:
        keep = np.fromfile(f"{stem}.keep", dtype=np.uint8).astype(bool)
        held = np.fromfile(f"{stem}.isval", dtype=np.uint8).astype(bool)
        ntrain += int(np.count_nonzero(keep & ~held))
        nval += int(np.count_nonzero(keep & held))
    val_parts, got = [], 0
    for stem, n in items:
        if got >= args.val_max:
            break
        p = shard_rows(stem, n, val=True)
        val_parts.append(p)
        got += len(p["white"])
    val = {c: np.concatenate([p[c] for p in val_parts])[:args.val_max] for c in val_parts[0]}
    del val_parts
    print(f"{len(items)} shards: {ntrain} training positions, {nval} validation ({len(val['white'])} used), "
          f"{sum(n for _, n in items)} before deduplication; set up in {time.time() - t0:.0f}s", flush=True)

    dev = torch.device("cuda")
    flip_t = torch.from_numpy(FLIP).to(dev)
    net = Net(args.hidden, aux=args.aux_weight > 0, dense=args.ft == "dense").to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    first_epoch = 1
    state_path = args.out + ".pt"
    if args.resume:
        state = torch.load(state_path, map_location=dev)
        if state["args"]["epochs"] != args.epochs:  # the schedule's length is fixed at the start
            raise SystemExit(f"{state_path} was started with --epochs {state['args']['epochs']}")
        if state["args"].get("mirror", False) != args.mirror:
            raise SystemExit(f"{state_path} was started {'without' if args.mirror else 'with'} --mirror")
        net.load_state_dict(state["net"])
        opt.load_state_dict(state["opt"])
        sched.load_state_dict(state["sched"])
        first_epoch = state["epoch"] + 1
        print(f"resumed after epoch {state['epoch']}", flush=True)

    def on_gpu(b):
        """Rows as GPU tensors: occupancy, pieces, side to move, and the main and auxiliary targets."""
        occ = torch.from_numpy(b["occ"].view(np.int64)).to(dev)
        pcs = torch.from_numpy(b["pcs"]).to(dev)
        w = torch.from_numpy(b["white"]).to(dev).bool()
        score = torch.from_numpy(b["scores"]).to(dev) * (w.float() * 2 - 1)
        result_w = torch.from_numpy(b["results"]).to(dev)
        target = args.lam * torch.sigmoid(score / SCALE) + (1 - args.lam) * torch.where(w, result_w, 1 - result_w)
        future_w = torch.from_numpy(b["future"]).to(dev)
        return occ, pcs, w, target, torch.where(w, future_w, 1 - future_w)

    def losses(occ, pcs, w, target, future):
        main, aux, _, _ = net(*views(decode(occ, pcs), w, flip_t, args.mirror))
        main_loss = torch.mean((torch.sigmoid(main) - target) ** 2)
        if aux is None:
            return main_loss, torch.zeros((), device=dev)
        return main_loss, torch.mean((torch.sigmoid(aux) - future) ** 2)

    def groups(epoch):
        # The epoch's shard order and each group's shuffle come from (seed, epoch), so a resumed run
        # sees the order it would have seen.
        order = np.random.default_rng([args.seed, epoch]).permutation(len(items))
        for g, s in enumerate(range(0, len(order), args.group)):
            parts = [shard_rows(*items[i], val=False) for i in order[s:s + args.group]]
            yield concat_shuffled(parts, np.random.default_rng([args.seed, epoch, g]))

    def prefetch(gen):
        q = queue.Queue(maxsize=1)

        def run():
            for x in gen:
                q.put(x)
            q.put(None)
        threading.Thread(target=run, daemon=True).start()
        while (x := q.get()) is not None:
            yield x

    # A copy from host memory and a loss read back with .item() both wait for the GPU to finish all
    # queued work, and with several in every step the Python side of a step could not overlap the GPU
    # side. So rows go to the GPU 64 batches at a time, and the loss total stays there until the epoch
    # ends (in float64, the same sum Python made of the .item() values).
    block = 64 * args.batch
    for epoch in range(first_epoch, args.epochs + 1):
        net.train()
        total, seen, te = torch.zeros((), dtype=torch.float64, device=dev), 0, time.time()
        for g in prefetch(groups(epoch)):
            m = len(g["white"])
            for s in range(0, m, block):
                rows = on_gpu({c: g[c][s:s + block] for c in g})
                for i in range(0, len(rows[0]), args.batch):
                    b = [t[i:i + args.batch] for t in rows]
                    opt.zero_grad()
                    main_loss, aux_loss = losses(*b)
                    (main_loss + args.aux_weight * aux_loss).backward()
                    opt.step()
                    net.clip()
                    total += main_loss.detach().double() * len(b[0])
            seen += m
            torch.cuda.synchronize()  # the rate below counts finished steps, not queued ones
            print(f"  epoch {epoch}: {seen}/{ntrain} positions, {seen / (time.time() - te):,.0f}/s", flush=True)
        sched.step()
        net.eval()
        v = va = 0.0
        nv = len(val["white"])
        with torch.no_grad():
            for i in range(0, nv, 65536):
                b = on_gpu({c: val[c][i:i + 65536] for c in val})
                main_loss, aux_loss = losses(*b)
                v += main_loss.item() * len(b[0])
                va += aux_loss.item() * len(b[0])
        aux_text = f" aux {va / nv:.5f}" if args.aux_weight > 0 else ""
        print(f"epoch {epoch:3d} train {total.item() / seen:.5f} val {v / nv:.5f}{aux_text}  ({time.time() - t0:.0f}s)", flush=True)
        export(net, f"{args.out}.e{epoch:02d}", args.mirror)
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "epoch": epoch,
                    "args": vars(args)}, state_path + ".tmp")
        os.replace(state_path + ".tmp", state_path)
        if args.stop_after and epoch >= args.stop_after:
            print(f"stopped after epoch {epoch} (--stop-after); continue with --resume", flush=True)
            return

    export(net, args.out, args.mirror)
    print(f"wrote {args.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="*", help="datagen text files (not with --shards)")
    ap.add_argument("out")
    ap.add_argument("--shards", action="append", help="train streaming from a shard directory (see shards.py); repeatable")
    ap.add_argument("--group", type=int, default=8, help="with --shards: shards shuffled together in memory at once")
    ap.add_argument("--val-max", type=int, default=20_000_000, help="with --shards: validation positions kept")
    ap.add_argument("--resume", action="store_true", help="with --shards: continue from <out>.pt")
    ap.add_argument("--stop-after", type=int, help="with --shards: stop after this epoch (the schedule still spans --epochs)")
    ap.add_argument("--ft", choices=("dense", "bag"), default="dense",
                    help="first layer as a matrix product (needs CuPy) or as torch's EmbeddingBag, the slower earlier path")
    ap.add_argument("--mirror", action="store_true",
                    help="mirror each perspective's squares left to right while its king is on files e-h (exports CSNM)")
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=16384)
    ap.add_argument("--lr", type=float, default=0.001)
    ap.add_argument("--lambda", dest="lam", type=float, default=0.75)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cache-dir", default=None, help="keeps parsed data per file; later runs parse only new lines")
    ap.add_argument("--frozen", action="store_true", help="use only already-cached data (see --cache-dir)")
    ap.add_argument("--aux-weight", type=float, default=0.0, help="weight of the auxiliary future-outcome loss")
    ap.add_argument("--future-plies", type=int, default=8)
    ap.add_argument("--gpu-data-gb", type=float, default=6.0, help="above this, positions stay in host RAM")
    ap.add_argument("--policy-weight", type=float, default=0.0, help="weight of the auxiliary played-move loss")
    ap.add_argument("--teacher", help="an exported network whose evaluation a training-only head learns")
    ap.add_argument("--teacher-weight", type=float, default=1.0, help="weight of the teacher loss (with --teacher)")
    args = ap.parse_args()
    if args.ft == "dense":
        try:
            screlu_kernels()
        except ImportError:
            ap.error("--ft dense needs CuPy (see gpu/README.md); --ft bag runs without it")
    if args.shards:
        if args.data or args.policy_weight > 0 or args.teacher:
            ap.error("--shards takes no data files, --policy-weight or --teacher")
        return train_streaming(args)
    if not args.data:
        ap.error("give data files or --shards")

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    t0 = time.time()
    policy = args.policy_weight > 0
    d = load(args.data, args.cache_dir, args.future_plies, args.frozen, moves=policy)
    n = len(d["scores"])
    # Validation holds whole games, about 2%, chosen by each game's stable key. So no game has
    # positions on both sides, and the same games stay held out as data grows and from one network
    # generation to the next. Networks trained before this split (net8 and earlier) used a random
    # one, so they did train on some of these games. --seed now sets only initialisation and order.
    games = d.pop("ngames")
    is_val = d.pop("is_val")
    val, train = np.flatnonzero(is_val).astype(np.int32), np.flatnonzero(~is_val).astype(np.int32)
    moves_text = f"; {np.mean(d['pfrom'] >= 0):.0%} have the played move" if policy else ""
    print(f"{n} unique positions from {games} games ({len(train)} train, {len(val)} validation), "
          f"loaded in {time.time() - t0:.0f}s{moves_text}", flush=True)

    dev = torch.device("cuda")
    # Positions are stored compactly (24 bytes, see encode) and decoded and flipped per batch on the
    # GPU. Up to --gpu-data-gb everything per position lives on the GPU. Above it, everything per
    # position (positions, targets, indices, the shuffle) stays in host RAM, and each batch is gathered
    # there and copied over: at 537M positions the targets and indices alone, with a GPU shuffle,
    # passed a 16 GB card, and Windows paged GPU memory to RAM instead.
    if "feats" in d:  # load_at_once keeps the feature lists
        d["occ"], d["pcs"] = encode(d.pop("feats"))
    on_gpu = d["occ"].nbytes + d["pcs"].nbytes <= args.gpu_data_gb * 1e9
    data_dev = dev if on_gpu else torch.device("cpu")
    occ_t = torch.from_numpy(d["occ"].view(np.int64)).to(data_dev)
    pcs_t = torch.from_numpy(d["pcs"]).to(data_dev)
    white_t = torch.from_numpy(d["white"]).to(data_dev).bool()
    flip_t = torch.from_numpy(FLIP).to(dev)
    # Targets are computed on the GPU in either case (chunk by chunk), so both modes train on the
    # same float32 values.
    target = torch.empty(n, device=data_dev)
    future_t = torch.empty(n, device=data_dev)
    for s in range(0, n, 1 << 24):
        sl = slice(s, min(s + (1 << 24), n))
        w = torch.from_numpy(d["white"][sl]).to(dev).bool()
        score = torch.from_numpy(d["scores"][sl]).to(dev) * (w.float() * 2 - 1)
        result_w = torch.from_numpy(d["results"][sl]).to(dev)
        target[sl] = (args.lam * torch.sigmoid(score / SCALE) + (1 - args.lam) * torch.where(w, result_w, 1 - result_w)).to(data_dev)
        future_w = torch.from_numpy(d["future"][sl]).to(dev)
        future_t[sl] = torch.where(w, future_w, 1 - future_w).to(data_dev)
    if policy:
        pfrom_t = torch.from_numpy(d["pfrom"].astype(np.int64)).to(data_dev)
        pto_t = torch.from_numpy(d["pto"].astype(np.int64)).to(data_dev)
    del d

    def to_dev(x):
        return x.to(dev, non_blocking=True)

    def inputs(idx, mirror=args.mirror):  # idx on data_dev
        return views(decode(to_dev(occ_t[idx]), to_dev(pcs_t[idx])), to_dev(white_t[idx]), flip_t, mirror)

    train_t, val_t = torch.from_numpy(train).to(data_dev), torch.from_numpy(val).to(data_dev)
    teacher = args.teacher is not None
    if teacher:
        teacher_t = teacher_predictions(args.teacher, inputs, n, dev, data_dev)
        tv = torch.mean((teacher_t[val_t] - target[val_t]) ** 2).item()
        print(f"teacher {os.path.basename(args.teacher)}: validation loss {tv:.5f} on this run's target", flush=True)

    net = Net(args.hidden, aux=args.aux_weight > 0, policy=args.policy_weight > 0, teacher=teacher,
              dense=args.ft == "dense").to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    zero = torch.zeros((), device=dev)

    def losses(idx):
        main, aux, pol, teach = net(*inputs(idx))
        main_loss = torch.mean((torch.sigmoid(main) - to_dev(target[idx])) ** 2)
        aux_loss = torch.mean((torch.sigmoid(aux) - to_dev(future_t[idx])) ** 2) if aux is not None else zero
        pol_loss = zero
        if pol is not None:
            f, t = to_dev(pfrom_t[idx]), to_dev(pto_t[idx])
            ok = f >= 0
            if ok.any():
                ce = torch.nn.functional.cross_entropy
                pol_loss = ce(pol[ok, :64], f[ok]) + ce(pol[ok, 64:], t[ok])
        teach_loss = torch.mean((torch.sigmoid(teach) - to_dev(teacher_t[idx])) ** 2) if teach is not None else zero
        return main_loss, aux_loss, pol_loss, teach_loss

    shuffle = torch.Generator().manual_seed(args.seed)  # on the CPU: the same order in either mode
    for epoch in range(1, args.epochs + 1):
        net.train()
        order = train_t[torch.randperm(len(train_t), generator=shuffle, dtype=torch.int32).to(data_dev)]
        total = torch.zeros((), dtype=torch.float64, device=dev)  # on the GPU: see train_streaming
        for i in range(0, len(order), args.batch):
            idx = order[i:i + args.batch]
            opt.zero_grad()
            main_loss, aux_loss, pol_loss, teach_loss = losses(idx)
            (main_loss + args.aux_weight * aux_loss + args.policy_weight * pol_loss
             + args.teacher_weight * teach_loss).backward()
            opt.step()
            net.clip()
            total += main_loss.detach().double() * len(idx)
        total = total.item()
        sched.step()
        net.eval()
        v = va = vp = vt = 0.0
        with torch.no_grad():
            for i in range(0, len(val_t), 65536):
                idx = val_t[i:i + 65536]
                main_loss, aux_loss, pol_loss, teach_loss = losses(idx)
                v += main_loss.item() * len(idx)
                va += aux_loss.item() * len(idx)
                vp += pol_loss.item() * len(idx)
                vt += teach_loss.item() * len(idx)
        aux_text = f" aux {va / len(val):.5f}" if args.aux_weight > 0 else ""
        aux_text += f" policy {vp / len(val):.3f}" if args.policy_weight > 0 else ""
        aux_text += f" teacher {vt / len(val):.5f}" if teacher else ""
        print(f"epoch {epoch:3d} train {total / len(train):.5f} val {v / len(val):.5f}{aux_text}  "
              f"({time.time() - t0:.0f}s)", flush=True)

    export(net.cpu(), args.out, args.mirror)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
