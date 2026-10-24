#!/usr/bin/env bash
# Set up a fresh Ubuntu-based Linux machine (such as Pop!_OS) as a ChessSI test and datagen worker.
# Run it from a clone of the repo; it is safe to run again.
#
#   scripts/setup-worker.sh
#
# Installs build tools, builds fastchess into ~/.local/bin, downloads the two opening books into
# books/, builds the Stash opponents for gauntlets into ~/gauntlet, and checks the engine's build.
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=$(nproc)

sudo apt-get update -qq
sudo apt-get install -y -qq build-essential git curl unzip rsync python3 python3-venv

# fastchess, built from source (a release binary also works; see docs/SETUP.md)
mkdir -p ~/.local/bin ~/src
if ! command -v fastchess >/dev/null && [ ! -x ~/.local/bin/fastchess ]; then
    [ -d ~/src/fastchess ] || git clone -q https://github.com/Disservin/fastchess.git ~/src/fastchess
    make -s -C ~/src/fastchess -j"$jobs"
    cp ~/src/fastchess/fastchess ~/.local/bin/
fi
export PATH="$HOME/.local/bin:$PATH"
grep -q '.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Opening books: UHO for SPRTs, 8moves_v3 for gauntlets
mkdir -p books
for f in UHO_Lichess_4852_v1.epd 8moves_v3.pgn; do
    if [ ! -f "books/$f" ]; then
        curl -sSL -o "books/$f.zip" "https://github.com/official-stockfish/books/raw/master/$f.zip"
        unzip -q -o "books/$f.zip" -d books && rm "books/$f.zip"
    fi
done

# Stash opponents with their CCRL Blitz ratings (the pool used for the 2026-10-23 gauntlets)
mkdir -p ~/gauntlet/bin ~/gauntlet/top2
[ -d ~/gauntlet/stash-bot ] || git clone -q https://github.com/mhouppin/stash-bot.git ~/gauntlet/stash-bot
: > ~/gauntlet/top2/ratings.txt
for e in "27.0 3049" "30.0 3153" "31.0 3208" "33.0 3273" "34.0 3315" "36.0 3375"; do
    set -- $e
    if [ ! -x ~/gauntlet/bin/stash-$1 ]; then
        git -C ~/gauntlet/stash-bot checkout -q -f "v$1" && git -C ~/gauntlet/stash-bot clean -qfdx
        make -s -C ~/gauntlet/stash-bot/src -j"$jobs" >/dev/null
        cp "$(find ~/gauntlet/stash-bot/src -maxdepth 2 -type f -executable -name 'stash*' | head -1)" ~/gauntlet/bin/stash-$1
    fi
    ln -sf ~/gauntlet/bin/stash-$1 ~/gauntlet/top2/stash-$1
    echo "stash-$1 $2" >> ~/gauntlet/top2/ratings.txt
done

# The engine itself: perft must pass, and the bench must match the one in README.md
make -s -j"$jobs"
make test | tail -1
echo "bench: $(./chesssi bench | tail -1 | cut -d' ' -f1) (README: $(grep -o 'Bench:\*\* `[0-9]*`' README.md | grep -o '[0-9]*'))"
echo "fastchess: $(command -v fastchess); books: $(ls books | tr '\n' ' '); Stash pool: $(wc -l < ~/gauntlet/top2/ratings.txt) engines"
