"""Does an opening's informativeness carry over between SPRTs?

Reads engines/sprt.pgn (every SPRT and pre-screen, appended), splits it into runs, pairs games by
(run, Round), and asks whether openings that gave decisive pairs (pair score != 1) in OTHER runs
also give decisive pairs, and more signal per pair, in a held-out run.
"""
import math
import re
import sys
from collections import defaultdict

path = sys.argv[1]
games = []
for chunk in open(path, encoding="utf-8").read().split("[Event ")[1:]:
    t = dict(re.findall(r'\[(\w+) "([^"]*)"\]', chunk))
    if t.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
        continue
    new_white = t["White"] == "new"
    pts = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[t["Result"]]
    games.append((t["TimeControl"], int(t["Round"]), t["FEN"], pts if new_white else 1 - pts))

# Runs: a new run starts when the time control changes or Round restarts near 1 after a long run.
runs, cur, tc, maxround = [], [], None, 0
for g in games:
    if cur and (g[0] != tc or (g[1] <= 3 and maxround > 30)):
        runs.append((tc, cur)); cur, maxround = [], 0
    tc = g[0]; cur.append(g); maxround = max(maxround, g[1])
runs.append((tc, cur))

pairs_by_run = []
for tc, gs in runs:
    byround = defaultdict(list)
    for _, rnd, fen, s in gs:
        byround[rnd].append((fen, s))
    pairs = [(v[0][0], v[0][1] + v[1][1]) for v in byround.values() if len(v) == 2 and v[0][0] == v[1][0]]
    pairs_by_run.append((tc, pairs))

print(f"{len(games)} games, {len(runs)} runs")
for i, (tc, p) in enumerate(pairs_by_run):
    m = sum(s - 1 for _, s in p) / len(p)
    print(f"  run {i:2d} {tc:8s} pairs {len(p):5d} mean {m:+.3f} decisive {sum(s != 1 for _, s in p) / len(p):.2f}")


def stats(scores):
    n = len(scores)
    if n < 30:
        return None
    m = sum(s - 1 for s in scores) / n
    var = sum((s - 1 - m) ** 2 for s in scores) / (n - 1)
    return n, m, math.sqrt(var), sum(s != 1 for s in scores) / n


print("\nHeld-out run vs openings ranked by decisiveness in all other runs")
print("run  pairs | seen-elsewhere: decisive rate in top half / bottom half | t^2 per pair: all, top half")
tot = defaultdict(float)
for i, (tc, pairs) in enumerate(pairs_by_run):
    other = defaultdict(lambda: [0, 0])  # opening -> [decisive, total] in other runs
    for j, (_, p2) in enumerate(pairs_by_run):
        if j != i:
            for fen, s in p2:
                other[fen][0] += s != 1
                other[fen][1] += 1
    seen = [(fen, s) for fen, s in pairs if fen in other]
    if len(seen) < 100:
        continue
    # Shrink toward the overall rate so openings seen once don't dominate.
    base = sum(d for d, _ in other.values()) / sum(n for _, n in other.values())
    score = {f: (d + 2 * base) / (n + 2) for f, (d, n) in other.items()}
    ranked = sorted(seen, key=lambda x: score[x[0]], reverse=True)
    top, bottom = ranked[: len(ranked) // 2], ranked[len(ranked) // 2:]
    a, t_, b = stats([s for _, s in seen]), stats([s for _, s in top]), stats([s for _, s in bottom])
    if not (a and t_ and b):
        continue
    eff_all = (a[1] / a[2]) ** 2
    eff_top = (t_[1] / t_[2]) ** 2
    print(f"{i:3d} {len(seen):6d} | {t_[3]:.2f} / {b[3]:.2f} | mean all {a[1]:+.3f} top {t_[1]:+.3f} bottom {b[1]:+.3f}"
          f" | t2 {eff_all:.4f} {eff_top:.4f}")
    tot["n"] += 1
    tot["dtop"] += t_[3]; tot["dbot"] += b[3]
    tot["eall"] += eff_all; tot["etop"] += eff_top
print(f"\nmean decisive rate top {tot['dtop'] / tot['n']:.3f} vs bottom {tot['dbot'] / tot['n']:.3f};"
      f" mean t^2/pair all {tot['eall'] / tot['n']:.4f} vs top half {tot['etop'] / tot['n']:.4f}")
