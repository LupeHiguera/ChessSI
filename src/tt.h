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
static_assert(sizeof(TTEntry) == 16, "four entries fill one 64-byte bucket");

// Four entries share one 64-byte cache line, so a probe still reads a single line but a position
// can sit in any of four places instead of one.
struct alignas(64) TTBucket {
    TTEntry entries[4];
};

// A new result takes its position's entry in the bucket if it has one, else the least valuable:
// an empty entry, then one from an earlier search, then the shallowest. As with one entry per
// bucket, a deeper result for another position written during this search is not replaced.
class TranspositionTable {
public:
    void resize(size_t megabytes);
    void clear();
    void new_search() { ++generation; }

    // Returns the entry if it holds this key, else nullptr.
    const TTEntry* probe(uint64_t key) const;
    // Starts loading the bucket for `key` into cache, ahead of a probe.
    void prefetch(uint64_t key) const { __builtin_prefetch(table.data() + index(key)); }
    void store(uint64_t key, Move move, int score, int depth, Bound bound);

private:
    size_t index(uint64_t key) const { return size_t((__uint128_t(key) * table.size()) >> 64); }
    std::vector<TTBucket> table;
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
