# Four-day moonshot: what could approach +400 Elo

Documentation only. No engine change, no games, no training, and no GPU job was run for this note. Nothing below is a ChessSI SPRT result. Every Elo band is an unverified planning prior. Bands overlap, so they do not add.

Pinned to [main `ed77fe7`](https://github.com/LupeHiguera/ChessSI/commit/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd), net12, accepted bench **69980** (not rerun). Author: Grok 4.7 (Cursor), 2026-10-29. This file does not claim a row in `docs/IDEAS.md`.

Machines are expected back around 20:40 America/Phoenix on 2026-10-28 (03:40 UTC on 2026-10-29): RTX 5080, RTX 5060 Ti 16 GB, 96 GB RAM, plus an optional second PC that can only play CPU matches. The window used here is the following ~96 hours, through the evening of 2026-11-01 Phoenix.

## Issue #21 comment

Paste from here through the rule.

ChessSI is about 3430 by extrapolation, not by a new gauntlet. The last measured rating is 3284 ± 21 on net10. Reaching +400 in four days is a right-tail outcome, not the plan's median.

Judgment, not a model: about a 4% chance the day-4 binary beats today's main by +400 in one self-play match; about a 12% chance the *sum* of separate SPRT point estimates reaches +400 if overlap is ignored; about 1–2% that a gauntlet moves +400 on the external scale (that would be the mid-3600s to high-3700s from today's anchors). A disciplined run that lands one architecture change and part of the already-drafted search stack is more like +80 to +200 self-play. Under +50 is a live outcome if the architecture screens are flat.

Do not spend the 5080 on another 5,000-node generation of the same 768 network. That slope is the recent +32 to +51 per generation, and the CUDA teacher is still missing main-search SEE, losing-capture ordering, pawn correction, and depth-and-age TT replacement. Stockfish's historical +400 from SF7 to SF14 took five years and Leela labels, which this project does not use.

The stack, in order: (1) on the 5060, a king-bucket feature transformer initialized so step 0 matches net12, screened against a three-layer control and an h512 control on the existing 436M positions; (2) on the 5080, a same-night probe of 5k vs ~40k labels, then either a deep relabel or a parity port of the stale teacher, not both as a four-day 5k run; (3) CPU SPRTs of the open drafts #59 and #60 on the farm, which this note does not restate. Two novel bets sit on top if (1) produces a second net: deep-label only the positions where the two own nets disagree, and a training head that predicts the deep-minus-shallow residual. Full threat inputs and double extensions are real and are not the first jobs. Double extensions wait on #60 and have been negative at short time controls in Stockfish. Viridithas threat inputs were +27 at fixed nodes and +3 at 8+0.08.

No new Elo was measured for this comment. Drafts #59–#68 stay as they are.

## 0. Two Elo numbers, and the chance +400 is real

Self-play SPRT Elo at 10+0.1 is the number `scripts/sprt.sh` reports. External rating is what the Stash gauntlets measured. They are not the same quantity.

| Anchor | What it actually is |
| --- | --- |
| 3284 ± 21 | Last gauntlet, 2026-10-24, net10, 1,200 games at 10+0.1 vs Stash 27–36. [README](../../../README.md), [IDEAS.md](../../IDEAS.md). |
| ~3430 (3400–3460) | Extrapolation. Eight later passes sum to +216 self-play. Earlier gauntlets kept 55% (net8 + SEE: +65 self-play, +36 outside) and 81% (net9 + speed + net10: +133.6 self-play, +108 outside). |
| +400 self-play vs today's main | One match of the day-4 engine against `ed77fe7`. Overlap means this is smaller than the sum of the patches inside it. |
| +400 external | About 3680 from the measured 3284, or about 3830 from the 3430 estimate. Phase 4 in [PLAN.md](../../PLAN.md) is 3400–3500+. Phase 5 is the last 100–200 to Stockfish. |

