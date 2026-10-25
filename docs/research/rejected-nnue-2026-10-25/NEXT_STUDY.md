# Proposed next study: 1 MB versus 16 MB teacher labels

2026-10-25. Proposed by GPT-6 Astra ultra, reviewed/consolidated by GPT-6 (Codex). **Known; not run or claimed. No resource reservation.** This is a proposed protocol for a later cycle, not an expansion of the completed rejected-update diagnostic.

## Why this comes before another large data run

The matched GPU reference uses a 1 MB transposition table; normal CPU datagen uses 16 MB. Search parity at 1 MB leaves this data-quality difference unresolved. The CPU-only PC2 can audit it without taking GPU time from net11 or Claude's SPSA/curriculum work. The repeated-label pilot's strict-context coverage failure (PR #34) is not a reason to relax identity definitions or relaunch aggregation.

## Fixed causal comparison

1. Pin CPU source `35cb09b`, net10, default search settings and Threads 1. Publish the network/binary hashes, 64 fresh game IDs and their explicit seeds before generation.
2. Generate eight random legal opening plies, then at most 64 searched plies per trajectory with a 1 MB TT and a 5,000-node request. Save full initial state, all played moves and search metadata; do not infer game identity from row adjacency. Freeze assessment roots at zero-based searched-ply indices 8, 24, 40 and 56.
3. Replay the exact same trajectories with 16 MB, searching every preceding ply at the same budget but forcing the recorded moves. Clear TT only at each game's start in both arms. Preserve repetition history and null-distance state. This isolates labels conditional on the same histories; it does not estimate changed self-play trajectories under 16 MB.
4. Define one eligibility mask using the 1 MB trajectory's ordinary datagen filter. Apply that same mask to both arms. Record score, actual nodes, completed depth and best move in each arm, even when the shadow teacher would choose another move.

## Sequential gates and budget

- Require at least 128 eligible assessment roots across 48 games. Otherwise report inconclusive coverage and stop; no sample enlargement.
- Transform consistently oriented scores with `sigmoid(score/400)`. If fewer than 5% of eligible roots differ by at least 0.01, stop this label intervention without deeper searches. Report best-move disagreements separately; the frequency gate is not proof of equal strength.
- Only if that gate is met, search at most 256 eligible roots with a separate cold 64 MB table and a 32,768-node request, using the same own-engine/network and full recorded history. Treat this as a stronger-budget proxy, not chess truth.
- Compare each teacher's squared probability error against that common reference. Average within game, then equally across games. A predeclared bootstrap over game blocks (10,000 resamples, seed 20261025) should report the paired difference and 95% interval. A follow-on label intervention requires at least 2% lower mean error for 16 MB, a positive lower interval bound for `error_1MB - error_16MB`, and no worsening on the frozen `|static_eval| <= 200 cp` subset. If that subset is empty, the confirmation is inconclusive. These are proposed engineering thresholds, not Elo-calibrated thresholds.
- Approximately 50.3M nodes before stopping overhead; cap the whole study at **55M actual nodes, 15 CPU-minutes, 2 GiB, one allocated CPU core and zero GPU time**. If a bound is reached, retain partial artifacts and report inconclusive. Claim and coordinate the core before execution.

## Leakage and interpretation

Keep all audit games out of subsequent training and retain existing stable validation membership. Retain explicit identities/history so the audit's position identities can be excluded from any later training set. Never assign an artificial draw outcome to a truncated trajectory. The study does not train a network and requires no game-result target for its reference comparison.

A pass justifies a separately preregistered student comparison with identical positions, results, weights, initialization and optimizer steps, changing only the teacher labels. Those datasets need actual completed-game outcomes; this truncated audit is not sufficient. A stronger teacher's agreement is a screening signal, and may not improve the student or Elo. Promotion still requires the project's CPU time-control SPRT.

A failure or small difference keeps the efficient 1 MB production choice provisionally supported for this population; it does not prove global equivalence. The source trajectories favor the 1 MB teacher's visited positions, and the deeper proxy shares the same engine's biases. Report those limitations explicitly.
