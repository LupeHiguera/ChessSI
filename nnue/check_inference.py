"""Check that ChessSI's C++ inference matches the exported network.

    python check_inference.py <net.nnue> <chesssi binary> <data.txt> [positions=200]

Recomputes each position's eval from the quantised file in exact integer arithmetic (the same
steps as src/nnue.cpp, including CSKB king buckets) and compares it with the engine's "eval" command
after loading the network with "setoption name EvalFile". Any difference is a bug in one of the two.
"""
import subprocess
import sys

from arch import evaluate


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
    data = open(net_path, "rb").read()
    script = f"setoption name EvalFile value {net_path}\n"
    script += "".join(f"position fen {fen}\neval\n" for fen in fens) + "quit\n"
    out = subprocess.run([engine], input=script, capture_output=True, text=True).stdout.splitlines()
    loaded = [l for l in out if "network" in l]
    evals = [int(l.split()[1]) for l in out if l.startswith("eval ")]
    print(loaded[0] if loaded else "no load message")
    if len(evals) != len(fens):
        print(f"expected {len(fens)} evals, parsed {len(evals)}; engine output starts: {out[:5]}")
        return 1
    bad = [(fen, e, evaluate(data, fen)) for fen, e in zip(fens, evals) if e != evaluate(data, fen)]
    print(f"{len(fens) - len(bad)}/{len(fens)} positions match")
    for fen, e, r in bad[:5]:
        print(f"  {fen}: engine {e}, reference {r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
