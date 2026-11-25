"""Win rate against the engine's raw score, from its own self-play data (White's view: fen | score | result | ...).
Finds the raw score at which the side ahead wins half its games, the usual meaning of 100 centipawns."""
import os, sys

path, limit = os.path.expanduser(sys.argv[1]), int(sys.argv[2])
step = 50
buckets = {}
with open(path) as f:
    for n, line in enumerate(f):
        if n >= limit:
            break
        parts = line.split("|")
        score, result = int(parts[1]), float(parts[2])
        if score < 0:
            score, result = -score, 1.0 - result
        b = buckets.setdefault(min(score // step, 40), [0, 0, 0, 0.0])
        b[0] += 1
        b[1] += result == 1.0
        b[2] += result == 0.5
        b[3] += result
print("raw score   positions   win%   draw%   expected")
prev = None
for k in sorted(buckets):
    n, w, d, e = buckets[k]
    if n < 2000:
        continue
    win = w / n
    print(f"{k * step:5d}-{k * step + step - 1:<5d} {n:9d}  {100 * win:5.1f}  {100 * d / n:5.1f}   {e / n:.3f}")
    if prev and prev[1] < 0.5 <= win:
        x0, w0 = prev
        x = x0 + (0.5 - w0) / (win - w0) * (k * step + step / 2 - x0)
        print(f"  -> the side ahead wins half its games at a raw score of about {x:.0f}")
    prev = (k * step + step / 2, win)
