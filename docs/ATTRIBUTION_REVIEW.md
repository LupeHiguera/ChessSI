# Documentation and attribution review — 2026-11-02

Reviewed by GPT-6 (Codex), at main `014dd979e612b5ebd1e509fade25f94ea61537a7`.
Scope: public README, rating bulletin, development guidance, network/GPU docs, the experiment log,
selected research reports, source attribution comments, evaluation tables, test positions and setup
dependencies. This is a documentation/provenance review, not an exhaustive source-similarity audit.

## Corrections made

- Added [CREDITS.md](../CREDITS.md), with separate entries for included material, established methods,
  research references, testing resources, dependencies, fonts and project roles.
- Replaced the claim that every idea gets thousands of games with the actual mix of offline gates,
  screens, stopped tests and completed SPRTs. Model attribution remains intact; this uncontrolled
  project history is not a fair ranking of model capabilities or evidence of AGI.
- Qualified novelty claims. Successful tuning establishes an improvement in the tested engine;
  it does not establish a new optimizer, first use of GPU chess search, or superiority to CPU tuning
  at equal cost. Auxiliary heads have KataGo/Lc0/multi-task-learning precedents. Historical log rows
  and numerical results are retained, with dated interpretation notes.
- Distinguished the Nov 1 local rating estimate for `8912405` from the newer default build.
  Updated the stale net12/net14 summaries to net22-h768 and the recorded bench 50868 at the reviewed
  main revision. These are existing results, not measurements performed by this review.
- Made explicit that external opening books and inherited evaluation techniques exist alongside
  the own-games/own-search-label training policy. Self-generated labels do not mean all ideas,
  tables, tools or starting positions originated here.
- Restricted CPU/GPU parity claims to the tested revisions/configurations. Corrected the description
  of UHO as balanced positions: tests pair the colors of deliberately unbalanced openings.
- Added a provenance rule for future agent changes and clarified the original roadmap's speculative
  timelines. Kept the owner's two-PC/two-GPU constraint and decision to defer promotion to 3700+.

## Follow-up requiring evidence

| Item | What the review established | What remains |
| --- | --- | --- |
| PeSTO material in `src/eval.cpp` | The file contains Friederich's published values, already named in its comment. The [CPW presentation](https://chessprogramming.org/PeSTO%27s_Evaluation_Function) credits the Koziol/TSCP lineage and carries CC BY-SA 3.0. | Record the exact source/revision used and the applicable reuse basis for these tables and any adapted code. No separate MIT-compatible permission was located in this review. Do not infer one from other engines' usage. Resolve the distribution terms or replace the material before representing the distribution as wholly MIT. This review leaves the project license unchanged. |
| Source-reference implementations | Search comments identify Stockfish, Caissa, Alexandria and Stash; SPSA names fishtest's update/schedules. The PRNG is the widely used xorshift64* construction. | Trace introducing commits/session records to exact upstream revisions and compare any adapted portions, preserving notices where required. These references alone neither establish copying nor certify an independent implementation. No blanket “clean-room” or “no copied code” claim is justified by this review. |
| Books | Setup fetches two named archives from official-stockfish/books. They are external opening resources. | Record archive hashes, contributor history and redistribution terms if included in a release or dataset. Credit Pohl's UHO method without assuming he alone assembled the particular Lichess file. |
| Test positions | `tests/perft.epd` names CPW; the first six bench positions overlap that corpus. | Preserve the per-position credits available upstream and trace the remaining eight bench positions if records exist. Do not attribute all 14 positions to a guessed source. |
| Python tooling distribution | `nnue/extract_pgn.py` imports python-chess; the [upstream README](https://github.com/niklasf/python-chess) identifies GPL-3.0-or-later. | Check the actual package versions and obligations for any redistributed training/tooling bundle; an MIT label on ChessSI does not replace dependency notices. |
| Historic claims | Some reports and log rows retain labels such as “Novel” or “Known + Novel.” | Read them with the dated correction and limited prior-art scope. A later stronger originality claim needs documented sources, dates, inaccessible areas and the precise difference from prior work. |

Unknown provenance is recorded as unknown. The review does not accuse an upstream project or a
ChessSI contributor of misconduct, and does not turn an unverified possibility into a copying claim.

## Public descriptions supported by this record

ChessSI is an experimental UCI engine developed mostly with AI assistance. It implements established
computer-chess methods, trains networks on its own games/search labels under the documented policy,
and records experiments, including failures. Its public claims should name the tested commit and
network, test conditions, game count, uncertainty and whether the result was measured locally or
issued by an independent rating list.

The 3700+ outreach target is an owner preference, not a CCRL entry requirement or a forecast. A local
rating estimate must be reproduced under stated conditions; adding individual SPRT gains is not a
rating measurement. Attribution and reproducible artifacts remain useful regardless of rating.
