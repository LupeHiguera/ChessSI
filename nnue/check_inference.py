"""Check that ChessSI's C++ inference matches the exported network.

    python check_inference.py <net.nnue> <chesssi binary> <data.txt> [positions=200]

Recomputes each position's eval from the network file's integers with train.py's quantized_eval, the
evaluation behind the trainer's "quantized" validation loss (the same integer steps as src/nnue.cpp, for
either tail), and compares it with the engine's "eval" command after loading the network with
"setoption name EvalFile". Any difference is a bug in one of the two.
"""
import subprocess
import sys

import torch

from train import PAD, features, quantized_eval, read_net


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
    q, mirror, tail = read_net(net_path)
    q = {k: torch.from_numpy(v.astype("int64")) for k, v in q.items()}
    stm, nstm = [], []
    for fen in fens:
        w, b = features(fen.split()[0], mirror)
        us, them = (w, b) if fen.split()[1] == "w" else (b, w)
        stm.append(us + [PAD] * (32 - len(us)))
        nstm.append(them + [PAD] * (32 - len(them)))
    reference = quantized_eval(q, torch.tensor(stm), torch.tensor(nstm)).long().tolist()

    script = f"setoption name EvalFile value {net_path}\n"
    script += "".join(f"position fen {fen}\neval\n" for fen in fens) + "quit\n"
    out = subprocess.run([engine], input=script, capture_output=True, text=True).stdout.splitlines()
    loaded = [l for l in out if "network" in l]
    evals = [int(l.split()[1]) for l in out if l.startswith("eval ")]
    print(f"{loaded[0] if loaded else 'no load message'} ({tail}{', mirrored' if mirror else ''})")
    if len(evals) != len(fens):
        print(f"expected {len(fens)} evals, parsed {len(evals)}; engine output starts: {out[:5]}")
        return 1
    bad = [(fen, e, r) for fen, e, r in zip(fens, evals, reference) if e != r]
    print(f"{len(fens) - len(bad)}/{len(fens)} positions match")
    for fen, e, r in bad[:5]:
        print(f"  {fen}: engine {e}, reference {r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
