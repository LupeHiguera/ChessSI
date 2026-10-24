# Brownian approximation of the normalized-Elo GSPRT on game pairs.
# Units: u = n * Delta^2 where Delta = per-pair standardized drift between the bounds.
# Bounds normalised to mu0=0, mu1=1 (in units of Delta). True effect mu (same units).
import numpy as np, math
rng = np.random.default_rng(1)
alpha = beta = 0.05
a, b = math.log(beta/(1-alpha)), math.log((1-beta)/alpha)
du = 0.004
def run(mu, rule, A=None, B=None, paths=20000, umax=200.0):
    X = np.zeros(paths); u = 0.0
    alive = np.ones(paths, bool); T = np.full(paths, np.nan); acc = np.zeros(paths, bool)
    while alive.any() and u < umax:
        X[alive] += mu*du + math.sqrt(du)*rng.standard_normal(alive.sum())
        u += du
        if rule == 'sprt':
            L = X - u/2
            up = alive & (L >= b); dn = alive & (L <= a)
        else:  # Lorden 2-SPRT with tilting point mu*=0.5
            L0 = 0.5*X - u/8          # log LR (mu*, mu0): large -> reject H0
            L1 = -0.5*X + 3*u/8       # log LR (mu*, mu1): large -> reject H1
            up = alive & (L0 >= A); dn = alive & (L1 >= B) & ~up
        acc[up] = True
        T[up | dn] = u; alive &= ~(up | dn)
    T[alive] = umax
    return np.nanmean(T), acc.mean()
# calibrate the 2-SPRT thresholds (symmetric) so that P(accept H1 | mu=0) = 0.05
lo, hi = 0.5, 3.0
for _ in range(14):
    mid = (lo+hi)/2
    _, p = run(0.0, '2sprt', mid, mid, paths=40000)
    if p > alpha: lo = mid
    else: hi = mid
A = (lo+hi)/2
print(f"2-SPRT threshold log A = log B = {A:.3f} (Wald SPRT a,b = {a:.3f},{b:.3f})")
delta = math.sqrt(2)*5*math.log(10)/800   # [0,5] nElo bounds, per game pair
print(f"[0,5] nElo: Delta per pair = {delta:.5f}; one u-unit = {1/delta**2:.0f} pairs")
print("true nElo | SPRT ASN u (pairs)  P(pass) | 2-SPRT ASN u (pairs) P(pass) | ratio")
for nelo in [0, 1, 2, 2.5, 3, 4, 5, 7.5, 10, 15]:
    mu = nelo/5
    t1, p1 = run(mu, 'sprt'); t2, p2 = run(mu, '2sprt', A, A)
    print(f"{nelo:7.1f}   | {t1:5.2f} ({t1/delta**2:7.0f})  {p1:.3f} | {t2:5.2f} ({t2/delta**2:7.0f})  {p2:.3f} | {t2/t1:.2f}")
print(f"fixed-sample test with same errors: u = {(1.6449+1.6449)**2:.2f} ({(1.6449+1.6449)**2/delta**2:.0f} pairs)")
