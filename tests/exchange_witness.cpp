// Selector tests for quiet defenses chosen by one exchange witness.
// The pass only reorders: these checks never require a cutoff or an extension.
#include "../src/search.cpp"

#include <iostream>
#include <string>
#include <vector>

void UCI::send(const std::string&) {}

namespace {

int passed = 0;
int failed = 0;

void expect(bool ok, const std::string& name) {
    std::cout << (ok ? "PASS " : "FAIL ") << name << '\n';
    ok ? ++passed : ++failed;
}

int find_move(const MoveList& list, const std::string& uci) {
    for (int i = 0; i < list.size; ++i)
        if (move_to_uci(list.moves[i]) == uci)
            return i;
    return -1;
}

struct Node {
    Position pos;
    SearchLimits limits;
    Searcher search;
    explicit Node(const std::string& fen) : limits(), search(pos, limits) {
        if (!pos.set(fen)) {
            std::cerr << "bad fen " << fen << '\n';
            std::exit(2);
        }
    }
};

struct Scored {
    MoveList list;
    int scores[256] = {};
    std::vector<Move> order;
    std::string fen;
    uint64_t key = 0;
};

Scored prepare(Node& node) {
    Scored out;
    generate(node.pos, out.list, ALL_MOVES);
    node.search.score_moves(out.list, out.scores, MOVE_NONE, 1);
    out.order.assign(out.list.moves, out.list.moves + out.list.size);
    out.fen = node.pos.fen();
    out.key = node.pos.key();
    return out;
}

void set_score(Scored& s, const std::string& uci, int score, const char* what) {
    int i = find_move(s.list, uci);
    if (i < 0) {
        std::cerr << "missing move " << uci << " for " << what << '\n';
        std::exit(2);
    }
    s.scores[i] = score;
}

bool restored(const Node& node, const Scored& s) {
    return node.pos.fen() == s.fen && node.pos.key() == s.key && node.pos.is_draw() == false;
}

bool same_moves(const Scored& s) {
    if (int(s.order.size()) != s.list.size)
        return false;
    for (int i = 0; i < s.list.size; ++i)
        if (s.list.moves[i] != s.order[i])
            return false;
    return true;
}

bool promoted(const Scored& s, const std::string& uci) {
    int i = find_move(s.list, uci);
    return i >= 0 && s.scores[i] >= 94'000;
}

// Blocks the rook that would take the knight. Moving that knight away is not
// the defense under test, even when history ranks it first.
void test_interpose_excludes_victim() {
    Node node("k6r/8/8/6N1/7N/8/8/4K3 w - - 0 1");
    Scored s = prepare(node);
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(7, 3))
            s.scores[i] = 80'000;
    set_score(s, "g5h7", 70'000, "interpose");
    int n = node.search.promote_exchange_defenses(s.list, s.scores, 0);
    bool victims = true;
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(7, 3) && s.scores[i] != 80'000)
            victims = false;
    expect(n >= 1 && promoted(s, "g5h7") && victims && restored(node, s) && same_moves(s),
           "interpose blocks the rook and does not promote moving the knight");
}

// A pawn step that recaptures the rook swings the exchange from +knight to a loss.
void test_pawn_defense_crosses_to_nonpositive() {
    Node node("r3k3/8/8/8/N7/8/1P6/4K3 w - - 0 1");
    Scored s = prepare(node);
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(0, 3))
            s.scores[i] = 80'000;
    set_score(s, "b2b3", 70'000, "pawn defense");
    int n = node.search.promote_exchange_defenses(s.list, s.scores, 0);
    bool victims = true;
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(0, 3) && s.scores[i] != 80'000)
            victims = false;
    expect(n >= 1 && promoted(s, "b2b3") && victims && restored(node, s) && same_moves(s),
           "pawn defense makes the rook capture unprofitable");
}

// Bishop recapture still leaves the knight's capture of the queen ahead.
void test_positive_gain_is_not_enough() {
    Node node("4k3/8/2n5/8/3Q4/8/8/4K2B w - - 0 1");
    Scored s = prepare(node);
    set_score(s, "h1e4", 70'000, "partial defense");
    int n = node.search.promote_exchange_defenses(s.list, s.scores, 0);
    expect(n == 0 && !promoted(s, "h1e4") && s.scores[find_move(s.list, "h1e4")] == 70'000 && restored(node, s),
           "a defense that leaves the exchange winning is not promoted");
}

// The bishop move does not attack the queen. It pins the knight that would take it.
void test_pin_makes_capture_illegal() {
    Node node("4k3/8/2n5/8/3Q4/8/2B5/4K3 w - - 0 1");
    Scored s = prepare(node);
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(3, 3))
            s.scores[i] = 80'000;
    set_score(s, "c2a4", 70'000, "pin");
    int n = node.search.promote_exchange_defenses(s.list, s.scores, 0);
    bool victims = true;
    for (int i = 0; i < s.list.size; ++i)
        if (from_sq(s.list.moves[i]) == make_square(3, 3) && s.scores[i] != 80'000)
            victims = false;
    expect(n >= 1 && promoted(s, "c2a4") && victims && restored(node, s) && same_moves(s),
           "pinning the capturer promotes the bishop");
}

// Four higher-history quiets sit on the pin ray and do not save the queen.
// The rook that does is fifth, so the cap leaves it alone. Ranked first, it is promoted.
void test_inspects_four_in_history_order() {
    const char* fen = "4k3/8/8/8/1Q2rNN1/8/8/2R4K w - - 0 1";
    {
        Node node(fen);
        Scored s = prepare(node);
        set_score(s, "f4e2", 400, "decoy");
        set_score(s, "f4e6", 300, "decoy");
        set_score(s, "g4e3", 200, "decoy");
        set_score(s, "g4e5", 100, "decoy");
        set_score(s, "c1e1", 50, "real pin");
        node.search.promote_exchange_defenses(s.list, s.scores, 0);
        expect(!promoted(s, "c1e1") && s.scores[find_move(s.list, "c1e1")] == 50
                   && s.scores[find_move(s.list, "f4e2")] == 400 && restored(node, s) && same_moves(s),
               "fifth history quiet is not inspected");
    }
    {
        Node node(fen);
        Scored s = prepare(node);
        set_score(s, "f4e2", 400, "decoy");
        set_score(s, "f4e6", 300, "decoy");
        set_score(s, "g4e3", 200, "decoy");
        set_score(s, "g4e5", 100, "decoy");
        set_score(s, "c1e1", 1000, "real pin");
        node.search.promote_exchange_defenses(s.list, s.scores, 0);
        expect(promoted(s, "c1e1") && !promoted(s, "f4e2") && restored(node, s),
               "same pin is promoted when it leads the history order");
    }
}

// The bishop wins the knight back with interest, so there is no witness.
void test_profit_below_a_pawn_selects_nothing() {
    Node node("4k3/6b1/8/R7/3N4/4P3/8/4K3 w - - 0 1");
    Scored s = prepare(node);
    set_score(s, "a5e5", 70'000, "would-be block");
    int n = node.search.promote_exchange_defenses(s.list, s.scores, 0);
    expect(n == 0 && s.scores[find_move(s.list, "a5e5")] == 70'000 && restored(node, s),
           "an exchange below a pawn is not a witness");
}

void test_search_window_and_option() {
    const char* fen = "k6r/8/8/6N1/7N/8/8/4K3 w - - 0 1";
    auto run = [&](bool on, int depth) {
        Search::clear();
        Search::stop = false;
        Search::set_exchange_witness(on);
        Position pos;
        if (!pos.set(fen))
            std::exit(2);
        std::string fenBefore = pos.fen();
        uint64_t key = pos.key();
        SearchLimits limits;
        limits.nodes = 200000;
        Searcher s(pos, limits);
        s.search(-VALUE_INF, VALUE_INF, depth, 0);
        bool ok = pos.fen() == fenBefore && pos.key() == key && !s.stopped;
        return std::pair<bool, int>(ok, s.witnessPromotions);
    };
    auto off = run(false, 5);
    auto shallow = run(true, 4);
    auto on = run(true, 5);
    expect(off.first && off.second == 0, "UCI option off promotes nothing at depth 5");
    expect(shallow.first && shallow.second == 0, "depth 4 is outside the witness window");
    expect(on.first && on.second > 0, "depth 5 search promotes a quiet defense");
    Search::set_exchange_witness(true);
}

} // namespace

int main() {
    Bitboards::init();
    Position::init();
    Eval::init();
    TT.resize(16);
    test_interpose_excludes_victim();
    test_pawn_defense_crosses_to_nonpositive();
    test_positive_gain_is_not_enough();
    test_pin_makes_capture_illegal();
    test_inspects_four_in_history_order();
    test_profit_below_a_pawn_selects_nothing();
    test_search_window_and_option();
    std::cout << passed << " passed, " << failed << " failed\n";
    return failed ? 1 : 0;
}
