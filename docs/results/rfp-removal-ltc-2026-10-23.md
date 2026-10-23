# RFP removal on historical PeSTO main: Failed at LTC

Prepared 2026-10-23 by GPT-6 (Codex). Kind: **Known**. Removing shallow reverse futility pruning failed the normalized [-5, 0] SPRT at 60+0.6: **H0 after 1,376 games / 688 pairs**, with logistic Elo **-37.00 +/- 12.28** for removal versus RFP enabled. An explicit AI-agent review accepted this historical result under the predeclared supervision-gap policy; no human review is claimed. The experimental removal was reverted. This result does not establish an RFP change on current NNUE main.

## Frozen comparison and protocol

| Item | Recorded setting |
| --- | --- |
| Baseline, RFP enabled | `c7e27702fe361e477de2afb3b26f5dafdc6b2e8f`; bench `276006` |
| Candidate, RFP removed | `705ec08bbac6565f0d7f242d0c9780821762ab73`; bench `358129` |
| Time control | 60 seconds + 0.6 seconds per move |
| SPRT | Normalized [-5, 0], alpha = beta = 0.05 |
| Resources | WSL Ubuntu; five concurrent games; CPUs 14-19 |
| Engine settings | Hash 16 MiB; Threads 1 |
| Opening book | `UHO_Lichess_4852_v1.epd`, paired colors |
| Seed / cap | `11194019307908266579` / 200,000 games |
| Adjudication | Resign: move_count 3, score 400, twosided true; draw: move_number 40, move_count 8, score 10 |
| Complete protocol and identities | Original/resume/final configurations, launch records and pinned hashes in the evidence bundle |

All estimates use **removal candidate minus RFP baseline**. H0 rejects removal; it does not establish an NNUE effect. The original 18 games plus 1,358 resumed games form **one cumulative trial**. Their 62,821-byte original PGN prefix was preserved exactly and counted once. The earlier 146-game, deadline-inconclusive LTC comparison against `f801f8c` is separate. Historical STC passes and Claude Code's independent PR #6 retest are also not pooled.

## Terminal evidence and arithmetic

| Field | Audited evidence |
| --- | --- |
| Terminal observation | 2026-10-23 21:58:40.994161 UTC; one threshold-specific H0 marker followed by `Finished match` in resumed raw output |
| Benchmark result | **Failed removal / H0**, assigned by explicit AI-agent policy review at 22:07 UTC |
| Counted and saved games | 1,376 games, 688 complete pairs; IDs 1-1376 |
| Candidate wins / losses / draws | 294 / 440 / 642 |
| Six counters: LL, LD, WL, DD, WD, WW | [50, 218, 122, 147, 130, 21] |
| Five bins: LL, LD, WL+DD, WD, WW | [50, 218, 269, 130, 21] |
| Logistic Elo | -37.00 +/- 12.28 |
| Normalized nElo | -55.78 +/- 18.36 |
| Unrounded decision-time LLR | -2.9459661520169598 |
| Lower decision boundary | -2.9444389791664403 |
| Legal replay and report reconciliation | All 1,376 games / 164,033 legal plies; 69 reports reconciled |
| Unpaired / postdecision completed games | None / none |
| Unfinished games, excluded | 1377-1380 |
| Frozen identities, protocol and original prefix | Verified; no observer anomalies or substantive accounting/identity contradictions |

The boundary calculation uses cumulative paired counts, not summed segment LLRs or the rounded display. Independent bisection agreed to approximately `1.68e-13`.

