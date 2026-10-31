# Review of pending changes and new research opportunities

**Reviewed 2026-10-30 Phoenix / 2026-10-31 UTC.** Main is still `ed77fe7cd8bf43a35f3dba6cca1cde886da4e7fd`, with net12 and inherited bench 69,980. Codex coordinated three Astra ultra reviews. This pass inventories all **23 open PRs**, concentrates new review on #76/#77, and rechecks pending search, learning/GPU and runner changes against the [earlier portfolio](REPORT.md), [deep follow-up](DEEP_FOLLOWUP.md) and [historical review](REVISITING_FAILURES.md).

There is actual progress beyond the stale public status: existing local logs contain completed H1 results for net14 and non-pawn correction. There are also concrete fixes to make before reviving capture history or relying on a mixed-version queue. The strongest new experiments isolate capture-history resolution, correction feedback strength, and unnecessary king-bucket refreshes.

No engine code, experiment queue, process, affinity or network was changed. No engine, build, test, trainer or GPU job was run. WSL access was used only to read existing result files, launch scripts and hashes. This is a source review and evidence reconciliation, not independent reproduction of the matches.

## Results recovered from existing operator records

The [evidence companion](CHANGES_EVIDENCE_2026-10-30.md) preserves exact terminal excerpts, filenames and SHA-256 hashes. Launch records map the source/network combinations below; this review did not rebuild the binaries or audit every PGN.

| Item | Recorded comparison | Evidence now available |
| --- | --- | --- |
| net14-warm | Same main binary, net14 versus net12 | Final stdout: **H1, +14.00 +/- 6.91, 3,376 games**, LLR 2.96; launcher records exit 0 |
| #77 non-pawn correction | `d0b9e4c` versus IIR/singular `c727e67`, net14 both | Final stdout: **H1, +16.74 +/- 7.27, 2,514 games**, LLR 2.95 |
| #76 capture history | `7bf9f5b` versus `c727e67`, net14 both | Finished 6,000-game cap: **-2.20 +/- 4.77**, LLR -1.63; **no SPRT verdict** |
| #60 singular/multi-cut | `6337590` versus main, net14 both | Operator `ACCEPT.txt` says H1, about 777 games; its own note says config accounts for 776 and PGN has 777. No terminal stdout was found in the inspected directory |
| #75 IIR with excluded-search guard | `c727e67` versus singular `6337590`, net14 both | Operator reconstruction says H1 at 2,770 games, about +15.6, LLR about 2.98; explicitly says final fastchess output was lost |
| IIR/singular/net14 gauntlet | `c727e67` against six Stash versions, 1,200 games | Stored fit **3452 +/- 24**, zero excluded time forfeits; an approximate rating against the supplied anchors |

The three directly inspected match logs use 10+0.1, one thread, Hash 16 and UHO openings; launchers specify nine concurrent games on cores 10–19. These are their operators' allocations, not cores borrowed by this review. The gauntlet uses a different opening book and resignation threshold.

Keep the evidence levels distinct. The singular/IIR summaries are useful operator records, but a reconstructed boundary and an approximate acceptance note are not the same artifact as complete final stdout. Their match orientation and accounting should be reconciled before publishing precise numbers. The invalid earlier base-first singular run is explicitly archived separately and must not be mixed into the candidate-first result.

The gauntlet figure is a local anchor-based estimate, not an official CCRL rating. Its script excludes zero time forfeits here and reports a statistical interval that omits anchor uncertainty and time-control mismatch. Its fractional-outcome curvature also does not model opening-pair dependence explicitly. Treat the 24-point margin as the script's reported uncertainty, not a complete uncertainty budget.

**Deployment boundary:** #77 targets main, so its displayed PR diff includes singular plus IIR. Its match isolates non-pawn correction against `c727e67`; merging that PR into current main incorporates the earlier search stack too. Furthermore, its [default Makefile still embeds net12](https://github.com/LupeHiguera/ChessSI/blob/d0b9e4cf4e04a230013f8c618d07002324138704/Makefile#L18), while the recorded wins use net14. Promote and record the exact tested source/network combination deliberately. Do not add these conditional gains together or describe an ordinary default build as the tested binary.

## Findings requiring action

### P1: #72 can run an old inner runner and silently finish an incomplete test

