# Sparse accumulator update: predeclared feasibility screen

Date: 2026-10-24. Owner: Astra / GPT-6 (Codex). Mathematical/method review:
GPT-6 Astra (ultra). Base: ea8a13d5635808b3a7d43f3d6db2aa68dbe484f3.
This is a standalone synthetic kernel study. No engine source, network or trainer changes.
No Elo estimate, novelty claim, or strength acceptance is possible from this screen.

## Question and controls

Does 32-neuron block sparsity save update time once the child accumulator is fully written?
ChessSI uses distinct accumulators per ply: an unchanged block still needs copying. The dense
control is the fused int16 update from src/nnue.cpp, with the same masked weights, runtime
hidden size 256, compiler settings and parent/output storage. The sparse version computes the
union of all changed row masks inside each timed call. An inactive block copies the parent;
an active block executes the fused dense arithmetic. A copy-only kernel is a deliberately
non-equivalent optimistic reference: it must not be reported as a correct candidate.

Synthetic masks have occupancy q in {0, 0.125, 0.25, 0.5, 1}. Two predefined structures:
independent feature-row masks, and masks tied across the 64 squares of each colored piece type.
The latter is an optimistic correlation model that limits network expressiveness. These are
synthetic weights, not sparsified versions of the accepted network. Feature indices respect
both perspective encodings; move-shaped quiet, capture and castle cases are measured separately.
They are not legal game/search traces and have no asserted production frequency.

Use 2048 operation descriptors over 64 parent and 64 child slots, one full 768x256 weight table,
32 passes per sample (65536 calls), seven fixed alternating dense/sparse paired samples per case,
and a copy-reference sample each round. Warm up before measurement. Keep checksums observable
and consume them outside the measured section. Report all raw samples, order, checksums and
observed changed-block union fractions, including zeros and slow cases. Do not rerun because of
an unfavorable result. Correctness or harness defects may require a separately disclosed revision.

## Correctness and decision

Before timing, compare every child element against an independent widened scalar calculation
and the dense control, including unchanged blocks. Check source buffers and guards. Values must
stay safely inside int16, including intermediate additions/subtractions. Run sanitizer checks
before the optimized measurement. Both masks must produce identical candidate/control outputs.
Compile a production-shaped control with runtime loop bounds; avoid making only one kernel's
hidden size a compile-time constant. Keep row-pointer setup in both timed kernels.

Primary gate: q=0.5 with independent masks must show at least 10% lower median paired time ratio
(sparse/dense <=0.90), and at least six of seven pairs faster, in BOTH quiet and capture cases.
Failure means this straightforward kernel is not ready to motivate sparse-network training.
Other densities, tied masks, castles and copy reference are descriptive controls. A pass only
justifies a later study of attainable masks and accuracy; it does not authorize accepting a
network or engine patch. Do not select a secondary condition after seeing outcomes and call it
a primary pass.

Resource scope: WSL Ubuntu, CPU 19 only, no GPU; Claude retains CPUs 0-13. Keep artifacts under
this Astra worktree. Record compiler, CPU affinity, source/binary hashes and raw CSV. Accepted
main's unmodified correctness suite and bench will be checked before any research commit.

## Limits and prior art

The benchmark is conditional on synthetic masks. It does not include pruning/training accuracy
loss, sparse-format decoding/compression, refresh, output evaluation, real search locality or
whole-engine scaling. Dense storage is retained, so it tests arithmetic skipping, not model
compression. Small repeated traces may favor branch prediction. It is neither a proven upper
bound for all sparse implementations nor proof that sparse NNUE is impossible if it fails.

Broad delta computation is Known: Neil et al., ICML 2017,
https://proceedings.mlr.press/v70/neil17a.html . SIMD-aware structured pruning is Known:
Yu et al., ISCA 2017, https://homes.luddy.indiana.edu/lukefahr/papers/jiecaoyu_isca17.pdf .
The narrow proposal is to train masks for unions of chess feature changes while preserving
per-ply copying. Its novelty is unestablished. No claimed paper speedup transfers to ChessSI.
