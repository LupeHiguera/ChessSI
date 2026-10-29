"""Train ChessSI's NNUE on positions in the datagen text format.

    python train.py <data.txt>... <out.nnue> [--hidden 128] [--epochs 20] [--lambda 0.75] [--cache-dir dir]
                    [--aux-weight 0] [--future-plies 8] [--policy-weight 0]
                    [--buckets 8|16] [--init nets/net12-h256.nnue]

Network: (768 -> H) x 2 perspectives -> SCReLU -> 1, the usual first NNUE. Input features are
(piece colour relative to the perspective, piece type, square), with squares mirrored vertically for
Black's perspective. The output, times SCALE, is centipawns for the side to move.

net13 adds king buckets on that feature transformer (CSKB), for gen9+ datagen and the net. It is
not a trained result and it claims no Elo. Omit --buckets to train a CSNN network, which is the
net12 recipe.

    --buckets 8    8 king buckets x 768, factorized as W = W0 + U. Requires --init.
    --buckets 16   16 buckets, same factorization. Requires --init.

Bucket id (friendly king, real board; arch.king_bucket and NNUE::king_bucket, the formula from
the research note in PR #69): if the file is a-d, mirror with ^ 7. 8 buckets is that e-h file
times ranks 1-4 vs 5-8. 16 is that file times the pairs (1-2, 3-4, 5-6, 7-8). Export folds
W0+U into a dense CSKB table. A king move refreshes that perspective; any other move is one add
and one sub of the current bucket. gpu/datagen.cu and gpu/nnue.cu load CSKB the same way, so a
net13 file can generate gen9.

--init copies W0 and the output from net12's int16 rows, dequantized, and sets U to 0. Before the
data load the integer eval is compared with that file on --init-check positions (default 1000)
and training stops if any position differs by more than 1 cp. The cache stores the 768 features,
not the bucket, so a bucketed run can share a CSNN run's --cache-dir.

5060 Ti, host mode, the net12 recipe otherwise (batch 16384, lambda 0.75). The data is the
generation-8 unique set net12 used, or a frozen slice of it. This script does not cut the slice.

    python train.py $DATA net13-k8.nnue --buckets 8 --init nets/net12-h256.nnue --hidden 256 --epochs 20 --seed 1 --cache-dir $CACHE --aux-weight 1.0 --future-plies 4 --gpu-data-gb 0

    python train.py $DATA net13-k16.nnue --buckets 16 --init nets/net12-h256.nnue --hidden 256 --epochs 20 --seed 1 --cache-dir $CACHE --aux-weight 1.0 --future-plies 4 --gpu-data-gb 0

gen9 self-play, after a net13 file exists, on the 5080:

    python gpu/datagen.py run net13-k8.nnue gen9.txt <games> 5000

Nothing here has been trained.

Loss: mean squared error between sigmoid(output) and a blend of sigmoid(score / SCALE) and the game
result, both from the side to move: target = lambda * score + (1 - lambda) * result. With
--aux-weight, a second head (training only, not exported) also learns the win probability
--future-plies later in the game. With --policy-weight, a third training-only head learns the
from and to squares of the move played (cross-entropy), where the next recorded position shows it.
With --teacher <net.nnue>, a training-only head learns that network's evaluation of each position
(self-distillation from an earlier ChessSI network), weighted by --teacher-weight.

Export (little-endian, see nnue/arch.py and src/nnue.cpp): CSNN as before; CSKB when --buckets
is 8 or 16. QA, QB and SCALE live in arch.py.
"""
import argparse
import hashlib
import os
import math
import random
import struct
from array import array
import time

import numpy as np
import torch

from arch import PAD, PIECES, QA, QB, SCALE, evaluate, features, load_csnn, pack_cskb, pack_csnn


# FLIP[f] is feature f seen from the other side: colours swap, squares mirror vertically. So one
# White-perspective list per position is enough; the Black one is FLIP applied to it.
FLIP = np.array([((f + 384) % 768) ^ 56 for f in range(PAD)] + [PAD], dtype=np.int64)


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
SQ_FEN = np.array([r * 8 + f for r in range(7, -1, -1) for f in range(8)], dtype=np.int64)


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
    f = torch.where(bits.bool(), piece * 64 + asc, PAD)[:, torch.from_numpy(SQ_FEN).to(dev)]
    order = torch.sort((f == PAD).to(torch.int8), dim=1, stable=True).indices[:, :32]
    return torch.gather(f, 1, order)


