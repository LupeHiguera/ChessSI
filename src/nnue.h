#pragma once

#include <cstdint>
#include <string>

#include "types.h"

class Position;

// NNUE evaluation, trained by nnue/train.py: (768 -> H) x 2 perspectives -> SCReLU -> 1.
// Until a network is loaded with the EvalFile option, evaluate() keeps using the PeSTO tables.
//
// An accumulator holds the first layer for both perspectives: [0, H) from White's side, [H, 2H)
// from Black's. Position keeps one per ply and updates it as pieces move.
namespace NNUE {

// Loads a network file; returns false and keeps the current evaluation if it is invalid.
bool load(const std::string& path);
bool loaded();

// Changes with every successful load, so a Position can tell its accumulators are stale.
// 0 means no network.
int generation();
int hidden();

void refresh(const Position& pos, int16_t* acc);
void add(int16_t* acc, Piece p, Square s);
void sub(int16_t* acc, Piece p, Square s);

// Centipawns from the side to move's point of view.
int evaluate(const Position& pos);

} // namespace NNUE
