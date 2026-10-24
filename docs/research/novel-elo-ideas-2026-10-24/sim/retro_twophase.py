# Two-phase (truncate at ply P, play a random subset out) on saved games: pair-level rho(P) and c(P).
import re, sys, math
cre = re.compile(r"\{([^}]*)\}")
ere = re.compile(r"^\s*([+-]?)(M?)(\d+(?:\.\d+)?)/\d+\s+(\d+(?:\.\d+)?)s")
CLIP = 4.0
games = []
for chunk in open(sys.argv[1], encoding="utf-8").read().split("[Event ")[1:]:
    t = dict(re.findall(r'\[(\w+) "([^"]*)"\]', chunk))
    if t.get("Result") not in ("1-0", "0-1", "1/2-1/2") or t.get("TimeControl") != "10+0.1": continue
    body = chunk.split("\n\n", 1)[1] if "\n\n" in chunk else ""
    wf = " w " in t["FEN"]; new_white = t["White"] == "new"
    pl = []   # (mover_is_new, score from new's perspective, seconds)
    for i, c in enumerate(cre.findall(body)):
        m = ere.match(c); mw = wf if i % 2 == 0 else not wf; mover_new = (mw == new_white)
        if not m: pl.append((mover_new, None, 0.0)); continue
        v = CLIP if m.group(2) else min(float(m.group(3)), CLIP); v = -v if m.group(1) == "-" else v
        pl.append((mover_new, v if mover_new else -v, float(m.group(4))))
    res_w = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[t["Result"]]
    games.append((t["FEN"], res_w if new_white else 1 - res_w, pl))
pairs = [(games[i], games[i+1]) for i in range(0, len(games)-1) if games[i][0] == games[i+1][0]]
pairs = pairs[::1]
def surrogate(g, P, who):
    _, y, pl = g
    if len(pl) <= P: return y
    last = 0.0
    for mover_new, v, _ in pl[:P]:
        if v is not None and (who == "both" or (who == "base") == (not mover_new)): last = v
    return 1/(1 + math.exp(-last/0.8))      # eval -> expected score, rough logistic
def corr(x, y):
    n = len(x); mx = sum(x)/n; my = sum(y)/n
    sxy = sum((a-mx)*(b-my) for a, b in zip(x, y)); sx = sum((a-mx)**2 for a in x); sy = sum((b-my)**2 for b in y)
    return sxy/math.sqrt(sx*sy)
Y = [a[1] + b[1] for a, b in pairs]
tot = [sum(s for *_, s in a[2]) + sum(s for *_, s in b[2]) for a, b in pairs]
print(f"{len(pairs)} pairs")
for P in [20, 40, 60, 80, 100]:
    c = sum(sum(s for *_, s in a[2][:P]) + sum(s for *_, s in b[2][:P]) for a, b in pairs)/sum(tot)
    for who in ["base", "both"]:
        F = [surrogate(a, P, who) + surrogate(b, P, who) for a, b in pairs]
        r = corr(F, Y)
        g = (math.sqrt((1-r*r)*(1-c)) + r*math.sqrt(c))**2
        print(f"P={P:3d} plies: CPU share c={c:.2f}; surrogate={who:4s}: pair-level rho={r:.2f}; "
              f"two-phase variance x cost = {g:.2f} ({'gain' if g < 1 else 'no gain'})")
