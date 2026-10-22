# Reliable and efficient ChessSI experiments

Author: GPT-6 through Codex. Research date: 2026-10-22 UTC. Audience: Lupe and the agents developing ChessSI.

ChessSI can gain more useful evidence per CPU hour by preserving exact experiments, validating adjudication, and calibrating its short screening matches. The initial inspection found a live PGN containing multiple sessions, making run isolation the immediate priority. Later experiments use separate frozen archives and independent pair/result audits; see the [current status](STATUS.md). A reused PGN still must not be treated as one match. The existing fastchess pentanomial SPRT is a sound starting point; replacing its statistics is a later research project.

## Observed repository state

These observations describe the Claude-owned `ChessSI` directory around 05:33-05:35 UTC, or 22:33-22:35 Arizona on October 21. They are observations of a changing working directory, not a frozen source manifest.

| Evidence | Observation and consequence |
| --- | --- |
| `engines/sprt-killers.log` header | Candidate `0c32170+working tree`, bench `13595909`; baseline `HEAD`, bench `20648203`; 18 concurrent games at `10+0.1`. The short launch revision resolves to `0c32170c75298ef2bdcf3d19eb478daec5332332`. |
| Repository HEAD at inspection | `24e50aea386011a3a556206b1ba9c22ea21b654d`, with later documentation and runner commits after the launch revision. Current HEAD cannot stand in for the launch baseline. |
| Working tree | `src/search.cpp` modified. A later working-tree copy does not prove which source produced a running executable. |
| Root `config.json` | SPRT `model=normalized`, bounds `[0,5]`, alpha and beta `0.05`; seed `2592085357017269485`; 18 concurrent games; resign and draw adjudication disabled. This autosave provides useful observation-time evidence, but future runs can overwrite it. |
| Live statistics block at 1,100 games | Logistic Elo `43.18 +/- 15.77`, normalized Elo `56.83 +/- 20.53`, pentanomial counts `[33,82,233,120,82]`, LLR `2.42` with upper boundary `2.94`. This was a provisional result. |
| `engines/sprt.pgn` | At least three sessions: paired Round 1 games begin at `19:01:46`, `21:53:38`, and `21:56:53` Arizona. The later first-game headers occur around lines 13,302 and 16,364. The same generic Event and `new`/`base` names occur throughout. Approximately 1,453 game-start tags were present at one inspection. Whole-file counts do not describe only the current match. |
| `scripts/sprt.sh` | Builds into reused `engines/new`, `engines/base`, and `engines/base-src`; uses shared `engines/sprt.pgn` and default root autosave; does not itself invoke `make test`; does not explicitly select a seed or Elo model. |
| `Makefile` | Binary prerequisites include C++ and header sources, but not compiler identity, flags, or the Makefile. Reusing a target after changing only build settings can retain a stale binary. Clean per-run builds avoid this ambiguity. |

The updated `AGENTS.md` supersedes the earlier hardware policy. It assigns Claude the `ChessSI` folder and guest CPUs 0-13, Astra the `ChessSI-astra` folder and guest CPUs 14-19, with five concurrent Astra games. WSL is explicitly exempted from a strict physical-core-type requirement; actual concurrency must be recorded. The current runner can re-execute under `taskset` when `CPUS` is set. Earlier observations of missing pinning concern the older live run, not the updated script.

