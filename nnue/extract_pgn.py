"""Turn fastchess PGNs from our own games into NNUE training positions.

    python extract_pgn.py [--engine NAME] <out.txt> <games.pgn> [more.pgn ...]

Every move comment carries the mover's search score of the position before that move ("+0.53/8
0.858s": pawns from the mover's side, then depth and time). Keeps quiet positions: not in check, the
move played is not a capture or promotion, and the score is not a mate. Writes the same format as
`chesssi datagen`: "<fen> | <cp> | <result>", score and result from White's side.

With --engine, keeps only positions where the engine whose PGN name starts with NAME is to move:
for games against other engines, so only ChessSI's own scores are used (see the rules in AGENTS.md).
"""
import argparse
import re

import chess
import chess.pgn

SCORE = re.compile(r"^\s*([+-]?\d+\.\d+)/\d+")
RESULTS = {"1-0": "1.0", "0-1": "0.0", "1/2-1/2": "0.5"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", help="keep only positions where this engine (PGN name prefix) is to move")
    ap.add_argument("out")
    ap.add_argument("pgns", nargs="+")
    args = ap.parse_args()
    games = kept = 0
    with open(args.out, "w") as out:
        for path in args.pgns:
            with open(path, encoding="utf-8") as f:
                while (game := chess.pgn.read_game(f)) is not None:
                    result = RESULTS.get(game.headers.get("Result"))
                    if result is None:
                        continue
                    games += 1
                    ours = {color for color, tag in ((chess.WHITE, "White"), (chess.BLACK, "Black"))
                            if args.engine is None or game.headers.get(tag, "").startswith(args.engine)}
                    board = game.board()
                    for node in game.mainline():
                        move = node.move
                        m = SCORE.match(node.comment or "")
                        if (m and board.turn in ours and not board.is_check() and not board.is_capture(move)
                                and move.promotion is None):
                            cp = round(float(m.group(1)) * 100)
                            if board.turn == chess.BLACK:
                                cp = -cp
                            out.write(f"{board.fen()} | {cp} | {result}\n")
                            kept += 1
                        board.push(move)
                    if games % 2000 == 0:
                        print(f"games {games} positions {kept}", flush=True)
    print(f"done: games {games} positions {kept}")


if __name__ == "__main__":
    main()
