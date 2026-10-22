# Plan of attack

Repo copy of the "Chess Engine Plan of Attack" doc (2026-10-21), so every agent can read it.

This preserves the original 2026-10-21 plan. Its timelines, rating ranges and checkboxes are historical planning assumptions. The engine, test infrastructure and experiment log are now in use; see [research status](research/codex-2026-10-22/STATUS.md) for completed work, measured results and next decisions. The "1 year+" row does not provide an evidence-based estimate for matching Stockfish.

Apply the evidence distinctions in the [research workflow](RESEARCH_WORKFLOW.md): controlled matches measure playing strength under a declared protocol; novelty requires a precise mechanism and comparison with prior art. A strength gain can reproduce a known method, and a novel proposal can fail. Establishing AGI would require evidence beyond chess, even if an engine matched or improved Stockfish.

## Goal and success criteria

Build a chess engine with AI doing most of the development, and use it as a personal benchmark of what AI
can actually do in research.

- **Reproducing the state of the art:** getting close to top engines with known techniques (neural
  evaluation, modern search pruning). This shows AI can implement known methods quickly, not that it found
  new ones.
- **A genuinely new method:** outscoring Stockfish over a full match at a fixed time control, or finding an
  idea that still gains Elo when added to Stockfish itself.
- **What counts as proof:** one game proves nothing. A claim needs hundreds to thousands of games at a fixed
  time control with balanced openings.

Stockfish is the bar. It absorbs every good idea, tests each change over tens of thousands of games, and
combines deep search with NNUE. It won the TCEC Season 29 superfinal 59–41 against Reckless, but Reckless
still won 23 games: single wins happen, and outscoring Stockfish over a match is the hard part.

## Roadmap

| Phase | When | Work | Rough rating |
| --- | --- | --- | --- |
| 1 · Working engine | Weeks 1–2 | Move generation, UCI, basic search | ~2000 |
| 2 · Classical engine | Months 1–2 | Caching, move ordering, pruning, tuned evaluation | ~2800–3000 |
| 3 · Neural evaluation | Months 2–5 | Self-play data, networks trained on the RTX 5080 | ~3200–3400 |
| 4 · Refinement | Months 6–12+ | Parameter tuning, bigger networks, more data | ~3400–3500+ |
| 5 · The final gap | 1 year+ | The last 100–200 Elo, where strong engines stall | Stockfish level |

AI speeds up the coding in phases 1–2; from phase 3 on, compute sets the pace. Ratings are rating-list Elo
and ballpark only.

## Hardware

| Machine | Role |
| --- | --- |
| Core Ultra 7 265K (20 cores) | Test matches and training-data games, ~2,000–3,000 fast games an hour |
| RTX 5080 | Main network trainer |
| RTX 5060 Ti | Second training run or experiments |
| MacBook Pro M2 Max | Extra test capacity, about half a 265K |
| Second 265K (optional) | Build only once tests sit queued for days |

At 60 hours a week the 265K plays about 100,000–150,000 fast games (10+0.1) or 15,000–25,000 long games
(60+0.6). Resolution: 1,000 games ≈ ±20 Elo, 10,000 ≈ ±7, 100,000 ≈ ±2.

## Testing method

- **Self-play SPRT** of each change against the previous version at 10+0.1; confirm winners at 60+0.6.
- **OpenBench** to pool every machine once more than one is testing.
- **Consistent hardware:** one machine and core type per test, or fixed node counts.
- **Balanced openings:** always use an opening book (UHO_Lichess_4852_v1).
- **Right opponents:** engines near our level, or Stockfish with limited strength, until we are close.

## Next steps

- [x] Set up the engine repository
- [x] Write move generation and verify it against known position counts (`make test`)
- [x] Add UCI and a basic search
- [ ] Set up Claude Code (and Astra) on the 265K; build and play the first games
- [ ] Install fastchess and the opening book; run the first SPRT (`scripts/sprt.sh`)
- [ ] Install OpenBench and connect the PC, then the MacBook
- [ ] Start the benchmark log and record every idea from the first change (`docs/IDEAS.md`)
- [ ] Revisit the second PC once tests sit queued for days
