# Updated-main RFP terminal evidence subset

This bundle preserves exact bytes from the audited `10+0.1` RFP comparison against accepted main `f801f8c519b0fe5b3d009b8f0664b049409a1188`. It ended normally at 17:57:28 UTC on 2026-10-22 with explicit H1 after 802 games / 401 complete pairs: 303 wins, 148 losses, 351 draws. Reported logistic Elo was +68.00 +/- 16.54 and normalized Elo +101.49 +/- 24.05. All 802 games, 88,397 legal plies and 41 reports reconciled; there were no completed unpaired games.

**This is a selected evidence subset, not a standalone full-replay package.** PGN, engine/manager binaries, opening book and full source/dependency archives remain local. `local-artifacts.json` records the omitted terminal-snapshot artifacts and the book with their paths, sizes and recorded hashes. The book entry explicitly identifies its declared hash and metadata sources; it is not a new verification of historical bytes loaded by the manager. Additional implementation dependency identities are recorded inside the copied audit result. Full legal replay requires the omitted PGN and pinned audit dependencies.

- `stc/` contains the original extraction, independent audit result and all report reconciliations, terminal guard state/plan, original snapshot manifest and digest, runner exit, exact collector/auditor source, and frozen terminal log/configuration.
- `transition/` contains the eligible terminal preflight and before/after preservation proof for moving completed STC outputs before LTC. These records establish the recorded transition, not an LTC outcome.
- `ltc-launch-only/launch-plan.json` is the immutable plan for the independent `60+0.6` confirmation launched at 18:07 UTC. It is **launch provenance only**, with no LTC decision or acceptance. Its source, baseline and binaries match the STC candidate; no first-pawn optimization is included.

The `manifest.json` inventory records the SHA-256, byte count and original source path of every copied file. Copied JSON, logs and Python sources are unchanged; generated inventory/README files are marked separately. `manifest.sha256` binds the bundle manifest. The original `stc/terminal-manifest.json` describes a larger local archive whose paths are intentionally not rewritten for this subset; its digest file binds those original bytes.

No engine query, game, build or legal-replay rerun was performed to create this bundle. Copying and byte/hash verification do not independently prove the experiment's statistical validity, historical source-to-binary correspondence or adjudication accuracy. The recorded STC pass is unpromoted pending the separate confirmation and repository acceptance process. Do not pool its estimate with the earlier result on a different baseline.

See the [full result and current confirmation status](../../rfp.md#final-result-on-updated-main). The separate [implementation/context evidence bundle](../rfp-current-main/README.md) remains unchanged.
