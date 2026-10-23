#include "search.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <thread>

#include "eval.h"
#include "movegen.h"
#include "tt.h"
#include "uci.h"

// Baseline search: iterative deepening, principal variation search, a
// transposition table, check extension, and captures-only quiescence search
// with MVV-LVA ordering, killer moves, a history heuristic, null-move pruning,
// late move reductions, late move pruning, futility pruning, SEE pruning in
// quiescence and aspiration windows. Other pruning is left out on purpose: each
// is a separate experiment for the ideas log.

std::atomic<bool> Search::stop{false};

namespace {

using Clock = std::chrono::steady_clock;

constexpr int PieceValue[7] = {100, 320, 330, 500, 900, 0, 0};

// Late move reduction in plies, by depth and move number (both capped at 63).
struct ReductionTable {
    int r[64][64] = {};
    ReductionTable() {
        for (int d = 1; d < 64; ++d)
            for (int n = 1; n < 64; ++n)
                r[d][n] = int(0.75 + std::log(d) * std::log(n) / 2.25);
    }
};
const ReductionTable Reductions;

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
    Move killers[MAX_PLY + 1][2] = {};
    int history[2][64][64] = {}; // [side to move][from][to], quiet moves only
    Move moveStack[MAX_PLY + 1] = {}; // move played at each ply; MOVE_NONE = null move

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

    bool is_quiet(Move m) const {
        return pos.piece_on(to_sq(m)) == NO_PIECE && move_type(m) != EN_PASSANT && move_type(m) != PROMOTION;
    }

