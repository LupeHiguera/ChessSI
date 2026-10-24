# NNUE architecture and inference ideas for ChessSI

Scope: network architecture and inference only. Training methods and data are covered in other notes.
Researched on 2026-10-24 by a Claude Opus 5.5 research subagent.

- **Code facts:** read from read-only shallow clones at the commits linked below.
- **"Computed" Elo:** worked out here from fishtest win/loss/draw counts with the logistic formula.
- **Snippets only:** talkchess.com, lichess.org, stockfishchess.org and cosmo.tardis.ac did not resolve
  from the fetch tool. Claims from those sites come from search-result snippets and are marked as such.
- **ChessSI facts:** from branch `origin/claude/artifact-access-issue-ug96zp` at `2ab6bd2`, in the files
  `src/nnue.cpp`, `src/nnue.h`, `nnue/train.py`, `nets/README.md` and `docs/IDEAS.md`.

## 1. Which architecture and inference features do top NNUE engines use, what did each give, and at what data scale and width does each pay off?

### Takeaway
The October 2026 state of the art combines several inputs: king-bucketed, horizontally mirrored
piece-square inputs, threat inputs and (since July 2026) pawn-pair inputs. They feed a pairwise-multiplied
accumulator about 1,024 wide, then two small hidden layers (16-32 wide) chosen by 8-32 material buckets.
Stockfish retired its small network and its PSQT shortcut in 2026.

Engines that train on their own data added each feature only once their data reached billions of
positions:
- 8 output buckets and 4-16 king buckets at about 1-6B positions;
- multi-layer heads at several billion;
- threat inputs at multi-billion scale (PlentyChess uses 15B+).

ChessSI has 0.1-1B positions. At that scale the useful part of the backlog is single-layer: inference
speed, mirroring, a few factorised king buckets, output buckets, moderate width, and distillation from
a larger teacher.

### Cited Findings

**Stockfish today (master at effdc3f, committed 2026-10-17)**
- Three input feature sets are summed into one accumulator per perspective:
  - `K32Q2`: own king in 32 horizontally mirrored buckets × whether the opponent has a queen (2
    states) × 11 × 64 piece-squares, with both kings sharing one plane.
  - `FullThreats`: 59,808 features, up to 256 active at once.
  - `PP_3Wide`: pawn pairs.

  Sources: [nnue_architecture.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_architecture.h),
  [k32q2.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/features/k32q2.h),
  [full_threats.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/features/full_threats.h),
  [pp_3wide.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/features/pp_3wide.h).
- Layer sizes are L1 = 1024, L2 = 32, L3 = 32, with 32 layer stacks. Each hidden layer's output goes
  through both a squared clipped ReLU and a plain clipped ReLU. The final layer reads both hidden layers,
  plus a skip term from the first layer —
  [nnue_architecture.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_architecture.h).
- The layer stack is chosen as (piece count − 1)/4 × 4 + a queen bucket. The queen bucket records
  whether each side has a queen —
  [network.cpp](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/network.cpp).
- Stockfish now uses one network. The raw score is then scaled by its agreement with a material count,
  by optimism, by total material and by the rule-50 counter —
  [evaluate.cpp](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/evaluate.cpp).
- Pairwise multiplication: the two clipped halves of the accumulator are multiplied together
  (`vec_mulhi_16`) before L1 —
  [nnue_feature_transformer.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_feature_transformer.h).
- Finny tables: the code describes per-thread "AccumulatorCaches" that are "commonly referred to as
  'Finny Tables'". Accumulator updates are lazy, using per-perspective `computed` flags and forward and
  backward incremental updates —
  [nnue_accumulator.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_accumulator.h).

**Stockfish history, with fishtest results**
- Architecture timeline —
  [nnue_architecture_history.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue_architecture_history.md):

  | Version | Dates | Change |
  | --- | --- | --- |
  | SFNNv9 | 2024-04 to 2025-11 | L1 3072 |
  | SFNNv10 | from 2025-11-12 | Added FullThreats, cut L1 to 1024, feature-transformer quantisation scale 255 |
  | v11, v12 | 2026-02 | Removed piece→king and king→piece threats |
  | v13 | 2026-02 | L2 16 → 32 |
  | v14 | 2026-04 | Opposed-pawn threat features |
  | v14.1 | 2026-05 | Fixed-point quantisation update |
  | v15 | 2026-07-03 | New recipe (details in a later bullet) |
  | v16 | 2026-07-20 | PP_3Wide pawn pairs |
  | v17 | 2026-09-30 | Removed the PSQT output |
