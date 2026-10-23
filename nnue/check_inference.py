"""Check that ChessSI's C++ inference matches the exported network.

    python check_inference.py <net.nnue> <chesssi binary> <data.txt> [positions=200]

Recomputes each position's eval from the quantised file in exact integer arithmetic (the same
steps as src/nnue.cpp) and compares it with the engine's "eval" command after loading the network
with "setoption name EvalFile". Any difference is a bug in one of the two.
"""
import struct
import subprocess
import sys

import numpy as np

from train import QA, QB, SCALE, features


def load(path):
    with open(path, "rb") as f:
        magic = f.read(4)
        assert magic in (b"CSNN", b"CSNB")
        (h,) = struct.unpack("<i", f.read(4))
        (n,) = struct.unpack("<i", f.read(4)) if magic == b"CSNB" else (1,)
        ft_w = np.frombuffer(f.read(768 * h * 2), dtype="<i2").reshape(768, h).astype(np.int64)
        ft_b = np.frombuffer(f.read(h * 2), dtype="<i2").astype(np.int64)
        out_w = np.frombuffer(f.read(n * 2 * h * 2), dtype="<i2").reshape(n, 2 * h).astype(np.int64)
        out_b = np.frombuffer(f.read(n * 4), dtype="<i4").astype(np.int64)
    return ft_w, ft_b, out_w, out_b


def tdiv(a, b):
    """Integer division truncating toward zero, as in C++."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def reference(net, fen):
    ft_w, ft_b, out_w, out_b = net
    parts = fen.split()
    w, b = features(parts[0])
    us, them = (w, b) if parts[1] == "w" else (b, w)
    acc = np.concatenate([ft_b + ft_w[us].sum(0), ft_b + ft_w[them].sum(0)])
    x = np.clip(acc, 0, QA)
    n = len(out_b)
    bucket = min((len(w) - 2) // ((32 + n - 1) // n), n - 1)
    total = int((x * x * out_w[bucket]).sum())
    total = tdiv(total, QA) + int(out_b[bucket])
    return tdiv(total * SCALE, QA * QB)


def main():
    net_path, engine, data = sys.argv[1:4]
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    fens = []
    with open(data) as f:
        for i, line in enumerate(f):
            if i % 997 == 0:
                fens.append(line.split("|")[0].strip())
            if len(fens) >= count:
                break
    net = load(net_path)
    script = f"setoption name EvalFile value {net_path}\n"
    script += "".join(f"position fen {fen}\neval\n" for fen in fens) + "quit\n"
    out = subprocess.run([engine], input=script, capture_output=True, text=True).stdout.splitlines()
    loaded = [l for l in out if "network" in l]
    evals = [int(l.split()[1]) for l in out if l.startswith("eval ")]
    print(loaded[0] if loaded else "no load message")
    if len(evals) != len(fens):
        print(f"expected {len(fens)} evals, parsed {len(evals)}; engine output starts: {out[:5]}")
        return 1
    bad = [(fen, e, reference(net, fen)) for fen, e in zip(fens, evals) if e != reference(net, fen)]
    print(f"{len(fens) - len(bad)}/{len(fens)} positions match")
    for fen, e, r in bad[:5]:
        print(f"  {fen}: engine {e}, reference {r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
