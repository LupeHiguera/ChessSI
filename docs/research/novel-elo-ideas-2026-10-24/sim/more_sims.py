import numpy as np, math
from math import erf, sqrt
rng = np.random.default_rng(7)
k = math.sqrt(2)*math.log(10)/800      # per-pair standardized drift per nElo
phi = lambda x: np.exp(-x*x/2)/math.sqrt(2*math.pi)
Phi = lambda x: 0.5*(1+np.vectorize(lambda t: erf(t/sqrt(2)))(x))

# ---------- 1. SPRT [0,5] vs Bayesian expected-loss stopping, Elo per CPU ----------
def sprt(theta, e0=0, e1=5, al=0.05, be=0.05, batch=50, nmax=200000):
    a, b = math.log(be/(1-al)), math.log((1-be)/al)
    d0, d1 = e0*k, e1*k
    S = np.zeros_like(theta); n = 0; done = np.zeros(theta.shape, bool)
    N = np.full(theta.shape, nmax, float); acc = np.zeros(theta.shape, bool)
    while not done.all() and n < nmax:
        S[~done] += theta[~done]*k*batch + math.sqrt(batch)*rng.standard_normal((~done).sum())
        n += batch
        L = (d1-d0)*S - n*(d1*d1-d0*d0)/2
        up = ~done & (L >= b); dn = ~done & (L <= a)
        acc[up] = True; N[up|dn] = n; done |= up|dn
    acc[~done] = False
    return N, acc
def eloss(theta, m0, s0, eps, batch=50, nmax=200000, nmin=200):
    S = np.zeros_like(theta); n = 0; done = np.zeros(theta.shape, bool)
    N = np.full(theta.shape, nmax, float); acc = np.zeros(theta.shape, bool)
    while not done.all() and n < nmax:
        S[~done] += theta[~done]*k*batch + math.sqrt(batch)*rng.standard_normal((~done).sum())
        n += batch
        prec = 1/s0**2 + n*k*k; m = (m0/s0**2 + k*S)/prec; s = 1/np.sqrt(prec)
        ela = s*phi(m/s) - m*Phi(-m/s)        # E[max(-theta,0)]: loss if we accept
        elr = s*phi(m/s) + m*Phi(m/s)         # E[max(theta,0)]:  loss if we reject
        stop = ~done & (np.minimum(ela, elr) < eps) & (n >= nmin)
        acc[stop] = (ela < elr)[stop]; N[stop] = n; done |= stop
    m_end = m; acc[~done] = (m_end > 0)[~done]
    return N, acc
print("== Elo per CPU: prior theta ~ N(m, s^2) in nElo; per idea averages ==")
for (pm, ps) in [(0.0, 6.0), (2.0, 8.0), (5.0, 15.0)]:
    theta = rng.normal(pm, ps, 4000)
    rows = []
    N, acc = sprt(theta); rows.append(("SPRT [0,5] a=b=0.05", N, acc))
    N, acc = sprt(theta, be=0.2); rows.append(("SPRT [0,5] a=0.05 b=0.20", N, acc))
    for eps in [0.05, 0.1, 0.2]:
        N, acc = eloss(theta, pm, ps, eps); rows.append((f"Expected loss < {eps} nElo", N, acc))
    print(f"-- prior N({pm}, {ps}^2) nElo --")
    for name, N, acc in rows:
        gain = (theta*acc).mean(); lost = (theta*acc*(theta<0)).mean()
        print(f"{name:28s} pairs/idea {N.mean():7.0f}  nElo gained/idea {gain:6.3f} (of which from bad accepts {lost:6.3f})  nElo per 10k pairs {1e4*gain/N.mean():6.3f}")

# ---------- 2. complementary-pair factorial: per-factor estimator variance ----------
print("== factorial check: k factors, games x vs complement, Hadamard-cycled signs ==")
H = np.array([[1,1,1,1,1,1,1,1],[1,-1,1,-1,1,-1,1,-1],[1,1,-1,-1,1,1,-1,-1],[1,-1,-1,1,1,-1,-1,1],
              [1,1,1,1,-1,-1,-1,-1],[1,-1,1,-1,-1,1,-1,1],[1,1,-1,-1,-1,-1,1,1],[1,-1,-1,1,-1,1,1,-1]])
signs = H[:, 1:5]            # 8 runs x 4 factors (orthogonal columns)
beta = np.array([8.0, 3.0, 0.0, -4.0])    # true effects in nElo
npairs, reps = 4000, 3000
est = np.zeros((reps, 4)); est_single = np.zeros(reps)
for r in range(reps):
    s = signs[np.arange(npairs) % 8]
    y = (s @ beta)*k + rng.standard_normal(npairs)     # per pair standardized outcome, engine x's view
    est[r] = (s*y[:, None]).mean(0)/k
    est_single[r] = ((beta[0]*k + rng.standard_normal(npairs)).mean())/k   # one-factor test, same pairs
print("true", beta, "mean est", est.mean(0).round(2), "sd est", est.std(0).round(2), "| single-factor sd", est_single.std().round(2))

# ---------- 3. pre-screen (2+0.02) vs full (10+0.1) results from docs/IDEAS.md ----------
pre  = np.array([76.6, -23.8, 107.5, 107.3, 43.1, 48.6, 12.2, 33.7, 30.8, 29.0, 7.0])
pse  = np.array([27.5, 20.5, 35.2, 32.2, 19.8, 21.9, 21.0, 19.5, 20.9, 19.5, 17.7])
full = np.array([43.5, -2.7, 157.1, 83.7, 56.1, 60.4, 52.5, 43.3, 6.0, 22.2, 6.7])
fse  = np.array([14.2, 4.7, 27.0, 19.4, 15.0, 16.1, 14.9, 13.4, 4.7, 9.1, 13.9])
pse, fse = pse/1.96, fse/1.96   # the log's +/- are 95% intervals
r = np.corrcoef(pre, full)[0,1]
X = np.c_[np.ones_like(pre), pre]; coef, *_ = np.linalg.lstsq(X, full, rcond=None)
resid = full - X@coef
excess = resid.var(ddof=2) - (coef[1]**2*pse**2 + fse**2).mean()
print(f"n={len(pre)} r={r:.2f} full = {coef[0]:.1f} + {coef[1]:.2f} * pre; resid sd {resid.std(ddof=2):.1f}; "
      f"mean noise sd {np.sqrt((coef[1]**2*pse**2 + fse**2).mean()):.1f}; implied true-scatter var {excess:.0f}")
print("full - pre per idea:", (full-pre).round(1))