[Stockfish 14's release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_14) says that engine was at least 400 Elo ahead of Stockfish 7, about 80 Elo a year for five years, and names two causes: billions of positions labeled by Leela, and a larger network that specializes by phase. ChessSI's rule forbids the first cause (no external network, no opponent evaluation). The second cause is the part this window can touch, on 436M own positions rather than billions.

The probabilities below are the author's judgment for scheduling. They are not a fitted model and not a confidence interval.

| Event | Judgment |
| --- | --- |
| Day-4 engine is +400 self-play vs today's main in one match | ~4% |
| Sum of accepted SPRT point estimates reaches +400, overlap ignored | ~12% |
| Gauntlet gains +400 from either anchor | ~1–2% |
| Day-4 engine is at least +150 self-play, if #59/#60 run on the CPU farm in parallel and one architecture screen hits | ~25% |
| Day-4 engine is under +50 self-play | ~35% |

[PR #62](https://github.com/LupeHiguera/ChessSI/pull/62) already set a planning band of +60 to +180 self-play, median about +110, for the drafted search stack plus a same-recipe net13. That band is theirs, it is unverified, and this note does not reopen it. Adding this note's upside to that high end is how a spreadsheet reaches +400. It is also how the same spreadsheet double-counts one better evaluation.

## 1. Already open, leave it alone

| Draft | What it is | This note |
| --- | --- | --- |
| [#59](https://github.com/LupeHiguera/ChessSI/pull/59) | Quiescence TT | CPU-farm SPRT when the box is back. Not restated. |
| [#60](https://github.com/LupeHiguera/ChessSI/pull/60) | Singular extensions with multi-cut | Same. Idea 9 below waits on its result. |
| [#61](https://github.com/LupeHiguera/ChessSI/pull/61) | Continuation history, kept and halved | Not restated. |
| [#62](https://github.com/LupeHiguera/ChessSI/pull/62) | The 2026-10-28 sprint plan | The search spine and the "gen9 at 5,000 nodes" default. This note disagrees with giving gen9 the 5080 for four days. |
| [#63](https://github.com/LupeHiguera/ChessSI/pull/63) | Exchange-witness quiet ordering | Card 5. Not restated. |
| [#64](https://github.com/LupeHiguera/ChessSI/pull/64) | `cutNode`, TT eval, `ttPv`, `improving` | Not restated. |
| [#65](https://github.com/LupeHiguera/ChessSI/pull/65) | LMR stage 1 | Not restated. |
| [#66](https://github.com/LupeHiguera/ChessSI/pull/66) | Internal iterative reductions | Not restated. |
| [#67](https://github.com/LupeHiguera/ChessSI/pull/67) | Capture history | Not restated. |
| [#68](https://github.com/LupeHiguera/ChessSI/pull/68) | History-scaled quiet LMR | Not restated. |
| [#57](https://github.com/LupeHiguera/ChessSI/pull/57) | Ten smaller experiments | Threat *ordering*, pin-aware SEE, helper election, eval cache, castling-right bits, a 32-term product, repetition detection, decorrelation. Useful later. None is a +400 pillar. |
| [#56](https://github.com/LupeHiguera/ChessSI/pull/56) | Recover a move after a repeated refutation fails | A selector inside LMR. Not a pillar. |

Search today, in [`src/search.cpp`](../../../src/search.cpp), already has iterative deepening, PVS, aspiration, a depth-and-age TT, killers, quiet history, null-move, LMR, LMP, futility, RFP, SEE pruning in quiescence and in the main search, losing captures after quiets, check extension with no cap (`++depth` whenever `in_check()`), pawn correction history capped near 64 cp, stability time management, and Lazy SMP that shares only the TT. The network is `(768 → 256) × 2 → SCReLU → 1`. The 768 index is piece-color, piece type, and square ([`feature()`](../../../src/nnue.cpp)). The king is one of those pieces. Castling rights are not an input. There is no second hidden layer, no king bucket, and no attack-pair feature.

## 2. Why the obvious data job is not the +400 job

net12 gained **+32.1 ± 10.8** on 436.4M unique positions, all generation 8, 19% fewer positions than net11, which had gained **+50.7 ± 13.2** on 537.6M. The early doublings were larger (+203, +139, +104, then +43 to +57). A further generation of the same recipe is a +20 to +45 prior, in the neighborhood of those last two steps. It is not a +200 prior, and it is not four of them.

The CUDA teacher is not current main. [`gpu/datagen.py`](../../../gpu/datagen.py) defaults match the accepted tune (RFP depth 5 margin 77, null-move divisor 4, LMR 0.82/1.72, futility 127). [`gpu/datagen.cu`](../../../gpu/datagen.cu) still always-replaces the TT, orders every capture above quiets with no SEE sign, and has no main-search SEE prune and no pawn correction. Those four CPU changes passed at +5.0, +30.4, +24.2, and +18.5. A student does not inherit search Elo one for one. It does inherit the positions and the scores that search produced. Four days of 5,000-node games from that kernel are a large corpus of a weaker teacher's opinions.

Published throughput, net10, 5,000 nodes, RTX 5080: about 13,000 positions/s and 91M nodes/s ([`gpu/README.md`](../../../gpu/README.md)). A full day at that rate is on the order of 10^9 lines. At 40,000 nodes the same box is several times slower; a linear scaling would be roughly 1/8 the positions, around 10^8 lines a day, and launch overhead can move that either way. That 40,000-node figure is an extrapolation, not a measurement. It is enough to say a one-day deep relabel of a chosen 50–100M subset fits, and a four-day shallow dump does too. The scarce resource is which of those the 5080 is allowed to be.

Training capacity is not the wall. net12's host-mode run on the 5060 Ti peaked at 26.2 GB RSS for 436M uniques ([`nets/README.md`](../../../nets/README.md)). The [2026-10-27 follow-up](../research-followup-2026-10-27/REPORT.md) put identified arrays near 21 GB at 500M uniques. 96 GB can hold on the order of a billion packed rows. Filling it with more 5,000-node lines does not by itself buy a new eval.

`gpu/match.py` compares two networks of one size at fixed nodes. A king-bucket net and net12 are different feature layouts, so that match does not rank them until `gpu/nnue.cu` implements the new index. Promotion of a new architecture is a CPU time SPRT either way, because Viridithas already showed a fixed-node gain collapsing at blitz (section 4).

## 3. Shortlist

Rank is judgmental expected self-play Elo, times the chance a go/no-go exists inside 96 hours, times hardware fit. Expected Elo is a central prior, not the upside. Upside is in the idea sections. "Land" means the screen or the SPRT actually runs, not that it passes.

| Rank | Idea | Kind | Lane | Central (band), unverified | P(lands) | Fit | Why it is on this list |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | King-bucket residual, initialized at net12 | Known family, new for this net | B | +30 (−25 to +80) | 0.65 | 5060, existing FENs | The 768 index never names the king. Largest missing eval structure that can train tonight. |
| 2 | Three-layer 768→256→32→1, same features | Known | B | +15 (−20 to +40) | 0.70 | 5060, existing FENs | The control that can steal rank 1, and a real net if buckets are flat. |
| 3 | Deep labels, after a same-night probe | Partially known | B | +20 (−40 to +80) | 0.55 | 5080, exclusive | The only data job whose upside is a new target rather than more of the same target. |
| 4 | Close the CUDA teacher, then raise the node budget | Known | B | +18 (−10 to +40) | 0.45 | 5080, a day of parity | Stops the next billion lines being the old search. Not a moonshot. Blocks a bad gen9. |
| 5 | Sparse attacked-piece features | Known, reduced | B | +12 (−25 to +45 at 10+0.1) | 0.30 | 5060, then CPU | Full threat inputs are a multi-week port. A short feature can still be large, and it can also die on NPS. |
| 6 | Disagreement mining between two own nets | Novel combination | B | +12 (−40 to +70) | 0.35 | Both GPUs, after rank 1 | Concentrates the deep budget on positions the current net and the new net do not share. |
| 7 | Residual head, deep minus shallow | Novel combination | B | +8 (−30 to +50) | 0.50 | 5060, rides on rank 3's file | Asks the hidden layer to represent what extra search finds. Inference use is a second, harsher test. |
| 8 | Nested net: narrow in quiescence, wide above | Novel combination | B, then C if the nest slips | +8 (−25 to +40) | 0.25 | CPU eval + a retrain | The way an h512 result could survive 10+0.1. h512 alone already failed that test once. |
| 9 | Budgeted double extension | Known | A, blocked on #60 | +8 (−20 to +30 at 10+0.1) | 0.25 | CPU farm, after #60 | Largest search-shape item not already drafted. Short-TC history includes losses. |

Lane A is a CPU SPRT that can start the night the box is back. Lane B needs a GPU. Lane C does not finish honestly inside 96 hours. Rank 9 is the only A-lane item, and it is blocked, so the first night of CPU cores belongs to #59 and #60 rather than to a new search patch from this note.

## 4. The stack that has a right tail near +400

Three jobs, three SPRTs, no combined patch.

1. **Eval features.** Rank 1 and rank 2 train on the frozen generation-8 FENs. One winner, one CPU SPRT against net12 in one binary. A pass here is the only single change with a plausible +40 to +80.
2. **Labels.** Rank 3 or rank 4, not a four-day blend of both. The output is a second network, SPRT'd against the winner of (1), or against net12 if (1) failed. A pass here is the second +20 to +60.
3. **Drafted search, already written.** #59 and #60 on the CPU farm, then whichever of #64–#68 the sprint owner runs. [PR #62](https://github.com/LupeHiguera/ChessSI/pull/62)'s median, unverified, is about +110 if several land, with overlap inside that stack already discounted by them.

A clean sweep of those three, with mild overlap between a better net and better search, is the +150 to +250 self-play region. +400 requires the high side of all three at once: buckets near +80, deep labels near +80, and the draft stack near its +180 high, *and* those highs mostly stacking. That is the ~4% cell. Scheduling as if it were the median spends the window on a gen9 dump and a pile of +5 ports.

The second PC, if it appears, plays the net SPRT and one draft SPRT. It does not train. The 5060 trains and can run `gpu/match.py` only for same-architecture pairs (the three-layer net vs net12 is legal there; the bucket net vs net12 is not, until the CUDA feature index exists). The 5080 does datagen or the deep probe, not a second training run, unless the 5060 is blocked.

## 5. Rank 1. King-bucket residual, initialized at net12

**Mechanism.** Index the feature transformer by a king bucket as well as by piece and square. Stockfish's HalfKAv2_hm does this with the king mirrored onto the e–h files and 32 buckets ([`half_ka_v2_hm.h`](https://github.com/official-stockfish/Stockfish/blob/master/src/nnue/features/half_ka_v2_hm.h)). Viridithas's v13.0.0 notes attribute +23.64 ± 8.91 to the new `gestalt` network, described there as more king buckets ([release text](https://github.com/cosmobobak/viridithas/releases)). That is their match for that network, not a ChessSI result, and the changelog line is not an ablation that held every other training knob fixed. The four-day shape is smaller than HalfKA's king×piece×square table: 8 or 16 buckets over the existing 768, factorized as `W[bucket, feature] = W_net12[feature] + U[bucket, feature]`, with `U` starting at 0. At export, add them and ship a dense table. Step 0 then evaluates like net12, because every bucket row is a copy of net12's row. A king move refreshes that perspective. Any other move is still one add and one sub, of the row for the current bucket.

**Why ChessSI.** [`feature()`](../../../src/nnue.cpp) is `side * 384 + piece_type * 64 + square`, with the square flipped for Black. The hidden layer has to build "knight near *this* king" as a conjunction of two 768-features inside 256 SCReLU units. That is the interaction HalfKA writes into the input. ChessSI's own queue already postponed king buckets to ~1B positions. 436M is under that rule of thumb, which is why the residual starts at net12 instead of splitting the data across randomly initialized buckets. If the offsets stay near zero, the export is the old net and the SPRT is unnecessary.

**Prior art.** Known. HalfKA and king buckets are the standard post-2020 NNUE input. The net12-exact initialization is the part that is local to this experiment; low-rank bucket residuals were already proposed for a later data size in the [2026-10-24 report](../novel-elo-ideas-2026-10-24/report.md), as a small gain *on top of* buckets. The jump from no buckets to buckets is the different baseline. Do not quote that report's +3 to +10 as this idea's prior.

**Interactions with #59–#68.** None in the search. Train and SPRT the net on accepted main, not on an untested draft branch, or the net inherits an unmeasured search. Pawn correction will relearn the new net's bias during games; that is not a code conflict. `gpu/datagen.cu` `feat()` is the 768 index. The new net cannot generate generation 10, and cannot play in `gpu/match.py` against net12, until that kernel knows the bucket. CPU `./chesssi` can, as soon as `src/nnue.cpp` does.

**Unverified band.** −25 to +80 at 10+0.1, central +30. The low side is a sparse bucket table that spends capacity on king squares the data barely visits, or a refresh so expensive that time control gives the Elo back. The high side is the 768 net being genuinely king-blind in middlegames. Fixed-node games can read higher than 10+0.1; Viridithas's later threat result is the warning (idea 5).

**Sketch.** `nnue/train.py` (`features`, the packed decode, the module, the exporter). `src/nnue.cpp` `feature()`, `apply()`, and a refresh when the moving piece is a king. Format: bump the magic or a version integer so a 768 file cannot load as a bucket file. Bucket id from the friendly king, mirrored so left and right share buckets, 8 first and 16 only as a second arm of the screen. `gpu/nnue.cu` and `gpu/datagen.cu` are a follow-up port, not a blocker for the CPU SPRT.

**SPRT gate.** Screen first, in [SPECS.md](SPECS.md). Full train only the arm that beats the 768 control on the frozen validation games in both seeds, or the single seed if the night only fits one. Then `make test`, a recorded bench, and `scripts/nnue-sprt.sh` at [0, 5], 10+0.1, Threads 1, both nets in one binary. A fixed-node GPU match is not available across feature layouts. A failed SPRT reverts the engine to net12. Log the row only after the match, in the usual way; this research PR does not log it.

**Fail modes.** Step 0 does not reproduce net12 (the init is wrong; do not train). The screen ties the control (stop; do not full-train a tie). NPS on bench drops more than about 8% and the time SPRT is the only one that counts. The CUDA port slips, so there is no generation-10 from this net inside the window: still a successful experiment if the CPU SPRT passed, and a failed schedule if the plan assumed that data.

## 6. Rank 2. A third layer on the same 768 features

**Mechanism.** Keep the 768 input and the 256-wide SCReLU. Add a small affine plus a clipped ReLU, 256×2 → 32 → 1, in place of the single output dot. Stockfish's current stack is a wide transform, a small second layer, and a third ([`nnue_architecture.h`](https://github.com/official-stockfish/Stockfish/blob/5eeca739/src/nnue/nnue_architecture.h)). Viridithas 14 bundled a three-layer net with more buckets and more width; the release-versus-release Elo is not an ablation, so it is not used here as a number.

**Why ChessSI.** The output is one squared dot product. Piece interactions that are not linear in the squared hidden units have nowhere to go. Output buckets were the previous attempt to specialize that dot, and they failed twice (level with net7 at −0.7 ± 14.7, level with net11 at −0.5 ± 2.8 over 21,824 games). A second layer shares data across phases instead of slicing it. It is also the honest control for rank 1: if a 32-unit layer gains as much as king buckets, the story "we needed king indices" is wrong and the layer is the patch to keep.

**Prior art.** Known. bullet's guidance, cited in the 2026-10-24 report, is to wait for on the order of a billion positions before a second layer. 436M is short of that. The screen exists to obey that warning cheaply.

**Interactions.** Same as rank 1: SPRT on main, and `gpu/match.py` *can* compare this net to net12 if the hidden width stays 256 and the exporter still produces a file the current kernel understands. A new output stack breaks the kernel. Treat the GPU match as unavailable until `nnue.cu`'s propagate matches. CPU SPRT does not care.

**Unverified band.** −20 to +40, central +15. High side requires the 256 units to already contain the features a second layer can mix. Low side is extra latency in an eval that is already a large share of node time, plus a layer trained on too little data.

**Sketch.** `nnue/train.py` module and export. `src/nnue.cpp` `evaluate()`, after the existing SCReLU sum, one 32-wide integer affine. Quantization has to be specified before any game: the current output path assumes `x * w` fits in int16. A second layer that ignores that will not match the trainer.

**SPRT gate.** Same screen budget as rank 1, same validation games, a separate full train, a separate [0, 5] SPRT. Do not ship buckets and a new layer in one file and call it one idea.

## 7. Rank 3. Deep labels, gated by a probe the same night

**Mechanism.** On a frozen list of positions drawn from generation 8, search each twice with net12: the datagen budget (5,000 nodes) and a deeper budget (20,000 or 40,000, chosen before the run). Train a network whose auxiliary target is the deep score, or whose main target replaces the shallow score, against a control trained on the shallow score of the same positions. The positions, the game results, and the train/validation split stay fixed. Only the search target changes.

**Why ChessSI.** The auxiliary head's ablations said a cleaner search target helps the shared layer, and that the head's horizon was not the mechanism: a head on the position's own search score matched a 4-ply head ([IDEAS.md](../../IDEAS.md)). That was the *same* search, heard twice. It does not say a deeper search is a better teacher. The [2026-10-27 follow-up](../research-followup-2026-10-27/REPORT.md) already rejected a confounded "deeper labels are worth +84" extrapolation. This experiment is the unconfounded version: same rows, same results, different teacher depth. Braun's preprint is the fail mode in the literature: a learned allocator improved label agreement and lost 60–100 Elo in play ([arXiv 2609.37447](https://arxiv.org/html/2609.37447v1), as cited in IDEAS.md). The budget here is a frozen depth, not a learned policy.

**Prior art.** Partially known. Viridithas relabels with its own net. Stockfish relabels with Leela, which this project will not do. Soft node caps are Viridithas's datagen practice and were already proposed, without a result, in the [2026-10-26 sprint](../research-sprint-2026-10-26/REPORT.md).

**Interactions.** The probe uses CPU or the 5080, not a draft search branch. Porting #59–#68 into the teacher before they pass mixes two experiments. Rank 4's parity port is the accepted-main search only. Rank 7 consumes this file if the probe says the deep score actually moves.

**Unverified band.** −40 to +80, central +20. The low side is Braun's, or a deep score that is almost the shallow score, so the net fits noise. The high side is the 5,000-node label being the binding error now that another 5,000-node generation is only worth the recent +32.

**Sketch.** A driver around `./chesssi` with `go nodes`, or `gpu/datagen.py` once per budget if the kernel is the teacher (say so in the log; the kernel is the stale one). Columns: fen, shallow score, deep score, result, static eval. Trainer change is which column feeds `--aux` or the main target. No search-code change.

**SPRT gate.** Probe 2,000 positions before any multi-hour relabel. Stop rule, frozen here, before anyone looks at the file: if the median absolute score change on positions whose shallow score is inside 200 cp is under 25 cp, do not relabel. 25 cp is below the 64 cp correction cap and below the scale at which a new target has previously been worth a match; it is still a judgment, not a measured threshold. If the probe passes, relabel a pre-registered 50M subset, train against the shallow control on those same rows, and SPRT [0, 5] at 10+0.1. A GPU fixed-node match is legal only when both nets share the architecture.

## 8. Rank 4. Make the CUDA teacher the accepted search, then spend nodes

**Mechanism.** Bring `gpu/datagen.cu` up to accepted main for four behaviors: depth-and-age TT replacement, losing captures ordered after quiets, main-search SEE pruning, and pawn correction applied to the static eval used by RFP, futility, null-move, and the quiescence stand-pat. Keep the tuned numeric defaults already in `DEFAULTS`. Re-check byte parity against `gpu/ref.cpp` on a few hundred games. Then generate at a soft 15,000-node budget with a hard cap, rather than another hard 5,000.

**Why ChessSI.** Section 2. The alternative is a billion lines of a search that does not contain four passed patches.

**Prior art.** Known. This is a port, not a new search idea. It is on the list because skipping it dominates the data half of the window.

**Interactions.** Do not port #59–#68 into this kernel until each has passed on CPU. A teacher that includes an untested singular extension produces data the project cannot attribute. Rank 3 and rank 4 share the 5080. The probe is a few hours; the port is the rest of a day if it stays inside those four behaviors. If the port is not parity-clean by the end of day 1, abandon it for this window and use rank 3's CPU deep labels. A half-ported teacher is worse than the stale one, because the labels have no name.

**Unverified band.** −10 to +40 for a network trained on the new teacher's games versus a network trained on the same number of old-kernel games, central +18. This is not +5+30+24+18. Search Elo does not transfer into the value net at that rate. The band can also be ~0 if the score scale shifts and the trainer's λ blend eats it.

**Sketch.** `gpu/datagen.cu` (`tt_store`, `score_moves`, the main-search move loop, an eval wrapper). `gpu/datagen.py` if the soft cap needs a flag. `gpu/ref.cpp` as the parity oracle, rebuilt from the same main. `gpu/README.md` only when a measured throughput exists.

**SPRT gate.** Parity first: a few hundred games, line-for-line, as the existing GPU notes require. Then one generation, one train, one [0, 5] net SPRT against net12 or against the rank-1 winner. Do not SPRT "port plus 15k nodes plus a new net architecture" as one row.

## 9. Rank 5. Sparse attacked-piece features

**Mechanism.** Add features for "this piece is attacked", a few hundred to ~768 extra rows, not Stockfish's full piece-to-attacked-piece product. Stockfish SFNNv10 adds Full Threats: active features are pairs whose second square lies in the first piece's attack set, on top of HalfKAv2_hm ([commit `8e5392d`](https://github.com/official-stockfish/Stockfish/commit/8e5392d79a36aba5b997cf6fb590937e3e624e80), [PR #6411](https://github.com/official-stockfish/Stockfish/pull/6411)). This note did not copy a fishtest Elo off that PR. Viridithas PR #425 implemented an SFNNv12-style threat set, excluded king threats, and measured three different regimes: **+27.43 ± 7.91 at 25 knodes**, **+2.98 ± 2.09 at 8+0.08**, **+5.38 ± 2.97 at 40+0.4**, at about 87% of the old speed on AVX-512 ([PR #425](https://github.com/cosmobobak/viridithas/pull/425)). That split is the result that governs this idea.

**Why ChessSI.** The 768 net sees a piece on a square and not the attack bit. SEE recovers tactics inside the search, near the leaves, and pays for them in nodes. A feature pays for them in the eval. ChessSI is far enough from Viridithas's already-bucketed net that the blitz collapse might be smaller. It might also be the same collapse. The experiment's job is to measure the split, not to assume the fixed-node number.

**Prior art.** Known. PR #57 card 1 is threat-*ordering* of quiets, a different and smaller patch. Do not build card 1 and call it this.

**Interactions.** Independent of #59–#68. Incremental attack updates are the whole engineering risk: a move changes attacks far from the moved piece. A full accumulator refresh on every node will lose more NPS than Viridithas's 13% and will not reach a SPRT. King-bucket work (rank 1) touches the same `feature()` and the same exporter. One of the two gets the first full train. The screen can run both; the SPRT cannot.

**Unverified band.** At 10+0.1, −25 to +45, central +12. At fixed nodes, a +20 to +40 reading is compatible with the Viridithas 25-knode result and is not a promotion. The high side of the time-control band is "ChessSI's net had more missing structure than Viridithas's, so the +3 does not apply." That sentence is a hope until the match.

**Sketch.** Trainer feature list from the FEN (attacks are a function of the board; old data is usable). `src/nnue.cpp` refresh of the threat slice. Prefer a design that refreshes threats only when an attack map changes, and fall back to "not this window" if the first bench is more than about 8% slower. No CUDA datagen of this net in the same week unless rank 1's port is already done.

**SPRT gate.** Validation screen against the 768 control. Then bench NPS. If NPS is worse by more than about 8%, require a same-node CPU screen of a few hundred games to be ahead before spending a [0, 5] time SPRT. The time SPRT is the only promotion. A fixed-node win with a time loss is a logged failure of the time test, not a near miss to retune in the same patch.

## 10. Rank 6. Moonshot: disagreement mining

**Mechanism.** Once rank 1 has produced a second net, run both nets over a frozen set of generation-8 positions. Keep positions where the two static evals differ by a margin frozen before the run (start at 80 cp; the number is a proposal, not a measurement). Label the kept set with a deep search from the stronger teacher, the winner of the rank-1 SPRT if it has passed, otherwise net12. Train one new net on the original corpus plus this set, against a control that spends the same GPU time adding ordinary 5,000-node positions.

**Why ChessSI.** Both networks are own networks. The rule against external evals is intact. The 5080 cannot deep-label 436M positions in this window. It can deep-label the slice where two of our own evals already disagree. That slice is exactly where a new feature layout might be teaching something the 768 net missed, or where it is simply wrong. The control separates those.

**Prior art.** The family is known: Lc0 diff-focus and KataGo surprise sampling, already relabeled as known in the 2026-10-24 report. Selecting by the gap between two ChessSI architectures, then paying a deeper own search only there, was not found in this repo's experiments. Call it a novel combination. Braun's negative result still applies if the selector throws away coverage the control kept.

**Interactions.** Depends on rank 1 existing as weights, not on it having passed. Depends on rank 3's deep-search driver. Does not touch #59–#68. Do not mine disagreements between main and an untested draft search; that confounds features with an uncommitted search.

**Unverified band.** −40 to +70, central +12. Central is low because selective data often looks informative and plays worse. The +70 is the moonshot cell: the bucket net is right where the 768 net is systematically wrong, and the deep label agrees with the bucket net. The −40 is the cell where the bucket net is confidently wrong and the trainer imitates it.

**Sketch.** A small Python join over two eval dumps and one search dump. Trainer change is a row weight or an extra file, not a new architecture. If rank 1 never produces weights, this idea does not start. That is likely inside a four-day window only if rank 1's screen finishes on night 0.

**SPRT gate.** Offline, before training: the kept set has to be at least a few percent of the scanned rows and not a single material class. If almost every disagreement is a queen endgame or almost none exist, stop. Then one train, one [0, 5] SPRT against the control network, same architecture, so a GPU fixed-node match can pre-screen.

## 11. Rank 7. Moonshot: a head for the deep-minus-shallow residual

**Mechanism.** On rows that have both scores, add a training-only head that predicts `deep − shallow`, behind a stop-gradient into the output layer so the exported eval still learns the usual blend. Drop the head at export. The existing auxiliary head already predicts a search score. This one predicts only the part the deeper search adds.

A second experiment, not part of the first SPRT: if the head's prediction, on a held-out set, lines up with positions where the shallow search's best move loses to the deep search's best move, *then* a search patch may consult it to refuse an LMR or to widen RFP. That search patch is its own test and should not be written until the correlation exists.

**Why ChessSI.** The policy head failed at every weight because a move target competed with the value target for 256 units. HL-Gauss at weight 0.01 lost −49.3 ± 14.9 for the same reason: the head's loss dominated. A residual in centipawns, with a weight that keeps its loss well under the main loss (the 0.0005 scale the HL-Gauss postmortem already pointed at), is a smaller ask. It is also the natural consumer of rank 3's file.

**Prior art.** KataGo's multi-horizon heads and stop-gradient error heads are the known tools. Using the residual specifically as "what another 8× nodes would change," and only later as an LMR veto, was not found in the ChessSI log. Novel as a combination. The inference veto is the part that could be large, and it is the part most likely to be uncalibrated.

**Interactions.** Training-only, so #59–#68 are untouched. The inference veto collides with #65 and #68, which rewrite LMR, and with #64's pruning flags. Do not stack the veto on an untested LMR branch. If those drafts pass first, the veto's baseline is the new LMR, not today's.

**Unverified band.** Training-only: −15 to +25, central +5. With a calibrated inference veto, the moonshot band is −30 to +50, central +8, and the central stays low because the veto is a second idea that usually does not get to run. The +50 cell is a head that correctly flags tactical positions the static net and the shallow search both miss, so LMR stops skipping them.

**Sketch.** `nnue/train.py` only, for the first experiment. Export unchanged. The veto, later, is a handful of lines in `search()` next to the LMR reduction, behind a UCI option, default off until its own SPRT.

**SPRT gate.** Same validation-loss discipline as the old auxiliary-head screens, on a frozen split, head versus no head, identical rows. Promote only a clear validation win to `scripts/nnue-sprt.sh`. The inference veto's gate is offline: on a held-out set of a few thousand positions it has to beat a trivial rule ("veto when `|shallow score| < 50` and the move is quiet") at predicting deep/shallow move disagreements. If it does not beat that rule, do not play games with it.

## 12. Rank 8. Moonshot: a narrow net in quiescence, a wide one above

**Mechanism.** Train a wide first layer with a nested loss so the first 64 units are themselves a legal network (a Matryoshka / nested dropout on the accumulator). Quiescence and depth-1 nodes evaluate the 64. The main search evaluates 256 or 512. h512 on net10's data was inconclusive at **+3.4 ± 4.8 over 8,116 games**, about 40% slower, and was stopped ([IDEAS.md](../../IDEAS.md)). The 2026-10-24 report's speed model said a 40% slower net needs on the order of +24 to +34 Elo of eval just to break even. That model is theirs, and it matches the decision to stop.

**Why ChessSI.** Width is the lever the project keeps almost reaching. It has never been given a deployment that avoids paying the width in the leaves, where most nodes are. A nested 64-wide quiescence eval is the combination that would make a measured fixed-node gain survivable at 10+0.1.

**Prior art.** Nested nets are a known compression trick. The 2026-10-24 report already called a nested accumulator a novel combination for NNUE and put a small prior on it (−5 to +10). The prior stays small. The reason to keep it is the h512 autopsy, not a new claim of a large central Elo.

**Interactions.** Changes `evaluate()` and therefore every pruning margin that was SPSA-tuned in net12's centipawns. A gain can be "the leaves are noisier and RFP fires differently." That is legal, and it is one idea only if the margins stay frozen. Retuning margins in the same patch is a second idea. No interaction with #59–#68 except that a different eval scale changes how often their pruning fires. SPRT on main first.

**Unverified band.** −25 to +40, central +8. Upside +40 is "h512 was worth ~30 at fixed nodes on 436M data, and the nest saves the NPS." That fixed-node worth is not established. The 64.6M-position sweep showed h512 almost tied h256 on validation while being much slower.

**Sketch.** `nnue/train.py` nested loss. `src/nnue.cpp` `evaluate(width)` or a second call path from `qsearch`. Bench will change. Record nodes and NPS.

**SPRT gate.** This is lane C if the nest is not bit-agreed between trainer and `nnue.cpp` within a day, because a quantization mismatch here is a silent eval bug. If the export parity is clean, the gate is a fixed-node comparison of wide-everywhere versus nested, same weights, then a time SPRT only for the nested binary against net12. A wide-everywhere binary that loses on time is the expected h512 repeat and should be logged as that, not debugged into a third architecture inside the window.

## 13. Rank 9. Budgeted double extension, only after #60

**Mechanism.** When singular search (the mechanism in #60, not re-specified here) finds the TT move is the only one that holds, extend it by two plies instead of one, and count the extension. Cap the number of double extensions on a path. Also count the existing unconditional check extension toward the same cap. Today's search does `++depth` on every checked node with no limit ([`search()`](../../../src/search.cpp)). A second extension system stacked on an uncapped check extension is how a tree explodes at 10+0.1.

**Why ChessSI.** It is the largest search-shape change that is not already a draft. Singular without a double extension was the smaller half of that family in amateur engines. The [2026-10-24 report](../novel-elo-ideas-2026-10-24/report.md) quotes Alexandria commit `b7129ca` at +13.72 ± 6.14 for double extensions. That is an Alexandria measurement, not a ChessSI one, and it is not +80.

**Prior art.** Known. Stockfish's "tweak doubly singular" patch passed STC and LTC with tight positive bounds ([`ff3fa0c`](https://github.com/official-stockfish/Stockfish/commit/ff3fa0c664a5799e5531b0908018c59633d761bf)). Later "do more singular extensions" patches were negative at STC: **−8.27 ± 2.5** over 20,000 games ([PR #4016](https://github.com/official-stockfish/Stockfish/pull/4016)) and **−2.49 ± 1.7** over 40,000 games ([`78532af`](https://github.com/official-stockfish/Stockfish/commit/78532af9dc585a81730d5d28763cc9d5273f96d1)), while passing longer tests. ChessSI's promotion time control is the short one. A patch that needs 60+0.6 to show up does not belong in a four-day blitz sprint unless the 10+0.1 pre-screen is already non-negative.

**Interactions.** Blocked on #60. Conflicts with #66 (IIR reduces depth when the TT move is missing; extensions increase it when the TT move is singular). Do not test both in one binary. #65 and #68 change the reduction this extension skips. If they land first, rebase; do not mix the Elo.

**Unverified band.** −20 to +30 at 10+0.1, central +8. The negative cell is the Stockfish STC result. There is no honest +80 cell at this time control.

**Sketch.** A counter on the search stack in `src/search.cpp`, next to #60's extension site. One constant for the cap (start at 3, do not tune it in the same patch). `make test`. Bench will change; record it.

**SPRT gate.** #60 has passed [0, 5] first. Then a pre-screen. A clearly negative pre-screen stops the idea, the way a clearly negative Stockfish STC should have warned us. A non-negative pre-screen goes to [0, 5] at 10+0.1, Threads 1. No LTC hunt inside this window.

## 14. Lanes

**A. CPU, the night the box is back.** #59 and #60, which are already written. Rank 9 only after #60 passes, and only if the farm is free. This note does not add a second search draft to that night. Threads 1. One draft per machine so two untested searches do not share a binary.

**B. GPU, same night through day 4.** Night 0, 5060: the rank-1 / rank-2 / h512-control screen on a frozen 32M-row slice, two epochs, two seeds if they fit, otherwise one seed and the second seed only for the leader. Night 0, 5080: the rank-3 probe of 2,000 positions, then either the rank-4 parity port or the start of the relabel, not a 5,000-node gen9. Day 1: full train of the screen leader on the 436M; finish the probe's decision. Day 2: CPU SPRT of that net on the farm or the second PC; 5080 does the relabel or the first clean datagen from the ported teacher. Day 3: rank 6 and rank 7 only if their inputs exist; otherwise a second seed of the leader, not a new idea. Day 4: the second net's SPRT. A gauntlet only if some net has passed, against opponents above 3400, and the gauntlet is a measurement, not a +400 claim.

**C. Not inside 96 hours.** Full SFNNv12 threat products (tens of thousands of features, incremental updates, a CUDA rewrite, and a data requirement ChessSI does not have). A from-scratch HalfKA at SF width. An h512 or h1024 deployed on every node, given the 8,116-game stop. A second generational loop after generation 10 (train, datagen, train again). Syzygy as a self-play plan: UHO games rarely reach them, and they do not move the SPRT that decides these patches. Anything that needs Leela labels or another engine's eval.

## 15. What not to try

These are burned, already drafted, or too small for this target. Several are still worth doing on a quiet week.

- The bodies of #59–#68, including qs-TT, singular, continuation history, capture history, the plumbing flags, LMR stage 1, IIR, history-scaled LMR, and the exchange witness.
- PR #57's ten cards as the work program of this window. Threat ordering, pin-aware SEE, an eval cache, castling-right bits, a 32-term product, and upcoming-repetition detection are real and small.
- PR #56's refutation retry as a pillar.
- A four-day generation 9 at 5,000 nodes on the current CUDA kernel. [PR #62](https://github.com/LupeHiguera/ChessSI/pull/62) lists it. This note's disagreement is only about the 5080's time. A short gen9 as a fallback corpus, after the deep-label probe has failed, is consistent with both.
- HL-Gauss at weight 0.01, **−49.3 ± 14.9**. Mirror augmentation, **−18.2 ± 9.2**. Result-gradient routing with the auxiliary head, **−34.5 ± 12.4**. A policy head on the shared layer, worse validation at every weight. Eight output buckets, twice, about zero. `--lambda 1.0`, **−80.4 ± 18.7**. Check evasions in quiescence, **−11.8 ± 8.4** on the pre-NNUE engine. History kept with no decay, failed its pre-screen. Continuation history that reset every search, failed its pre-screen (the retry is #61). Correction history keyed by accumulator sign bits, failed the offline gate where the eval error is small. h512 everywhere, stopped at +3.4 ± 4.8 because of speed.
- Material correction as a +400 item. Pawn correction passed at +18.5 ± 7.9. Another key is a follow-on in the existing queue, on the order of the extra Stockfish keys, not a new net.
- "More extensions" without a cap, and any singular-margin tweak whose justification is a long time control. Section 13.
- Vine self-play as a pillar. The 2026-10-24 central prior was about +8, with a stated upside to +25. The disagreement probe is cheap and can run if both GPUs are idle. It is not this stack.
- Counting Lazy SMP's +129 for 4 threads against 1 thread. That is scaling inside one binary, already measured, not a patch, and the SPRTs that decide this window are Threads 1.
- A factorial of the moonshots. The project rule is one idea per SPRT because interactions have changed sign before (history, LMP).
- External data. A Stockfish-14-shaped leap that depends on Leela labels is out of bounds for this repository, not merely deferred.

## 16. Reading the result on day 4

Write down, before the first SPRT of a net from this note returns, which of these sentences is allowed:

- A passed [0, 5] row is that patch's Elo, with its error bar and its game count, in `docs/IDEAS.md`, by whoever ran it.
- A sum of those rows is not the strength of the combined engine.
- A gauntlet is the external number, and the historical retention is 55–81%, so a +150 self-play engine can be a +80 to +120 rating engine.
- +400 is a result only if a match against today's main, or a gauntlet anchored at 3284, actually shows it. The planning bands in this file cannot be quoted as the engine's gain.

The median of this schedule, if it is followed, is one architecture decision and one label decision, plus whatever #59 and #60 do on their own. That is a successful four days even when the sum is far from +400.
