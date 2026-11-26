#pragma once

#include <cstdint>
#include <string>

#include "types.h"

class Position;

// NNUE evaluation, trained by nnue/train.py: (768 -> H) x 2 perspectives, then one of two tails. SCReLU -> 1 is
// the first: each unit clipped and squared, one output. The pairwise tail multiplies unit j of each perspective's
// first half by unit j of its second half, then runs layers of 16, 32 and 1 neurons, all in integers.
// Without a network (none compiled in, none loaded with the EvalFile option) evaluate() uses PeSTO.
//
// An accumulator holds the first layer for both perspectives: [0, H) from White's side, [H, 2H)
// from Black's. Position keeps one per ply and updates it as pieces move.
//
// A mirrored network also flips a perspective's view left to right while that side's own king stands on files
// e-h, so each side sees its king on files a-d only. A king move across the d/e line changes its own side's
// whole view, so that half is rebuilt instead of updated.
//
// Files: "CSNN" is a plain SCReLU network and "CSNM" a mirrored one; "CSN2" states both choices in its header
// (see parse in nnue.cpp).
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
// acc = prev updated for the move d that led to pos.
void apply(const int16_t* prev, int16_t* acc, const Delta& d, const Position& pos);

// Centipawns from the side to move's point of view.
int evaluate(const Position& pos);

} // namespace NNUE
