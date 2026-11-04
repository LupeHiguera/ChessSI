#include "tt.h"

#include <algorithm>

TranspositionTable TT;

void TranspositionTable::resize(size_t megabytes) {
    table.assign(std::max<size_t>(1, megabytes * 1024 * 1024 / sizeof(TTBucket)), TTBucket{});
}

void TranspositionTable::clear() {
    std::fill(table.begin(), table.end(), TTBucket{});
}

const TTEntry* TranspositionTable::probe(uint64_t key) const {
    for (const TTEntry& e : table[index(key)].entries)
        if (e.key == key && e.bound != BOUND_NONE)
            return &e;
    return nullptr;
}

void TranspositionTable::store(uint64_t key, Move move, int score, int depth, Bound bound) {
    TTBucket& b = table[index(key)];
    TTEntry* e = nullptr;
    for (TTEntry& c : b.entries)
        if (c.key == key && c.bound != BOUND_NONE) {
            e = &c;
            break;
        }
    if (!e) {
        // The least valuable entry: empty first, then from an earlier search, then the shallowest.
        auto worth = [&](const TTEntry& c) {
            return c.bound == BOUND_NONE ? -1000 : (c.generation == generation ? 256 : 0) + c.depth;
        };
        e = &b.entries[0];
        for (TTEntry& c : b.entries)
            if (worth(c) < worth(*e))
                e = &c;
        // A deeper result for another position, written during this search, stays.
        if (e->bound != BOUND_NONE && e->generation == generation && depth < e->depth)
            return;
    }
    // Keep the old best move when this search found none for the same position.
    if (move == MOVE_NONE && e->key == key)
        move = e->move;
    *e = {key, move, int16_t(score), int8_t(depth), uint8_t(bound), generation};
}
