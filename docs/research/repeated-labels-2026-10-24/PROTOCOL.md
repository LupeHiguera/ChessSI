# Repeated position label study

Astra is testing whether ChessSI can learn better targets from positions it has already seen in several games. The current trainer keeps the first observation of each position. This study separates the effect of a newer teacher from the effect of averaging repeated labels.

**Status:** claimed on 2026-10-24; research protocol only. No dataset scan, training run, engine change or strength result. Local execution waits until a machine is available. Owner: GPT-6 (Codex); mathematical and experimental review: GPT-6 Astra ultra. Source baseline: `7af0aaebdae884584d0b8cd92f706a8f9be52acd`. Initial plan: [merged PR 27](https://github.com/LupeHiguera/ChessSI/pull/27). Follow-up branch: `astra/repeated-label-review-20261024`.

## Hypothesis and prior art

The hypothesis is that multiple comparable observations reduce target noise at unchanged training weight per position. Newer labels may also help, but these are different effects.

This is **Known**, not a novelty claim. The [neural-chess aggregation implementation](https://github.com/pbaer/neural-chess/blob/524ba14d4af3b739cbe19bd8cd0b14892e6305ca/src/v3/aggregate.py) already compares averaged game outcomes with a single observed outcome. It is prior art only; ChessSI will use its own games and search scores exclusively.

For squared loss, `sum((p - y_i)^2) = n * (p - mean(y))^2 + constant`. Average the probability targets, not the centipawn scores before applying sigmoid. Giving the resulting row weight `n` also changes position frequency; this experiment gives every identity one weight.

## What the current code does

Both loaders in [nnue/train.py](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/nnue/train.py#L172-L236) retain the first index returned by `np.unique`. The position key contains the first four FEN fields, omitting move counters. The parser ignores the fourth data field, the static evaluation.

The [generator](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/src/datagen.cpp) writes completed games contiguously as `FEN | White search score | result | White static eval`. It omits noisy positions and does not write a game ID or move history. A decrease or repetition in absolute ply, or a changed result, proves a new game has started. An uninterrupted increasing ply sequence does not prove that all its rows belong to one game.

The existing loader's inferred game IDs therefore cannot be treated as exact ground truth. This limits the first study to a conservative group screen.

## Evidence from the training run

[Claude's run report](https://github.com/LupeHiguera/ChessSI/pull/27#issuecomment-6389446390) confirms that files were supplied oldest generation first. A repeated position can therefore retain its PeSTO label even when generation 6 contains a net9 search label. This supports keeping the latest-teacher control; it does not establish a gain from replacing the label.

Claude reports roughly 255 million raw rows and 233.7 million retained positions. Conditional on those approximate totals, about 21.3 million rows are excess observations, roughly 8.4% of raw rows. This is not the fraction of unique positions affected: if raw count is R, distinct count U and repeated-identity count K, then `K <= R - U`. The reported totals imply an upper bound near 9.1% of unique identities, while cross-generation repeats and context-matched eligible identities can be much fewer.

The [network record](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/nets/README.md) gives generation figures summing to about 262.6 million positions and uses `<data files>` in its command. These summaries do not resolve the exact raw count or source order. Freeze the actual ordered file ranges and cache endpoints before the pilot; use existing logs/manifests where available. No full-corpus scan is needed to reconcile the reported accounting before this bounded study.

## Bounded CPU pilot

When PC2 is ready, use one assigned CPU worker, a **2 GiB working-memory cap**, and **at most 2 million raw rows**. Use streaming input and disk-backed partitions instead of loading the training corpus. Stop at the cap and report coverage; do not expand the scan after seeing its result.

Freeze a manifest before examining labels. It must identify the exact source ranges, their hashes and order, the ChessSI source/binary/network, generator version, seed or writer run, node budget and random-opening settings. Use original single-writer streams with known ordering. Reordered exports, copied runs and unknown teacher/budget mixtures are ineligible.

Select the latest documented teacher cohort at one node budget in advance. Reserve up to 1.5 million rows for it and up to 0.5 million for documented earlier teachers at the same budget and generator settings. Divide each allowance equally across eligible writer streams, assigning any remainder in fixed manifest order. If no matched earlier cohort exists, allocate the full cap to the latest cohort and omit the teacher-refresh comparison. Record this choice before reading labels. A bounded prefix study describes those prefixes, not the whole corpus.

Retain source offsets and full FEN strings to verify hash matches. Truncate only at complete records and exclude the last unfinished conservative group at each sampled range boundary. Establish group boundaries before filtering or aggregating. If provenance cannot establish original game-contiguous streams, stop with a readiness result; recovering missing history is a separate task.

## Position and game context

Use full six-field FEN equality for the primary screen and restrict it to halfmove clock zero. This matches absolute ply and removes earlier board-repetition history after the latest pawn move or capture. Keep teacher, node budget, random-opening settings and adjudication settings explicit. The generator's 400 searched-ply horizon makes absolute ply and random-opening length relevant.

Halfmove clock zero does **not** recover all generator/search state: adjudication win streaks, TT contents and search-history tables can still differ. Treat their effect as residual variation in observed labels. This is a repeatability study, not proof that the observations came from identical complete states.

Where explicit game IDs exist, use them. Otherwise define a conservative group between certified boundaries in each original writer stream. Such a group can merge games but cannot split a game under the stated provenance assumptions. Keep at most one vote per position per group. Never label the inferred count as an exact number of independent games.

As a separate descriptive count, report how often the current first-four-FEN key merges different halfmove clocks or absolute plies. Do not mix that broader population into the primary comparison to increase coverage.

## Three comparison arms

For each context-matched position, use the same eligible observations and the same position weight:

| Arm | Label rule | Question |
| --- | --- | --- |
| F | First eligible observation in frozen source order across documented teachers | Context-matched analogue of first occurrence |
| L | First eligible observation from the predeclared latest teacher at the matched budget | Does changing teacher generation help? |
| M | Mean of the latest teacher's labels, one vote per conservative group | Does averaging help beyond teacher refresh? |

F is not an exact reproduction of the current loader: the primary screen deliberately excludes aliased clock/history contexts. Audit the literal current selection separately.

For each White-relative score `s` and outcome `r`, compute `y = 0.75 * sigmoid(s / 400) + 0.25 * r`, then flip to `1 - y` for Black to move. M averages these targets in probability space. Keep score-only and result-only errors as secondary diagnostics; changing their weights is outside this experiment.

M versus L is the primary contrast. L versus F is a secondary teacher-refresh contrast on their common eligible identities where F actually comes from an earlier teacher. A newer generation is not assumed to be better. F versus L evaluated against latest-teacher labels measures agreement with that teacher, not its accuracy or chess strength. It cannot by itself promote the refresh policy.

## Keep target selection separate from row selection

Changing the index returned by `np.unique`, or reversing the input files, is not a label-only experiment. The loader uses that index for `game`, `gkey`, `future` and row order as well as scores/results. Training then splits on `gkey % 50` and supervises the auxiliary head with `future`.

Use a frozen observation table and a separate fixed representative-row table. Observation identity is the immutable writer/run and source offset. Each position has one output-row ID, weight one, fixed features and side to move, fixed group/split assignment, and fixed auxiliary target/eligibility. F, L and M change only an explicit probability-target column. Preserve original scores/results for audit; do not encode a mean probability as an averaged centipawn score.

Determine allowed donor groups before target selection. Held-out groups are absent from every donor pool. Later training likewise excludes validation-group labels from its targets even when an identical position has a training representative. Neither `gkey` nor auxiliary supervision may be inherited from a newly selected donor. Verify equal row IDs, ordering, weights, split membership, features and auxiliary targets across arms before training.

## Held out observations and decision rule

Hold out complete conservative groups before calculating any predictors. A position must have observations in at least three latest-teacher groups so that a held-out observation can be predicted from at least two others. Every observation used as an evaluation target is excluded, together with its whole group, from that prediction's F, L and M construction.

Compute leave-one-group-out errors for the latest-teacher observations. Average errors within each identity, then give each identity equal weight in the aggregate. Report `MSE(M) - MSE(L)` and relative reduction, with exact eligible identity/group/stream counts. Apply the same held-out targets and weights to F wherever it exists.

This intentionally measures agreement on repeated positions. It is not a test of network generalization to unseen positions or an Elo estimate. Shared identities and groups also mean individual row errors are not independent.

The engineering screen requires:

- At least 500 eligible identities and 200 held-out conservative groups.
- Eligible identities representing at least 0.5% of the distinct latest-teacher first-four-FEN keys in the sampled raw records. Count each such key only once in this coverage ratio.
- At least a 2% relative reduction in primary MSE for M versus L.
- A positive reduction in four of five predetermined reporting bins, assigned by a stable hash of the manifest's writer/run ID and group start offset with seed 20261024. These bins group the already-held-out errors; they do not change the leave-one-group-out construction.
- A positive reduction for every latest-teacher writer contributing at least 100 eligible identities. Report all writer results, including smaller writers, and how many qualify for this condition.

These are resource-allocation thresholds, not statistical significance or estimated Elo. They are fixed before the pilot, not calibrated claims about the data. If coverage is insufficient, report inconclusive and stop this pilot. If coverage is sufficient but the gain or robustness condition fails, stop the aggregation candidate. Do not widen clock, teacher or budget matching to rescue it.

Save the frozen manifest, exclusion counts, source-code version, per-identity paired errors, target component diagnostics, memory peak and CPU time. Record every outcome in the research log; only played SPRTs receive an Elo estimate.

## Diagnostics within the same sample

Report repeated first-four-FEN keys and two distinct paths of coverage: cross-generation keys leading to changed F/L targets; and latest-teacher keys with at least three groups leading to full-context primary eligibility. Include the denominator for each count. These paths need not contain one another.

Generation 6 records the static evaluation as its fourth field. For a fixed board, side and evaluator version, [NNUE's static output](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/src/nnue.cpp) should be deterministic when accumulators are correct. Report the integer static-score range for matching inputs; unexplained nonzero ranges indicate a provenance, formatting or inference inconsistency. Report search-minus-static corrections descriptively.

Let q be the search probability and v the static probability for such an identity. Since v is constant, `Var(q - v) = Var(q)`; subtracting v from both predictor and held-out target also leaves score error unchanged. This subtraction does not remove random variation or identify teacher-generation shift. Missing older static values prevent a direct matched decomposition, and residual means over different position populations confound generation with position mix.

For each arm, retain score-probability error e_q and outcome error e_r in the same orientation and weighting as the primary metric. Report their cross term as well as their separate squared errors:

`MSE_blend = 0.5625 * E[e_q^2] + 0.0625 * E[e_r^2] + 0.375 * E[e_q * e_r]`.

These descriptive additions use the same records, arms and held-out groups. They do not enlarge the sample, change the decision thresholds or add a GPU experiment.

## Training and strength test after a useful screen

A passing screen earns one matched GPU comparison. Coordinate its slot with Claude in [issue 21](https://github.com/LupeHiguera/ChessSI/issues/21), including host-memory use as well as the GPU. Claude reports about 26 GB peak for one full net10 load in WSL's 46 GB; do not overlap two such loads based only on having two GPUs. A reported GPU finishing time is not a reservation. Freeze the training population, validation groups, representative features, initialization, minibatch order, number of optimizer steps, architecture and loss weights. Change only the primary target rule L versus M. Keep the existing auxiliary target and its eligibility identical between arms; averaging it too would be another experiment.

Split games/groups before aggregation and never use held-out labels in training averages. Report repeat-position and unseen-position validation separately. Do not compare each network against its own different target set.

The exact larger-data construction must be frozen before training; the pilot's clock-zero result does not authorize aggregation across arbitrary clocks/history. Match controls on the identities actually changed and preserve the rest of the dataset.

Validate exported inference and run required engine correctness checks. Use the same frozen current engine binary for both networks in a [network SPRT](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/scripts/nnue-sprt.sh), with balanced openings and `[0, 5]` bounds at 10+0.1, followed by 60+0.6 confirmation when appropriate. A matched training-control win isolates the idea; acceptance into main additionally needs the resulting network tested against the current default. Log both baselines accurately.

## Proposed use of PC2

Use the second 265K with 32 GB RAM as Astra's CPU experiment machine. Give it separate worktrees and astra/ branches, and share a visible queue with Claude so existing candidates are not duplicated. The initial priority is this bounded pilot; while awaiting GPU training, the machine can execute agreed queued strength tests or produce ChessSI self-play data.

The [265K has eight performance cores and twelve efficient cores](https://www.intel.com/content/www/us/en/products/sku/241063/intel-core-ultra-7-processor-265k-30m-cache-up-to-5-50-ghz/specifications.html). Map PC2's actual topology and measure throughput before choosing concurrency. Prefer a consistent core type per strength test; keep each SPRT on one machine and record affinity/concurrency. Do not assume PC1's logical CPU IDs carry over. Windows scheduling under WSL still needs the repository's documented caveat.

The current [trainer explicitly selects CUDA](https://github.com/LupeHiguera/ChessSI/blob/7af0aaebdae884584d0b8cd92f706a8f9be52acd/nnue/train.py#L385-L402), so GPU training remains on PC1. CPU engine games and the label screen do not require a discrete GPU. A 32 GB machine suits these bounded workloads, but the full training loader also allocates large arrays and temporaries; it is not a streaming 233.7-million-row training solution.

PC2 is still being prepared. This role is a recommendation, not an active resource reassignment. Until it is available, preserve the existing shared-PC allocation and research-only restriction.