The patched [queue checks out/rebases the candidate](https://github.com/LupeHiguera/ChessSI/blob/e34130e03d11619d6e755c0430d007f9af84315d/scripts/idea-queue.sh#L69), then invokes **that candidate's** [`scripts/run-idea.sh`](https://github.com/LupeHiguera/ChessSI/blob/e34130e03d11619d6e755c0430d007f9af84315d/scripts/idea-queue.sh#L78). It does not require the candidate to contain #72. The patched outer queue [accepts exit 1 as a completed candidate failure](https://github.com/LupeHiguera/ChessSI/blob/e34130e03d11619d6e755c0430d007f9af84315d/scripts/idea-queue.sh#L89).

For example, [#67's actual runner](https://github.com/LupeHiguera/ChessSI/blob/f7be5c19479f25d60495694711b7ecb55bcdf332/scripts/run-idea.sh#L19) is still the old version. An unavailable opening book makes its pre-screen fail, after which it exits 1. Under the patched outer controller on unchanged main, the line is marked done rather than left pending. Its old full-match path can also end with exit 0 after an incomplete match. Testing the new outer and inner scripts together does not exercise this mixed-version case.

**Repair:** require a vetted runner revision/hash in the candidate worktree and treat mismatch as infrastructure failure. Merging #72 and rebasing candidates onto that updated main resolves this particular path; custom stacked baselines still need the version check. Record orchestration and engine revisions separately.

A durable design can run a pinned orchestration bundle against an explicit candidate directory. Simply calling the parent's runner by absolute path is not sufficient: it changes directory relative to its own location and would test the parent checkout. Future tests should specifically use a new controller plus an old candidate, with unavailable-book and interrupted-match cases. [Existing stub review](https://github.com/LupeHiguera/ChessSI/pull/72#issuecomment-6502145316) remains useful within its tested scope.

### P2: #76 rewards capture-promotions in the wrong history entry

The [lookup](https://github.com/LupeHiguera/ChessSI/blob/7bf9f5b4f966f962ce56e1e8c1c14dfdd911851f/src/search.cpp#L145) and ordinary cutoff reward index the moving piece before the move. The [incoming-capture fail-low reward](https://github.com/LupeHiguera/ChessSI/blob/7bf9f5b4f966f962ce56e1e8c1c14dfdd911851f/src/search.cpp#L203) reads the piece now occupying the destination.

A `g7xh8=Q` capture of a rook therefore reads and normally rewards `[white pawn][h8][rook]`, but a completed child fail-low rewards `[white queen][h8][rook]`. Underpromotions have the same mismatch. This is a provenance defect, not an out-of-bounds access, and its playing impact has not been measured.

The older [#67 code](https://github.com/LupeHiguera/ChessSI/blob/f7be5c19479f25d60495694711b7ecb55bcdf332/src/search.cpp#L236) used a saved original mover. Removing continuation-history plumbing during the port lost that information.

**Repair:** retain the original mover, or recover a pawn of the incoming mover's color for promotion moves. A focused future fixture should check which entry is credited for normal captures, en passant and all capture-promotion types. Do not claim this rare path explains the capped -2.20 result.

### P2: older #67/#68 reward terminal positions as successful refutations

In [#67](https://github.com/LupeHiguera/ChessSI/blob/f7be5c19479f25d60495694711b7ecb55bcdf332/src/search.cpp#L530) and [#68](https://github.com/LupeHiguera/ChessSI/blob/de00ee1f0f6b22b197fba049b8954cf2351fdfa2/src/search.cpp#L548), the incoming-capture bonus runs on `bestMove == MOVE_NONE` before resolving `legalMoves == 0`.

A derived fixture is `k7/8/1pK5/1Q6/8/8/8/8 w - - 0 1`, followed by `b5b6`. Black is stalemated. With the actual incoming move context, cold TT and positive-depth child window `[-1,0]`, the code rewards the capture before returning zero, although zero is fail-high in that window.

Resolve terminal results first or require an appropriate nonterminal bound. **#76 already guards with `legalMoves > 0 && !excludedMove`**, so this is a reason not to revive the older branches unchanged. It is not a second terminal bug in #76.

### P2 integration hazard: #63's score bands conflict with older #67

The witness pass treats [score below 100,000](https://github.com/LupeHiguera/ChessSI/blob/36061f63dcfbac527f610a819ac0aed5926dc3f0/src/search.cpp#L724) as evidence that good captures are exhausted and promotes selected defenses to 95,000. Older #67 [adds signed capture history directly](https://github.com/LupeHiguera/ChessSI/blob/f7be5c19479f25d60495694711b7ecb55bcdf332/src/search.cpp#L180) to that band.

A SEE-nonnegative queen capture of a pawn with history -6,000 scores `100000 + 1000 - 4 - 6000 = 94996`. The witness pass can run before that good capture and put a promoted quiet ahead of it, changing the intended mechanism.

Use semantic move stages or shared disjoint score-band contracts when combining those older drafts. Test saturated histories. **#76's newer nonnegative tiebreak preserves the good-capture boundary**, so this is a conditional incompatibility of #63 with #67/#68, not a fault in #76's newer ordering. #77 does not include capture history.

## Three sharper experiments

### 1. Preserve capture-history resolution without changing material priority

#76's [mapping](https://github.com/LupeHiguera/ChessSI/blob/7bf9f5b4f966f962ce56e1e8c1c14dfdd911851f/src/search.cpp#L165) is:

`tiebreak = floor((history + 16384) * 31 / 32768)`

Every integer from **-528 through +528 maps to 15**. Thus histories -400 and +400 cannot change their tie, and a first depth-four reward of 16 has no ordering effect. The table is also halved at each search. This is a proven loss of resolution, not proof that the discarded distinctions predict good moves.

There is a second limit: two white knights capturing the same pawn on e4 share `[white knight][e4][pawn]`, so their histories are identical at any precision. Counting all equal-MVV-LVA pairs would overstate usable coverage.

**Smallest intervention:** preserve the current primary MVV-LVA key and SEE bands, but compare full history as a lexicographic secondary key. Keep updates and decay fixed. First fix the promotion provenance defect in both comparator arms.

**Gate:** count equal-primary captures with different history keys, unequal raw values erased by quantization, and actual ordering changes among moves that survive legality/SEE. Separate main and QS opportunities: [QS uses the same scorer](https://github.com/LupeHiguera/ChessSI/blob/7bf9f5b4f966f962ce56e1e8c1c14dfdd911851f/src/search.cpp#L302), so the existing package changes both. Advance only if coverage and held-out cutoff ordering justify the overhead, then use equal-time play.

This is a targeted adaptation, not a globally novel capture heuristic. [Stockfish uses full-resolution capture history](https://github.com/official-stockfish/Stockfish/blob/sf_17/src/movepick.cpp#L146), although its material/history combination differs from this proposed strict-secondary comparison.

### 2. Separate non-pawn information from stronger correction feedback

#77 [updates three entries with the same bonus](https://github.com/LupeHiguera/ChessSI/blob/d0b9e4cf4e04a230013f8c618d07002324138704/src/search.cpp#L173), then reads:

`correction = (pawn + (nonpawn_white + nonpawn_black)/2) / 16`

Starting at zero, `diff=16, depth=4` produces bonus 16. All entries become 16, so the new correction is **2 cp**, versus **1 cp** in the parent. The possible combined correction expands from **±64 to ±128 cp**. The retained 64-cp comment no longer describes the total.

This does not prove harmful double-counting. Training uses the residual against the combined corrected value, so entries can adapt together. The local H1 is valid evidence for the complete tested package. What remains unresolved is how much came from better positional generalization and how much from feedback strength/range.

**Control:** use the same three tables, weights and updates, but give the two extra tables the pawn key. Starting identically, all three entries remain equal for any fixed update trace; they introduce no new non-pawn information while preserving the duplicated feedback mechanism. Compare this with #77, then consider matched-step/range variants only if needed.

A fixed-event trace is a cheap predictive screen; live searches and equal-time matches must include changed feedback and hash/lookup costs. A simple multiplication of the existing rounded pawn correction is not necessarily an exact substitute because rounding, residual trajectories and storage differ. Stop attributing the gain to spatial information if the duplicate-key control explains it. The control is a new refinement of existing S09, not a new claim that non-pawn correction itself is novel.

### 3. Avoid full refresh for king moves that stay in a bucket

#71 currently rebuilds the friendly accumulator after every king move on [CPU](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/src/nnue.cpp#L261) and [GPU](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/gpu/datagen.cu#L299). Yet e1→e2 stays in the same K8 and K16 bucket; e2→e3 stays in K8; d1→e1 stays in both.

ChessSI's [piece feature mapping](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/src/nnue.cpp#L58) does not horizontally reorient every other piece when the king crosses d/e. Consequently, unchanged bucket identity leaves every unchanged piece row unchanged. Ordinary add/sub updates suffice, including all captured-piece rows.

Compare old/new friendly king bucket IDs; refresh only when they differ or the delta shape is unsupported. First verify both raw accumulator halves against full refresh with unsaturated, feature-dependent fixtures, including king captures, bucket crossings and undo. Preserve scores, moves and fixed-depth nodes. Count avoided refreshes by material and time the uninstrumented complete search/generator. Stop if dispatch overhead offsets the savings.

This is a concrete Known optimization with [Arasan prior art](https://github.com/jdart1/arasan-chess/blob/master/doc/programr.html). Its opportunity is specific to #71's current representation and remains conditional on that architecture becoming useful.

## Learning/GPU integration and review coverage

#71's [GPU match wrapper](https://github.com/LupeHiguera/ChessSI/blob/5f758cbce925975b0a91607977f30f5a9806611e/gpu/match.py#L62) rejects differing bucket counts, although the kernel already carries separate counts for the two networks. This is a capability restriction, not a wrong-result defect. Mixed counts at the same hidden width could be admitted after mixed-format CPU/GPU parity, color-swap and pause/resume checks. Repeating flat rows into bucketed format is a fixed-node workaround; it does not preserve the native flat network's memory/refresh costs for an efficiency comparison.

#71 and #74 also change overlapping kernel/host argument contracts. The [reported #74 parity](https://github.com/LupeHiguera/ChessSI/pull/74#issuecomment-6502791125) used flat net12. It does not cover the combined bucket/teacher-port source. Before combined data generation, check both native CSNN and nontrivial CSKB networks on the combined source, cold rescoring, persistent correction, slot reuse/reset, interrupted/resumed work, both match sides and SPSA parameters. This is an integration obligation, not evidence existing labels are wrong. Keep teacher manifests tied to exact source and network; #77's CPU win does not silently update #74.

| PRs | Scope and conclusion |
| --- | --- |
| #59 | Prior source finding retained: qs-TT includes a main-search same-key replacement change; unchanged head, capped result remains inconclusive |
| #60, #66, #75 | Singular/IIR code and dependencies rechecked; #75 supplies excluded-node IIR guard; local acceptance artifacts need the evidence qualifications above |
| #61 | Continuation indexing, null context, persistence and helpers inspected; no additional defect found |
| #63 | Witness integration hazard with old signed capture bands identified |
| #64 | Raw-eval caching, invalidation, stack padding and cut-node propagation inspected; no additional defect found; prior correction-drift hypothesis remains |
| #65 | Depth clamping, checking moves, confirmation and PV escalation inspected; no additional independent defect found |
| #67, #68 | Terminal reward issue identified; avoid importing older score bands blindly |
| #71 | All 14 changed-file diffs and relevant context reviewed; previous clipping/optimizer/test findings retained; new bucket-refresh opportunity |
| #72 | Actual mixed-version runner path reviewed; P1 above |
| #74 | All five changed-file diffs and relevant context reviewed; previous parity/cost findings retained; combined #71 integration remains untested |
| #76, #77 | New deltas, inherited stack and recorded results reviewed; promotion provenance and two causal follow-ups above |
| #13, #29, #56, #57, #62, #69, #70, #73 | Documentation/research PRs inventoried against earlier work; no fresh audit of #13's entire historical evidence bundle; older queue and forecast prose is a dated snapshot, not authority over current operators |

The old bucket clipping/Adam and auxiliary-initialization findings have not been rediscovered as new. No new global novelty claim is justified by this pass. The distinct new contributions are narrower mechanisms and controls that can make the next experiment informative.

**Recommended order:** preserve and publish the new result records with exact identities; address runner provenance before queue automation; correct capture-promotion credit before a capture retest; screen full-resolution ties and the correction control; pursue same-bucket refresh if the bucket architecture survives its existing learning gates. These are recommendations, not queue edits, claims or permission to consume a test slot.

Validation of this artifact: source/context and primary-source review, three delegated adversarial reviews, documentation-only diff, relative links and Markdown checks. Bench 69,980 is inherited from main and was not rerun.
