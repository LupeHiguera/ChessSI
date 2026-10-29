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
    return e.key == key && e.bound() != BOUND_NONE ? &e : nullptr;
}

void TranspositionTable::store(uint64_t key, Move move, int score, int depth, Bound bound, int eval, bool pv) {
    TTEntry& e = table[index(key)];
    // A deeper result for another position, written during this search, stays.
    if (e.key != key && e.age() == generation && depth < e.depth)
        return;
    // Keep the old best move when this search found none for the same position.
    if (move == MOVE_NONE && e.key == key)
        move = e.move;
    // VALUE_NONE (and anything outside int16) means "no eval"; never store a truncated one.
    int16_t storedEval = VALUE_NONE;
    if (eval > -VALUE_NONE && eval < VALUE_NONE)
        storedEval = int16_t(eval);
    e.key = key;
    e.move = move;
    e.score = int16_t(score);
    e.eval = storedEval;
    e.depth = int8_t(depth);
    e.genBound = uint8_t((generation << 3) | (pv ? 4 : 0) | (int(bound) & 3));
}
