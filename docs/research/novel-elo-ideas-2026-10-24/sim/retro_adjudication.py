# Retrospective look at saved fastchess games: CPU spent after a game is "nearly decided",
# and the variance price of stopping such games at random with an AIPW correction.
import re, sys, math
from collections import defaultdict
cre = re.compile(r"\{([^}]*)\}")
ere = re.compile(r"^\s*([+-]?)(M?)(\d+(?:\.\d+)?)/\d+\s+(\d+(?:\.\d+)?)s")
games = []
for chunk in open(sys.argv[1], encoding="utf-8").read().split("[Event ")[1:]:
    t = dict(re.findall(r'\[(\w+) "([^"]*)"\]', chunk))
    if t.get("Result") not in ("1-0", "0-1", "1/2-1/2") or t.get("TimeControl") != "10+0.1":
        continue
    body = chunk.split("\n\n", 1)[1] if "\n\n" in chunk else ""
    white_first = " w " in t["FEN"]
    pl = []   # (white-perspective score in pawns or None, seconds)
    for i, c in enumerate(cre.findall(body)):
        m = ere.match(c)
        mover_white = white_first if i % 2 == 0 else not white_first
        if not m: pl.append((None, 0.0)); continue
        v = 100.0 if m.group(2) else float(m.group(3))
        v = -v if m.group(1) == "-" else v
        pl.append((v if mover_white else -v, float(m.group(4))))
    res_w = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[t["Result"]]
    games.append(dict(fen=t["FEN"], rnd=t.get("Round"), new_white=(t["White"] == "new"), res_w=res_w,
                      pl=pl, term=t.get("Termination", "")))
print(f"{len(games)} games at 10+0.1")
# pair consecutive games with the same opening
pairs, i = [], 0
while i + 1 < len(games):
    if games[i]["fen"] == games[i+1]["fen"]:
        pairs.append((games[i], games[i+1])); i += 2
    else: i += 1
print(f"{len(pairs)} colour-reversed pairs")
def cpu(g): return sum(s for _, s in g["pl"])
def trigger(g, T, m=6):
    """first ply index after which the last m plies all show the same side >= T pawns (white persp)."""
    run_sign, run = 0, 0
    for k, (v, _) in enumerate(g["pl"]):
        if v is None: run = 0; continue
        sgn = 1 if v >= T else (-1 if v <= -T else 0)
        if sgn != 0 and sgn == run_sign: run += 1
        else: run_sign, run = sgn, (1 if sgn else 0)
        if run >= m: return k, run_sign
    return None, 0
def new_score(g): return g["res_w"] if g["new_white"] else 1 - g["res_w"]
pair_scores = [new_score(a) + new_score(b) for a, b in pairs]
mu = sum(pair_scores)/len(pair_scores); var_pair = sum((x-mu)**2 for x in pair_scores)/len(pair_scores)
cpu_pair = sum(cpu(a) + cpu(b) for a, b in pairs)/len(pairs)
print(f"pair score (0-2) mean {mu:.3f} var {var_pair:.4f}; mean CPU per pair {cpu_pair:.1f} s (both engines)")
for T in [1.0, 1.5, 2.0, 3.0]:
    # calibration: favoured side's final score after the trigger, pooled over games
    trig, after, fav = [], [], []
    for a, b in pairs:
        for g in (a, b):
            k, s = trigger(g, T)
            if k is None: continue
            after.append(sum(x for _, x in g["pl"][k+1:]))
            fav.append(g["res_w"] if s > 0 else 1 - g["res_w"])
    n_trig = len(fav); f = sum(fav)/n_trig
    mse = sum((y - f)**2 for y in fav)/n_trig        # E[(Y-f)^2] with a constant calibrated f
    rev = sum(1 for y in fav if y == 0.0)/n_trig; dr = sum(1 for y in fav if y == 0.5)/n_trig
    saved_per_pair = sum(after)/len(pairs)            # CPU after trigger, per pair, if every triggered game stopped
    line = (f"T={T:.1f} pawns, 6 plies: {n_trig/(2*len(pairs)):.1%} of games trigger; favoured side scores {f:.3f} "
            f"(draws {dr:.1%}, reversals {rev:.1%}); CPU after trigger = {saved_per_pair/cpu_pair:.1%} of all CPU")
    print(line)
    for pi in [1.0, 0.5, 0.25, 0.1]:
        extra = (n_trig/len(pairs)) * (1/pi - 1) * mse            # per pair, AIPW randomisation variance
        cost = cpu_pair - (1 - pi) * saved_per_pair
        eff = (var_pair * cpu_pair) / ((var_pair + extra) * cost)
        print(f"     play-out prob {pi:4.2f}: pair variance x{(var_pair+extra)/var_pair:.3f}, CPU x{cost/cpu_pair:.3f} -> efficiency x{eff:.3f}")
# CPU per pair and signal proxy by opening imbalance (first reported eval in the game, |white persp|)
band = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
for (a, b), ps in zip(pairs, pair_scores):
    v = next((v for v, _ in a["pl"] if v is not None and abs(v) < 50), None)
    if v is None: continue
    key = min(int(abs(v)/0.25), 6)
    rec = band[key]; rec[0] += 1; rec[1] += cpu(a) + cpu(b); rec[2] += ps; rec[3] += ps*ps
print("opening |first eval| band: pairs, mean CPU per pair (s), pair-score variance")
for key in sorted(band):
    n, c, s1, s2 = band[key]; m1 = s1/n
    print(f"  {key*0.25:.2f}-{(key+1)*0.25 if key < 6 else 9:.2f}: {n:5d}  {c/n:6.1f}  {s2/n - m1*m1:.3f}")
