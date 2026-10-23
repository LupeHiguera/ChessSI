"""Train ChessSI's NNUE on positions in the datagen text format.

    python train.py <data.txt>... <out.nnue> [--hidden 128] [--epochs 20] [--lambda 0.75] [--cache-dir dir]
                    [--aux-weight 0] [--future-plies 8]

Network: (768 -> H) x 2 perspectives -> SCReLU -> 1, the usual first NNUE. Input features are
(piece colour relative to the perspective, piece type, square), with squares mirrored vertically for
Black's perspective. The output, times SCALE, is centipawns for the side to move.

Loss: mean squared error between sigmoid(output) and a blend of sigmoid(score / SCALE) and the game
result, both from the side to move: target = lambda * score + (1 - lambda) * result. With
--aux-weight, a second head (training only, not exported) also learns the win probability
--future-plies later in the game.

Export (little-endian, see src/nnue.cpp): magic "CSNN", hidden size (int32), feature weights
int16[768][H] and biases int16[H] scaled by QA, output weights int16[2H] scaled by QB, output bias
int32 scaled by QA * QB.
"""
import argparse
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


FIELDS = ("feats", "white", "scores", "results", "keys", "ply")


def parse_lines(lines):
    """Raw arrays (no deduplication) for datagen text lines; returns them and the malformed count."""
    feats, white, scores, results, keys, ply = array("h"), array("b"), array("f"), array("f"), array("q"), array("h")
    bad = 0
    for line in lines:
        try:
            fen, score, result = (x.strip() for x in line.split("|"))
            parts = fen.split()
            w = white_features(parts[0])
            cp, res = int(score), float(result)
            p = 2 * (int(parts[5]) - 1) + (parts[1] == "b")
        except (ValueError, KeyError, IndexError):
            bad += 1  # e.g. a line cut short by stopping datagen
            continue
        keys.append(hash(" ".join(parts[:4])) & 0x7FFFFFFFFFFFFFFF)  # ignore move counters
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
        stem = os.path.join(cache_dir, os.path.basename(path))
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


def load(paths, cache_dir=None, future_plies=8, frozen=False):
    """Unique positions from datagen text files: White-perspective features int16[n, 32] padded
    with PAD, side to move (1 for White), White-relative score and result, a game number, and the
    White-relative win probability `future_plies` later in the same game (the game result if it
    ends first). Games are contiguous in each file; a new one starts where the ply goes back or
    the result changes."""
    parts, game_base = [], 0
    for path in paths:
        d = load_file(path, cache_dir, frozen)
        if d is None:
            continue
        n = len(d["ply"])
        ply = d["ply"].astype(np.int64)
        new_game = np.ones(n, dtype=bool)
        new_game[1:] = (ply[1:] <= ply[:-1]) | (d["results"][1:] != d["results"][:-1])
        d["game"] = game_base + np.cumsum(new_game) - 1
        game_base = int(d["game"][-1]) + 1
        parts.append(d)
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

    # Win probability future_plies later: the first recorded position at least that far ahead.
    order_key = d["game"] * 4096 + d["ply"].astype(np.int64)
    j = np.searchsorted(order_key, order_key + future_plies)
    jc = np.minimum(j, len(j) - 1)
    valid = (j < len(j)) & (d["game"][jc] == d["game"])
    future = np.where(valid, 1 / (1 + np.exp(-d["scores"][jc] / SCALE)), d["results"]).astype(np.float32)

    _, first = np.unique(d["keys"], return_index=True)
    first.sort()
    return {"feats": d["feats"][first], "white": d["white"][first], "scores": d["scores"][first],
            "results": d["results"][first], "game": d["game"][first], "future": future[first]}


