# Proposed orthogonal perturbation screen

Status: proposed, unclaimed and not run. This is one local tuning-method experiment, capped at 2,048 color-swapped game pairs. It does not estimate the Elo of a completed tuning run.

## Frozen configuration

Use accepted main 4348bbb, one own network, 50,000 requested nodes per move and the same 1 MB TT on both sides. Explicitly realize accepted CPU constants rather than taking stale GPU defaults. Complete the existing GPU write-ownership repair and matched CPU/GPU parity first. Record the entire parameter/table/network/build manifest.

Hold the center fixed throughout the study. Freeze the two LMR-table parameters and vary the 15 integer parameters. Publish their effective positive half-differences c_j before games; require integer rounding to give common midpoints and nonzero constant half-differences at every design row. Choose endpoints inside legal ranges, without clipping-induced changes to the intended center. Reject duplicate or zero-effective coordinates before play.

Freeze the shared UHO_Lichess_4852_v1.epd book hash, opening identities, partition membership and randomization seed (20261026) before observing outcomes. Allocate the three disjoint opening pools by one outcome-blind uniform random permutation of book indices. Use independent RNG streams for opening allocation and perturbation signs. All stages target that same book population; finite disjoint pools are not additional independent draws of the same opening. Preserve both colors within each pair. Fixed-node games and 1 MB TT remain research conditions; the eventual CPU timed SPRT uses the project's production settings.

## Estimand

Let P_o(d) be the plus side's total points in its two color-swapped games on opening o. Define Y_o(d)=P_o(d)-1, in [-1,1]. Let beta=E[d*Y_o(d)] for independent uniform signs d and the declared opening population. This is a directional self-match response vector, not necessarily the gradient of Elo or strength against a fixed opponent.

Each method estimates beta by averaging d*Y. For Hadamard, take the 15 nonconstant columns of a 16-row matrix. Independently flip each column's sign for every opening block, using randomness fixed in the manifest. Each row then has the same marginal direction law as the IID control. Within a block the directions are correlated.

Use one opening for all 16 directions in a block. Orthogonal cancellation in a local linear model requires a common response vector; using a different opening for each row breaks that argument. The control also uses 16 directions on that same opening and the same frozen center. Thus batching, center staleness and opening allocation are held constant.

## Pair allocation

| Stage | Allocation | Pair cap |
| --- | --- | ---: |
| Estimate | 32 openings x 16 directions x 2 methods | 1,024 |
| Validate directional prediction | 32 new openings x 16 fresh IID directions, one common panel | 512 |
| Compare one update | 256 untouched openings x 2 candidate-versus-center pairs | 512 |

The two methods produce beta_H and beta_I from the estimation stage. On the common validation panel, predict Y using d^T beta_hat, with no fitting, clipping or parameter selection on that panel. Primary difference is mean[(Y-d^T beta_H)^2 - (Y-d^T beta_I)^2]. Conditional on the fitted vectors and the frozen validation opening pool, define beta_V=E[dY] for a uniform opening from that pool and fresh IID signs. Expected prediction-risk differences then equal ||beta_H-beta_V||^2 - ||beta_I-beta_V||^2 because E[dd^T]=I. The finite observed panel estimates that risk; it is not an exact algebraic identity for its realized design matrix. This definition avoids assuming that disjoint finite opening pools have identical response vectors. The comparison does not require the game response itself to be linear.

Report a paired confidence interval clustered by opening, using 10,000 block-bootstrap resamples and seed 20261026. Compare each predictor to the zero predictor too. A favorable Hadamard screen requires a 95% upper bound below zero for its risk difference against IID and a 95% upper bound below zero for its paired risk difference against the zero predictor. Otherwise stop as rejected or inconclusive and omit the final-step games. The interval assesses these realized estimators; it does not prove lower variance across all tuning runs.

## One predeclared update

For a simple fixed local step, use theta'_j = theta_j + c_j*clip(2*beta_hat_j,-1,1), then apply the shared integer realization and legal-range clipping. This is the same coordinate-capped rule for both methods. Current gpu/spsa.py uses wins-minus-losses=2Y, so the uncapped 2*c_j*beta_hat_j form corresponds to a_j=c_j^2 under this repository's convention. Keep LMR floats fixed. Do not choose the gain from the validation results.

On each final opening, play candidate_H versus center and candidate_I versus center, both with swapped colors. Compare candidate scores paired by opening. If the realized candidates are identical, omit these matches and report no operational difference at this step size. Publish the interval and any sign disagreement with the prediction result. A nonnegative paired score difference without clear contradictory evidence can justify an independent replication; it is not proof of noninferiority or a strength gain. A negative or broad result must remain visible rather than prompting a new step-size search on these same openings.

## What would falsify the idea

Park the method if it fails the independent prediction gate, if perturbations mostly realize to identical settings, or if its frozen update performs worse in the untouched comparison. Favorable results justify another fresh-block replication, then a separately budgeted complete-tuning comparison. They do not justify replacing ordinary SPSA immediately.

Nonlinear interactions, opening-specific effects and coarse integer parameters can erase the local-linear advantage. Repeating exactly the same deterministic games creates no independent evidence. Group uncertainty by openings, preserve every exclusion, and use new openings for replication. Primary prior art: [Bhatnagar et al., deterministic perturbation sequences](https://www.cs.jhu.edu/~ijwang/pub/p180-bhatnagar.pdf).