    // Assigns each move an ordering score, best first.
    void score_moves(MoveList& list, int* scores, Move ttMove, int ply) {
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
            else if (ply >= 0 && m == killers[ply][0])
                scores[i] = 80'000;
            else if (ply >= 0 && m == killers[ply][1])
                scores[i] = 70'000;
            else if (ply >= 0)
                scores[i] = history[pos.side_to_move()][from_sq(m)][to_sq(m)];
            else
                scores[i] = 0;
        }
    }

    // Moves the entry toward +/-MaxHistory so it never leaves the quiet band
    // of the move ordering (below killers at 70,000).
    void update_history(Move m, int bonus) {
        constexpr int MaxHistory = 16384;
        int& h = history[pos.side_to_move()][from_sq(m)][to_sq(m)];
        h += bonus - h * std::abs(bonus) / MaxHistory;
    }

    // Static exchange evaluation: does capturing on the target square, with
    // both sides then recapturing with their least valuable attacker, gain at
    // least `threshold`? Castling, en passant and promotions count as even.
    bool see_ge(Move m, int threshold) const {
        static constexpr int SeeValue[6] = {100, 320, 330, 500, 900, 20000};
        if (move_type(m) != NORMAL)
            return 0 >= threshold;

        Square from = from_sq(m), to = to_sq(m);
        Piece victim = pos.piece_on(to);
        int swap = (victim == NO_PIECE ? 0 : SeeValue[type_of(victim)]) - threshold;
        if (swap < 0)
            return false;
        swap = SeeValue[type_of(pos.piece_on(from))] - swap;
        if (swap <= 0)
            return true;

        Bitboard occ = pos.pieces() ^ square_bb(from) ^ square_bb(to);
        Bitboard bishops = pos.pieces(BISHOP) | pos.pieces(QUEEN);
        Bitboard rooks = pos.pieces(ROOK) | pos.pieces(QUEEN);
        Bitboard attackers = (PawnAttacks[BLACK][to] & pos.pieces(WHITE, PAWN))
                           | (PawnAttacks[WHITE][to] & pos.pieces(BLACK, PAWN))
                           | (KnightAttacks[to] & pos.pieces(KNIGHT))
                           | (KingAttacks[to] & pos.pieces(KING))
                           | (bishop_attacks(to, occ) & bishops)
                           | (rook_attacks(to, occ) & rooks);
        Color stm = color_of(pos.piece_on(from));
        bool result = true;
        while (true) {
            stm = ~stm;
            attackers &= occ;
            Bitboard ours = attackers & pos.pieces(stm);
            if (!ours)
                break;
            result = !result;

            PieceType pt = PAWN;
            while (!(ours & pos.pieces(pt)))
                pt = PieceType(pt + 1);
            if (pt == KING) // the king may only recapture if nothing can take it back
                return (attackers & pos.pieces(~stm)) ? !result : result;
            if ((swap = SeeValue[pt] - swap) < int(result))
                break;
            occ ^= square_bb(lsb(ours & pos.pieces(pt)));
            if (pt == PAWN || pt == BISHOP || pt == QUEEN)
                attackers |= bishop_attacks(to, occ) & bishops;
            if (pt == ROOK || pt == QUEEN)
                attackers |= rook_attacks(to, occ) & rooks;
        }
        return result;
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
        score_moves(list, scores, MOVE_NONE, -1);

        int best = standPat;
        for (int i = 0; i < list.size; ++i) {
            Move m = pick_move(list, scores, i);
            if (!see_ge(m, 0)) // losing captures cannot raise the stand-pat score
                continue;
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

        int staticEval = inCheck ? -VALUE_INF : evaluate(pos);

        // Reverse futility pruning: at shallow null-window nodes, a large
        // static advantage may make the remaining search unnecessary.
        if (!root && !pvNode && !inCheck && depth <= 3
            && pos.rule50() + depth < 100
            && std::abs(beta) < VALUE_MATE_IN_MAX_PLY
            && (pos.pieces(pos.side_to_move()) & ~(pos.pieces(PAWN) | pos.pieces(KING)))) {
            if (std::abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 150 * depth >= beta)
                // A static advantage cannot override stalemate.
                return first_legal_move() == MOVE_NONE ? 0 : staticEval;
        }

        // Null-move pruning: if passing the turn still fails high, a real move
        // almost surely would too. Skipped in check, without pieces (zugzwang)
        // and right after another null move.
        Color us = pos.side_to_move();
        bool hasPieces = pos.pieces(us) & ~pos.pieces(PAWN) & ~pos.pieces(KING);
        if (!pvNode && !inCheck && !root && depth >= 3 && hasPieces && moveStack[ply - 1] != MOVE_NONE
            && staticEval >= beta) {
            int R = 3 + depth / 6;
            moveStack[ply] = MOVE_NONE;
            pos.do_null_move();
            int score = -search(-beta, -beta + 1, depth - 1 - R, ply + 1);
            pos.undo_null_move();
            if (stopped)
                return 0;
            if (score >= beta)
                return score >= VALUE_MATE_IN_MAX_PLY ? beta : score;
        }

        MoveList list;
        generate(pos, list, ALL_MOVES);
        int scores[256];
        score_moves(list, scores, ttMove, ply);

        int originalAlpha = alpha;
        int best = -VALUE_INF;
        Move bestMove = MOVE_NONE;
        int legalMoves = 0;
        Move quietsTried[256];
        int quietCount = 0;

        for (int i = 0; i < list.size; ++i) {
            Move m = pick_move(list, scores, i);
            bool quiet = is_quiet(m);

            // Late move pruning: near the leaves, quiet moves this far down
            // the ordering almost never matter, so skip them once a move has
            // kept us out of a mate score.
            if (!pvNode && !inCheck && quiet && depth <= 8 && best > -VALUE_MATE_IN_MAX_PLY
                && quietCount >= 3 + depth * depth)
                continue;

            // Futility pruning: if even a generous margin over the static
            // eval cannot reach alpha, a quiet move will not either.
            if (!pvNode && !inCheck && quiet && depth <= 6 && best > -VALUE_MATE_IN_MAX_PLY
                && staticEval + 120 * depth <= alpha)
                continue;
            if (!pos.do_move(m)) {
                pos.undo_move(m);
                continue;
            }
            ++legalMoves;
            moveStack[ply] = m;

            int score;
            if (legalMoves == 1)
                score = -search(-beta, -alpha, depth - 1, ply + 1);
            else {
                // Late quiet moves are searched shallower first, and only
                // re-searched at full depth if they beat alpha.
                int r = 0;
                if (depth >= 3 && legalMoves > 3 && quiet && !inCheck && !pos.in_check()) {
                    r = Reductions.r[std::min(depth, 63)][std::min(legalMoves, 63)];
                    if (pvNode)
                        --r;
                    r = std::clamp(r, 0, depth - 2);
                }
                score = -search(-alpha - 1, -alpha, depth - 1 - r, ply + 1);
                if (score > alpha && r > 0)
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
                    if (score >= beta) {
                        if (quiet) {
                            if (m != killers[ply][0]) {
                                killers[ply][1] = killers[ply][0];
                                killers[ply][0] = m;
                            }
                            int bonus = std::min(depth * depth, 1200);
                            update_history(m, bonus);
                            for (int j = 0; j < quietCount; ++j)
                                update_history(quietsTried[j], -bonus);
                        }
                        break;
                    }
                }
            }
            if (quiet)
                quietsTried[quietCount++] = m;
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
    TT.new_search();
    Searcher s(pos, limits);
    s.set_time_limits();
    SearchResult result;

    for (int depth = 1; depth <= std::min(limits.depth, MAX_PLY - 1); ++depth) {
        // Aspiration windows: search a narrow window around the last score and
        // widen whichever side fails until the score lands inside it.
        int delta = 25;
        int alpha = -VALUE_INF, beta = VALUE_INF;
        if (depth >= 5) {
            alpha = std::max(result.score - delta, -VALUE_INF);
            beta = std::min(result.score + delta, int(VALUE_INF));
        }
        int score;
        while (true) {
            score = s.search(alpha, beta, depth, 0);
            if (s.stopped)
                break;
            if (score <= alpha)
                alpha = std::max(score - delta, -VALUE_INF);
            else if (score >= beta)
                beta = std::min(score + delta, int(VALUE_INF));
            else
                break;
            delta *= 2;
        }
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
