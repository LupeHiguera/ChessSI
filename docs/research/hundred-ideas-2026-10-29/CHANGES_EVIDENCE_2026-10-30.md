# Existing operator results inspected during the changes review

**Captured 2026-10-31 UTC (2026-10-30 Phoenix).** These are excerpts of existing local records read by Codex, not matches run by this review. See [the review](CHANGES_REVIEW_2026-10-30.md) for interpretation and limitations.

The final net14, capture-history and non-pawn-correction logs were read from WSL Ubuntu. Their launchers specify 10+0.1, Hash16, Threads1, UHO_Lichess_4852_v1, nine concurrent games pinned to cores10–19. The net14 launcher records main ed77fe7 and exit0; the capture and non-pawn launchers identify 7bf9f5b and d0b9e4c against c727e67, with the same net14 file loaded through EvalFile. Source-to-binary reproducibility was not independently rebuilt.

The singular and IIR ACCEPT files are operator summaries. Their caveats are preserved verbatim. In particular, the singular summary has an accounting mismatch and an explicitly separate invalid earlier orientation; the IIR summary says its final stdout was lost. Neither is upgraded into independently verified final stdout here.

The gauntlet's saved fit uses six supplied Stash anchors, 1,200 games, 10+0.1, 8moves_v3.pgn and a 600cp resignation threshold. The SPRTs use UHO openings and 400cp resignation. The saved ±24 interval is the rating script's statistical interval; it does not account for uncertain anchors, protocol mismatch or opening-pair dependence.

## Terminal excerpts, operator summaries and fingerprints

