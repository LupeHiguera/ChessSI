# Reviewable RFP experiment evidence

Recorded while the RFP match was running on 2026-10-22. These files are evidence artifacts; they do not apply an engine change to this research branch. See [the experiment report](../../rfp.md) and the benchmark log for later outcomes.

- `rfp-engine.patch` reconstructs the tested RFP candidate from accepted baseline `a8eebea2e6ec78d223745d7ee64fe8b0dd777325`, including the regression test that was untracked during the match launch. It also includes the workspace's generated-config ignore entry.
- `first-pawn-witness.patch` applies **after** that patch and reconstructs the isolated optimization. It was not used in the live match.
- `experiment.json` records attribution, settings, signatures and per-file hashes. Patch application reproduced every listed source byte at both stages; details are in `patch-verification.json`.
- `optimization-checks.json` retains the correctness gates and all six timing pairs. A short benchmark improvement is not an Elo result.
- `move-disagreement-cases.json` supplies the complete starting FENs and move histories for all three different root choices. The reference and matched-depth JSON files retain every result and node accounting. These selected, reused development cases are not held-out strength evidence.

For reproduction, use a separate clean checkout at the stated baseline. Keep the evidence files outside that checkout or record their absolute paths before switching revisions. Apply and inspect one stage at a time:

```sh
git apply --check /path/to/rfp-engine.patch
git apply /path/to/rfp-engine.patch
taskset -c 14-19 make -j6 -B test
taskset -c 14-19 ./chesssi bench
# Expected: 35 perft and 15 RFP checks passed; bench 11112214.

git apply --check /path/to/first-pawn-witness.patch
git apply /path/to/first-pawn-witness.patch
taskset -c 14-19 make -j6 -B test
taskset -c 14-19 ./chesssi bench
# Expected: the same checks and bench signature.
```

The byte-reconstruction check added here is not a new performance or strength run. Full local transcripts, source snapshots, sanitizer logs, the larger legal-position corpus and match archives remain under `engines/rfp-validation/` in the Astra worktree. The first invalid diagonal-pin test fixture and its correction remain in that local archive; the optimization source itself did not change during that correction.
