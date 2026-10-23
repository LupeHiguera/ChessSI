"""Fit one rating for ChessSI from a gauntlet PGN and the opponents' CCRL ratings.

    python3 scripts/gauntlet_rating.py games.pgn ratings.txt

ratings.txt has one "<engine name> <rating>" per line. Time forfeits are left out: they measure an
engine's clock handling under WSL, not its play. The error bar is statistical only; it does not
cover the time-control difference from CCRL or drift in the anchors' ratings.
"""

import math
import re
import sys
from collections import defaultdict


def main():
    pgn, ratings_file = sys.argv[1], sys.argv[2]
    ratings = {}
    for line in open(ratings_file):
        if line.split():
            name, rating = line.split()
            ratings[name] = float(rating)

    tally = defaultdict(lambda: [0, 0, 0])  # wins, draws, losses for ChessSI
    forfeits = 0
    for game in re.split(r"\n(?=\[Event )", open(pgn).read()):
        tags = dict(re.findall(r'\[(\w+) "([^"]*)"\]', game))
        if "Result" not in tags or tags["Result"] == "*":
            continue
        if tags.get("Termination") == "time forfeit":
            forfeits += 1
            continue
        white_is_us = tags["White"].startswith("ChessSI")
        opponent = tags["Black"] if white_is_us else tags["White"]
        if tags["Result"] == "1/2-1/2":
            tally[opponent][1] += 1
        elif (tags["Result"] == "1-0") == white_is_us:
            tally[opponent][0] += 1
        else:
            tally[opponent][2] += 1

    def log_likelihood(r):
        total = 0.0
        for opponent, (w, d, l) in tally.items():
            e = 1 / (1 + 10 ** ((ratings[opponent] - r) / 400))
            total += (w + d / 2) * math.log(e) + (l + d / 2) * math.log(1 - e)
        return total

    best = max((x / 2 for x in range(0, 9000)), key=log_likelihood)
    curvature = -(log_likelihood(best + 1) - 2 * log_likelihood(best) + log_likelihood(best - 1))
    margin = 1.96 / math.sqrt(curvature)

    print(f"{'Opponent':12} {'CCRL':>5} {'W':>4} {'D':>4} {'L':>4} {'Score':>6} {'Perf':>5}")
    for opponent in sorted(tally, key=lambda o: ratings[o]):
        w, d, l = tally[opponent]
        score = (w + d / 2) / (w + d + l)
        perf = ratings[opponent] - 400 * math.log10(1 / score - 1) if 0 < score < 1 else float("nan")
        print(f"{opponent:12} {ratings[opponent]:5.0f} {w:4} {d:4} {l:4} {score:6.3f} {perf:5.0f}")
    print(f"Rating: {best:.0f} +/- {margin:.0f} (95%), {forfeits} time forfeits excluded")


if __name__ == "__main__":
    main()
