import numpy as np, math
rng = np.random.default_rng(11)
k = math.sqrt(2)*math.log(10)/800
a, b = math.log(0.05/0.95), math.log(0.95/0.05)
d1 = 5*k
def factorial_vs_separate(beta, reps=3000, batch=16, nmax=150000):
    K = len(beta)
    H = np.array([[1,1,1,1,1,1,1,1],[1,-1,1,-1,1,-1,1,-1],[1,1,-1,-1,1,1,-1,-1],[1,-1,-1,1,1,-1,-1,1],
                  [1,1,1,1,-1,-1,-1,-1],[1,-1,1,-1,-1,1,-1,1],[1,1,-1,-1,-1,-1,1,1],[1,-1,-1,1,-1,1,1,-1]])[:, 1:K+1]
    sep_N = np.zeros((reps, K)); sep_acc = np.zeros((reps, K))
    for j in range(K):   # separate SPRTs
        S = np.zeros(reps); n = 0; done = np.zeros(reps, bool)
        while not done.all() and n < nmax:
            S[~done] += beta[j]*k*batch + math.sqrt(batch)*rng.standard_normal((~done).sum()); n += batch
            L = d1*S - n*d1*d1/2
            up = ~done & (L >= b); dn = ~done & (L <= a)
            sep_acc[up, j] = 1; sep_N[up|dn, j] = n; done |= up|dn
        sep_N[~done, j] = nmax
    # factorial: every pair is x vs complement; rows of H cycled within each batch of 8 pairs
    S = np.zeros((reps, K)); n = 0; done = np.zeros((reps, K), bool); fN = np.zeros(reps); facc = np.zeros((reps, K))
    s_batch = H[np.arange(batch) % 8]                 # batch x K signs
    mean_y = s_batch @ np.array(beta) * k             # batch
    while not done.all() and n < nmax:
        y = mean_y[None, :] + rng.standard_normal((reps, batch))
        S += y @ s_batch; n += batch
        L = d1*S - n*d1*d1/2
        up = ~done & (L >= b); dn = ~done & (L <= a)
        facc[up] = 1; done |= up | dn
        fN[(done.all(1)) & (fN == 0)] = n
    fN[fN == 0] = nmax
    print(f"effects {beta} nElo: separate SPRTs total pairs {sep_N.sum(1).mean():.0f} (each {sep_N.mean(0).round(0)}), "
          f"P(pass) {sep_acc.mean(0).round(3)} | factorial pairs until all decided {fN.mean():.0f}, P(pass) {facc.mean(0).round(3)} "
          f"| saving x{sep_N.sum(1).mean()/fN.mean():.2f}")
factorial_vs_separate([4.3, 7.1, 0.0, -2.8])
factorial_vs_separate([10.0, 4.3, 7.1, 0.0])
factorial_vs_separate([4.3, 7.1, 0.0, -2.8, 14.0, 2.0, -5.0][:7])