FIELDS = ("feats", "white", "scores", "results", "keys", "ply")
# Cache files are named <data file>.v<CACHE_VERSION>.<byte offset>.npz. Version 2: deterministic
# position keys (version 1 used Python's hash(), which differs between processes, so duplicates in
# chunks cached by different runs were never found).
CACHE_VERSION = 2


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
        stem = os.path.join(cache_dir, f"{os.path.basename(path)}.v{CACHE_VERSION}")
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
    each of the n positions (`inputs` maps position indices on data_dev to feature tensors on dev,
    as in main), kept on data_dev. The weights are dequantised back to floats, so this matches the
    engine's eval up to rounding."""
    with open(path, "rb") as f:
        assert f.read(4) == b"CSNN", "the teacher must be a one-bucket (CSNN) network"
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
            stm, nstm = inputs(idx)[:2]
            a = torch.clamp(torch.nn.functional.embedding_bag(stm, w, mode="sum") + b, 0, 1) ** 2
            c = torch.clamp(torch.nn.functional.embedding_bag(nstm, w, mode="sum") + b, 0, 1) ** 2
            out[s:s + len(idx)] = torch.sigmoid(a @ ow[:h] + c @ ow[h:] + out_b / (QA * QB)).to(data_dev)
    return out


class Net(torch.nn.Module):
    def __init__(self, hidden, aux=False, policy=False, teacher=False, buckets=1):
        super().__init__()
        self.n_buckets = buckets
        # W0, shared across king buckets. With buckets == 1 this is the whole feature transformer.
        self.ft = torch.nn.EmbeddingBag(PAD + 1, hidden, mode="sum", padding_idx=PAD)
        self.ft_bias = torch.nn.Parameter(torch.zeros(hidden))
        self.out = torch.nn.Linear(2 * hidden, 1)
        # U[bucket, feature], the net13 factoriser offset. Export folds W0 + U into a dense table.
        # The last row is the padding index and stays zero.
        if buckets > 1:
            self.U = torch.nn.EmbeddingBag(buckets * PAD + 1, hidden, mode="sum", padding_idx=buckets * PAD)
        else:
            self.U = None
        # Auxiliary head, used only in training and not exported: predicts the outcome a few plies
        # later from the same hidden layer, as extra signal for the shared first layer.
        self.aux = torch.nn.Linear(2 * hidden, 1) if aux else None
        # Policy head, also training only: logits for the played move's from square (first 64)
        # and to square (last 64).
        self.policy = torch.nn.Linear(2 * hidden, 128) if policy else None
        with torch.no_grad():
            self.ft.weight.uniform_(-0.05, 0.05)
            self.ft.weight[PAD].zero_()
            if self.U is not None:
                self.U.weight.zero_()
        # Teacher head, also training only: predicts an earlier network's evaluation. Made after
        # the first layer's initialisation, so a run with a teacher starts from the same weights
        # as one without.
        self.teach = torch.nn.Linear(2 * hidden, 1) if teacher else None

    def embed(self, feats, buckets):
        # W[bucket, feature] = W0[feature] + U[bucket, feature]. U is absent on a 768 net.
        x = self.ft(feats)
        if self.U is not None:
            pad = self.n_buckets * PAD
            idx = buckets.reshape(-1, 1) * PAD + feats
            idx = torch.where(feats == PAD, pad, idx)
            x = x + self.U(idx)
        return x + self.ft_bias

    def forward(self, stm, nstm, stm_bucket=None, nstm_bucket=None):
        a = torch.clamp(self.embed(stm, stm_bucket), 0, 1) ** 2
        b = torch.clamp(self.embed(nstm, nstm_bucket), 0, 1) ** 2
        x = torch.cat([a, b], dim=1)
        main = self.out(x).squeeze(1)
        return (main, self.aux(x).squeeze(1) if self.aux is not None else None,
                self.policy(x) if self.policy is not None else None,
                self.teach(x).squeeze(1) if self.teach is not None else None)

    def clip(self):
        # Keeps quantised values in range: QA * w and QB * w must fit int16, and the int32
        # output sum must not overflow (see src/nnue.cpp). The folded bucket row, not W0 or U
        # alone, is what the accumulator adds.
        with torch.no_grad():
            w0 = self.ft.weight[:PAD]
            w0.clamp_(-1.98, 1.98)
            if self.U is not None:
                u = self.U.weight[:-1].view(self.n_buckets, PAD, -1)
                u.copy_(torch.clamp(w0.unsqueeze(0) + u, -1.98, 1.98) - w0.unsqueeze(0))
                self.U.weight[-1].zero_()
            self.ft.weight[PAD].zero_()
            self.out.weight.clamp_(-1.98, 1.98)

    def copy_init(self, path):
        """W0 and the output dot from a CSNN file (net12). Bucket offsets stay 0."""
        raw = load_csnn(path)
        hidden = self.ft_bias.shape[0]
        if raw["hidden"] != hidden:
            raise SystemExit(f"{path} has hidden {raw['hidden']}, this arm wants {hidden}")
        with torch.no_grad():
            self.ft.weight[:PAD].copy_(torch.from_numpy(raw["ft_w"][0].astype(np.float32) / QA))
            self.ft.weight[PAD].zero_()
            self.ft_bias.copy_(torch.from_numpy(raw["ft_b"].astype(np.float32) / QA))
            self.out.weight.copy_(torch.from_numpy(raw["out_w"].astype(np.float32) / QB).view(1, -1))
            self.out.bias.copy_(torch.tensor([raw["out_b"] / (QA * QB)], dtype=torch.float32))
            if self.U is not None:
                self.U.weight.zero_()


