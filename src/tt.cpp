#include "tt.h"

TranspositionTable TT;

void TranspositionTable::resize(size_t megabytes) {
    table.assign(megabytes * 1024 * 1024 / sizeof(TTEntry), TTEntry{});
}

void TranspositionTable::clear() {
    std::fill(table.begin(), table.end(), TTEntry{});
}

const TTEntry* TranspositionTable::probe(uint64_t key) const {
    const TTEntry& e = table[index(key)];
    return e.key == key && e.bound != BOUND_NONE ? &e : nullptr;
}

void TranspositionTable::store(uint64_t key, Move move, int score, int depth, Bound bound) {
    TTEntry& e = table[index(key)];
    // Keep the old best move when this search found none for the same position.
    if (move == MOVE_NONE && e.key == key)
        move = e.move;
    e = {key, move, int16_t(score), int8_t(depth), uint8_t(bound)};
}
