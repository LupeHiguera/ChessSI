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
| 2026-10-23 | Claude Opus 5.5 | Novel | Auxiliary head, replication on a second data snapshot (47.4M positions; head at 8 plies, weight 1.0) against a no-head control with the same data, seed and epochs | Passed | +34.6 ± 12.2 | 1,502 (4 concurrent, cores 6-9) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known + Novel | net7 replaces net6: 1.7× the data (64.6M positions, adding about 18.6M from net6 self-play) and the auxiliary head at 4 plies instead of 8 | Passed | +103.7 ± 21.8 | 628 (4 concurrent, cores 0-3) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | SEE pruning in quiescence (skip captures with SEE < 0), retest on the NNUE engine (net6, against d243d1c) | Passed | +22.2 ± 9.1 | 2,212 (4 concurrent, cores 10-13) | Inconclusive at 600-game cap, +29.0 ± 19.5 |
| 2026-10-23 | Claude Opus 5.5 | Known | net7's recipe with `--lambda 1.0` (search score only, no game result in the target), same data and seed, vs net7 | Failed | −80.4 ± 18.7 | 642 (4 concurrent, cores 0-3) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | Improving flag in LMR: one more ply of reduction when the static eval is not above its value two plies earlier | Inconclusive (stopped to free cores, LLR 0.32) | +6.7 ± 13.9 | 940 (4 concurrent, cores 10-13) | Inconclusive at 600-game cap, +7.0 ± 17.7 |
| 2026-10-23 | Claude Opus 5.5 | Novel | Policy auxiliary head: a training-only head predicting the played move's from and to squares, on net7's recipe and data | Failed (validation loss, no SPRT) | Not run | 0 (validation only: worse than no head at every weight tried) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | net7's recipe with `--lambda 0.6` (more game result in the target), same data and seed, vs net7 | Inconclusive (stopped to free cores for datagen, LLR 0.01) | +1.8 ± 13.4 | 1,160 (4 concurrent, cores 6-9) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | Eight material output buckets (by piece count), net7's recipe and data, vs net7 in one binary (`claude/output-buckets`) | Inconclusive (stopped to free cores, LLR −0.15) | −0.7 ± 14.7 | 1,002 (4 concurrent, cores 0-3) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | Continuation history, 1 and 2 plies back, in quiet-move ordering (tables reset on every `go`, like history) | Failed (pre-screen) | −2.9 ± 18.1 (pre-screen) | 600 (4 concurrent, cores 0-3) | Failed, 600 games; full SPRT skipped by the gate |
| 2026-10-23 | Claude Opus 5.5 | Known | History heuristic kept between moves (cleared only on `ucinewgame`), no decay | Failed (pre-screen) | −9.9 ± 18.5 (pre-screen) | 600 (4 concurrent, cores 0-3) | Failed, 600 games; full SPRT skipped by the gate |
| 2026-10-23 | Claude Opus 5.5 | Known | TT replacement by depth and age (an entry from the current search stays unless the new one, for another position, is at least as deep; older entries always give way), on the PeSTO engine against afe9aab | Inconclusive (stopped when main moved to NNUE, LLR 1.50) | +10.4 ± 8.9 | 2,998 (4 concurrent, 4-core cloud containers on two CPU types) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known | TT replacement by depth and age, the same change on the NNUE engine (net4, against fb4d163) | Inconclusive (cloud container stopped; handed to the PC, now `claude/tt-replacement` rebased onto main, LLR 0.56) | +4.4 ± 7.9 | 3,660 (4 concurrent, 4-core cloud container) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known + Novel | net8 replaces net7: net7's recipe (with the training-only auxiliary head) on 1.4× the data, 91.3M self-play positions including 20.3M from net7 | Passed | +43.1 ± 13.2 | 1,208 (4 concurrent, cores 6-9) | Not run |
| 2026-10-23 | Claude Opus 5.5 | Known + Novel | net9 replaces net8: net8's recipe on 1.3× the data (119.8M self-play positions, adding 29.6M more from net7 and 4.1M from net8), the first with deterministic dedup keys and the stable validation split | Passed | +48.4 ± 14.3 | 1,062 (12 concurrent, cores 0-3 and 6-13) | Not run |
| 2026-10-23 | GPT-6 (Codex) proposed, Claude Opus 5.5 implemented | Novel | TT instability flag: a TT entry is flagged when two searches of its position (depths ≥ 4, within 2 plies) give score ranges ≥ 64 cp apart, and flagged nodes reduce one ply less (`claude/astra-tt-conflict`) | Failed (Astra's preregistered frequency gate, no SPRT) | Not run | 0 (47 flags in a depth-11 bench; 0.3% of reductions changed) | Not run |
| 2026-10-24 | GPT-6 (Codex) | Known | Transition-cost block sparsity: fused accumulator runtime gate at 50% independent row occupancy | Failed (offline feasibility gate; no SPRT) | Not measured | 0 games; 630 kernel timing samples, CPU 19; [report](research/sparse-update-gate-2026-10-24/RESULT.md) | Not run |

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
10. TT replacement by depth and age, and TT cutoffs in quiescence - *Claude Code (cloud); quiescence part taken over by Claude Code. The replacement change, rebased onto main, is ready for PC 2 on `claude/tt-replacement`*
11. Internal iterative reductions when there is no TT move - *Claude Code (ready on `claude/iir`: depth ≥ 4, one ply)*
12. Mate distance pruning; insufficient-material draws
13. Time management: stop early when the best move is stable - *Claude Code (ready on `claude/tm-stability`: Stash's best-move stability and score-trend scaling of the soft limit)*
14. Phase 3: self-play data generation and a first NNUE network - *Claude Code, done (net4)*

Added 2026-10-22 from a prior-art review by Claude Code research agents (Stash's per-version
changelog gives most of the expected gains, measured at 10+0.1 or 8+0.08). Rough order, after the
first network is in, since pruning margins are in eval units and must be rechecked against it:

15. Probe and store the TT in quiescence (Stash +35.7 and +28.5)
16. Order losing captures (SEE < 0) below quiet moves (Stash +17.9); then SEE pruning in the main
    search - *Claude Code (ordering first; SEE pruning in the main search is ready on
    `claude/see-pruning`)*
17. Improving flag in RFP, LMP and LMR; count all moves, not just quiets, for LMP - *Claude Code
    (LMR alone was inconclusive, +6.7 ± 13.9; RFP untried; the LMP part, half the moves when not
    improving as in Stockfish, is ready on `claude/lmp-improving`)*
18. Continuation history (1 and 2 plies back), then capture history - *Claude Code (continuation
    history failed its pre-screen, −2.9 ± 18.1; its 590k-entry table resets on every `go`, so retest
    after item 19)*
19. Keep killers and history between moves (they reset on every `go`) - *Claude Code (history
    without decay failed its pre-screen, −9.9 ± 18.5; halving it at each new search is ready on
    `claude/history-decay`)*
20. Null-move reduction that grows with eval − beta; singular extensions after TT buckets - *Claude
    Code (singular extensions with multi-cut ready on `claude/singular`, stacked on TT replacement)*
21. Hard time limit capped below the remaining clock; node-fraction time management
22. Small fixes: no futility/LMP pruning of checking moves; a rule50 guard on TT cutoffs (Astra's
    TT draw-clock probe showed a +562 score from clock 0 reused at clock 98); checkmate before the
    fifty-move draw; RFP's stalemate check costs a full move generation per cutoff (now answered
    from a few attack lookups with the same result, on `claude/rfp-fast-legal`). For the rule50
    guard, use Astra's probe as the test: `tests/diagnostics/tt_clock_context.cpp` on branch
    `astra/research-workflow`. Astra's own follow-up found no root move changed in 16 constructed
    cases, so expect a small gain. Also a real bug, fixed on `claude/fix-zero-time`: with no
    increment and under 75 ms left, both time limits rounded to 0 ("no limit"), so the engine
    searched until stopped and lost on time. Increment games, and so every SPRT, never hit it.
23. Correction history: pawn key first (Caissa 2023; Alexandria +11.29 ± 4.66 at 8+0.08), then
    non-pawn and continuation keys, then abs(correction) in pruning margins - *Claude Code (pawn
    version ready on `claude/corrhist`)*

NNUE track (each is a trainer or data change, measured by an SPRT of the resulting network):

- Hidden size 128 vs 256 vs 512 at equal training time; NPS counts, so compare in games
- Game-result weight 0.25 → 0.4 (`--lambda 0.6`); filter early plies and score/result contradictions
- Faster inference: compile-time hidden size, the SCReLU multiply trick, fewer accumulator passes.
  *Claude Code:* the SCReLU multiply trick was already in `nnue.cpp`. A speed series with identical
  search (bench and depth-11 node counts unchanged) is ready: `claude/acc-no-zero-fill` (the
  accumulator stack stops zero-filling 1 KB per move, +2.6% nps), `claude/nnue-simd` on top (the
  output layer hand-vectorized with vpmaddwd and AVX-VNNI vpdpwssd where GCC 13 had emitted 32-bit
  multiplies, +18%), and `claude/rfp-fast-legal` on top (see item 22, +2.7%). Together about +21%
  nps against main in alternating depth-11 runs, measured while the PC was in use. A gprof profile
  of main put the network at about 22% of search time (output layer 18%, accumulator updates 4%),
  but the +18% from the output layer alone implies its true share was higher: sampling profilers
  overcharge many small calls. The accumulator update is already vectorized (vpaddw and vpsubw on
  ymm), so lazy updates are the remaining NNUE lever.
- Datagen records the static eval before each search as a fourth field (`claude/datagen-eval`):
  same games with the same seed, and the trainer reads old and new files alike. Several queued ideas
  need it, so PC 2's first generation should use it.
- Validation split by game, not by position (same-game positions make validation loss optimistic)
- Material output buckets (*Claude Code*: level with net7 at 64.6M positions, −0.7 ± 14.7; code on
  branch `claude/output-buckets`, worth retrying with more data); horizontal mirroring; king buckets
  only past ~1B positions
- **Labelled experiment: games against other engines as data** (*Claude Code*; the owner keeps it to
  one experiment, off the main line). ChessSI at 5,000 nodes plays Stash 25-36 at 12,500 nodes,
  scoring 48.7% over 42,000 games. Only ChessSI's side is kept, with its own scores (see AGENTS.md):
  1.6M positions from the first run, about 3.2M after the second. Test: net9 with and without that
  data, otherwise identical, by SPRT. Networks that include it are marked in `nets/README.md`.
- Second generation: data from the NNUE engine itself

## Novel ideas

The goal is to find out whether AI can improve on the state of the art, not just reproduce it. Known
techniques raise the baseline that novel ideas must beat; novel ideas are what the benchmark is about.
Any part of the project counts: search, evaluation, training, data, or the testing method itself.

Before testing a novel idea, check the prior-art sources above. If it turns out to exist, log it as
Known and note where it was found.

Prior art collected by Astra (GPT-6 (Codex)) in its research PR #2, closed 2026-10-23:
- **Harder self-play is a known direction.** Joshi's search-contempt paper
  ([arXiv 2504.07757](https://arxiv.org/html/2504.07757v1)) uses asymmetric MCTS to steer self-play
  toward positions a shallow opponent mishandles. A ChessSI version of "generate positions the eval
  gets wrong" needs a precise mechanism, compared against temperature, random restarts and plain
  disagreement sampling.
- **Selecting which positions get deeper labels needs a downstream test.** Braun's preprint
  ([arXiv 2609.37447](https://arxiv.org/html/2609.37447v1)) found a learned search allocator
  improved label agreement but trailed controls by 60-100 Elo in play. Label agreement alone cannot
  accept a selector: compare trained networks at equal total cost, then games.

Proposals:

- **Transition-cost block sparsity: runtime feasibility gate.** *Astra / GPT-6 (Codex),
  completed 2026-10-24 on `astra/sparse-update-gate-20261024`.* The standalone update kernel
  included copying untouched blocks into the separate child accumulator. Against the fused
  dense control on identical synthetic masked weights, it [failed the fixed gate](research/sparse-update-gate-2026-10-24/RESULT.md):
  at 50% independent row occupancy, median paired times were 1.594x quiet and 1.471x capture,
  slower in all seven pairs of both. No training or engine change followed; no Elo was measured.
  Broad block-sparse NNUE has prior art; narrow novelty is unestablished. CPU 19 only, no GPU.

- **Cheaper testing (methodology).** CPU time for SPRTs is the bottleneck. Ways to get more decisions
  per CPU hour count as research too: early adjudication of decided games (in `sprt.sh`), cheap
  pre-screening at very fast time controls (`scripts/prescreen.sh`, being validated), and testing several independent changes at once with a factorial design that
  separates their effects (verified against single-idea SPRTs before it is trusted).
- **GPU teacher for data (phase 3).** Data generation is CPU-bound. Train a larger network on the GPUs
  from our own games and use it to relabel positions in large batches, so the CPU plays games and the
  GPU supplies the evaluation targets. **Known** (prior art found by the cloud research, PR #16):
  Viridithas's `relabel` tool rescores stored positions with a network, Stockfish relabels its
  training data with an Lc0 network, and YaneuraOu's recommended loop relabels NNUE self-play data
  with a dlshogi model.
- **Uncertainty-aware evaluation.** Train the network to also predict how unsure it is, and use that to
  set pruning margins and time use instead of fixed values. Partially known: Stockfish widens its RFP
  margin by the size of its correction history, which comes from search, not a learned head. Check
  first that the predicted error correlates with real eval error before playing games.
- **Auxiliary training targets (transplant).** *Claude Code.* **Passed: +53.2 ± 15.6** (log above);
  replicated on a second data snapshot, **+34.6 ± 12.2**. The ablations under "NNUE training
  measurements" show the gain comes from an extra pure-search-score target, not from looking ahead.
  That makes it closer to ordinary multi-task learning than to KataGo's future targets. Extra outputs
  read the accumulator only during
  training and are dropped at export, so the engine is no slower: the search score some plies later
  (KataGo's short-term value targets), material later, moves left. Found in KataGo (arXiv 1902.10565)
  and Lc0, where the heads are used at inference; Lc0's transformer nets also train "future" heads
  that predict the next two moves ([arXiv 2409.12272](https://arxiv.org/abs/2409.12272)). Not found
  for NNUE: nnue-pytorch, bullet, the chessprogramming wiki and TalkChess were searched on 2026-10-23
  (Discord, where much NNUE work is discussed, could not be).
  Needs no new data: games are contiguous in the datagen files. Correction from the cloud research
  (PR #16): Lc0's optional categorical value head is training-only and left out of its exported
  networks, so it is the nearest chess precedent, though its target is the same value split into
  buckets rather than a second, cleaner target. A second web and TalkChess search on 2026-10-23
  (Claude Code on the PC) again found no training-only head for an NNUE; the only hit was this repo.
- **Adaptive LMR from reduced-versus-full disagreement.** *Proposed by Astra (GPT-6 (Codex)), to be
  implemented and tested by Claude Code on the second PC; the log row will name both models.* At one
  node, a late move's reduced search can fail high while its full-depth re-search fails low. That
  says the reduction was over-optimistic there, so later siblings are reduced one ply less. Idea 4
  in Astra's notes (`docs/research/codex-2026-10-22/search.md` on branch `astra/research-workflow`),
  with its prior-art check. Its cheap falsification comes first: does the disagreement predict
  costly misses among later siblings? *Implemented 2026-10-23 on `claude/astra-lmr-disagreement`
  (bench 168915).* The trigger is common: in a depth-11 bench, 1.6% of reduced searches failed high
  (4,606 of 290,867), 61% of those failed low at full depth, and 22,333 later reductions shrank. So
  most reduced fail-highs are false alarms. The full predictive check (verifying a sample of reduced
  fail-lows) needs an isolated diagnostic build; the SPRT on PC 2 comes first, as the owner asked.
- **TT instability flag.** *Proposed by Astra (GPT-6 (Codex)), queued for Claude Code after the one
  above.* When two searches of the same position give disjoint score intervals (both depths at
  least 4 and within 2 of each other, a gap of at least 64 cp), a 2-bit warning is stored in the TT
  entry, and that position gets one ply less LMR reduction. Idea 3 in the same notes.
  *Implemented 2026-10-23 on `claude/astra-tt-conflict` (a one-bit flag in the entry's padding,
  still 16 bytes; bench 164124).* **It fails Astra's frequency gate:** in a depth-11 bench only 47
  of 117,804 same-key stores set the flag, changing 799 of 263,385 reductions (0.3%). Astra's notes
  say to stop rather than widen the gates in that case, so no SPRT unless the owner asks for one.
- **Self-distillation head (transplant).** *Claude Code.* A training-only head that learns an earlier
  ChessSI network's static evaluation of each position (`train.py --teacher`), dropped at export.
  It follows from the auxiliary-head ablation: a low-noise target helps the shared layer, and a
  network's own evaluation is smoother than any search score. Two variants on net8's data: net7 as
  the teacher (the previous generation), and net8 itself (a born-again network). The teacher's
  network is ChessSI's own, so this stays within the data rule. Prior art: born-again networks
  ([arXiv 1805.04770](https://arxiv.org/abs/1805.04770)), where students trained on their
  teacher's outputs beat it, and distillation for compression in
  [DeepChess](https://arxiv.org/abs/1711.09667). Not found for NNUE training (web searched
  2026-10-23).
- **Policy auxiliary head (transplant).** *Claude Code.* **Failed: validation loss worse than no
  head at every weight tried** (see "NNUE training measurements"); `--policy-weight` stays in the
  trainer, off by default. A second
  training-only head on the accumulator, predicting the from and to squares of the move played
  (cross-entropy), dropped at export like the value head. Datagen plays the search's best move, so
  the move is the difference between a recorded position and the next ply's; 79% of positions have
  one. The idea follows from the ablation above: an extra target with real signal helps the shared
  layer, and a move choice says more per position than one scalar. Prior art: AlphaZero trains
  policy and value on one trunk, and [dshawul's nn-train](https://github.com/dshawul/nn-train)
  trains value, policy and score heads together, but in both the policy is used at inference.
  [Lc0's transformer](https://arxiv.org/abs/2409.12272) adds auxiliary future-move targets. Not
  found as a training-only signal for an alpha-beta NNUE (web and TalkChess searched 2026-10-23).
- **Playout-cap randomization in datagen (transplant).** Most moves get a cheap unrecorded search and
  some get a deeper recorded one, so CPU goes to fewer, better-labelled, less correlated positions.
  From KataGo; in chess only node-count jitter was found. Test at equal CPU: two datasets, one SPRT.
- **Train on the positions the eval gets wrong (phase 3).** *Claude Code.* Weight training positions
  by how far the static eval is from the search score, instead of filtering those positions out. The
  closest prior art does the opposite: [arXiv 2412.17948](https://arxiv.org/abs/2412.17948) keeps
  only positions where static eval, quiescence and search agree. Test: three networks from the same
  `datagen` positions and the same training budget (uniform, agreement-filtered, disagreement-
  weighted), compared by SPRT. Needs `datagen` to also record the static eval. **Known** (prior art
  found by the cloud research, PR #16): Lc0's "diff focus" samples positions by abs(best_q − orig_q)
  plus policy divergence, and KataGo weights by value and policy surprise. RHO-LOSS selection is
  the untried successor (see the report).
- **History prior learned offline.** *Claude Code.* Start each search with history scores learned
  from our own games, keyed by piece, from and to square and game phase, instead of zeros. No prior
  art found yet. It depends on a known fix that comes first: ChessSI rebuilds its searcher on every
  move, so killers and history reset each move. Test keeping them between moves (Known) first; the
  prior can only add on top of that. Prior art found by the cloud research (PR #16): learned move
  ordering by Kocsis et al. and the Neural MoveMap heuristic in chess, and Giraffe's move evaluator.
  Its label waits on the owner's decision about a "Partially known" value for the Kind column.

Added 2026-10-23 from the cloud research (`docs/research/novel-elo-ideas-2026-10-24/`, PR #16), with
prior art rechecked on the web and TalkChess from the PC the same day (the cloud session saw those
only as search snippets). Each is a GPU screen or offline gate first; switches for the first three
are on `claude/trainer-screens` (`nnue/train.py`, all off by default).

- **Route the game result's gradient away from the first layer.** *Claude Code.* A hypothesis for
  why the auxiliary head works: it changes how much of the first layer's training signal comes from
  the noisy game result. Without the head, 25% of the target is the result. With a weight-1.0 head
  learning pure search score, the result's share of the gradient reaching the first layer falls to
  about 12.5%, while the exported output still learns the 75/25 blend. `--result-grad B` scales only
  the result's gradient into the first layer (the output layer still learns the whole blend, so
  calibration is unchanged); at B = 0.5 the share is about 14%, close to the head's. Screen on
  net9's frozen snapshot: B = 1, 0.5 and 0 without a head, and the head with B = 0.5. If B = 0.5
  alone matches the head, the head's gain is gradient routing, and B = 0 may go further; if not, the
  head's extra readout matters. Prior art: KataGo trains its error heads behind a stop-gradient and
  Lc0's trainer has `propagate_value_gradients`, but neither applies it to the outcome part of a value
  target, and nnue-pytorch and bullet have nothing like it (cloud research; no TalkChess hit).
- **Mirror castling-free positions left to right.** *Claude Code.* Without castling rights the rules
  are symmetric under the a↔h mirror, so such positions can be flipped at random in training with
  the same score and result: free extra data, which has been ChessSI's strongest lever. `--mirror`
  judges castling from king and rook placement (the data cache has no castling field) and prints the
  share of positions that qualify; under about 40% leaves little to gain. Partially known: AlphaGo
  Zero trained on board symmetries, and NNUE's horizontally mirrored inputs build the symmetry into
  the encoding instead. No augmentation was found in nnue-pytorch, bullet, Viridithas or Stormphrax,
  nor on TalkChess.
- **HL-Gauss histogram head.** *Claude Code.* A training-only head predicts a 51-bin histogram of
  sigmoid(score / 400), by cross-entropy against a Gaussian-smoothed target (Farebrother et al.,
  ICML 2024, found it degrades less than MSE as targets get noisier). `--hl-weight` at 0.003, 0.01
  and 0.03, since cross-entropy runs at a few nats against MSE's 0.0065. The nearest chess result is
  a TalkChess thread where plain cross-entropy on the main output trained weaker than MSE, which is
  a different design. Watch for the failure that sank the policy head: a cross-entropy head
  competing with the value for 256 units.
- **Branched ("vine") self-play.** Proposed by the cloud research. Fork datagen games mid-game into
  two continuations and give the shared prefix the mean of both results, halving the result noise
  on those positions at no extra search (TRPO's vine estimator; KataGo branches games for coverage
  but never averages). No forking was found in any own-data datagen or on TalkChess. Gate first, for
  PC 2: from 2,000 positions of old games, play two continuations each and stop if fewer than about
  10% end differently.
- **Correction history keyed by the network's own hidden units.** Proposed by the cloud research,
  after pawn correction history passes: hash the signs of 12-20 accumulator units into a correction
  table, so a bias the search finds generalises along the network's notion of similarity. Every key
  found in engines is a hand-chosen piece set or move history, and the web search found none.
  Offline gate: residual variance explained against a random-bit key of the same width.
- **Randomised pruning audits.** Proposed by the cloud research. With probability about 1/256, a node
  that RFP, futility, LMP or null-move pruning would cut is searched anyway and the outcome logged:
  false-prune rates by technique and depth, and unbiased data for fitting margins. Verified null-move
  pruning re-searches every null-move cutoff, but no random-sample measurement was found.

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
  1.0.
- **The head works without looking ahead at all, so the horizon is not the mechanism.** On net7's
  64.6M positions, a head predicting the position's own search score (0 plies) matched the 4-ply head:
  no head 0.00662, own score 0.00652, 4 plies 0.00653 (net7). A second seed, which also redraws the
  validation games, gave 0.00668 vs 0.00655. A head predicting only the game result made things much
  worse (0.00717). So the head helps as a second, low-noise target for the shared layer. The exported
  head learns a blend that is 25% game result, which is noisy, and the auxiliary head adds pure search
  score. Farther horizons lose because a later score is a worse estimate of the current position's
  value. That points at the blend itself, tested next as `--lambda 1.0` and `--lambda 0.6`.
- **The game result matters, and λ 0.75 is about right.** `--lambda 1.0` lost −80.4 ± 18.7
  against net7 (λ 0.75), while `--lambda 0.6` was level (+1.8 ± 13.4 over 1,160 games). Validation
  loss is not comparable across λ. So the noisy game result carries information the search score
  lacks. The auxiliary head lets the network keep it and still get a clean score target.
- **Wider networks are only slightly better at 64.6M positions.** With net7's recipe: h256 0.00653,
  h384 0.00649, h512 0.00649. At 47.4M all three were level. The gap is opening as data grows, but
  h512 searches about 40% slower, so h256 stays for now.
- **A policy head hurts at every weight tried.** The move played (from and to squares,
  cross-entropy), on net7's recipe and data: weight 0.0003 0.00655, 0.001 0.00657, 0.003 0.00668,
  0.03 0.00726 at epoch 12 (stopped), against 0.00653 without it. The harm grows steadily with the
  weight. Predicting moves seems to compete with the value target for 256 hidden units rather than
  teach them anything useful. A wider first layer might change that.
- **A self-distillation head helps a little, and a validation pitfall turned up.** On net8's
  snapshot (91.3M positions, net8 0.00674), a head learning net8's own evaluation (born-again)
  reached 0.00671. That result is clean, since net8 never saw its validation games. A head
  learning net7 reached 0.00667, but that number is contaminated. The validation split is redrawn
  whenever the data changes, so most of net8's validation games were in net7's training data. That
  is why net7 itself scores 0.00671 there, better than net8, while losing to net8 by 43 Elo in
  games. Fix: choose validation games by a stable hash of each game, so networks from different
  generations share the same unseen games. Both variants need SPRTs.
- **Two data-pipeline fixes for net9 onward.** Position keys came from Python's `hash()`, which is
  randomised per process, so duplicates across cache chunks from different runs were never removed.
  On the 79.0M positions of generations 1-3 and the SPRT games, deterministic keys remove 10.19% as
  duplicates against 9.03% before: 918k positions (1.16%) had been counted twice. Validation games
  are now chosen by a stable per-game key (the key of the game's first position), the fix for the
  pitfall above. Networks up to net8 were trained without either fix.
- **Training hyperparameters barely move validation loss.** Against net7's 0.00653: 40 epochs
  0.00649, learning rate 0.002 0.00651, batch 8,192 0.00651. Eight material output buckets reached
  0.00650; their SPRT is running.
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
| 2026-10-23 | `cdfc298` (net7) | 264979 | Stash 19, 20.0.1, 21, 25, 27, 30, 31, 33, 34, 36 (CCRL Blitz 2474-3375) | 959 at 10+0.1, 8moves_v3 book, 4 concurrent (cores 0-3) | **3150 ± 26** |
| 2026-10-23 | `d2b1e25` (net8, SEE in quiescence) | 137954 | Stash 27, 30, 31, 33, 34, 36 (CCRL Blitz 3049-3375) | 600 at 10+0.1, 8moves_v3 book, 4 concurrent (cores 6-9) | **3176 ± 29** |

The 2026-10-22 gauntlet used a balanced book (`8moves_v3`), not the SPRT book: UHO openings give one
side an edge, which stretches rating gaps. Run it with `scripts/gauntlet.sh`. The ± is statistical
only; 10+0.1 is much faster than CCRL's 2+1, so treat the rating as approximate. Performance rose
with opponent strength (2356-2402 vs the weakest, 2461-2467 vs Stash 17 and 19), a sign of rating
compression at the extremes, so the true figure is likely nearer 2460. The 12 time forfeits, all by
Stash, were excluded. Stash 20.0.1 (2512) and 21 (2714) are now built for later gauntlets, so the
next one has opponents above ChessSI.

The 2026-10-23 gauntlet rates net7 before SEE pruning in quiescence, 710 Elo above the first
gauntlet. Since `74412b7` the engine gained the NNUE, which was worth +203, +139 and +104 in
self-play across three networks. It also gained aspiration windows, the history heuristic, late move
pruning, futility pruning and RFP. It ran in two parts. The first pool was
Stash 19-27, where ChessSI scored 70-99%, too high to say much. It was stopped after 359 games, and
600 more were played against Stash 27-36, chosen to bracket ChessSI. Those alone give 3140 ± 30.
ChessSI scored 49% against Stash 30 (3153). Performance was 3090-3150 against the four strongest
opponents and 3200 against Stash 27, so compression at the extremes again lifts the combined figure
a little. Each Stash build reproduces the bench in its release commit. The same caveat applies: this
is 10+0.1 under WSL, not CCRL's conditions.

The net8 gauntlet used only the Stash 27-36 pool, where net7 had scored 3140 ± 30. So the gain is
+36 against outside engines, from net8 and SEE pruning together, whose self-play gains were +43
and +22. Against the same opponents: Stash 30 went from 49% to 62%, Stash 33 from 30% to 36%, and
Stash 36 from 18% to 22%.
