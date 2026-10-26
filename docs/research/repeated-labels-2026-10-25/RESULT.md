# Repeated-label pilot: inconclusive coverage

Date: 2026-10-25. Owner: GPT-6 (Codex); analyzer implementation and independent review: GPT-6 Astra ultra.

**Decision: stop this bounded pilot for insufficient comparable repeats.** The frozen two-million-row sample contains one eligible full-context position across three conservative groups. The protocol requires at least 500 identities, 200 groups and 0.5% coverage. No trainer change, GPU training, match or Elo result follows from this screen.

## Population and provenance

Source and compiled network: ChessSI `35cb09b`, net10-h256, 5,000 requested nodes per move, eight random opening plies. Thirteen original generation-7 writers, seeds 9291611100 through 9291611112, supplied equal prefix allowances: 153,847 rows for the first two, 153,846 for the other eleven. All two million records were captured.

Before examining label values, `freeze.py` recorded the launch script, runtime writer arguments, open output descriptors, inode metadata, binary/network hashes, and archived source hashes. Archived Makefile/source files matched the pinned worktree after line-ending normalization; network bytes and running executable hashes matched. Bounded snapshots, exact offsets and SHA-256 hashes were frozen before analysis. Claude's original files remained read-only.

The current net10 generation is the latest documented cohort. Historical generation-6 launch budgets could not be established from the available records, so the protocol-permitted latest-only allocation was fixed in advance. F versus L / teacher refresh is omitted. This is a prefix study, not an estimate of the entire training corpus.

The frozen [protocol](PROTOCOL.md) is an exact snapshot of PR29's controls; its original research-only status paragraph is historical. This result supersedes that execution status for this pilot.

## Fixed gates and observed coverage

| Measure | Observed | Required |
| --- | --- | --- |
| Raw records / writers | 2,000,000 / 13 | At most 2,000,000 |
| Complete conservative groups | 20,995 | Not exact game identities |
| Excluded final groups / rows | 13 / 746 | Exclude each range's unfinished group |
| Retained clock-zero rows | 536,452 | Context filter fixed before analysis |
| Distinct first-four-FEN keys in all raw rows | 1,933,340 | Coverage denominator |
| Eligible exact six-field FEN identities | **1** | At least 500 |
| Held-out groups for eligible identities | **3** | At least 200 |
| Eligible distinct-key coverage | **0.000051724%** | At least 0.5% |
| Positive reporting bins | 3 of 5 | At least 4 of 5 |
| Writers with at least 100 eligible identities | 0 | All qualifying writers positive |

The writer condition is vacuous here; it is not positive evidence. The three populated bins describe the same sole identity, not independent replications.

Broader repeats exist: 27,538 four-field keys repeat, and 11,504 occur in at least three complete groups. Among repeated keys, 25,717 have different halfmove clocks and 27,236 have different absolute plies. Those broader populations are descriptive; they were not substituted into the primary comparison after the result.

## Error diagnostics, with their limits

The sole eligible FEN is `8/8/8/8/8/4K3/6k1/5q2 w - - 0 72`: king versus king and queen. Three held-out observations produce MSE(L) = 2.06141101498e-06 and MSE(M) = 1.02985387363e-06. Their approximately 50% relative difference says nothing reliable about population denoising or playing strength.

Outcome-error and cross terms are zero in this case; the variation is entirely in search-score targets. The blend identity `MSE_y = 0.5625 E[e_q^2] + 0.0625 E[e_r^2] + 0.375 E[e_q e_r]` reconciles for both arms. Each identity receives one weight after averaging its held-out-group errors.

All two million static fields were checked within the same sample. There were 1,933,311 board/side input identities and **zero nonzero static-score ranges**. This supports consistency within sampled inputs; it is not a proof of inference correctness in every position.

## Execution and checks

The completed analysis ran on CPU 19 under a hard 2 GiB address-space limit and 900 CPU-second ceiling. It took 254.68 seconds wall time and 75.14 CPU seconds; reported peak RSS was 669.48 MiB. No GPU was used.

The first attempt was interrupted during ingestion because 32 MiB cache and 5,000-row commits caused heavy DrvFS I/O. No result metrics had been inspected. Its source and interruption record are preserved. A runtime-only retry used a 512 MiB cache, synchronous NORMAL and one commit per verified writer. The same hashed prefixes, ordering, formulas and gates were reused; the sample was not expanded.

Validation: all 15 synthetic analysis tests passed before and after the runtime change. Repository checks passed (35 perft and 17 search-boundary cases, zero failures), and the unchanged engine bench was **158506**. Code review checked whole-group exclusion, equal identity weighting, Black orientation, the coverage denominator and metadata separation. Independent review agreed with the stop decision.

## Evidence and reproduction

- [Frozen manifest](evidence/manifest.json), [pre-analysis plan](evidence/plan.json).
- [Machine-readable result](evidence/summary.json), [per-identity errors](evidence/per_identity.jsonl), [validation](evidence/validation.json).
- [Artifact hashes](evidence/artifacts.json), [interrupted-attempt record](evidence/interruption.json), [original analyzer](evidence/analyzer-v1.py).
- `engines/repeated-labels-20261025/` retains the snapshots, both attempt directories, SQLite database and full static-range output locally. Large derivatives are not committed.

Run from this worktree after supplying the immutable snapshots at the manifest paths:

```sh
taskset -c 19 python3 -B -m unittest discover -s docs/research/repeated-labels-2026-10-25 -p test_analyze.py
taskset -c 19 prlimit --as=2147483648 --cpu=900 -- python3 -B docs/research/repeated-labels-2026-10-25/analyze.py engines/repeated-labels-20261025/manifest.json engines/repeated-labels-20261025/reproduction
```

The output directory must be new. Verify hashes before comparing results; moving snapshots requires an explicitly recorded manifest-path adaptation.

## Consequence

This closes the current pilot as **Inconclusive (coverage)**. It does not show that averaging is harmful or useless, and it supplies no training promotion. Do not enlarge this sample or relax clock/ply/teacher matching to rescue it. Any broader-context proposal must state a different hypothesis and controls before another experiment.
