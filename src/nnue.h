#pragma once

#include <cstdint>
#include <string>

#include "types.h"

class Position;

// NNUE evaluation, trained by nnue/train.py.
//   CSNN  (768 -> H) x 2 perspectives -> SCReLU -> 1. net12 and earlier.
//   CSKB  the same dot, with feature rows chosen by a friendly-king bucket (8 or 16).
//         This is the net13 feature transformer, for gen9+ datagen once a file exists.
// Without a network (none compiled in, none loaded with the EvalFile option) evaluate() uses PeSTO.
//
// An accumulator holds the first layer for both perspectives: [0, H) from White's side, [H, 2H)
// from Black's. Position keeps one per ply and updates it as pieces move. A king move on a
// bucketed net refreshes that perspective, because every row belongs to the new bucket.
namespace NNUE {

// Friendly-king bucket for net13 (CSKB). Formula from the research note in PR #69. Square a1 = 0.
// If the king's file is a-d, mirror with ^ 7 so it stands on files e-h.
// K8:  file id (e=0 .. h=3) + 4 * (ranks 1-4 vs 5-8).
// K16: file id + 4 * rank pair (1-2, 3-4, 5-6, 7-8).
// Rank is the real rank. Black's bucket is Black's king on the real board, not vertically flipped.
// nnue/arch.py king_bucket() is this function.
constexpr int king_bucket(Square king, int nBuckets) {
    if (file_of(king) < 4)
        king = Square(king ^ 7);
    int file = file_of(king) - 4; // 0..3 for e..h
    int rank = rank_of(king);     // 0..7
    if (nBuckets == 8)
        return file + 4 * (rank >= 4 ? 1 : 0);
    return file + 4 * (rank >> 1);
}

static_assert(king_bucket(4, 8) == 0);    // e1, ranks 1-4
static_assert(king_bucket(7, 8) == 3);    // h1
static_assert(king_bucket(0, 8) == 3);    // a1 mirrors to h1
static_assert(king_bucket(3, 8) == 0);    // d1 mirrors to e1
static_assert(king_bucket(28, 8) == 0);   // e4, still ranks 1-4
static_assert(king_bucket(36, 8) == 4);   // e5, ranks 5-8
static_assert(king_bucket(60, 8) == 4);   // e8
static_assert(king_bucket(56, 8) == 7);   // a8 mirrors to h8
static_assert(king_bucket(63, 8) == 7);   // h8
static_assert(king_bucket(4, 16) == 0);   // e1, pair 1-2
static_assert(king_bucket(12, 16) == 0);  // e2, same pair
static_assert(king_bucket(20, 16) == 4);  // e3, pair 3-4
static_assert(king_bucket(36, 16) == 8);  // e5, pair 5-6
static_assert(king_bucket(63, 16) == 15); // h8, pair 7-8, file h
static_assert(king_bucket(56, 16) == 15); // a8 mirrors to h8
static_assert(king_bucket(0, 16) == 3);   // a1 mirrors to h1

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
// On a king-bucket net, a perspective whose king is in the delta is refreshed from pos
// (the position after the move) instead of updated one row at a time.
void apply(const int16_t* prev, int16_t* acc, const Delta& d, const Position& pos);
void add(int16_t* acc, Piece p, Square s);
void sub(int16_t* acc, Piece p, Square s);

// Centipawns from the side to move's point of view.
int evaluate(const Position& pos);

} // namespace NNUE
