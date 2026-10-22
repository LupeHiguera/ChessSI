#include "search.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <thread>

#include "eval.h"
#include "movegen.h"
#include "tt.h"
#include "uci.h"

// Baseline search: iterative deepening, principal variation search, a
// transposition table, check extension, and captures-only quiescence search
// with MVV-LVA ordering, plus the shallow reverse futility pruning trial.
// Further pruning, reductions and history remain separate experiments.

std::atomic<bool> Search::stop{false};

namespace {

using Clock = std::chrono::steady_clock;

constexpr int PieceValue[7] = {100, 320, 330, 500, 900, 0, 0};

struct Searcher {
    Position& pos;
    SearchLimits limits;
    Clock::time_point start = Clock::now();
    int64_t softLimit = 0; // stop deepening after this many ms (0 = none)
    int64_t hardLimit = 0; // abort the search after this many ms (0 = none)
    uint64_t nodes = 0;
    bool stopped = false;

    Move pv[MAX_PLY + 1][MAX_PLY + 1];
    int pvLength[MAX_PLY + 1];

    Searcher(Position& p, const SearchLimits& l) : pos(p), limits(l) {}

    int64_t elapsed() const {
        return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - start).count();
    }

    void set_time_limits() {
        constexpr int64_t overhead = 50;
        Color us = pos.side_to_move();
        if (limits.movetime) {
            softLimit = hardLimit = std::max<int64_t>(1, limits.movetime - overhead);
        } else if (limits.time[us]) {
            int64_t available = std::max<int64_t>(1, limits.time[us] - overhead);
            int movesToGo = limits.movestogo ? limits.movestogo : 25;
            softLimit = std::min(available, available / movesToGo + limits.inc[us] * 3 / 4);
            hardLimit = std::min(available, softLimit * 3);
        }
    }

    void check_limits() {
        if ((nodes & 1023) != 0)
            return;
        if (Search::stop || (hardLimit && elapsed() >= hardLimit) || (limits.nodes && nodes >= limits.nodes))
            stopped = true;
    }

    // Assigns each move an ordering score, best first.
    void score_moves(MoveList& list, int* scores, Move ttMove) {
        for (int i = 0; i < list.size; ++i) {
            Move m = list.moves[i];
            if (m == ttMove)
                scores[i] = 1'000'000;
            else if (move_type(m) == EN_PASSANT)
                scores[i] = 100'000 + PieceValue[PAWN] * 10 - PAWN;
            else if (pos.piece_on(to_sq(m)) != NO_PIECE)
                scores[i] = 100'000 + PieceValue[type_of(pos.piece_on(to_sq(m)))] * 10 - type_of(pos.piece_on(from_sq(m)));
            else if (move_type(m) == PROMOTION && promotion_type(m) == QUEEN)
                scores[i] = 90'000;
            else
                scores[i] = 0;
        }
    }

    // Selection sort step: brings the best remaining move to index i.
    static Move pick_move(MoveList& list, int* scores, int i) {
        int best = i;
        for (int j = i + 1; j < list.size; ++j)
            if (scores[j] > scores[best])
                best = j;
        std::swap(list.moves[i], list.moves[best]);
        std::swap(scores[i], scores[best]);
        return list.moves[i];
    }

    int qsearch(int alpha, int beta, int ply) {
        pvLength[ply] = 0;
        ++nodes;
        check_limits();
        if (stopped)
            return 0;

        int standPat = evaluate(pos);
        if (ply >= MAX_PLY - 1 || standPat >= beta)
            return standPat;
        alpha = std::max(alpha, standPat);

        MoveList list;
        generate(pos, list, NOISY_MOVES);
        int scores[256];
        score_moves(list, scores, MOVE_NONE);

        int best = standPat;
        for (int i = 0; i < list.size; ++i) {
            Move m = pick_move(list, scores, i);
            if (!pos.do_move(m)) {
                pos.undo_move(m);
                continue;
            }
            int score = -qsearch(-beta, -alpha, ply + 1);
            pos.undo_move(m);
            if (stopped)
                return 0;

            if (score > best) {
                best = score;
                if (score > alpha) {
                    alpha = score;
                    if (score >= beta)
                        break;
                }
            }
        }
        return best;
    }

