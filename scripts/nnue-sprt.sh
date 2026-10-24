#!/usr/bin/env bash
# SPRT one network against another, both loaded with EvalFile into the same binary.
#
#   scripts/nnue-sprt.sh <new.nnue> <base.nnue>
#
# The binary is built from REF (default HEAD) into engines/<NAME>-bin, so the working tree can hold
# other changes. Output goes to stdout (redirect it to a log); games go to engines/<NAME>.pgn.
#
# Settings (environment variables), as in sprt.sh:
#   NAME=nnue-sprt   name for the binary and PGN, so several tests can run at once
#   REF=HEAD         commit to build the binary from
#   TC=10+0.1  ELO0=0 ELO1=5  ALPHA=0.05 BETA=0.05  ROUNDS=100000  CONCURRENCY=N  CPUS=list
#   BOOK=path        EPD opening book (default: books/UHO_Lichess_4852_v1.epd)
#   FASTCHESS=path   fastchess binary (default: fastchess on PATH)
set -euo pipefail
if [ -n "${CPUS:-}" ] && [ -z "${SPRT_PINNED:-}" ]; then
    SPRT_PINNED=1 exec taskset -c "$CPUS" "$0" "$@"
fi
cd "$(dirname "$0")/.."

new=$(realpath "${1:?usage: scripts/nnue-sprt.sh <new.nnue> <base.nnue>}")
base=$(realpath "${2:?usage: scripts/nnue-sprt.sh <new.nnue> <base.nnue>}")
NAME=${NAME:-nnue-sprt} REF=${REF:-HEAD}
TC=${TC:-10+0.1} ELO0=${ELO0:-0} ELO1=${ELO1:-5} ALPHA=${ALPHA:-0.05} BETA=${BETA:-0.05}
ROUNDS=${ROUNDS:-100000}
BOOK=${BOOK:-books/UHO_Lichess_4852_v1.epd}
FASTCHESS=${FASTCHESS:-fastchess}
CORES=$(getconf _NPROCESSORS_ONLN)
CONCURRENCY=${CONCURRENCY:-$(( CORES > 3 ? CORES - 2 : 1 ))}
[ -f "$BOOK" ] || { echo "Opening book not found: $BOOK (see docs/SETUP.md)" >&2; exit 1; }
command -v "$FASTCHESS" >/dev/null || { echo "fastchess not found (see docs/SETUP.md)" >&2; exit 1; }

mkdir -p engines
rm -rf "engines/$NAME-src"; mkdir "engines/$NAME-src"
git archive "$REF" | tar -x -C "engines/$NAME-src"
make -s -C "engines/$NAME-src" EXE="$PWD/engines/$NAME-bin"
n=$(basename "$new" .nnue) b=$(basename "$base" .nnue)
echo "binary from $(git rev-parse --short "$REF"); $n vs $b at $TC, SPRT [$ELO0, $ELO1], $CONCURRENCY games in parallel${CPUS:+ on cores $CPUS}"

"$FASTCHESS" \
    -engine cmd="engines/$NAME-bin" name="$n" option.EvalFile="$new" \
    -engine cmd="engines/$NAME-bin" name="$b" option.EvalFile="$base" \
    -each tc="$TC" option.Hash=16 option.Threads=1 \
    -openings file="$BOOK" format=epd order=random \
    -rounds "$ROUNDS" -games 2 -repeat -recover \
    -resign movecount=3 score=400 twosided=true \
    -draw movenumber=40 movecount=8 score=10 \
    -concurrency "$CONCURRENCY" \
    -sprt elo0="$ELO0" elo1="$ELO1" alpha="$ALPHA" beta="$BETA" \
    -pgnout file="engines/$NAME.pgn"
