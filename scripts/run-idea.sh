#!/usr/bin/env bash
# One idea through the loop in AGENTS.md: perft, bench, a pre-screen, then the full SPRT.
#
#   scripts/run-idea.sh <name> [base-ref]      logs: engines/<name>-pre.log, engines/<name>-sprt.log
#
# The pre-screen gates the SPRT: if it rejects the idea, or runs out of games with its whole 95%
# interval below 0, the full SPRT is skipped (a negative estimate alone is not enough: at 600 games a
# true +5 idea scores below 0 about a third of the time). FULL=1 runs it anyway. CPUS, CONCURRENCY and the other sprt.sh
# settings apply to both runs. SPRT_ROUNDS caps the full SPRT at that many game pairs, after which it
# stops undecided (ROUNDS would also resize the pre-screen). To test several ideas at once, give each
# its own worktree.
set -uo pipefail
cd "$(dirname "$0")/.."
name=${1:?usage: scripts/run-idea.sh <name> [base-ref]}
base=${2:-HEAD}
pin() { if [ -n "${CPUS:-}" ]; then taskset -c "$CPUS" "$@"; else "$@"; fi; }
mkdir -p engines

pin make -s >/dev/null 2>&1 || { echo "BUILD FAILED"; exit 1; }
# Exit codes: 0 = finished or gated, 1 = build, test or bench failed (a verdict on the branch: the
# queue marks it done and goes on), 2 = infrastructure failure (pre-screen or SPRT didn't complete).
# The queue treats exit 2 as "not done" and stops.
test_out=$(pin make test 2>&1); test_rc=$?
echo "perft: $(grep -E 'passed|failed' <<< "$test_out" | tail -1)"
[ "$test_rc" -eq 0 ] || { echo "TEST FAILED (exit $test_rc)"; exit 1; }
bench_out=$(pin ./chesssi bench 2>&1); bench_rc=$?
echo "bench: $(tail -1 <<< "$bench_out")"
[ "$bench_rc" -eq 0 ] || { echo "BENCH FAILED (exit $bench_rc)"; exit 1; }

rm -f "engines/$name-pre.log" "engines/$name-sprt.log"
scripts/prescreen.sh "$base" > "engines/$name-pre.log" 2>&1
pre_rc=$?
echo "pre-screen:"; grep -E 'Elo:|Games:|LLR:|H0 was|H1 was' "engines/$name-pre.log" | tail -4
if [ "$pre_rc" -ne 0 ] || ! grep -q "Finished match" "engines/$name-pre.log"; then
    echo "PRE-SCREEN DID NOT RUN (exit $pre_rc):"; tail -3 "engines/$name-pre.log"; exit 2
fi

read -r pre_elo pre_err <<< "$(grep 'Elo:' "engines/$name-pre.log" | tail -1 | awk '{gsub(",", ""); print $2, $4}')"
if [ "${FULL:-0}" != 1 ] && { grep -q "H0 was accepted" "engines/$name-pre.log" || awk -v e="$pre_elo" -v d="$pre_err" 'BEGIN{exit !(e + d < 0)}'; }; then
    echo "GATED: pre-screen rejected it ($pre_elo +/- $pre_err), full SPRT skipped"; exit 0
fi
ROUNDS="${SPRT_ROUNDS:-${ROUNDS:-100000}}" scripts/sprt.sh "$base" > "engines/$name-sprt.log" 2>&1
sprt_rc=$?
echo "sprt:"; grep -E 'Elo:|Games:|LLR:|H0 was|H1 was' "engines/$name-sprt.log" | tail -4
if [ "$sprt_rc" -ne 0 ] || ! grep -q "Finished match" "engines/$name-sprt.log"; then
    echo "SPRT DID NOT RUN (exit $sprt_rc):"; tail -3 "engines/$name-sprt.log"; exit 2
fi
echo "problems: $(cat "engines/$name-pre.log" "engines/$name-sprt.log" | grep -ciE 'loses on time|illegal|crash|disconnect')"
