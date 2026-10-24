"""Train ChessSI's NNUE on positions in the datagen text format.

    python train.py <data.txt>... <out.nnue> [--hidden 128] [--epochs 20] [--lambda 0.75] [--cache-dir dir]
                    [--aux-weight 0] [--future-plies 8] [--policy-weight 0]

Network: (768 -> H) x 2 perspectives -> SCReLU -> 1, the usual first NNUE. Input features are
(piece colour relative to the perspective, piece type, square), with squares mirrored vertically for
Black's perspective. The output, times SCALE, is centipawns for the side to move.

Loss: mean squared error between sigmoid(output) and a blend of sigmoid(score / SCALE) and the game
result, both from the side to move: target = lambda * score + (1 - lambda) * result. With
--aux-weight, a second head (training only, not exported) also learns the win probability
--future-plies later in the game. With --policy-weight, a third training-only head learns the
from and to squares of the move played (cross-entropy), where the next recorded position shows it.
With --teacher <net.nnue>, a training-only head learns that network's evaluation of each position
(self-distillation from an earlier ChessSI network), weighted by --teacher-weight.

Export (little-endian, see src/nnue.cpp): magic "CSNN", hidden size (int32), feature weights
int16[768][H] and biases int16[H] scaled by QA, output weights int16[2H] scaled by QB, output bias
int32 scaled by QA * QB.
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

SCALE = 400
QA, QB = 255, 64
PIECES = {"P": 0, "N": 1, "B": 2, "R": 3, "Q": 4, "K": 5}
PAD = 768


def features(board_field):
    """Feature indices from White's and Black's perspective for one FEN board field."""
    white, black = [], []
    rank = 7
    file = 0
    for ch in board_field:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            sq = rank * 8 + file
            is_white = ch.isupper()
            pt = PIECES[ch.upper()]
            white.append((0 if is_white else 384) + pt * 64 + sq)
            black.append((0 if not is_white else 384) + pt * 64 + (sq ^ 56))
            file += 1
    return white, black


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


def load_file(path, cache_dir, frozen=False):
    """Raw arrays for one file. With cache_dir, each parsed byte range is kept as an .npz and only
    lines appended since the last run are parsed (datagen files grow while it runs). frozen: use
    only what is cached, so runs compared with each other see the same data."""
    chunks, start = [], 0
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        stem = os.path.join(cache_dir, f"{os.path.basename(path)}.v{CACHE_VERSION}")
        while os.path.exists(f"{stem}.{start}.npz"):
            z = np.load(f"{stem}.{start}.npz")
            chunks.append({k: z[k] for k in FIELDS})
            start = int(z["end"])
    if frozen:  # files with nothing cached yet are left out
        return {k: np.concatenate([c[k] for c in chunks]) for k in FIELDS} if chunks else None
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    end = start + data.rfind(b"\n") + 1  # only complete lines
    if end > start:
        chunk, bad = parse_lines(data[:end - start].decode().splitlines())
        if bad:
            print(f"{path}: skipped {bad} malformed lines")
        if cache_dir:
            np.savez(f"{stem}.{start}.npz", end=end, **chunk)
        chunks.append(chunk)
    return {k: np.concatenate([c[k] for c in chunks]) for k in FIELDS} if chunks else None


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
        d = load_file(path, cache_dir, frozen)
        if d is None:
            continue
        game, future, gkey = per_file(d, game_base, future_plies)
        game_base = int(game[-1]) + 1
        small.append({"keys": d["keys"], "white": d["white"], "scores": d["scores"], "results": d["results"],
                      "game": game, "future": future, "gkey": gkey})
        used.append((path, len(game)))
        del d  # the features are read again below, file by file
    d = {k: np.concatenate([p.pop(k) for p in small]) for k in ("keys", "white", "scores", "results", "game", "future", "gkey")}
    _, first = np.unique(d.pop("keys"), return_index=True)
    first.sort()
    out = {k: d.pop(k)[first] for k in ("white", "scores", "results", "game", "future", "gkey")}

    # Every file is cached by now, so frozen reads return exactly what was just used. The kept
    # positions are stored compactly (see encode) as each file is read.
    occ, pcs = np.empty(len(first), dtype=np.uint64), np.empty((len(first), 16), dtype=np.uint8)
    offset = filled = 0
    for path, n in used:
        f = load_file(path, cache_dir, frozen=True)["feats"]
        if len(f) != n:
            raise RuntimeError(f"{path} changed while loading ({n} then {len(f)} positions)")
        lo, hi = np.searchsorted(first, (offset, offset + n))
        occ[filled:filled + hi - lo], pcs[filled:filled + hi - lo] = encode(f[first[lo:hi] - offset])
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

    _, first = np.unique(d["keys"], return_index=True)
    first.sort()
    out = {"feats": d["feats"][first], "white": d["white"][first], "scores": d["scores"][first],
           "results": d["results"][first], "game": d["game"][first], "future": d["future"][first],
           "gkey": d["gkey"][first]}
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


def teacher_predictions(path, inputs, n, dev, chunk=1 << 18):
    """Win probability, from the side to move's view, that an exported one-bucket network gives
    each of the n positions (`inputs` maps position indices to feature tensors, as in main). The
    weights are dequantised back to floats, so this matches the engine's eval up to rounding."""
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
    out = torch.empty(n, device=dev)
    with torch.no_grad():
        for s in range(0, n, chunk):
            idx = torch.arange(s, min(s + chunk, n), device=dev)
            stm, nstm = inputs(idx)[:2]
            a = torch.clamp(torch.nn.functional.embedding_bag(stm, w, mode="sum") + b, 0, 1) ** 2
            c = torch.clamp(torch.nn.functional.embedding_bag(nstm, w, mode="sum") + b, 0, 1) ** 2
            out[s:s + len(idx)] = torch.sigmoid(a @ ow[:h] + c @ ow[h:] + out_b / (QA * QB))
    return out


