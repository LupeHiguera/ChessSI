"""King-bucket checks for net13 (CSKB). No torch and no GPU.

    python nnue/test_buckets.py [./chesssi]

Compares nnue/arch.py with the engine: the bucket id, a CSKB file whose rows repeat
net12 (step 0), and a net whose rows differ by bucket so a missed king refresh shows up.
"""

import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arch import QA, QB, evaluate, king_bucket, pack_cskb, parse_net, requant_matches  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET12 = os.path.join(ROOT, "nets", "net12-h256.nnue")

# The same squares as the static_asserts in src/nnue.h.
ASSERTS = [
    (4, 8, 0), (7, 8, 3), (0, 8, 3), (3, 8, 0), (28, 8, 0), (36, 8, 4),
    (60, 8, 4), (56, 8, 7), (63, 8, 7),
    (4, 16, 0), (12, 16, 0), (20, 16, 4), (36, 16, 8), (63, 16, 15),
    (56, 16, 15), (0, 16, 3),
]


def run_engine(engine, script):
    proc = subprocess.run([engine], input=script, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"engine exited {proc.returncode}\n{proc.stderr}\n{proc.stdout[:500]}")
    return proc.stdout


def evals_of(engine, net_path, commands):
    """commands are UCI lines (position / d / eval). Returns eval ints and Fen lines, in order."""
    script = f"setoption name EvalFile value {net_path}\n" + "\n".join(commands) + "\nquit\n"
    out = run_engine(engine, script)
    if "could not load network" in out:
        raise SystemExit(f"engine rejected {net_path}\n{out}")
    if "loaded network" not in out:
        raise SystemExit(f"no load message for {net_path}\n{out}")
    ev, fens = [], []
    for line in out.splitlines():
        if line.startswith("eval "):
            ev.append(int(line.split()[1]))
        elif line.startswith("Fen: "):
            fens.append(line[len("Fen: "):])
    return ev, fens


def two_kings(wk, bk, stm):
    cells = ["."] * 64
    cells[wk] = "K"
    cells[bk] = "k"
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for file in range(8):
            ch = cells[rank * 8 + file]
            if ch == ".":
                empty += 1
            else:
                row += (str(empty) if empty else "") + ch
                empty = 0
        rows.append(row + (str(empty) if empty else ""))
    return "/".join(rows) + f" {stm} - - 0 1"


def distinguished(buckets):
    """Unit 0 of every row is 50 + 5 * bucket. Only the side-to-move output uses it."""
    hidden = 32
    ft = np.zeros((buckets, 768, hidden), np.int16)
    for b in range(buckets):
        ft[b, :, 0] = np.int16(50 + 5 * b)
    out = np.zeros(2 * hidden, np.int16)
    out[0] = 64
    return pack_cskb(hidden, buckets, ft, np.zeros(hidden, np.int16), out, 0)


