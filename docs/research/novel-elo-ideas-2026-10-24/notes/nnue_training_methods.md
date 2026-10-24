# Novel NNUE training-side methods for ChessSI (research notes, 2026-10-24)

Scope: ideas on the training side only: losses, targets, auxiliary tasks, regularisation, distillation,
data weighting, curriculum, optimiser and weight averaging, quantisation-aware training, distributional
targets and symmetry losses. Every experiment below uses only ChessSI's own games, searches and
networks.

Method and access notes:
- Read-only shallow clones were grepped: nnue-pytorch `ed84cc1` (17 Oct 2026), bullet `579b78b`
  (20 Oct 2026) and lczero-training `7c20696` (23 Oct 2026). KataGoMethods.md was fetched from GitHub.
- arxiv.org and talkchess.com are blocked by this environment's proxy (403 / ENOTFOUND). Papers on
  arXiv are cited by their arXiv or venue pages, with content taken from search-engine abstracts and
  snippets, never from the full text. TalkChess, fishtest and Discord could not be searched directly.
- ChessSI's own files are cited from branch `claude/artifact-access-issue-ug96zp` of
  github.com/LupeHiguera/ChessSI.

## Ranked list of training-side candidates (the objective)

### Takeaway
Nine candidates, ranked by expected Elo × confidence ÷ CPU cost. CPU for SPRTs is the bottleneck, so
ideas that keep the main target unchanged rank higher: their validation loss stays comparable and they
can be screened on the GPU before any games are played. The four best all extend the passed
auxiliary-head mechanism or the data supply:

| Rank | Idea | Verdict | Expected Elo (central) | Confidence | GPU-screenable |
| --- | --- | --- | --- | --- | --- |
| 1 | HL-Gauss (histogram cross-entropy) training-only auxiliary head | Novel for NNUE; partially known (Lc0 has a one-hot categorical training head) | 0 to +15 (+5) | low-medium | yes |
| 2 | Gradient routing: the game-result part of the loss trains only the output layer | Novel (not found) | −10 to +15 (+3) | low; also a cheap diagnostic | yes |
| 3 | Ensemble-teacher distillation head: average of several wider ChessSI nets, GPU only | Partially known | 0 to +15 (+5) | low-medium | yes |
| 4 | Exact left-right mirror augmentation of positions with no castling rights | Partially known (standard in Go; not found for NNUE) | 0 to +12 (+4) | low-medium | yes |
| 5 | λ-return (TD(λ)) in place of the raw game result in the 25% term | Partially known (TDLeaf, KataGo auxiliary heads) | −5 to +10 (+3) | low | no (target changes) |
| 6 | Root-sibling bounds with a hinge loss (TreeStrap(αβ)-lite) | Partially known (TreeStrap 2009) | −10 to +15 (+3) | low | mostly |
| 7 | Iterative-deepening trajectory auxiliary heads (score at depths 1..D) | Novel (not found) | 0 to +8 (+2) | low | yes, needs new data |
| 8 | Sharpness-aware minimisation (SAM) in the last epochs | Novel for NNUE (not found) | −3 to +6 (+1) | low | yes |
| 9 | Reducible-holdout-loss (RHO-LOSS) weighting, a fix to the queued "weight by abs(eval − score)" idea | Partially known (Lc0 diff focus, KataGo surprise weighting) | −5 to +8 (+1) | low | yes |

The "Known backlog" at the end of this section lists techniques already in other trainers. One of them
has high practical value: down-weighting or annealing away the PeSTO-era generation-1 labels, which are
37.2M of net8's 91.3M positions.

### Cited Findings
- ChessSI exports the last epoch of plain Adam with a cosine schedule. The loss is MSE between
  sigmoid(output) and 0.75·sigmoid(score/400) + 0.25·result. Optional training-only heads exist
  (`--aux-weight` with `--future-plies`, `--policy-weight`, `--teacher`). Weights are clamped to ±1.98,
  with QA=255 and QB=64 — [ChessSI nnue/train.py](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/nnue/train.py)
- ChessSI's datagen writes only `fen | whiteScore | result`, for positions that are quiet, not in
  check and without a mate score. It records no static eval, no iteration scores and no root-move
  bounds — [ChessSI src/datagen.cpp](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/src/datagen.cpp)
