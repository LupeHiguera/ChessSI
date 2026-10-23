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
| 2026-10-23 | GPT-6 (Codex) | Known | Remove shallow reverse futility pruning (historical PeSTO c7e2770; LTC 60+0.6) | Failed | -37.00 +/- 12.28 | 1,376 (688 pairs; 5 concurrent, CPUs 14-19; resumed once) | Not run |

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
5. Reverse futility pruning (static null move) - *Astra / GPT-6 (Codex); historical removal rejected by H0 at 60+0.6; no active run*
6. Aspiration windows - *Claude Code*
7. Late move pruning and futility pruning - *Claude Code*
8. Static exchange evaluation (SEE) for capture ordering and quiescence pruning - *Claude Code*
9. Check evasions in quiescence search - *Astra / GPT-6 (Codex)*
10. TT replacement by depth and age, and TT cutoffs in quiescence - *Claude Code (cloud)*
11. Internal iterative reductions when there is no TT move - *Claude Code*
12. Mate distance pruning; insufficient-material draws
13. Time management: stop early when the best move is stable - *Claude Code*
14. Phase 3: self-play data generation and a first NNUE network (trainer on the RTX 5080)

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
  set pruning margins and time use instead of fixed values.

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

## RFP removal experiment

Claimed by GPT-6 (Codex) on 2026-10-23 UTC. Main `c7e27702fe361e477de2afb3b26f5dafdc6b2e8f` already includes the RFP implementation after Claude Code's separate retest. The earlier 146-game confirmation remains Inconclusive and will not be resumed or pooled.

Test a single simplification: remove the shallow reverse futility block, keeping every other search rule unchanged. Compare against accepted main at `60+0.6`, normalized SPRT `[-5,0]`, alpha/beta `0.05`, 5 concurrent games on WSL Ubuntu CPUs 14-19, Hash 16 MB and Threads 1. Use the shared UHO book, paired openings, the repository's unchanged adjudication, and a fresh manager seed. Stop at a terminal SPRT decision or the existing 100,000-pair cap; no new wall-clock deadline was requested. H0 rejects removal; H1 makes removal eligible for review under the repository's simplification rule. A cap or external interruption is Inconclusive. This tests whether the accepted technique earns its search cost at the longer time control; it is a Known ablation, not a novel method. Exact source, binary, protocol and result records will be retained under this worktree's ignored `engines/` directory.

### User-requested stop

The user requested research only and no coding while gaming. At 2026-10-23 03:34 UTC, this session sent SIGINT to its verified manager and stopped all of its engine jobs. The result is Inconclusive: no SPRT decision or Elo estimate. The frozen comparison used baseline c7e27702fe361e477de2afb3b26f5dafdc6b2e8f and candidate 705ec08bbac6565f0d7f242d0c9780821762ab73 (bench 276006 / 358129).

All 18 saved games form 9 complete pairs: candidate removal 2 wins, 6 losses and 10 draws; pentanomial [1,3,4,1,0]. Games 19-23 were unfinished and excluded. Automatic archival and legal replay finished after the stop: 2,195 legal plies, no result gaps or suspect terminations, 26 archived files verified. No statistics report was printed. The manager seed is 11194019307908266579. The first saved configuration was captured during shutdown, not as an independent pre-interruption snapshot. The runner records its own signal status as unknown because the root session sent the signal externally; the root tool transcript and user-stop.json record that intervention.

The candidate remains an unpromoted experimental branch. No code was reverted or changed after the user's research-only instruction. No builds or engine tests are authorized while that constraint remains. Raw evidence is in engines/rfp-removal-validation; terminal manifest SHA-256 015b529e93130b11f75b2e44433b211594e1a0e85ca911cd613427b50a83a59a and independent audit result SHA-256 4f17393e629884fdc0a23b4344851ed901e576961612d5b079f177445f7fd0b3.


### Authorized continuation preparation

On 2026-10-23 UTC, the user made the PC available again and explicitly requested coordination with Claude. The gaming restriction above is lifted. The existing split remains in force: Astra uses only WSL CPUs 14-19, CONCURRENCY=5; Claude retains CPUs 0-13. No cores will be borrowed. Coordination notice: https://github.com/LupeHiguera/ChessSI/pull/2#issuecomment-6358481119.

The same 18-game RFP-removal comparison is eligible for continuation only while accepted main remains c7e27702fe361e477de2afb3b26f5dafdc6b2e8f and all frozen identities agree. A separate collector in engines/rfp-removal-resume-01 preserves both raw sessions and the exact original PGN prefix. Its derived logical log has an explicit omission ledger for the five abandoned starts and the first session's interruption/footer; it does not discard completed results. All six saved pair counters and cumulative PGN/log/config totals must reconcile before interpreting any terminal decision. Existing validated engine binaries are reused; no engine source changes or new idea are introduced. Twenty continuation-accounting tests passed on CPU19, and source/binary/book/manager/prefix preflight passed. Original interruption evidence remains unchanged. The benchmark row above remains the stopped-run status until a verified continuation supplies a result.


The continuation started at 2026-10-23 06:06:21 UTC. Manager and engine executable identities and CPUs 14-19 were verified; the resumed manager started games 19-23, retaining the original 18. Claude's observed workloads occupy CPUs 0-7 and 8-13. No CPU allocation overlaps, no cores are borrowed, and no engine source was changed. The match is running; no new Elo or SPRT verdict is available yet.

