"""Turn fastchess PGNs from our own tests into NNUE training positions.

    python extract_pgn.py <out.txt> <games.pgn> [more.pgn ...]

Every move comment carries ChessSI's search score of the position before that move ("+0.53/8
0.858s": pawns from the mover's side, then depth and time). Keeps quiet positions: not in check, the
move played is not a capture or promotion, and the score is not a mate. Writes the same format as
`chesssi datagen`: "<fen> | <cp> | <result>", score and result from White's side.
"""
import re
import sys

import chess
import chess.pgn

SCORE = re.compile(r"^\s*([+-]?\d+\.\d+)/\d+")
RESULTS = {"1-0": "1.0", "0-1": "0.0", "1/2-1/2": "0.5"}


def main():
    out_path, pgns = sys.argv[1], sys.argv[2:]
    games = kept = 0
    with open(out_path, "w") as out:
        for path in pgns:
            with open(path, encoding="utf-8") as f:
                while (game := chess.pgn.read_game(f)) is not None:
                    result = RESULTS.get(game.headers.get("Result"))
                    if result is None:
                        continue
                    games += 1
                    board = game.board()
                    for node in game.mainline():
                        move = node.move
                        m = SCORE.match(node.comment or "")
                        if (m and not board.is_check() and not board.is_capture(move)
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
