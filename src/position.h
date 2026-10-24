#pragma once

#include <string>
#include <vector>

#include "bitboard.h"
#include "nnue.h"

inline const std::string StartFEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// Everything do_move changes that undo_move cannot recompute.
struct StateInfo {
    uint64_t key;
    int castling;
    Square ep;
    int rule50;
    Piece captured;
    int pliesFromNull = 0; // repetitions cannot reach back past a null move
};

class Position {
public:
    static void init();

    // Returns false if the FEN cannot be parsed.
    bool set(const std::string& fen);
    std::string fen() const;
    std::string pretty() const;

    Bitboard pieces() const { return byColor[WHITE] | byColor[BLACK]; }
    Bitboard pieces(Color c) const { return byColor[c]; }
    Bitboard pieces(PieceType pt) const { return byType[pt]; }
    Bitboard pieces(Color c, PieceType pt) const { return byColor[c] & byType[pt]; }
    Piece piece_on(Square s) const { return board[s]; }
    Color side_to_move() const { return stm; }
    Square king_square(Color c) const { return lsb(pieces(c, KING)); }
    Square ep_square() const { return states.back().ep; }
    int castling_rights() const { return states.back().castling; }
    int rule50() const { return states.back().rule50; }
    uint64_t key() const { return states.back().key; }

    bool attacked(Square s, Color by) const;
    bool in_check() const { return attacked(king_square(stm), ~stm); }

    // Plays a pseudo-legal move and returns whether it was legal (the mover's
    // king is not left in check). Always pair with undo_move, legal or not.
    bool do_move(Move m);
    void undo_move(Move m);

    // Passes the turn. Only for null-move pruning; never while in check.
    void do_null_move();
    void undo_null_move();

    // Fifty-move rule or any repetition since the last irreversible move.
    bool is_draw() const;

    // The NNUE accumulator for this ply, or nullptr if none matches the loaded network.
    const int16_t* accumulator() const;

private:
    void put_piece(Piece p, Square s);
    void remove_piece(Square s);
    void move_piece(Square from, Square to);
    uint64_t compute_key() const;
    void push_accumulator(const NNUE::Delta& delta);

    // One NNUE accumulator per ply, 2 * accHidden values each, for network accGeneration (0: none).
    // The first accTop values are in use. The buffer only grows, so moves never resize it (a resize
    // would zero-fill each new accumulator before the update overwrites it).
    std::vector<int16_t> accStack;
    size_t accTop = 0;
    int accGeneration = 0;
    int accHidden = 0;

    Bitboard byType[6] = {};
    Bitboard byColor[2] = {};
    Piece board[64];
    Color stm = WHITE;
    int fullmove = 1;
    std::vector<StateInfo> states;
};

std::string square_to_string(Square s);
std::string move_to_uci(Move m);
