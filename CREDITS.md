# Credits and provenance

ChessSI builds on decades of work by chess programmers, researchers, testers, and tool maintainers.
AI-assisted implementation does not make those methods AI inventions. This inventory distinguishes
material included in ChessSI, techniques and references, and separately installed tools. It records
the evidence available at main commit `014dd979` (2026-11-02); it is not an exhaustive authorship or
license clearance. Remaining questions are in [the attribution review](docs/ATTRIBUTION_REVIEW.md).

## Included evaluation tables and test positions

- **Ronald Friederich (RofChade / PeSTO):** `src/eval.cpp` contains the published PeSTO middlegame
  and endgame piece values and piece-square tables. These are reused values, not tables invented or
  tuned by ChessSI. Sources: [PeSTO's Evaluation Function](https://chessprogramming.org/PeSTO%27s_Evaluation_Function)
  and [Friederich's description](https://rofchade.nl/?p=307). The wiki presentation credits
  **Pawel Koziol's implementation in Tom Kerrigan's TSCP**; [Kerrigan's archive](https://www.tckerrigan.com/Chess/TSCP/Community/)
  records that adaptation. ChessSI changes the board/piece indexing and integration. The wiki page
  names **Gerd Isenberg** as its contributor and carries [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
  A separate permissive grant for the incorporated material has not been recorded in this repo;
  the license question remains open in the review. Do not describe these values as original MIT material.
- **Chess Programming Wiki contributors and the original position authors/testers:**
  [Perft Results](https://chessprogramming.org/Perft_Results) is the stated source of the positions
  and counts in `tests/perft.epd`. In particular, credit **Peter McKenzie** for Kiwipete and
  **Steven Edwards** for the results/corrections credited to him for positions 5 and 6. The first
  six entries of `BenchFens` in `src/uci.cpp` use the start position and five standard test positions.
  This is a reused
  community test corpus, not a ChessSI-created chess benchmark. The remaining eight bench positions
  have no individual source recorded; this review does not invent one.

## Methods and implementation references

These credits describe established methods or documented influences. They do not, by themselves,
establish whether particular lines were copied. Where code was copied or adapted, its exact source,
revision, authors, and applicable notices must also be recorded.

| Contribution | Credit and evidence in ChessSI |
| --- | --- |
| NNUE evaluation | **Yu Nasu** introduced NNUE for shogi; **Hisayori Noda (nodchip)** brought it to chess. **Motohiro Isozaki / YaneuraOu** and the **Stockfish developers and contributors** developed and shared the surrounding techniques. See the [Stockfish NNUE documentation](https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md). ChessSI uses the NNUE family in `src/nnue.*` and `nnue/train.py`, with its own trained weights. |
| NNUE architecture, training and optimization references | The **nnue-pytorch** and **bullet** contributors, and **Cosmo / Viridithas**, whose [NNUE notes](https://cosmo.tardis.ac/files/2024-06-01-nnue.html) are cited in the project research. See [nnue-pytorch](https://github.com/official-stockfish/nnue-pytorch) and [bullet](https://github.com/jw1912/bullet). SCReLU, quantization, SIMD inference and training from search scores are established techniques. These projects are references, not the source of ChessSI's network files. |
| Pawn and non-pawn correction history | **Caissa, Alexandria, and Stockfish developers/contributors**. `src/search.cpp` explicitly names these precedents. See [Caissa](https://github.com/Witek902/Caissa), [Alexandria](https://github.com/PGG106/Alexandria), and [Stockfish](https://github.com/official-stockfish/Stockfish). The log records the tested ChessSI variants. |
| Improving flag in reverse futility pruning; capped linear history bonus | **Stockfish developers/contributors**; `src/search.cpp` identifies Stockfish and Stockfish 15 respectively. These are applications of known search techniques. |
| Best-move stability time management and search-development references | **Morgan Houppin and Stash contributors**. `src/search.cpp` credits Stash for the soft time limit; `docs/IDEAS.md` also uses its documented search experiments as references. See [Stash](https://github.com/mhouppin/stash-bot). |
| SPSA tuning | **James C. Spall** for SPSA; **Joona Kiiski** for early chess-engine adaptation; the **Stockfish/fishtest contributors** for the update rules and schedules explicitly followed in `gpu/spsa.py`. See [Kiiski's tuner and Spall reference](https://github.com/zamar/spsa) and [fishtest](https://github.com/official-stockfish/fishtest). Running tuning games on ChessSI's GPU port does not make SPSA a new algorithm. |
| Auxiliary training heads | **David J. Wu / KataGo contributors** and the **Leela Chess Zero contributors** supply relevant precedents. See [KataGo methods](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md) and [Lc0 training](https://github.com/LeelaChessZero/lczero-training). ChessSI's log records successful auxiliary-value experiments and later ablations; those establish usefulness here, not invention of auxiliary learning. |
| Standard engine foundations | Alpha-beta/PVS, iterative deepening, quiescence, aspiration windows, transposition tables, Zobrist hashing, magic bitboards, history/killer ordering, pruning, extensions and Lazy SMP come from the computer-chess community. The [Chess Programming Wiki](https://chessprogramming.org/) and [TalkChess](https://talkchess.com/) preserve much of that history. ChessSI does not claim to have originated these methods. |
| Random-number generation | `src/bitboard.cpp` and `src/position.cpp` use the standard xorshift64* construction, not a new ChessSI PRNG. Credit **George Marsaglia** for xorshift and **Sebastiano Vigna** for the [xorshift* study and parameter analysis](https://arxiv.org/abs/1402.6246). Magic and Zobrist keys are generated locally; that does not establish independent provenance of the code that generates them. |

## Books, testing, tools and presentation

| Resource | Role and credit |
| --- | --- |
| [fastchess](https://github.com/Disservin/fastchess) | Match runner and SPRT tooling used by the shell scripts. Credit **Disservin, Szil, PGG106 and all contributors**. Separately installed software with its own license. |
| [Stockfish opening books](https://github.com/official-stockfish/books) | Distribution source for `UHO_Lichess_4852_v1.epd` and `8moves_v3.pgn` downloaded by setup. Credit the book contributors, curators and underlying game providers/players. **Stefan Pohl's [UHO work](https://www.sp-cc.de/uho_2024.htm)** is a methodological precedent; the exact contributor/permission chain for these two downloaded files still needs recording. Distribution by Stockfish is not proof of sole authorship. |
| [CCRL](https://computerchess.org.uk/ccrl/404/) | Volunteer testers supply the published opponent ratings used as anchors in local gauntlets. ChessSI's estimates are not ratings issued by CCRL and imply no endorsement. |
| Gauntlet opponents | Credit the developers and contributors of **Stash, Stockfish, Viridithas, Koivisto, Stormphrax and Halogen** for the engines used in the recorded tests. Opponent versions and conditions are in [Measurements](docs/IDEAS.md#measurements). Opponent evaluations are not permitted training labels. |
| [OpenBench](https://github.com/AndyGrant/OpenBench) | **Andrew Grant and contributors**; documented integration target and testing reference. This credit does not assert a deployed ChessSI OpenBench service. |
| [PyTorch](https://pytorch.org/), [NumPy](https://numpy.org/), [CuPy](https://cupy.dev/), [NVIDIA CUDA/NVRTC](https://developer.nvidia.com/cuda-toolkit) | Training, numerical work and GPU compilation/runtime used by the Python/CUDA tools. Credit their authors, maintainers and contributors; each keeps its own terms. They are not runtime requirements for the standalone CPU UCI executable. |
| [python-chess](https://github.com/niklasf/python-chess) | **Niklas Fiekas and contributors**; imported by `nnue/extract_pgn.py` for PGN processing. The upstream package is GPL-3.0-or-later. This is a tooling dependency, not code in the C++ engine; a redistributed tooling bundle needs its own dependency/license review. |
| [IBM Plex](https://github.com/IBM/plex) and [Source Serif](https://github.com/adobe-fonts/source-serif) | **IBM** and **Adobe**, with their font contributors. `docs/index.html` requests IBM Plex Mono and Source Serif 4 through Google Fonts; font files are not vendored in this snapshot. |
| Build and development tools | The **GCC, Clang/LLVM, GNU Make, Python, Git, Linux and WSL** communities provide the documented build/development environment. Tool use is distinct from authorship of the chess methods. |

## Research references and project contributors

The reports under [docs/research](docs/research/) credit additional engines and papers per proposal,
including ideas that failed or were never implemented. Examples include **Reckless, PlentyChess,
Stormphrax, Viridithas, YaneuraOu, Lc0 and KataGo**. Preserve those source links and author names when
promoting a proposal into the implementation. A research citation does not mean its code or weights
are included in ChessSI. The existing GPU prior-art search also names **Zeta, Tinsmith and ChessGPU**;
GPU chess search itself is not a ChessSI invention.

**Guadalupe Higuera** owns and directs the project, supplies the hardware, and makes project-policy
decisions. The experiment log and Git history identify the AI systems involved in proposing,
implementing, testing and reviewing changes, including **Claude Code / Claude Opus 5.5**, **GPT-6
(Codex / Astra)** and **Grok 4.7 via Cursor** as recorded at the time. Those labels describe work on
ChessSI, not ownership or invention of the upstream techniques. Human contributors retain credit for
their work. No listed person, project, testing group or AI provider is being represented as endorsing ChessSI.

## License and corrections

The repository's project license is [MIT](LICENSE). That notice does not relicense third-party
material or separately installed dependencies. In particular, the PeSTO/wiki reuse terms and exact
source provenance still need the follow-up recorded in [ATTRIBUTION_REVIEW.md](docs/ATTRIBUTION_REVIEW.md).
Giving credit alone does not resolve a license mismatch.

If a credit is missing or inaccurate, please [open an issue](https://github.com/LupeHiguera/ChessSI/issues)
with the affected file, source and suggested correction. Keep corrections dated and preserve the
historical experiments rather than silently changing their results.
