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
    uint8_t generation;
};

// Single-entry buckets. An entry from the current search is only replaced by
// one for another position if the new one is at least as deep. For the same
// position, a non-exact store also leaves an entry more than two plies deeper
// in place (so a depth-0 quiescence write does not evict a main-search result);
// an exact store still replaces it. Entries from an earlier search always give way.
class TranspositionTable {
public:
    void resize(size_t megabytes);
    void clear();
    void new_search() { ++generation; }

    // Returns the entry if it holds this key, else nullptr.
    const TTEntry* probe(uint64_t key) const;
    // Starts loading the entry for `key` into cache, ahead of a probe.
    void prefetch(uint64_t key) const { __builtin_prefetch(table.data() + index(key)); }
    void store(uint64_t key, Move move, int score, int depth, Bound bound);

private:
    size_t index(uint64_t key) const { return size_t((__uint128_t(key) * table.size()) >> 64); }
    std::vector<TTEntry> table;
    uint8_t generation = 0;
};

extern TranspositionTable TT;

// Mate scores are stored relative to the node, not the root.
inline int score_to_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score + ply : score <= -VALUE_MATE_IN_MAX_PLY ? score - ply : score;
}
inline int score_from_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score - ply : score <= -VALUE_MATE_IN_MAX_PLY ? score + ply : score;
}