Fastchess uses completed-pair bins (LL, LD, WL+DD, WD, WW) and z=1.959963984540054; pair-score variance v uses denominator N (no Bessel correction). Logistic Elo transforms the mean score; its error halves the distance between the Elo transforms of mu +/- z*sqrt(v/N). The reported error bars are nominal 95% paired normal-approximation halfwidths, without sequential-stopping adjustment; transformed logistic endpoints need not center on the estimate. Normalized nElo and regularized LLR use separate arithmetic. [Paired estimator](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/elo/elo_pentanomial.cpp#L9), [Elo transform](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/elo/elo.hpp#L30).

## Supervision gap and explicit AI review

The original continuation collector disappeared while the manager continued. Its precise exit time and cause are unknown. A detached observer attached to the same manager without restarting games; it cannot recover the nonchild exit code or certify the complete signal history.

The extractor is unchanged: `evidence_status: unresolved`, `benchmark_result: not_assigned`, exit code **2**. Its retained issue is:

> Signal sent or signal status unknown; review interruption ordering

GPT-6 (Codex) performed the separate explicit AI-agent review, supported by two independent GPT-6 Astra (ultra) reviews of arithmetic and provenance. The validated policy was recorded before any terminal hypothesis was observed. Review confirmed the genuine boundary crossing, complete cumulative outcomes, frozen identities/protocol, exact prefix, stable archives and all required accounting. Only the disclosed unknown supervision metadata remains; the policy permits that limitation after these checks. This does not establish continuously supervised natural termination.

The original raw logs remain intact. The derived logical log omits only five abandoned original starts and three original interruption/footer lines; no completed outcome is removed. Raw/logical snapshots agree on config, PGN and binaries. The original collector's exit time/cause, manager nonchild exit code, global signal history and continuous supervision across the gap remain unknown.

Review record within the bundle: `ChessSI-astra/engines/rfp-removal-worktree/engines/rfp-removal-disposition/manual-review.json`, SHA-256 `28f72cd1024dbdf85d59d20e8ef1b6475acc2e34667d0b2b3dfa0a16a67f1c52`.

## Candidate disposition

After termination, the experimental source and tests were restored from `c7e2770`. On CPU 19, 35 perft cases and 17 RFP boundary cases passed, zero failed; bench returned `276006`. Rebuilt binary SHA-256 `08525665631c71fbdcdf884c0a73ae24206ae03c6cc81750c74d7d5e47a87f76` exactly matches the original RFP-enabled baseline. This restoration is not a new strength trial; original terminal evidence remains unchanged.

Disposition validation: `ChessSI-astra/engines/rfp-removal-worktree/engines/rfp-removal-disposition/validation.json`, SHA-256 `5c432c9851ee58a6dc849c162aae38053d2761d1a9870913f9bc56b0b7da4fb8`.

## Evidence package

| Artifact | Location or identity |
| --- | --- |
| Complete compressed evidence | [rfp-removal-ltc-2026-10-23.tar.gz](evidence/rfp-removal-ltc-2026-10-23.tar.gz) |
| Bundle SHA-256 | `2f60905192f551257592fa43d60800817ca572734718540b5970cdf6765d0074` |
| Bundle bytes | `5,838,597` |
| File inventory and reproduction instructions | Top-level `inventory.json` and `README.md` inside the bundle |

The package preserves both raw sessions, original/checkpoint/terminal snapshots, configurations, provenance, review policy, audit outputs, explicit AI review and disposition validation. Every manifest-addressed artifact is retained, including baseline/candidate binaries. The README documents original-layout reproduction, path/runtime constraints, external book provenance and the intentionally unresolved extractor status.

## Publication baseline and scope

The separate documentation branch `astra/rfp-ltc-result` starts at accepted main `d4e26f5eb9fa4c583e8d9ea005d6718828c62f93`. Its existing validation passed 35 perft and 17 RFP boundary cases with zero failures and bench `151950`, on CPU 19. Record: `engines/accepted-main-validation/validation.json`, SHA-256 `68c64069f750ace42dc37b7390c0ddd85d87402f352ff6cb9edd868b3c50cecb`. Those checks concern the NNUE publication baseline, not the historical match engine or its strength.

[PR #2](https://github.com/LupeHiguera/ChessSI/pull/2) remains closed and unmerged. This report, its evidence and one cumulative benchmark row constitute a separate narrow result change. No current NNUE engine change, novelty finding, Stockfish parity or AGI conclusion is claimed.
