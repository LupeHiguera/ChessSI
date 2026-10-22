#!/usr/bin/env bash
# Quick pre-screen before a full SPRT: a short, loose SPRT at a very fast time control.
#
#   scripts/prescreen.sh [base-ref]     same arguments and settings as sprt.sh
#
# Verdicts: "H0 was accepted" means drop the idea; "H1 was accepted" or no verdict within the game
# cap means run the full SPRT. A methodology experiment: until enough ideas have both a pre-screen and
# a full SPRT in docs/IDEAS.md to show they agree, always run the full SPRT as well.
set -euo pipefail
export TC=${TC:-2+0.02}
export ALPHA=${ALPHA:-0.2}
export BETA=${BETA:-0.2}
export ROUNDS=${ROUNDS:-300}
exec "$(dirname "$0")/sprt.sh" "$@"
