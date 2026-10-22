#pragma once

#include <cstdint>
#include <string>

#include "position.h"

uint64_t perft(Position& pos, int depth);

// Prints the node count under each root move, then the total.
void perft_divide(Position& pos, int depth);

// Runs an EPD file of "fen ;D1 n ;D2 n ..." lines up to maxDepth.
// Returns true if every count matches.
bool perft_suite(const std::string& path, int maxDepth);
