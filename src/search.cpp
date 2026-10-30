#include "search.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <sstream>
#include <thread>
#include <vector>

#include "eval.h"
#include "movegen.h"
#include "tt.h"
#include "uci.h"

// Baseline search: iterative deepening, principal variation search, a
// transposition table, check extension, and captures-only quiescence search
// with MVV-LVA ordering, killer moves, a history heuristic, null-move pruning,
// late move reductions, late move pruning, futility pruning, SEE pruning in
// quiescence and aspiration windows. Other pruning is left out on purpose: each
// is a separate experiment for the ideas log. With more than one thread, helper
// threads search the same root and share only the transposition table (Lazy SMP).

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
                r[d][n] = int(0.82 + std::log(d) * std::log(n) / 1.72);
    }
};
const ReductionTable Reductions;

// Correction history (Caissa 2023, then Alexandria and Stockfish): how far the static eval has
// been off from search results in positions with the same pawns and side to move. The main
// thread's table lasts the whole game; helper threads keep their own, fresh for each search.
// Entries are in 1/16 cp, so a correction never exceeds 64 cp.
constexpr int CorrHistSize = 16384;
constexpr int CorrHistLimit = 1024;
int mainCorrHist[2][CorrHistSize];
// Non-pawn correction history (Alexandria, Stockfish): the same idea keyed by one side's
// non-pawn pieces (knights, bishops, rooks, queens and king), one table per keyed colour.
int mainNonPawnCorrHist[2][2][CorrHistSize]; // [side to move][keyed colour][hash]

int pawn_index(const Position& pos) {
    uint64_t h = pos.pieces(WHITE, PAWN) * 0x9E3779B97F4A7C15ull ^ pos.pieces(BLACK, PAWN) * 0xC2B2AE3D27D4EB4Full;
    h ^= h >> 31;
    h *= 0xBF58476D1CE4E5B9ull;
    return int(h >> 50); // top 14 bits: 0 to CorrHistSize - 1
}

int nonpawn_index(const Position& pos, Color c) {
    uint64_t h = (pos.pieces(c) & ~pos.pieces(PAWN)) * 0x9E3779B97F4A7C15ull;
    h ^= pos.pieces(c, KNIGHT) * 0xD6E8FEB86659FD93ull ^ pos.pieces(c, BISHOP) * 0xC2B2AE3D27D4EB4Full
       ^ pos.pieces(c, ROOK) * 0x165667B19E3779F9ull ^ pos.pieces(c, QUEEN) * 0x27D4EB2F165667C5ull;
    h ^= h >> 31;
    h *= 0xBF58476D1CE4E5B9ull;
    h ^= h >> 29;
    return int(h >> 50);
}

int threadCount = 1; // the UCI Threads option

struct Searcher {
    Position& pos;
    SearchLimits limits;
    Clock::time_point start = Clock::now();
    int64_t softLimit = 0; // stop deepening after this many ms (0 = none)
    int64_t hardLimit = 0; // abort the search after this many ms (0 = none)
    int64_t baseSoft = 0;  // the soft limit before stability scaling (0 = no clock)
    uint64_t nodes = 0;
    bool stopped = false;
    // Helper threads only: set by the main thread to stop them, and their node
    // count so far, for the main thread's info lines.
    const std::atomic<bool>* abort = nullptr;
    std::atomic<uint64_t> sharedNodes{0};