def _round_i16(t):
    return torch.round(t).clamp(-32767, 32767).to(torch.int16).cpu().numpy()


def export(net, path=None):
    """Write CSNN, or CSKB with W0+U folded. Returns the bytes as well."""
    hidden = int(net.ft_bias.shape[0])
    ft_b = _round_i16(net.ft_bias.detach() * QA)
    out_w = _round_i16(net.out.weight.detach()[0] * QB)
    out_b = int(round(net.out.bias.detach().item() * QA * QB))
    if net.U is not None:
        w0 = net.ft.weight.detach()[:PAD]
        u = net.U.weight.detach()[:-1].view(net.n_buckets, PAD, hidden)
        ft_w = _round_i16((w0.unsqueeze(0) + u) * QA)
        blob = pack_cskb(hidden, net.n_buckets, ft_w, ft_b, out_w, out_b)
    else:
        ft_w = _round_i16(net.ft.weight.detach()[:PAD] * QA)
        blob = pack_csnn(hidden, ft_w, ft_b, out_w, out_b)
    if path is not None:
        with open(path, "wb") as f:
            f.write(blob)
    return blob


# Same formula as arch.king_bucket, on a tensor of real-board squares.
def bucket_ids(sq, n_buckets):
    sq = sq.long()
    mirrored = torch.where((sq & 7) < 4, sq ^ 7, sq)
    file_id = (mirrored & 7) - 4
    rank = sq >> 3
    if n_buckets == 8:
        return file_id + 4 * (rank >= 4).long()
    return file_id + 4 * (rank >> 1)


def perspective_buckets(white_feats, n_buckets):
    """White-perspective feature lists -> (white king bucket, black king bucket)."""
    wk = (white_feats >= 320) & (white_feats < 384)
    bk = (white_feats >= 704) & (white_feats < 768)
    zero = torch.zeros((), dtype=white_feats.dtype, device=white_feats.device)
    wsq = torch.where(wk, white_feats - 320, zero).sum(1)
    bsq = torch.where(bk, white_feats - 704, zero).sum(1)
    return bucket_ids(wsq, n_buckets), bucket_ids(bsq, n_buckets)


def read_check_fens(path, n):
    fens = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            fen = line.split("|", 1)[0].strip()
            parts = fen.split()
            if len(parts) >= 2 and parts[1] in ("w", "b"):
                fens.append(fen)
            if len(fens) >= n:
                break
    return fens


