# Specs for the four-day moonshot note

Companion to [REPORT.md](REPORT.md). Procedures only. No result in this file is a measurement. Thresholds marked "frozen" are pre-registered judgments from that note; change them before the run, not after seeing the outcome.

Pinned engine: main `ed77fe7`, net12, bench 69980. Own games and own searches only.

## S0. Common rules

- One mechanism per SPRT. A king-bucket net with a new layer and a deep target is three experiments.
- `make test` prints `0 failed` before any match.
- Search patches record `./chesssi bench`. Nets record the bench of the binary they ship in.
- Promotion is `scripts/sprt.sh` or `scripts/nnue-sprt.sh`, bounds [0, 5], 10+0.1, Threads 1, against the last accepted engine (or against the named control net in one binary).
- `gpu/match.py` is a screen for two files of the same feature layout. It does not promote, and it does not compare a bucketed net with net12.
- Log a row in `docs/IDEAS.md` only after a real match, with the model that ran it. This research PR does not add a row.
- Failed code reverts. The log row stays.

## S1. Night-0 architecture screen (ranks 1 and 2)

**Data.** A frozen 32M-row slice of generation 8, whole games kept intact, the stable per-game validation split. The same files, the same seed list, and the same trainer revision for every arm. Do not redraw the split per arm.

**Arms.**

| Id | Network | Init |
| --- | --- | --- |
| C0 | Today's 768 → 256 → 1, auxiliary head on, the net12 recipe | Fresh, seed listed below |
| K8 | 8 king buckets × 768, factorized, folded at export | `W0` copied from net12's int16 rows, dequantized; bucket offsets `U = 0`; output copied from net12 |
| K16 | Same with 16 buckets | Same |
| L3 | 768 → 256 → 32 → 1, no buckets | Feature transformer copied from net12; the new layer's weights start at 0 so step 0 matches net12's dot product plus a zero residual, or are trained from a fresh init if that constraint is impossible to state exactly. Say which in the log |
| H5 | 768 → 512 → 1 | Fresh. This is the speed control, not a deployment candidate by itself |

Seeds: 1 and 2. Epochs: 2. Batch and λ: the net12 recipe (`--lambda` left at the trainer default 0.75, `--aux-weight 1.0`, `--future-plies 4`, `--gpu-data-gb 0`). If both seeds do not fit before morning, run seed 1 on every arm and seed 2 only on the leader and on C0.

**Step-0 check for K8, K16, and L3.** On 1,000 held-out FENs, the integer eval matches net12 within 1 cp on every position. A miss means the initialization is wrong. Do not train that arm.

**Bucket id.** Friendly king. If its file is a–d, mirror the square with `^ 7` first, so the king is treated as standing on files e–h. K8 is that file (4 values) times a rank band (ranks 1–4 vs 5–8). K16 is that file times four rank pairs (1–2, 3–4, 5–6, 7–8). Write this formula next to the code. Do not try a second layout in the same screen.

**Leader.** Lowest validation loss on the shared split, and the loss must beat C0. A tie with C0 does not full-train. K8 and K16 count as one family: full-train the better bucket count only.

**Full train.** The leader only, on the full generation-8 unique set net12 used (436,375,660 uniques, same files as [`nets/README.md`](../../../nets/README.md)), 20 epochs, seed 1, same auxiliary settings. Then a CPU [0, 5] SPRT against net12.

**NPS.** Bench the leader. If nodes per second are worse than net12 by more than about 8%, the time SPRT is still the promotion test, and a fixed-node lead alone does not ship it.

**CUDA.** Not required for S1's CPU SPRT. Required before this net generates data or enters `gpu/match.py`.

## S2. Deep-label probe and relabel (rank 3)

**Probe, before any long job.** 2,000 positions, one per game, from generation 8, ply at least 16, not in the validation games of S1. For each, with net12, a cleared or identically seeded TT, and the same cold history:

- score at 5,000 nodes
- score at 40,000 nodes (the deep budget; do not change it after looking)

Record fen, both scores, static eval, result if the row has one.

**Stop, frozen.** On the subset whose 5,000-node score is inside ±200 cp, if the median absolute difference between the two scores is under 25 cp, do not relabel. Report the median and the correlation anyway.

**Relabel, only if the probe continues.** 50M positions, whole games, disjoint from S1's validation games. Store shallow score, deep score, result, static eval. Two trains, same rows, same seed, same epoch count:

- T_shallow: main target uses the 5,000-node score, as today
- T_deep: main target uses the 40,000-node score, result blend unchanged, or the auxiliary head uses the deep score and the main target stays shallow

Pick one of those two contrasts before training and do not run both as a single claim. The recommendation is the auxiliary-head contrast, because it keeps the exported target's blend comparable. Say which one in the log.

**Promotion.** GPU fixed-node match only if the architecture matches. CPU [0, 5] against the control net either way.

