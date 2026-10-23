#pragma once

#include <string>

#include "position.h"

// NNUE evaluation, trained by nnue/train.py: (768 -> H) x 2 perspectives -> SCReLU -> 1.
// Until a network is loaded with the EvalFile option, evaluate() keeps using the PeSTO tables.
namespace NNUE {

// Loads a network file; returns false and keeps the current evaluation if it is invalid.
bool load(const std::string& path);
bool loaded();

// Centipawns from the side to move's point of view. Recomputes the accumulators from scratch.
int evaluate(const Position& pos);

} // namespace NNUE
