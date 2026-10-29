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
    Search::clear(); // all search state, so each probe starts fresh
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

// The original 15 direct probes deliberately leave the ply stack's moves as MOVE_NONE,
// isolating RFP from NMP at their entry. These two cases preserve actual prefix context.
void check_context(const char* name, bool throughNull) {
    Position pos;
    const std::string initial = throughNull
        ? "5k2/8/2K5/8/8/8/8/R7 w - - 0 1"
        : "5k2/8/2K5/8/8/8/8/R7 b - - 0 1";
    if (!pos.set(initial)) std::exit(2);
    const std::string initialFen = pos.fen();
    const uint64_t initialKey = pos.key();
    const bool initialDraw = pos.is_draw();
    if (throughNull) pos.do_null_move();
    const Move predecessor = make_move(make_square(5, 7), make_square(4, 7));
    if (!pos.do_move(predecessor)) {
        pos.undo_move(predecessor);
        std::exit(2);
    }
    const std::string contextFen = pos.fen();
    const uint64_t contextKey = pos.key();
    const bool contextDraw = pos.is_draw();
    const int staticEval = evaluate(pos);
    Search::clear(); // all search state, so each probe starts fresh
    Search::stop = false;
    SearchLimits limits;
    limits.nodes = 200000;
    Searcher s(pos, limits);
    const int ply = throughNull ? 2 : 1;
    if (throughNull) s.ply_stack(0)->move = MOVE_NONE;
    s.ply_stack(ply - 1)->move = predecessor;
    const int score = s.search(0, 1, 3, ply, false);
    bool ok = !s.stopped && s.nodes == 1 && score == staticEval
           && staticEval - 450 >= 1
           && pos.rule50() == (throughNull ? 2 : 1)
           && pos.fen() == contextFen && pos.key() == contextKey
           && pos.is_draw() == contextDraw
           && s.ply_stack(ply - 1)->move == predecessor;
    if (throughNull) ok &= s.ply_stack(0)->move == MOVE_NONE;
    pos.undo_move(predecessor);
    if (throughNull) pos.undo_null_move();
    ok &= pos.fen() == initialFen && pos.key() == initialKey
       && pos.is_draw() == initialDraw;
    std::cout << (ok ? "PASS " : "FAIL ") << name << ": score " << score
              << ", nodes " << s.nodes << ", stopped " << s.stopped << '\n';
    ok ? ++passed : ++failed;
}

// Round-trip of the plumbing flags. Quiet LMR reads them deeper than these probes.
void check_plumbing() {
    const std::string rook = "4k3/8/2K5/8/8/8/8/R7 w - - 0 1";
    Position pos;
    if (!pos.set(rook)) std::exit(2);
    Search::clear();
    TT.new_search();
    SearchLimits limits;
    limits.nodes = 200000;

    TT.store(0x1234, make_move(0, 8), 12, 3, BOUND_LOWER, 400, true);
    const TTEntry* e = TT.probe(0x1234);
    bool ok = e && e->move == make_move(0, 8) && e->score == 12 && e->depth == 3
           && e->bound() == BOUND_LOWER && e->eval == 400 && e->is_pv();
    // A store with no move keeps the old one. An out-of-range eval is recorded as missing.
    TT.store(0x1234, MOVE_NONE, -5, 4, BOUND_EXACT, 40000, false);
    e = TT.probe(0x1234);
    ok &= e && e->move == make_move(0, 8) && e->score == -5 && e->bound() == BOUND_EXACT
       && e->eval == VALUE_NONE && !e->is_pv();

    Search::clear();
    TT.new_search();
    Searcher wide(pos, limits);
    const int raw = evaluate(pos);
    wide.search(-1000, 1000, 1, 0, false);
    e = TT.probe(pos.key());
    ok &= e && e->is_pv() && e->eval == raw && wide.ply_stack(0)->ttPv
       && wide.ply_stack(0)->improving && wide.ply_stack(0)->staticEval == raw;

    Search::clear();
    TT.new_search();
    Searcher narrow(pos, limits);
    narrow.ply_stack(0)->staticEval = 2000; // two plies before the node under test
    narrow.search(0, 1, 1, 2, true);
    ok &= narrow.ply_stack(2)->staticEval == raw && !narrow.ply_stack(2)->improving
       && !narrow.ply_stack(2)->ttPv;

    narrow.ply_stack(0)->staticEval = VALUE_NONE;
    narrow.ply_stack(-2)->staticEval = 2000; // in check two plies ago: fall back four plies
    narrow.search(0, 1, 1, 2, true);
    ok &= !narrow.ply_stack(2)->improving;
    narrow.ply_stack(-2)->staticEval = 0;
    narrow.search(0, 1, 1, 2, true);
    ok &= narrow.ply_stack(2)->improving;

    Position checked;
    if (!checked.set("7k/8/5K2/8/8/8/r7/7R b - - 0 1")) std::exit(2);
    Searcher evasions(checked, limits);
    evasions.search(-2001, -2000, 1, 1, true);
    ok &= evasions.ply_stack(1)->staticEval == VALUE_NONE && !evasions.ply_stack(1)->improving;

    std::cout << (ok ? "PASS " : "FAIL ") << "search plumbing round-trip\n";
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
    check("depth six searches", rook, 6, -2001, -2000, SearchTree);
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
    check_context("real predecessor enables RFP before NMP", false);
    check_context("null descendant retains RFP eligibility", true);
    check_plumbing();
    std::cout << passed << " passed, " << failed << " failed\n";
    return failed ? 1 : 0;
}