def repeat_net12(buckets):
    base = parse_net(open(NET12, "rb").read())
    ft = np.broadcast_to(base["ft_w"], (buckets, 768, base["hidden"])).copy()
    return pack_cskb(base["hidden"], buckets, ft, base["ft_b"], base["out_w"], base["out_b"])


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "chesssi")
    failed = 0

    def check(ok, msg):
        nonlocal failed
        print(("ok  " if ok else "FAIL") + " " + msg)
        if not ok:
            failed += 1

    for sq, n, expect in ASSERTS:
        check(king_bucket(sq, n) == expect, f"king_bucket({sq}, {n}) == {expect}")
    # e1 and the mirror of d1 share a bucket; e5 does not, for both layouts.
    check(king_bucket(4, 8) == king_bucket(3, 8) and king_bucket(4, 8) != king_bucket(36, 8),
          "K8 groups e1 with d1 and not with e5")
    check(king_bucket(4, 16) == king_bucket(12, 16) and king_bucket(4, 16) != king_bucket(20, 16),
          "K16 groups e1 with e2 and not with e3")

    net12 = parse_net(open(NET12, "rb").read())
    check(net12["magic"] == b"CSNN" and net12["buckets"] == 1, "net12 parses as CSNN")
    check(requant_matches(net12["ft_w"], QA) and requant_matches(net12["ft_b"], QA)
          and requant_matches(net12["out_w"], QB), "net12 int16 weights round-trip at QA/QB")
    try:
        parse_net(b"CSKB" + open(NET12, "rb").read()[4:])
        check(False, "a CSNN body with a CSKB magic must not parse")
    except ValueError:
        check(True, "a CSNN body with a CSKB magic does not parse")

    lines = [
        "e2e4",
        "e2e4 e7e5",
        "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6",
        "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 e1g1",
        "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 e1g1 e8g8",
        "e2e4 d7d5 e4d5",
        "e2e4 a7a5 e4e5 d7d5 e5d6",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path12 = os.path.join(tmp, "net12.nnue")
        open(path12, "wb").write(open(NET12, "rb").read())
        move_cmds = ["position startpos", "d", "eval"]
        for moves in lines:
            move_cmds += [f"position startpos moves {moves}", "d", "eval"]
        ev12, fens = evals_of(engine, path12, move_cmds)
        check(len(ev12) == len(fens) == len(lines) + 1, f"net12 move list returned {len(ev12)} evals")
        for fen, ev in zip(fens, ev12):
            got = evaluate(open(path12, "rb").read(), fen)
            if got != ev:
                check(False, f"net12 python {got} engine {ev} on {fen}")
                break
        else:
            check(True, f"net12 python matches engine on {len(fens)} positions")

        for buckets in (8, 16):
            path = os.path.join(tmp, f"repeat-k{buckets}.nnue")
            open(path, "wb").write(repeat_net12(buckets))
            ev, fens_b = evals_of(engine, path, move_cmds)
            check(ev == ev12 and fens_b == fens, f"CSKB x{buckets} repeating net12 matches net12 on the move list")
            raw = open(path, "rb").read()
            mismatch = [fen for fen, e in zip(fens, ev) if evaluate(raw, fen) != e]
            check(not mismatch, f"CSKB x{buckets} python matches engine" + (f" ({mismatch[0]})" if mismatch else ""))

            dist = os.path.join(tmp, f"dist-k{buckets}.nnue")
            blob = distinguished(buckets)
            open(dist, "wb").write(blob)
            sweep = []
            for stm in ("w", "b"):
                for sq in range(64):
                    other = 0 if sq != 0 else 7
                    sweep.append(two_kings(sq if stm == "w" else other, other if stm == "w" else sq, stm))
            cmds = [c for fen in sweep for c in (f"position fen {fen}", "eval")]
            evs, _ = evals_of(engine, dist, cmds)
            bad = []
            by_bucket = {}
            for fen, ev in zip(sweep, evs):
                ref = evaluate(blob, fen)
                if ref != ev:
                    bad.append((fen, ev, ref))
                sq = king_sq_from_fen(fen, fen.split()[1])
                by_bucket.setdefault(king_bucket(sq, buckets), set()).add(ev)
            check(not bad, f"K{buckets} king sweep python matches engine"
                  + (f" ({bad[0]})" if bad else f" ({len(sweep)} positions)"))
            values = {next(iter(v)) for v in by_bucket.values()}
            one_each = len(by_bucket) == buckets and all(len(v) == 1 for v in by_bucket.values())
            check(one_each and len(values) == buckets,
                  f"K{buckets} distinct buckets give distinct evals ({len(values)} values)")

            ev_m, fens_m = evals_of(engine, dist, move_cmds)
            fen_cmds = [c for fen in fens_m for c in (f"position fen {fen}", "eval")]
            ev_f, _ = evals_of(engine, dist, fen_cmds)
            py = [evaluate(blob, fen) for fen in fens_m]
            check(ev_m == ev_f == py, f"K{buckets} move path matches a fresh fen and python")

        bad_buckets = os.path.join(tmp, "bad-buckets.nnue")
        # magic, hidden, buckets=4. 4 is not 8 or 16, so the loader rejects it.
        open(bad_buckets, "wb").write(b"CSKB" + (32).to_bytes(4, "little") + (4).to_bytes(4, "little"))
        rejected = run_engine(engine, f"setoption name EvalFile value {bad_buckets}\nquit\n")
        check("could not load network" in rejected, "buckets other than 8 or 16 are rejected")
        renamed = os.path.join(tmp, "renamed.nnue")
        open(renamed, "wb").write(b"CSKB" + open(NET12, "rb").read()[4:])
        rejected = run_engine(engine, f"setoption name EvalFile value {renamed}\nquit\n")
        check("could not load network" in rejected, "CSNN bytes under a CSKB magic are rejected")

    if failed:
        print(f"{failed} failed")
        return 1
    print("0 failed")
    return 0


def king_sq_from_fen(fen, stm):
    board = fen.split()[0]
    rank, file = 7, 0
    want = "K" if stm == "w" else "k"
    for ch in board:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            if ch == want:
                return rank * 8 + file
            file += 1
    raise ValueError(fen)


if __name__ == "__main__":
    sys.exit(main())
