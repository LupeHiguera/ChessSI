"""Train ChessSI's NNUE on positions in the datagen text format.

    python train.py <data.txt> <out.nnue> [--hidden 128] [--epochs 20] [--lambda 0.75] [--gpu 1]

Network: (768 -> H) x 2 perspectives -> SCReLU -> 1, the usual first NNUE. Input features are
(piece colour relative to the perspective, piece type, square), with squares mirrored vertically for
Black's perspective. The output, times SCALE, is centipawns for the side to move.

Loss: mean squared error between sigmoid(output) and a blend of sigmoid(score / SCALE) and the game
result, both from the side to move: target = lambda * score + (1 - lambda) * result.

Export (little-endian, see src/nnue.cpp): magic "CSNN", hidden size (int32), feature weights
int16[768][H] and biases int16[H] scaled by QA, output weights int16[2H] scaled by QB, output bias
int32 scaled by QA * QB.
"""
import argparse
import math
import random
import struct
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


def load(path, max_positions=None):
    stm_f, nstm_f, scores, results = [], [], [], []
    seen = set()
    with open(path) as f:
        for line in f:
            fen, score, result = (x.strip() for x in line.split("|"))
            key = fen.rsplit(" ", 2)[0]  # ignore move counters
            if key in seen:
                continue
            seen.add(key)
            parts = fen.split()
            w, b = features(parts[0])
            cp, res = int(score), float(result)
            if parts[1] == "b":
                w, b, cp, res = b, w, -cp, 1.0 - res
            stm_f.append(w + [PAD] * (32 - len(w)))
            nstm_f.append(b + [PAD] * (32 - len(b)))
            scores.append(cp)
            results.append(res)
            if max_positions and len(scores) >= max_positions:
                break
    return (np.array(stm_f, dtype=np.int16), np.array(nstm_f, dtype=np.int16),
            np.array(scores, dtype=np.float32), np.array(results, dtype=np.float32))


class Net(torch.nn.Module):
    def __init__(self, hidden):
        super().__init__()
        self.ft = torch.nn.EmbeddingBag(PAD + 1, hidden, mode="sum", padding_idx=PAD)
        self.ft_bias = torch.nn.Parameter(torch.zeros(hidden))
        self.out = torch.nn.Linear(2 * hidden, 1)
        with torch.no_grad():
            self.ft.weight.uniform_(-0.05, 0.05)
            self.ft.weight[PAD].zero_()

    def forward(self, stm, nstm):
        a = torch.clamp(self.ft(stm) + self.ft_bias, 0, 1) ** 2
        b = torch.clamp(self.ft(nstm) + self.ft_bias, 0, 1) ** 2
        return self.out(torch.cat([a, b], dim=1)).squeeze(1)

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
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=16384)
    ap.add_argument("--lr", type=float, default=0.001)
    ap.add_argument("--lambda", dest="lam", type=float, default=0.75)
    ap.add_argument("--max-positions", type=int, default=None)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    t0 = time.time()
    stm, nstm, score, result = load(args.data, args.max_positions)
    n = len(score)
    perm = np.random.default_rng(args.seed).permutation(n)
    val = perm[: max(n // 50, 1)]
    train = perm[len(val):]
    print(f"{n} unique positions ({len(train)} train, {len(val)} validation), loaded in {time.time() - t0:.0f}s")

    dev = torch.device("cuda")
    to = lambda a, dt: torch.from_numpy(a).to(dev, dt)
    stm_t, nstm_t = to(stm, torch.long), to(nstm, torch.long)
    target = args.lam * torch.sigmoid(to(score, torch.float32) / SCALE) + (1 - args.lam) * to(result, torch.float32)

    net = Net(args.hidden).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    train_t, val_t = torch.from_numpy(train).to(dev), torch.from_numpy(val).to(dev)

    def loss_on(idx):
        return torch.mean((torch.sigmoid(net(stm_t[idx], nstm_t[idx])) - target[idx]) ** 2)

    for epoch in range(1, args.epochs + 1):
        net.train()
        order = train_t[torch.randperm(len(train_t), device=dev)]
        total = 0.0
        for i in range(0, len(order), args.batch):
            idx = order[i:i + args.batch]
            opt.zero_grad()
            loss = loss_on(idx)
            loss.backward()
            opt.step()
            net.clip()
            total += loss.item() * len(idx)
        sched.step()
        net.eval()
        with torch.no_grad():
            v = sum(loss_on(val_t[i:i + 65536]).item() * len(val_t[i:i + 65536]) for i in range(0, len(val_t), 65536))
        print(f"epoch {epoch:3d} train {total / len(train):.5f} val {v / len(val):.5f}  ({time.time() - t0:.0f}s)", flush=True)

    export(net.cpu(), args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
