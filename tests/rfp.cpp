// Exercise the private search boundaries without adding an engine API.
#include "../src/search.cpp"

#include <iostream>
#include <optional>

void UCI::send(const std::string&) {}

namespace {
int passed = 0;
int failed = 0;
enum Expected { Cut, SearchTree, Draw, Stop };

void check(const char* name, const std::string& fen, int depth, int alpha, int beta,
           Expected expected, int ply = 1, bool requirePV = false,
           std::optional<int> expectedScore = std::nullopt) {
    Position pos;
    if (!pos.set(fen)) std::exit(2);
    const std::string originalFen = pos.fen();
    const uint64_t originalKey = pos.key();
    const bool originalDraw = pos.is_draw();
    const int staticEval = evaluate(pos);
    TT.clear();
    Search::stop = expected == Stop;
    SearchLimits limits;
    limits.nodes = 200000;
    Searcher s(pos, limits);
    if (expected == Stop) s.nodes = 1023;
    const int score = s.search(alpha, beta, depth, ply);
    bool ok = pos.fen() == originalFen && pos.key() == originalKey
           && pos.is_draw() == originalDraw;
    if (expected == Cut) ok &= !s.stopped && s.nodes == 1 && score == staticEval;
    if (expected == SearchTree) ok &= !s.stopped && s.nodes > 1;
    if (expected == Draw) ok &= !s.stopped && score == 0;
    if (expected == Stop) ok &= s.stopped && s.nodes == 1024 && score == 0;
    if (expectedScore) ok &= score == *expectedScore;
    if (requirePV) {
        ok &= s.pvLength[ply] > 0;
        if (s.pvLength[ply] > 0) {
            const Move move = s.pv[ply][0];
            ok &= pos.do_move(move);
            pos.undo_move(move);
            ok &= pos.fen() == originalFen && pos.key() == originalKey;
        }
    }
    Search::stop = false;
    std::cout << (ok ? "PASS " : "FAIL ") << name << ": score " << score
              << ", nodes " << s.nodes << ", stopped " << s.stopped << '\n';
    ok ? ++passed : ++failed;
}
} // namespace

int main() {
    Bitboards::init();
    Position::init();
    Eval::init();
    TT.resize(16);
    const std::string rook = "4k3/8/2K5/8/8/8/8/R7 w - - 0 1";
    const std::string rookBlack = "r7/8/8/8/8/2k5/8/4K3 b - - 0 1";
    check("eligible depth one", rook, 1, 0, 1, Cut);
    check("eligible depth three", rook, 3, 0, 1, Cut);
    check("eligible black side", rookBlack, 3, 0, 1, Cut);
    check("root keeps a legal PV", rook, 1, 0, 1, SearchTree, 0, true);
    check("wide window searches", rook, 1, -1, 1, SearchTree);
    check("check searches evasions", "7k/8/5K2/8/8/8/r7/7R b - - 0 1",
          1, -2001, -2000, SearchTree);
    check("pawn-only ending searches", "4k3/P7/2K5/8/8/8/8/8 w - - 0 1",
          1, -2001, -2000, SearchTree);
    check("depth four searches", rook, 4, -2001, -2000, SearchTree);
    check("mate-band window searches", rook, 1, -VALUE_MATE_IN_MAX_PLY - 1,
          -VALUE_MATE_IN_MAX_PLY, SearchTree);
    check("insufficient static margin searches", rook, 1, 999, 1000, SearchTree);
    check("fifty-move horizon searches", "4k3/8/2K5/8/8/8/8/R7 w - - 98 1",
          3, 0, 1, SearchTree, 1, false, 0);
    check("stalemate overrides static advantage",
          "7k/4p3/4P3/p3P3/P3P3/P1b5/PRb5/K7 w - - 0 1", 1, 0, 1, Draw);
    check("mirrored stalemate overrides static advantage",
          "k7/prB5/p1B5/p3p3/P3p3/4p3/4P3/7K b - - 0 1", 1, 0, 1, Draw);
    check("draw exit precedes pruning", "4k3/8/2K5/8/8/8/8/R7 w - - 100 1",
          3, 0, 1, Draw);
    check("stop exit precedes pruning", rook, 3, 0, 1, Stop);
    std::cout << passed << " passed, " << failed << " failed\n";
    return failed ? 1 : 0;
}
