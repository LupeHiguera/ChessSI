#pragma once

#include <atomic>
#include <cstdint>

#include "position.h"

struct SearchLimits {
    int depth = MAX_PLY - 1;
    uint64_t nodes = 0;
    int64_t movetime = 0;
    int64_t time[2] = {0, 0};
    int64_t inc[2] = {0, 0};
    int movestogo = 0;
    bool infinite = false;
};

struct SearchResult {
    Move best = MOVE_NONE;
    int score = 0;
    uint64_t nodes = 0;
};

namespace Search {

extern std::atomic<bool> stop;

// Forget everything learned in earlier games.
void clear();

// Search threads (the UCI Threads option). With more than one, helper threads
// search the same root and share the transposition table (Lazy SMP).
void set_threads(int n);

// Iterative deepening from the root. Prints UCI "info" lines when verbose.
SearchResult think(Position& pos, const SearchLimits& limits, bool verbose);

} // namespace Search
