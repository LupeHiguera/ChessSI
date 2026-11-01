"""Binary training shards for `train.py --shards`, made from datagen text by shards.cpp.

    g++ -O2 -o shards nnue/shards.cpp
    ./shards <dir> <name> <data.txt> [max lines] [positions per shard]    # one data file -> <name>-NNNNN
    python shards.py finalize <dir> [--future-plies 4]   # per_file's targets for every shard in <dir>
    python shards.py dedup <dir> [--bits 36]              # keep masks: each position's first occurrence
    python shards.py check <dir> <name> <data.txt> <cache dir>   # shards equal train.py's cache of that file

A shard is one column file per field, little-endian, no header: .occ (u64) and .pcs (u8 x 16), the board
as train.encode stores it; .white (i8), .scores and .results (f32, White-relative), .ply (i16), .keys
(i64, train.position_key), from shards.cpp; .future (f32, White-relative win probability --future-plies
later in the game, as per_file computes it) and .isval (u8: the game is held out for validation, game
key % 50 == 0), from finalize; .keep (u8), from dedup. Shards hold whole games, so per_file on one shard
gives what it gives on the whole file. <dir>/<name>.manifest lists the shards of one data file in order.

Deduplication: train.load keeps the first occurrence of each position key over all the data, which
needs every key in memory at once (about 40 GB at 5 billion positions). dedup instead marks each key
in a bit array of 2^bits entries, shard by shard in manifest order. Positions repeated within a shard
are found exactly; across shards, a position whose bit some other key already set is dropped too. That
false-positive rate is about (positions so far) / 2^bits: it is printed at the end.
"""
import argparse
import glob
import os
import time

import numpy as np

import train

COLS = {"occ": (np.uint64, 1), "pcs": (np.uint8, 16), "white": (np.int8, 1), "scores": (np.float32, 1),
        "results": (np.float32, 1), "ply": (np.int16, 1), "keys": (np.int64, 1),
        "future": (np.float32, 1), "isval": (np.uint8, 1), "keep": (np.uint8, 1)}


def shard_list(d, name=None):
    """(path stem, positions) for each shard in d: manifests in name order, shards in manifest order."""
    out = []
    pattern = f"{name}.manifest" if name else "*.manifest"
    for m in sorted(glob.glob(os.path.join(d, pattern))):
        with open(m) as f:
            for line in f:
                shard, n = line.split()[:2]
                out.append((os.path.join(d, shard), int(n)))
    return out


def read(stem, col, n=None):
    dtype, width = COLS[col]
    a = np.fromfile(f"{stem}.{col}", dtype=dtype)
    if width > 1:
        a = a.reshape(-1, width)
    if n is not None and len(a) != n:
        raise RuntimeError(f"{stem}.{col}: {len(a)} rows, the manifest says {n}")
    return a


def write(stem, col, a):
    tmp = f"{stem}.{col}.tmp"
    np.ascontiguousarray(a, dtype=COLS[col][0]).tofile(tmp)
    os.replace(tmp, f"{stem}.{col}")


def finalize(d, future_plies, force=False):
    path = os.path.join(d, "FUTURE_PLIES")
    if os.path.exists(path):
        with open(path) as f:
            if int(f.read()) != future_plies:
                raise SystemExit(f"{d} was finalized with another --future-plies; use --force to redo all")
    with open(path, "w") as f:
        f.write(f"{future_plies}\n")
    t0, done = time.time(), 0
    for stem, n in shard_list(d):
        if not force and os.path.exists(f"{stem}.isval"):
            continue
        raw = {c: read(stem, c, n) for c in ("ply", "results", "scores", "keys")}
        _, future, gkey = train.per_file(raw, 0, future_plies)
        write(stem, "future", future)
        write(stem, "isval", gkey % 50 == 0)
        done += n
    print(f"finalized {done} positions in {time.time() - t0:.0f}s")


def dedup(d, bits):
    bitmap = np.zeros(1 << (bits - 3), dtype=np.uint8)
    mask = np.int64((1 << bits) - 1)
    total = kept = 0
    t0 = time.time()
    for stem, n in shard_list(d):
        keys = read(stem, "keys", n)
        first = np.unique(keys, return_index=True)[1]  # exact within the shard
        idx = keys[first] & mask
        byte, bit = idx >> 3, (idx & 7).astype(np.uint8)
        new = first[((bitmap[byte] >> bit) & 1) == 0]
        np.bitwise_or.at(bitmap, byte, np.left_shift(np.uint8(1), bit))
        keep = np.zeros(n, dtype=np.uint8)
        keep[new] = 1
        write(stem, "keep", keep)
        total += n
        kept += len(new)
    print(f"dedup: kept {kept} of {total} positions ({kept / max(total, 1):.2%}) in {time.time() - t0:.0f}s; "
          f"final false-positive rate about {kept / (1 << bits):.2%} (2^{bits} bits)")


def check(d, name, data_file, cache_dir):
    """The shards of one data file against train.load_file's cached arrays for it."""
    cached = train.load_file(data_file, cache_dir, frozen=True)
    if cached is None:
        raise SystemExit(f"{data_file} has nothing cached in {cache_dir}")
    items = shard_list(d, name)
    cols = {c: np.concatenate([read(s, c, n) for s, n in items]) for c in ("white", "scores", "results", "ply", "keys")}
    n = len(cached["white"])
    bad = []
    if len(cols["white"]) != n:
        bad.append(f"rows {len(cols['white'])} vs cache {n}")
    else:
        for c in ("white", "scores", "results", "ply", "keys"):
            if not np.array_equal(cols[c], cached[c]):
                bad.append(f"{c}: {int(np.count_nonzero(cols[c] != cached[c]))} rows differ")
        occ = np.concatenate([read(s, "occ", m) for s, m in items])
        pcs = np.concatenate([read(s, "pcs", m) for s, m in items])
        for s in range(0, n, 1 << 22):
            o, p = train.encode(cached["feats"][s:s + (1 << 22)])
            if not (np.array_equal(o, occ[s:s + len(o)]) and np.array_equal(p, pcs[s:s + len(o)])):
                bad.append(f"boards differ in rows {s}-{s + len(o)}")
                break
    print(f"{name}: {n} positions, {len(items)} shards: " + ("IDENTICAL" if not bad else "; ".join(bad)), flush=True)
    return not bad


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("dir")
    f.add_argument("--future-plies", type=int, default=4)
    f.add_argument("--force", action="store_true")
    u = sub.add_parser("dedup")
    u.add_argument("dir")
    u.add_argument("--bits", type=int, default=36)
    c = sub.add_parser("check")
    c.add_argument("dir")
    c.add_argument("name")
    c.add_argument("data")
    c.add_argument("cache_dir")
    args = ap.parse_args()
    if args.cmd == "finalize":
        finalize(args.dir, args.future_plies, args.force)
    elif args.cmd == "dedup":
        dedup(args.dir, args.bits)
    else:
        raise SystemExit(0 if check(args.dir, args.name, args.data, args.cache_dir) else 1)


if __name__ == "__main__":
    main()
