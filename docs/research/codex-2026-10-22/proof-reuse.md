# Reusing tactical proofs across related positions

Research date: 2026-10-22. Proposer and diagnostic author: GPT-6 (Codex). Status: Known broad method; one naive certificate rule rejected by a constructed counterexample. No engine implementation, queue claim, strength test or Elo result is attached to this proposal. This proposal was investigated during idea 9, whose check-evasion trial later failed and was reverted. See the [current research status](STATUS.md) for the active experiment.

The question is whether ChessSI can reuse a short forced-mate strategy after an unrelated part of the board changes. An ordinary transposition table needs the same position key. A proof cache would instead retain the conditions that make a strategy valid. The challenge is to make verification substantially cheaper than finding the strategy again, while preserving every legal defense and relevant history condition.

## Prior art changes the novelty claim

| Primary source | What is already established | Consequence for this proposal |
| --- | --- | --- |
| Ginsberg, [Partition Search, 1996](https://cdn.aaai.org/AAAI/1996/AAAI96-034.pdf) | Dependency analysis generalizes a transposition-table entry from one position to a set of positions with a reusable result. The paper explicitly motivates this with repeated chess refutations, but reports its experimental results in bridge. | Reusing a proof over partly different boards is Known, including its chess motivation. A new name or mask encoding would not establish novelty. |
| Shih et al., [A Local-Pattern Related Look-Up Table, 2022](https://arxiv.org/html/2212.13922v1) | A relevance-zone pattern table stores winning patterns and uses a radix tree for matching. The work treats Go and Kill-all Go; it explicitly leaves repetitions outside its scope. | Local proof patterns and specialized lookup structures are Known. Their correctness and speed do not transfer automatically to chess or solve history dependence. |
| Lin et al., [Relevance-Zone Reduction in Game Solving, 2025](https://arxiv.org/html/2510.00689v1) | Repeated constrained solving shrinks reusable zones, with fixed work limits and a pattern table. Experiments concern 7x7 Killall-Go. | Learning or searching for smaller proof conditions is also established. A chess-specific implementation would need its own measured contribution. |

This is a bounded prior-art review. It does not establish that a future chess variant is new, and the Go/bridge results are not evidence of a chess strength gain. Search existing chess implementations and historical analogy methods before attaching a novelty label to a concrete implementation.

## A cheap rejection of the obvious mask

Consider a certificate that records the played move's path, both kings and their neighboring squares, plus material counts, side, castling rights, en-passant state and clocks. The following constructed legal positions have identical values for all of those recorded conditions:

| Position | FEN | Result after `h1h7` |
| --- | --- | --- |
| A | `7k/7r/6K1/8/8/8/8/r6Q w - - 0 1` | `Qxh7#`; no legal defense |
| B | `7k/r6r/6K1/8/8/8/8/7Q w - - 0 1` | `Qxh7+`; the sole legal defense is `a7h7` |

Only Black's remote rook moved from a1 to a7. Both squares lie outside the mask. The queen on h7 remains supported by White's king on g6, but that does not prevent the rook from capturing it while protecting Black's king. Material equality and unchanged king neighborhoods therefore do not certify the original mate.

The exact mask was `h1 h2 h3 h4 f5 g5 h5 f6 g6 h6 f7 g7 h7 g8 h8`. Pinned python-chess 1.11.2 checked position validity, move legality, equal recorded conditions, checkmate in A and the complete legal reply set in B. These are constructed counterexamples, not positions sampled from the running match. They invalidate this particular mask rule; they do not disprove sound dependency tracking or establish the full minimax value of B.

Local evidence is in `engines/qsearch-validation/proof-reuse-research-01/`, including the source and `result.json`. The source SHA-256 is `3107177f469cc464978a33e4cd3f126a527cf31eddfa884557df7e7a2c6128db`. The diagnostic ran on CPU 19 without launching an engine or changing the live match. The FENs and exact mask above make the rejection independently reproducible.

## A conservative implementation contract

Start with short, bounded forced mates. Do not reuse arbitrary centipawn bounds from local patterns: the current evaluator depends on the entire position, and a future neural evaluator does too.

1. Store an attacker strategy and the defender branches required to establish it. At attacker nodes, the prescribed move must be legal. At defender nodes, generate the complete current legal reply set and verify a continuation for every reply. A new or unsupported reply invalidates reuse; an unavailable attacker move does likewise.
2. Replay with the current full state and history. Apply correct terminal, repetition and clock semantics at every node. Castling, en passant, promotion, discovered attacks, pins and remote interpositions must be covered by legal verification, not inferred from the local mask. A bounded certificate must not silently accept a cycle.
3. Treat a verified forced mate within D plies as a bound on mate distance. It does not establish that no shorter mate exists. Normalize the score for the current ply and preserve the correct bound direction; do not store an exact mate score merely because one strategy was verified.
4. Initially use pattern matching only to find a candidate certificate. A cache hit supplies no cutoff until full verification succeeds. On failure or verification budget exhaustion, continue ordinary search. Candidate lookup, replay and failed attempts all consume the same search budget.
5. A stronger static guard that can replace replay needs a sound dependency argument covering absent defenses as well as the moves that occurred. Random board mutations and oracle comparisons can falsify a guard, but passing them cannot prove its universal correctness.

A move-ordering hint from a partially matching certificate is a separate, simpler control. It may obtain much of the benefit without a cutoff proof. Do not combine the hint policy and certified cutoffs in one initial strength patch.

Correct draw handling and bound semantics are prerequisites. The existing quiescence draw omission recorded in [the qsearch report](qsearch.md) must be resolved independently before its outputs become trusted certificate data.

## Stop cheaply if reuse cannot repay its cost

The first useful diagnostic is opportunity measurement, not a pattern-table implementation. Freeze a development corpus and baseline; count completed short-mate proofs, their construction work, subsequent different-full-key candidate matches, and verification work. Exclude ordinary full-key TT hits from the claimed new benefit. Group analysis by whole game/opening, and keep a later holdout untouched.

Compute an optimistic saved-work estimate on the frozen trace using disjoint subtree intervals. Never sum nested proof subtrees twice or count a certificate before it was available. Even this is only a counterfactual screen: cutoffs change future search order and TT contents. A positive estimate is not a measured runtime saving. The existing count of terminal checkmates alone provides no useful upper bound on recoverable proof work.

Charge proof capture, indexing, matching, verification, failed matches and memory effects. Keep the ordinary production TT as a baseline, then compare augmented search against a TT-only control receiving the entire combined memory allowance and a hint-only control with that same total allowance. Freeze a minimum worthwhile end-to-end saving before the holdout evaluation. If even the optimistic estimate cannot pay measured overhead, stop; if verified reuse disagrees on any required mate claim, stop and retain the counterexample.

Only after those gates should a separately claimed engine experiment receive the normal perft/search checks, fixed-time SPRT and longer-time confirmation. A successful result would show useful chess proof reuse. It would not establish AGI.

## Research record

| Date | Model | Attempt | Outcome | Charged work / next decision |
| --- | --- | --- | --- | --- |
| 2026-10-22 | GPT-6 (Codex) | Played-path and king-neighborhood mask, with material/state metadata | Rejected by the remote-rook counterexample | Two constructed positions, legal move/reply enumeration; zero engine searches or games |
| 2026-10-22 | GPT-6 (Codex) | Fully reverified short-mate strategy reuse | Proposal only; broad method Known | No implementation or measured benefit; opportunity screen and draw prerequisites first |
