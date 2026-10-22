#pragma once

#include <cstddef>
#include <vector>

#include "types.h"

enum Bound : uint8_t { BOUND_NONE, BOUND_UPPER, BOUND_LOWER, BOUND_EXACT };

struct TTEntry {
    uint64_t key;
    Move move;
    int16_t score;
    int8_t depth;
    uint8_t bound;
};

// Single-entry buckets with always-replace; a better replacement scheme is an
// obvious early experiment.
class TranspositionTable {
public:
    void resize(size_t megabytes);
    void clear();

    // Returns the entry if it holds this key, else nullptr.
    const TTEntry* probe(uint64_t key) const;
    void store(uint64_t key, Move move, int score, int depth, Bound bound);

private:
    size_t index(uint64_t key) const { return size_t((__uint128_t(key) * table.size()) >> 64); }
    std::vector<TTEntry> table;
};

extern TranspositionTable TT;

// Mate scores are stored relative to the node, not the root.
inline int score_to_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score + ply : score <= -VALUE_MATE_IN_MAX_PLY ? score - ply : score;
}
inline int score_from_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score - ply : score <= -VALUE_MATE_IN_MAX_PLY ? score + ply : score;
}
