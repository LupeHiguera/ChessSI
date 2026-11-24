# PC2 net26 validation, 2026-11-04
Owner asked Codex to put idle PC2 cores to work. Claude Code proposed/trained net26; GPT-6 (Codex) operates these CPU tests. Source is main 014dd979, fetched immediately before launch. Same validated binary on both sides.
- Net26 vs accepted default net22: PC2 P-cores 0-7, 8 concurrent.
- Net26 vs unmerged predecessor net25: PC2 E-cores 8-13, 6 concurrent.
- Each: Threads 1, Hash 16, 10+0.1, SPRT [0,5], alpha/beta .05, UHO paired openings, standard resign/draw adjudication, 15,000-game cap.
- QS evasions stays on PC2 E-cores 14-19. These lanes borrow otherwise idle cores at the owner's request.
- No Elo result yet. These two comparisons are separate and their statistics must not be pooled.
- make test: 35 perft +17 RFP, zero failed. Main bench 50868. EvalFile load confirmed; net25 bench 55715; net26 bench 47010.
- Net26: gens10-13 own self-play, 1,771,974,804 training rows; 16 epochs, h1024. Training script pipeline8.sh and full training/screen logs preserved in /home/pc2/jobs-astra-net26-20261104. SHA256SUMS records binary and network identities.
- Source/branch: /home/pc2/lanes/astra-net26-20261104, astra/pc2-net26-20261104.
- Logs/config/PGN: runs/v22 and runs/v25 inside that worktree.
- Own pause controller: /home/pc2/jobs-astra-net26-20261104/lanepause.sh, list /home/pc2/peak-astra-net26-20261104/mine.txt. Stops at 16:00, resumes after 19:00 weekdays Arizona using saved fastchess config.
- Detached result monitor records terminal raw evidence in this folder and updates this worktree's IDEAS/network log. It does not merge, commit or promote a network automatically.
- Original Claude source and other job controllers are untouched.