#pragma once

#include <cstddef>
#include <vector>

#include "types.h"

enum Bound : uint8_t { BOUND_NONE, BOUND_UPPER, BOUND_LOWER, BOUND_EXACT };

// 16 bytes, same as before the eval and ttPv fields, so a fixed hash size keeps the same
// number of slots. Generation is the top 5 bits (32 searches) so bound and the ttPv bit fit
// in the low 3; an entry from 32 searches ago can therefore look current. One search, and
// the depth-7 bench, never wraps.
struct TTEntry {
    uint64_t key;
    Move move;
    int16_t score;
    int16_t eval; // raw evaluate(), before correction history; VALUE_NONE if unknown
    int8_t depth;
    uint8_t genBound; // bits 0-1 bound, bit 2 ttPv, bits 3-7 generation

    Bound bound() const { return Bound(genBound & 3); }
    bool is_pv() const { return genBound & 4; }
    uint8_t age() const { return uint8_t(genBound >> 3); }
};

static_assert(sizeof(TTEntry) == 16, "TT entry size changes the bench signature");

// Single-entry buckets. An entry from the current search is only replaced by
// one for another position if the new one is at least as deep.
class TranspositionTable {
public:
    void resize(size_t megabytes);
    void clear();
    void new_search() { generation = uint8_t((generation + 1) & 31); }

    // Returns the entry if it holds this key, else nullptr.
    const TTEntry* probe(uint64_t key) const;
    // Starts loading the entry for `key` into cache, ahead of a probe.
    void prefetch(uint64_t key) const { __builtin_prefetch(table.data() + index(key)); }
    // `eval` is the raw static eval, or VALUE_NONE. `pv` is the ttPv bit.
    void store(uint64_t key, Move move, int score, int depth, Bound bound, int eval, bool pv);

private:
    size_t index(uint64_t key) const { return size_t((__uint128_t(key) * table.size()) >> 64); }
    std::vector<TTEntry> table;
    uint8_t generation = 0; // 0..31, see TTEntry::age
};

extern TranspositionTable TT;

// Mate scores are stored relative to the node, not the root.
inline int score_to_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score + ply : score <= -VALUE_MATE_IN_MAX_PLY ? score - ply : score;
}
inline int score_from_tt(int score, int ply) {
    return score >= VALUE_MATE_IN_MAX_PLY ? score - ply : score <= -VALUE_MATE_IN_MAX_PLY ? score + ply : score;
}
