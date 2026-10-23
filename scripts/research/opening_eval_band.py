"""Does the engine's own eval of an opening predict how informative its game pair is?

For each pair, take |eval| from the first move of the first game (the engine's own search of the
book position), bin pairs by it, and compare per bin: decisive rate (pair score != 1), mean pair
score, and signal per pair. Signal is normalised within each run: t2_bin / t2_run, where
t2 = (mean / sd)^2 is what an SPRT accumulates per pair.
"""
import math
import re
import sys
from collections import defaultdict

games = []
for chunk in open(sys.argv[1], encoding="utf-8").read().split("[Event ")[1:]:
    t = dict(re.findall(r'\[(\w+) "([^"]*)"\]', chunk))
    if t.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
        continue
    m = re.search(r"\{([+-]?\d+\.\d+|[+-]?M\d+)/\d+", chunk)
    ev = None
    if m and "M" not in m.group(1):
        ev = abs(float(m.group(1)))
    pts = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[t["Result"]]
    games.append((t["TimeControl"], int(t["Round"]), t["FEN"], pts if t["White"] == "new" else 1 - pts, ev))

runs, cur, tc, maxround = [], [], None, 0
for g in games:
    if cur and (g[0] != tc or (g[1] <= 3 and maxround > 30)):
        runs.append((tc, cur)); cur, maxround = [], 0
    tc = g[0]; cur.append(g); maxround = max(maxround, g[1])
runs.append((tc, cur))

edges = [0.0, 0.3, 0.5, 0.65, 0.8, 1.0, 99]
label = lambda e: next(f"{edges[k]:.1f}-{edges[k+1]:.1f}" for k in range(len(edges) - 1) if e < edges[k + 1])

def t2(scores):
    n = len(scores)
    m = sum(s - 1 for s in scores) / n
    v = sum((s - 1 - m) ** 2 for s in scores) / (n - 1)
    return (m * m / v) if v > 0 else 0.0, m

agg = defaultdict(lambda: {"n": 0, "dec": 0, "w": 0.0, "ratio": 0.0, "mean_rel": 0.0, "var_rel": 0.0})
total_pairs = 0
for tc, gs in runs:
    byround = defaultdict(list)
    for _, rnd, fen, s, ev in gs:
        byround[rnd].append((fen, s, ev))
    pairs = [(v[0][2], v[0][1] + v[1][1]) for v in byround.values()
             if len(v) == 2 and v[0][0] == v[1][0] and v[0][2] is not None]
    if len(pairs) < 200:
        continue
    run_t2, run_m = t2([s for _, s in pairs])
    run_var = sum((s - 1 - run_m) ** 2 for _, s in pairs) / (len(pairs) - 1)
    if run_t2 <= 0 or abs(run_m) < 0.02:
        continue  # near-zero runs give a meaningless ratio
    total_pairs += len(pairs)
    bins = defaultdict(list)
    for ev, s in pairs:
        bins[label(ev)].append(s)
    for b, sc in bins.items():
        if len(sc) < 20:
            continue
        bt2, bm = t2(sc)
        a = agg[b]
        a["n"] += len(sc); a["dec"] += sum(s != 1 for s in sc)
        bvar = sum((x - 1 - bm) ** 2 for x in sc) / (len(sc) - 1)
        a["w"] += len(sc); a["ratio"] += len(sc) * bt2 / run_t2; a["mean_rel"] += len(sc) * bm / run_m
        a["var_rel"] += len(sc) * bvar / run_var

print(f"{len(games)} games, {total_pairs} pairs from runs with a clear Elo difference")
print(f"{'|eval| band':11} {'pairs':>6} {'share':>6} {'decisive':>9} {'mean vs run':>12} {'var vs run':>11} {'efficiency':>11}")
for b in sorted(agg, key=lambda x: float(x.split('-')[0])):
    a = agg[b]
    mr, vr = a['mean_rel'] / a['w'], a['var_rel'] / a['w']
    print(f"{b:11} {a['n']:6d} {a['n'] / total_pairs:6.2f} {a['dec'] / a['n']:9.2f} {mr:12.2f} {vr:11.2f} {mr * mr / vr:11.2f}")
