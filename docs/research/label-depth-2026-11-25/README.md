# Label depth against volume at equal generation compute

Claude Fable 5.2 designed and started this on 2026-11-24 and Claude Opus 5.5 finished it on 2026-11-25.

The question was whether training labels from deeper searches are worth what they cost in data volume. Each
position costs search nodes to label, so at a fixed generation budget a deeper search makes fewer positions. The
strong engines that train on their own data label at 20,000 to 25,000 nodes a move; ChessSI labels at 5,000. No
public test held the generation compute fixed. The closest evidence, Stormphrax's PRs 311 and 314 in 2026, lost
28 Elo at short control when 24,000-node data replaced 5,000-node data, and gained about 25 when the deep data
was used only for a final training stage.

## Setup

Both arms used the same teacher network (net27-h1536), the same search (the GPU port of main `005fc57`, checked
identical to the CPU reference at both node counts on the RTX 5080), the same openings (8 random plies) and the
same position filters. Only the nodes per move differed.

| | Arm A | Arm B |
| --- | --- | --- |
| Nodes a move | 5,000 | 20,000 |
| Positions generated | 421,721,432 (the first lines of generation 17, RTX 5060 Ti) | 105,430,358 (RTX 5080) |
| Search nodes spent | 2.11 × 10^12 | 2.11 × 10^12 |
| Unique training rows | 371,556,289 | 96,887,626 |

Each arm trained a network of 768 hidden units with net28's recipe (aux head, future plies 4, seed 1) and the
trainer from PR #108. Arm A trained 10 epochs. Arm B trained 38 epochs, the same number of position-visits. A
second arm-B network, B10, trained 10 epochs to check whether repeating the smaller set 38 times was what hurt.

## Results

GPU matches at equal nodes, 1,024 game pairs each, UHO openings; same-size network matches on the GPU have
agreed with every CPU SPRT so far. Elo is arm B's network against arm A's, with 95% intervals.

| Arm B network | Training loss | Validation loss (own data) | 20,000 nodes, seed 1 | 20,000 nodes, seed 2 | 100,000 nodes |
| --- | --- | --- | --- | --- | --- |
| B, 38 epochs (equal visits) | 0.00665 | 0.00759 | −83.7 ± 12.0 | −73.0 ± 11.5 | −70.9 ± 10.8 |
| B10, 10 epochs | 0.00705 | 0.00785 | −111.8 ± 12.6 | −101.3 ± 12.0 | −88.0 ± 10.7 |

Arm A's network: training loss 0.00801, validation loss 0.00824 on its own data. The validation sets differ
between arms, so the losses do not compare across them.

## Reading

At this scale, volume wins clearly. Four times the positions at a quarter of the search effort each made a
network about 70 to 85 Elo stronger. The deeper set did not lose because it was repeated: with fewer passes
(B10) it lost by more. The gap narrows somewhat from 20,000 to 100,000 nodes a move, so deeper labels may matter
more for longer searches, but not enough to close it here.

Limits: one teacher, one network size (768), and data sets of 100 to 400 million positions, far below the
billions the main networks train on. Deep labels may still pay as a final training stage on top of a large
5,000-node set, as Stormphrax found; that is untested here. The matches ran at fixed nodes on the GPU; no CPU
SPRT was run, because the gap is many times the error of either method.

## Files

`~/claude-scratch/depthexp/` and `~/claude-scratch/night5080/` on PC1 (logs, match output), the data in
`~/nnue/data/dg17n20/` and the first 22 files of `~/nnue/data/dg17/`, the shards `~/nnue/shards/g171s` and
`g172s`, and the networks `~/nnue/nets/depthA-h768.nnue`, `depthB-h768.nnue` and `depthB10-h768.nnue`. The
scripts are `claude-work/2026-11-25/depthexp2.sh` and `night5080.sh` on the same machine.
