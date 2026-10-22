#!/usr/bin/env bash
# SPRT the working tree against a git ref with fastchess.
#
#   scripts/sprt.sh [base-ref]          base-ref defaults to HEAD
#
# Settings (environment variables):
#   TC=10+0.1        time control; confirm winners with TC=60+0.6
#   ELO0=0 ELO1=5    SPRT bounds; use ELO0=-5 ELO1=0 for simplifications
#   CONCURRENCY=N    games in parallel (default: cores - 2)
#   BOOK=path        EPD opening book (default: books/UHO_Lichess_4852_v1.epd)
#   FASTCHESS=path   fastchess binary (default: fastchess on PATH)
#
# Decided games end early to save CPU: a resign when both engines agree one side is 4+ pawns up for
# 3 moves, a draw from move 40 when both report a score within 0.1 pawns for 8 moves.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_REF=${1:-HEAD}
TC=${TC:-10+0.1}
ELO0=${ELO0:-0}
ELO1=${ELO1:-5}
BOOK=${BOOK:-books/UHO_Lichess_4852_v1.epd}
FASTCHESS=${FASTCHESS:-fastchess}
CORES=$(getconf _NPROCESSORS_ONLN)
CONCURRENCY=${CONCURRENCY:-$(( CORES > 3 ? CORES - 2 : 1 ))}

if [ ! -f "$BOOK" ]; then
    echo "Opening book not found: $BOOK (see docs/SETUP.md)" >&2
    exit 1
fi
command -v "$FASTCHESS" >/dev/null || { echo "fastchess not found (see docs/SETUP.md)" >&2; exit 1; }

mkdir -p engines
rm -rf engines/base-src
mkdir engines/base-src
git archive "$BASE_REF" | tar -x -C engines/base-src

make -s EXE=engines/new
make -s -C engines/base-src EXE="$PWD/engines/base"

echo "new  ($(git rev-parse --short HEAD)+working tree): bench $(engines/new bench | tail -1 | cut -d' ' -f1)"
echo "base ($BASE_REF): bench $(engines/base bench | tail -1 | cut -d' ' -f1)"
echo "SPRT [$ELO0, $ELO1] at $TC, $CONCURRENCY games in parallel"

"$FASTCHESS" \
    -engine cmd=engines/new name=new \
    -engine cmd=engines/base name=base \
    -each tc="$TC" option.Hash=16 option.Threads=1 \
    -openings file="$BOOK" format=epd order=random \
    -rounds 100000 -games 2 -repeat -recover \
    -resign movecount=3 score=400 twosided=true \
    -draw movenumber=40 movecount=8 score=10 \
    -concurrency "$CONCURRENCY" \
    -sprt elo0="$ELO0" elo1="$ELO1" alpha=0.05 beta=0.05 \
    -pgnout file=engines/sprt.pgn