    Move pv[MAX_PLY + 1][MAX_PLY + 1];
    int pvLength[MAX_PLY + 1];
    Move killers[MAX_PLY + 1][2] = {};
    int history[2][64][64] = {}; // [side to move][from][to], quiet moves only
    int ownCorrHist[2][CorrHistSize] = {};
    int (*corrHist)[CorrHistSize] = ownCorrHist; // the main thread's points to mainCorrHist
    int ownNonPawnCorrHist[2][2][CorrHistSize] = {};
    int (*nonPawnCorrHist)[2][CorrHistSize] = ownNonPawnCorrHist; // main thread: mainNonPawnCorrHist
    Move moveStack[MAX_PLY + 1] = {}; // move played at each ply; MOVE_NONE = null move
    Move excluded[MAX_PLY + 1] = {};  // move a singular search leaves out at each ply
    int rootDepth = 0;

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
            // At least 1 ms each: 0 means "no limit", which with a nearly empty clock and no
            // increment would search until told to stop.
            baseSoft = softLimit = std::max<int64_t>(1, std::min(available, available / movesToGo + limits.inc[us] * 3 / 4));
            hardLimit = std::min(available, softLimit * 3);
        }
    }

    void check_limits() {
        if ((nodes & 1023) != 0)
            return;
        if (abort) { // a helper: the main thread keeps the clock and the node limit
            sharedNodes.store(nodes, std::memory_order_relaxed);
            if (abort->load(std::memory_order_relaxed))
                stopped = true;
            return;
        }
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
            else if (pos.piece_on(to_sq(m)) != NO_PIECE) {
                // In the main search, captures that lose material by SEE go
                // after the quiet moves (whose history scores are above -16,384).
                int mvvLva = PieceValue[type_of(pos.piece_on(to_sq(m)))] * 10 - type_of(pos.piece_on(from_sq(m)));
                scores[i] = (ply >= 0 && !see_ge(m, 0) ? -100'000 : 100'000) + mvvLva;
            }
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

    // The network's eval plus what correction history has learned for these pawns.
    int corrected_eval() {
        Color us = pos.side_to_move();
        int nonPawn = nonPawnCorrHist[us][WHITE][nonpawn_index(pos, WHITE)]
                    + nonPawnCorrHist[us][BLACK][nonpawn_index(pos, BLACK)];
        int correction = (corrHist[us][pawn_index(pos)] + nonPawn / 2) / 16;
        return std::clamp(evaluate(pos) + correction, -VALUE_MATE_IN_MAX_PLY + 1, VALUE_MATE_IN_MAX_PLY - 1);
    }

    // Moves the entry toward the search result, more for deeper searches; the gravity term
    // keeps it within +/-CorrHistLimit.
    void update_corrhist(int diff, int depth) {
        int& e = corrHist[pos.side_to_move()][pawn_index(pos)];
        int bonus = std::clamp(diff * depth / 4, -CorrHistLimit / 4, CorrHistLimit / 4);
        e += bonus - e * std::abs(bonus) / CorrHistLimit;
        for (Color c : {WHITE, BLACK}) {
            int& n = nonPawnCorrHist[pos.side_to_move()][c][nonpawn_index(pos, c)];
            n += bonus - n * std::abs(bonus) / CorrHistLimit;
        }
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

        int standPat = corrected_eval();
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

        // A singular search (one move excluded) neither reads nor writes this node's TT entry.
        Move excludedMove = excluded[ply];
        const TTEntry* tte = excludedMove ? nullptr : TT.probe(pos.key());
        Move ttMove = tte ? tte->move : MOVE_NONE;
        int ttScore = tte ? score_from_tt(tte->score, ply) : 0;
        int ttDepth = tte ? tte->depth : -1;
        Bound ttBound = tte ? Bound(tte->bound) : BOUND_NONE;
        if (tte && !pvNode && ttDepth >= depth) {
            if (ttBound == BOUND_EXACT
                || (ttBound == BOUND_LOWER && ttScore >= beta)
                || (ttBound == BOUND_UPPER && ttScore <= alpha))
                return ttScore;
        }

        int staticEval = inCheck ? -VALUE_INF : corrected_eval();

        // Reverse futility pruning: at shallow null-window nodes, a large
        // static advantage may make the remaining search unnecessary.
        if (!root && !pvNode && !inCheck && !excludedMove && depth <= 5
            && pos.rule50() + depth < 100
            && std::abs(beta) < VALUE_MATE_IN_MAX_PLY
            && (pos.pieces(pos.side_to_move()) & ~(pos.pieces(PAWN) | pos.pieces(KING)))) {
            if (std::abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 77 * depth >= beta)
                // A static advantage cannot override stalemate.
                return has_legal_move() ? staticEval : 0;
        }

        // Null-move pruning: if passing the turn still fails high, a real move
        // almost surely would too. Skipped in check, without pieces (zugzwang)
        // and right after another null move.
        Color us = pos.side_to_move();
        bool hasPieces = pos.pieces(us) & ~pos.pieces(PAWN) & ~pos.pieces(KING);
        if (!pvNode && !inCheck && !root && !excludedMove && depth >= 3 && hasPieces && moveStack[ply - 1] != MOVE_NONE
            && staticEval >= beta) {
            int R = 3 + depth / 4;
            moveStack[ply] = MOVE_NONE;
            pos.do_null_move();
            int score = -search(-beta, -beta + 1, depth - 1 - R, ply + 1);
            pos.undo_null_move();
            if (stopped)
                return 0;
            if (score >= beta)
                return score >= VALUE_MATE_IN_MAX_PLY ? beta : score;
        }

        // Internal iterative reductions: with no TT move the ordering here is
        // poor, so search one ply shallower. Skipped in a singular search
        // (a move excluded): there the TT is not probed, so ttMove is always
        // none and the verification depth must stay as the caller set it.
        if (!root && !excludedMove && depth >= 4 && ttMove == MOVE_NONE)
            --depth;

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
            if (m == excludedMove)
                continue;
            bool quiet = is_quiet(m);

            // Late move pruning: near the leaves, quiet moves this far down
            // the ordering almost never matter, so skip them once a move has
            // kept us out of a mate score.
            if (!pvNode && !inCheck && quiet && depth <= 7 && best > -VALUE_MATE_IN_MAX_PLY
                && quietCount >= 6 + depth * depth)
                continue;

            // Futility pruning: if even a generous margin over the static
            // eval cannot reach alpha, a quiet move will not either.
            if (!pvNode && !inCheck && quiet && depth <= 6 && best > -VALUE_MATE_IN_MAX_PLY
                && staticEval + 127 * depth <= alpha)
                continue;

            // SEE pruning: near the leaves, skip a move that loses more material in the exchange
            // on its target square than a depth-scaled margin (wider for captures).
            if (!root && !inCheck && depth <= 6 && best > -VALUE_MATE_IN_MAX_PLY
                && !see_ge(m, quiet ? -60 * depth : -30 * depth * depth))
                continue;

            // Singular extension: when a reduced search without the TT move cannot get near
            // its TT score, that move is the only good one here, so search it a ply deeper.
            // When even the reduced search beats beta, several moves do: cut (multi-cut).
            int extension = 0;
            if (!root && m == ttMove && depth >= 8 && ttDepth >= depth - 3 && ttBound != BOUND_UPPER
                && std::abs(ttScore) < VALUE_MATE_IN_MAX_PLY && ply < 2 * rootDepth) {
                int singularBeta = ttScore - depth;
                excluded[ply] = m;
                int singularScore = search(singularBeta - 1, singularBeta, (depth - 1) / 2, ply);
                excluded[ply] = MOVE_NONE;
                if (stopped)
                    return 0;
                if (singularScore < singularBeta)
                    extension = 1;
                else if (singularBeta >= beta)
                    return singularBeta;
            }

            if (!pos.do_move(m)) {
                pos.undo_move(m);
                continue;
            }
            ++legalMoves;
            moveStack[ply] = m;

            int newDepth = depth - 1 + extension;
            int score;
            if (legalMoves == 1)
                score = -search(-beta, -alpha, newDepth, ply + 1);
            else {
                // Late quiet moves are searched shallower first, and only
                // re-searched at full depth if they beat alpha.
                int r = 0;
                if (depth >= 3 && legalMoves > 4 && quiet && !inCheck && !pos.in_check()) {
                    r = Reductions.r[std::min(depth, 63)][std::min(legalMoves, 63)];
                    if (pvNode)
                        --r;
                    r = std::clamp(r, 0, depth - 2);
                }
                score = -search(-alpha - 1, -alpha, newDepth - r, ply + 1);
                if (score > alpha && r > 0)
                    score = -search(-alpha - 1, -alpha, newDepth, ply + 1);
                if (score > alpha && score < beta)
                    score = -search(-beta, -alpha, newDepth, ply + 1);
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
                            int bonus = std::min(depth * depth, 1239);
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

        if (legalMoves == 0) // with a move excluded, the excluded move was the only legal one
            return excludedMove ? alpha : inCheck ? -VALUE_MATE + ply : 0;

        Bound bound = best >= beta ? BOUND_LOWER : alpha > originalAlpha ? BOUND_EXACT : BOUND_UPPER;
        // A search with a move excluded (the singular test) is not this position's result, so neither
        // the table nor the correction history learns from it.
        if (!excludedMove) {
            // Learn from the gap between search and static eval when it is trustworthy: not in
            // check, no capture as the best move, and a bound that points away from the eval.
            if (!inCheck && (bestMove == MOVE_NONE || is_quiet(bestMove)) && std::abs(best) < VALUE_MATE_IN_MAX_PLY
                && !(bound == BOUND_LOWER && best <= staticEval) && !(bound == BOUND_UPPER && best >= staticEval))
                update_corrhist(best - staticEval, depth);
            TT.store(pos.key(), bestMove, score_to_tt(best, ply), depth, bound);
        }
        return best;
    }

    // One iteration from the root. Aspiration windows: search a narrow window
    // around the last score and widen whichever side fails until the score
    // lands inside it.
    int search_root(int depth, int prevScore) {
        int delta = 22;
        int alpha = -VALUE_INF, beta = VALUE_INF;
        if (depth >= 4) {
            alpha = std::max(prevScore - delta, -VALUE_INF);
            beta = std::min(prevScore + delta, int(VALUE_INF));
        }
        while (true) {
            int score = search(alpha, beta, depth, 0);
            if (stopped)
                return score;
            if (score <= alpha)
                alpha = std::max(score - delta, -VALUE_INF);
            else if (score >= beta)
                beta = std::min(score + delta, int(VALUE_INF));
            else
                return score;
            delta *= 2;
        }
    }

    // A helper thread's search: the main thread's iterative deepening, with no
    // output and no clock. It helps only through what it leaves in the TT.
    void helper_search(int maxDepth) {
        int score = 0;
        for (int depth = 1; depth <= maxDepth; ++depth) {
            rootDepth = depth;
            int s = search_root(depth, score);
            if (stopped)
                return;
            score = s;
        }
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

    // Whether the side to move, not in check, has a legal move. A piece on no line through its own
    // king cannot be pinned, so when not in check any move it has is legal; most positions have one,
    // which spares generating every move. Otherwise (and for en passant) try the moves.
    bool has_legal_move() {
        Color us = pos.side_to_move();
        Square k = pos.king_square(us);
        Bitboard own = pos.pieces(us), occ = pos.pieces();
        for (Bitboard b = own & ~pos.pieces(KING); b;) {
            Square s = pop_lsb(b);
            int df = file_of(s) - file_of(k), dr = rank_of(s) - rank_of(k);
            if (df == 0 || dr == 0 || df == dr || df == -dr)
                continue;
            Bitboard targets;
            switch (type_of(pos.piece_on(s))) {
            case PAWN: {
                Square push = us == WHITE ? s + 8 : s - 8; // pawns never stand on the last rank
                targets = (PawnAttacks[us][s] & pos.pieces(~us)) | (pos.piece_on(push) == NO_PIECE ? square_bb(push) : 0);
                break;
            }
            case KNIGHT: targets = KnightAttacks[s] & ~own; break;
            case BISHOP: targets = bishop_attacks(s, occ) & ~own; break;
            case ROOK: targets = rook_attacks(s, occ) & ~own; break;
            default: targets = queen_attacks(s, occ) & ~own; break;
            }
            if (targets)
                return true;
        }
        return first_legal_move() != MOVE_NONE;
    }
};

} // namespace

void Search::clear() {
    TT.clear();
    std::fill(&mainCorrHist[0][0], &mainCorrHist[0][0] + 2 * CorrHistSize, 0);
    std::fill(&mainNonPawnCorrHist[0][0][0], &mainNonPawnCorrHist[0][0][0] + 4 * CorrHistSize, 0);
}

void Search::set_threads(int n) {
    threadCount = std::max(1, n);
}

SearchResult Search::think(Position& pos, const SearchLimits& limits, bool verbose) {
    TT.new_search();
    Searcher s(pos, limits);
    s.corrHist = mainCorrHist;
    s.nonPawnCorrHist = mainNonPawnCorrHist;
    s.set_time_limits();
    SearchResult result;
    int maxDepth = std::min(limits.depth, MAX_PLY - 1);

    // Soft-limit scale by how many iterations in a row the best move has held (after Stash).
    constexpr double StabilityScale[5] = {2.50, 1.20, 0.90, 0.80, 0.75};
    int stability = 0;
    Move prevBest = MOVE_NONE;

    // Helper threads, each with its own copy of the position and its own
    // history and killers, until the main thread stops them.
    std::atomic<bool> stopHelpers{false};
    std::vector<std::unique_ptr<Position>> helperPositions;
    std::vector<std::unique_ptr<Searcher>> helpers;
    std::vector<std::thread> helperThreads;
    for (int i = 1; i < threadCount; ++i) {
        helperPositions.push_back(std::make_unique<Position>(pos));
        helpers.push_back(std::make_unique<Searcher>(*helperPositions.back(), SearchLimits{}));
        helpers.back()->abort = &stopHelpers;
        helperThreads.emplace_back([h = helpers.back().get(), maxDepth] { h->helper_search(maxDepth); });
    }
    auto totalNodes = [&] {
        uint64_t n = s.nodes;
        for (const auto& h : helpers)
            n += h->sharedNodes.load(std::memory_order_relaxed);
        return n;
    };

    for (int depth = 1; depth <= maxDepth; ++depth) {
        s.rootDepth = depth;
        int score = s.search_root(depth, result.score);
        if (s.stopped)
            break;

        int prevScore = result.score;
        if (s.pvLength[0] > 0)
            result.best = s.pv[0][0];
        result.score = score;

        if (verbose) {
            int64_t ms = s.elapsed();
            std::ostringstream info;
            uint64_t nodes = totalNodes();
            info << "info depth " << depth << " score " << s.score_string(score) << " nodes " << nodes
                 << " nps " << nodes * 1000 / (ms + 1) << " time " << ms << " pv";
            for (int i = 0; i < s.pvLength[0]; ++i)
                info << " " << move_to_uci(s.pv[0][i]);
            UCI::send(info.str());
        }

        // Stop sooner when the best move keeps holding and the score is not falling; take
        // longer while either changes. The hard limit still caps the soft one.
        if (s.baseSoft) {
            stability = result.best == prevBest ? std::min(stability + 1, 4) : 0;
            prevBest = result.best;
            double scale = StabilityScale[stability];
            if (depth > 1) // a 100 cp drop doubles the time, a 100 cp rise halves it
                scale *= std::exp2(std::clamp(prevScore - score, -100, 100) / 100.0);
            s.softLimit = std::max<int64_t>(1, std::min(s.hardLimit, int64_t(double(s.baseSoft) * scale)));
        }

        if (s.softLimit && s.elapsed() >= s.softLimit)
            break;
    }

    // "go infinite" must not report a move until told to stop.
    while (limits.infinite && !Search::stop)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));

    stopHelpers = true;
    for (std::thread& t : helperThreads)
        t.join();

    if (result.best == MOVE_NONE)
        result.best = s.first_legal_move();
    result.nodes = s.nodes;
    for (const auto& h : helpers)
        result.nodes += h->nodes;
    return result;
}