## S3. CUDA teacher parity (rank 4)

Port into `gpu/datagen.cu`, and nowhere else, these accepted-main behaviors:

1. TT replacement by depth and age, matching `src/tt.cpp` on current main.
2. Captures with SEE < 0 ordered after quiets, matching `score_moves`.
3. Main-search SEE pruning with the margins in `src/search.cpp` (`-60 * depth` quiets, `-30 * depth * depth` captures, depth ≤ 6).
4. Pawn correction history applied inside the static eval that RFP, futility, null-move, and quiescence stand-pat read. Helper state can be per game. The table does not need to persist across games for datagen.

Leave #59–#68 out. Leave the numeric `DEFAULTS` in `gpu/datagen.py` as they are (they already match the tune).

**Parity.** Rebuild `gpu/ref.cpp` from the same main. A few hundred games, same starts, line-for-line, as `gpu/README.md` already requires for a teacher change. A mismatch blocks datagen. Do not "fix" parity by weakening the CPU reference.

**Then.** One soft-cap generation, 15,000 nodes soft, hard cap at least 2×, only after parity. Train one net. SPRT it as its own row against net12 or against the S1 leader, not against a mixture.

If parity is not clean by the end of day 1, stop S3 and spend the 5080 on S2.

## S4. Disagreement mining (rank 6)

Starts only after K8 or K16 weights exist.

**Scan.** 100M generation-8 positions, or whatever fits in an hour of the 5060. Both static evals, net12 and the bucket net, same FEN.

**Keep.** Absolute eval gap at least 80 cp. Frozen. If the kept fraction is under 2% or over 40%, stop and report the histogram instead of training. If more than about 70% of the kept rows share one material class (same piece counts), stop; the selector collapsed.

**Label.** Deep search, budget from S2, teacher = the S1 SPRT winner if that match has passed, otherwise net12. Cap the labeled set at the number of positions the 5080 can finish in one day. Write that cap down before the scan.

**Control.** A second set of the same size, drawn at random from the scanned rows, labeled at 5,000 nodes, same teacher. Same added training time.

**Train and SPRT** one architecture, the S1 leader's, [0, 5], control vs mined.

## S5. Residual head (rank 7)

Uses S2's file. Training only.

- Head reads the accumulator after a stop-gradient.
- Target is `deep − shallow` in the trainer's sigmoid space or in centipawns, chosen before the run. Centipawns are easier to weight.
- Weight such that the head's contribution to the loss is under one fifth of the main loss on the first epoch. The HL-Gauss failure mode was a head several times the main loss. Do not set the weight by fishing on the validation games.
- Export drops the head. A byte-level check that the exported file matches a no-head export of the same backbone is not required; a check that inference code ignores the head is.

**Validation.** Head vs no-head, identical rows, two seeds, the shared split. Promote to a net SPRT only if both seeds improve the main validation loss. A head that helps its own loss and hurts the main loss is a failure.

**Inference veto, separate spec, do not start in this window unless S5's net has already passed and the farm is idle.** On 4,000 held-out positions with both a shallow and a deep best move, the head (or a scalar derived from it) has to beat the rule "the shallow score is inside ±50 cp and the move is quiet" at ranking positions where the two searches disagree on the best move. If it ties or loses to that rule, no search patch.

## S6. Nested width (rank 8)

Do not start until S1's H5 arm has a validation number. If H5 is not clearly better than C0 on validation, skip S6 for the window. The nested deployment exists to rescue a width that is good and slow, not to rescue a width that is tied.

If it starts:

- Nested loss on the first 64 units so they form a complete eval.
- `qsearch` calls the 64. `search` at depth ≥ 1 calls the full width.
- Quantized eval of the 64-prefix matches the trainer's 64-prefix on 1,000 FENs before any game.
- Margins stay at the accepted SPSA values. No retune in this patch.
- Time SPRT against net12. Also record NPS. A fixed-node win with a time loss is a loss of the promotion test.

## S7. Double extension (rank 9)

Starts only after #60 has passed a [0, 5] SPRT on its own.

- When #60's singular condition holds, extension is 2 instead of 1, unless the path already has 3 double extensions.
- The existing `++depth` on an in-check node counts as one extension toward a path cap of 6 total extra plies, so checks and double extensions share a budget. The numbers 3 and 6 are the frozen starting constants. Do not SPSA them in the same patch.
- `make test`. Bench recorded. Pre-screen. A clearly negative pre-screen stops the work. Otherwise [0, 5] at 10+0.1, Threads 1, against the #60 binary, not against a pile of other drafts.

## S8. What the 5080 is forbidden to do on night 0

- A multi-day `gpu/datagen.py` run at 5,000 nodes with the current kernel.
- Training a second full network while the 5060 is already training S1 (the 5080 is the datagen device; the 5060 is the trainer, matching how net12 was trained).
- A teacher kernel that contains untested code from #59–#68.