class Net(torch.nn.Module):
    def __init__(self, hidden, aux=False, policy=False, teacher=False):
        super().__init__()
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
        a = torch.clamp(self.ft(stm) + self.ft_bias, 0, 1) ** 2
        b = torch.clamp(self.ft(nstm) + self.ft_bias, 0, 1) ** 2
        x = torch.cat([a, b], dim=1)
        return (self.out(x).squeeze(1), self.aux(x).squeeze(1) if self.aux is not None else None,
                self.policy(x) if self.policy is not None else None,
                self.teach(x).squeeze(1) if self.teach is not None else None)

    def clip(self):
        # Keeps quantised values in range: QA * w and QB * w must fit int16, and the int32
        # output sum must not overflow (see src/nnue.cpp).
        with torch.no_grad():
            self.ft.weight.clamp_(-1.98, 1.98)
            self.out.weight.clamp_(-1.98, 1.98)


def export(net, path):
    hidden = net.ft_bias.shape[0]
    ft_w = torch.round(net.ft.weight[:PAD] * QA).to(torch.int16).cpu().numpy()
    ft_b = torch.round(net.ft_bias * QA).to(torch.int16).cpu().numpy()
    out_w = torch.round(net.out.weight[0] * QB).to(torch.int16).cpu().numpy()
    out_b = int(round(net.out.bias.item() * QA * QB))
    with open(path, "wb") as f:
        f.write(b"CSNN")
        f.write(struct.pack("<i", hidden))
        f.write(ft_w.astype("<i2").tobytes())
        f.write(ft_b.astype("<i2").tobytes())
        f.write(out_w.astype("<i2").tobytes())
        f.write(struct.pack("<i", out_b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="+")
    ap.add_argument("out")
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
    games = np.unique(d["game"])
    is_val = d["gkey"] % 50 == 0
    val, train = np.flatnonzero(is_val), np.flatnonzero(~is_val)
    moves_text = f"; {np.mean(d['pfrom'] >= 0):.0%} have the played move" if policy else ""
    print(f"{n} unique positions from {len(games)} games ({len(train)} train, {len(val)} validation), "
          f"loaded in {time.time() - t0:.0f}s{moves_text}", flush=True)

    dev = torch.device("cuda")
    # Positions are stored compactly (24 bytes, see encode) and decoded and flipped per batch on the
    # GPU. Above --gpu-data-gb they stay in host RAM and each batch is copied over.
    if "feats" in d:  # load_at_once keeps the feature lists
        d["occ"], d["pcs"] = encode(d.pop("feats"))
    on_gpu = d["occ"].nbytes + d["pcs"].nbytes <= args.gpu_data_gb * 1e9
    occ_t, pcs_t = torch.from_numpy(d["occ"].view(np.int64)), torch.from_numpy(d["pcs"])
    if on_gpu:
        occ_t, pcs_t = occ_t.to(dev), pcs_t.to(dev)
    white_t = torch.from_numpy(d["white"]).to(dev).bool()
    flip_t = torch.from_numpy(FLIP).to(dev)
    sign = white_t.float() * 2 - 1
    score_t = torch.from_numpy(d["scores"]).to(dev) * sign
    result_w = torch.from_numpy(d["results"]).to(dev)
    target = args.lam * torch.sigmoid(score_t / SCALE) + (1 - args.lam) * torch.where(white_t, result_w, 1 - result_w)
    future_w = torch.from_numpy(d["future"]).to(dev)
    future_t = torch.where(white_t, future_w, 1 - future_w)
    if policy:
        pfrom_t = torch.from_numpy(d["pfrom"].astype(np.int64)).to(dev)
        pto_t = torch.from_numpy(d["pto"].astype(np.int64)).to(dev)
    del score_t, result_w, future_w, d

    def inputs(idx):
        if on_gpu:
            w = decode(occ_t[idx], pcs_t[idx])
        else:
            i = idx.cpu()
            w = decode(occ_t[i].to(dev, non_blocking=True), pcs_t[i].to(dev, non_blocking=True))
        b = flip_t[w]
        wt = white_t[idx].unsqueeze(1)
        return torch.where(wt, w, b), torch.where(wt, b, w)

    train_t, val_t = torch.from_numpy(train).to(dev), torch.from_numpy(val).to(dev)
    teacher = args.teacher is not None
    if teacher:
        teacher_t = teacher_predictions(args.teacher, inputs, n, dev)
        tv = torch.mean((teacher_t[val_t] - target[val_t]) ** 2).item()
        print(f"teacher {os.path.basename(args.teacher)}: validation loss {tv:.5f} on this run's target", flush=True)

    net = Net(args.hidden, aux=args.aux_weight > 0, policy=args.policy_weight > 0, teacher=teacher).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    zero = torch.zeros((), device=dev)

    def losses(idx):
        main, aux, pol, teach = net(*inputs(idx))
        main_loss = torch.mean((torch.sigmoid(main) - target[idx]) ** 2)
        aux_loss = torch.mean((torch.sigmoid(aux) - future_t[idx]) ** 2) if aux is not None else zero
        pol_loss = zero
        if pol is not None:
            f, t = pfrom_t[idx], pto_t[idx]
            ok = f >= 0
            if ok.any():
                ce = torch.nn.functional.cross_entropy
                pol_loss = ce(pol[ok, :64], f[ok]) + ce(pol[ok, 64:], t[ok])
        teach_loss = torch.mean((torch.sigmoid(teach) - teacher_t[idx]) ** 2) if teach is not None else zero
        return main_loss, aux_loss, pol_loss, teach_loss

    for epoch in range(1, args.epochs + 1):
        net.train()
        order = train_t[torch.randperm(len(train_t), device=dev)]
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
