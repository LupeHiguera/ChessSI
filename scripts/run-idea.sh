#!/usr/bin/env bash
# One idea through the loop in AGENTS.md: perft, bench, a pre-screen, then the full SPRT.
#
#   scripts/run-idea.sh <name> [base-ref]      logs: engines/<name>-pre.log, engines/<name>-sprt.log
#
# The pre-screen gates the SPRT: if it rejects the idea, or runs out of games while scoring
# negative, the full SPRT is skipped. FULL=1 runs it anyway. CPUS, CONCURRENCY and the other sprt.sh
# settings apply to both runs. To test several ideas at once, give each its own worktree.
set -uo pipefail
cd "$(dirname "$0")/.."
name=${1:?usage: scripts/run-idea.sh <name> [base-ref]}
base=${2:-HEAD}
pin() { if [ -n "${CPUS:-}" ]; then taskset -c "$CPUS" "$@"; else "$@"; fi; }
mkdir -p engines

pin make -s >/dev/null 2>&1 || { echo "BUILD FAILED"; exit 1; }
echo "perft: $(pin make test 2>&1 | grep -E 'passed|failed' | tail -1)"
echo "bench: $(pin ./chesssi bench | tail -1)"

scripts/prescreen.sh "$base" > "engines/$name-pre.log" 2>&1
echo "pre-screen:"; grep -E 'Elo:|Games:|LLR:|H0 was|H1 was' "engines/$name-pre.log" | tail -4
grep -q "Finished match" "engines/$name-pre.log" || { echo "PRE-SCREEN DID NOT RUN:"; tail -3 "engines/$name-pre.log"; exit 1; }

pre_elo=$(grep 'Elo:' "engines/$name-pre.log" | tail -1 | awk '{print $2}')
if [ "${FULL:-0}" != 1 ] && { grep -q "H0 was accepted" "engines/$name-pre.log" || awk -v e="$pre_elo" 'BEGIN{exit !(e<0)}'; }; then
    echo "GATED: pre-screen negative ($pre_elo), full SPRT skipped"; exit 0
fi
scripts/sprt.sh "$base" > "engines/$name-sprt.log" 2>&1
echo "sprt:"; grep -E 'Elo:|Games:|LLR:|H0 was|H1 was' "engines/$name-sprt.log" | tail -4
echo "problems: $(cat "engines/$name-pre.log" "engines/$name-sprt.log" | grep -ciE 'loses on time|illegal|crash|disconnect')"
