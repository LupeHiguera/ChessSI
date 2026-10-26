// CPU reference for the GPU datagen port (issue #31, stage 2): plays datagen games from the given
// start positions exactly like Datagen::play_game in src/datagen.cpp, with a 1 MB transposition table
// (the size of each GPU game's table), and prints the same "<fen> | <score> | <result> | <eval>" lines.
// With -v it also prints each ply's search ("#ply <n> <best> <score> <nodes>"), to find where the GPU
// first goes another way.
//
//   g++ -std=c++20 -O2 -march=native -DNDEBUG -DEVALFILE='"<repo>/nets/<net>.nnue"' gpu/ref.cpp \
//       $(ls src/*.cpp | grep -v main.cpp) -o gpu-ref -pthread
//   ./gpu-ref <file of FENs> <nodes> [-v]
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "../src/bitboard.h"
#include "../src/eval.h"
#include "../src/movegen.h"
#include "../src/nnue.h"
#include "../src/position.h"
#include "../src/search.h"
#include "../src/tt.h"

namespace {

constexpr int MaxPlies = 400, WinScore = 2500, WinPlies = 6; // as in src/datagen.cpp

bool has_legal_move(Position& pos) {
    MoveList list;
    generate(pos, list, ALL_MOVES);
    for (Move m : list) {
        bool legal = pos.do_move(m);
        pos.undo_move(m);
        if (legal)
            return true;
    }
    return false;
}

bool is_noisy(const Position& pos, Move m) {
    return pos.piece_on(to_sq(m)) != NO_PIECE || move_type(m) == EN_PASSANT || move_type(m) == PROMOTION;
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "usage: gpu-ref <file of FENs> <nodes> [-v]" << std::endl;
        return 1;
    }
    Bitboards::init();
    Position::init();
    Eval::init();
    NNUE::load_embedded();
    TT.resize(1);
    std::ifstream in(argv[1]);
    uint64_t nodes = std::strtoull(argv[2], nullptr, 10);
    bool verbose = argc > 3 && std::strcmp(argv[3], "-v") == 0;
    std::string fen;
    int game = 0;
    while (std::getline(in, fen)) {
        if (fen.empty())
            continue;
        Position pos;
        pos.set(fen);
        Search::clear();
        struct Sample { std::string fen; int score, eval; };
        std::vector<Sample> samples;
        double result = 0.5;
        int winStreak = 0;
        for (int ply = 0; ply < MaxPlies; ++ply) {
            if (!has_legal_move(pos)) {
                result = pos.in_check() ? (pos.side_to_move() == WHITE ? 0.0 : 1.0) : 0.5;
                break;
            }
            if (pos.is_draw()) {
                result = 0.5;
                break;
            }
            SearchLimits limits;
            limits.nodes = nodes;
            int whiteEval = pos.side_to_move() == WHITE ? evaluate(pos) : -evaluate(pos);
            SearchResult r = Search::think(pos, limits, false);
            int whiteScore = pos.side_to_move() == WHITE ? r.score : -r.score;
            if (verbose)
                std::cout << "#ply " << ply << " " << move_to_uci(r.best) << " " << r.score << " " << r.nodes << "\n";
            if (!pos.in_check() && !is_noisy(pos, r.best) && std::abs(r.score) < VALUE_MATE_IN_MAX_PLY)
                samples.push_back({pos.fen(), whiteScore, whiteEval});
            if (whiteScore >= WinScore)
                winStreak = winStreak > 0 ? winStreak + 1 : 1;
            else if (whiteScore <= -WinScore)
                winStreak = winStreak < 0 ? winStreak - 1 : -1;
            else
                winStreak = 0;
            if (winStreak >= WinPlies) {
                result = 1.0;
                break;
            }
            if (winStreak <= -WinPlies) {
                result = 0.0;
                break;
            }
            pos.do_move(r.best);
        }
        const char* resultText = result == 1.0 ? "1.0" : result == 0.0 ? "0.0" : "0.5";
        for (const Sample& s : samples)
            std::cout << s.fen << " | " << s.score << " | " << resultText << " | " << s.eval << "\n";
        std::cout << "# game " << game++ << " result " << resultText << std::endl;
    }
    return 0;
}