- **Threat inputs (SFNNv10)**
  - STC: 63,424 games, score 0.5029 (computed +2.0 Elo, 95% +0.0..+4.0).
  - LTC: 27,876 games (computed +3.8).
  - VVLTC: 12,458 games (computed +7.0).
  - An ARM LTC estimate of +13.9 ± 1.9.

  Source: [commit 8e5392d](https://github.com/official-stockfish/Stockfish/commit/8e5392d79a36aba5b997cf6fb590937e3e624e80).
- **How threat features are handled**
  - They are accumulated separately because they have "different refresh patterns".
  - Redundant pairs are removed. For example, "rook attacks queen" is dropped because the queen
    attacking the rook is implied.
  - They are stored as i8. That "seems to increase speed much more on ARM architectures (+10%)
    compared to x86 (+5%)".

  Source: [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
- **L2 16 → 32 (SFNNv13)**
  - Justified because, with threat inputs, "the accumulator/L1 size has significantly decreased".
  - STC failed over 189,184 games (computed 0.0).
  - LTC computed +3.0; VLTC SMP computed +4.5.

  Source: [commit a6d055d](https://github.com/official-stockfish/Stockfish/commit/a6d055d7e27ab3e29a42e8b94215102824760057).
- **SFNNv15**
  - Changes: new recipe, "newly relabled data", L2 widened from 31 to 32 outputs, a squared clipped ReLU
    after L2, and a skip term.
  - STC computed +4.2; LTC computed +3.3.

  Source: [commit e33bb26](https://github.com/official-stockfish/Stockfish/commit/e33bb26ee7320629dd9114a936a38e6f4d43d52a).
- **Pawn pairs (SFNNv16)**
  - Pawns on the same or adjacent files, an idea from the Pawnocchio engine.
  - STC failed (computed −0.1 over 144,768 games).
  - LTC +1.2 over 189,888 games; VLTC +2.2; VVLTC +2.3 (computed).
  - Slowdown "around 10%" at first and "about 3.5%" after optimisation.

  Source: [commit f4bcd40](https://github.com/official-stockfish/Stockfish/commit/f4bcd40409f94bd397a083c5d6243bac6dcc6d85).
- **Removing the PSQT output (SFNNv17)**
  - Passed as a non-regression: STC computed +1.8, LTC computed +1.9.
  - "Training speed is significantly faster".

  Source: [commit a17c0ce](https://github.com/official-stockfish/Stockfish/commit/a17c0ce28d5a4cc40e3f2d0e8892cb1cb4234730).
- **Small network**
  - Stockfish 16.1 (2024) added a second, small network for positions that are "easily decided" —
    [Stockfish 16.1 blog, search snippet only](https://stockfishchess.org/blog/2024/stockfish-16-1/).
  - Stockfish 19 (2026) "retired" it —
    [newreleases.io, Stockfish 19 notes](https://newreleases.io/project/github/official-stockfish/Stockfish/release/sf_19);
    [AlternativeTo](https://alternativeto.net/news/2026/9/stockfish-19-brings-stronger-neural-network-universal-binaries-and-wider-platform-support/).
- **Horizontal mirroring (HalfKAv2_hm)**
  - The board is flipped so the king is always on files e-h, which halves the feature transformer.
  - "the strength difference is hardly measurable".
  - Stockfish has used it since August 2021.

  Source: [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
- **The factoriser**
  - Virtual features learn the common factor shared across king buckets and are merged into the real
    weights at export.
  - In Stockfish it "seems to only be relevant in the early stages ... But it quickly becomes
    unimportant".
  - Other factors are listed: K, and HalfRelativeKP (piece position relative to the king).

  Source: [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
- **Layer stacks and sparse layers**
  - Layer stacks chosen by `(piece_count - 1) / 4` are described.
  - The same document says "It might be worth it to initialize the layers in each layer stack
    identically, or introduce a factorizer for the first layer in the layer stacks".
  - It also documents a sparse-input L1 and its blocked variants.

  Source: [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).

**Engines trained with bullet: architecture constants in October 2026**
- **Viridithas**
  - Architecture string: `(704×16hm + (59808 + 4560)hm → 1024)×2 → (32 → 32×2 → 1)×8`.
  - That is 16 mirrored king buckets, threat and pawn-pair inputs, pairwise multiplication and 8 output
    buckets, with QA 255 and QB 64.

  Sources: [network.rs](https://github.com/cosmobobak/viridithas/blob/b407e3eb0b8fc6e251d22664b696cfa870208a7a/src/nnue/network.rs);
  [releases](https://github.com/cosmobobak/viridithas-networks/releases).
- **Stormphrax**
  - L1 1024, L2 32, L3 64.
  - Both CReLU and SCReLU outputs ("dual activation"), a skip over L2, pairwise multiplication.
  - Merged, mirrored king buckets plus pawn-pawn threat inputs; 8 material output buckets.

  Source: [arch.h](https://github.com/Ciekce/Stormphrax/blob/d1468d99e3d3733100d20d682ac627998cce94b2/src/eval/arch.h).
- **PlentyChess**
  - 12 king buckets plus threat and pawn-pair inputs; L1 1024 → 16 → 32; 8 output buckets; int8 threat
    weights.
  - Its README says it is "trained on 15+ billion self-generated chess positions ... using
    self-distillation techniques for part of the training".

  Sources: [nnue.h](https://github.com/Yoshie2000/PlentyChess/blob/9ca005740a35967c1403bfb9a3a9032c97ee003d/src/nnue.h);
  [README](https://github.com/Yoshie2000/PlentyChess/blob/9ca005740a35967c1403bfb9a3a9032c97ee003d/README.md).
- **Alexandria**
  - 16 input buckets plus threat and pawn-pair inputs; L1 768 → 16 → 32; 8 output buckets.
  - Trained on Lc0 data.

  Sources: [nnue.h](https://github.com/PGG106/Alexandria/blob/54d4c206d76146fc88721b74f7ec65e077ab5dcb/src/nnue.h);
  [README](https://github.com/PGG106/Alexandria/blob/54d4c206d76146fc88721b74f7ec65e077ab5dcb/README.md).
- **Reckless**
  - 10 input buckets; L1 768 → 16 → 32; 8 output buckets; feature-transformer quantisation 255, L1
    quantisation 64.
  - Has threat features.

  Source: [nnue.rs](https://github.com/codedeliveryservice/Reckless/blob/69aea9086899189ee38fd3e556bf9469b805552a/src/nnue.rs).
- **Obsidian** (last commit 2025-09)
  - 13 king buckets; L1 1536 → 16 → 32; 8 output buckets; QA 255, QB 128; Finny tables.
  - Trained on Lc0 data.

  Sources: [nnue.h](https://github.com/gab8192/Obsidian/blob/720614a61ed6201037516d555f0bd2f7e5aeae3c/src/nnue.h);
  [README](https://github.com/gab8192/Obsidian/blob/720614a61ed6201037516d555f0bd2f7e5aeae3c/README.md).
- **Berserk**: "Horizontally Mirrored 16 Buckets", plus a refresh table —
  [README](https://github.com/jhonnold/berserk/blob/32628515050b83805bab4afa1026dd2bcaa93f55/README.md).
- **GaiaChess**: 12 king buckets × 768 plus filtered threats (~41K inputs) → 640 → CReLU and pairwise
  → 16 → 32 → 1, with 8 output buckets —
  [model card](https://huggingface.co/jromanghf/gaiachess-networks).
- **Renegade**: 14 mirrored king buckets, 8 output buckets —
  [model card](https://huggingface.co/pkrisz/renegade-net-36).

**Measured gains in engines trained on their own data, with data scale**
- **Viridithas, in order** —
  [releases page 4](https://github.com/cosmobobak/viridithas-networks/releases?page=4),
  [page 3](https://github.com/cosmobobak/viridithas-networks/releases?page=3).

  | Net | Change | Result |
  | --- | --- | --- |
  | gemstone | 768×2 SCReLU, no buckets, 963M positions | — |
  | omega | 1536×2, no buckets | +1.98 ± 1.60 at 40+0.4 |
  | artemis | +500M positions | +4.27 ± 3.04 at 8+0.08 |
  | signalis | 1536×2, 4 mirrored buckets | — |
  | gestalt | 9 buckets | +23.64 ± 8.91 at 8+0.08 |
  | semiotic | 8 material output buckets + a larger dataset | +19.76 at 25k nodes, +23.89 at 8+0.08 |
  | pendragon | 2048×2 + 16 king buckets | +31.64 ± 8.76 at 25k nodes, only +4.83 ± 2.85 at 40+0.4 |
  | hyperstition | 2048×2 pairwise → 16 → 32 → 1, feature transformer permuted for sparsity | +9.44 ± 4.12 at 40+0.4 |
  | voyager | 474M + 80M new positions | +8.73 at 40+0.4 |
- **Viridithas, later nets** —
  [releases page 1](https://github.com/cosmobobak/viridithas-networks/releases):
  - Threat inputs ("convocation"): +27.43 ± 7.91 at 25k nodes, but +2.98 ± 2.09 at 8+0.08 (30,040
    games) and +5.38 ± 2.97 at 40+0.4.
  - A residual connection across layer two: +8.05, +8.21 and +9.38 at 25k nodes, 8+0.08 and 40+0.4.
- **akimbo** — [releases](https://github.com/jw1912/akimbo/releases):

  | Network | Data | Result |
  | --- | --- | --- |
  | 768→256×2→1, replacing the hand-crafted eval | — | +387 |
  | 768→512×2→8 (output buckets) | 1B positions | +96, with other changes |
  | (768→768)×2→1 | 1.5B | +73 |
  | (768×4hm → 1024)×2 → 1 | 1.5B | +34.9 ± 16.9, only 350 games |
- **Leorik** (self-play data) — [Leorik README](https://github.com/lithander/Leorik):

  | Version | Network | Data | CCRL Blitz |
  | --- | --- | --- | --- |
  | 3.0 | 768 → 256 | 622M positions | 3276 |
  | 3.1 | 640, SCReLU | 5.2B | 3430 |
  | 3.2 | (768×5 → 640)×2 → 1×8: 5 king buckets, 8 output buckets | over 6B | 3496 |
- **Leorik devlog:** king buckets were worth about +20 Elo even though refreshes cost about 10% of
  nodes per second, and about +30 together with output buckets —
  [TalkChess p=987095](https://www.talkchess.com/forum3/viewtopic.php?p=987095) /
  [p=987228](https://www.talkchess.com/viewtopic.php?p=987228) (search snippet only).
- **Output buckets in a small engine:** about +14 Elo for piece-count output buckets —
  [kevlu8 Lichess blog](https://lichess.org/@/kevlu8/blog/the-gruelling-road-to-2800-elo/7xyxsA3T)
  (search snippet only).
- **bullet's guidance** — [docs/1-basics.md](https://github.com/jw1912/bullet/blob/579b78b37a694cacd6e9ede4706386c15c34837c/docs/1-basics.md):
  - Start with plain 768 inputs: "You won't have enough data for things like HalfKA/HalfKP at first
    (or perhaps ever, custom bucket schemes will generally serve better with less data)".
  - On extra layers: "Usually more beneficial to just increase the size of the first hidden layer (up
    to at least 1024)". Extra layers need "manual SIMD and well considered quantisation tech".
- **bullet's example progression** —
  [examples/progression](https://github.com/jw1912/bullet/tree/579b78b37a694cacd6e9ede4706386c15c34837c/examples/progression).
  A superbatch is 6,104 batches × 16,384 positions, about 100M positions seen.

  | Example | Network | Training length |
  | --- | --- | --- |
  | 1_simple | hidden layer 128 | 40 superbatches |
  | 2_output_buckets | 512 | 320 |
  | 3_input_buckets | 1024 + factoriser | 640 |
  | 4_multi_layer | 1024, pairwise CReLU | 800 |
- **A forum rule of thumb:** indexing by king square or king bucket "may need at least a billion"
  positions — [TalkChess p=940373](https://talkchess.com/viewtopic.php?p=940373) (search snippet
  only; which post it came from is uncertain).
- **Training-side gains in Viridithas** (not architecture) —
  [releases page 1](https://github.com/cosmobobak/viridithas-networks/releases):
  - Distilling from "a much larger teacher net": +3.69 ± 2.35 at 40+0.4 over 19,226 games.
  - Ranger instead of Adam: +8.98 ± 3.92.
  - Better initialisation and weight clipping: +6.52 ± 3.70.

**ChessSI's current state** (branch at `2ab6bd2`)
- **Network** (`src/nnue.cpp`)
  - (768 → H)×2 → SCReLU → 1, with QA 255, QB 64, eval scale 400.
  - The hidden size H is set at run time, not compile time.
  - Accumulators are updated eagerly every ply, in auto-vectorised C++. The output already multiplies
    v·w in int16 before multiplying by v (the SCReLU trick).
- **Measurements** (`docs/IDEAS.md`)
  - At 47.4M positions, h256, h384 and h512 reached the same validation loss.
  - At 64.6M: h256 0.00653, h384 0.00649, h512 0.00649.
  - "h512 searches about 40% slower".
  - Eight material output buckets: −0.7 ± 14.7 over 1,002 games at 64.6M positions.

### Inferences
- **Known backlog for ChessSI, ranked.** Expected Elo is my estimate for ChessSI at 10+0.1 on a single
  thread, not a sourced figure.

| Rank | Feature | Evidence | Pays off from | Expected for ChessSI | Cost |
| --- | --- | --- | --- | --- | --- |
| 1 | Faster inference: hand-written AVX2/AVX-VNNI and NEON, compile-time H, register-tiled and lazy updates | Tetrarch: lazy per-perspective updates gave +59.8% NPS, part of a +63 Elo speed release; cost model in section 3 | Any data | +10 to +23 if the network gets 2× faster | 1-2 days; bench unchanged; 1 SPRT |
| 2 | Horizontal mirroring of the 768 inputs (flip so the own king is on files e-h; refresh when it crosses) | Stockfish: "hardly measurable" in HalfKA; used by almost every bullet engine | Any (no new weights) | 0 to +8 | 0.5 day; trainer plus refresh logic |
| 3 | 4-8 mirrored king buckets with a factoriser, plus Finny tables | Leorik +20 at −10% NPS; Viridithas 9 buckets +23.6 at STC (confounded with other changes); akimbo 4hm at 1.5B | About 0.5-1.5B positions (earlier with a factoriser) | 0-10 at 100-300M; +10-20 at 0.5-1B | 1-2 days; 2-3 GPU runs; 1-2 SPRTs |
| 4 | 8 output buckets, retested | About +14 in a small engine; Viridithas +20-24 together with more data; ChessSI level at 64.6M | About 0.5-1B | 0 to +10 | The branch exists; 1 run, 1 SPRT |
| 5 | Distilling from a wide teacher trained only on the GPU (ChessSI's own network, so within the data rule) | Viridithas +3.69 at LTC; PlentyChess uses self-distillation | Any | +3 to +10 | GPU hours only |
| 6 | Width 384-768, after rank 1 | ChessSI's validation gap is opening; Leorik used 640 at 5.2B; akimbo 768-1024 at 1.5B | About 0.3-1B, and only after faster inference | −15 to +20 depending on speed | Training only |
| 7 | Pairwise multiplication plus a small second layer (→16→32→1 × 8), int8 L1 weights, sparse L1 | Viridithas multi-layer +9.4 at LTC with 2048 width; residual +8-9; Stockfish L2 16→32 +3 at LTC | About 1-2B, with manual SIMD | −20 to +30, depending on the implementation | 3-5 days |
| 8 | Threat inputs, then pawn pairs | Stockfish +2 / +3.8 / +7 (STC / LTC / VVLTC); Viridithas +27 at fixed nodes but +3 to +5 at time controls; pawn pairs +1-2 | Several billion (PlentyChess 15B+) | ≤0 before 1B; +5 to +25 at 3B+ | 1-2 weeks |
| — | Dual network; PSQT shortcut | Stockfish retired both in 2026 | — | Skip | — |

- **Test at fixed nodes as well as by time.** Gains at fixed nodes shrink a lot at real time controls
  when a feature costs speed (Viridithas: 16 buckets +31.6 → +4.8; threat inputs +27.4 → +3.0 / +5.4).
  ChessSI should test each architecture change at fixed nodes, which measures eval quality, and at
  10+0.1, which gives the net effect.
- **What Stockfish's path shows.** Threat inputs let L1 fall from 3072 to 1024, then L2 was doubled, the
  small network retired and the PSQT output removed. Richer inputs replaced width there, but only with
  Stockfish-scale data relabelled by Lc0. That path is not a guide below about 1B of ChessSI's own
  positions.
- **Which engines to compare with.** Alexandria, Obsidian and Stockfish train on Lc0-derived data, so
  their data scale says little about ChessSI's own-data regime. Viridithas, Stormphrax, PlentyChess,
  Leorik and akimbo are the right comparisons.
- **The single-layer ceiling is still high.** Leorik reached CCRL Blitz 3496 with one hidden layer of
  640, 5 king buckets and 8 output buckets. ChessSI at 3176 has a lot of room before it needs a
  multi-layer network.

### Gaps
- **No Elo found for several features:** Finny tables, sparse L1 inference, permuting the feature
  transformer, and Stockfish's queen dimension in K32Q2. The date K32Q2 landed was not found either.
- **Small-network removal:** the Stockfish commit that removed it was not found; only secondary
  coverage of the Stockfish 19 notes.
- **Sources not reachable:** TalkChess, the Lichess blog, cosmo.tardis.ac (the Viridithas author's NNUE
  performance article, recommended by bullet's docs) and Discord could not be read in full.
- **No controlled data-scale curves.** The "pays off from" column is inferred from release notes in
  which data, width and buckets often changed together.

## 2. Which genuinely novel efficient-ML architecture ideas have or have not been tried in NNUE chess, and which could work within incremental updates?

### Takeaway
Many ideas from efficient machine learning are already in NNUE chess, under other names:
- hard-gated mixtures of experts: output buckets and layer stacks;
- learned feature crosses: pairwise multiplication, threat inputs, pawn pairs;
- int8 mixed precision: i8 threat weights and int8 L1 weights;
- activation sparsity: sparse-input L1 and feature-transformer permutation;
- wide-to-narrow distillation: Viridithas, PlentyChess.

No public use was found of:
- low-rank or structured parameterisations of king buckets;
- soft or interpolated output buckets (proposed, never implemented);
- conditioning the activation on the bucket (FiLM-style);
- nested Matryoshka accumulators;
- block-sparse feature-transformer weights;
- int4 weights;
- learned bucket layouts.

A cached pawn-king subnetwork exists only with a hand-crafted eval (Ethereal) and as an untested forum
proposal. Attention does not survive incremental updates; its NNUE-compatible substitutes (piece-pair
features) are already known.

### Cited Findings
- **Mixtures of experts**
  - The closest published work is M2CTS. It gates between phase-specialised full networks inside an
    AlphaZero-style MCTS and reports up to +122 Elo over a single model —
    [arXiv 2401.16852](https://arxiv.org/abs/2401.16852).
  - TalkChess posts propose a gate network that picks among several NNUE experts, with no results —
    [p=992258](https://www.talkchess.com/viewtopic.php?p=992258),
    [p=992191](https://talkchess.com/viewtopic.php?p=992191) (search snippets only).
  - The hard-gated forms are standard: material output buckets in bullet
    ([example 2](https://github.com/jw1912/bullet/tree/579b78b37a694cacd6e9ede4706386c15c34837c/examples/progression))
    and Stockfish's 32 layer stacks, chosen by piece count and queen presence
    ([network.cpp](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/network.cpp)).
- **Soft or interpolated phase experts**
  - A TalkChess post proposes training separate phase networks and then "smoothly interpolate as we
    go from one phase to the next" — [p=879993](https://talkchess.com/viewtopic.php?p=879993) (search
    snippet only).
  - The Leorik devlog likens output buckets to tapered PSQTs —
    [p=987095](https://www.talkchess.com/forum3/viewtopic.php?p=987095) (search snippet only).
  - No interpolation was found in the 10 cloned repositories (grep for lerp, interpolate, taper, soft
    buckets).
- **Factorisers and other training-time reparameterisations of buckets are known**
  - bullet merges a factoriser `l0f` into the bucketed weights when it saves the network —
    [example 3](https://github.com/jw1912/bullet/tree/579b78b37a694cacd6e9ede4706386c15c34837c/examples/progression).
  - nnue-pytorch documents virtual features, including K and HalfRelativeKP factors —
    [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
  - Web searches for low-rank or LoRA NNUE found nothing. Grepping all 10 clones for low-rank, LoRA,
    mixture, gating, Matryoshka, nested, early exit, attention, k-means, int4 and distil found no
    NNUE-architecture hits.
- **Learned feature crosses are known**
  - Full threats model "a subset of 'AA' (i.e. pairs of 'A' features)".
  - PP_3Wide models pairs of pawns on the same or adjacent files.

  Source: [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
  Pairwise multiplication is in Stockfish, Viridithas and Stormphrax (links in section 1).
- **Mixed precision**
  - i8 feature-transformer weights for threats and pawn pairs in Stockfish
    ([nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md))
    and PlentyChess (`int8_t inputThreatWeights`,
    [nnue.h](https://github.com/Yoshie2000/PlentyChess/blob/9ca005740a35967c1403bfb9a3a9032c97ee003d/src/nnue.h)).
  - Tetrarch's int8 propagation: +23.5% NPS —
    [Tetrarch releases](https://github.com/IchNukeDichWeg/Tetrarch/releases).
  - A search for int4 NNUE weights found nothing.
- **Sparsity**
  - Activation sparsity is used: Stockfish's sparse-input L1 (`AffineTransformSparseInput`, NNZ) —
    [nnue_architecture.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_architecture.h).
  - The feature transformer is permuted so that frequently active neurons come first —
    [ftperm.py](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/ftperm.py);
    Viridithas "hyperstition" in [releases page 3](https://github.com/cosmobobak/viridithas-networks/releases?page=3).
  - No source on weight pruning or structured weight sparsity of the feature transformer was found
    (web search and the clones).
- **Distillation**
  - Viridithas "acolyte" "Distills from `nemmerle`, a much larger teacher net", +3.69 ± 2.35 at 40+0.4 —
    [releases page 1](https://github.com/cosmobobak/viridithas-networks/releases).
  - PlentyChess uses "self-distillation techniques for part of the training" —
    [README](https://github.com/Yoshie2000/PlentyChess/blob/9ca005740a35967c1403bfb9a3a9032c97ee003d/README.md).
  - This matters for ChessSI's own log: its "self-distillation head" should be recorded as Partially
    known.
- **Nested or early-exit networks**
  - Nothing found for NNUE.
  - The closest known designs are Stockfish's separate small network (added in 16.1, retired in 19) —
    [newreleases.io](https://newreleases.io/project/github/official-stockfish/Stockfish/release/sf_19) —
    and a Stockfish 14-era commit that removed a "lazy" path inside the NNUE evaluation —
    [nextchessmove dev build page](https://m.nextchessmove.com/dev-builds/sf14/f193778446acc6e60d7f0f99c6eb01489f89e962).
- **Cached pawn-king network**
  - Ethereal 12.75 used a [224, 32, 1] pawn-king network alongside its hand-crafted eval. It reported
    over 92% hits in its pawn-king cache, about 2.5% speed cost for the incremental update and under 1%
    for the eval itself — [TalkChess p=861680](https://talkchess.com/viewtopic.php?p=861680) (search
    snippet only).
  - Those figures conflict with Grant's statement, in the 12.75 release thread, that neither network is
    "Updated Incrementally" —
    [p=864847](https://talkchess.com/viewtopic.php?p=864847) (search snippet only).
  - A TalkChess thread proposed feeding a pawn-king network's output into an NNUE hidden layer, cached
    in a pawn-king table. No result was found —
    [p=924777](https://talkchess.com/viewtopic.php?p=924777) (search snippet only).
- **Learned bucket layouts**
  - Hand-designed layouts vary widely: 4hm in akimbo, 5 in Leorik, 10 in Reckless, 12 in PlentyChess
    and GaiaChess, 13 in Obsidian, 14 in Renegade, 16 in Viridithas, Alexandria and Berserk, and
    32 × queen presence in Stockfish (links in section 1).
  - The Leorik devlog says there are plenty of viable layouts —
    [p=987228](https://www.talkchess.com/viewtopic.php?p=987228) (search snippet only).
  - No learned or clustered layout was found.
- **Background methods from machine learning** (not fetched; cited as the source field):
  - LoRA ([arXiv 2106.09685](https://arxiv.org/abs/2106.09685));
  - Matryoshka representations ([arXiv 2205.13147](https://arxiv.org/abs/2205.13147));
  - FiLM conditioning ([arXiv 1709.07871](https://arxiv.org/abs/1709.07871));
  - sparsely gated mixtures of experts ([arXiv 1701.06538](https://arxiv.org/abs/1701.06538));
  - 2:4 structured sparsity ([arXiv 2104.08378](https://arxiv.org/abs/2104.08378));
  - GPTQ low-bit quantisation ([arXiv 2210.17323](https://arxiv.org/abs/2210.17323)).

### Inferences

The eight candidates below are ranked by expected value per unit of cost for ChessSI at 0.1-1B
positions. All of them train only on ChessSI's own data, and any teacher is a ChessSI network.

**N1. Low-rank king-bucket residuals ("rank-scheduled king buckets")**
- **Idea.** Write each bucket's feature weights as W_b = W_shared + U_b·V. V (r × H) is shared, U_b (768
  × r) belongs to bucket b, and r is 4-64. At export the weights are expanded into ordinary int16
  bucketed weights, so inference is the same as plain king buckets. The rank r is a dial that can grow
  with the data: r = 0 means no buckets, and large r approaches full buckets with a factoriser. A
  variant ties the residual by piece position relative to the king (HalfRelativeKP-style).
  - Source field: LoRA plus NNUE factorisers.
- **Prior art: Partially known.**
  - The factoriser is Known (bullet example 3; nnue-pytorch virtual features, including HalfRelativeKP).
  - A low-rank or shared-subspace residual was not found (web; 10 repositories).
- **Why it could help.** Data is ChessSI's binding constraint: h384 and h512 were level with h256 at
  47M positions, and the 8 output buckets were level at 64.6M. Full per-bucket residuals see rare king
  squares rarely. A rank-r residual pools that evidence, so buckets should pay off earlier than the
  "about 1B" rule of thumb.
- **Expected Elo.** +3 to +10 over plain factorised buckets at 100M-1B, if any bucket scheme gains.
  Confidence is low to moderate (about 30% chance of a clear win). The speed cost is the same as plain
  buckets: refreshes, which Finny tables mitigate.
- **Cost.**
  - Trainer: about 60 lines.
  - The engine needs king-bucket support, which the Known path needs anyway.
  - About 4 GPU runs of 30 minutes, and one SPRT of 1-3k games.
- **Minimal experiment.** On a frozen snapshot with the stable per-game validation split (91M now, then
  about 250M), train five networks: no buckets; 8 mirrored buckets with a full factoriser; and the
  low-rank version at r = 4, 16 and 64. Compare validation losses. Then SPRT the best bucketed network
  against the no-bucket control, in one binary, at 25k fixed nodes and at 10+0.1.
- **Risks.** It may only tie a full factoriser. Validation-loss gains may not become Elo. A low-rank
  model may train slower under Adam.

**N2. Phase-interpolated output experts (train soft; deploy soft or hard)**
- **Idea.** Replace hard material buckets with K heads blended by a smooth phase p. Two options:
  - K = 2 (middlegame/endgame), with p taken from non-pawn material as in a tapered eval;
  - 8 knots over piece count, blending the two neighbouring knots linearly.

  Every head gets gradient from every position it is close to, so the data is not split K ways.
  Deployment has two options. Soft deployment computes the SCReLU once and then two dot products. Hard
  deployment evaluates the trained interpolation at each bucket's centre and exports ordinary hard
  buckets, at zero inference cost.
  - Source field: tapered evaluation; soft mixtures of experts.
- **Prior art: Partially known.**
  - Hard output buckets and layer stacks are Known.
  - nnue-pytorch suggests a "factorizer for the first layer in the layer stacks".
  - A TalkChess post proposed interpolating between phase networks.
  - No implementation or result was found.
- **Why it could help.** ChessSI's 8 hard buckets were level (−0.7 ± 14.7) at 64.6M. That fits data
  fragmentation: each bucket's 512 output weights see about 1/8 of the data. Interpolation keeps the
  phase specialisation while sharing the data.
- **Expected Elo.** 0 to +8, low to moderate confidence.
  - Hard deployment costs nothing in speed.
  - Soft deployment costs about 0.6× more in the output layer, which at today's inference is roughly
    −3 to −8% NPS.
- **Cost.** About 30 lines in the trainer, an export change, and a few lines in the engine (the output
  bucket branch already exists). One or two runs and one SPRT.
- **Minimal experiment.** Same data and seed for four networks: 1 head; 8 hard buckets (existing
  branch); 2-head tapered; 8-knot interpolated, exported hard. Compare validation losses, then SPRT the
  best against the 1-head network.
- **Risks.** It may equal hard buckets, and a small effect is hard to detect. Its interplay with the
  auxiliary head is unknown.

**N3. Cached pawn-king subnetwork feeding the output**
- **Idea.** Add a separate, deeper network over pawns and kings only, for example 2 × (96 + 64) inputs
  → 128 → 32. It is evaluated only when the pawn-king key changes and cached in a pawn-king table. A
  learned linear term carries its outputs into the final evaluation, or into L2 once there is a second
  layer. Caching lets it be deeper than anything incrementally updated.
  - Source field: hash-cached evaluation; the pawn-king network in Ethereal.
- **Prior art: Partially known.**
  - Ethereal's pawn-king network (with a hand-crafted eval) is Known.
  - Concatenating a pawn-king network into an NNUE was proposed on TalkChess (p=924777), with no result
    found.
  - Stockfish's pawn-pair inputs (Known, about +1-2 at LTC) are an incremental, linear alternative.
- **Why it could help.** ChessSI's single SCReLU layer represents pawn structure mostly as a sum of
  per-pawn terms passed through one squaring. Passed-pawn races, majorities and king shelters are
  multi-pawn interactions. A cached deep branch adds them at almost no amortised cost; Ethereal reported
  over 92% cache hits.
- **Expected Elo.** +3 to +15 for a single-layer network, and 0 to +5 once ChessSI has a second layer.
  Low to moderate confidence. Speed cost about −1 to −3%.
- **Cost.**
  - Trainer: a second branch, about 80 lines.
  - Engine: a pawn-king key, a table and a small dense inference, about 100-150 lines.
  - Two runs and one SPRT.
- **Minimal experiment.** Train with and without the branch on the same 91M snapshot and compare
  validation loss. Measure the pawn-king hit rate in `bench`. Then SPRT at 10+0.1.
- **Risks.** The feature transformer may already capture most of this. In joint training the branch
  may take over what the feature transformer learned. Pawn captures in quiescence cause cache misses.

**N4. Bucket-conditioned activation (a FiLM-style scale and shift on the accumulator)**
- **Idea.** Each material bucket b, or a soft phase, gets a learned per-neuron gain γ_b and offset β_b,
  applied before the clamp: h_i = SCReLU(γ_{b,i}·acc_i + β_{b,i}). That is 2H parameters per bucket,
  against 768H for a copy of the feature transformer. At evaluation it costs one multiply-high and one
  add per neuron; the incremental update is unchanged. The minimal version keeps only β.
  - Source field: FiLM conditioning.
- **Prior art: Novel (none found).** The closest Known techniques are output buckets and layer stacks,
  which act after the nonlinearity, and Stockfish's queen-state input buckets, which duplicate the
  whole feature transformer.
- **Why it could help.** Output buckets are linear in the activations, so they cannot move a neuron's
  saturation point by phase. Phase-dependent thresholds let one feature detector be active in endgames
  and saturated in middlegames: a cheap phase-dependent nonlinearity that suits a single-layer network.
- **Expected Elo.** 0 to +8, low confidence. Speed cost about −2 to −5% at evaluation.
- **Cost.** About 30 lines in the trainer and care with quantisation (γ in Q8.8, or applied in
  int32). One or two runs and one SPRT.
- **Minimal experiment.** Train β-only and γ+β over 8 material buckets, initialised at identity, on
  91M positions. Compare against the baseline and against 8 output buckets. SPRT only if validation
  loss improves by more than about 0.5%.
- **Risks.** It may behave like output buckets plus a bias. Quantising γ near 1 is awkward.

**N5. Matryoshka (nested) accumulator: a built-in small network with lazy tail updates**
- **Idea.** Train the feature transformer so that its first k = H/4 neurons, with their own output
  weights, form a usable small evaluation (loss at prefix k plus loss at full H). In search:
  - update the prefix eagerly and queue the tail's deltas, catching up only when a full evaluation is
    needed;
  - use the prefix eval where precision barely matters, for example a quiescence stand-pat or a
    reverse-futility decision far from its margin.
  - Source field: Matryoshka representation learning; early-exit networks.
- **Prior art: Novel as a combination; Partially known in spirit.** Stockfish's separate small network
  (16.1, retired in 19) and classical lazy evaluation are the related ideas. Nothing on nested-width
  NNUE was found.
- **Why it could help.** If the NNUE takes about 40% of node time (section 3) and half of evaluations
  can use a quarter-width prefix, NPS rises by roughly 12-18%.
- **Expected Elo.** −5 to +10, low confidence. Stockfish's own small network was retired because it
  lost quality where used.
- **Cost.**
  - Trainer: easy.
  - Engine: high (tail queues per ply plus a selection policy).
  - Two to four SPRTs.
- **Minimal experiment.** Step 1 needs no engine change: train with the nested loss and check that the
  full-width validation loss is unchanged while the prefix comes close to a standalone h64. Only then
  try prefix-only stand-pat in quiescence when the prefix eval minus a margin is at least beta.
- **Risks.** Complexity. The bookkeeping can eat the gain. It matters mostly at H ≥ 512.

**N6. Learned king-bucket layout (cluster first, then bucket)**
- **Idea.** Train once with a residual per mirrored king square (32 of them, low-rank as in N1).
  Cluster the squares by their learned residuals with k-means, K = 4-12, and retrain with that map.
  Re-cluster as the data grows to choose K. Penalise clusters that the king crosses often, since each
  crossing costs a refresh.
  - Source field: clustering learned embeddings.
- **Prior art: Novel (method).** Layouts are hand-made and tuned by SPRT; none found learned.
- **Expected Elo.** 0 to +5 over a good hand layout, low confidence. Training-only cost of about 1 GPU
  hour.
- **Minimal experiment.** Compare a hand-made 8-bucket layout with a clustered 8-bucket layout on the
  same data: validation loss, then an SPRT.
- **Risks.** Many layouts are nearly equivalent, so the effect is small and needs many games.

**N7. Block-sparse feature-transformer weights (structured sparsity)**
- **Idea.** Each input row is non-zero only in a fixed subset of neuron blocks, for example 2 of 4
  blocks. The mask is learned with a group-lasso penalty and then frozen. Updates touch only the
  non-zero blocks, so h512 at 50% density costs the same update time as dense h256. Evaluation stays
  dense.
  - Source field: 2:4 and other structured sparsity.
- **Prior art: Novel (none found).** Activation sparsity is Known; feature-transformer weight sparsity
  was not found.
- **Why it could help.** Width is blocked by speed: h512 costs −40% NPS. This halves the update part of
  that cost.
- **Expected Elo.** −5 to +10, low confidence. Evaluation remains about half of the network's time, so
  the saving is partial.
- **Cost.**
  - Trainer: about 80 lines.
  - Engine: per-feature block lists.
  - Three or four runs.
- **Minimal experiment.** At equal update cost, compare dense h256 with 50%-sparse h512: validation
  loss, NPS, then an SPRT.
- **Risks.** The accuracy lost to sparsity may cancel the gain from width. Memory access becomes
  irregular.

**N8. int4 / mixed-precision feature-transformer rows**
- **Idea.** Store rarely used or small-magnitude rows (bucket residuals, later threat rows) as int4
  with a per-row scale, unpacked to int16 on the fly. Common rows stay int16.
  - Source field: low-bit quantisation (GPTQ and similar).
- **Prior art: Partially known.** i8 rows are Known (Stockfish, PlentyChess); int4 was not found.
- **Why it could help.** It pays only once the feature transformer outgrows L2, for example 8 buckets ×
  512 × 768 × 2 B ≈ 6.3 MB. Today's h256 table is 393 KB.
- **Expected Elo.** 0 now, perhaps +1 to +5 later, and only through speed. Low confidence.
- **Minimal experiment.** A microbenchmark of int16, int8 and int4 copies of a bucketed table, plus the
  validation loss of a model trained with clipping that simulates the quantisation.
- **Risks.** Unpacking may cost more than the bandwidth saved on AVX2.

**Not candidates**
- **Attention.** Attention over pieces cannot be updated incrementally. Its NNUE-compatible
  approximations are pairwise piece features (threats, pawn pairs) and pairwise multiplication, which
  are Known.
- **Wide-to-narrow distillation.** It is Known (Viridithas, PlentyChess), so it belongs in the backlog.

### Gaps
- **Discord.** The Stockfish and Engine Programming Discords, where much NNUE work is discussed, could
  not be searched. Any "not found" verdict above could be overturned there.
- **Partial reads.** TalkChess threads were seen only as search snippets.
- **No arXiv paper on NNUE-specific mixtures of experts, low-rank layers or int4 was found.** The
  machine-learning background papers above were not fetched.
- **Shogi NNUE work was not checked.** It is a likely place for feature-transformer variants.

## 3. What is the best next architectural step for ChessSI at 100M to 1B+ positions (king buckets, width, or a second layer), and what is the speed/Elo trade-off at about 3.8M nodes per second?

### Takeaway
- **First: inference speed.** It is cheap, does not change the bench node count, and lowers the price
  of every later widening.
- **Then king buckets.** 4-8 mirrored buckets with a factoriser, alongside the novel low-rank variant
  (N1), at H = 256. Buckets add capacity with almost no per-node compute.
- **Then width,** after the speed work.
- **Then a second layer,** at about 1B positions or more, once int8 SIMD exists.

ChessSI's own measurement that h512 is about 40% slower implies the network takes about 40% of node
time. At that cost, h512 needs about +24 to +34 Elo of evaluation quality just to break even. The
validation gap of about 0.6% at 64.6M positions is far from that.

### Cited Findings
- **ChessSI measurements.** "h512 searches about 40% slower". Wider networks were level at 47.4M
  positions and "only slightly better at 64.6M positions" — ChessSI `docs/IDEAS.md`.
- **Data rate.** Data will reach about 100M-1B+ positions, with a second PC adding about 30-60M
  positions an hour — task brief.
- **Bench speed** with the network is about 1.3-3.8M nodes per second per core, depending on the CPU —
  task brief.
- **Hardware.** The test machine is a Core Ultra 7 265K with AVX2 and AVX-VNNI and no AVX-512, plus an
  M2 Max (NEON) — task brief.
- **Speed-to-Elo exchange rate**
  - Tetrarch's release notes measured "+115 Elo per doubling of search speed, well above the +50 to +70
    a two-player engine expects", and "A 10% speedup is about +15 Elo here". Tetrarch is apparently not
    a two-player chess engine, so treat these as rough exchange rates —
    [Tetrarch releases](https://github.com/IchNukeDichWeg/Tetrarch/releases).
  - Leorik's king buckets gained about +20 Elo despite about −10% NPS —
    [TalkChess p=987228](https://www.talkchess.com/viewtopic.php?p=987228) (search snippet only).
- **How others progressed**
  - bullet recommends widening the first layer "up to at least 1024" before adding layers —
    [docs/1-basics.md](https://github.com/jw1912/bullet/blob/579b78b37a694cacd6e9ede4706386c15c34837c/docs/1-basics.md).
  - akimbo went 512 + output buckets at 1B, then 768 at 1.5B, then 1024 + 4hm buckets at 1.5B —
    [releases](https://github.com/jw1912/akimbo/releases).
  - Leorik went 256 at 622M, then 640 at 5.2B, then 5 buckets + 8 output buckets at 6B or more —
    [README](https://github.com/lithander/Leorik).
  - Viridithas went 768 at 963M, then 1536, then 4 → 9 buckets, then 8 output buckets, then 2048 + 16
    buckets, then multi-layer —
    [releases](https://github.com/cosmobobak/viridithas-networks/releases?page=4).

### Inferences
- **Speed cost model.** Assume node time is T0 + c·H. ChessSI's 40% figure gives T0 = 384c, so the
  network is 40% of node time at h256. The Elo columns use 50-70 Elo per doubling of speed.

| H | Time vs h256 | NPS from 3.8M | Elo from speed (50 / 70 per doubling) |
| --- | --- | --- | --- |
| 128 | 0.80 | 4.75M | +16 / +23 |
| 384 | 1.20 | 3.17M | −13 / −18 |
| 512 | 1.40 | 2.71M | −24 / −34 |
| 768 | 1.80 | 2.11M | −42 / −59 |
| 1024 | 2.20 | 1.73M | −57 / −80 |

  - Making the network 2× faster at h256 gives a time ratio of 0.80, worth about +16 to +23 Elo, and
    makes h512 cost what h256 costs today.
  - Check the 40% share with `perf record ./chesssi bench` before relying on it. Cache effects and the
    runtime-H loops may make the cost non-linear.
- **Roadmap by data stage.** The second PC may reach 1B positions within a day or two of generation,
  so plan by data, not by calendar.
  - **Now (any data):**
    - Measure the exchange rate once, with a time-odds SPRT (10+0.1 against 5+0.05) or a 2× node-odds
      match. This gives ChessSI's own Elo per doubling for every later decision.
    - Profile to find the network's share of node time.
    - Rewrite inference with the bench unchanged (section 4).
  - **100-300M:**
    - Horizontal mirroring of the 768 inputs (no new weights).
    - Retest the 8 output buckets together with the interpolated version (N2) on the same data.
    - Train a wide teacher on the GPU only (for example h1024 × 8 buckets) and distil it into h256
      (Known; Viridithas +3.7). The teacher also shows how much quality is missing.
  - **300M-1B:**
    - King buckets: 4-8 mirrored, with a factoriser (Known), against the low-rank variant (N1), plus
      Finny tables.
    - At H = 256, 8 buckets come to about 3.1 MB of int16 feature weights. That is about one P-core's
      L2 if Arrow Lake's P-core L2 is 3 MB (assumed, not verified).
    - Then re-sweep h256, h384 and h512 on the faster binary. Accept width only if a fixed-node SPRT
      gain exceeds the speed cost measured in the time-control SPRT.
  - **1B and above:**
    - Pairwise multiplication + L1 → 16 → 32 → 1 × 8 output buckets.
    - int8 L1 weights with VNNI `dpbusd`, sparse L1 with feature-transformer permutation.
    - A residual connection across layer 2 (Viridithas +8-9).
    - Width 768-1024.
  - **Several billion:** threat inputs, then pawn pairs.
- **Why king buckets before width or a second layer.**
  - Buckets add parameters without adding per-node compute. The extra cost is only refreshes, and Finny
    tables recover most of the roughly −10% Leorik saw.
  - Width pays in compute on every node.
  - A second layer needs int8 SIMD and, per bullet's guidance, more data than ChessSI has.
  - Data hunger is the risk with buckets. Factorisers and N1 are the hedge. If buckets are level at
    300M, re-run at 1B before discarding them, as ChessSI's log already shows ideas changing sign with
    the baseline.

### Gaps
- **Unmeasured inputs.** The network's real share of node time and ChessSI's Elo per doubling of speed
  have not been measured. Both drive the table above.
- **Cache size.** Arrow Lake's per-core L2 size was not verified from a source.
- **No controlled study** of when king buckets start paying in own-data chess engines; only release
  notes, where several changes are mixed together.

## 4. Which SIMD and inference optimisations matter most for (768 → H) × 2 SCReLU networks on AVX2, AVX-VNNI, AVX-512 and NEON?

### Takeaway
ChessSI already has the main arithmetic trick for SCReLU: multiply v·w in int16, then multiply by v
into int32, which allows QA 255. The remaining gains come from four places:
- **Explicit intrinsics** with a compile-time H, so whole accumulator tiles stay in registers.
- **Lazy updates:** compute the accumulator only when an evaluation is needed, and fuse two deltas.
- **AVX-VNNI's `vpdpwssd`**, which fuses the multiply-add and the accumulate in the output dot product.
- **Later:** int8 L1 weights with `vpdpbusd`, sparse L1, Finny tables and i8 weights for the big
  feature sets.

Accumulators stay int16 in every engine examined. int8 appears only in weights (threat rows and L1)
and in post-accumulator activations.

### Cited Findings
- **ChessSI's evaluation today** (`src/nnue.cpp`)
  - It clamps to [0, QA], forms v·w in int16 (checked at load: |w| ≤ 128, so QA·w fits int16), and then
    sums (v·w)·v in int32 over chunks of 32. The comment notes this gives "twice the lanes of the plain
    x * x * w form".
  - The weights are clipped to ±1.98 so that 32 pieces plus the bias stay inside int16.
  - Accumulators are updated in do_move for both perspectives, by templated loops over a runtime H.
- **Why QA 255 needed this trick.** Viridithas requantised with QA = 181 "to allow for efficient SIMD
  inference" (artemis), then moved back to QA = 255 (signalis-qa255) —
  [releases page 4](https://github.com/cosmobobak/viridithas-networks/releases?page=4) and
  [page 3](https://github.com/cosmobobak/viridithas-networks/releases?page=3). This is consistent with
  181² < 32,767 being the older way to fit the square in int16 before the v·w-first trick.
- **AVX-VNNI paths (`dpbusd` / `dpwssd`)** exist in Stockfish
  ([simd.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/simd.h)),
  Viridithas, Stormphrax (avx2.h, neon.h, multilayer.h) and Obsidian, found by grepping the clones.
- **int8 propagation** after the accumulator gave +23.5% NPS in Tetrarch (CReLU activations bounded to
  [0, 127]). Its lazy per-perspective updates gave +59.8% NPS —
  [Tetrarch releases](https://github.com/IchNukeDichWeg/Tetrarch/releases).
- **i8 threat weights** gave +5% speed on x86 and +10% on ARM —
  [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md).
- **Stockfish's update machinery:** lazy accumulators (`computed` flags, forward and backward
  incremental updates, `forward_update_incremental_both`) and Finny tables —
  [nnue_accumulator.h](https://github.com/official-stockfish/Stockfish/blob/effdc3fd3f6de6e75fe1374a51a7a7eed66f880b/src/nnue/nnue_accumulator.h).
- **Sparse L1:** documented with optimised AVX2 kernels in
  [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md)
  ("Linear layer with sparse input", "blocked sparse input").
- **Stockfish's quantisation scheme** — "Stockfish quantization scheme" section of
  [nnue.md](https://github.com/official-stockfish/nnue-pytorch/blob/ed84cc1fd2255faa0f33dcfa7839c9b6b4bb49b8/docs/nnue.md):
  - The feature transformer cannot use int8 accumulators: "using int8 integers for the accumulator
    doesn't provide enough space", so accumulators are int16.
  - Linear layers take int8 inputs (clipped ReLU on 0..127) with int8 multiplication and int32
    accumulation.
- **Profile of an NNUE engine:** a TalkChess thread split the work into "Incremental Update (50%),
  FeatureTransform (5%), Propagation (5%)". Stockfish developers questioned the thread's headline
  "60% faster" claim — [TalkChess p=948872](https://talkchess.com/viewtopic.php?p=948872) (search
  snippet only).

### Inferences
- **Priorities for ChessSI** (265K: AVX2 + AVX-VNNI; M2: NEON), in order:
  1. **Compile-time H** (a template instantiated for 128, 256, 384, 512, 768 and 1024), `__restrict`
     pointers, and no `std::vector` allocation on `evaluate()`'s fallback path. The compiler can then
     fully unroll the loops and drop alias checks.
  2. **Register-tiled updates.** For each 256-lane tile (16 ymm × 16 int16), load the previous
     accumulator once, apply all adds and subtracts, and store once, for both perspectives. On NEON,
     use 32 q-registers × 8 lanes.
  3. **Lazy updates.** Record the delta in do_move. Compute an accumulator only when `evaluate()` needs
     it, walking back to the last computed ply. Fuse two pending deltas in one pass, as Stockfish does.
     This saves the updates at TT cutoffs and in-check nodes, which never evaluate.
  4. **Output dot product.** `max/min_epi16` → `mullo_epi16(v, w)` → `madd_epi16(prod, v)` →
     accumulate. With AVX-VNNI, `_mm256_dpwssd_avx_epi32(acc, prod, v)` fuses the last two steps. On
     NEON: `vmulq_s16` then `vmlal_s16` / `vmlal_high_s16`.
  5. **Check each step.** The bench node count must not change, and each step needs its own SPRT, per
     ChessSI's rules.
- **AVX-512 does not apply** to the 265K. Keep a generic and an AVX2 path, and NEON for the M2.
- **int16 against int8.**
  - Accumulators must stay int16, because 32 rows times weights of up to about 505 need the range.
  - int8 feature-transformer weights for the 768 piece-square inputs would need a smaller QA or a
    per-row scale. They are not worth it while the table fits in L2 (393 KB at h256).
  - Revisit at 8+ buckets × 512 or with threat inputs, where Stockfish found i8 gives +5% on x86 and
    +10% on ARM.
  - Once there is a second layer, int8 L1 weights × u8 activations with `vpdpbusd` and sparse L1 are
    the standard, worthwhile path.
- **Fused update and evaluate.** A single-layer network with eager updates could compute the SCReLU
  dot product for the new side to move in the same pass as its accumulator update. This saves one
  reload of the accumulator. It was not found in the clones and is probably minor (the data is in L1).
  It conflicts with lazy updates, so pick one.
- **Finny tables** only matter after king buckets (or mirroring) arrive. Then they are the standard way
  to make refreshes cheap: cache an accumulator plus piece bitboards per (perspective, bucket).

### Gaps
- **Speed and Elo of SIMD steps.** No measured NPS or Elo was found for each SIMD step on
  single-layer SCReLU networks.
- **Profile.** ChessSI's actual profile is unknown; this note did not run the engine.
- **The "lizard" name.** No primary source was found for the name of the SCReLU trick.
- **The Viridithas author's article** on NNUE performance improvements (cosmo.tardis.ac, linked from
  bullet's docs) could not be fetched.