class Net(torch.nn.Module):
    def __init__(self, hidden, aux=False):
        super().__init__()
        self.ft = torch.nn.EmbeddingBag(PAD + 1, hidden, mode="sum", padding_idx=PAD)
        self.ft_bias = torch.nn.Parameter(torch.zeros(hidden))
        self.out = torch.nn.Linear(2 * hidden, 1)
        # Auxiliary head, used only in training and not exported: predicts the outcome a few plies
        # later from the same hidden layer, as extra signal for the shared first layer.
        self.aux = torch.nn.Linear(2 * hidden, 1) if aux else None
        with torch.no_grad():
            self.ft.weight.uniform_(-0.05, 0.05)
            self.ft.weight[PAD].zero_()

    def forward(self, stm, nstm):
        a = torch.clamp(self.ft(stm) + self.ft_bias, 0, 1) ** 2
        b = torch.clamp(self.ft(nstm) + self.ft_bias, 0, 1) ** 2
        x = torch.cat([a, b], dim=1)
        return self.out(x).squeeze(1), (self.aux(x).squeeze(1) if self.aux is not None else None)

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
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    t0 = time.time()
    d = load(args.data, args.cache_dir, args.future_plies, args.frozen)
    n = len(d["scores"])
    # Validation holds whole games, so no game has positions on both sides of the split.
    games = np.unique(d["game"])
    rng = np.random.default_rng(args.seed)
    val_games = rng.choice(games, size=max(len(games) // 50, 1), replace=False)
    is_val = np.isin(d["game"], val_games)
    val, train = np.flatnonzero(is_val), np.flatnonzero(~is_val)
    print(f"{n} unique positions from {len(games)} games ({len(train)} train, {len(val)} validation), "
          f"loaded in {time.time() - t0:.0f}s", flush=True)

    dev = torch.device("cuda")
    # Features are int16 (64 bytes a position), widened and flipped per batch on the GPU. Above
    # --gpu-data-gb they stay in host RAM and each batch is copied over.
    on_gpu = d["feats"].nbytes <= args.gpu_data_gb * 1e9
    feats_t = torch.from_numpy(d["feats"]).to(dev) if on_gpu else torch.from_numpy(d["feats"])
    white_t = torch.from_numpy(d["white"]).to(dev).bool()
    flip_t = torch.from_numpy(FLIP).to(dev)
    sign = white_t.float() * 2 - 1
    score_t = torch.from_numpy(d["scores"]).to(dev) * sign
    result_w = torch.from_numpy(d["results"]).to(dev)
    target = args.lam * torch.sigmoid(score_t / SCALE) + (1 - args.lam) * torch.where(white_t, result_w, 1 - result_w)
    future_w = torch.from_numpy(d["future"]).to(dev)
    future_t = torch.where(white_t, future_w, 1 - future_w)
    del score_t, result_w, future_w, d

    def inputs(idx):
        w = (feats_t[idx] if on_gpu else feats_t[idx.cpu()].to(dev, non_blocking=True)).long()
        b = flip_t[w]
        wt = white_t[idx].unsqueeze(1)
        return torch.where(wt, w, b), torch.where(wt, b, w)

    net = Net(args.hidden, aux=args.aux_weight > 0).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    train_t, val_t = torch.from_numpy(train).to(dev), torch.from_numpy(val).to(dev)

    def losses(idx):
        main, aux = net(*inputs(idx))
        main_loss = torch.mean((torch.sigmoid(main) - target[idx]) ** 2)
        aux_loss = torch.mean((torch.sigmoid(aux) - future_t[idx]) ** 2) if aux is not None else torch.zeros((), device=dev)
        return main_loss, aux_loss

    for epoch in range(1, args.epochs + 1):
        net.train()
        order = train_t[torch.randperm(len(train_t), device=dev)]
        total = 0.0
        for i in range(0, len(order), args.batch):
            idx = order[i:i + args.batch]
            opt.zero_grad()
            main_loss, aux_loss = losses(idx)
            (main_loss + args.aux_weight * aux_loss).backward()
            opt.step()
            net.clip()
            total += main_loss.item() * len(idx)
        sched.step()
        net.eval()
        v = va = 0.0
        with torch.no_grad():
            for i in range(0, len(val_t), 65536):
                idx = val_t[i:i + 65536]
                main_loss, aux_loss = losses(idx)
                v += main_loss.item() * len(idx)
                va += aux_loss.item() * len(idx)
        aux_text = f" aux {va / len(val):.5f}" if args.aux_weight > 0 else ""
        print(f"epoch {epoch:3d} train {total / len(train):.5f} val {v / len(val):.5f}{aux_text}  "
              f"({time.time() - t0:.0f}s)", flush=True)

    export(net.cpu(), args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
