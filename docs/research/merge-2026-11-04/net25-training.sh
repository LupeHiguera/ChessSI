#!/bin/bash
# The 5080 is Claude's until Wednesday 2026-11-04 night (owner, 2026-11-02 23:50). net25-h1024: net24's data
# (scattered generations 10 and 11, 1.39B positions) and recipe at 1024 hidden units instead of 768, to measure
# capacity on its own. 16 epochs, one per process via train-offpeak.sh, which waits out 16:00-19:00 on weekdays.
# Log: ~/nnue/shards/pipeline.log ("run 7" lines), ~/nnue/nets/net25-h1024.log.
set -uo pipefail
source ~/nnue/venv/bin/activate
export OMP_NUM_THREADS=1
T=/mnt/c/Users/Lupe/claude-work/wt-stream/nnue S=~/nnue/shards N=~/nnue/nets L=$S/pipeline.log
log() { echo "$(date '+%F %T') run 7: $*" >> $L; }
cd $T
log "net25-h1024 on scattered generations 10 and 11, 16 epochs, off-peak"
CUDA_VISIBLE_DEVICES=0 taskset -c 5 bash /mnt/c/Users/Lupe/claude-work/2026-11-01/train-offpeak.sh $N/net25-h1024.log 16 2400 \
    --shards $S/g10s --shards $S/g11s $N/net25-h1024.nnue --hidden 1024 --seed 1 --aux-weight 1.0 --future-plies 4
log "net25-h1024 exit $?: $(grep '^epoch' $N/net25-h1024.log | tail -1)"