```text
==> /home/lupe/build/sprt-net14-warm/net14-sprt.log <==
Started game 3383 of 15000 (net14-warm vs net12-h256)
Finished game 3377 (net14-warm vs net12-h256): 1-0 {White wins by adjudication}
Started game 3384 of 15000 (net12-h256 vs net14-warm)
Finished game 3376 (net12-h256 vs net14-warm): 0-1 {Black wins by adjudication}
Started game 3385 of 15000 (net14-warm vs net12-h256)
Finished game 3370 (net12-h256 vs net14-warm): 1/2-1/2 {Draw by 3-fold repetition}
--------------------------------------------------
Results of net14-warm vs net12-h256 (10+0.1, 1t, 16MB, UHO_Lichess_4852_v1.epd):
Elo: 14.00 +/- 6.91, nElo: 23.78 +/- 11.72
LOS: 100.00 %, DrawRatio: 45.02 %, PairsRatio: 1.29
Games: 3376, Wins: 958, Losses: 822, Draws: 1596, Points: 1756.0 (52.01 %)
Ptnml(0-2): [32, 374, 760, 470, 52], WL/DD Ratio: 1.02
LLR: 2.96 (100.6%) (-2.94, 2.94) [0.00, 5.00]
--------------------------------------------------
SPRT ([0.00, 5.00]) completed - H1 was accepted
Finished match
Total Time: 02:56:23 (hours:minutes:seconds)


==> /home/lupe/build/sprt67-net14/sprt67.log <==
Finished game 5996 (iir-net14 vs capthist-net14): 0-1 {Black wins by adjudication}
Finished game 5998 (iir-net14 vs capthist-net14): 1-0 {White wins by adjudication}
Finished game 5999 (capthist-net14 vs iir-net14): 1-0 {White wins by adjudication}
Finished game 5997 (capthist-net14 vs iir-net14): 1/2-1/2 {Draw by adjudication}
Finished game 5992 (iir-net14 vs capthist-net14): 1/2-1/2 {Draw by 3-fold repetition}
Finished game 5991 (capthist-net14 vs iir-net14): 1/2-1/2 {Draw by fifty moves rule}
Finished game 6000 (iir-net14 vs capthist-net14): 1/2-1/2 {Draw by 3-fold repetition}
--------------------------------------------------
Results of capthist-net14 vs iir-net14 (10+0.1, 1t, 16MB, UHO_Lichess_4852_v1.epd):
Elo: -2.20 +/- 4.77, nElo: -4.05 +/- 8.79
LOS: 18.30 %, DrawRatio: 50.67 %, PairsRatio: 0.95
Games: 6000, Wins: 1387, Losses: 1425, Draws: 3188, Points: 2981.0 (49.68 %)
Ptnml(0-2): [49, 709, 1520, 675, 47], WL/DD Ratio: 0.69
LLR: -1.63 (-55.3%) (-2.94, 2.94) [0.00, 5.00]
--------------------------------------------------
Finished match
Total Time: 05:16:24 (hours:minutes:seconds)


==> /home/lupe/build/sprt68-net14/sprt68.log <==
Started game 2521 of 6000 (npcorr-net14 vs iir-net14)
Finished game 2513 (npcorr-net14 vs iir-net14): 1-0 {White wins by adjudication}
Started game 2522 of 6000 (iir-net14 vs npcorr-net14)
Finished game 2516 (iir-net14 vs npcorr-net14): 1/2-1/2 {Draw by 3-fold repetition}
Started game 2523 of 6000 (npcorr-net14 vs iir-net14)
Finished game 2514 (iir-net14 vs npcorr-net14): 1/2-1/2 {Draw by 3-fold repetition}
--------------------------------------------------
Results of npcorr-net14 vs iir-net14 (10+0.1, 1t, 16MB, UHO_Lichess_4852_v1.epd):
Elo: 16.74 +/- 7.27, nElo: 31.30 +/- 13.58
LOS: 100.00 %, DrawRatio: 49.64 %, PairsRatio: 1.47
Games: 2514, Wins: 661, Losses: 540, Draws: 1313, Points: 1317.5 (52.41 %)
Ptnml(0-2): [16, 240, 624, 361, 16], WL/DD Ratio: 0.75
LLR: 2.95 (100.2%) (-2.94, 2.94) [0.00, 5.00]
--------------------------------------------------
SPRT ([0.00, 5.00]) completed - H1 was accepted
Finished match
Total Time: 02:12:52 (hours:minutes:seconds)

SPRT #60 ? ACCEPTED (early stop, H1)  ? frozen 2026-10-29
Candidate: singular-net14 = 6337590 (cand, src-cand/)
Base:      main-net14     = ed77fe7 (base, src-base/)
Net: net14-warm.nnue (both engines, compiled-in via make EVALFILE=; sha256 440ef1960ff97e575a9ce420ab18a1d3e312ed887dc48f45f15aa96f64cc17ec)
TC 10+0.1, Hash16 Threads1, UHO_Lichess_4852_v1, SPRT [0,5] a=b=0.05, conc 9 on cores 10-19, cap 3000 rounds x2
Result: ~777 games  W247 L123 D406-407 (config.json stats D406; PGN has 777 results)  ~ +55.9 +/- 8.6 Elo
Files: sprt60.pgn (valid, cand-first via run60.sh), config.json, run60.sh
NOTE: sprt60-wrong-order.pgn = invalid earlier run from launch-sprt60.sh (base listed first) ? kept for archive, do not use.
SPRT #66 IIR — ACCEPTED (recorded Fri Oct 30 01:36:19 MST 2026)
cand c727e67 (iir-net14) vs base 6337590 (singular-net14); net14 both; TC 10+0.1; SPRT [0,5]
~2770 games W716 L592 D1462; ~+15.6 +/- 7.1 Elo; LLR ~2.98 (recomputed from pentanomial)
Caveat: official fastchess final line lost with tmux session; numbers recomputed from sprt66.pgn/config.json.
Opponent      CCRL    W    D    L  Score  Perf
stash-27.0    3049  172   21    7  0.912  3456
stash-30.0    3153  154   36   10  0.860  3468
stash-31.0    3208  145   34   21  0.810  3460
stash-33.0    3273  126   50   24  0.755  3469
stash-34.0    3315   97   81   22  0.688  3452
stash-36.0    3375   78   72   50  0.570  3424
Rating: 3452 +/- 24 (95%), 0 time forfeits excluded
01de3c9aad9c2c52c347174c56f8d044b984fbe072e6bd64effba128af602212  /home/lupe/build/sprt-net14-warm/net14-sprt.log
8c664da34c189e593a33fdc480fdc2a77ecd7d58c93f22850c835a61590d6de4  /home/lupe/build/sprt68-net14/sprt68.log
4235e5e00cbf3b17e32e00dc67a82d4ea7e15dbf7d3b17c5363fd0ffdba28bb9  /home/lupe/build/sprt67-net14/sprt67.log
8b357523c7f4fe64dc4d8b6ac9cc5b10cbb1ee83aff9860a22eaaa439f1658f5  /home/lupe/build/sprt60-net14/ACCEPT.txt
05bc5689fd77b1207c4302e4c9e402ffbb4665e7b0059abdeea118b8cb6f8404  /home/lupe/build/sprt66-net14/ACCEPT.txt
41801d89c337679335278ba469d09046d9ad2aa623a60eae861d5de1da24f583  /home/lupe/build/gauntlet-stacked-iir/rating.txt
440ef1960ff97e575a9ce420ab18a1d3e312ed887dc48f45f15aa96f64cc17ec  /home/lupe/build/sprt60-net14/net14-warm.nnue
```

The SHA-256 lines identify the complete source log/summary files as read, not hashes of these excerpts. The net14 network hash matches the full hash recorded in the singular ACCEPT file and the prefix in the net14 launcher log. No networks, game collections or binaries are copied into this research artifact.
