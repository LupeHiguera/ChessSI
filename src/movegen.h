#pragma once

#include "position.h"

struct MoveList {
    Move moves[256];
    int size = 0;

    void add(Move m) { moves[size++] = m; }
    Move* begin() { return moves; }
    Move* end() { return moves + size; }
};

enum GenType {
    ALL_MOVES,
    NOISY_MOVES, // captures and queen promotions, for quiescence search
};

// Generates pseudo-legal moves; Position::do_move reports which are legal.
void generate(const Position& pos, MoveList& list, GenType type);

// Returns the legal move matching a UCI string such as "e2e4" or "e7e8q", or MOVE_NONE.
Move parse_uci_move(Position& pos, const std::string& str);
