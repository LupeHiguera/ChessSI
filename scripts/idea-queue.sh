#!/usr/bin/env bash
# Run a queue of tests one after another, each candidate branch in its own worktree, so a worker can
# work through them unattended.
#
#   scripts/idea-queue.sh <queue-file>
#
# The queue file has one test per line; blank lines and lines starting with # are skipped:
#
#   <branch> [base-ref]                  scripts/run-idea.sh on the branch, rebased onto base-ref
#                                        (default origin/main; for a stacked candidate, name the
#                                        branch below it, e.g. origin/claude/tt-replacement)
#   nnue <name> <new.nnue> <base.nnue>   scripts/nnue-sprt.sh, with the binary built from origin/main
#
# The file is read again before each test, so lines can be added, removed or reordered while the
# queue runs. Each finished or skipped line is appended to engines/queue-done.txt and not run again;
# to repeat a test, delete its line there. A test interrupted by stopping the script isn't listed, so
# it starts again from the beginning when the script is restarted. Before each test the script fetches origin and fixes the base to one
# commit, so a merge to main mid-test can't change what the pre-screen and the SPRT compare against.
# The branch is rebased onto that commit, so it is tested against the latest accepted engine, as
# AGENTS.md asks; a branch that doesn't rebase cleanly is skipped and logged. Each branch is tested in
# ../queue-<name>, which is removed afterwards. Its logs and games are copied to
# engines/<name>-pre.log, engines/<name>-sprt.log and engines/<name>.pgn, and one summary line per
# test goes to engines/queue.log. Create engines/queue.stop to stop after the current test. CPUS,
# CONCURRENCY, FULL and the other run-idea.sh and sprt.sh settings pass through.
set -uo pipefail
cd "$(dirname "$0")/.."
queue=${1:?usage: scripts/idea-queue.sh <queue-file>}
[ -f "$queue" ] || { echo "no queue file: $queue" >&2; exit 1; }
mkdir -p engines
repo=$PWD
done_list=engines/queue-done.txt
touch "$done_list"
rm -f engines/queue.stop

log() { echo "$(date '+%Y-%m-%d %H:%M') $1: $2" | tee -a engines/queue.log; }
finish() { echo "$line" >> "$done_list"; }

# The first line of the queue file that isn't in the done list, or nothing.
next_test() {
    grep -vE '^[[:space:]]*(#|$)' "$queue" | while IFS= read -r line; do
        grep -qxF -- "$line" "$done_list" || { echo "$line"; break; }
    done
}

while [ ! -e engines/queue.stop ] && line=$(next_test) && [ -n "$line" ]; do
    if ! git fetch -q origin < /dev/null; then
        log "$line" "fetch failed, retrying in 5 minutes"; sleep 300; continue
    fi
    read -r first second third fourth _ <<< "$line"

    if [ "$first" = nnue ]; then
        name=$second
        ref=$(git rev-parse --short origin/main)
        log "$name" "started: $third vs $fourth, binary from $ref"
        NAME=$name REF=$ref scripts/nnue-sprt.sh "$third" "$fourth" < /dev/null > "engines/$name.log" 2>&1
        rc=$?
        if [ "$rc" -ne 0 ] || ! grep -q "Finished match" "engines/$name.log"; then
            log "$name" "INFRA FAILURE (exit $rc), left pending; queue stopped"; stopped=1; break
        fi
        log "$name" "done $(grep -E 'Elo:|H0 was|H1 was' "engines/$name.log" | tail -2 | tr -s ' \n' ' ')"
        finish; continue
    fi

    branch=$first base=${second:-origin/main}
    name=${branch//\//-}
    dir=$repo/../queue-$name
    base_sha=$(git rev-parse --verify -q "$base^{commit}") || { log "$branch vs $base" "no such base, skipped"; finish; continue; }
    git worktree remove --force "$dir" 2>/dev/null
    git worktree add -q --detach "$dir" "origin/$branch" < /dev/null || { log "$branch vs $base" "checkout failed, skipped"; finish; continue; }
    if ! git -C "$dir" -c user.name=idea-queue -c user.email=idea-queue@localhost rebase -q "$base_sha" < /dev/null > /dev/null 2>&1; then
        git -C "$dir" rebase --abort 2>/dev/null
        git worktree remove --force "$dir"
        log "$branch vs $base" "doesn't rebase cleanly onto ${base_sha:0:7}, skipped"; finish; continue
    fi
    [ -d books ] && ln -s "$repo/books" "$dir/books" # the opening book is shared and read-only

    log "$branch vs $base" "started: $(git -C "$dir" log -1 --format='%h %s') on ${base_sha:0:7}"
    (cd "$dir" && scripts/run-idea.sh "$name" "$base_sha") < /dev/null > "engines/queue-$name.log" 2>&1
    rc=$?
    for f in "$name-pre.log" "$name-sprt.log"; do
        [ -f "$dir/engines/$f" ] && cp "$dir/engines/$f" engines/
    done
    [ -f "$dir/engines/sprt.pgn" ] && cp "$dir/engines/sprt.pgn" "engines/$name.pgn"
    verdict=$(grep -E 'BUILD FAILED|TEST FAILED|BENCH FAILED|GATED|DID NOT RUN' "engines/queue-$name.log" | head -1)
    result=$(grep -E 'Elo:|H0 was|H1 was' "engines/queue-$name.log" | tail -2 | tr -s ' \n' ' ')
    git worktree remove --force "$dir"
    # Exit 2 (pre-screen or SPRT didn't complete; a failed build, test or bench is exit 1, a verdict) is an infrastructure failure: leave the
    # line pending so no partial or pre-screen result is recorded as a verdict, and stop the queue.
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
        log "$branch vs $base" "INFRA FAILURE (exit $rc): ${verdict:-$(tail -1 "engines/queue-$name.log")}, left pending; queue stopped"
        stopped=1; break
    fi
    log "$branch vs $base" "${verdict:-done} $result"
    finish
done
if [ -e engines/queue.stop ]; then log queue "stopped by engines/queue.stop"; fi
[ "${stopped:-0}" = 1 ] && exit 2
exit 0
