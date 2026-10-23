#pragma once

#include <cstdint>
#include <string>

#include "types.h"

class Position;

// NNUE evaluation, trained by nnue/train.py: (768 -> H) x 2 perspectives -> SCReLU -> 1, with
// optionally one set of output weights per range of piece counts. Without a network (none compiled in, none loaded with the EvalFile option) evaluate() uses PeSTO.
//
// An accumulator holds the first layer for both perspectives: [0, H) from White's side, [H, 2H)
// from Black's. Position keeps one per ply and updates it as pieces move.
namespace NNUE {

// Loads a network file; returns false and keeps the current evaluation if it is invalid.
bool load(const std::string& path);
// Loads the network compiled in with `make EVALFILE=...`; false if there is none.
bool load_embedded();
bool has_embedded();
bool loaded();

// Changes with every successful load, so a Position can tell its accumulators are stale.
// 0 means no network.
int generation();
int hidden();

// The pieces a move adds and removes: at most two of each (castling; a capture removes two).
struct Delta {
    int adds = 0, subs = 0;
    Piece addPiece[2], subPiece[2];
    Square addSq[2], subSq[2];
    void add(Piece p, Square s) { addPiece[adds] = p; addSq[adds++] = s; }
    void sub(Piece p, Square s) { subPiece[subs] = p; subSq[subs++] = s; }
};

void refresh(const Position& pos, int16_t* acc);
// acc = prev with the delta applied, in one pass; prev may equal acc.
void apply(const int16_t* prev, int16_t* acc, const Delta& d);
void add(int16_t* acc, Piece p, Square s);
void sub(int16_t* acc, Piece p, Square s);

// Centipawns from the side to move's point of view.
int evaluate(const Position& pos);

} // namespace NNUE