def step0_check(blob, init_path, fens):
    """Integer eval of the export against the init file. Within 1 cp on every position, or do not train."""
    init = open(init_path, "rb").read()
    worst = 0
    bad = 0
    for fen in fens:
        diff = abs(evaluate(blob, fen) - evaluate(init, fen))
        worst = max(worst, diff)
        bad += diff > 1
    if bad:
        raise SystemExit(
            f"step-0 init check failed: {bad}/{len(fens)} positions differ from {init_path} "
            f"by more than 1 cp (max |diff| {worst}). Not training.")
    print(f"step-0 init check: {len(fens)} positions, max |diff| {worst} cp", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="+")
    ap.add_argument("out")
    ap.add_argument("--hidden", type=int, default=None)
    ap.add_argument("--buckets", type=int, default=1, choices=(1, 8, 16),
                    help="king buckets. 8 or 16 is net13 (CSKB) and needs --init; 1 is today's CSNN")
    ap.add_argument("--init", default=None, help="CSNN file copied into W0 and the output (net12 for net13)")
    ap.add_argument("--init-check", type=int, default=None,
                    help="positions for the step-0 integer check (default 1000 when --init is required)")
    ap.add_argument("--init-check-file", default=None,
                    help="FENs or datagen lines for the step-0 check (default: the first data file)")
    ap.add_argument("--init-only", action="store_true",
                    help="write the initialized network and exit, before loading the training set")
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

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    buckets = args.buckets
    if buckets > 1 and not args.init:
        raise SystemExit("--buckets 8 or 16 needs --init so step 0 matches that CSNN file (net12)")
    if buckets == 1 and args.init:
        raise SystemExit("--init is for net13 (--buckets 8 or 16). A CSNN run starts fresh")
    hidden = args.hidden
    if hidden is None:
        hidden = 256 if buckets > 1 else 128
    if args.init_check is None:
        args.init_check = 1000 if buckets > 1 else 0

    print(f"{'net13' if buckets > 1 else 'csnn'} hidden {hidden} buckets {buckets} "
          f"init {args.init or 'fresh'}", flush=True)
    policy = args.policy_weight > 0
    teacher = args.teacher is not None
    # Built before the data load so a failed step-0 check does not read the training set.
    net = Net(hidden, aux=args.aux_weight > 0, policy=policy, teacher=teacher, buckets=buckets)
    if args.init:
        net.copy_init(args.init)
        if args.init_check:
            src = args.init_check_file or args.data[0]
            fens = read_check_fens(src, args.init_check)
            if len(fens) < args.init_check:
                raise SystemExit(f"{src}: needed {args.init_check} FENs for the step-0 check, found {len(fens)}")
            step0_check(export(net), args.init, fens)
    if args.init_only:
        export(net, args.out)
        print(f"wrote {args.out}")
        return

    t0 = time.time()
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

    def inputs(idx):  # idx on data_dev
        w = decode(to_dev(occ_t[idx]), to_dev(pcs_t[idx]))
        b = flip_t[w]
        wt = to_dev(white_t[idx]).unsqueeze(1)
        stm, nstm = torch.where(wt, w, b), torch.where(wt, b, w)
        if net.U is None:
            return stm, nstm
        # Buckets come from the white-perspective list (real king squares), then follow the side.
        wb, bb = perspective_buckets(w, net.n_buckets)
        side = wt.squeeze(1)
        return stm, nstm, torch.where(side, wb, bb), torch.where(side, bb, wb)

    net = net.to(dev)
    train_t, val_t = torch.from_numpy(train).to(data_dev), torch.from_numpy(val).to(data_dev)
    if teacher:
        teacher_t = teacher_predictions(args.teacher, inputs, n, dev, data_dev)
        tv = torch.mean((teacher_t[val_t] - target[val_t]) ** 2).item()
        print(f"teacher {os.path.basename(args.teacher)}: validation loss {tv:.5f} on this run's target", flush=True)

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
        total = 0.0
        for i in range(0, len(order), args.batch):
            idx = order[i:i + args.batch]
            opt.zero_grad()
            main_loss, aux_loss, pol_loss, teach_loss = losses(idx)
            (main_loss + args.aux_weight * aux_loss + args.policy_weight * pol_loss
             + args.teacher_weight * teach_loss).backward()
            opt.step()
            net.clip()
            total += main_loss.item() * len(idx)
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

    export(net.cpu(), args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
