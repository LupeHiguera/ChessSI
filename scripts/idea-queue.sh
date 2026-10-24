#!/usr/bin/env bash
# Run scripts/run-idea.sh for candidate branches one after another, each in its own worktree, so a
# worker can work through a queue unattended.
#
#   scripts/idea-queue.sh <queue-file>
#
# The queue file has one "<branch> [base-ref]" per line (base defaults to origin/main; for a stacked
# candidate, name the branch below it, e.g. origin/claude/tt-replacement); blank lines and lines
# starting with # are skipped. The file is read once at the start, so editing it later changes
# nothing. Before each idea the script fetches origin, so origin/main is whatever main is then. Each
# branch is tested in ../queue-<name>, which is removed afterwards; its logs and games are copied to
# engines/<name>-pre.log, engines/<name>-sprt.log and engines/<name>.pgn, and one summary line per
# idea goes to engines/queue.log. CPUS, CONCURRENCY, FULL and the other run-idea.sh and sprt.sh
# settings pass through.
set -uo pipefail
cd "$(dirname "$0")/.."
queue=${1:?usage: scripts/idea-queue.sh <queue-file>}
[ -f "$queue" ] || { echo "no queue file: $queue" >&2; exit 1; }
mapfile -t lines < <(grep -vE '^[[:space:]]*(#|$)' "$queue")
mkdir -p engines
repo=$PWD

log() { echo "$(date '+%Y-%m-%d %H:%M') $1 vs $2: $3" | tee -a engines/queue.log; }

for line in "${lines[@]}"; do
    read -r branch base _ <<< "$line"
    base=${base:-origin/main}
    name=${branch//\//-}
    dir=$repo/../queue-$name

    git fetch -q origin < /dev/null || { log "$branch" "$base" "fetch failed"; continue; }
    git worktree remove --force "$dir" 2>/dev/null
    git worktree add -q --detach "$dir" "origin/$branch" < /dev/null || { log "$branch" "$base" "checkout failed"; continue; }
    [ -d books ] && ln -s "$repo/books" "$dir/books" # the opening book is shared and read-only

    log "$branch" "$base" "started at $(git -C "$dir" log -1 --format='%h %s')"
    (cd "$dir" && scripts/run-idea.sh "$name" "$base") < /dev/null > "engines/queue-$name.log" 2>&1
    for f in "$name-pre.log" "$name-sprt.log"; do
        [ -f "$dir/engines/$f" ] && cp "$dir/engines/$f" engines/
    done
    [ -f "$dir/engines/sprt.pgn" ] && cp "$dir/engines/sprt.pgn" "engines/$name.pgn"
    verdict=$(grep -E 'BUILD FAILED|GATED|DID NOT RUN' "engines/queue-$name.log" | head -1)
    result=$(grep -E 'Elo:|H0 was|H1 was' "engines/queue-$name.log" | tail -2 | tr -s ' \n' ' ')
    log "$branch" "$base" "${verdict:-done} $result"
    git worktree remove --force "$dir"
done