### Persistent observation after collector loss

On the next active review, the original continuation collector was absent while the same verified fastchess process remained running. Its exact exit time and cause are unknown. The match was neither stopped nor restarted for this monitoring failure. A detached read-only observer was attached after verifying the WSL boot ID, manager PID/start time, executable, command, working directory, process group and CPU affinity before and after opening a process handle. It uses CPU19 and cannot signal or reconfigure engines. Its launcher exited successfully; subsequent independent checks showed advancing heartbeats and continuing games.

Recovery evidence is under engines/rfp-removal-watch-01. The observer preserves terminal raw bytes before deriving a logical log and running legal replay/accounting. It retains unknown nonchild exit code and unknown global signal history; existing extractor safeguards remain unchanged. The outcome-independent manual-review rule is in manual-review-policy-validated.json, declared before any terminal SPRT decision was observed. The earlier policy attempt remains preserved with its validated successor noting the Windows shared-file read failure. Every extractor issue and observer anomaly must be reviewed; an accounting-complete label alone is not benchmark acceptance.

The match remains on the same frozen comparison and CPUs14-19, five concurrent games. No engine source changes, restarts, core borrowing, or new strength claims accompany this monitoring recovery.
### Live checkpoint and independent SPRT arithmetic

The first recovered-observer checkpoint legally replayed all 73 saved games (8,568 plies), reconciled all three printed reports, and found no PGN/log coverage gaps or suspect endings. There were 72 paired games and one completed unpaired game (73); the saved live config lagged at 58 games and matched an earlier complete-pair boundary, as permitted for a live checkpoint. This is interim evidence, not a terminal result. Artifacts: engines/rfp-removal-watch-01/checkpoint-01.

A separate CPU19-only arithmetic verifier now calls the unchanged SPRT implementation from pinned fastchess f618e34540f94f4719ad3817950618dabe441318, with explicit data-only Stats and no-op logging adapters. It is a source-level reproduction, not a byte-identical rebuild of the installed manager. The MIT-licensed source, adapters, source hashes, compiler version/flags, evaluator hash and validation are retained under engines/rfp-removal-watch-01/sprt-arithmetic. Seven fixtures, four invalid-input checks, and independently reconstructed reports at 20, 40 and 60 games passed; a separate bisection implementation agreed. Their unrounded LLRs are -0.0675138057940508, -0.20012740015876518 and -0.1557289892783664. None is a boundary crossing. The initial synthetic fixtures did not cover both boundaries: the negative case remained CONTINUE while the positive case already crossed H1. Scaling both synthetic count sets tenfold provided clear H0 and H1 branch coverage.

Final review must compare the reconstructed decision-time counts against the full-precision bounds, +/-log(19), rather than the displayed rounded +/-2.94. The pinned round-robin reporting code has a match-cap condition in the terminal-message branch; no claim is made that its ambiguous wording path is reachable in this run. Recomputing the actual likelihood ratio prevents treating wording alone as evidence of a crossing. Original and resumed counts must be combined before regularization and likelihood fitting; segment LLRs must not be added. The existing terminal review still requires raw evidence, exact original prefix, legal replay, complete pair accounting, protocol/binary identity, and explicit handling of every monitoring/extraction issue.
### Final cumulative result and disposition

The continuation reached H0 at 2026-10-23 21:58 UTC. Explicit GPT-6 (Codex) review under the predeclared policy, with independent GPT-6 Astra (ultra) arithmetic and provenance reviews, records **Failed: RFP removal**. This is an AI review, not a claim of human review. The original 18 games and 1,358 resumed games form one trial; the single cumulative row above supersedes the stopped-prefix row. The older 146-game LTC experiment remains separate.

All 1,376 saved games form 688 complete pairs: removal candidate 294 wins, 440 losses and 642 draws, pentanomial [50,218,269,130,21]. Legal replay covers 164,033 plies; all 69 reports and all six pair counters reconcile. There are no completed unpaired or postdecision games. Starts 1377-1380 remain unfinished and excluded. The unrounded normalized LLR is -2.9459661520169598, below -2.9444389791664403. The resumed raw log contains one explicit H0 followed by Finished match. Logistic Elo is -37.00 +/- 12.28 and nElo -55.78 +/- 18.36; errors are fastchess's nominal 95% paired normal-approximation half-widths without sequential-stopping adjustment.

The original extractor remains unresolved (exit 2): global signal history, the nonchild manager exit code and the collector supervision gap remain unknown. Frozen identities, full protocol, exact original PGN prefix, raw-log reconstruction and actual boundary crossing passed review under the outcome-independent policy. No continuously supervised natural exit is claimed. This historical PeSTO comparison does not establish an RFP effect on the later NNUE engine.

After preserving the terminal snapshots, source and boundary expectations were restored exactly to c7e2770. All 35 perft and 17 RFP boundary checks pass; bench is 276006. The rebuilt binary SHA-256 08525665631c71fbdcdf884c0a73ae24206ae03c6cc81750c74d7d5e47a87f76 matches the original baseline. Records are in engines/rfp-removal-disposition; original evidence remains in the validation, resume and watch directories. The separate [narrow result report](https://github.com/LupeHiguera/ChessSI/blob/astra/rfp-ltc-result/docs/results/rfp-removal-ltc-2026-10-23.md) carries the cumulative row and complete evidence package; closed PR #2 is unchanged.
