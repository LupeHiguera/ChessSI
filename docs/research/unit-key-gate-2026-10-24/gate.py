"""Offline gate for correction history keyed by the network's hidden units (cloud research proposal):
does the on/off pattern of K accumulator units explain more of the static eval's error than a random
key of the same width, and how does it compare with the pawn key correction history uses now?

Target: the stm-relative eval error, search score minus static eval, from generation-6 datagen lines
(net9's search and net9's static eval). Keys index 2 x 2^K buckets (side to move x key), like the
correction tables. Out of sample: group means (shrunk toward 0) from one half, R^2 on the other half,
splitting by whole games and by alternate positions within each game.

usage: python unit-key-gate.py <net9.nnue> <dg6 files...>"""
import sys, hashlib
import numpy as np

sys.path.insert(0, "/mnt/c/Users/Lupe/CLionProjects/ChessSI/nnue")
from check_inference import load
from train import features

K = 14          # key width: 2^14 = 16,384 buckets per side, the correction table's size
PER_FILE = 100_000
SHRINK = 20.0   # group mean * n / (n + SHRINK)
rng = np.random.default_rng(1)

ft_w, ft_b, _, _ = load(sys.argv[1])
H = ft_b.shape[0]

fens, err, stm, game, ply, evs = [], [], [], [], [], []
g = 0
for path in sys.argv[2:]:
    prev_ply, prev_res = -1, None
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= PER_FILE:
                break
            parts = line.split("|")
            if len(parts) < 4:
                continue
            fen, score, res, ev = parts[0].strip(), int(parts[1]), parts[2].strip(), int(parts[3])
            fp = fen.split()
            p = 2 * (int(fp[5]) - 1) + (fp[1] == "b")
            if p <= prev_ply or res != prev_res:
                g += 1
            prev_ply, prev_res = p, res
            sign = 1 if fp[1] == "w" else -1
            fens.append(fen); err.append(np.clip((score - ev) * sign, -1000, 1000)); stm.append(fp[1] == "w")
            game.append(g); ply.append(p); evs.append(ev * sign)
    g += 1
err = np.array(err, dtype=np.float64); stm = np.array(stm); game = np.array(game); ply = np.array(ply); evs = np.array(evs)
n = len(err)
print(f"{n} positions from {len(set(game))} games; eval error sd {err.std():.1f} cp, mean {err.mean():.1f}")

# Side-to-move feature lists, padded to 32 with an all-zero row.
idx = np.full((n, 32), 768, dtype=np.int64)
pawns = np.zeros((n, 2), dtype=np.uint64)
for i, fen in enumerate(fens):
    w, b = features(fen.split()[0])
    us = w if stm[i] else b
    idx[i, :len(us)] = us
    board, sq = fen.split()[0], 56
    for ch in board:
        if ch == "/":
            sq -= 16
        elif ch.isdigit():
            sq += int(ch)
        else:
            if ch == "P":
                pawns[i, 0] |= np.uint64(1) << np.uint64(sq)
            elif ch == "p":
                pawns[i, 1] |= np.uint64(1) << np.uint64(sq)
            sq += 1
w_pad = np.vstack([ft_w, np.zeros((1, H), dtype=ft_w.dtype)])

def unit_signs(units):
    out = np.zeros((n, len(units)), dtype=bool)
    sub = w_pad[:, units]
    for s in range(0, n, 50_000):
        out[s:s + 50_000] = (ft_b[units] + sub[idx[s:s + 50_000]].sum(1)) > 0
    return out

# Which units are on about half the time (the most even splits), from a sample.
sample = rng.choice(n, 20_000, replace=False)
acc = ft_b + w_pad[idx[sample]].sum(1)
p_on = (acc > 0).mean(0)
balanced = np.argsort(np.abs(p_on - 0.5))[:K]
print(f"units on 50% +/- {np.abs(p_on[balanced] - 0.5).max():.2f} of the time: {sorted(balanced.tolist())}; "
      f"median unit on {np.median(p_on):.2f} of the time")

def bits_to_key(bits):
    return (bits.astype(np.int64) << np.arange(bits.shape[1])).sum(1)

def mix(x):
    x = x.astype(np.uint64)
    x ^= x >> np.uint64(31); x *= np.uint64(0xBF58476D1CE4E5B9); x ^= x >> np.uint64(29)
    return (x >> np.uint64(64 - K)).astype(np.int64)

keys = {
    "random": np.array([int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little") >> (64 - K) for f in fens]),
    "pawns": mix(pawns[:, 0] * np.uint64(0x9E3779B97F4A7C15) ^ pawns[:, 1] * np.uint64(0xC2B2AE3D27D4EB4F)),
    "eval value": np.minimum(np.searchsorted(np.quantile(evs, np.linspace(0, 1, (1 << K) + 1)[1:-1]), evs), (1 << K) - 1),
    "material": mix(np.array([sum(hash_piece * fen.split()[0].count(ch) for hash_piece, ch in zip(
        (1, 9, 81, 729, 6561, 59049, 531441, 4782969, 43046721, 387420489), "PNBRQpnbrq")) for fen in fens], dtype=np.uint64)
        * np.uint64(0x9E3779B97F4A7C15)),
    "units 0-13": bits_to_key(unit_signs(np.arange(K))),
    "units, balanced": bits_to_key(unit_signs(balanced)),
}

def predict(key, train, test):
    k = key * 2 + stm
    sums = np.bincount(k[train], weights=err[train], minlength=2 << K)
    cnt = np.bincount(k[train], minlength=2 << K)
    mean = sums / np.maximum(cnt, 1) * (cnt / (cnt + SHRINK))
    return mean[k[test]], (cnt[k[test]] > 0).mean()

import os
near = np.abs(evs) < int(os.environ.get("NEAR", "100000"))  # NEAR=200: only balanced positions
print(f"positions kept: {near.mean():.0%} (|static eval| < {os.environ.get('NEAR', 'any')} cp); error sd there {err[near].std():.1f} cp")
splits = {"by game": (game * 2654435761 % 1000) < 500, "alternate pairs of plies": (ply // 2) % 2 == 0}
for split, in_train in splits.items():
    train, test = np.flatnonzero(in_train & near), np.flatnonzero(~in_train & near)
    sst = ((err[test] - err[test].mean()) ** 2).sum()
    print(f"--- split {split}: {len(train)} train, {len(test)} test")
    preds = {}
    for name, key in keys.items():
        pr, seen = predict(key, train, test)
        preds[name] = pr
        print(f"  {name:16s} R^2 {1 - ((err[test] - pr) ** 2).sum() / sst:+.4f}   (test buckets seen in training: {seen:.0%})")
    for name in ("units, balanced", "eval value"):
        both = (preds["pawns"] + preds[name]) / 2
        print(f"  pawns + {name:9s} R^2 {1 - ((err[test] - both) ** 2).sum() / sst:+.4f}   (average of the two corrections)")
