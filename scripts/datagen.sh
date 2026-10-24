#!/usr/bin/env bash
# Self-play training data: one `chesssi datagen` process per core, from a committed ref.
#
#   scripts/datagen.sh <generation> <cores>      e.g. scripts/datagen.sh 5 "0 1 2 3"
#   scripts/datagen.sh stop                       stop every datagen process
#
# Builds the ref (default network compiled in) into $DATA/bin/dg<generation>-chesssi and appends
# positions to $DATA/dg<generation>/dg<generation>-<seed>.txt, one file per process. Seeds come from
# the clock, so a restarted generation never replays the same games. Records the source commit,
# network and bench in $DATA/dg<generation>/SOURCE.
#
# Settings (environment variables):
#   REF=HEAD        commit to build
#   DATA=path       data directory (default: ~/nnue/data)
#   NODES=5000      nodes per move
#   RANDOM_PLIES=8  random opening plies before the recorded game
set -euo pipefail
cd "$(dirname "$0")/.."
DATA=${DATA:-$HOME/nnue/data}

if [ "${1:-}" = stop ]; then
    pkill -f 'chesssi datagen ' && echo "stopped datagen" || echo "no datagen running"
    exit 0
fi
gen=${1:?usage: scripts/datagen.sh <generation> <cores> | stop}
cores=${2:?usage: scripts/datagen.sh <generation> <cores> | stop}
REF=${REF:-HEAD} NODES=${NODES:-5000} RANDOM_PLIES=${RANDOM_PLIES:-8}

out=$DATA/dg$gen src=$DATA/bin/dg$gen-src bin=$DATA/bin/dg$gen-chesssi
mkdir -p "$out" "$DATA/bin"
rm -rf "$src"; mkdir -p "$src"
git archive "$REF" | tar -x -C "$src"
taskset -c "$(echo $cores | tr ' ' ',')" make -s -C "$src" EXE="$bin"
echo "built from $(git rev-parse --short "$REF"), $(grep '^EVALFILE' Makefile), bench $("$bin" bench | tail -1 | cut -d' ' -f1)" \
    >> "$out/SOURCE"
base=$(( $(date +%s) % 100000000 * 100 ))
for c in $cores; do
    seed=$((base + c))
    nohup taskset -c "$c" "$bin" datagen "$out/dg$gen-$seed.txt" 1000000 "$seed" "$NODES" "$RANDOM_PLIES" \
        > "$out/dg$gen-$seed.log" 2>&1 &
done
sleep 1
tail -1 "$out/SOURCE"
echo "$(pgrep -f "dg$gen-chesssi datagen" | wc -l) generation-$gen datagen processes on cores: $cores"