WSL guest affinity and host P/E-core identity are different facts. Microsoft describes `.wslconfig` processors as the logical processors assigned to the VM. Record guest affinity, host processor topology when available, and `host_core_type_verified=false` until a mapping is demonstrated. Do not infer that guest CPUs 14-19 are six particular physical cores. [Microsoft WSL configuration](https://learn.microsoft.com/windows/wsl/wsl-config)

## Ranked experiments

All items below are hypotheses or engineering proposals. None has a measured gain here.

| Priority | Proposal and classification | Falsifiable prediction | Minimum evaluation |
| --- | --- | --- | --- |
| 1 | Isolated immutable run artifacts. Known engineering practice. | A stopped, restarted, or concurrent run cannot overwrite another run or silently change its identity. | Synthetic fixtures for collisions, source drift, stale builds, partial writes, and replaced executables; a tiny manager smoke test when CPU allocation permits. |
| 2 | Replay adjudication on completed games. Known method. | Candidate resignation/draw rules save thinking time without a material directional score bias on fresh validation games. | Separate old PGN sessions; mirror the installed manager's actual semantics; tune on one cohort and validate on another. Report pair-level signed score changes, mismatches, and estimated saved seconds. |
| 3 | Calibrate the existing `2+0.02` pre-screen. Known multi-stage testing. | It rejects enough poor candidates to save net CPU time while retaining most candidates that pass prescribed `10+0.1` and `60+0.6` tests. | Run screen and full test for every calibration candidate, including screen rejects. Freeze a rule before using it to discard work. |
| 4 | Compare opening books by information per CPU hour. Known testing method. | A frozen alternative yields stronger discrimination per CPU hour across a representative patch suite. | Use independent calibration and evaluation patch sets; measure uncertainty, pair variance, duration, and decision agreement. Keep final confirmation on a declared reference book. |
| 5 | Calibrate concurrency within each assigned CPU set. Known performance engineering. | A chosen concurrency improves valid completed pairs per hour without more time losses or much wider per-game speed variation. | A baseline-versus-baseline diagnostic at several fixed concurrency levels, separately scheduled from important strength tests. Record power/load and WSL/host conditions. |
| 6 | Cost-aware stratified opening sampling. Known statistical ingredients; chess-specific contribution unestablished. | A frozen allocation over opening strata reduces variance per CPU second for the same declared target opening distribution. | Historical-pair simulation, held-out patches, and false-positive calibration before real acceptance use. Requires weighted inference; ordinary pooled SPRT cannot simply be reused after biased sampling. |

### Validate adjudication before relying on it

The latest runner proposes resignation after both engines report at least 400 cp for three moves and draw adjudication after move 40 with an eight-move near-zero sequence. The live run began with adjudication disabled, so its completed games can help evaluate prospective rules. A rule can be symmetric and still favor one engine if evaluation scales or error patterns differ.

Andy Grant's 2023 analyzer already replays adjudication on saved games and compares predicted results with played results. Thus replay-based threshold selection is prior art. Its parser and rules would need adaptation to ChessSI's manager version and PGNs; it must not be treated as an exact specification for fastchess. [Original analyzer](https://gist.github.com/AndyGrant/9a0aaf58c9bc7fc6ecde339f23cf9938)

Freeze a threshold configuration after calibration. On a fresh cohort, retain the original result, proposed earlier result, engine/color identity, trigger ply, and later thinking time. Summarize signed score differences by paired opening and termination class. Later continuation is an empirical reference for these engines at this time control, not a proof of the theoretical chess result. Revalidate when the evaluator's score scale, strength, or time control changes. A small sample with no mismatches gives an upper bound on error, not evidence of zero error.

At inspection, current fishtest worker source used draw adjudication and did not contain a resignation option. ChessSI's 400 cp resignation rule should therefore not be called a fishtest default. Fishtest also records engine crashes and time losses and detects protocol errors. [Fishtest worker source](https://github.com/official-stockfish/fishtest/blob/master/worker/games.py)

### Preserve the target of the test

Color-swapped games from the same opening are a pair. Pair outcomes have five possible total scores; keeping this structure allows the pentanomial model to account for correlated opening advantages. Do not flatten paired games into independent wins, losses, and draws for confidence calculations. [Pentanomial implementation and explanation](https://github.com/vdbergh/pentanomial)

The current screen uses alpha and beta 0.2, a cap of 300 pairs, and `2+0.02`. A rejected screen is a screening decision; it is not a completed failure under the prescribed full test. A capped test is inconclusive. Record both. A short-TC ranking can change at longer TC, particularly for time management or expensive search features.

Fishtest's established workflow uses STC followed by LTC and cautions against repeatedly trying a change until it gets lucky. Fresh confirmation data and a frozen candidate keep the selected screen result from becoming its own confirmation. [Fishtest test workflow](https://official-stockfish.github.io/docs/fishtest-wiki/Creating-my-first-test.html), [Fishtest FAQ](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-FAQ.html)

Normalized Elo and logistic Elo are separate quantities. Preserve both estimates when available, and explicitly label the SPRT's model. The present `[0,5]` uses normalized Elo. A pass does not mean the point estimate is the true gain or that the gain must exceed five logistic Elo. Near the midpoint of `[0,5]`, a published Brownian approximation gives a worst-case expected test length around 41,861 games at alpha=beta=0.05; major improvements can finish much sooner. [Normalized Elo mathematics](https://www.cantate.be/Fishtest/normalized_elo_practical.pdf)

Screening, factorial design, SPSA, paired testing, and early adjudication are established methods. They belong in the Known category unless a specific new contribution is articulated. The current one-idea-per-agent rule also excludes using a factorial bundle as a normal acceptance test.

### A bounded research direction

Partition a fixed reference opening distribution into strata using features available before the candidate is tested: material, opening advantage, game phase, or historical duration. Let `w_h` be the target stratum weight, `sigma_h` the standard deviation of the paired score, and `c_h` the average pair CPU cost. For independent samples within frozen strata, minimizing `sum(w_h^2 sigma_h^2 / n_h)` subject to a fixed `sum(n_h c_h)` gives the classical allocation `n_h proportional to w_h sigma_h / sqrt(c_h)`.

The mathematical allocation is known. A possible contribution would be a robust chess-specific choice of strata and sequential inference that saves compute across unseen engine changes. Prior art already includes cost-constrained optimal allocation and active model evaluation through approximate Neyman allocation. [Optimal allocation research](https://arxiv.org/abs/2204.04035), [Active model evaluation](https://arxiv.org/abs/2605.10075)

Start with fixed sample sizes and independently estimated strata. Preserve the reference distribution through weights. Oversampling promising openings and feeding the resulting counts into ordinary fastchess SPRT changes the question being answered. Adaptive sampling and many hypotheses require additional statistical machinery; e-value and online false-discovery methods are existing research, not an automatic property of the current likelihood ratio. [Online multiple testing with e-values](https://arxiv.org/abs/2311.06412)

## Minimal read-only provenance archiver

The first tool should only read an explicitly named source repository and known match process, then write a new archive under the requesting agent's own directory. It must not compile, execute an engine, change affinity, stop a process, alter the source runner, or read process environments. A source root and output root must resolve to different locations. Output creation must fail if the chosen run directory exists.

Suggested interface:

```text
archive_run.py --source-repo <read-only-repo> --output-root <own-archives>
               --manager-pid <known-fastchess-pid> --label <observed-run>
               [--proc-root /proc] [--max-file-bytes 33554432]
validate_archive.py <archive-directory>
```

The parser should work with copied fixtures and no live processes. A separate optional Linux probe can inspect a known manager and its descendants, allowing Windows file archiving to function even when `/proc` is unavailable. Return explicit `not_observed`, `permission_denied`, or `process_exited` states. Lack of access is not proof that a process or setting was absent.

1. Capture UTC start/end timestamps, source path, current revision, branch, tracked diff, untracked code file list, and an allowlisted source-file digest map. Use command-scoped Git safe-directory handling if necessary; do not modify global Git configuration. Record whether the tree changed across the capture. A snapshot taken after launch only proves the bytes captured then.
2. Copy raw autosave bytes using bounded retries if a read is incomplete. Parse the copy, retain its SHA-256, and record file identity and stat values before and after reading. Config autosaves may be replaced atomically; a valid old copy is still useful if labeled with its observed identity and timing. Do not manufacture launch provenance from an observation-time snapshot.
3. Preserve the launch log and a size-bounded PGN prefix. Open each file, read its initial size, and copy exactly that many bytes. Record initial/final identity and size. A partial last PGN game remains raw evidence but is excluded from completed-game statistics. If the file was replaced, truncated, or changed non-append-only, report the inconsistency; do not combine it with another file version.
4. Hash candidate/base pathname binaries and copy their bytes if size permits. For known Linux processes, separately inspect `/proc/PID/exe`, executable device/inode, process start ticks, PPID, cwd, allowed guest CPU list, and expected argv. Hash each distinct opened executable inode, including `(deleted)` files when accessible. Compare process start ticks before and after collection to catch PID reuse. Never assume the pathname still refers to the executable mapped into a running process.
5. Resolve relative engine and artifact paths against the manager's observed cwd, not the archiver cwd. Preserve absolute observed paths in metadata and use relative paths only inside the archive. Apply an explicit allowlist and path-boundary checks before reading files or writing archive members.
6. Capture book and manager identity. For a large shared book, record size/stat and an existing trusted digest if available; allow a deferred hash rather than forcing large I/O during a match. An uncomputed hash must be null, not a placeholder presented as verification.
7. Extract the latest complete statistics block from the captured log, preserving its byte offset. Record whether the block precedes or follows the autosave counts. A small discrepancy between separately captured live files is expected; do not silently reconcile mismatched observations into invented simultaneous state.
8. Write the manifest last, then validate the archive's own hashes. Preserve failures as capture findings. Never delete or modify the source files.

## Required manifest fields

JSON integers are suitable for counts in Python, but represent the RNG seed and process start ticks as decimal strings for interoperability. The observed seed exceeds JavaScript's safe integer range. `null` means unobserved; do not substitute zero.

```json
{
  "schema_version": 1,
  "capture_id": "unique-directory-name",
  "capture": {
    "started_utc": "ISO8601",
    "finished_utc": "ISO8601",
    "source_repo": "absolute-path",
    "mode": "live-read-only",
    "consistent_source_snapshot": false
  },
  "lineage": {
    "observed_head": "full-sha-or-null",
    "observed_branch": "name-or-null",
    "launch_candidate_revision": "full-sha-or-null",
    "launch_baseline_revision": null,
    "baseline_evidence": "unverified",
    "source_linkage": "binary-only",
    "source_manifest_sha256": "digest-or-null",
    "patch_sha256": "digest-or-null"
  },
  "experiment": {
    "idea_id": "declared-id-or-null",
    "proposer_model": "declared-name-or-null",
    "implementer_model": "declared-name-or-null",
    "human_interventions": [],
    "kind": "Known",
    "kind_evidence": [],
    "stage": "stc",
    "parent_run_id": null,
    "protocol_predeclared": false
  },
  "protocol": {
    "time_control": "10+0.1",
    "threads": 1,
    "hash_mb": 16,
    "concurrency": 18,
    "guest_affinity": null,
    "host_core_type_verified": false,
    "sprt_model": "normalized",
    "elo0": 0,
    "elo1": 5,
    "alpha": 0.05,
    "beta": 0.05,
    "max_pairs": 100000,
    "seed_decimal": "2592085357017269485",
    "paired_colors": true,
    "book_sha256": null,
    "manager_sha256": null,
    "adjudication": {"resign": false, "draw": false},
    "argv": []
  },
  "artifacts": [],
  "processes": [],
  "observations": [],
  "findings": [],
  "result": {
    "decision": "running",
    "reason": null,
    "validity": "incomplete-provenance",
    "games": null,
    "pairs": null,
    "wins": null,
    "draws": null,
    "losses": null,
    "pentanomial": null,
    "llr": null,
    "elo_logistic": null,
    "elo_normalized": null,
    "confidence_method": null,
    "crashes": null,
    "time_losses": null,
    "illegal_moves": null,
    "cpu_seconds": null,
    "wall_seconds": null
  }
}
```

Each artifact entry requires `role`, `source_path`, `archive_path`, `sha256`, `bytes_copied`, `capture_started_utc`, `capture_finished_utc`, `source_stat_before`, `source_stat_after`, `copy_mode` (`complete` or `prefix`), and `read_status`. Stat objects should contain identity, size, and timestamps supported by the OS. Each process entry needs PID, PPID, start ticks, executable link target, device/inode, executable digest, cwd, allowed CPU list, observation timestamp, and read status.

Each observation records its source artifact, byte offset or JSON path, observed value, and capture timestamp. Each finding has `code`, `severity`, `evidence`, and `message`. Suggested codes include `PGN_MULTIPLE_SESSIONS`, `PGN_PARTIAL_TAIL`, `SOURCE_CHANGED_DURING_CAPTURE`, `RUNNING_BINARY_DIFFERS_FROM_PATH`, `BASELINE_ONLY_INFERRED`, `CONFIG_CHANGED_DURING_CAPTURE`, `COUNTS_FROM_DIFFERENT_TIMES`, and `PROCESS_ID_REUSED`.

For finalized experiments, decision is one of `passed`, `failed`, `inconclusive_cap`, `interrupted`, or `screen_rejected`; validity is independent. A test can cross a statistical boundary yet have a configuration or provenance problem. Retain raw outcomes and the reason rather than editing history. Unknown model names, compiler flags, or launch revisions stay unknown.

## Validator fixtures and edge cases

| Fixture | Required behavior |
| --- | --- |
| Seed `2592085357017269485` | Exact decimal preservation through archive and reload. |
| Config truncated halfway through JSON | Bounded retry or explicit failed capture; no default protocol substituted. |
| Config atomically replaced during read | Preserve one coherent copy and flag identity/timing change. |
| Source changes during snapshot | Archive captured bytes but refuse an exact stable-source claim. |
| Binary pathname replaced while old process runs | Separate pathname and `/proc/PID/exe` identities and digests; flag mismatch. |
| PID exits or is reused | Record disappearance or start-tick mismatch; never merge two processes. |
| PGN contains three Round 1 pairs with identical names | Flag multiple sessions; do not sum the file as one match. |
| Games finish out of order | Pair by declared session/opening/round/color identifiers, not file adjacency. |
| PGN ends mid-comment or game | Retain prefix; exclude unfinished tail from game and pair counts. |
| One game of a color pair is complete | Preserve single-game evidence but exclude from completed-pair SPRT inputs. |
| Config counts trail a later log block | Keep both timestamped observations; do not label ordinary live lag corruption. |
| Pentanomial sum differs from half the same-block game count | Reject that block as internally inconsistent. |
| LLR upper boundary crossed but no final manager termination | Report provisional crossing; preserve whether outstanding games or a final verdict remain. |
| Manager resumed with prior stats and PGN append | Require continuity evidence; new process PID alone does not imply a new independent experiment. |
| PGN unexpectedly appends to a preexisting file | Flag preexisting bytes; isolate run by recorded offset/identity or mark segmentation unresolved. |
| Paths contain spaces, Unicode, or `..` | Resolve safely; no shell interpolation; reject traversal outside allowlisted roots. |
| Binary/book exceeds archive size cap | Record skipped bytes and null digest unless independently verified; continue partial archive. |
| `-recover` hides a crash behind ongoing games | Preserve crash/game termination evidence and emit a quality finding. |
| Build flags change but source timestamps do not | A frozen run's clean build must not reuse the earlier executable. |

A baseline-versus-baseline match is a useful pipeline diagnostic, but a few hundred roughly balanced games do not validate nominal false-positive rates. Validate a statistics implementation with many simulated null runs and known alternatives; keep simulation separate from measured engine improvements.

## Minimal isolated runner for new experiments

Use a new, exclusively created `engines/runs/<timestamp>-<idea>-<unique-id>/` in the agent's own worktree. Resolve the accepted baseline to a full commit before any build. Freeze the candidate patch and source tree, and capture compiler version, flags, build commands, and source digests. Reject a candidate snapshot if source drift is detected. Build both engines from clean per-run source directories.

Run `make test` against the exact candidate executable, save its output and return status, then bench both binaries and hash them. A search-preserving change requires the expected unchanged node signature. The source, compiler, binary, and tests must all refer to the same build.

Run fastchess with its cwd inside that run directory, explicit absolute engine/book paths, unique engine names, an explicit decimal seed, `model=normalized`, paired colors, fixed adjudication, and `append=false` for the newly created PGN. Its default `config.json` will then be local to the run. Confirm supported options using the installed version's help before relying on them. Preserve manager version and digest. Fastchess documents explicit seed control, Elo models, PGN append behavior, and configuration recovery; isolation must include the autosave as well as the PGN. [Fastchess manual](https://github.com/Disservin/fastchess/blob/master/man.md)

The outer launcher must pin builds, tests, and the manager to the authorized guest CPU range and record concurrency. It must refuse simultaneous use of the same run directory. A lightweight ownership marker can identify the active run; it must not kill an unrelated process on the basis of a stale PID file.

Use the existing prescribed statistical bounds. Parse the final verdict and count crashes, time losses, and protocol errors. Preserve unfinished runs as unfinished. A successful STC run creates a separately identified LTC confirmation using frozen binaries and fresh openings; it does not mutate the old run into a different protocol.

## Research record and next action

Log all proposals, variants, screened candidates, failed runs, interruptions, and confirmations with links to immutable artifacts. Record proposer, implementer, and substantive human interventions separately. Comparisons between AI models need matched starting engines, permissions, compute budgets, and opportunities; a raw hit rate on progressively harder baselines is not a controlled model comparison.

For this session, the useful order is: preserve the live evidence; implement and verify run isolation in the assigned worktree; finish one engine experiment; then use completed games to calibrate adjudication. Book optimization and weighted sequential testing should wait until enough trustworthy paired experiments exist to evaluate them.
## Validated interruption and recovery behavior

On 2026-10-22 UTC, GPT-6 (Codex) exercised the installed fastchess `alpha 1.8.2`, commit suffix `f618e34`, on lifecycle fixtures using only CPU 19 and one concurrent game. These were baseline-versus-baseline fixtures with node caps and a move cap; they establish process and data behavior, not playing strength or statistical calibration. The active five-game quiescence SPRT was not interrupted.

The installed revision's [signal handler](https://github.com/Disservin/fastchess/blob/f618e34/app/src/core/globals/globals.cpp) maps SIGINT to tournament stop and abnormal-termination flags. Its [main function](https://github.com/Disservin/fastchess/blob/f618e34/app/src/main.cpp) reports an interrupted tournament and a recovery command. The fixture confirmed that SIGINT terminated the manager, retained its configuration and completed PGNs, and allowed a verified terminal snapshot. A second fixture completed normally and was archived without receiving a signal. Deliberately incorrect manager and engine hashes were rejected while the fixture manager remained alive.

The interrupted fixture contained 381 completed legal games but its persisted configuration counted 380. Resuming from a copy of that configuration and appending to a copy of the PGN produced 385 PGN entries for 384 counted games. Round 191's first game appeared twice; in this fixed-node fixture the duplicate had identical moves and result. Do not assume timed-game duplicates will be identical. The original interrupted artifacts were preserved unchanged.

Running `prepare_corpus.py` on that resumed PGN correctly rejected game 382 with `Duplicate game key (Round, White, Black)`. The fixture therefore checks a real recovery output, beyond the existing synthetic parser tests. The initial CLI invocation omitted the required seed and was rejected before parsing; its error was retained, then the check was repeated with seed `20261022`.

**Recovery rule:** keep the pre-interruption archive, resume command, original byte count, configuration and schedule identities. Use fastchess's authoritative completed-pair accounting for the match. Do not derive a new result by summing an appended PGN. A corpus needs explicitly reconciled session segments, with any repeated unpaired games identified and documented. The current corpus tool intentionally rejects unresolved duplicates rather than guessing which copy to use.

Local scripts and artifacts are under ignored `engines/qsearch-validation/`:

- `watch_match.py`: a Linux pidfd guard with process hash, start-time, command, working-directory and affinity checks; it sends at most one SIGINT and does not restart a match or interpret an SPRT verdict.
- `watch-smoke-01/`: wrong-identity rejection, timed interruption, legal-PGN replay and verified terminal archive.
- `watch-natural-01/`: normal completion, no signal, verified terminal archive.
- `resume-smoke-01/`: copied recovery session, duplicate identity report and corpus-rejection evidence.

The guard is local session infrastructure, not a general scheduler. At the deadline it permits up to 60 seconds for graceful termination, then records whether the manager remains live. A live snapshot is explicitly distinct from a terminal snapshot. Before replacing run files or starting another experiment, wait for its `state.json` to report `archived` and inspect the final snapshot. Process exit and byte integrity alone do not establish an accepted strength result.

## Resolution of the remaining research window

A resource-planning observation at 2026-10-22 07:55 UTC captured the last complete 1,220-game report and the original manager's verified start tick. The observed rate was about 601 reported games/hour with five concurrent games. If that rate persisted until 19:53 UTC, roughly 7,194 additional games would fit, for about 8,414 total. This is a capacity projection, not a forecast of the current test's stopping time. The active protocol and stopping rule remain unchanged.

The installed fastchess revision uses normalized Elo for this SPRT. With pair score variance `v`, mean score `s`, and `C = 800/ln(10)`, its displayed normalized estimate is `(s - 0.5) * C / sqrt(2*v)`. Its displayed 95% half-width simplifies to `1.959963984540054 * C / sqrt(games)`. Recomputing both logistic and normalized estimates/errors from the captured pentanomial block reproduced all four printed values to rounding. The projected 8,414-game half-width is about 7.42 normalized Elo. This displayed interval is not an anytime-valid confidence sequence. [Pinned Elo implementation](https://github.com/Disservin/fastchess/blob/f618e34/app/src/matchmaking/elo/elo_pentanomial.cpp), [confidence constant](https://github.com/Disservin/fastchess/blob/f618e34/app/src/matchmaking/elo/elo.hpp)

For scheduling only, a continuous Gaussian log-likelihood approximation illustrates the cost of the prescribed `[0,5]` test. Let hypothetical true normalized Elo be `e`, boundary `A = ln(19)`, drift per game `d = 5*(e-2.5)/C^2`, and variance rate `q = 25/C^2`. Starting a fresh test at LLR zero, the Brownian approximation gives mean games `(A/d)*tanh(A*d/q)`, with limit `A^2/q` when drift is zero. These are derived planning estimates; fastchess actually uses a constrained multinomial maximum-likelihood calculation. [Pinned SPRT implementation](https://github.com/Disservin/fastchess/blob/f618e34/app/src/matchmaking/sprt/sprt.cpp)

| Hypothetical true normalized Elo | Approximate mean games from a new run | Hours at the observed rate |
| --- | --- | --- |
| -20 | 3,159 | 5.25 |
| 0 or +5 | 25,591 | 42.56 |
| +2.5 | 41,861 | 69.62 |
| +10 | 9,475 | 15.76 |
| +20 | 4,062 | 6.76 |
| +40 | 1,896 | 3.15 |
| +80 | 917 | 1.53 |

The approximation ignores discrete overshoot, finite-sample variance estimation, opening heterogeneity and changes in throughput. A mean is not a deadline guarantee. These hypothetical effects are not estimates for any prepared variant, and the current test's interim point estimate is not substituted to produce an ETA. No optional early rejection or altered boundary follows from this calculation.

The practical priority is to finish the current test and preserve its outcome. Small throughput observations are worth retaining, but a few-percent micro-optimization should not automatically consume the next full match. Prefer a well-motivated candidate with a larger plausible effect, or a cheap offline experiment that can falsify its mechanism before spending thousands of games. No speed percentage is converted into Elo here. Raw captured log bytes, the report block, process timing, calculations and limitations are preserved in `engines/qsearch-validation/budget-01/`; the reproduction script is `estimate_budget.py` one directory above it.

## Independent live-game and report audit

A new immutable observation of the original quiescence run was captured on 2026-10-22 around 08:35 UTC. Snapshot verification passed for all 26 archived artifacts. A separate audit on CPU 19 used the pinned python-chess 1.11.2 parser plus the corpus tool's strict movetext checks to replay every game, compare each parsed move with legal SAN replay, verify `PlyCount`, and reject duplicate round/color keys or inconsistent session headers.

The captured PGN contained 1,613 completed games and 158,650 legal plies. Every completed reverse-color pair used the same initial position. Its 806 complete pairs contributed 1,612 games: 556 candidate wins, 643 losses and 413 draws, with pentanomial counts `[108,150,337,143,68]`. Game 1613 had no completed partner and was retained separately. The finished-game log and PGN agreed on all 1,613 individual results; their complete-pair aggregates were identical.

Independently rebuilding completed pairs as each finished-game log event arrived reproduced the W/L/D and pentanomial counts at all 80 printed statistical reports, with zero mismatches. This checks the data entering the statistical procedure; it does not reimplement or calibrate fastchess's sequential likelihood calculation.

The saved configuration held 1,598 counted games, older than the PGN and latest printed report. Its complete W/L/D and pentanomial state matched the log immediately after line 3838, where game 1594 finished. Higher-numbered games had already finished: completion order is not numerical game order. The match is therefore consistent at an earlier autosave boundary; the lag is not evidence of corruption. Matching only printed 20-game reports, or assuming that an N-game state contains the first N game numbers, would give the wrong diagnosis.

Of the captured games, 1,285 ended by adjudication and 328 by natural rules. The latter comprised 216 threefold repetitions, 30 fifty-move draws, 80 insufficient-material draws, one stalemate and one checkmate. Their logged reasons agreed with the independently replayed final board/history. No crash, disconnect, illegal-move or time-loss termination appeared in these records. This does not establish that adjudication thresholds preserve eventual results; that requires a separate continuation experiment.

The auditor was then exercised on one valid two-game fixture and six intentional corruptions, using isolated copies and no new engine games. It accepted the valid control and rejected duplicate PGN keys, different paired openings, illegal movetext, a wrong printed pentanomial vector, a missing finished-game event behind a claimed report, and autosave counts that matched no completed-pair boundary. These fixtures check the auditor's behavior, not the SPRT's false-positive rate.

Artifacts are in `engines/qsearch-validation/game-audit-01/` (snapshot, original analysis, and the extended `analysis-v2/` that checks every completed-pair boundary) and `game-audit-fixtures-01/`. Reproduction scripts are `audit_match.py` and `validate_match_audit.py` one directory above. The extended auditor's SHA-256 is `567fc6c868f9df7bfa8da871815f75d046c6b17f4eee93bfc83098fa2101bdac`; each extended analysis preserves its own source copy. The original audit source is retained as `analysis/audit_match.v1.py`.

The original match and stopping rule continued unchanged. This is a validity observation of frozen live prefixes, not a terminal result, acceptance, Elo gain or novelty claim. Repeat the audit on the final guarded snapshot before logging the experiment outcome.

## Adjudication reference screen, 2026-10-22

A small stronger-reference screen examined recorded adjudications from Astra's frozen, independently audited 1,613-game snapshot. It does not calibrate the adjudicator: the original games stopped early, and a bounded reference evaluation is not their unplayed continuation result. The ongoing SPRT's rules and recorded outcomes were left unchanged.

The plan was written before reference searches. It considered complete opening pairs with game IDs above 1,000, excluded any pair overlapping a reserved labeling opening or recorded board/side state, and retained only adjudicated games whose final positions were not naturally terminal. There were 489 eligible games. A deterministic hash with seed `20261022` first chose at most one game per pair. That pool contained 142 White wins, 132 Black wins and 17 draws. A second fixed hash selected eight from each result stratum, for 24 cases from distinct pairs. This sampling targets varied diagnostic cases, not the match's population outcome proportions.

The reference used the same checksum-verified Stockfish 19 release described in [the qsearch report](qsearch.md). Each case was searched independently at 262,144 and 1,048,576 requested nodes, with fresh TT, one thread, Hash 16 MB, MultiPV 1, full strength, no pondering and `NumaPolicy=none`. All recorded moves from the original opening FEN were replayed, and the resulting six-field FEN was verified before search. Every reported PV was replayed for legality. All checked thread affinities remained on CPU 19.

The preset triage rules flagged a decisive result when Stockfish's CP score from the declared winner's perspective was zero or negative, or when it reported mate against that winner. A draw was flagged for an absolute CP score above 100 or a nonzero mate report. Missing and zero-mate categories were retained separately. These are deliberately explicit diagnostic thresholds, not calibrated probabilities of adjudication error.

| Recorded result | Selected cases | Flags at 262,144 nodes | Flags at 1,048,576 nodes |
| --- | --- | --- | --- |
| White win | 8 | 0 | 0 |
| Black win | 8 | 0 | 0 |
| Draw | 8 | 0 | 0 |

At the larger budget, twelve decisive cases had reference scores between +697 and +1236 cp from the declared winner's perspective; four had mate reports favoring that winner. Seven draw cases had reference scores of zero and one had +4 cp from White's perspective. None of the selected final positions had a presently available fifty-move or threefold claim according to the independent replay. All scores are Stockfish's operational search outputs, not ChessSI's evaluation scale or proven game values.

No sampled discrepancy crossed the preset thresholds. This supplies limited reassurance about these cases, not a zero error rate, a false-positive bound, or permission to treat resignation settings as calibrated. The small stratified sample, heuristic reference, two correlated budgets and selected completed-game snapshot all limit inference. A negative screen cannot replace the separately proposed validation on games played to completion without adjudication, followed by exact replay of the installed manager's trigger semantics on a fresh cohort.

The screen charged 31,457,280 requested nodes; the largest reported node counts summed to 31,469,106. No additional match games were played, no reserved pilot labels were collected, and no source or live match binary changed. The sampling plan, pool counts, selected full histories, all 48 transcripts, score conversions, affinity observations and result summary are preserved in `engines/qsearch-validation/adjudication-reference-01/`. Reproduce with `engines/qsearch-validation/triage_adjudication.py`, SHA-256 `6c132ee814810c5bdc0803328fa5706e40668e66f1eb3571fc5eb1d65604e845`. GPT-6 (Codex) designed and ran this diagnostic.

## Many attempts and the strength of the final claim

AI can propose patches faster than this machine can validate them. Trying more ideas is useful, but a per-test error setting is not a campaign-wide guarantee. This is Known multiple-testing methodology, not a novel engine contribution. The repository's prescribed tests remain unchanged.

An exact hypothetical calculation illustrates the distinction. Assume each non-improving candidate has an independent false-pass probability of exactly 0.05. The chance of at least one false pass among N attempts is `1 - (1 - 0.05)^N`. These assumptions are for arithmetic only: they do not calibrate fastchess's nominal alpha, establish independence between real tests, or estimate this project's actual error rate.

| Independent all-null attempts | At least one false pass, one stage | At least one false pass, two independent stages both null |
| --- | --- | --- |
| 5 | 22.62% | 1.24% |
| 10 | 40.13% | 2.47% |
| 20 | 64.15% | 4.88% |
| 100 | 99.41% | 22.14% |

The last column assumes an error probability of `0.05 * 0.05` per candidate. That product is justified only when both stage-specific nulls apply and confirmation remains valid after first-stage selection. Reusing the same decision as its own confirmation leaves the hypothetical probability at 0.05. A patch that reliably gains at STC but has no gain at LTC can also have a 0.05 false LTC pass probability; the STC stage need not supply another factor of 0.05. Thus STC plus LTC does not imply a universal 0.25% false-claim rate for longer-time strength. Exact enumeration of a 20-by-20 product space verifies these distinctions without simulating chess.

The established Fishtest workflow limits repeated tries and warns that selected passing-patch estimates overstate aggregate progress. Follow the repository's normal acceptance and confirmation loop, preserve every revision and restart, and do not use the sum of accepted patches' point estimates as the measured strength improvement. A separate comparison of a frozen final engine against a frozen earlier anchor, using a predeclared protocol and fresh games, measures the aggregate change more directly. It still applies to its chosen hardware, time control and opening distribution. [Fishtest FAQ](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-FAQ.html)

For a future formal model-comparison study, define the inferential target before choosing an error policy. Controlling the probability of any false acceptance across a family is different from controlling the expected fraction of false discoveries; choose the criterion that matches the intended claim. A simple familywise option is a deterministic allocation `alpha_i = 0.05 / [i(i+1)]`; its infinite sum is 0.05. The union-bound argument needs each null test's error to be bounded at its allocated level, including conditional validity when the hypothesis is chosen using prior results. The algebra does not establish that the current manager provides those guarantees. A fixed twenty-attempt family could instead allocate 0.0025 per attempt. Either choice can cost much more compute and would require a separately frozen, validated study protocol; neither is activated here. [Tian and Ramdas, online familywise error control](https://arxiv.org/abs/1910.04900v2)

The immediate action is accurate accounting, not a new stopping rule: distinguish proposals, local diagnostic variants, strength-test attempts, completed STC passes and fresh LTC confirmations. Compare AI models at matched starting engines and resource allowances, and report the full attempt denominator alongside gains. Local qsearch implementation variants are not completed SPRTs or independent discoveries.

The exact fractions, finite counterexamples, telescoping-sum checks and assumptions are preserved in `engines/qsearch-validation/multiple-attempts-01/`. Reproduce with `analyze_multiple_attempts.py` one directory above, SHA-256 `4f05d07d03aa874cfa18fc2389a834c6962c80bba1638da9baae548dcffec5f0`. GPT-6 (Codex) ran the analysis on CPU 19; it used no engine searches, pilot labels or match games.

## Interpreting the terminal SPRT record

A read-only review of the installed fastchess source revision `f618e34540f94f4719ad3817950618dabe441318` clarified two accounting details before the active test concluded. This review changes no stopping rule or manager code.

The round-robin report trigger uses scheduled pairing IDs when pentanomial reporting is enabled, while the displayed statistics come from completed pairs. Consequently, a report need not contain a multiple of twenty counted games. The observed 3,038-game report was printed when scheduled game 3040 finished while an earlier partner was still outstanding. The subsequent log continued starting games; that unusual count was not a terminal result. The existing independent auditor already reconstructs completion order rather than assuming numerical-prefix order. [Pinned round-robin reporting and callbacks](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/tournament/roundrobin/roundrobin.cpp)

At a decision, the manager sets its stop flag and prints the current result block plus an explicit H0/H1 acceptance message. The numerical decision is made against unrounded likelihood boundaries; the displayed LLR has only two decimals. The percentage printed beside it is a fraction of the boundary, not a probability that the candidate is good or bad. [Pinned SPRT decision and fraction functions](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/sprt/sprt.cpp), [pinned output formatting](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/output/output_fastchess.hpp)

For the terminal audit, preserve the decision block and its exact log location separately from the end-of-process file totals. Verify the guard's terminal snapshot, replay the games, and reconstruct pair counts at the logged decision. Inspect any later completed records instead of silently adding them to the stopping-point evidence. The outer game callback checks the stop flag before invoking the locked result callback; source inspection alone does not establish that no callback could already be in flight. This is a reason to check the actual terminal log, not a claim that a late-result race occurred in this run. [Pinned game completion path](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/tournament/base/tournament.cpp)

A cap, interruption, missing decision, or unresolved accounting conflict remains Inconclusive. Process exit, a rounded boundary-like number, a negative interim Elo estimate, or a completed-pair count alone is insufficient for a pass/fail claim. If there are multiple decision messages, retain them all and investigate any disagreement before promoting or attributing a result.

## Read-only terminal evidence extractor

`scripts/research/extract_result.py` reads a frozen snapshot plus the local watcher's terminal observation. It checks archive hashes, complete input captures, final binary digests, observation ordering, a unique explicit decision and its associated statistics. It reconstructs completed pairs from game-finish order, preserves unpaired and unfinished game IDs, and flags later starts and completions separately. Game or statistics events after `Finished match` also require review; unfinished starts from before the decision remain permitted. Rounded LLR is used only to detect an incompatible claim; it cannot create a decision. The input hashes are included in the output.

```sh
# In WSL, on the assigned auxiliary core. The command writes JSON to stdout.
taskset -c 19 python3 -B scripts/research/extract_result.py \
  --snapshot engines/qsearch-validation/live-watch-01/terminal-snapshot \
  --terminal-state engines/qsearch-validation/live-watch-01/state.json
```

Exit zero means `ready_for_independent_audit`, not Passed. The output always keeps `benchmark_result` as `not_assigned`. PGN legality and result reconciliation, build/source linkage, protocol compliance, statistical boundary verification where ambiguous, and independent longer-time confirmation remain separate responsibilities. The watcher record is locally supplied evidence, not a cryptographic attestation. This extractor supports the fresh, paired `new`/`base` normalized-SPRT format used here; other formats require review. A capped run is conservatively flagged even if it contains an acceptance message.

The installed manager has a branch that would format a non-H0 outcome as H1 if the game-cap condition were reached inside `updateSprtStatus`. However, the ordinary finish callback calls that function before incrementing `match_count_`, and the scheduler limits generated games. Source inspection therefore does not establish a reachable false acceptance on an ordinary capped run. No such failure was reproduced or claimed, and the manager was not changed. [Pinned callback and stopping code](https://github.com/Disservin/fastchess/blob/f618e34540f94f4719ad3817950618dabe441318/app/src/matchmaking/tournament/roundrobin/roundrobin.cpp)

Validation now covers 34 deterministic tests, including caps, interrupted/live observations, duplicate/conflicting decisions, rounding ambiguity, count disagreements, altered archives and late/unpaired games. Synthetic parser fixtures intentionally do not establish a valid numerical SPRT. Against the actual qsearch terminal archive, extraction reproduced H0 at log line 9679, all 202 statistics reports, the 4,026 counted games and excluded unpaired game 4027, with no findings. Against the frozen 232-game RFP prefix it returned unresolved with no hypothesis. These agree with the separately completed PGN audits. Earlier outputs remain in `engines/rfp-validation/terminal-extractor-check-01/`. After input-validation and event-ordering fixes, `terminal-extractor-check-02/` reproduced the same real terminal and live-prefix outcomes. The full four-tool suite now passes 98 tests; `review-hardening-01/` preserves final sources and logs. GPT-6 (Codex) wrote and validated the tool on CPU 19; no engine search or new match was used.


## Review of terminal audit and confirmation readiness

A separate manual review found three readiness defects before these checks could authorize a new match: the confirmation helper compared SPRT hypotheses but not the complete recorded STC protocol; the extractor omitted starts after the decision; and Python optimization could remove validation assertions in the independent PGN auditor. These were defects in the evidence checks, not evidence that the current match used incorrect settings or that the previous outcome was wrong.

The extractor now retains start-line locations and rejects late events. The local PGN auditor uses ordinary validation checks and explicitly rejects optimized execution. Schema 2 records its runtime flags, its own and helper/dependency source digests, the snapshot manifest digest and the exact log/PGN/config digests. It rechecks input and implementation bindings before publishing results. This is local provenance evidence, not proof against a malicious host.

The revised confirmation helper compares the complete terminal configuration, excluding only live statistics, to the first frozen configuration. Hash-pinned launch and process observations bind manager arguments, PID/start ticks, executable identity, affinity, watcher boot identity and the observed opening seed. It also binds the independent audit to the exact terminal manifest and artifacts, checks dependency identities, and rechecks the deadline at return. The book evidence remains a recorded configured path and declared/current digest; it does not attest the bytes historically loaded inside the manager.

Validation on CPU 19 passed 19 focused confirmation checks and 18 auditor regressions, in addition to the 98 public-tool tests. Replaying the entire frozen qsearch terminal archive with the hardened auditor reproduced all 4,027 games, 398,577 legal plies, 202 reports, 4,026 paired games and excluded game 4027, without findings. Old audit results were preserved. Local evidence is under `engines/rfp-validation/review-hardening-01/` and `auditor-hardening-01/`; the latter includes the synthetic regression sources and `qsearch-recheck-01/compatibility.json`. Auditor SHA-256: `e67123fa57194ed4dc700a4614ec3a73fc2bf3a7b23f094e6485c2f284a1dac9`.

At 16:00 UTC the corrected preflight remained closed: the STC manager was still running and accepted main had advanced. This validates an actual refusal path, not a successful terminal launch path. No confirmation was started and no benchmark result was assigned by these helpers.

## Audited RFP result and the baseline gate

The original RFP match ended normally at approximately 16:16:52 UTC with H1 at log line 3779. Extraction and an independent schema-2 audit reconciled **1,568 counted games: 653 wins, 476 losses and 439 draws**, with pentanomial counts **60 / 134 / 281 / 187 / 122**. All **1,569 saved games, 156,543 legal plies and 79 statistics reports** reconciled; completed game **1568** was excluded as unpaired. Started games **1567, 1571, 1572 and 1573** had no recorded finish. No late events, missing cross-source games or suspect terminations were found. The runner and guard completed with exit code 0; the guard sent no signal and recorded no engine-binary drift.

The reported estimates are logistic Elo **+39.39 +/- 13.98**, normalized Elo **+48.89 +/- 17.20**, and printed LLR **2.95**. This supports **STC Passed only against the original a8eebea baseline**, with the recorded adjudication and 10+0.1 protocol. It is neither an LTC result nor an accepted gain on the newer main. Full identities and scope are in the [RFP final result](rfp.md#final-result-on-the-original-baseline).

The 16:18 UTC `confirmation-preflight-04/preflight.json` had complete terminal evidence and no active manager, but refused LTC because accepted main had moved to `f801f8c519b0fe5b3d009b8f0664b049409a1188`, rechecked at 16:17:43 UTC. This exercises the post-H1 baseline gate. An isolated candidate on that main passed 35 perft, 17 boundary and 17 sanitizer cases, with candidate/base benches 609035/864538. Those preparation checks start no match and transfer none of the old statistics; a properly rebased, freshly identified STC comparison and later LTC remain separate gates.

Local evidence: `engines/rfp-validation/terminal-extraction.json`, `terminal-audit-01/result.json`, `live-watch-01/state.json`, `runner-exit.json`, `confirmation-preflight-04/preflight.json` and `new-main-preparation-01/rfp-candidate/result.json`. The extractor and auditor still do not assign benchmark acceptance themselves; the STC classification follows the combined terminal, protocol, provenance and independent result review.


The required fresh comparison subsequently launched at 16:26 UTC on `astra/rfp-current-main`, based directly on rechecked main `f801f8c`. Its guard, fresh opening seed, exact engine identities and prescribed settings are recorded in the [new-run section](rfp.md#fresh-stc-comparison-on-updated-main). An initial independent audit reconciled all 33 saved games and the first statistics report. This live prefix establishes integrity only; the new comparison has no terminal verdict.
## Updated-main confirmation preparation

A separate read-only preflight is now prepared for the frozen `f801f8c` comparison. It pins the launch, process, guard, initial configuration and source-snapshot records; checks all 21 source/build/test inputs and both engine identities; and binds the terminal extractor and independent PGN audit to their exact inputs and implementation dependencies. The near-launch book observation records its on-disk path, size and digest, without claiming to attest historical manager-loaded bytes.

The intended independent confirmation remains `60+0.6`, normalized SPRT `[0,5]`, five concurrent games on CPUs 14-19 and the same 19:53 UTC deadline. The helper requires an explicit audited H1, normal runner exit, completed guard archive and unchanged accepted baseline. An external-main observation older than five minutes requires a fresh check; the helper does not fetch or authenticate remote main itself. It never launches a match, moves outputs or assigns benchmark acceptance.

On CPU 19, **27 focused helper tests passed**. At **16:45:15 UTC**, the actual preflight reported no problems and correctly remained closed while the STC manager was active, its terminal archive was absent and the recorded main observation was stale. This exercises the live waiting path; the complete eligible-H1 path has not been exercised. Local evidence: `engines/rfp-current-main-validation/confirmation-validation-01/validation.json`, `helper-tests-01/` and `live-preflight-01/`. Helper SHA-256: `0d849d627e66f6f198aa2371b7307b0d4b9cb3f60ac6561461962c1fa0b5e31b`.

The separate terminal collector is prepared to bind extraction and legal replay to this run's frozen archive. Its attempted use during the live run correctly refused before writing terminal outputs. It preserves unresolved or deadline-interrupted evidence without inferring a decision. Collector: `engines/rfp-current-main-validation/audit_terminal.py`, SHA-256 `0fd0f168b6de545365cf9ced98c1db6308cf91026f047fd2a62346f16f7f6118`. No terminal result or LTC launch is claimed by this preparation.
