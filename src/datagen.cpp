#include "datagen.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <vector>

#include "movegen.h"
#include "search.h"

namespace {

constexpr int MaxPlies = 400;       // longer games are scored as draws
constexpr int WinScore = 2500;      // adjudicate a win after this many centipawns...
constexpr int WinPlies = 6;         // ...held by the same side for this many plies in a row

struct Sample {
    std::string fen;
    int whiteScore;
};

std::vector<Move> legal_moves(Position& pos) {
    MoveList list;
    generate(pos, list, ALL_MOVES);
    std::vector<Move> legal;
    for (Move m : list) {
        if (pos.do_move(m))
            legal.push_back(m);
        pos.undo_move(m);
    }
    return legal;
}

bool is_noisy(const Position& pos, Move m) {
    return pos.piece_on(to_sq(m)) != NO_PIECE || move_type(m) == EN_PASSANT || move_type(m) == PROMOTION;
}

// Plays one game and returns its result from White's side (1, 0.5 or 0), or -1 if the random
// opening already ended it. Quiet positions with a non-mate score go into `samples`.
double play_game(std::mt19937_64& rng, uint64_t nodes, int randomPlies, std::vector<Sample>& samples) {
    Position pos;
    pos.set(StartFEN);

    for (int i = 0; i < randomPlies; ++i) {
        std::vector<Move> legal = legal_moves(pos);
        if (legal.empty())
            return -1;
        Move m = legal[rng() % legal.size()];
        pos.do_move(m);
    }

    Search::clear();
    int winStreak = 0; // positive: White winning for that many plies; negative: Black
    for (int ply = 0; ply < MaxPlies; ++ply) {
        if (legal_moves(pos).empty())
            return pos.in_check() ? (pos.side_to_move() == WHITE ? 0.0 : 1.0) : 0.5;
        if (pos.is_draw())
            return 0.5;

        SearchLimits limits;
        limits.nodes = nodes;
        SearchResult r = Search::think(pos, limits, false);
        int whiteScore = pos.side_to_move() == WHITE ? r.score : -r.score;

        if (!pos.in_check() && !is_noisy(pos, r.best) && std::abs(r.score) < VALUE_MATE_IN_MAX_PLY)
            samples.push_back({pos.fen(), whiteScore});

        if (whiteScore >= WinScore)
            winStreak = winStreak > 0 ? winStreak + 1 : 1;
        else if (whiteScore <= -WinScore)
            winStreak = winStreak < 0 ? winStreak - 1 : -1;
        else
            winStreak = 0;
        if (winStreak >= WinPlies)
            return 1.0;
        if (winStreak <= -WinPlies)
            return 0.0;

        pos.do_move(r.best);
    }
    return 0.5;
}

} // namespace

void Datagen::run(const std::string& path, int games, uint64_t seed, uint64_t nodes, int randomPlies) {
    std::ofstream out(path, std::ios::app);
    if (!out) {
        std::cerr << "cannot open " << path << std::endl;
        return;
    }
    std::mt19937_64 rng(seed);
    uint64_t positions = 0;
    std::vector<Sample> samples;
    for (int g = 1; g <= games; ++g) {
        samples.clear();
        double result = play_game(rng, nodes, randomPlies, samples);
        if (result < 0)
            continue;
        const char* resultText = result == 1.0 ? "1.0" : result == 0.0 ? "0.0" : "0.5";
        for (const Sample& s : samples)
            out << s.fen << " | " << s.whiteScore << " | " << resultText << "\n";
        positions += samples.size();
        if (g % 100 == 0) {
            out.flush();
            std::cout << "games " << g << " positions " << positions << std::endl;
        }
    }
    std::cout << "done: games " << games << " positions " << positions << std::endl;
}
