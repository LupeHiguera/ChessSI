#include "tt.h"

#include <cstdlib>

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

namespace {

// Whether two searches of one position, both at least 4 deep and within 2 plies of each other, gave
// finite score ranges at least 64 cp apart (Astra's preregistered thresholds). A lower bound s is the
// range [s, inf), an upper bound (-inf, s], an exact score [s, s].
bool disjoint(int s1, int d1, Bound b1, int s2, int d2, Bound b2) {
    constexpr int Gap = 64;
    if (d1 < 4 || d2 < 4 || std::abs(d1 - d2) > 2)
        return false;
    if (std::abs(s1) >= VALUE_MATE_IN_MAX_PLY || std::abs(s2) >= VALUE_MATE_IN_MAX_PLY)
        return false;
    int lo1 = b1 == BOUND_UPPER ? -VALUE_INF : s1, hi1 = b1 == BOUND_LOWER ? VALUE_INF : s1;
    int lo2 = b2 == BOUND_UPPER ? -VALUE_INF : s2, hi2 = b2 == BOUND_LOWER ? VALUE_INF : s2;
    return lo2 - hi1 >= Gap || lo1 - hi2 >= Gap;
}

} // namespace

void TranspositionTable::store(uint64_t key, Move move, int score, int depth, Bound bound) {
    TTEntry& e = table[index(key)];
    uint8_t conflict = 0;
    if (e.key == key) {
        // Keep the old best move when this search found none for the same position.
        if (move == MOVE_NONE)
            move = e.move;
        // A warning stays for as long as the entry holds this position.
        conflict = e.conflict
                   || (e.bound != BOUND_NONE && disjoint(e.score, e.depth, Bound(e.bound), score, depth, bound));
    }
    e = {key, move, int16_t(score), int8_t(depth), uint8_t(bound), conflict};
}
