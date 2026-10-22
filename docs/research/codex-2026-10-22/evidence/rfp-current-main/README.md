# RFP diagnostics on current main

These artifacts preserve two diagnostics of the RFP candidate based on accepted commit `f801f8c519b0fe5b3d009b8f0664b049409a1188`. They report **no accepted strength result** and apply no engine change to this research branch. The first-pawn variant was isolated from the strength-match candidate.

The [context result](context/result.json) and [independent verification](context/peer-verification.json) cover 128 reused development roots and 384 parent transcripts. All parent traces matched. Of 979 sampled cutoffs, 267 occurred after a reduction and 19 under a null ancestor; all 979 probes completed and none crossed below beta. Warm transposition tables may contain RFP-derived bounds, and the other search approximations remain active. This is a bounded diagnostic sample, not a safety proof, population estimate or Elo result. The controls also retain two constructed contradictions; those are separate from the sampled ordinary-search contexts.

The [first-pawn result](first-pawn/result.json) and [independent verification](first-pawn/peer-verification.json) passed 35 perft, 17 boundary, 17 sanitizer cases, 2,203 exact-witness cases, benchmark 609035, and 128 full-history trace comparisons (1,181 completed iterations). Six predeclared alternating pairs each contained 32 default benches per binary. Median reported search time was 2534.0 ms versus 2476.5 ms, a 2.27% decrease; median whole-process bundle wall time increased 1.03%. One search-time pair differed by only 3 ms. These six bundles on a shared machine do not establish a general speed gain or playing strength.

## Reconstructible sources

- `rfp-engine.patch` reconstructs the current candidate from the stated baseline, including the 17-case regression test. `candidate-source.patch` and `tests-rfp.cpp` retain the exact separately captured launch artifacts from which the complete patch was assembled.
- `first-pawn-witness.patch` applies after `rfp-engine.patch`. It changes only the first-legal-move implementation with the preserved 12-line shortcut; expected default bench remains 609035.
- `context-reference.patch` and `context-observer.patch` each apply independently after `rfp-engine.patch`. The observer additionally uses the exact `context/audit_members.inc` and `context/controls.cpp` at its source-root level.
- `patch-verification.json` records fresh byte-for-byte reconstruction: all 21 candidate inputs, all 21 first-pawn inputs, and all 18 source files in each context build. This check ran no engine or compiler.

Use a separate clean checkout at the stated commit. Keep this evidence outside that checkout, then apply one stage at a time:

```sh
git apply --check /absolute/path/to/rfp-engine.patch
git apply /absolute/path/to/rfp-engine.patch
# For the first-pawn variant only:
git apply --check /absolute/path/to/first-pawn-witness.patch
git apply /absolute/path/to/first-pawn-witness.patch
```

## Exact archived harnesses

The collectors, controls and verification scripts are exact archival copies, **not portable runners**. They contain original absolute paths, fixed deadlines, expected hashes and local artifact dependencies. A separately planned reproduction must supply the exact input corpora and adapt its paths, outputs and deadline explicitly. `context/label_budget.py` preserves the shared UCI helper; python-chess was 1.11.2 at commit `3516d7c6c0879af724c2855fac5a304a4ef40949`.

Plans and their amendments remain separate and unchanged. The context preflight typo correction, failed missing-dependency launch and archived optimization-guard checks are retained. The first-pawn plan preserves the earlier invalid-fixture correction and uses the corrected oracle. The context peer verifier and stdout were archived after their original completed read-only execution; `context/peer-archival.json` describes that provenance precisely.

The first-pawn release builds used `-O3 -march=native -DNDEBUG`. Make/test recipes inherited CPUs 14-19, compiler processes used CPU 19, and direct witnesses, trace queries and timing invocations used CPU 19. The shared machine was also running the five-game strength match; WSL scheduling does not attest one physical core type.

## Local raw artifacts and manifest

`local-artifacts.json` gives exact source paths, sizes and SHA256 identities for the full 128-root history corpus, corrected 2,203-position witness oracle, 979 context samples, complete trace tables, 387 benchmark invocation records, 391 command records and the large original hash inventories. It also records counts, total sizes and canonical index digests for all 384 raw context transcripts, 128 first-pawn raw traces and 1,173 command stdout/stderr/metadata files. These complete raw artifacts remain under `engines/rfp-current-main-validation/` in the Astra worktree; they have not been silently truncated into this bundle. The prior first-pawn inventory covers 1,487 files before the later peer-verification additions.

Consequently this compact bundle supports source reconstruction and review of the recorded conclusions, but does not contain every input or raw output needed for an independent empirical rerun. No engine binaries, opening book, PGN, live log or full raw corpus is included. `manifest.json` distinguishes exact copies from generated patches and metadata, records their real local source paths and hashes, and is bound by `manifest.sha256`.