    int search(int alpha, int beta, int depth, int ply) {
        pvLength[ply] = 0;
        bool inCheck = pos.in_check();
        if (inCheck)
            ++depth;
        if (depth <= 0)
            return qsearch(alpha, beta, ply);

        ++nodes;
        check_limits();
        if (stopped)
            return 0;

        bool root = ply == 0;
        bool pvNode = beta - alpha > 1;
        if (!root) {
            if (pos.is_draw())
                return 0;
            if (ply >= MAX_PLY - 1)
                return evaluate(pos);
        }

        const TTEntry* tte = TT.probe(pos.key());
        Move ttMove = tte ? tte->move : MOVE_NONE;
        if (tte && !pvNode && tte->depth >= depth) {
            int ttScore = score_from_tt(tte->score, ply);
            if (tte->bound == BOUND_EXACT
                || (tte->bound == BOUND_LOWER && ttScore >= beta)
                || (tte->bound == BOUND_UPPER && ttScore <= alpha))
                return ttScore;
        }

        // Reverse futility pruning: at shallow null-window nodes, a large
        // static advantage may make the remaining search unnecessary.
        if (!root && !pvNode && !inCheck && depth <= 3
            && pos.rule50() + depth < 100
            && std::abs(beta) < VALUE_MATE_IN_MAX_PLY
            && (pos.pieces(pos.side_to_move()) & ~(pos.pieces(PAWN) | pos.pieces(KING)))) {
            const int staticEval = evaluate(pos);
            if (std::abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 150 * depth >= beta)
                // A static advantage cannot override stalemate.
                return first_legal_move() == MOVE_NONE ? 0 : staticEval;
        }

        MoveList list;
        generate(pos, list, ALL_MOVES);
        int scores[256];
        score_moves(list, scores, ttMove);

        int originalAlpha = alpha;
        int best = -VALUE_INF;
        Move bestMove = MOVE_NONE;
        int legalMoves = 0;

        for (int i = 0; i < list.size; ++i) {
            Move m = pick_move(list, scores, i);
            if (!pos.do_move(m)) {
                pos.undo_move(m);
                continue;
            }
            ++legalMoves;

            int score;
            if (legalMoves == 1)
                score = -search(-beta, -alpha, depth - 1, ply + 1);
            else {
                score = -search(-alpha - 1, -alpha, depth - 1, ply + 1);
                if (score > alpha && score < beta)
                    score = -search(-beta, -alpha, depth - 1, ply + 1);
            }
            pos.undo_move(m);
            if (stopped)
                return 0;

            if (score > best) {
                best = score;
                if (score > alpha) {
                    alpha = score;
                    bestMove = m;
                    pv[ply][0] = m;
                    for (int j = 0; j < pvLength[ply + 1]; ++j)
                        pv[ply][j + 1] = pv[ply + 1][j];
                    pvLength[ply] = pvLength[ply + 1] + 1;
                    if (score >= beta)
                        break;
                }
            }
        }

        if (legalMoves == 0)
            return inCheck ? -VALUE_MATE + ply : 0;

        Bound bound = best >= beta ? BOUND_LOWER : alpha > originalAlpha ? BOUND_EXACT : BOUND_UPPER;
        TT.store(pos.key(), bestMove, score_to_tt(best, ply), depth, bound);
        return best;
    }

    std::string score_string(int score) const {
        if (std::abs(score) < VALUE_MATE_IN_MAX_PLY)
            return "cp " + std::to_string(score);
        int moves = score > 0 ? (VALUE_MATE - score + 1) / 2 : -(VALUE_MATE + score) / 2;
        return "mate " + std::to_string(moves);
    }

    Move first_legal_move() {
        MoveList list;
        generate(pos, list, ALL_MOVES);
        for (Move m : list) {
            bool legal = pos.do_move(m);
            pos.undo_move(m);
            if (legal)
                return m;
        }
        return MOVE_NONE;
    }
};

} // namespace

void Search::clear() {
    TT.clear();
}

SearchResult Search::think(Position& pos, const SearchLimits& limits, bool verbose) {
    Searcher s(pos, limits);
    s.set_time_limits();
    SearchResult result;

    for (int depth = 1; depth <= std::min(limits.depth, MAX_PLY - 1); ++depth) {
        int score = s.search(-VALUE_INF, VALUE_INF, depth, 0);
        if (s.stopped)
            break;

        if (s.pvLength[0] > 0)
            result.best = s.pv[0][0];
        result.score = score;

        if (verbose) {
            int64_t ms = s.elapsed();
            std::ostringstream info;
            info << "info depth " << depth << " score " << s.score_string(score) << " nodes " << s.nodes
                 << " nps " << s.nodes * 1000 / (ms + 1) << " time " << ms << " pv";
            for (int i = 0; i < s.pvLength[0]; ++i)
                info << " " << move_to_uci(s.pv[0][i]);
            UCI::send(info.str());
        }

        if (s.softLimit && s.elapsed() >= s.softLimit)
            break;
    }

    // "go infinite" must not report a move until told to stop.
    while (limits.infinite && !Search::stop)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));

    if (result.best == MOVE_NONE)
        result.best = s.first_legal_move();
    result.nodes = s.nodes;
    return result;
}
