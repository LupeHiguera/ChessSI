"""Truncated games judged by the unchanged engine: how much signal per CPU second?

For each game, play stops (hypothetically) after ply P of the game proper. The judgement is the
BASE engine's last reported eval at or before ply P, from new's side, clipped to +/-CLIP pawns;
a game already over by ply P counts as +/-CLIP or 0. For each run we compare, per pair:
  - final results (what the SPRT uses) vs the truncated judgement
  - signal t2 = (mean/sd)^2 per pair, and per CPU second spent (both engines' move times)
  - whether the truncated judgement agrees with the final result on the sign of each run
"""
import math
import re
import sys
from collections import defaultdict

CLIP = 4.0
PLIES = [10, 20, 30, 40, 60]

move_comment = re.compile(r"\{([^}]*)\}")
eval_re = re.compile(r"^\s*([+-]?)(M?)(\d+(?:\.\d+)?)/\d+\s+(\d+(?:\.\d+)?)s")

games = []
for chunk in open(sys.argv[1], encoding="utf-8").read().split("[Event ")[1:]:
    t = dict(re.findall(r'\[(\w+) "([^"]*)"\]', chunk))
    if t.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
        continue
    body = chunk.split("\n\n", 1)[1] if "\n\n" in chunk else ""
    first_white = " w " in t["FEN"]
    plies = []  # (mover_is_white, eval in pawns from mover's side or None, seconds)
    for k, c in enumerate(move_comment.findall(body)):
        m = eval_re.match(c)
        mover_white = first_white if k % 2 == 0 else not first_white
        if not m:
            plies.append((mover_white, None, 0.0))
            continue
        sign = -1 if m.group(1) == "-" else 1
        val = CLIP if m.group(2) else min(float(m.group(3)), CLIP)
        plies.append((mover_white, sign * val, float(m.group(4))))
    new_white = t["White"] == "new"
    pts = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[t["Result"]]
    new_pts = pts if new_white else 1 - pts
    games.append((t["TimeControl"], int(t["Round"]), t["FEN"], new_pts, new_white, plies))

runs, cur, tc, maxround = [], [], None, 0
for g in games:
    if cur and (g[0] != tc or (g[1] <= 3 and maxround > 30)):
        runs.append((tc, cur)); cur, maxround = [], 0
    tc = g[0]; cur.append(g); maxround = max(maxround, g[1])
runs.append((tc, cur))


def judge(g, P):
    """Base engine's last eval at or before ply P, from new's side, and CPU seconds used."""
    _, _, _, new_pts, new_white, plies = g
    secs = sum(p[2] for p in plies[:P])
    if len(plies) <= P:  # game over by then: use the result
        return (new_pts - 0.5) * 2 * CLIP, secs
    last = 0.0
    for mover_white, ev, _ in plies[:P]:
        if ev is not None and mover_white != new_white:  # base moved
            last = -ev
    return last, secs


def t2(xs):
    n = len(xs); m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m * m / v if v > 0 else 0.0, m, math.sqrt(v / n)


rows = defaultdict(lambda: {"runs": 0, "agree": 0, "gain": 0.0, "corr_n": 0})
print("run tc       pairs  final: mean(+-se)    | judged at ply P: t2-per-CPU-second relative to final, sign agrees")
for i, (tc, gs) in enumerate(runs):
    byround = defaultdict(list)
    for g in gs:
        byround[g[1]].append(g)
    pairs = [v for v in byround.values() if len(v) == 2 and v[0][2] == v[1][2]]
    if len(pairs) < 150:
        continue
    final = [a[3] + b[3] - 1 for a, b in pairs]
    full_secs = sum(sum(p[2] for p in g[5]) for v in pairs for g in v) / len(pairs)
    ft2, fm, fse = t2(final)
    line = f"{i:3d} {tc:8s} {len(pairs):5d}  {fm:+.3f} (+-{fse:.3f})   |"
    for P in PLIES:
        js, secs = [], 0.0
        for a, b in pairs:
            ja, sa = judge(a, P); jb, sb = judge(b, P)
            js.append(ja + jb); secs += sa + sb
        jt2, jm, jse = t2(js)
        secs /= len(pairs)
        rel = (jt2 / secs) / (ft2 / full_secs) if ft2 > 0 and secs > 0 else float("nan")
        agree = (jm > 0) == (fm > 0)
        line += f" P{P}: {rel:5.2f}{'' if agree else '!'}"
        if abs(fm) > 2 * fse:  # only runs whose final result is clearly non-zero
            r = rows[P]; r["runs"] += 1; r["agree"] += agree; r["gain"] += math.log(rel) if rel > 0 else 0
    print(line)

print("\nRuns with a clear final result (|mean| > 2 se):")
for P in PLIES:
    r = rows[P]
    if r["runs"]:
        print(f"  P={P:2d}: sign agrees in {r['agree']}/{r['runs']} runs; geometric-mean signal per CPU second "
              f"{math.exp(r['gain'] / r['runs']):.2f}x the final-result SPRT")
