// Reporting probe for TT reuse across fifty-move clocks. This deliberately
// includes the current private implementation; it changes no engine behavior.
#include "../../src/search.cpp"

#include <cstdlib>
#include <iostream>
#include <string>

void UCI::send(const std::string&) {}

namespace {
int failures = 0;

void probe(const char* label, const std::string& prefix, int clock,
           bool clear, int alpha, int beta) {
    if (clear)
        TT.clear();

    Position pos;
    if (!pos.set(prefix + std::to_string(clock) + " 1"))
        std::exit(2);
    const auto fen = pos.fen();
    const auto key = pos.key();
    const bool draw = pos.is_draw();
    const TTEntry* prior = TT.probe(key);
    const int priorScore = prior ? score_from_tt(prior->score, 1) : 0;
    const int priorDepth = prior ? prior->depth : -1;
    const int priorBound = prior ? int(prior->bound) : int(BOUND_NONE);

    SearchLimits limits;
    limits.nodes = 131072;
    Searcher searcher(pos, limits);
    const int value = searcher.search(alpha, beta, 3, 1);
    const bool restored = pos.fen() == fen && pos.key() == key && pos.is_draw() == draw;

    std::cout << label << '|' << clock << '|' << value << '|' << searcher.nodes
              << '|' << key << '|' << draw << '|' << searcher.stopped << '|' << restored
              << '|' << priorScore << '|' << priorDepth << '|' << priorBound << '\n';
    failures += !restored || searcher.stopped;
}
} // namespace

int main() {
    Bitboards::init();
    Position::init();
    Eval::init();
    TT.resize(16);
    Search::stop = false;
    const std::string positions[] = {
        "4k3/8/2K5/8/8/8/8/R7 w - - ",
        "r7/8/8/8/8/2k5/8/4K3 b - - "
    };
    std::cout << "# label|clock|score|nodes|key|draw|stopped|restored|prior_score|prior_depth|prior_bound\n";
    for (int index = 0; index < 2; ++index) {
        std::cout << "POSITION " << index << '\n';
        const auto& fen = positions[index];
        probe("fresh_0_full", fen, 0, true, -VALUE_INF, VALUE_INF);
        probe("warm_98_from_0", fen, 98, false, 0, 1);
        probe("fresh_98_null", fen, 98, true, 0, 1);
        probe("fresh_98_full", fen, 98, true, -VALUE_INF, VALUE_INF);
        probe("warm_0_from_98", fen, 0, false, 0, 1);
        probe("fresh_0_null", fen, 0, true, 0, 1);
        probe("fresh_0_full_anchor", fen, 0, true, -VALUE_INF, VALUE_INF);
        probe("warm_100_from_0", fen, 100, false, 0, 1);
        probe("fresh_98_full_repeat", fen, 98, true, -VALUE_INF, VALUE_INF);
    }
    // Success means the bounded probe completed and restored position state.
    // Scores are evidence to inspect, not assertions that existing bugs remain.
    return failures ? 1 : 0;
}