- Auxiliary-head results. On 38.5M positions, validation went 0.00672 → 0.00661 and the head won
  **+53.2 ± 15.6**. On 47.4M positions with the 8-ply head, validation went 0.00659 → 0.00651 and the
  head won **+34.6 ± 12.2**. Other heads on the same data: own search score 0.00652 vs 4-ply 0.00653
  (no head 0.00662); result-only head 0.00717 (much worse); policy head worse at every weight;
  born-again teacher 0.00674 → 0.00671. At h512 the gap is larger, 0.00712 vs 0.00694 — [ChessSI docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- λ results: `--lambda 1.0` (no game result) scored −80.4 ± 18.7, and `--lambda 0.6` was level at
  +1.8 ± 13.4. Eight output buckets improved validation 0.00653 → 0.00650 but scored −0.7 ± 14.7 over
  1,002 games. h256 on 23M positions overfits after about 10 epochs — [ChessSI docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- SPRT lengths in ChessSI's log: +43.1 decided after 1,208 games, +34.6 after 1,502, +22.2 after
  2,212. A +6.0 ± 4.7 test was still undecided after 9,398 games, and a −2.7 test took 11,690 games
  to fail — [ChessSI docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)
- net8's data is 37.2M generation-1 positions (PeSTO engine, `d574e70`), 12.4M generation-2 (net4),
  26.8M generation-3 (net6), 20.3M generation-4 (net7) and 2.6M from SPRT games — [ChessSI nets/README.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/nets/README.md)
- For the external prior art behind each verdict, see the cited findings under the four key questions
  below. Each card in the next subsection repeats its key links.

### Inferences

**Screening economics.** From ChessSI's two matched auxiliary-head pairs, a validation drop of
0.00001 was worth roughly +4.5 Elo (−0.00011 gave +53, −0.00008 gave +35). Read this only as a
same-target, same-data, no-NPS-cost rule of thumb. Output buckets broke it: −0.00003 in validation,
about 0 Elo. Even so, it suggests a −0.00002 validation gain (≈ +9 Elo) as the bar for spending SPRT
games. At about 2,500 games an hour, the log above implies roughly 1 h of the full PC for a +20 Elo
idea, 2–3 h for +10 and 4–8 h or more for +5. A +1 to +3 idea is rarely resolvable. Ideas 1–4 and 7–9
can therefore be tried in many variants on the GPU first, while idea 5 needs games for each variant.

#### 1. HL-Gauss histogram auxiliary head (training-only, dropped at export)
1. **Idea.** Add a training-only linear head 2H → K (K ≈ 51) on the accumulator. Train it with
   cross-entropy against a Gaussian-smoothed histogram (HL-Gauss) of a clean target: the position's
   own search score in win-probability space, or the 4-ply target. It can sit next to the existing MSE
   auxiliary head or replace it.
   - Field: distributional regression and deep RL. Imani & White, ICML 2018, introduced the histogram
     loss ([mlanthology](https://mlanthology.org/icml/2018/imani2018icml-improving)). Farebrother et
     al., "Stop Regressing", ICML 2024 oral, introduced HL-Gauss
     ([arXiv 2403.03950](https://arxiv.org/abs/2403.03950),
     [ICML](https://icml.cc/virtual/2024/oral/35498)). Ruoss et al. used win-probability bins in
     searchless chess ([arXiv 2402.04494](https://arxiv.org/abs/2402.04494)).
2. **Prior art: Novel for NNUE, partially known overall.**
   - Lc0's trainer has an optional categorical value head that Lc0's export format does not include,
     so it is training-only. It uses plain one-hot buckets of Q with softmax cross-entropy, not
     Gaussian smoothing
     ([value_head.py](https://github.com/LeelaChessZero/lczero-training/blob/master/src/lczero_training/model/value_head.py),
     [loss_function.py](https://github.com/LeelaChessZero/lczero-training/blob/master/src/lczero_training/model/loss_function.py)).
   - Nothing similar was found in nnue-pytorch or bullet (grep), or in web searches for "HL-Gauss
     NNUE".
   - A TalkChess thread compared scalar cross-entropy or KL with MSE on the *main* NNUE output. One
     tester saw no significant difference (CI −10 to +21); another found CE clearly weaker. That is
     not a histogram auxiliary head
     ([TalkChess t=85963](https://talkchess.com/viewtopic.php?t=85963), seen as search snippet only).
3. **Mechanism.**
   - ChessSI's ablation says the gain comes from a second, low-noise target that shapes the shared
     layer.
   - With MSE on a sigmoid, the gradient into the accumulator is (σ − t)·σ′. That gradient is nearly
     zero for clearly won or lost positions, so those positions barely train the feature transformer.
     A softmax cross-entropy head has gradient (p − target histogram) at the logits, which does not
     vanish in the tails.
   - Imani & White attribute their gains to easier optimisation and better-behaved gradients, not
     representation. Farebrother et al. add robustness to noisy targets and use of the target's
     ordinal structure; HL-Gauss beat Two-Hot.
4. **Expected Elo: 0 to +15 (central +5), confidence low-medium.** The clean-target benefit (+35 to
   +53) is already taken. What remains is the effect of loss geometry. In RL that effect was large
   but appeared mostly at scale, and NNUE is a small fixed-target regression.
5. **Cost.**
   - About 40 trainer lines.
   - 3–6 GPU runs of about 30 min each on net8's snapshot (two GPUs halve the wall time).
   - One SPRT, about 1–3 h if the gain is +10 or more.
6. **Minimal experiment.**
   - Setup: net8's frozen snapshot, same seed, 20 epochs, stable per-game validation.
   - (a) Control: net8's recipe (`--aux-weight 1.0 --future-plies 4`).
   - (b) The control plus an HL-Gauss head on sigmoid(own score/400). Use K = 51 bins on [0, 1] and a
     Gaussian σ of about 0.75 bin widths (the commonly quoted default; not verified, see Gaps). Try
     head weights 0.003, 0.01 and 0.03, since cross-entropy runs at about 1–4 nats against MSE's 0.0065.
   - (c) As (b), but with the HL-Gauss head replacing the MSE head on the 4-ply target.
   - Run an SPRT [0, 5] only if the main-head validation loss beats the control by at least 0.00002.
     Data is ChessSI-only.
7. **Risks.**
   - A cross-entropy head can swamp the shared layer, as the policy head did; tune the weight.
   - Win-probability bins crowd near 0.5. Bins in centipawn space (±2,000 cp) are an alternative.
   - Validation loss may not translate to Elo.

#### 2. Gradient routing for the noisy game-result term
1. **Idea.** Write the main loss as
   λ·MSE(σ(W·x), σ(score)) + (1 − λ)·MSE(σ(W·sg(x)), result), where sg is a stop-gradient on the
   accumulator activations x. The game result then trains only the output layer, while the search score
   and the auxiliary heads train the feature transformer.
   - Without sg, the two forms have exactly the same gradient as today's loss, and the loss values
     differ only by a constant. The output-layer optimum is therefore unchanged, and validation loss
     on the usual blend stays directly comparable.
   - Variant: let a fraction β ∈ {0, 0.25, 0.5} of the result gradient reach the feature transformer.
   - Field: multi-task and noisy-label learning. The stop-gradient isolation is borrowed from KataGo's
     uncertainty heads ("stop-gradients keep the error heads from changing the value heads",
     [KataGoMethods.md](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)) and
     Lc0's `propagate_value_gradients` flag
     ([training_config.proto](https://github.com/LeelaChessZero/lczero-training/blob/master/proto/training_config.proto)).
2. **Prior art: Novel.** Not found in nnue-pytorch, bullet or the Lc0 trainer. There, stop-gradients
   isolate only error and uncertainty heads, never the outcome part of a value target.
3. **Mechanism.** Three ChessSI results together suggest that the result's information matters at the
   output, but its noise harms the shared features:
   - a result-only auxiliary head badly hurt the shared layer (0.00717 vs 0.00662);
   - dropping the result entirely cost 80 Elo;
   - a clean search-score head helped.
   Routing tests that directly, at zero inference cost.
4. **Expected Elo: −10 to +15 (central +3), confidence low.** The result is useful even if this loses.
   If β = 0 loses, the result's value lies in features it teaches the first layer, which points to
   β = 0.5 or to idea 5. If it wins, the result's value is mostly calibration.
5. **Cost.** About 15 lines and 2–3 GPU runs. An SPRT only if validation improves.
6. **Minimal experiment.** On net8's snapshot, compare the control with β = 0 and β = 0.5, measured
   against the standard blended validation target. Send the best to an SPRT [0, 5] if it is at least
   0.00002 better.
7. **Risks.**
   - λ = 1.0's loss may come from missing features rather than calibration, in which case β = 0 fails.
   - The output layer has only 2H + 1 weights to absorb the result signal.
   - Weight clipping interacts with these dynamics in ways that are hard to predict.

#### 3. Ensemble-teacher distillation head (own nets, GPU only)
1. **Idea.** Train K = 4 wider ChessSI networks (h512 or h768, different seeds, 20–40 epochs) on the
   same training games. Average their sigmoid outputs and use that average as the target of the
   existing training-only `--teacher` head, or put it in place of part of the search-score term.
   - Field: knowledge distillation and ensembles. Generalized distillation unifies distillation with
     learning using privileged information
     ([Lopez-Paz et al., ICLR 2016](https://mlanthology.org/iclr/2016/lopezpaz2016iclr-unifying)).
     Born-again networks are already cited in ChessSI's queue.
2. **Prior art: Partially known.**
   - Stockfish trains NNUE on Lc0 data scored by large Lc0 networks (T77–T80), which is distillation
     from an external teacher and forbidden here
     ([Stockfish PR #4465](https://github.com/official-stockfish/Stockfish/pull/4465)).
   - ChessSI's own born-again head gained −0.00003 in validation and has had no SPRT
     ([IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)).
   - Ensembles of the engine's own NNUEs as teacher: not found.
3. **Mechanism.** The averaged prediction of wider nets is the smoothest, lowest-noise target ChessSI
   can make from its own data. That is exactly what the auxiliary-head ablation says helps the shared
   layer. h512 alone already validated at 0.00649 against h256's 0.00653 on 64.6M positions, and it
   costs only GPU time, which sits idle.
4. **Expected Elo: 0 to +15 (central +5), confidence low-medium.** The born-again teacher gave only
   a small gain because its errors match the student's. An ensemble of wider nets is a better teacher,
   but it saw the same data, so its errors are still correlated.
5. **Cost.**
   - 4 × h512 runs of about 45–60 min each (about 2 h on two GPUs), plus minutes of teacher inference.
   - About 10 trainer lines to accept several `--teacher` files.
   - One SPRT.
6. **Minimal experiment.**
   - Teachers are trained on the stable training split only, so they never see validation games.
   - Student: net8's recipe plus the teacher head at weights 0.5 and 1.0, against the control.
   - Control for the confound of more training compute by also testing a single h512 teacher.
   - SPRT if the gain is at least 0.00002.
7. **Risks.** The teacher's errors are correlated with the student's. The gain may stay at the
   born-again level. GPU time grows with K.

#### 4. Exact mirror augmentation for castling-free positions
1. **Idea.** For positions whose FEN castling field is `-`, randomly mirror files a↔h (p = 0.5 per
   sample) and keep the score and result. Without castling rights, chess rules are invariant under
   this reflection, so the labels are exact.
   - Field: data augmentation by symmetry. AlphaGo and AlphaGo Zero augmented Go data with 8
     symmetries. AlphaZero "does not augment the training data" for chess, because "the rules of chess
     and shogi are asymmetric" ([arXiv 1712.01815](https://arxiv.org/abs/1712.01815)).
2. **Prior art: Partially known.** Symmetry augmentation is standard in Go. It is absent from
   nnue-pytorch and bullet (grep for mirror and augment) and from web searches.
   - Horizontal mirroring in NNUE so far is an architectural trick for king buckets, already listed in
     ChessSI's NNUE queue.
   - A colour-flip consistency loss is a no-op for ChessSI: the perspective network already shares
     weights across colours, with squares mirrored vertically for Black.
3. **Mechanism.** Data volume is ChessSI's main lever: +139, +104 and +43 Elo came from more data,
   while wider nets do not help yet. Data generation is CPU-bound. Without king buckets, a 768-input
   net sees a mirrored position as different inputs, so mirroring adds coverage for free.
4. **Expected Elo: 0 to +12 (central +4), confidence low-medium.** Mirrored copies are perfectly
   correlated with their originals, including the same label noise, so the effective data gain is
   well below 2× on that subset.
5. **Cost.** About 25 trainer lines (parse the castling field, map square s to s ^ 7). No extra epochs
   are needed with on-the-fly mirroring. One SPRT.
6. **Minimal experiment.** First measure the share of castling-free positions in net8's data. Then
   compare net8's recipe with random mirroring against the control, using the same seed and epochs and
   unmirrored validation games. SPRT if the gain is at least 0.00002.
7. **Risks.** The net may already generalise across the mirror. The gain may be smaller than its
   SPRT can resolve.

#### 5. λ-return (TD(λ)) in place of the raw game result
1. **Idea.** Keep 0.75·σ(score_t), but replace the result in the 0.25 term with
   G_t = (1 − μ)·σ(s_{t+1}) + μ·G_{t+1}, with G_T = result.
   - G_t is computed backward over each game, which is possible because datagen games are contiguous.
   - μ → 1 recovers today's target. μ → 0 approaches `--lambda 1.0`, which lost 80 Elo.
   - Variant: λ that depends on plies to the end of the game.
   - Field: TD(λ). KnightCap's TDLeaf(λ) is the chess precedent
     ([arXiv cs/9901002](https://arxiv.org/abs/cs/9901002),
     [CPW](https://www.chessprogramming.org/Temporal_Difference_Learning)). KataGo's short-term value
     targets use the same exponential weighting, (1 − λ)Σλ^t v_t, with horizons of about 6, 16 and 50
     turns ([KataGoMethods.md](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)).
2. **Prior art: Partially known.** TD learning is classic in chess, and KataGo uses λ-returns, but only
   as auxiliary-head targets. nnue-pytorch schedules λ over training and adds per-sample λ jitter,
   but its outcome term is always the raw result
   ([config.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/config.py)).
   λ-returns as an NNUE target: not found.
3. **Mechanism.** The result carries long-horizon information that the search score lacks, but it is
   noisy. A λ-return keeps the result where it is informative, near the end of the game. Early in the
   game it replaces coin-flip noise with the consensus of later searches.
4. **Expected Elo: −5 to +10 (central +3), confidence low.** ChessSI's horizon sweep found farther
   horizons worse as auxiliary targets.
5. **Cost.**
   - About 20 lines and 3 GPU runs (μ per recorded ply ∈ {0.97, 0.99, 0.995}).
   - Validation loss is not comparable across targets, so each variant needs a common yardstick
     (log-loss of final results and MSE against the standard blend on held-out games) and probably
     2 SPRTs. This makes it the most CPU-hungry of the trainer-only ideas.
6. **Minimal experiment.** On net8's snapshot, train μ = 0.99 against net8. Check both yardsticks,
   then run an SPRT [0, 5].
7. **Risks.**
   - Future scores share the engine's systematic biases, which the raw result corrects.
   - Only quiet positions are recorded, so steps are irregular.

#### 6. Root-sibling bounds with a hinge loss (TreeStrap(αβ)-lite)
1. **Idea.** During datagen, log the child position of every root move together with the bound the
   search proved for it. Non-best moves fail low, giving an upper bound from the mover's side. Add a
   one-sided hinge loss that penalises the network only when its eval of the child violates the bound.
   - Field: bootstrapping from game-tree search
     ([Veness, Silver, Uther, Blair, NIPS 2009](https://papers.nips.cc/paper/3722-bootstrapping-from-game-tree-search)).
     The [CPW Meep page](https://www.chessprogramming.org/Meep) reports relative ratings of TD-Leaf
     1068, RootStrap(αβ) 1362, TreeStrap(mm) 1807 and TreeStrap(αβ) 2157, for a linear eval learnt from
     self-play.
2. **Prior art: Partially known.** TreeStrap dates from 2009, with a linear evaluation. NNUE pipelines
   train on exact root scores only. Stockfish used depth-6 multipv2 searches to *filter* positions
   ([PR #4314](https://github.com/official-stockfish/Stockfish/pull/4314)), not to train on siblings.
3. **Mechanism.**
   - Each 5,000-node search already visits every root move, so logging adds about 30 one-sided labels
     per search at zero extra nodes, and CPU is the bottleneck.
   - These "after a mistake" positions are where static-eval pruning (RFP, futility, null move) makes
     its decisions inside the search.
4. **Expected Elo: −10 to +15 (central +3), confidence low.**
5. **Cost.**
   - About 60 lines of C++ in datagen, folded into the next generation's run on the second 265K.
   - A hinge loss with a mixing weight in the trainer.
   - 2–3 GPU runs and 1–2 SPRTs.
6. **Minimal experiment.** Train the next generation's recipe with and without the sibling term
   (weights 0.1 and 0.3, quiet children only). Validate on root positions, then run an SPRT.
7. **Risks.**
   - Late move reductions and pruning make fail-low bounds unreliable.
   - Children after a blunder are often not quiet.
   - The data shifts toward lost positions, and storage grows about 30× unless subsampled.

#### 7. Iterative-deepening trajectory auxiliary heads
1. **Idea.** Record the root score after each completed iteration (depths 1..D) in datagen. Add
   training-only heads that predict σ(score at depth k) for a few k, such as 1, D/2 and D. This is
   KataGo's multi-horizon auxiliary heads moved from the time axis to the search-effort axis.
2. **Prior art: Novel (not found).** NNUE trainers use only the final score, and ChessSI records only
   `fen | score | result`.
3. **Mechanism.** The 0-ply head showed that a second target on the same position helps. Iteration
   scores are further nearly free, low-noise targets of graded depth.
4. **Expected Elo: 0 to +8 (central +2), confidence low.**
5. **Cost.** About 20 lines in datagen plus a new data generation; K small heads in the trainer;
   2–3 GPU runs.
6. **Minimal experiment.** On the next generation, compare net8's recipe with and without the depth-1
   and depth-D/2 heads (weight 0.5 each). SPRT only if the gain is at least 0.00002.
7. **Risks.** Shallow targets may pull capacity toward short tactics that the search resolves anyway,
   which is what sank the policy head. Results are delayed until new data exists.

#### 8. Sharpness-aware minimisation (SAM) in the last epochs
1. **Idea.** Use SAM steps, an ascent of radius ρ followed by descent, for the final 25–50% of
   epochs.
   - Field: optimisation and generalisation. Baek, Kolter & Raghunathan (ICLR 2024) found SAM's gains
     under label noise far larger than on clean data, peaking with early stopping
     ([ICLR](https://iclr.cc/virtual/2024/poster/19504)).
2. **Prior art: Novel for NNUE.** SAM is absent from nnue-pytorch and bullet (grep), and no NNUE use
   was found.
3. **Mechanism.** ChessSI's target has label noise from the 25% result term, and h256 overfits after
   about 10 epochs at 23M positions. Evidence that flatter minima tolerate quantisation better is
   limited to diffusion models.
4. **Expected Elo: −3 to +6 (central +1), confidence low.** NNUEs are small relative to 91M
   positions, and SAM shines mostly in over-parameterised, noisy settings.
5. **Cost.** 2× GPU time per step, about 30 lines and 2–3 runs (ρ ∈ {0.01, 0.05}).
6. **Minimal experiment.** On net8's snapshot, compare SAM in the final 5 epochs with the control.
   SPRT only if the gain is at least 0.00002.
7. **Risks.** The ascent step interacts with weight clipping. The effect is too small for an
   affordable SPRT.

#### 9. RHO-LOSS weighting (fixes the queued "weight by abs(static eval − score)" idea)
1. **Idea.** Instead of up-weighting positions where the static eval disagrees with the search, weight
   or select positions by training loss minus "irreducible" loss. The irreducible loss comes from a
   model trained on held-out games; two half-data models can score each other's halves.
   - Field: data selection
     ([Mindermann et al., ICML 2022, arXiv 2206.07137](https://arxiv.org/abs/2206.07137)), which
     reported 18× fewer steps on noisy Clothing-1M and showed that small irreducible-loss models
     suffice.
2. **Prior art: Partially known.** The queued ChessSI idea is essentially already Known.
   - Lc0's "diff focus" samples positions by |best_q − orig_q| (search value minus the raw network
     eval) plus policy KLD
     ([position_sampling.cc](https://github.com/LeelaChessZero/lczero-training/blob/master/csrc/loader/stages/position_sampling.cc),
     [chunkparser.py](https://github.com/LeelaChessZero/lczero-training/blob/master/tf/chunkparser.py),
     [Lc0 project history](https://lczero.org/dev/wiki/project-history/)).
   - KataGo weights positions by policy surprise
     ([KataGoMethods.md](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)).
   - nnue-pytorch filters on win/draw/loss disagreement (`wld_filtered`).
   - RHO-LOSS in chess: not found.
3. **Mechanism.** It separates positions that are hard because of label noise from those that are
   hard because they are not yet learnt.
4. **Expected Elo: −5 to +8 (central +1), confidence low.** GPU steps are cheap for ChessSI, so
   faster training is worth little. A gain needs better final quality.
5. **Cost.** 2 half-data runs, a scoring pass and a weighted run.
6. **Minimal experiment.** Compare net8's recipe with RHO weights against both the control and an
   abs(eval − score)-weighted run. SPRT the best.
7. **Risks.** Weighting biases the training distribution, and calibration may suffer.

#### Known backlog (not novel; already in other trainers)
- **K1. Generation-aware weighting or annealing (high practical value).**
  - Generation 1 (37.2M positions) has scores from a PeSTO engine, about 700 Elo weaker than net7, at
    5,000 nodes.
  - Options: down-weight it (0.5 or 0), train it only in early epochs, or finish the last epochs on
    generations 3–4.
  - Prior art: Stockfish's multi-stage retraining on successive datasets with λ schedules
    ([PR #4465](https://github.com/official-stockfish/Stockfish/pull/4465);
    [nn-0dd1cebea573 five-step sequence, mirror page](https://m.nextchessmove.com/dev-builds/373359b44d0947cce2628a9a8c9b432a458615a8)).
  - Relabelling generation 1 with the current engine is also Known practice and costs only about an
    hour of the second PC's datagen throughput.
- **K2. EMA or SWA of weights at export.**
  - Lc0 has SWA with an export option
    ([training_config.proto](https://github.com/LeelaChessZero/lczero-training/blob/master/proto/training_config.proto)).
  - nnue-pytorch's default optimiser is RangerLite with Lookahead (merge every 5 steps, α 0.5), with
    Schedule-Free AdamW as an option. bullet has Ranger with Lookahead (α 0.5, k 6).
  - ChessSI exports the last plain-Adam iterate.
  - EMA models are more robust to label noise and better calibrated
    ([Morales-Brotons et al., TMLR 2024](https://mlanthology.org/tmlr/2024/moralesbrotons2024tmlr-exponential)).
    Expect a small gain, because the cosine-to-zero schedule already anneals the last iterate. It
    costs about zero GPU.
- **K3. Draw-aware win-rate conversion and power loss.** nnue-pytorch's defaults are offsets 270,
  scalings 340 and 380, and a loss of |pt − qf|^2.5
  ([nnue.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/nnue.py)).
- **K4. λ schedule and jitter.** For example, λ 1.0 → 0.7 over training, plus per-sample and
  per-batch jitter in nnue-pytorch.
- **K5. QAT.** nnue-pytorch trains with fake quantisation and a straight-through estimator, on by
  default. A cheap first check is to measure |float − int16| eval error on validation positions.
  - A rough back-of-envelope estimate (inference, unverified): QB = 64 rounding over 512 SCReLU inputs
    could cause eval errors of several cp per position.
- **K6. Position filters and sampling.** "Smart" skipping of capture and in-check positions,
  win/draw/loss-disagreement skipping, early-ply skipping and a piece-count distribution
  (nnue-pytorch `pc_y*`; bullet's advanced filter example).
- **K7. Other optimisers.** AdamW with weight decay, Ranger and Schedule-Free.
- **K8. WDL outputs and a moves-left head.** WDL outputs exist in Lc0 and in Seer's NNUE; Lc0 has the
  moves-left head. Low priority, given that ChessSI's result-only head hurt.

### Gaps
- The full texts of the HL-Gauss, searchless-chess, KataGo and RHO-LOSS papers could not be read
  (arXiv blocked). Missing details include the exact searchless-chess ablation numbers for one-hot
  vs HL-Gauss vs MSE, and the recommended σ-to-bin-width ratio; the "0.75" above is from memory.
- TalkChess, fishtest and Discord could not be searched directly. An NNUE use of EMA, mirror
  augmentation, SAM or λ-returns may exist there unreported, so "Novel" means "not found in the
  sources reachable here".
- All Elo ranges are judgement calls anchored on ChessSI's own validation-to-Elo pairs (two
  auxiliary-head tests and one output-bucket test), not on measurements of these ideas.

## Which modern ML training techniques have or have not been tried in NNUE training?

### Takeaway
The mainstream NNUE trainers already cover loss shaping, schedules, filtering, QAT and Lookahead or
schedule-free averaging. Classification or histogram targets, auxiliary heads, distillation from the
engine's own nets, symmetry augmentation, SAM, λ-returns, internal-node training and loss-based data
selection were not found in NNUE training. Several of them exist in Lc0 or KataGo.

### Cited Findings
- QAT: nnue-pytorch defaults `use_fake_act_quantization` and `use_fake_weight_quantization` to True,
  described as "fake quantization with STE ... during training" — [nnue-pytorch model/config.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/config.py)
- The nnue-pytorch loss uses a draw-aware win-rate model, power 2.5, `qp_asymmetry` and per-sample
  weights `1 + (2**w1 - 1)*((pf-0.5)**2*pf*(1-pf))**w2` (w1 = 0 by default) — [nnue-pytorch model/nnue.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/nnue.py)
- HL-Gauss, the Gaussian-smoothed histogram target, beat Two-Hot, apparently through less overfitting
  and use of ordinal structure, and degrades more slowly than MSE as reward noise grows. Gains were
  reported on Atari, robotics, Wordle and searchless chess — [Farebrother et al., ICML 2024 (arXiv 2403.03950)](https://arxiv.org/abs/2403.03950); [ICML oral](https://icml.cc/virtual/2024/oral/35498)
- In chess, HL-Gauss closed the gap to AlphaZero with 400 MCTS simulations for Stockfish-distilled
  transformers. The MSE baseline was omitted because Ruoss et al. had found one-hot targets beat MSE
  (search snippet; full text not read) — [arXiv 2403.03950](https://arxiv.org/abs/2403.03950); [Ruoss et al., arXiv 2402.04494](https://arxiv.org/abs/2402.04494)
- Imani & White's histogram loss "significantly improves prediction accuracy". They attribute this to
  easier optimisation and better-behaved gradients, not to representation or less overfitting —
  [Imani & White, ICML 2018](https://mlanthology.org/icml/2018/imani2018icml-improving); follow-up [arXiv 2402.13425](https://arxiv.org/abs/2402.13425)
- A TalkChess thread on scalar cross-entropy or KL vs MSE on the NNUE output reports one result as
  "statistically insignificant (confidence interval of [-10 to +21] ELO)" and another as "significantly
  weaker than training with MSE" (search snippet only) — [TalkChess "NNUE loss function, why MSE?"](https://talkchess.com/viewtopic.php?t=85963)
- EMA of weights: EMA models show better robustness to noisy labels, prediction consistency,
  calibration and transfer, and need less learning-rate decay — [Morales-Brotons, Vogels, Hendrikx, TMLR 2024](https://mlanthology.org/tmlr/2024/moralesbrotons2024tmlr-exponential)
- SAM's gains under label noise are far larger than on clean data, peaking under early stopping —
  [Baek, Kolter, Raghunathan, ICLR 2024](https://iclr.cc/virtual/2024/poster/19504)
- RHO-LOSS selects points by training loss minus irreducible holdout loss, reaching 18× fewer steps on
  Clothing-1M. Its speedups are largest on noisy or redundant data — [Mindermann et al., arXiv 2206.07137](https://arxiv.org/abs/2206.07137)
- A good data-pruning metric can in theory beat power-law scaling (Sorscher et al., NeurIPS 2022
  outstanding paper) — [Meta AI publication page](https://ai.meta.com/research/publications/beyond-neural-scaling-laws-beating-power-law-scaling-via-data-pruning/)
- TreeStrap(αβ) trains toward the values of all nodes of an alpha-beta search; in Meep it learned
  master-level weights from random initialisation — [Veness et al., NIPS 2009](https://papers.nips.cc/paper/3722-bootstrapping-from-game-tree-search); [CPW Meep](https://www.chessprogramming.org/Meep)
- TD(λ) and TDLeaf(λ): KnightCap was trained with TDLeaf; the TD literature in chess is old and
  pre-NNUE — [KnightCap, arXiv cs/9901002](https://arxiv.org/abs/cs/9901002); [CPW Temporal Difference Learning](https://www.chessprogramming.org/Temporal_Difference_Learning)
- Curriculum: Stockfish retrains in stages on successive datasets with λ schedules, for example
  λ 1.0 → 0.7 with early-fen-skipping 30 over 900 epochs in PR #4465 — [PR #4465](https://github.com/official-stockfish/Stockfish/pull/4465); [PR #4314](https://github.com/official-stockfish/Stockfish/pull/4314)
- Seer trains by "retrograde learning", starting from 6-man Syzygy WDL and backing values up with its
  own search; its network estimates WDL probabilities — [CPW Seer](https://www.chessprogramming.org/Seer); [seer-nnue](https://github.com/connormcmonigle/seer-nnue)
- Symmetry: Go's AlphaGo and AlphaGo Zero augmented data with 8 symmetries; AlphaZero "does not augment
  the training data" because chess and shogi rules are asymmetric — [Silver et al., arXiv 1712.01815](https://arxiv.org/abs/1712.01815)

### Inferences
Status of each checklist item for ChessSI:

| Technique | Status | Card |
| --- | --- | --- |
| HL-Gauss / two-hot | Not in NNUE; Lc0 has a one-hot categorical training head | Card 1 |
| WDL distributions | Known (Lc0 WDL head; Seer's WDL NNUE) | Backlog K8 |
| Quantile targets | Not found; low priority, since alpha-beta consumes one scalar | — |
| EMA / SWA | Known in Lc0; NNUE trainers use Lookahead or schedule-free averaging | Backlog K2 |
| SAM | Not found | Card 8 |
| Label smoothing / noisy labels | Filters and λ jitter are Known; HL-Gauss and gradient routing are new routes | Cards 1, 2 |
| Data pruning by difficulty | Known in Lc0 and KataGo surprise weighting; RHO-LOSS is new | Card 9 |
| Curriculum | Known (Stockfish stages, Seer retrograde) | Backlog K1 |
| Ensemble → distil | Partially known | Card 3 |
| QAT | Known (nnue-pytorch) | Backlog K5 |
| Colour-flip consistency | Built into the architecture, so nothing to gain | — |
| Mirror symmetry | Not used as data augmentation in NNUE | Card 4 |
| TD(λ) | Known historically, not used for NNUE targets | Card 5 |
| Internal-node training | TreeStrap known, not used for NNUE | Card 6 |

### Gaps
- Fishtest's history of nnue-pytorch experiments, such as whether EMA or SAM was ever tried, could not
  be searched from here.
- Sorscher et al.'s claim that large datasets should keep hard examples and small ones easy examples
  could not be verified from the reachable sources.

## How can the auxiliary-head mechanism be amplified, and why do auxiliary targets help small networks?

### Takeaway
The ML literature explains ChessSI's result: related tasks with shared signal but different noise
amplify the data, bias the representation toward the shared regularity and regularise. Targets that
are cheaper than or privileged relative to the main label act like a teacher. Conflicting tasks hurt,
which is how the policy head failed. Extensions should therefore add cleaner targets (cards 1, 3, 7),
remove noisy gradients from the shared layer (card 2), and gate conflicting heads.

### Cited Findings
- Caruana's multitask-learning mechanisms are statistical data amplification, eavesdropping (one task
  picks up features learned for another), representation bias and attribute selection. MTL "improves
  generalization by using the domain information contained in the training signals of related tasks as
  an inductive bias" — [Caruana 1997, Machine Learning 28](https://www.cs.williams.edu/~andrea/cs374/Articles/Caruana.pdf); [Caruana NIPS 1994](https://papers.nips.cc/paper_files/paper/1994/file/0f840be9b8db4d3fbd5ba2ce59211f55-Paper.pdf)
- KataGo: auxiliary ownership and score targets "suggest a much more general meta-learning heuristic:
  that predicting subcomponents of desired targets can greatly improve training". A binary result
  gives little credit assignment (snippet; full text not read) — [Wu 2019, arXiv 1902.10565](https://arxiv.org/abs/1902.10565)
- KataGo's short-term value auxiliary heads made nets "train slightly faster" with "slightly better
  value and score loss" on the main head, in a partial test — [KataGoMethods.md](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)
- Generalized distillation unifies distillation with learning using privileged information: a teacher
  that uses information unavailable at test time supplies soft labels — [Lopez-Paz, Bottou, Schölkopf, Vapnik, ICLR 2016](https://mlanthology.org/iclr/2016/lopezpaz2016iclr-unifying)
- Adapting auxiliary losses by gradient similarity: weight the auxiliary loss by the cosine between
  its gradient and the main task's, or drop it when the cosine is below a threshold. This provably
  still converges to critical points of the main task — [Du et al. 2018, arXiv 1812.02224](https://arxiv.org/abs/1812.02224); [poster](https://www.gatsby.ucl.ac.uk/~balaji/CL-NeurIPS2018-adapt-poster.pdf)
- Auxiliary tasks shape representation dynamics; Lyle et al. tie the representations they induce to
  the transition operator's spectrum (RL setting) — [Lyle et al., AISTATS 2021](https://proceedings.mlr.press/v130/lyle21a.html)
- ChessSI's own evidence:
  - an own-score head worked as well as a 4-ply head;
  - a result-only head hurt (0.00717);
  - a policy head hurt at every weight;
  - the head helped more at h512 (0.00712 vs 0.00694), which is consistent with regularisation.

  Source: [ChessSI docs/IDEAS.md](https://github.com/LupeHiguera/ChessSI/blob/claude/artifact-access-issue-ug96zp/docs/IDEAS.md)

### Inferences
- **Mechanism.** The search score and the main blend share most of their signal. The search score
  lacks the noise of the 25% result term, so the shared layer gets an averaged, lower-variance
  gradient. In the privileged-information reading, the search is the teacher with privileged
  computation. This predicts that noisier targets hurt (result-only) and that targets which compete
  for 256 units hurt (policy). Both happened.
- **Ways to amplify the mechanism, cheapest first:**
  - (a) Combine the existing heads: own score, 4-ply and born-again teacher together. This is a
    zero-code validation screen.
  - (b) An HL-Gauss loss on the clean head (card 1).
  - (c) Stop the result's gradient from reaching the shared layer (card 2).
  - (d) An even cleaner teacher, an ensemble of wider nets (card 3).
  - (e) More clean same-position targets, the iteration scores (card 7).
  - (f) Gradient-similarity gating (Du et al.) for any head that competes. This is a principled way
    to retry the policy head at a higher weight without hurting the value head.
  - (g) Keep auxiliary heads linear on the accumulator. A deeper head would solve its task with less
    pressure on the shared layer, which is where the benefit comes from.

### Gaps
- No paper was found that isolates why auxiliary targets help *tiny, shallow* networks (one hidden
  layer) in supervised regression with mixed-noise labels. The explanations above are transferred
  from multi-task learning, distillation and RL.
- KataGo's Elo ablation for its auxiliary targets could not be read (arXiv blocked).

## What do the main NNUE trainers (nnue-pytorch, bullet) already implement?

### Takeaway
nnue-pytorch already has:
- QAT (on by default);
- a draw-aware power-2.5 loss with optional asymmetry and sample weights;
- λ schedules with jitter;
- smart, win/draw/loss, random, early-ply and simple-eval position skipping;
- piece-count sampling;
- AdamW, RangerLite with Lookahead (the default), Ranger21 and Schedule-Free AdamW.

bullet has AdamW, RAdam, Ranger with Lookahead, weight clipping, a constant or scheduled WDL blend
with sigmoid squared error, and user filters. Neither has EMA or SWA export, auxiliary heads,
categorical targets, distillation, mirror augmentation or SAM. ChessSI's trainer has none of the
nnue-pytorch extras, but it does have training-only auxiliary, policy and teacher heads.

### Cited Findings
- nnue-pytorch's optimiser choices are `"schedulefree", "ranger21", "rangerlite", "adamw"`, defaulting
  to `"rangerlite"`. RangerLite defaults to `lookahead_active=True, lookahead_mergetime=5,
  lookahead_blending_alpha=0.5` — [nnue-pytorch model/optimizers](https://github.com/official-stockfish/nnue-pytorch/tree/master/model/optimizers)
- The nnue-pytorch λ config holds start and end λ, "std of normal distributed per sample jitter to add
  to lambda", per-batch jitter with decay, and a cyclic schedule with warmup — [nnue-pytorch model/config.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/model/config.py)
- The nnue-pytorch loader has `filtered` ("smart fen skipping"), `wld_filtered`, `random_fen_skipping`,
  `early_fen_skipping`, `soft_early_fen_skipping` (20), `simple_eval_skipping` and `pc_y0..pc_y4`
  (piece-count frequency spline) — [nnue-pytorch data_loader/config.py](https://github.com/official-stockfish/nnue-pytorch/blob/master/data_loader/config.py)
- Grepping nnue-pytorch for `ema`, `swa`, averaging, SAM or sharpness, label smoothing and
  mirror/augment found nothing beyond Lookahead and Schedule-Free — [nnue-pytorch](https://github.com/official-stockfish/nnue-pytorch)
- bullet's example `(768 -> N)x2 -> 1` uses SCReLU and AdamW, with
  `loss_fn(|output, target| output.sigmoid().squared_error(target))`. The target is
  `wdl * game_result + (1 - wdl) * sigmoid(score / SCALE)` with `ConstantWDL { value: 0.75 }`, so 75%
  game result in that example, and the LR is stepped. It notes "There's potentially a lot of elo
  available by adjusting the wdl and lr schedulers" — [bullet examples/simple.rs](https://github.com/jw1912/bullet/blob/main/examples/simple.rs)
- bullet's optimisers are adam, radam, ranger (`RangerLookaheadParams` default `alpha: 0.5, k: 6`),
  clip and decay. Its advanced example filters positions toward a target piece-count distribution — [bullet optimiser](https://github.com/jw1912/bullet/tree/main/crates/trainer/src/optimiser); [bullet examples/advanced/filter.rs](https://github.com/jw1912/bullet/blob/main/examples/advanced/filter.rs)
- The CPW NNUE page lists bullet as the most widely adopted trainer among top engines as of 2025
  (search snippet) — [CPW NNUE](https://www.chessprogramming.org/NNUE)

### Inferences
- The cheapest Known gains for ChessSI are backlog items K1 (generation weighting), K2 (EMA), K3
  (power loss and draw-aware conversion) and K5 (QAT, after measuring quantisation error). Each is
  one experiment under the one-idea rule.
- ChessSI's training-only auxiliary, teacher and policy heads are unusual: no mainstream NNUE trainer
  has them. That supports treating cards 1–3 and 7 as genuinely open territory.

### Gaps
- bullet's newer graph API could express multi-output training graphs; whether any engine built on
  bullet trains auxiliary heads privately is unknown, since there is no public example.

## What have Lc0 and KataGo done on the training side that has not transferred to NNUE?

### Takeaway
Six things have not transferred to NNUE:
- categorical value heads (Lc0);
- value-error or uncertainty heads (Lc0, KataGo);
- λ-weighted short-term value targets (KataGo);
- surprise-based data weighting (KataGo policy surprise, Lc0 diff focus);
- SWA export (Lc0);
- a moves-left head (Lc0).

WDL outputs did reach one NNUE engine (Seer). The policy-side methods (soft policy, optimistic
policy) do not apply to a value-only NNUE.

### Cited Findings
- Lc0's value head returns `(wdl, error, categorical)`. The categorical head maps Q from [−1, 1) to
  one-hot buckets with softmax cross-entropy. The WDL target is built from search q and d as
  w = (1 + q − d)/2, l = (1 − q − d)/2 — [value_head.py](https://github.com/LeelaChessZero/lczero-training/blob/master/src/lczero_training/model/value_head.py); [loss_function.py](https://github.com/LeelaChessZero/lczero-training/blob/master/src/lczero_training/model/loss_function.py)
- Lc0's export writes `OUTPUT_WDL`, `VALUE_WDL` and `MOVES_LEFT_V1`; the categorical head is not in
  the exported format — [jax_to_leela.py](https://github.com/LeelaChessZero/lczero-training/blob/master/src/lczero_training/convert/jax_to_leela.py)
- Lc0 SWA config holds `period_steps` and `num_averages`, plus `export_swa_model` — [training_config.proto](https://github.com/LeelaChessZero/lczero-training/blob/master/proto/training_config.proto)
- Lc0 diff focus computes `diff_q = abs(best_q - orig_q)`, then weight =
  min(((q_weight·diff_q + policy_kld)/(q_weight + pol_scale)·α + β)^γ, τ). It skips records
  "according to how accurate the no-search eval ('orig_q') is compared to eval after search
  ('best_q')" — [position_sampling.cc](https://github.com/LeelaChessZero/lczero-training/blob/master/csrc/loader/stages/position_sampling.cc); [tf/chunkparser.py](https://github.com/LeelaChessZero/lczero-training/blob/master/tf/chunkparser.py)
- Lc0's project history records "value focus" tuning in T60 and "diff focus" introduced in run 610161
  (search snippet) — [Lc0 project history](https://lczero.org/dev/wiki/project-history/)
- KataGo's training methods include:
  - short-term value and score heads with λ horizons of about 6, 16 and 50 turns;
  - uncertainty heads predicting squared error (stop-gradient, Huber), about 75 Elo with dynamic
    cPUCT, not isolated;
  - policy surprise weighting, "one of the larger improvements";
  - an auxiliary soft policy (T = 4, weight 8×);
  - an optimistic policy, "40 to 90 Elo";
  - two copies of the heads, at 80% and 20% loss weight.

  Source: [KataGoMethods.md](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md)
- Seer's NNUE estimates WDL probabilities and was trained by retrograde learning from Syzygy
  tablebases — [CPW Seer](https://www.chessprogramming.org/Seer)

### Inferences
Mapping each method to ChessSI:

| Method | What it means for ChessSI |
| --- | --- |
| Lc0 categorical head | Source of card 1 (upgrade one-hot to HL-Gauss) |
| KataGo λ short-term values | Source of card 5; also a λ-weighted variant of ChessSI's N-ply auxiliary head |
| Uncertainty / error heads | Support ChessSI's queued uncertainty-aware evaluation |
| Surprise weighting, diff focus | Make ChessSI's queued abs(eval − score) weighting Known; card 9 is the novel correction |
| SWA | Backlog K2 |
| Moves-left head | Low value as a training-only target (noisy, like the result) |
| Soft / optimistic policy | Not applicable to a value-only NNUE |
| Seer's retrograde curriculum | Uses external tablebases, which the data rule forbids; a version with ChessSI's own tablebase generator would be allowed but is costly |

The KataGo uncertainty heads are the closest prior art for ChessSI's queued uncertainty-aware
evaluation. KataGo adds them with a stop-gradient, so they do not disturb the value head. An NNUE
version costs one more output at inference.

### Gaps
- The Elo effect of Lc0's categorical head and of diff focus is not documented in the sources reached.
- KataGo's per-component ablations are in its paper's full text, which could not be read.
