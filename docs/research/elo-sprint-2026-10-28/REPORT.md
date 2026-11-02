# ChessSI Elo sprint research — 2026-10-28

Documentation only. No engine change, no games, no training, and no GPU job was run for this report.

Pinned to [main `ed77fe7`](https://github.com/LupeHiguera/ChessSI/commit/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd) (`src/search.cpp`, 623 lines, net12, accepted bench **69980**, not rerun). This file incorporates an executor draft written the same day and checks it against that tree, the open drafts, [docs/IDEAS.md](../../IDEAS.md), the [ten-ideas report](https://github.com/LupeHiguera/ChessSI/blob/astra/ten-ideas-20261028/docs/research/ten-ideas-2026-10-28/REPORT.md) (PR #57), the [2026-10-24 ten-ideas-of-record report](../novel-elo-ideas-2026-10-24/report.md), and a read of tag [`sf_17`](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp) on 2026-10-28.

**Every Elo figure below is a planning prior.** None of it is a ChessSI measurement. Items overlap, so they do not add. The sprint band is **+60 to +180 self-play Elo, median about +110**. Reaching +200 needs the high end of both the search stack and net13. That is a stretch outcome, not a forecast the project can quote as a result.

Author: the executor draft, reconciled in this file by Grok 4.7 (Cursor). The items are unclaimed proposals. This PR does not write names into the queue in `docs/IDEAS.md`.

## 0. Decisions

The strength spine, in order:

1. **Plumbing PR.** Thread `cutNode`, a TT-PV bit, the static eval stored in the TT, and `improving`. No other search decision changes. Eval reuse is the only intended behaviour change.
2. **LMR rework.** Cut-node, TT-PV, improving, a wider gate, checks no longer exempt, and the deeper/shallower re-search. History term left at zero.
3. **Continuation history and capture history**, built from [`claude/conthist2`](https://github.com/LupeHiguera/ChessSI/tree/claude/conthist2), then fed into LMR as one stat score.
4. **net13**, after that spine is at least in test. Generation-9 datagen on the 5080 runs in parallel from the moment the machines are free. The net13 match does not jump the queue.

Already open. Do not reimplement them, and do not start a second copy:

| Draft | What it is | Sprint slot |
| --- | --- | --- |
| [PR #59](https://github.com/LupeHiguera/ChessSI/pull/59) `cursor/qs-tt-1639` | Quiescence probes and stores the TT. Bench reported there as 63652 at depth 7. Elo untested. | **PC1** SPRT `[0, 5]` at 10+0.1, Threads 1 |
| [PR #60](https://github.com/LupeHiguera/ChessSI/pull/60) `cursor/singular-extensions-da4b` | Singular extensions with multi-cut, ported from `claude/singular` (`549cd44`). Depth-7 bench reported there as 69980 because the extension starts at depth 8. Elo untested. | **PC2** SPRT `[0, 5]` at 10+0.1, Threads 1 |
| [PR #57](https://github.com/LupeHiguera/ChessSI/pull/57) card 5 | Research card only: quiet defenses selected by an exchange witness. No implementation PR was open while this report was written. | Offline gate only. No SPRT cores until card 1 / threat history has a result |

PR #60's text says to wait for card 5 before the singular match. This sprint does not. Card 5's own gate already requires card 1 as the control, and the strength track spends those games on #59, #60, the plumbing, and the LMR rework. If a card-5 implementation branch appears from an agent already in flight, leave it alone. Do not open another one, and do not put it on the SPRT farm ahead of card 1.

Machines, when the heat pause recorded on #59 and #60 lifts (both drafts say the PC is off; this report starts nothing):

- **RTX 5080:** generation-9 datagen, and nothing else that would stop it.
- **RTX 5060 Ti:** network screens and SPSA. It does not pre-screen #59 or #60. `gpu/match.py` plays the kernel in `gpu/datagen.cu`, which has neither quiescence TT stores nor singular extensions.
- **PC1:** SPRT of #59.
- **PC2:** SPRT of #60.

## 1. What main has, and what the large LMR terms need

Current late-move reduction, [src/search.cpp](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/search.cpp#L384):

```text
depth >= 3 && legalMoves > 4 && quiet && !inCheck && !childInCheck
r = int(0.82 + ln(depth) * ln(legalMoves) / 1.72)   // table, both axes capped at 63
if (pvNode) r -= 1
r = clamp(r, 0, depth - 2)
re-search at full depth when the reduced score > alpha
```

There is no `cutNode` argument, no PV bit in the TT ([src/tt.h](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/tt.h)), no static eval in the entry, no eval stack, and no `improving` flag. Quiet history is `int history[2][64][64]`, bonus `min(depth², 1239)`, gravity toward ±16384, and the `Searcher` is rebuilt on every `go`, so the table dies with the move. Capture history does not exist. The default hash is 16 MB ([src/uci.cpp](https://github.com/LupeHiguera/ChessSI/blob/ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd/src/uci.cpp)).

The history rows below landed near zero. That is the reason to build the missing state before another history tweak, not a verdict that history terms are useless. The same log is why a term can change sign when the baseline changes: the history heuristic went from −2.7 ± 4.7 to +60.4 ± 16.1 once LMR existed.

| Test | Result in [docs/IDEAS.md](../../IDEAS.md) | Why it bears on this sprint |
| --- | --- | --- |
| Improving flag in LMR only | Inconclusive, +6.7 ± 13.9, 940 games, stopped | `improving` had no other consumers and no eval stack |
| Continuation history, tables cleared every `go` | Pre-screen failed, −2.9 ± 18.1, 600 games | A 2 MB table cannot warm up inside one 10+0.1 search |
| History kept with no decay | Pre-screen failed, −9.9 ± 18.5, 600 games | Persistence without a fade was the wrong fix |
| History halved between searches | Inconclusive, +0.7 ± 2.7, 19,978 games, stopped for net12 | At most about +3. `claude/conthist2` still stacks on this |
| LMR reduced by butterfly history / 8192 | Inconclusive, +0.4 ± 2.3, 28,070 games, LLR −2.06 | At most about +2.7. Butterfly alone, on quiets only |

Together the last two rows are the 48,048 games the ten-ideas report counts. Do not spend another capped SPRT on butterfly-only LMR.

Priors from engines at a similar rating live in the [2026-10-24 report](../novel-elo-ideas-2026-10-24/report.md), measured by Stash and Alexandria at 8+0.08 or 10+0.1, not by ChessSI:

| Missing piece | Measured elsewhere | What ChessSI already took |
| --- | --- | --- |
| Quiescence TT, probe and store | Stash +35.68 ± 13.22 and a second store gain the ideas log quotes as +28.5 | Two failed tries (−19.7 ± 19.3 probe-only; −18.3 ± 26.1 probe-and-store on an always-replace table, no prefetch). #59 is the retest on depth-and-age replacement |
| Singular, then double extensions | Stash +5.91 ± 4.38 at 10+0.1, +13.50 ± 6.87 at 60+0.6; Alexandria double extensions +13.72 ± 6.14 | #60 is one-ply singular plus multi-cut. It does not add double or triple extensions |
| Continuation, capture, countermove | Alexandria capture history +8.71 ± 4.67; Stash countermove +6.07 ± 4.51, continuation +6.06 ± 4.51 | Continuation failed while the table was cleared every move |
| Cut-node and history LMR, improving LMP, SEE | Alexandria cut-node LMR +5.54 ± 3.54; Stash improving LMP +16.20 ± 8.08; Stash SEE +9.94 ± 6.21 | SEE in the main search passed here at +24.2 ± 9.3. Cut-node LMR and improving LMP have not |
| IIR | Alexandria +7.77 ± 4.38 | Ready as a one-line depth reduction on `claude/iir`, not yet rebased onto this main |

Stockfish 17's own parentheticals ("~4 Elo" on the cut-node term, "~8 Elo" on the history term, "~117 Elo" on LMR as a whole) are Stockfish's comments at Stockfish's strength. They are cited in [§8](#8-sf_17-check) so the shape is sourced. They are not ChessSI priors and they are not additive with the Stash rows.

## 2. Plumbing, then the LMR rework

### 2a. Plumbing

One PR. The search function gains `bool cutNode`. A per-ply stack carries `staticEval`, the move, a continuation-history pointer (null until §3), `ttPv`, and `statScore` (0 until §3).

Call convention from the `sf_17` call sites in §8, not from the executor draft's shorter table. The draft passed `!cutNode` into the null-move child and `true` into every later zero-window. The tag does neither.

| Call | `cutNode` passed to the child |
| --- | --- |
| Root, and any PV search | `false` |
| First move at a non-PV node | `!cutNode` |
| Reduced LMR probe | `true` |
| Full-depth zero-window re-search after that probe | `!cutNode` |
| Zero-window when LMR is skipped | `!cutNode` |
| Null-move child | `false` |

`ttPv` for the node is `pvNode || (tte && tte->ttPv)`. Store it on the existing end-of-node `TT.store`. Do not add Stockfish's early eval-only store (`DEPTH_UNSEARCHED`, bound none): that write changes replacement, so it is outside a plumbing PR.

`improving`, computed and unused in this PR, follows the `sf_17` control flow rather than a hand-rolled fallback:

- In check, `improving` is false. The node's stored static eval is copied from two plies above, which is how `sf_17` carries the last real eval through a check.
- Otherwise `improving = staticEval > stack[ply - 2].staticEval`.
- A node that was in check already copied its eval from further up, so the comparison walks back without a separate "if both were checks, improving = true" rule. That extra true-default is not in `sf_17`.

**TT layout.** The entry is 15 bytes of fields and 16 bytes with padding (`uint64` key, `uint16` move, `int16` score, `int8` depth, `uint8` bound, `uint8` generation). An `int16` eval does not fit. Packing it by shrinking `generation` would weaken the depth-and-age rule that passed at +5.0 ± 3.6: `new_search()` runs every move, and a short generation counter makes an old entry look current.

The plumbing PR therefore uses a 24-byte entry: add `int16 eval` and pack `ttPv` into the bound byte (bounds stay 0..3). `sizeof(TTEntry) == 24` is an assertion. Store the **raw** `evaluate()` result, the value before correction history. On probe, if the key matches and `eval` is not a sentinel, skip `evaluate()` and then add `corrHist / 16` as `corrected_eval()` does today. A corrected value stored and corrected again would move every time the pawn table moves.

Two checks, because 24/16 means a 16 MB hash holds two thirds as many entries:

1. **Reuse off, same entry count.** Scale Hash by 3/2 and ignore the stored eval. Depth-7 bench nodes stay 69980. A depth-11 count on the same switch stays on the main binary's count. Any other difference is a bug in the flags or the replacement rule.
2. **The match uses production Hash 16.** That is the configuration whose Elo matters. Non-regression SPRT with `ELO0=-3 ELO1=1` (`scripts/sprt.sh` reads those variables; the project's usual simplification pair is `[-5, 0]`, and either pair is an acceptable recording of this gate). Threads 1, 10+0.1.

If that SPRT fails, the fallback is a 16-byte entry that stores `ttPv` and does not store eval. Eval reuse is then a later patch with its own gate. Do not silently accept a node-count change from a smaller table as an eval-reuse win.

### 2b. LMR rework

One PR on top of plumbing, quiets only, stat score held at 0. Capture reductions and the history term land with §3, so a pass here is not a second copy of the inconclusive butterfly test.

The current table stays: `Reductions[d][n] = int(0.82 + ln d · ln n / 1.72)`, axes capped at 63. The formula is written in 1/1024 ply so a later SPSA can move the coefficients without rewriting the shape. **These coefficients are sprint priors, not Stockfish's integers.** Section 8 is the `sf_17` check; where it disagrees, the frozen ChessSI constant is the one in this box, and the Stockfish expression is the citation beside it.

```text
R = 1024 * Reductions[d][n]
  + 1024 * (!improving)          // K_imp  = 1 ply. sf_17 adds at most 1, and only when the base reduction is large
  + 2048 * cutNode               // K_cut  = 2 plies. sf_17 uses 2, or 1 when the TT entry is deep and ttPv
  - 1024 * ttPv                  // K_ttpv = 1 ply. sf_17 subtracts 1, 2, or 3 (see §8)
  + 1024 * ttCapture             // TT move is a capture; other moves reduced one ply more
  - 1024 * pvNode                // the reduction main already applies
  - statScore * 1024 / 8192      // 0 in this PR. §3 fills it. Clamp this term to ±2048 (±2 plies)
  - 1024 * givesCheck            // prior only. sf_17 has no general "checks reduced by 1"
r = clamp(R / 1024, 0, depth - 1)
```

Gate for this PR, quiets only: `depth >= 2 && legalMoves > 1 + pvNode`. Root counts as a PV node, so the root still searches two moves at full depth. The parent-in-check exemption stays (the node is already extended). The child-in-check exemption goes away: a checking move is reduced, and the `- givesCheck` prior reduces it by one ply less than a quiet of the same index. That `- 1` is the sprint's prior for replacing a total exemption. `sf_17` does not have it; `sf_17` simply does not exempt checks. If this bundle is marginal, the first ablation turns that coefficient to 0.

Re-search, in this same PR, because it does not need the history tables:

```text
if (reduced score > alpha && r > 0):
    newDepth += (score > best + 35 + 2 * newDepth)   // doDeeper. sf_17 uses 35; the executor draft had 40
    newDepth -= (score < best + 8)                    // doShallower
    search the zero window at newDepth with cutNode = !cutNode
```

The post-LMR continuation-history update (`sf_17` applies `stat_bonus` or `-stat_malus` there) waits for §3. Shipping it here would update a table this PR does not have.

**What this PR does not copy from `sf_17`.** The product table `(18.62 + ln(Threads)/2) * ln(i)`, the aspiration-width term inside `reduction()`, cutoff counts, and the "no TT move, reduce the zero-window by 2 extra" rule. Each of those would change the baseline reduction and make the patch unreadable. They are later SPSA parameters or later ideas.

**Experiments.** Preferred: one SPRT of this whole quiet rework, `[0, 5]` at 10+0.1, Threads 1, after the usual pre-screen. The executor's split, if the combined patch passes by a point estimate under +10 and attribution matters, is the order to bisect, each as its own patch rather than a set of flags left on:

1. `cutNode` +2 alone. Largest single prior.
2. Gate `depth >= 2 && legalMoves > 1 + pvNode`, and checks no longer exempt.
3. `ttPv` −1 and `!improving` +1.
4. doDeeper / doShallower.

Capture LMR is not in this list. It is part of §3.

**Reject this PR if** the pre-screen's 95% interval lies entirely below 0 (that is the gate `scripts/run-idea.sh` already implements), or the full test accepts H0 at `[0, 5]`. A depth-11 node count falling by a large fraction is the point of a reduction change; it is not a rejection by itself. A tactical suite (WAC, ERET, or anything else outside this repo) is a smoke screen only. The SPRT decides. An LTC look, if STC passes, is the project's 60+0.6 confirmation, recorded with its interval. A point estimate of −2 Elo at 2,000 games is inside the noise `docs/PLAN.md` quotes (about ±20 at 1,000 games) and is not a rejection rule.

SPSA of `K_imp`, `K_cut`, `K_ttpv`, and the check coefficient is a 5060 Ti job **after** the kernel in `gpu/datagen.cu` grows those fields. The current `gpu/spsa.py` space is the 17 constants already tuned (+40.4 ± 11.7). Retuning those 17 is not this experiment. The 90-minute, 30,000-pair figure in [gpu/README.md](../../../gpu/README.md) was measured on the 5080 at about 5.8 pairs a second. The 5060 Ti rate was not measured. The 5080 stays on datagen.

## 3. Continuation history and capture history

### Why `claude/conthist2` is the base, and what it already is

[`claude/conthist2`](https://github.com/LupeHiguera/ChessSI/commit/5bcc472) (`5bcc472`) is one commit on top of history-decay (`ccae417`). Neither commit is on `ed77fe7`. The branch is behind main: it does not have net12, losing-captures-last, or the tuned constants. The implementation rebases the mechanism onto accepted main. It does not SPRT that stale tree.

What the commit actually does:

- Main-thread butterfly history and one continuation table, `int mainContHist[12*64][12*64]` (768×768 ints, about 2.25 MiB). Helpers keep a fresh butterfly history and no continuation table.
- Both are halved at each `go` and cleared on `ucinewgame`.
- Index is `(piece << 6 | to-square)` of the move one ply back and two plies back. Null moves and ply 0 contribute nothing.
- The same bonus, still `min(depth², 1239)`, is applied with the same gravity (`±16384`) to the butterfly entry and both continuation entries.
- Ordering adds the two continuation entries to the butterfly score. Nothing else reads them. LMR is untouched. There is no capture history and no ply−4 term.

The first continuation test failed its pre-screen because the table was cleared every move. This commit is the retest the ideas log already describes, plus, when it is rebased, the capture table and the LMR feed below. History-decay by itself was +0.7 ± 2.7 over 19,978 games. If the combined patch passes, the log attributes the pass to the new tables, and the persistence rule stays as the condition those tables need, not as a rediscovery of history-decay.

### Tables

Per searcher. The main thread's tables persist and are halved each search, as on `conthist2`. Helpers get their own, fresh each search, the same rule as pawn correction history. A helper that inherited a 2 MB table would blow the core budget for a feature the match runs at one thread.

| Table | Shape | Size | Replaces |
| --- | --- | --- | --- |
| `quietHist[2][64][64]` | `int16` or the existing `int` | 16 KiB as int16, 32 KiB as int | Today's butterfly array |
| `contHist[12][64][12][64]` | `int16` | 1,179,648 bytes | `conthist2`'s 2.25 MiB `int` table. Same key: previous piece and to-square, then this piece and to-square. Ply−1 and ply−2. Ply−4 is out of this PR |
| `capHist[12][64][6]` | `int16`, moved piece, to-square, captured type | 9,216 bytes | Nothing yet. Good/bad SEE split from losing-captures-last stays |

`int16` is a proposal relative to `conthist2`, whose entries are 32-bit. The nps gate below is what justifies the shrink. Gravity's fixed point is ±16384, which fits in `int16`. Compute the update in 32-bit arithmetic and store the clamped result. If a bench shows the stored values stuck at ±32767, keep `conthist2`'s `int` and record the nps.

### Bonus

Freeze one pair before any games. The sprint pair, a prior rounded from the `sf_17` shape and then held still:

```text
bonus = min(190 * depth - 108, 1596)    // sf_17 stat_bonus
malus = min(736 * depth - 268, 2044)    // sf_17 stat_malus
```

The executor draft had `min(170*depth - 90, 1600)` and `min(450*depth - 40, 1300)`. Those stay unused once this pair is frozen. Gravity stays `h += b - h * |b| / 16384`, so the entries remain inside the quiet band under the killers (70,000). Today's `min(depth², 1239)` is what the near-zero tests used; this PR is allowed to change it because the new tables are the hypothesis, and the log should say both changed.

Updates on a beta cutoff:

- Best move quiet: `+bonus` into `quietHist`, ply−1 continuation, and ply−2 continuation. Other quiets tried: `−malus` in the same three.
- Best move a capture: `+bonus` into `capHist` for that moved piece, to-square, and captured type.
- Captures tried before the cutoff: `−malus` in `capHist`.

### Ordering

Quiet score = `quietHist + cont1 + cont2`. Killers, the TT move, and the good-capture band stay above that sum. Capture score inside each SEE band stays MVV-LVA plus `capHist / 8`. Losing captures remain after the quiets (the passed patch, +30.4 ± 10.4). A SEE threshold of `−capHist/32` is not in this PR.

### Feeding LMR

After the ordering patch has its own result, a second patch replaces the zero stat score:

```text
quiet:   statScore = quietHist + cont1 + cont2
capture: statScore = capHist
R -= clamp(statScore * 1024 / 8192, -2048, +2048)
```

`/8192` is the ChessSI scale: one ply per 8192 of stat score, two plies at the ±16384 gravity limit, with the term clamped to ±2. The inconclusive butterfly test (`claude/lmr-history`, `cbf0306`) used the same denominator with rounding, `(h ± 4096) / 8192`, so its steps were one ply at |history| 4096 and two at 12288. This term truncates instead, and it reads the summed stat score. `sf_17` divides a different statistic (`2*mainHistory + cont0 + cont1 - 4664`) by 10898. Pasting 10898 onto this `statScore` would not reproduce that test. One term, in place of the butterfly-only adjustment.

Capture LMR turns on in this same second patch: the §2b formula applies to captures as well as quiets, with the capture stat score, good captures only when `!pvNode`, losing captures at every node that passes the gate. The base table is not multiplied by 0.75. That factor was in the executor draft and is not in `sf_17`; leaving it out keeps the patch to one new rule.

Stage 2, only if the ordering patch passes and only as its own SPRT: skip a quiet at depth ≤ 4 when `cont1 + cont2 < −4165 * depth`. The threshold is the `sf_17` continuation-history prune (`history < -4165 * depth` on a wider sum). The executor's `−3000 * depth` is the un-checked prior and is not the frozen constant.

### Gates

- nps on `./chesssi bench` drops by more than 4% against the parent: stop, before a match. The table is there to order moves, and a 4% slowdown is already on the order of a small SPRT gain.
- Pre-screen 95% interval entirely below 0: stop, as `run-idea.sh` does.
- After a capped run (`SPRT_ROUNDS=15000`, the cap #55 added and the queue has been using; `sprt.sh` itself still defaults to 100,000), the estimate is inside ±2: stop. Do not retune bonuses. This repository has already spent 48,048 games on history refinements that landed in that band.

Planning prior for the ordering patch, discounted because of those two near-zero runs: median about +8, band −2 to +20. The Alexandria and Stash history rows in §1 are the undiscounted inputs. The LMR feed is a further prior of a few Elo on top, and it is a separate result.

## 4. net13 and the two GPUs

### The teacher the 5080 actually runs

`gpu/datagen.cu` on this main is not the CPU search. It still always-replaces TT entries (the comment at `tt_store` says so), evaluates with the raw network (no pawn correction), does not apply main-search SEE pruning, and orders every capture in the MVV-LVA band (no losing-captures-last). Its LMR is the quiet-only rule. `gpu/datagen.py` does pass the tuned numeric defaults (`rfp` 5/77, null-move divisor 4, LMR 0.82/1.72, history cap 1239). The [2026-10-27 follow-up](../research-followup-2026-10-27/REPORT.md) recorded this lag, and it is still true at `ed77fe7`.

Generation 8, which net12 trained on, was already GPU datagen. Generation 9 stays on that kernel so the file has one teacher. Syncing the kernel to CPU main in the middle of the file mixes two teachers. A kernel sync is a different experiment and gets its own generation id. The static-eval field already written by datagen is the raw network eval, which is the field this kernel has.

### Recipe

Primary, one change from the net12 recipe:

- **Data.** `gpu/datagen.py` with net12, 5,000 nodes a move, 8 random plies, the existing adjudication (win at ±2500 cp held for 6 plies, draws at 400 plies). Those are `src/datagen.cpp`'s `WinScore` and `WinPlies`, which the GPU loop follows. Target **at least 450M unique** new positions, generation 9 only.
- **Throughput prior, not a promise.** [gpu/README.md](../../../gpu/README.md) gives about 13,000 positions a second on the 5080 with net10. Generation 8 kept 436.4M unique out of 505.6M lines (86%). At those two rates, 450M unique is about 11 hours. The executor's 24–36 hours is the buffer if the GPU is shared or the rate is closer to the earlier 5,900–8,800 figures in that README. Plan a day, and record the real rate from the datagen log.
- **Training.** net12's command: hidden 256, 20 epochs, seed 1, `--aux-weight 1.0`, `--future-plies 4`, `--gpu-data-gb 0`, host mode. λ stays 0.75. Net12 at 436M unique took 2 h 34 min plus 65 min of loading on the 5060 Ti ([nets/README.md](../../../nets/README.md)). A similar corpus is the same shape of job. The executor's 4–6 hours covers a slow load.
- **Why not the union with generation 8.** The executor draft trains on gen9 ∪ gen8, about 880M unique, with 24 epochs. Net12's accepted result was generation 8 **only**, at 81% of net11's volume, +32.1 ± 10.8, and the follow-up says that result does not establish a retention policy. The same follow-up puts 500M unique rows near 21–26 GB of identified arrays, and net12's recorded peak was 26.2 GB inside a WSL limit that had already OOM-killed a larger parse at 46 GB. An 880M-row union needs a measured memory cap before anyone launches it. It is a second experiment (retention), not the first net13.

Recorded alternatives, each its own later comparison if the primary is done and the machines are free:

| Alternative in the executor draft | Why it is not in the first net13 |
| --- | --- |
| gen9 ∪ gen8, newest-duplicate wins | Different hypothesis from the net12 result, and the memory follow-up does not clear 880M rows |
| Epochs 24 | Second factor on top of a new corpus |
| λ in {0.6, 0.75} | λ 0.6 was +1.8 ± 13.4 and stopped; λ 1.0 lost −80.4 ± 18.7. Keep 0.75 |
| UHO openings, root eval band ±300 cp | Generator change. Gen7/8 start from the initial position plus 8 random plies |
| Adjudicate at \|score\| ≥ 2000 for 4 plies | Generator change. The code uses 2500 cp and 6 plies |
| h384 if the 5060 Ti is idle | Inference cost. h512 was +3.4 ± 4.8 and about 40% slower, and was stopped |
| Fallback corpus: 250M gen9 plus a gen8/gen7 subsample | Use only if the 5080 run is cut off below 450M. Say so in `nets/README.md` |

### Gates

1. `nnue/check_inference.py`: the exported net matches the engine on the usual check set. The executor's "200/200" is this check, not a new sample size to invent.
2. GPU match, `gpu/match.py`, net13 vs net12, 2,048 games at 20,000 nodes, on the **5060 Ti**. The screen prior is the executor's ≥ +15. Fixed nodes ignore speed. A pass here is not a promotion.
3. CPU SPRT `[0, 5]` at 10+0.1, both nets in one binary, Threads 1. That match is spine step 4: it waits until the plumbing, the LMR rework, and the history feed are at least running, so the GPU is not asked to SPRT a net against a search the CPU has already replaced. If those SPRTs are still going, the net waits on whichever PC frees first. It does not preempt #59 or #60.

Planning prior, from the shrinking data gains in the log (+56.8, +50.7, +32.1): **+15 to +45, median about +28**. Validation loss on a gen9 holdout is recorded and is not a promotion rule. Net12's validation loss was already not comparable with net11's, because the holdout games changed.

### GPU week

| Device | Job | Not its job |
| --- | --- | --- |
| RTX 5080 | `gpu/datagen.py` for generation 9, continuously | Training, SPSA, matches |
| RTX 5060 Ti | Network match screens. SPSA of **new** LMR coefficients once `Params` in `gpu/datagen.cu` has them and a CPU/GPU parity check has been written for that kernel. Training of net13 when the 450M rows exist (this is the machine that trained net11 and net12) | Pre-screening #59 or #60. Those are CPU searches the kernel does not implement |

`scripts/prescreen.sh` at 2+0.02 is the screen for a search patch. A near-zero pre-screen does not skip the 10+0.1 SPRT for a depth-dependent reduction; the ideas log already records that the gate skips only on a negative pre-screen.

## 5. Dual-PC SPRT

`docs/PLAN.md` rates one 265K at about 100,000–150,000 games of 10+0.1 per 60 hours, roughly 1,700–2,500 games an hour for the whole chip. A 15,000-game cap is therefore several hours on one machine. The 4–5 hour figure for 31 concurrent games is that planning rate applied to two machines, not a measurement from this sprint. Early stops on large effects are shorter. Nulls run to the cap.

| Machine | Assignment |
| --- | --- |
| PC1, the GPU box | Cores 0–12: one SPRT at a time, 13 concurrent, Threads 1, starting with **#59**. Core 13: the OS and the datagen host. Cores 14–19: the second queue only while no other agent has claimed them, or the trainer's host threads while net13 loads. Training needs a couple of cores. GPU datagen needs about one per device |
| PC2, the second 265K | **#60**, one full SPRT. 18 concurrent at 10+0.1, Hash 16, Threads 1, two cores left for the OS. P-cores and E-cores differ in nps. Pin both engines of a pair to the same concurrency slots so the difference adds noise and not a colour bias. Before the match, a short self-play of the **same** binary (on the order of 200 games) should land near 0; a large self-play score means the pinning is wrong |

Rules:

- One SPRT lives on one machine. Splitting a match across PCs changes the effective time control unless the slower box's clock is scaled by the bench nps ratio, and this sprint does not do that.
- Set `SPRT_ROUNDS=15000` explicitly. PR #55 added the variable. The default in `sprt.sh` is 100,000.
- Threads 1 for every search SPRT. A multi-thread election is a different idea (ten-ideas card 3) and is not in this queue.
- `AGENTS.md` splits one 265K between Claude (cores 0–13) and Astra (cores 14–19). The layout above is for a machine dedicated to this sprint. It belongs in a note on issue #21 before either box ignores that split. This report does not reserve the cores.
- PC2's core counts are the executor's assumption (8 P-cores + 12 E-cores, no SMT). `nproc` on the box is the check. `docs/PLAN.md` describes the 265K as 20 cores and does not record a second machine as already online.

LTC confirmation of whatever stack has passed, at 60+0.6, waits until day-scale STC results exist. Eight concurrent games on P-cores is the executor's suggestion for that run. It is one match, on one machine, of the combined accepted binary against the sprint's starting main, and it is not a substitute for the individual `[0, 5]` tests.

## 6. Card 5 and card 1

Card 5 in the [ten-ideas report](https://github.com/LupeHiguera/ChessSI/blob/astra/ten-ideas-20261028/docs/research/ten-ideas-2026-10-28/REPORT.md) is a quiet-ordering rule. At non-check nodes of depth 5 through 9, after the TT move and the good captures fail to cut off, it inspects at most four hypothetical opponent captures, keeps the first legal threat against a non-pawn with at least a pawn of SEE profit, then inspects at most four later quiets that touch that exchange. A quiet is promoted only when that same capture becomes illegal or its SEE profit crosses from positive to non-positive. Moving the victim away is excluded from the primary test, which is the report's distinction from card 1. The report classifies it **partially known, exact selector potentially new**, and its first gate is an offline count: 64 eligible cases across 32 games, compared with card 1 and with a geometry-only control, before any match.

Card 1 is the known term: a fixed bonus for stepping off a cheaper attacker's attack, and a penalty for stepping onto one, computed from pawn, minor, and rook attack masks once per node. The ten-ideas report cites [Stockfish 17's move picker](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp#L112). That is the strength-track threat ordering. Threat-indexed history (a butterfly table keyed by the threatened from/to as well as the move) is the executor's preferred form of the same idea, attributed there to Ethereal and Berserk. This pass did not re-read those two codebases, so the executor's **+5 to +15** for that table stays an unverified prior. Card 1's mask bonus is the smaller, cheaper first patch; the indexed table is the follow-up if the masks pass and the quiet-history PR has landed, because it multiplies the quiet table.

Card 5's plausible effect, as the executor judged it from the depth window and the 4×4 cap, is a few Elo either side of zero, median about +0.5, under what a 15,000-game SPRT resolves. That firing rate was not measured here. The ten-ideas gate (64 eligible cases, or stop) is the measurement, and it is cheap. Until it fires often enough, and until card 1 is the control arm the card itself asks for, card 5 does not take a SPRT slot. The novelty claim, if the selector survives the adversarial prior-art pass the ten-ideas report already requires, is a research result. It is not part of the +110 planning band.

PR #56 (repeated refutation retry) is a different mechanism and is not card 5. It stays where that draft left it.

## 7. Ranked queue

Priors are the executor's medians and bands, discounted as in the sections above. They are not additive. The interaction discount the executor applied, about 30%, is how the rows collapse to **+60 to +180, median about +110**.

| # | Item | When | Prior (band) | Slot |
| --- | --- | --- | --- | --- |
| 0 | Gen9 datagen, net12, current GPU kernel | From the moment the 5080 is free, through the corpus | — | 5080 |
| 1 | qs-TT, PR #59 | First PC1 match | +8 (0 to +20) | PC1 |
| 2 | Singular + multi-cut, PR #60 | First PC2 match. Does not wait on card 5 or on the plumbing PR. #60 does not read `cutNode`; its multi-cut is `singularBeta >= beta` | +15 (0 to +35). The top of the band includes double extensions this patch does not have | PC2 |
| 3 | Plumbing (§2a) | Next code. After #59/#60 have started, not after they finish, if a third coder is free; the match waits for a machine | +3 (−2 to +8), plus whatever the smaller hash costs | First free SPRT slot |
| 4 | LMR rework (§2b), quiets, stat score 0 | After plumbing passes its non-regression gate | +22 (+8 to +40) | SPRT `[0, 5]` |
| 5 | Continuation + capture ordering (§3), rebased from `conthist2` | After the LMR PR is in test | +8 (−2 to +20) | SPRT `[0, 5]` |
| 6 | Stat score into LMR, and capture LMR | After the ordering result | a few Elo; bisect if the pair is marginal | SPRT `[0, 5]` |
| 7 | IIR, the `claude/iir` rule (depth − 1 at depth ≥ 4 with no TT move), rebased. Not a rewrite into the `sf_17` pair of rules (PV depth − 3 with no TT move; cut-node depth − 2 or − 1) | Fills a gap | +5 (0 to +12) | SPRT `[0, 5]` |
| 8 | Improving in LMP, `claude/lmp-improving`, after plumbing supplies the flag | Fills a gap | +5 (0 to +12) | SPRT `[0, 5]` |
| 9 | Card 1 threat masks, then threat-indexed history if the masks pass | Strength-track threat work. Ahead of any card 5 match | +7 (0 to +15) for the indexed form, unverified prior | SPRT `[0, 5]` |
| 10 | Null-move `R += min((eval − beta) / 200, 3)`, capped, on top of `R = 3 + depth/4` | One line, its own test | +4 (0 to +10) | SPRT `[0, 5]` |
| 11 | net13 CPU SPRT | After rows 3–6 are in test, and after the GPU screen | +28 (+10 to +45) | CPU, either PC when free |
| 12 | SPSA of the new LMR coefficients | After the kernel has those fields. 5060 Ti | +10 (0 to +25) if the shape was right and the constants were coarse | 5060 Ti, then a CPU SPRT of the exported set |
| 13 | LTC of the accepted stack vs this main, 60+0.6 | After the STC passes exist | confirmation, not a new prior | One machine |
| R | Card 5 offline gate from PR #57 | Parallel, a few core-minutes | ~0 for the strength track | No SPRT |

Next code when the #59 and #60 agents are done with their drafts: row 3, then row 4. Row 5 is the `conthist2` rebase, for whoever takes that branch, after row 4 is the parent. Generation 9 does not wait for any of that.

## 8. `sf_17` check

Read on 2026-10-28 from tag [`sf_17` `src/search.cpp`](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/search.cpp). The sprint constants in §2b and §3 are priors **shaped** by this file. They are not a paste of it. Berserk was not re-read; anything this report says about Berserk is the executor's prior and stays unchecked.

Stockfish's parenthetical Elo comments below are Stockfish's, at Stockfish's time control and strength.

| Term | `sf_17` | Frozen for ChessSI | Note |
| --- | --- | --- | --- |
| Base reduction | `reductions[i] = int((18.62 + ln(Threads)/2) * ln(i))`, then `(reductions[d]*reductions[mn] + 1274 − delta*746/rootDelta) / 1024`, plus 1 when `!improving` and the product exceeds 1293 | Keep `int(0.82 + ln d · ln n / 1.72)` | Replacing the table would confound the patch |
| `!improving` | At most +1 ply, and only when the base product is large. In check, improving is false | `+1` ply whenever `!improving` | Coarser than `sf_17` on purpose |
| `cutNode` | `r += 2 - (ttDepth >= depth && ttPv)`. Comment "~4 Elo" | `+2` plies, no deep-TT exception | The exception is an ablation if +2 is too much |
| `ttPv` | `r -= 1 + (ttValue > alpha) + (ttDepth >= depth)`. Comment "~7 Elo" | `−1` ply | The extra −1/−2 are not in the first patch |
| `pvNode` | `r -= 1`. Comment "~0 Elo STC, ~2 LTC" | `−1`, already on main | |
| `ttCapture` | `r += 1`. Comment "~3 Elo" | `+1` | |
| History | `statScore = 2*mainHistory + cont0 + cont1 − 4664`, `r -= statScore / 10898`. Comment "~8 Elo" | `statScore / 8192`, clamped to ±2, and only once §3's tables exist | `/8192` matches the ±16384 gravity. `/10898` does not transfer |
| Checks | No general check bonus. Checks are not exempt from the gate | Exemption removed, plus a prior of −1 ply | The −1 is not from `sf_17`. Ablate it first if the result is marginal |
| Gate | `depth >= 2 && moveCount > 1 + (root && depth < 10)` | `depth >= 2 && legalMoves > 1 + pvNode`, quiets only until §3 | Different predicate, frozen so it is not "corrected" mid-test |
| doDeeper / doShallower | `value > best + 35 + 2*newDepth`, `value < best + 8`. Comments "~1 Elo" and "~2 Elo" | 35 and 8 | The executor draft had 40; the checked value is 35 |
| Bonus / malus | `min(190*d − 108, 1596)`, `min(736*d − 268, 2044)` | Those two expressions | Replaces the draft's 170/450 pair |
| Continuation prune | `history < -4165 * depth` on a three-table sum. Comment "~2 Elo" | `cont1+cont2 < -4165*depth`, stage 2 only | |
| Capture LMR | The same gate as quiets. No ×0.75 on the table | On in the §3 feed, not in §2b | The 0.75 factor is dropped |

A same-day read of Stockfish master (not a pinned tag) showed the integers already moving: reductions live entirely in 1/1024 units, the cut-node addend is thousands of those units, and capture moves get their own stat score from piece value and capture history. Master is where the formula is going. It is not the source of the constants this sprint freezes. A future retune reads a pinned master commit and treats it as a new prior, in its own patch, after this stack has a result.

`sf_17` also stores the uncorrected static eval and sets `ttPv = pvNode || (ttHit && ttData.is_pv)`, which is the plumbing in §2a. Its internal iterative reductions are two rules, and the "~9 Elo" comment sits on the first: a PV node with no TT move loses 3 plies, and a cut node at depth 7 or more loses 2 plies with no TT move or 1 ply when the TT bound is upper. `claude/iir` is neither rule. It subtracts one ply at depth 4 or more whenever the TT move is missing.

## 9. Caveats

- The +60 to +180 band, median about +110, is a planning prior with the executor's overlap discount. It is not an Elo claim. `AGENTS.md` forbids quoting a gain without an SPRT.
- #59's 63652 and #60's 69980 are the benches those drafts report. This session did not rebuild them.
- PC1's 96 GB and PC2's P/E split are the executor's hardware notes. The follow-up on trainer memory recorded a 46 GB WSL cap on the GPU box. Check both before a corpus larger than generation 9 alone.
- Self-play Elo at 10+0.1 has been transferring to the Stash gauntlet at roughly 55–81% in the README's summary of past gauntlets. A +110 self-play stack is not a +110 rating. The next gauntlet still needs opponents above 3400, and it is not part of this four-day queue.
- No external games, networks, or evaluations enter generation 9. The data rule in `AGENTS.md` is unchanged.
- Claim a row in `docs/IDEAS.md` when an agent starts it, on a branch that is not this one. This PR only orders the work.

## Sources

- This tree at `ed77fe7`: `src/search.cpp`, `src/tt.h`, `src/tt.cpp`, `src/uci.cpp` (16 MB hash), `src/datagen.cpp` (2500 cp / 6 plies), `gpu/datagen.cu`, `gpu/datagen.py`, `gpu/spsa.py`, `gpu/README.md`, `scripts/sprt.sh`, `scripts/run-idea.sh`.
- [docs/IDEAS.md](../../IDEAS.md) benchmark log and queue items 15–20. [docs/PLAN.md](../../PLAN.md) hardware and game rates. [nets/README.md](../../../nets/README.md) net10–net12. [README.md](../../../README.md) gauntlet transfer.
- [docs/research/novel-elo-ideas-2026-10-24/report.md](../novel-elo-ideas-2026-10-24/report.md) Stash and Alexandria table. [docs/research/ten-ideas-2026-10-28/REPORT.md](https://github.com/LupeHiguera/ChessSI/blob/astra/ten-ideas-20261028/docs/research/ten-ideas-2026-10-28/REPORT.md) on `astra/ten-ideas-20261028` (PR #57), cards 1 and 5. [docs/research/research-followup-2026-10-27/REPORT.md](../research-followup-2026-10-27/REPORT.md) trainer memory and the GPU teacher lag.
- Pull requests [#59](https://github.com/LupeHiguera/ChessSI/pull/59), [#60](https://github.com/LupeHiguera/ChessSI/pull/60), [#57](https://github.com/LupeHiguera/ChessSI/pull/57), [#55](https://github.com/LupeHiguera/ChessSI/pull/55). Branch [`claude/conthist2`](https://github.com/LupeHiguera/ChessSI/commit/5bcc472). LMR-history commit [`cbf0306`](https://github.com/LupeHiguera/ChessSI/commit/cbf0306bcbf015dc22bbc520a843628531c39f94).
- Stockfish tag `sf_17`, `src/search.cpp` (reduction, LMR block, `stat_bonus` / `stat_malus`, improving, TT eval) and `src/movepick.cpp` (threat ordering, via the ten-ideas citation). Alexandria cut-node LMR commit [`04beb5bd`](https://github.com/PGG106/Alexandria/commit/04beb5bd6e83947735e271e8c1053eec364255ab), capture-history commit [`b83a0eb`](https://github.com/PGG106/Alexandria/commit/b83a0eb1384420af98c2ae9b7c92bdcc4bdb50dc), as cited by the 2026-10-24 report.
