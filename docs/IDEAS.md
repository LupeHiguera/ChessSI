# Ideas

## Benchmark log

Every idea tested, newest first, pass or fail. **Model** is the AI that proposed and wrote the change.
**Kind** is Known (an existing technique, reimplemented) or Novel (not found in prior art: the
chessprogramming wiki, TalkChess, Stockfish's fishtest). Novel ideas are the real benchmark signal.
**Pre-screen** is the verdict and game count from `scripts/prescreen.sh` (2+0.02, loose SPRT); logging
it next to the full result shows whether the pre-screen can be trusted to drop ideas on its own.
**Result** is Passed, Failed or Inconclusive. **Elo** is the SPRT estimate with its error bar.

| Date | Model | Kind | Idea | Result | Elo | Games | Pre-screen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-21 | Claude Opus 5.5 | Known | Killer moves | Passed | +43.5 ± 14.2 | 1,332 (18 concurrent, no adjudication) | Passed, 364 games, +76.6 ± 27.5 |
| 2026-10-21 | Claude Opus 5.5 | Known | History heuristic (gravity, bonus min(d², 1200), malus on earlier quiets) | Failed | −2.7 ± 4.7 | 11,690 (13 concurrent) | Inconclusive at 600-game cap, −23.8 ± 20.5 |
| 2026-10-22 | GPT-6 (Codex) | Known | Check evasions in quiescence | Failed | -11.83 +/- 8.36 | 4,026 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | Null-move pruning (R = 3 + depth/6, needs non-pawn pieces and static eval >= beta) | Passed | +157.1 ± 27.0 | 472 (13 concurrent) | Passed, 310 games, +107.5 ± 35.2 |
| 2026-10-22 | Claude Opus 5.5 | Known | Late move reductions (log table, quiet moves after the third, re-search on fail high) | Passed | +83.7 ± 19.4 | 732 (13 concurrent) | Passed, 284 games, +107.3 ± 32.2 |
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (original baseline; STC only) | Passed | +39.39 +/- 13.98 | 1,568 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | Aspiration windows (from depth 5, ±25 cp, doubling on fail) | Passed | +56.1 ± 15.0 | 944 (13 concurrent) | Passed, 592 games, +43.1 ± 19.8 |
| 2026-10-22 | Claude Opus 5.5 | Known | Late move pruning (non-PV, depth <= 8, skip quiets after 3 + depth²) | Failed | −140.0 ± 39.8 (pre-screen) | 238 (13 concurrent) | Failed, 238 games; full SPRT skipped by the gate |
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (updated main; STC only) | Passed | +68.00 +/- 16.54 | 802 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | History heuristic, retest of the same code on top of LMR | Passed | +60.4 ± 16.1 | 930 (13 concurrent) | Passed, 568 games, +48.6 ± 21.9 |
| 2026-10-22 | Claude Opus 5.5 | Known | Late move pruning, retest of the same code on top of the history heuristic | Passed | +52.5 ± 14.9 | 1,000 (13 concurrent) | Inconclusive at 600-game cap, +12.2 ± 21.0 |
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (updated main; LTC 60+0.6) | Inconclusive | Not established (deadline) | 146 (5 concurrent, CPUs 14-19, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | Futility pruning (non-PV, depth <= 6, skip quiets when eval + 120 × depth <= alpha) | Passed | +43.3 ± 13.4 | 1,210 (13 concurrent) | Inconclusive at 600-game cap, +33.7 ± 19.5 |
| 2026-10-22 | GPT-6 (Codex) | Known | Shallow reverse futility pruning (depth <= 3, margin 150 × depth), retest on top of futility pruning; run by Claude Code | Passed | +31.4 ± 11.6 | 1,730 (4 concurrent, 4-core cloud container, adjudication) | Not run |
| 2026-10-22 | Claude Opus 5.5 | Known | SEE pruning in quiescence (skip captures with SEE < 0), against 684badc, before reverse futility pruning | Inconclusive (stopped when the PC was needed, LLR 2.48 of 2.94) | +6.0 ± 4.7 | 9,398 (13 concurrent) | Inconclusive at 600-game cap, +30.8 ± 20.9 |
| 2026-10-22 | Claude Opus 5.5 | Known | First NNUE network vs PeSTO: (768 → 256) × 2, SCReLU, 2.5M positions from our SPRT games (net1) | Inconclusive (stopped for net4, trained on 7× the data; LLR 0.84) | +47.8 ± 29.3 | 380 (5 concurrent, cores 8-13) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | NNUE evaluation replaces PeSTO: net4, (768 → 256) × 2, SCReLU, 17.5M positions of our own self-play and test games | Passed | +203.3 ± 33.2 | 416 (5 concurrent, cores 8-13) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | TT probe in quiescence only (cutoffs and TT-move ordering, no stores), on the NNUE engine | Failed (pre-screen) | −19.7 ± 19.3 (pre-screen) | 600 (7 concurrent, cores 6-13) | Failed, 600 games; full SPRT skipped by the gate |
| 2026-10-23 | Claude Opus 5.5 | Known | TT probe and store in quiescence (stores never evict a deeper entry for another position) | Stopped (flawed: same-key stores overwrote deeper entries, and the probe without prefetch cost 26% NPS) | −18.3 ± 26.1 (pre-screen) | 380 (7 concurrent, cores 6-13) | Stopped at 380 games |
| 2026-10-23 | Claude Opus 5.5 | Known + Novel | net6 replaces net4: 2.2× the data (38.5M positions, partly from net4 self-play) and the training-only auxiliary head; the aux head alone is tested separately | Passed | +138.6 ± 24.7 | 496 (7 concurrent, cores 6-13) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Novel | Training-only auxiliary head predicting the win probability 8 plies later (weight 1.0), dropped at export: net6 vs a control trained on the same 38.5M positions with the same seed and epochs, no head | Passed | +53.2 ± 15.6 | 1,066 (4 concurrent, cores 6-9) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known + Novel | net7 replaces net6: 1.7× the data (64.6M positions, adding about 18.6M from net6 self-play) and the auxiliary head at 4 plies instead of 8 | Passed | +103.7 ± 21.8 | 628 (4 concurrent, cores 0-3) | Not run |

Late move pruning failed because quiet moves after the killers are in generation order, so the
"late" moves it skipped were arbitrary rather than the worst. It needs a history heuristic first.
The history heuristic was retested on top of late move reductions, where quiet-move order matters
far more than on the bare baseline. The identical code went from −2.7 ± 4.7 to +60.4 ± 16.1: a
failed idea is a result about one baseline, not a verdict on the idea, and is worth retrying once
the techniques it feeds are in. Late move pruning, retried on top of history, went from −140 to
+52.5 ± 14.9.

The pre-screen at 2+0.02 scored that late-move-pruning retest at only +12.2 ± 21.0. Pruning gains
grow with search depth, so very short games understate them. The gate skips the full SPRT only on
a negative pre-screen; a near-zero pre-screen for a depth-dependent idea should still go to 10+0.1.

Probing the TT in quiescence without storing there costs a memory access at every quiescence node,
but only finds entries the main search wrote (depth 1 and up), which few quiescence positions have.
Stash's gains came with quiescence also storing. The next test is probe and store together.

The GPT-6 (Codex) rows come from Astra's branches; the audited details are in draft PRs #2 and #4.
Astra stopped before its reverse futility pruning reached an accepted engine, so Claude Code rebased
the same code, unchanged, onto the futility-pruning commit `684badc` and ran the SPRT: H1 accepted
after 1,730 games (nElo +44.6 ± 16.4). The gain shrank from +68 to +31 because futility pruning already
skips some of the same nodes. The run was resumed once from fastchess's saved state after the cloud
container restarted at game 960.

Baseline before the first idea: bench `20648203`.

What to watch over time:

- **Hit rate:** the share of ideas that pass. A rising hit rate means better judgment, not just faster code.
- **Elo per accepted idea** and **games per accepted change** show how efficient each model is.
- **New models:** when one ships, run the same loop and compare these numbers with earlier models.
- **Novel ideas:** how many are proposed, how many pass, and their Elo. This is the closest measure of
  research ability rather than implementation speed.

## Queue

Known techniques, roughly in order of expected gain for this baseline. Each is one experiment. An
*italic name* marks an idea claimed by that agent (see "Sharing the PC" in `AGENTS.md`). Take the
top one, test it, log it, then move on.

1. Killer moves (two quiet moves per ply that caused a beta cutoff) - *Claude Code*
2. History heuristic for quiet move ordering - *Claude Code*
3. Null-move pruning - *Claude Code*
4. Late move reductions - *Claude Code*
5. Reverse futility pruning (static null move) - *Astra / GPT-6 (Codex)*
6. Aspiration windows - *Claude Code*
7. Late move pruning and futility pruning - *Claude Code*
8. Static exchange evaluation (SEE) for capture ordering and quiescence pruning - *Claude Code*
9. Check evasions in quiescence search - *Astra / GPT-6 (Codex)*
10. TT replacement by depth and age, and TT cutoffs in quiescence - *Claude Code (cloud); quiescence part taken over by Claude Code*
11. Internal iterative reductions when there is no TT move - *Claude Code*
12. Mate distance pruning; insufficient-material draws
13. Time management: stop early when the best move is stable - *Claude Code*
14. Phase 3: self-play data generation and a first NNUE network - *Claude Code, done (net4)*

Added 2026-10-22 from a prior-art review by Claude Code research agents (Stash's per-version
changelog gives most of the expected gains, measured at 10+0.1 or 8+0.08). Rough order, after the
first network is in, since pruning margins are in eval units and must be rechecked against it:

15. Probe and store the TT in quiescence (Stash +35.7 and +28.5)
16. Order losing captures (SEE < 0) below quiet moves (Stash +17.9); then SEE pruning in the main search
17. Improving flag in RFP, LMP and LMR; count all moves, not just quiets, for LMP
18. Continuation history (1 and 2 plies back), then capture history
19. Keep killers and history between moves (they reset on every `go`)
20. Null-move reduction that grows with eval − beta; singular extensions after TT buckets
21. Hard time limit capped below the remaining clock; node-fraction time management
22. Small fixes: no futility/LMP pruning of checking moves; a rule50 guard on TT cutoffs (Astra's
    TT draw-clock probe showed a +562 score from clock 0 reused at clock 98); checkmate before the
    fifty-move draw; RFP's stalemate check costs a full move generation per cutoff

NNUE track (each is a trainer or data change, measured by an SPRT of the resulting network):

- Hidden size 128 vs 256 vs 512 at equal training time; NPS counts, so compare in games
- Game-result weight 0.25 → 0.4 (`--lambda 0.6`); filter early plies and score/result contradictions
- Faster inference: compile-time hidden size, the SCReLU multiply trick, fewer accumulator passes
- Validation split by game, not by position (same-game positions make validation loss optimistic)
- Material output buckets; horizontal mirroring; king buckets only past ~1B positions
- Second generation: data from the NNUE engine itself

## Novel ideas

The goal is to find out whether AI can improve on the state of the art, not just reproduce it. Known
techniques raise the baseline that novel ideas must beat; novel ideas are what the benchmark is about.
Any part of the project counts: search, evaluation, training, data, or the testing method itself.

Before testing a novel idea, check the prior-art sources above. If it turns out to exist, log it as
Known and note where it was found. Proposals:

- **Cheaper testing (methodology).** CPU time for SPRTs is the bottleneck. Ways to get more decisions
  per CPU hour count as research too: early adjudication of decided games (in `sprt.sh`), cheap
  pre-screening at very fast time controls (`scripts/prescreen.sh`, being validated), and testing several independent changes at once with a factorial design that
  separates their effects (verified against single-idea SPRTs before it is trusted).
- **GPU teacher for data (phase 3).** Data generation is CPU-bound. Train a larger network on the GPUs
  from our own games and use it to relabel positions in large batches, so the CPU plays games and the
  GPU supplies the evaluation targets.
- **Uncertainty-aware evaluation.** Train the network to also predict how unsure it is, and use that to
  set pruning margins and time use instead of fixed values. Partially known: Stockfish widens its RFP
  margin by the size of its correction history, which comes from search, not a learned head. Check
  first that the predicted error correlates with real eval error before playing games.
- **Auxiliary training targets (transplant).** *Claude Code.* **Passed: +53.2 ± 15.6** (log above);
  a replication on a second data snapshot is running. Extra outputs read the accumulator only during
  training and are dropped at export, so the engine is no slower: the search score some plies later
  (KataGo's short-term value targets), material later, moves left. Found in KataGo (arXiv 1902.10565)
  and Lc0, where the heads are used at inference; Lc0's transformer nets also train "future" heads
  that predict the next two moves ([arXiv 2409.12272](https://arxiv.org/abs/2409.12272)). Not found
  for NNUE: nnue-pytorch, bullet, the chessprogramming wiki and TalkChess were searched on 2026-10-23
  (Discord, where much NNUE work is discussed, could not be).
  Needs no new data: games are contiguous in the datagen files.
- **Playout-cap randomization in datagen (transplant).** Most moves get a cheap unrecorded search and
  some get a deeper recorded one, so CPU goes to fewer, better-labelled, less correlated positions.
  From KataGo; in chess only node-count jitter was found. Test at equal CPU: two datasets, one SPRT.
- **Train on the positions the eval gets wrong (phase 3).** *Claude Code.* Weight training positions
  by how far the static eval is from the search score, instead of filtering those positions out. The
  closest prior art does the opposite: [arXiv 2412.17948](https://arxiv.org/abs/2412.17948) keeps
  only positions where static eval, quiescence and search agree. Test: three networks from the same
  `datagen` positions and the same training budget (uniform, agreement-filtered, disagreement-
  weighted), compared by SPRT. Needs `datagen` to also record the static eval.
- **History prior learned offline.** *Claude Code.* Start each search with history scores learned
  from our own games, keyed by piece, from and to square and game phase, instead of zeros. No prior
  art found yet. It depends on a known fix that comes first: ChessSI rebuilds its searcher on every
  move, so killers and history reset each move. Test keeping them between moves (Known) first; the
  prior can only add on top of that.

### NNUE training measurements (2026-10-23)

Validation loss on held-out games: a guide to which networks are worth an SPRT, not an Elo result.
Each comparison uses the same frozen data, seed and epochs, with validation games never seen in
training. *Claude Code.*

- **Validating on whole games exposed overfitting.** A random-position split had put positions from
  the same game on both sides. Split by game, h256 on 23M positions stops improving after about 10
  epochs while its training loss keeps falling.
- **The auxiliary head lowers validation loss at every size tried.** At 23M positions with h256: no
  head 0.00690, weight 0.5 0.00678, weight 1.0 0.00673. At 38.5M: 0.00672 without, 0.00661 with
  (weight 1.0, this is net6). At h512 the gap is larger (0.00712 vs 0.00694), consistent with the
  head acting partly as a regulariser.
- **A near horizon works best for the auxiliary target.** At 47.4M positions with h256 (no head
  0.00659), the win probability this many plies later gave: 1 ply 0.00646, 2 plies 0.00646, 4 plies
  0.00645, 8 plies 0.00651, 16 plies 0.00657. A weight of 2.0 at 8 plies (0.00652) was no better than
  1.0. One reading: the search score at 5,000 nodes is a noisy label, and the scores of positions a
  few plies on in the same game are extra, partly independent measurements of nearly the same value.
  That is a different job from KataGo's longer-range auxiliary targets.
- **More hidden neurons don't help yet.** At 47.4M positions with the head: h256 0.00651, h384
  0.00652, h512 0.00653, while h512 searches about 40% slower. Data, not network size, is the limit.

### Findings from existing games (2026-10-22, no new games played)

Two methodology questions, answered from the 32,743 SPRT and pre-screen games in `engines/sprt.pgn`
by *Claude Code* while the PC was in use. Scripts: `scripts/research/` (each reads only the PGN).

- **Truncated games judged by the base engine: rejected.** The idea: stop each game after P plies and
  score it with the unchanged engine's eval instead of playing it out. Signal per CPU second, relative
  to the final results: 0.18× at P=10, 0.56× at 20, 0.35× at 30, 0.59× at 40, 0.85× at 60. It
  is never cheaper, and it is misleading. For the history heuristic's first test it found a large
  "effect" the results did not (a shift in eval scale, not strength), and for SEE it got the sign
  wrong. Engine evals are not a substitute for results.
- **Openings the engine itself scores as unbalanced carry more signal: a lead.** UHO openings never
  repeat between tests (the book has 2.6 million), so "openings that were informative before" cannot
  be measured. Binning pairs by ChessSI's own |eval| of the opening instead, signal per pair relative
  to its run was 0.63× below 0.3 pawns, about 0.8-1.05× between 0.3 and 0.7, 1.29× at 0.7-0.8 and
  1.46× at 0.8-1.0 (about ±0.2 each; 5,072 pairs). Selecting openings by an eval band is what UHO
  already does with Stockfish's eval, so this is Known in principle. The candidate variation is
  re-filtering by the tested engine's own eval, so the band tracks the engine's strength. Next: build a
  book from the 0.7+ band, then compare SPRT lengths on the same patches.

## Measurements

Rating checks, not ideas: they change no code, get no SPRT and don't count toward the hit rate. Log
each result here with the date, the commit and its bench.

- **Gauntlet against rated engines,** after ideas 1-4 are tested. Play a few hundred games against 3-4
  open-source engines with known CCRL Blitz ratings, picked to sit above and below ChessSI, using
  `fastchess -tournament gauntlet` with the same book and time control as SPRTs. Fitting the scores
  to the opponents' ratings turns the strength estimate into a measured rating. Repeat after major
  milestones (end of phase 2, first NNUE) to chart progress.

| Date | Commit | Bench | Opponents | Games | Rating |
| --- | --- | --- | --- | --- | --- |
| 2026-10-22 | `74412b7` | 864538 | Stash 12, 13, 14, 15.3, 17, 19 (CCRL Blitz 1883-2474) | 2,400 at 10+0.1, 8moves_v3 book, 13 concurrent | **2440 ± 19** |

The 2026-10-22 gauntlet used a balanced book (`8moves_v3`), not the SPRT book: UHO openings give one
side an edge, which stretches rating gaps. Run it with `scripts/gauntlet.sh`. The ± is statistical
only; 10+0.1 is much faster than CCRL's 2+1, so treat the rating as approximate. Performance rose
with opponent strength (2356-2402 vs the weakest, 2461-2467 vs Stash 17 and 19), a sign of rating
compression at the extremes, so the true figure is likely nearer 2460. The 12 time forfeits, all by
Stash, were excluded. Stash 20.0.1 (2512) and 21 (2714) are now built for later gauntlets, so the
next one has opponents above ChessSI.
