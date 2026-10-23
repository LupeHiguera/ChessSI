#!/usr/bin/env bash
# Rate HEAD against engines with known CCRL Blitz ratings, then fit one rating to the results.
#
#   scripts/gauntlet.sh
#
# Settings (environment variables):
#   OPPONENTS=dir    opponent binaries plus ratings.txt, one "<binary> <CCRL Blitz rating>" per line
#                    (default: ~/gauntlet/bin)
#   TC=10+0.1        time control
#   ROUNDS=200       game pairs per opponent
#   CONCURRENCY=N    games in parallel (default: cores - 2)
#   CPUS=list        run everything on these cores only, e.g. CPUS=0-13 (see "Sharing the PC" in AGENTS.md)
#   BOOK=path        PGN opening book (default: books/8moves_v3.pgn, balanced openings; the UHO book
#                    used for SPRTs gives one side an edge, which stretches rating gaps)
#   FASTCHESS=path   fastchess binary (default: fastchess on PATH)
#
# The ChessSI binary is copied before the run, so later edits cannot change it. Results go to
# engines/gauntlet-<commit>-<tc>/. Stash (github.com/mhouppin/stash-bot) builds from its version tags
# and spans 1300-3400 CCRL, which makes it a convenient ladder.
set -euo pipefail
if [ -n "${CPUS:-}" ] && [ -z "${GAUNTLET_PINNED:-}" ]; then
    GAUNTLET_PINNED=1 exec taskset -c "$CPUS" "$0" "$@"
fi
cd "$(dirname "$0")/.."

OPPONENTS=${OPPONENTS:-$HOME/gauntlet/bin}
TC=${TC:-10+0.1}
ROUNDS=${ROUNDS:-200}
BOOK=${BOOK:-books/8moves_v3.pgn}
FASTCHESS=${FASTCHESS:-fastchess}
CORES=$(getconf _NPROCESSORS_ONLN)
CONCURRENCY=${CONCURRENCY:-$(( CORES > 3 ? CORES - 2 : 1 ))}

[ -f "$OPPONENTS/ratings.txt" ] || { echo "Missing $OPPONENTS/ratings.txt" >&2; exit 1; }
[ -f "$BOOK" ] || { echo "Opening book not found: $BOOK (see docs/SETUP.md)" >&2; exit 1; }
command -v "$FASTCHESS" >/dev/null || { echo "fastchess not found (see docs/SETUP.md)" >&2; exit 1; }
git diff --quiet HEAD -- src || { echo "src/ has uncommitted changes; a gauntlet rates a commit" >&2; exit 1; }

rev=$(git rev-parse --short HEAD)
out=engines/gauntlet-$rev-${TC/+/_}
mkdir -p "$out"
make -s
cp chesssi "$out/chesssi-$rev"
echo "ChessSI $rev, bench $("$out/chesssi-$rev" bench | tail -1 | cut -d' ' -f1), TC $TC, $ROUNDS pairs per opponent"

args=(-engine cmd="$out/chesssi-$rev" name="ChessSI-$rev")
while read -r bin rating; do
    [ -n "$bin" ] && args+=(-engine cmd="$OPPONENTS/$bin" name="$bin")
done < "$OPPONENTS/ratings.txt"

"$FASTCHESS" -tournament gauntlet -seeds 1 "${args[@]}" \
    -each tc="$TC" option.Hash=16 option.Threads=1 \
    -openings file="$BOOK" format=pgn order=random \
    -rounds "$ROUNDS" -games 2 -repeat -recover \
    -resign movecount=3 score=600 twosided=true \
    -draw movenumber=40 movecount=8 score=10 \
    -concurrency "$CONCURRENCY" \
    -pgnout file="$out/games.pgn" > "$out/fastchess.log" 2>&1

python3 scripts/gauntlet_rating.py "$out/games.pgn" "$OPPONENTS/ratings.txt" | tee "$out/rating.txt"
