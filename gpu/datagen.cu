// ChessSI's self-play data generation on the GPU (issue #31, stage 2): a line-by-line port of the
// search in src/search.cpp, the move generator in src/movegen.cpp (same move order), do_move /
// undo_move with the same Zobrist keys (src/position.cpp), and the game loop of src/datagen.cpp.
// The aim is the same output as the CPU for the same start positions, checked with gpu/ref.cpp.
//
// One game per warp. All 32 lanes run the same scalar code in lockstep on one copy of the game in
// global memory (same-address reads are broadcast and same-value writes merge), except the NNUE work:
// each lane owns H / 32 hidden units of both perspectives. Every launch plays one ply of every game,
// which keeps kernels well under the Windows GPU watchdog. Compiled at run time with NVRTC.
//
// The search is not recursive: a recursive call saves every lane's registers at each level, 32 copies
// of what is one set of values. search() runs the calls of src/search.cpp's search and qsearch from
// an explicit stack of frames, one copy per game (see Frame), which made data generation 32% faster.

typedef unsigned long long u64;
typedef unsigned short u16;
typedef unsigned char u8;

#define MAX_PLY 128
#define VALUE_INF 32001
#define VALUE_MATE 32000
#define VALUE_MATE_IN_MAX_PLY (VALUE_MATE - MAX_PLY)
#define NO_PIECE 12
#define SQ_NONE 64
#define MOVE_NONE 0
#define M_PROMOTION (1 << 14)
#define M_EN_PASSANT (2 << 14)
#define M_CASTLING (3 << 14)
#ifndef H
#define H 256
#endif
#define UNITS (H / 32)
#define QA 255
#define QB 64
#define EVAL_SCALE 400
#define MAX_STATES 768 // a 600-ply match game, the start, and the deepest search (MAX_PLY), with room to spare
#ifndef TT_BITS
#define TT_BITS 16     // 65,536 entries of 16 bytes: 1 MB per game, like gpu/ref.cpp (GPU_TT_BITS sets it)
#endif
#define ACC_SLOTS (MAX_PLY + 2)
#define MAX_SAMPLES 400
#define MAX_PLIES 400
#define WIN_SCORE 2500
#define WIN_PLIES 6

enum { PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING };
enum { WHITE_OO = 1, WHITE_OOO = 2, BLACK_OO = 4, BLACK_OOO = 8 };
enum { BOUND_NONE, BOUND_UPPER, BOUND_LOWER, BOUND_EXACT };

__constant__ u64 Z_PSQ[12][64];
__constant__ u64 Z_CASTLING[16];
__constant__ u64 Z_EP[8];
__constant__ u64 Z_SIDE[1];

// -DPROFILE: clock64() cycles per section, summed by lane 0 into Game::prof. Sections are timed at
// their call sites in the search, so the step total minus the sections is the search's own control.
enum { P_GEN, P_SCORE, P_PICK, P_DO, P_UNDO, P_EVAL, P_TT, P_SEE, P_CHECK, P_DRAW, P_STEP, P_COUNT };
#ifdef PROFILE
#define PB(id) long long _pb##id = clock64();
#define PE(id) if ((threadIdx.x & 31) == 0) g->prof[id] += clock64() - _pb##id;
#else
#define PB(id)
#define PE(id)
#endif

struct StateInfo {
    u64 key;
    int castling, ep, rule50, captured, pliesFromNull, pad;
};
struct TTEntry {
    u64 key;
    u16 move;
    short score;
    signed char depth;
    u8 bound, gen, pad;
};
struct Sample { // one datagen line before formatting: the position, and White-relative score and eval
    u8 board[64];
    u8 stm, castling, ep, pad;
    short rule50, fullmove, score, eval;
    int pad2;
};
// One call of search or qsearch in src/search.cpp: its arguments, the locals that live across a child
// call, and the state to resume in when the child returns. The running call is in registers; the
// calls waiting on it are in Game::frames.
struct Frame {
    int state, alpha, beta, depth, ply;
    int originalAlpha, best, legalMoves, quietCount, staticEval, n, i, r, childScore, ttScore;
    u64 key;
    u16 ttMove, bestMove, m;
    u16 excl; // the move a singular search leaves out (excluded[ply]); MOVE_NONE otherwise
    signed char ttDepth, ext; // the TT entry's depth (-1 without one), and the singular extension of f.m
    u8 ttBound;
    bool inCheck, pvNode, root, quiet, improving;
};

// The search's constants (src/search.cpp has them inline), so that matches can give each side its own.
// gpu/datagen.py fills in src/search.cpp's values.
struct Params {
    int rfpDepth, rfpMargin;       // reverse futility pruning: depth <= 3, staticEval - 150 * depth >= beta
    int nmpDepth, nmpBase, nmpDiv; // null move: depth >= 3, R = 3 + depth / 6
    int nmpEvalDiv, nmpEvalMax;    // null move R += min((staticEval - beta) / nmpEvalDiv, nmpEvalMax) (0: off; nmp-eval: 200, 3)
    int lmpDepth, lmpBase;         // late move pruning: depth <= 8, quietCount >= 3 + depth * depth
    int futDepth, futMargin;       // futility pruning: depth <= 6, staticEval + 120 * depth <= alpha
    int lmrDepth, lmrMoves;        // late move reductions: depth >= 3, legalMoves > 3
    int histMax;                   // history bonus cap (1600 since PR #88)
    int aspDepth, aspDelta;        // aspiration windows from depth 5, delta 25
    int qsSee;                     // quiescence skips captures that fail see_ge(m, 0)
    int seeDepth, seeQuiet, seeCapture; // SEE pruning: depth <= 6, quiets below -60 * depth, captures below -30 * depth^2
    int iirDepth;                  // internal iterative reductions: depth >= 4 with no TT move
    int singDepth, singTTMargin, singBeta; // singular extensions: depth >= 8, ttDepth >= depth - 3, beta ttScore - 16 * depth / 16
    int negExt;                    // 1: a non-singular TT move whose TT score beats beta gets extension -1 (off in the engine)
    int dextMargin, dextLimit;     // extension 2 below singular beta - dextMargin, dextLimit times a path (off: limit 0)
    int contHist;                  // 1: continuation history in quiet-move order (#81; 0: PR #78)
    int lmpImproving, rfpImproving; // 1: LMP keeps half the quiets when not improving; RFP's margin a ply smaller when improving
    int lmrImproving;              // 1: LMR reduces one ply more when not improving
    int histPruneDepth, histPruneMargin; // history pruning: quiets scored below -margin * depth, depth <= (0: off)
    int qsDelta;                   // delta pruning: quiescence skips captures that miss alpha by more than this over the victim (0: off)
    int histMul;                   // history bonus min(histMul * depth * depth, histMax) (1: the engine)
    int histLin, histOff;          // if histLin: the bonus is min(histLin * depth - histOff, histMax) instead (PR #88: 300, 250)
    u8 lmr[64][64];                // the reduction: int(0.75 + log(depth) * log(moves) / 2.25)
};

// Correction history (src/search.cpp): per side to move and pawn structure, and per side to move and
// each colour's non-pawn pieces, in 1/16 cp.
#define CORR_SIZE 16384
#define CORR_LIMIT 1024
#define CH_BLOCKS (12 * 64 * 12 * 64 / 8) // continuation history in 16-byte blocks of 8 entries
#define CH_WORDS (CH_BLOCKS / 32)          // the blocks' marks, 32 to a word (see Tables::chMask)
// What one engine keeps from move to move, and Search::clear() empties: the TT with its generation, and
// the main thread's correction histories (int in the engine; their values stay within +-CORR_LIMIT). Each
// game has one; in a match each side has its own, as two engines would.
struct Tables {
    TTEntry tt[1 << TT_BITS];
    short corr[2][CORR_SIZE];
    short npcorr[2][2][CORR_SIZE]; // [side to move][keyed colour][hash]
    // Continuation history (the engine's mainContHist, an int table whose gravity keeps it within +-16384):
    // [earlier piece * 64 + its target][piece * 64 + target], kept for the game and halved at each search
    short conthist[12 * 64][12 * 64];
    // One bit per 16-byte block of conthist (8 entries), set whenever an entry of the block is written and
    // cleared when halving leaves the block all zero. Every non-zero entry's block is marked, so the
    // halving before each search can skip the rest: halving zero is a no-op, so the values are the same.
    unsigned chMask[CH_WORDS];
    unsigned gen, pad[3]; // TT.new_search() at each search; entries keep its low 8 bits, as the engine's uint8_t
};

struct Game {
    // Position (src/position.h)
    u64 byType[6], byColor[2];
    u8 board[64];
    int stm, fullmove, nstates, accTop;
    StateInfo states[MAX_STATES];
    // Search (struct Searcher in src/search.cpp); only pv[0][0] and pvLength[0] > 0 are ever read
    u64 nodes, nodeLimit;
    int stopped, rootPv;
    u16 rootBest, pad16;
    // A move's search between kernel launches (think_run): the running call and the loops of
    // Search::think and search_root, with the side to move at the root and its static eval
    Frame cur;
    int sp, thinkState, thinkDepth, thinkScore, aspAlpha, aspBeta, aspDelta, rootStm, rootEval;
    u16 thinkBest, pad17;
    u16 killers[MAX_PLY + 1][2];
    u16 moveStack[MAX_PLY + 1];
    u8 pieceStack[MAX_PLY + 1]; // the piece that played moveStack[ply], for continuation history
    int evalStack[MAX_PLY + 1]; // each ply's static eval (-VALUE_INF in check), for "improving"
    signed char doubleExt[MAX_PLY + 2]; // double extensions on the path to each ply
    int history[2][64][64];
    // A singular search runs at its parent's ply while the parent waits, so each ply has two slots for
    // the calls in flight and their moves: [ply] for ordinary calls, [MAX_PLY + 1 + ply] for singular ones.
    Frame frames[2 * (MAX_PLY + 1)];
    u16 moves[2 * (MAX_PLY + 1)][256];
    int scores[2 * (MAX_PLY + 1)][256]; // move order (see score_moves)
    u16 quiets[2 * (MAX_PLY + 1)][256];
    // Game loop (src/datagen.cpp)
    int winStreak, ply, done, nsamples;
    float result;
    int lastScore, lastNodes;
    u16 lastBest, pad3;
    Sample samples[MAX_SAMPLES];
    int plyBest[MAX_PLIES], plyScore[MAX_PLIES], plyNodes[MAX_PLIES];
    long long prof[P_COUNT];
    // Match play (match_step): which color network A has, and the adjudication counters
    int aColor, resignPlies, drawPlies, matchResult; // matchResult: -1 playing, 0 Black won, 1 draw, 2 White won
};
struct Net {
    const short *ftw, *ftb, *outw;
    int outb;
};


#define NOT_A 0xFEFEFEFEFEFEFEFEULL
#define NOT_AB 0xFCFCFCFCFCFCFCFCULL
#define NOT_H 0x7F7F7F7F7F7F7F7FULL
#define NOT_GH 0x3F3F3F3F3F3F3F3FULL

__device__ __forceinline__ u64 bit(int s) { return 1ULL << s; }
__device__ __forceinline__ int lsb(u64 b) { return __ffsll((long long)b) - 1; }
__device__ __forceinline__ int lane_id() { return threadIdx.x & 31; }

// Attacks: hyperbola quintessence with a full bit reversal for sliders, shifts for the rest.
__device__ __forceinline__ u64 line_attacks(u64 occ, u64 mask, int s) {
    u64 b = bit(s), f = occ & mask, r = __brevll(f);
    f -= b;
    r -= __brevll(b);
    f ^= __brevll(r);
    return f & mask;
}
__device__ __forceinline__ u64 file_mask(int s) { return (0x0101010101010101ULL << (s & 7)) ^ bit(s); }
__device__ __forceinline__ u64 rank_mask(int s) { return (0xFFULL << (s & 56)) ^ bit(s); }
__device__ __forceinline__ u64 diag_mask_calc(int s) {
    int d = (s >> 3) - (s & 7);
    u64 m = 0x8040201008040201ULL;
    return (d >= 0 ? m << (8 * d) : m >> (-8 * d)) ^ bit(s);
}
__device__ __forceinline__ u64 anti_mask_calc(int s) {
    int d = (s >> 3) + (s & 7) - 7;
    u64 m = 0x0102040810204080ULL;
    return (d >= 0 ? m << (8 * d) : m >> (-8 * d)) ^ bit(s);
}
// Single squares' attack sets and line masks: computed (ATTACK_CALC), or one load from tables that
// attack_tables_init fills with the computed values (6 to 16 instructions each otherwise).
__device__ __forceinline__ u64 knight_att(u64 b);
__device__ __forceinline__ u64 king_att(u64 b);
__device__ __forceinline__ u64 pawn_att_calc(int s, int c);
__device__ __forceinline__ u64 line_mask_calc(int kind, int s);
#ifdef ATTACK_CALC
__device__ __forceinline__ u64 diag_mask(int s) { return diag_mask_calc(s); }
__device__ __forceinline__ u64 anti_mask(int s) { return anti_mask_calc(s); }
__device__ __forceinline__ u64 knight_sq(int s) { return knight_att(bit(s)); }
__device__ __forceinline__ u64 king_att_sq(int s) { return king_att(bit(s)); }
__device__ __forceinline__ u64 pawn_att(int s, int c) { return pawn_att_calc(s, c); }
__device__ __forceinline__ u64 line_mask(int kind, int s) { return line_mask_calc(kind, s); }
#else
__device__ u64 T_KNIGHT[64], T_KING[64], T_PAWN[2][64], T_LINE[5][64]; // T_LINE[kind]: line_mask's kinds 1-4
__device__ __forceinline__ u64 diag_mask(int s) { return __ldg(&T_LINE[3][s]); }
__device__ __forceinline__ u64 anti_mask(int s) { return __ldg(&T_LINE[4][s]); }
__device__ __forceinline__ u64 knight_sq(int s) { return __ldg(&T_KNIGHT[s]); }
__device__ __forceinline__ u64 king_att_sq(int s) { return __ldg(&T_KING[s]); }
__device__ __forceinline__ u64 pawn_att(int s, int c) { return __ldg(&T_PAWN[c][s]); }
__device__ __forceinline__ u64 line_mask(int kind, int s) { return __ldg(&T_LINE[kind][s]); }
#endif
__device__ __forceinline__ u64 rook_att(int s, u64 occ) { return line_attacks(occ, file_mask(s), s) | line_attacks(occ, rank_mask(s), s); }
__device__ __forceinline__ u64 bishop_att(int s, u64 occ) { return line_attacks(occ, diag_mask(s), s) | line_attacks(occ, anti_mask(s), s); }
__device__ __forceinline__ u64 knight_att(u64 b) {
    return ((b << 17) & NOT_A) | ((b << 15) & NOT_H) | ((b << 10) & NOT_AB) | ((b << 6) & NOT_GH)
         | ((b >> 17) & NOT_H) | ((b >> 15) & NOT_A) | ((b >> 10) & NOT_GH) | ((b >> 6) & NOT_AB);
}
__device__ __forceinline__ u64 king_att(u64 b) {
    u64 lr = ((b << 1) & NOT_A) | ((b >> 1) & NOT_H), row = b | lr;
    return lr | (row << 8) | (row >> 8);
}
// PawnAttacks[c][s] in src/bitboard: squares a pawn of color c on s attacks.
__device__ __forceinline__ u64 pawn_att_calc(int s, int c) {
    u64 b = bit(s);
    return c == 0 ? ((b << 9) & NOT_A) | ((b << 7) & NOT_H) : ((b >> 7) & NOT_A) | ((b >> 9) & NOT_H);
}
__device__ __forceinline__ u64 attacks_bb(int pt, int s, u64 occ) {
    switch (pt) {
        case KNIGHT: return knight_sq(s);
        case BISHOP: return bishop_att(s, occ);
        case ROOK: return rook_att(s, occ);
        case QUEEN: return bishop_att(s, occ) | rook_att(s, occ);
        default: return king_att_sq(s);
    }
}

// ---- Position ----
__device__ __forceinline__ int type_of(int p) { return p % 6; }
__device__ __forceinline__ int color_of(int p) { return p / 6; }
__device__ __forceinline__ u64 occupied(const Game* g) { return g->byColor[0] | g->byColor[1]; }
__device__ __forceinline__ u64 pcs(const Game* g, int c, int t) { return g->byColor[c] & g->byType[t]; }
__device__ __forceinline__ StateInfo* state(Game* g) { return &g->states[g->nstates - 1]; }
__device__ __forceinline__ int king_sq(const Game* g, int c) { return lsb(pcs(g, c, KING)); }
__device__ __forceinline__ int castling_mask(int s) {
    return s == 0 ? 15 & ~WHITE_OOO : s == 7 ? 15 & ~WHITE_OO : s == 4 ? 15 & ~(WHITE_OO | WHITE_OOO)
         : s == 56 ? 15 & ~BLACK_OOO : s == 63 ? 15 & ~BLACK_OO : s == 60 ? 15 & ~(BLACK_OO | BLACK_OOO) : 15;
}

__device__ bool attacked(const Game* g, int s, int by) {
    u64 occ = occupied(g);
    return (pawn_att(s, by ^ 1) & pcs(g, by, PAWN)) || (knight_sq(s) & pcs(g, by, KNIGHT))
        || (king_att_sq(s) & pcs(g, by, KING))
        || (bishop_att(s, occ) & (pcs(g, by, BISHOP) | pcs(g, by, QUEEN)))
        || (rook_att(s, occ) & (pcs(g, by, ROOK) | pcs(g, by, QUEEN)));
}
__device__ __forceinline__ bool in_check(const Game* g) { return attacked(g, king_sq(g, g->stm), g->stm ^ 1); }

// The line through squares a != b: 1 file, 2 rank, 3 diagonal, 4 anti-diagonal, 0 none.
__device__ __forceinline__ int line_kind(int a, int b) {
    int df = (a & 7) - (b & 7), dr = (a >> 3) - (b >> 3);
    return df == 0 ? 1 : dr == 0 ? 2 : df == dr ? 3 : df == -dr ? 4 : 0;
}
__device__ __forceinline__ u64 line_mask_calc(int kind, int s) {
    return kind == 1 ? file_mask(s) : kind == 2 ? rank_mask(s) : kind == 3 ? diag_mask_calc(s) : anti_mask_calc(s);
}
// Fills the attack tables (one block of 64 threads, a square each); empty with ATTACK_CALC.
extern "C" __global__ void attack_tables_init() {
#ifndef ATTACK_CALC
    int s = threadIdx.x;
    T_KNIGHT[s] = knight_att(bit(s));
    T_KING[s] = king_att(bit(s));
    T_PAWN[0][s] = pawn_att_calc(s, 0);
    T_PAWN[1][s] = pawn_att_calc(s, 1);
    T_LINE[0][s] = 0;
    for (int kind = 1; kind <= 4; ++kind) T_LINE[kind][s] = line_mask_calc(kind, s);
#endif
}
// Color c's sliders that move along lines of this kind.
__device__ __forceinline__ u64 line_sliders(const Game* g, int c, int kind) {
    return g->byColor[c] & (g->byType[QUEEN] | g->byType[kind <= 2 ? ROOK : BISHOP]);
}

// Would the pseudo-legal move m leave the mover's king attacked? Before do_move, so an illegal move is never
// made; inCheck is whether the side to move is in check now. Not in check, a move other than a king move or en
// passant is illegal only when it uncovers the king: `from` on a line through it, `to` off that line, and an
// enemy slider of the line's kind behind `from`. Everything else gets the exact test on the board after the move.
__device__ bool legal(const Game* g, u16 m, bool inCheck) {
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14), us = g->stm, them = us ^ 1, k = king_sq(g, us);
    if (!inCheck && from != k && type != M_EN_PASSANT) {
        int kind = line_kind(from, k);
        if (!kind || line_kind(to, k) == kind) return true;
        u64 mask = line_mask(kind, k), sl = line_sliders(g, them, kind);
        return !(mask & sl) || !(line_attacks(occupied(g) ^ bit(from), mask, k) & sl);
    }
    u64 occ = occupied(g), enemy = g->byColor[them];
    if (type == M_CASTLING) {
        bool kingside = to > from;
        occ ^= bit(from) | bit(to) | bit(kingside ? from + 3 : from - 4) | bit(kingside ? from + 1 : from - 1);
    } else {
        int capSq = type == M_EN_PASSANT ? (us == 0 ? to - 8 : to + 8) : to;
        occ = (occ ^ bit(from) ^ bit(capSq) * (capSq != to)) | bit(to);
        enemy &= ~bit(capSq);
    }
    int s = from == k ? to : k;
    return !((pawn_att(s, us) & enemy & g->byType[PAWN]) || (knight_sq(s) & enemy & g->byType[KNIGHT])
          || (king_att_sq(s) & enemy & g->byType[KING])
          || (bishop_att(s, occ) & enemy & (g->byType[BISHOP] | g->byType[QUEEN]))
          || (rook_att(s, occ) & enemy & (g->byType[ROOK] | g->byType[QUEEN])));
}

// Just after do_move(m): is the side to move in check? Only the piece on `to` can give it directly, and only a
// line through `from` can open; castling and en passant (rook, captured pawn) take in_check.
__device__ bool gives_check(const Game* g, u16 m) {
    int type = m & (3 << 14);
    if (type == M_CASTLING || type == M_EN_PASSANT) return in_check(g);
    int from = m & 63, to = (m >> 6) & 63, mover = g->stm ^ 1, k = king_sq(g, g->stm), pt = type_of(g->board[to]);
    u64 occ = occupied(g);
    if (pt == PAWN) {
        if (pawn_att(to, mover) & bit(k)) return true;
    } else if (pt == KNIGHT) {
        if (knight_sq(to) & bit(k)) return true;
    } else if (pt != KING) {
        int kind = line_kind(to, k);
        if (kind && (pt == QUEEN || (pt == ROOK) == (kind <= 2)) && (line_attacks(occ, line_mask(kind, k), k) & bit(to)))
            return true;
    }
    int kind = line_kind(from, k);
    if (!kind || line_kind(to, k) == kind) return false;
    u64 mask = line_mask(kind, k), sl = line_sliders(g, mover, kind);
    return (mask & sl) && (line_attacks(occ, mask, k) & sl);
}

// ---- NNUE (one warp per game; this lane's units) ----
__device__ __forceinline__ short* acc_slot(short* acc, int slot) { return acc + (size_t)slot * 2 * H; }
__device__ __forceinline__ int feat(int persp, int p, int s) { // White's view, or Black's (colors swapped, ranks flipped)
    return persp == 0 ? p * 64 + s : ((color_of(p) ^ 1) * 6 + type_of(p)) * 64 + (s ^ 56);
}
// A lane's units move in groups of 8 int16 values, one 16-byte load or store each (rows and
// accumulators are 16-byte aligned). __vadd2 and __vsub2 add two int16 values per 32-bit word with
// the same wrap-around as (short)(a + b).
static_assert(UNITS % 8 == 0, "each lane's units must be whole groups of 8");
// Lane l owns the 8-unit groups l, l + 32, l + 64, ...: each group access of the warp is one contiguous 512 bytes,
// at any hidden size (owning H / 32 consecutive units instead measured 3.8% slower at 768 units).
#define LANE_BASE (lane_id() * 8)
#define UOFF(c) (base + (c) * 32)
__device__ __forceinline__ uint4 load8(const short* p) { return *(const uint4*)p; }
__device__ __forceinline__ void store8(short* p, uint4 v) { *(uint4*)p = v; }
__device__ __forceinline__ uint4 add8(uint4 a, uint4 b) {
    return make_uint4(__vadd2(a.x, b.x), __vadd2(a.y, b.y), __vadd2(a.z, b.z), __vadd2(a.w, b.w));
}
__device__ __forceinline__ uint4 sub8(uint4 a, uint4 b) {
    return make_uint4(__vsub2(a.x, b.x), __vsub2(a.y, b.y), __vsub2(a.z, b.z), __vsub2(a.w, b.w));
}

__device__ void refresh(const Game* g, const Net& net, short* a) {
    int base = LANE_BASE;
    for (int persp = 0; persp < 2; ++persp) {
        for (int c = 0; c < UNITS; c += 8) {
            uint4 v = load8(net.ftb + UOFF(c));
            for (u64 b = occupied(g); b; b &= b - 1) {
                int s = lsb(b);
                v = add8(v, load8(net.ftw + (size_t)feat(persp, g->board[s], s) * H + UOFF(c)));
            }
            store8(a + persp * H + UOFF(c), v);
        }
    }
}
// The feature changes of a move, in fixed slots: 0 off and 1 on for the moving piece (1 is the new
// piece for a promotion), 2 off for a capture or castling's rook, 3 on for the rook. Fixed slots keep
// the indices compile-time constants, so the struct stays in registers.
struct Delta {
    int n;
    int piece[4], sq[4];
};
// net.ftw holds 768 rows of feature weights and then the same rows negated (feature_rows in datagen.py): a removed
// feature (slots 0 and 2) adds its negated row, one 16x2 add per word where a subtraction takes three on sm_120.
#ifndef NO_NEG_ROWS
#define OFF_ROW(k) ((k) % 2 ? 0 : 768)
#endif
__device__ void apply_delta(const Net& net, const short* from, short* to, const Delta& d) {
    int base = LANE_BASE;
#ifndef JOINT_DELTA
    // One perspective at a time: half the loads in flight (20 registers instead of 40 at the search's
    // busiest point), at the cost of a second wait for the weight rows. Measured on the RTX 5060 Ti
    // (claude-work/2026-10-31/gpu-bench.py, 103,680 searches): spills 104 -> 16 B and 1.5% faster than
    // JOINT_DELTA, the former way below that loads both perspectives' rows at once.
    for (int c = 0; c < UNITS; c += 8) {
#pragma unroll 1
        for (int persp = 0; persp < 2; ++persp) {
            uint4 v = load8(from + persp * H + UOFF(c)), w[4];
#pragma unroll
            for (int k = 0; k < 4; ++k)
#ifdef NO_NEG_ROWS
                if (k < d.n) w[k] = load8(net.ftw + (size_t)feat(persp, d.piece[k], d.sq[k]) * H + UOFF(c));
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) v = k % 2 ? add8(v, w[k]) : sub8(v, w[k]);
#else
                if (k < d.n) w[k] = load8(net.ftw + (size_t)(feat(persp, d.piece[k], d.sq[k]) + OFF_ROW(k)) * H + UOFF(c));
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) v = add8(v, w[k]);
#endif
            store8(to + persp * H + UOFF(c), v);
        }
    }
#else
    for (int c = 0; c < UNITS; c += 8) {
        // Every load first, both perspectives and all (up to 4) features, so their latencies overlap.
        uint4 v[2], w[2][4];
#pragma unroll
        for (int persp = 0; persp < 2; ++persp) {
            v[persp] = load8(from + persp * H + UOFF(c));
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) w[persp][k] = load8(net.ftw + (size_t)feat(persp, d.piece[k], d.sq[k]) * H + UOFF(c));
        }
#pragma unroll
        for (int persp = 0; persp < 2; ++persp) {
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) v[persp] = k % 2 ? add8(v[persp], w[persp][k]) : sub8(v[persp], w[persp][k]);
            store8(to + persp * H + UOFF(c), v[persp]);
        }
    }
#endif
}
// dp2a: the two 16-bit halves of a, as signed values, times two bytes of b, as unsigned ones (bytes 0 and 1 for lo,
// 2 and 3 for hi), plus c. One instruction (IDP.2A) on the GPUs we use.
__device__ __forceinline__ int dp2a_lo(unsigned a, unsigned b, int c) {
    int d;
    asm("dp2a.lo.s32.u32 %0, %1, %2, %3;" : "=r"(d) : "r"(a), "r"(b), "r"(c));
    return d;
}
__device__ __forceinline__ int dp2a_hi(unsigned a, unsigned b, int c) {
    int d;
    asm("dp2a.hi.s32.u32 %0, %1, %2, %3;" : "=r"(d) : "r"(a), "r"(b), "r"(c));
    return d;
}
// Both halves of a, as signed 16-bit values, clamped to [0, QA]: min.relu.s16x2 is min(a, QA) with negative results
// set to 0, one instruction (VIMNMX.S16x2.RELU) on sm_90 and later.
__device__ __forceinline__ unsigned clamp2(unsigned a) {
    unsigned d;
    asm("min.relu.s16x2 %0, %1, %2;" : "=r"(d) : "r"(a), "r"(QA * 0x10001u));
    return d;
}
// SCReLU of two units, one 32-bit word of accumulator a and of output weights w: part + (short)(v * w) * v for each
// half, v = clamp(a, 0, QA). With QA < 256 each v is a byte of the clamped word (bytes 1 and 3 are zero), so dp2a
// multiplies by it directly: 6 instructions a pair instead of 13 (SCALAR_EVAL).
static_assert(QA < 256, "screlu2 needs each clamped unit to fit a byte");
__device__ __forceinline__ int screlu2(unsigned a, unsigned w, int part) {
    unsigned v = clamp2(a);                                 // bytes v0, 0, v1, 0
    unsigned p0 = v * w;                                    // low half (short)(v0 * w0); the high half is never read
    unsigned p1 = (unsigned)dp2a_hi(w, v << 8, 0);          // w0 * 0 + w1 * v1: low half (short)(v1 * w1)
    part = dp2a_lo(p0, v, part);                            // + (short)(v0 * w0) * v0 + (high half) * 0
    return dp2a_hi(p1, v, part);                            // + (short)(v1 * w1) * v1 + (high half) * 0
}
// NNUE::evaluate: the side to move's view first, SCReLU, int16 v * w times v, truncating divisions.
__device__ int evaluate(const Game* g, const Net& net, const short* acc) {
    const short* a = acc_slot((short*)acc, g->accTop);
    int base = LANE_BASE, part = 0;
    for (int half = 0; half < 2; ++half) {
        int persp = half == 0 ? g->stm : g->stm ^ 1;
        for (int c = 0; c < UNITS; c += 8) {
            uint4 av = load8(a + persp * H + UOFF(c)), wv = load8(net.outw + half * H + UOFF(c));
            unsigned aw[4] = {av.x, av.y, av.z, av.w}, ww[4] = {wv.x, wv.y, wv.z, wv.w};
#ifdef SCALAR_EVAL
            for (int j = 0; j < 8; ++j) { // unit j of the group: half j % 2 of word j / 2
                int v = min(max((int)(short)(aw[j / 2] >> (16 * (j % 2))), 0), QA);
                int vw = (short)(v * (short)(ww[j / 2] >> (16 * (j % 2))));
                part += vw * v;
            }
#else
#pragma unroll
            for (int j = 0; j < 4; ++j) part = screlu2(aw[j], ww[j], part);
#endif
        }
    }
    // part = hi * 65536 + lo with lo in [0, 65535]: each half's total fits an int, and the sum is exact.
    int hiSum = __reduce_add_sync(0xffffffffu, part >> 16);
    unsigned loSum = __reduce_add_sync(0xffffffffu, (unsigned)(part & 0xFFFF));
    long long sum = ((long long)hiSum << 16) + loSum;
    sum = sum / QA + net.outb;
    return (int)(sum * EVAL_SCALE / (QA * QB));
}

// Board edits. do_move and undo_move read the position with every lane, and after a __syncwarp() one lane toggles
// the moved pieces in place (xor_piece: a type word and a color word each), so no lane can see a half-done update
// (the lanes of a warp are not guaranteed to run in lockstep) and the next __syncwarp() publishes it.
__device__ __forceinline__ void xor_piece(Game* g, int p, u64 mask) {
    g->byType[type_of(p)] ^= mask;
    g->byColor[color_of(p)] ^= mask;
}
// BOARD_COPY, the former way: every lane copies all eight words into registers after a __syncwarp(), toggles them
// there and stores them back. The copies are only ever indexed by constants (the loops unroll): an index known only
// at run time would put them in local memory, a copy per lane.
struct Board {
    u64 bt[6], bc[2];
};
// Toggles piece p on the squares of mask.
__device__ __forceinline__ void b_xor(Board& b, int p, u64 mask) {
    int t = type_of(p), c = color_of(p);
#pragma unroll
    for (int i = 0; i < 6; ++i)
        if (i == t) b.bt[i] ^= mask;
#pragma unroll
    for (int i = 0; i < 2; ++i)
        if (i == c) b.bc[i] ^= mask;
}
__device__ __forceinline__ void b_load(const Game* g, Board& b) {
#pragma unroll
    for (int i = 0; i < 6; ++i) b.bt[i] = g->byType[i];
    b.bc[0] = g->byColor[0];
    b.bc[1] = g->byColor[1];
}
__device__ __forceinline__ void b_store(Game* g, const Board& b) {
#pragma unroll
    for (int i = 0; i < 6; ++i) g->byType[i] = b.bt[i];
    g->byColor[0] = b.bc[0];
    g->byColor[1] = b.bc[1];
}

// Prefetching (no value changes, only when data arrives), off unless PREFETCH is defined: measured on the
// RTX 5060 Ti it made the search 4-11% slower (15 lines a node, most never read before they are evicted).
// PREFETCH_L1 asks for L1 instead of L2.
__device__ __forceinline__ void prefetch_line(const void* p) {
#ifdef PREFETCH_L1
    asm volatile("prefetch.global.L1 [%0];" ::"l"(p));
#else
    asm volatile("prefetch.global.L2 [%0];" ::"l"(p));
#endif
}
__device__ __forceinline__ TTEntry* tt_entry(TTEntry* tt, u64 key);
__device__ __forceinline__ int pawn_index(const Game* g);
__device__ __forceinline__ int nonpawn_index(const Game* g, int c);
enum { PF_NONE, PF_QSEARCH, PF_SEARCH };
// From the parent's do_move, with the child position already in g: what the child looks up first. Its
// correction-history entries (both kinds), and in the main search its TT entry and the continuation-history row
// it scores quiet moves from (the moved piece and its target, 1,536 bytes: 13 lines when not 128-byte aligned).
// Each lane computes the same indices and takes one address, so one prefetch instruction covers all of them.
__device__ __forceinline__ void prefetch_child(const Game* g, Tables* tb, u64 key, int piece, int to, int kind) {
    int lane = lane_id(), us = g->stm;
    int pi = pawn_index(g), n0 = nonpawn_index(g, 0), n1 = nonpawn_index(g, 1);
    const char* row = (const char*)&tb->conthist[piece * 64 + to][0];
    const char* a = lane == 0 ? (const char*)tt_entry(tb->tt, key)
                  : lane == 1 ? (const char*)&tb->corr[us][pi]
                  : lane == 2 ? (const char*)&tb->npcorr[us][0][n0]
                  : lane == 3 ? (const char*)&tb->npcorr[us][1][n1]
                              : row + (lane - 4) * 128;
    if (kind == PF_SEARCH ? lane < 17 : lane >= 1 && lane <= 3) prefetch_line(a);
}

// Position::do_move: plays a pseudo-legal move and returns whether it was legal. With tb and a prefetch kind,
// it also prefetches what the child will look up first (prefetch_child).
__device__ bool do_move(Game* g, u16 m, const Net& net, short* acc, Tables* tb = nullptr, int prefetch = PF_NONE,
                        bool known = false) { // known: legal() said yes
    __syncwarp();
    int n = g->nstates, top = g->accTop, us = g->stm, them = us ^ 1, fm = g->fullmove;
    StateInfo st = g->states[n - 1];
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14);
    int pc = g->board[from];
#ifdef BOARD_COPY
    Board b;
    b_load(g, b);
#endif
    st.captured = NO_PIECE;
    ++st.rule50;
    ++st.pliesFromNull;
    Delta d;
    d.n = 2;
    d.piece[0] = pc;
    d.sq[0] = from;
    d.sq[1] = to;
    if (st.ep != SQ_NONE) {
        st.key ^= Z_EP[st.ep & 7];
        st.ep = SQ_NONE;
    }
    int arriving = pc, capSq = to, rookFrom = SQ_NONE, rookTo = SQ_NONE, rook = NO_PIECE;
    if (type == M_CASTLING) {
        bool kingside = to > from;
        rookFrom = kingside ? from + 3 : from - 4;
        rookTo = kingside ? from + 1 : from - 1;
        rook = g->board[rookFrom];
#ifdef BOARD_COPY
        b_xor(b, pc, bit(from) | bit(to));
        b_xor(b, rook, bit(rookFrom) | bit(rookTo));
#endif
        d.piece[2] = rook; d.sq[2] = rookFrom;
        d.piece[3] = rook; d.sq[3] = rookTo;
        d.n = 4;
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to] ^ Z_PSQ[rook][rookFrom] ^ Z_PSQ[rook][rookTo];
    } else {
        if (type == M_EN_PASSANT) capSq = us == 0 ? to - 8 : to + 8;
        int captured = g->board[capSq];
        if (captured != NO_PIECE) {
#ifdef BOARD_COPY
            b_xor(b, captured, bit(capSq));
#endif
            d.piece[2] = captured; d.sq[2] = capSq;
            d.n = 3;
            st.key ^= Z_PSQ[captured][capSq];
            st.captured = captured;
            st.rule50 = 0;
        }
#ifdef BOARD_COPY
        b_xor(b, pc, bit(from) | bit(to));
#endif
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to];
        if (type_of(pc) == PAWN) {
            st.rule50 = 0;
            if (type == M_PROMOTION) {
                arriving = us * 6 + ((m >> 12) & 3) + KNIGHT; // the pawn arrives as the new piece
#ifdef BOARD_COPY
                b_xor(b, pc, bit(to));
                b_xor(b, arriving, bit(to));
#endif
                st.key ^= Z_PSQ[pc][to] ^ Z_PSQ[arriving][to];
            } else if (to - from == 16 || from - to == 16) {
                int ep = (from + to) / 2;
#ifdef BOARD_COPY
                if (pawn_att(ep, us) & (them ? b.bc[1] : b.bc[0]) & b.bt[PAWN]) {
#else
                if (pawn_att(ep, us) & g->byColor[them] & g->byType[PAWN]) { // the enemy's pawns, which this move keeps
#endif
                    st.ep = ep;
                    st.key ^= Z_EP[ep & 7];
                }
            }
        }
    }
    d.piece[1] = arriving;
    int castling = st.castling & castling_mask(from) & castling_mask(to);
    if (castling != st.castling) {
        st.key ^= Z_CASTLING[st.castling] ^ Z_CASTLING[castling];
        st.castling = castling;
    }
    st.key ^= Z_SIDE[0];
    __syncwarp();
#ifdef BOARD_COPY
    b_store(g, b);
#else
    if (lane_id() == 0) {
        if (rook != NO_PIECE) {
            xor_piece(g, pc, bit(from) | bit(to));
            xor_piece(g, rook, bit(rookFrom) | bit(rookTo));
        } else {
            if (st.captured != NO_PIECE) xor_piece(g, st.captured, bit(capSq));
            if (arriving != pc) { // a promotion: the pawn leaves, the new piece arrives
                xor_piece(g, pc, bit(from));
                xor_piece(g, arriving, bit(to));
            } else {
                xor_piece(g, pc, bit(from) | bit(to));
            }
        }
    }
#endif
    g->board[from] = NO_PIECE;
    if (rook != NO_PIECE) {
        g->board[rookFrom] = NO_PIECE;
        g->board[rookTo] = rook;
    } else if (capSq != to) {
        g->board[capSq] = NO_PIECE; // en passant
    }
    g->board[to] = arriving;
    g->states[n] = st;
    g->nstates = n + 1;
    g->stm = them;
    g->fullmove = fm + (us == 1);
    g->accTop = top + 1;
    __syncwarp();
#ifdef PREFETCH
    if (prefetch != PF_NONE) prefetch_child(g, tb, st.key, pc, to, prefetch);
#endif
    // Legal first: the caller undoes an illegal move at once, and nothing ever reads its
    // accumulator, so it is only computed for legal ones. The search checks with legal() before.
    bool legal = known || !attacked(g, king_sq(g, us), them);
    if (legal) apply_delta(net, acc_slot(acc, top), acc_slot(acc, top + 1), d);
    __syncwarp();
    return legal;
}

__device__ void undo_move(Game* g, u16 m) {
    __syncwarp();
    int n = g->nstates, top = g->accTop, us = g->stm ^ 1, fm = g->fullmove;
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14);
    int captured = g->states[n - 1].captured;
#ifdef BOARD_COPY
    Board b;
    b_load(g, b);
#endif
    int moved = g->board[to], back = moved, capSq = to, rookFrom = SQ_NONE, rookTo = SQ_NONE, rook = NO_PIECE;
    if (type == M_CASTLING) {
        bool kingside = to > from;
        rookFrom = kingside ? from + 3 : from - 4;
        rookTo = kingside ? from + 1 : from - 1;
        rook = g->board[rookTo];
#ifdef BOARD_COPY
        b_xor(b, moved, bit(to) | bit(from));
        b_xor(b, rook, bit(rookTo) | bit(rookFrom));
#endif
    } else {
        if (type == M_PROMOTION) {
            back = us * 6 + PAWN; // the new piece goes, a pawn returns
#ifdef BOARD_COPY
            b_xor(b, moved, bit(to));
            b_xor(b, back, bit(to));
#endif
        }
#ifdef BOARD_COPY
        b_xor(b, back, bit(to) | bit(from));
#endif
        if (captured != NO_PIECE) {
            if (type == M_EN_PASSANT) capSq = us == 0 ? to - 8 : to + 8;
#ifdef BOARD_COPY
            b_xor(b, captured, bit(capSq));
#endif
        }
    }
    __syncwarp();
#ifdef BOARD_COPY
    b_store(g, b);
#else
    if (lane_id() == 0) {
        if (rook != NO_PIECE) {
            xor_piece(g, moved, bit(to) | bit(from));
            xor_piece(g, rook, bit(rookTo) | bit(rookFrom));
        } else {
            if (back != moved) { // a promotion: the new piece goes, the pawn returns
                xor_piece(g, moved, bit(to));
                xor_piece(g, back, bit(from));
            } else {
                xor_piece(g, moved, bit(to) | bit(from));
            }
            if (captured != NO_PIECE) xor_piece(g, captured, bit(capSq));
        }
    }
#endif
    g->board[to] = NO_PIECE;
    if (rook != NO_PIECE) {
        g->board[rookTo] = NO_PIECE;
        g->board[rookFrom] = rook;
    } else if (captured != NO_PIECE) {
        g->board[capSq] = (u8)captured; // capSq is `to` unless en passant
    }
    g->board[from] = (u8)back;
    g->stm = us;
    g->fullmove = fm - (us == 1);
    g->accTop = top - 1;
    g->nstates = n - 1;
    __syncwarp();
}

__device__ void do_null_move(Game* g) {
    __syncwarp();
    int n = g->nstates, us = g->stm;
    StateInfo st = g->states[n - 1];
    st.captured = NO_PIECE;
    ++st.rule50;
    st.pliesFromNull = 0;
    if (st.ep != SQ_NONE) {
        st.key ^= Z_EP[st.ep & 7];
        st.ep = SQ_NONE;
    }
    st.key ^= Z_SIDE[0];
    __syncwarp();
    g->states[n] = st;
    g->nstates = n + 1;
    g->stm = us ^ 1;
    __syncwarp();
}
__device__ void undo_null_move(Game* g) {
    __syncwarp();
    int n = g->nstates, us = g->stm;
    __syncwarp();
    g->stm = us ^ 1;
    g->nstates = n - 1;
    __syncwarp();
}


__device__ bool is_draw(Game* g) {
    __syncwarp();
    int n = g->nstates;
    const StateInfo& st = g->states[n - 1];
    if (st.rule50 >= 100) return true;
    u64 key = st.key;
    int lookback = min(min(st.rule50, st.pliesFromNull), n - 1);
    bool found = false;
    for (int i = 4 + 2 * lane_id(); i <= lookback; i += 64) // lane l checks plies 4 + 2l, 4 + 2l + 64, ...
        if (g->states[n - 1 - i].key == key) found = true;
    return __any_sync(0xffffffffu, found);
}

// ---- Move generation (src/movegen.cpp order) ----
__device__ __forceinline__ void add(u16* list, int& n, int from, int to, int type, int promo) {
    list[n++] = (u16)(from | (to << 6) | ((promo - KNIGHT) << 12) | type);
}
__device__ __forceinline__ void add_promotions(u16* list, int& n, int from, int to, bool queenOnly) {
    add(list, n, from, to, M_PROMOTION, QUEEN);
    if (!queenOnly) {
        add(list, n, from, to, M_PROMOTION, KNIGHT);
        add(list, n, from, to, M_PROMOTION, ROOK);
        add(list, n, from, to, M_PROMOTION, BISHOP);
    }
}
// Appends a move to each square of `to`, in square order, from `from` (or, when from < 0, from the square
// `delta` behind): lane l writes the moves to squares l and l + 32, each after the targets below it.
__device__ __forceinline__ void add_set(u16* list, int& n, u64 to, int from, int delta) {
    int lane = lane_id();
    unsigned lo = (unsigned)to, hi = (unsigned)(to >> 32), below = (1u << lane) - 1;
    int nlo = __popc(lo);
    if ((lo >> lane) & 1) list[n + __popc(lo & below)] = (u16)((from < 0 ? lane - delta : from) | (lane << 6));
    if ((hi >> lane) & 1) list[n + nlo + __popc(hi & below)] = (u16)((from < 0 ? lane + 32 - delta : from) | ((lane + 32) << 6));
    n += nlo + __popc(hi);
}
__device__ int generate(Game* g, u16* list, bool noisy) {
    int us = g->stm, them = us ^ 1, n = 0;
    u64 pawns = pcs(g, us, PAWN), empty = ~occupied(g), enemies = g->byColor[them];
    u64 seventh = us == 0 ? 0x00FF000000000000ULL : 0xFF00ULL, third = us == 0 ? 0xFF0000ULL : 0xFF0000000000ULL;
    int up = us == 0 ? 8 : -8;
#define PUSH(b) (us == 0 ? (b) << 8 : (b) >> 8)
    if (!noisy) {
        u64 single = PUSH(pawns & ~seventh) & empty, twice = PUSH(single & third) & empty;
#ifndef SERIAL_GEN
        add_set(list, n, single, -1, up);
        add_set(list, n, twice, -1, 2 * up);
#else
        for (; single; single &= single - 1) { int to = lsb(single); add(list, n, to - up, to, 0, KNIGHT); }
        for (; twice; twice &= twice - 1) { int to = lsb(twice); add(list, n, to - 2 * up, to, 0, KNIGHT); }
#endif
    }
    for (u64 b = PUSH(pawns & seventh) & empty; b; b &= b - 1) { int to = lsb(b); add_promotions(list, n, to - up, to, noisy); }
#undef PUSH
    for (u64 b = pawns; b; b &= b - 1) {
        int from = lsb(b);
        for (u64 c = pawn_att(from, us) & enemies; c; c &= c - 1) {
            int to = lsb(c);
            if (bit(from) & seventh) add_promotions(list, n, from, to, noisy);
            else add(list, n, from, to, 0, KNIGHT);
        }
    }
    int ep = g->states[g->nstates - 1].ep;
    if (ep != SQ_NONE)
        for (u64 a = pawn_att(ep, them) & pawns; a; a &= a - 1) add(list, n, lsb(a), ep, M_EN_PASSANT, KNIGHT);
    u64 occ = occupied(g), targets = noisy ? g->byColor[them] : ~g->byColor[us];
#ifndef SERIAL_GEN
    {
        // Lane l: the l-th piece in generation order and its targets (at most 16 pieces).
        int lane = lane_id(), rank = lane, pt = -1, count = 0;
        u64 mine = 0;
        for (int t = KNIGHT; t <= KING; ++t) {
            u64 bt = pcs(g, us, t);
            int c = __popcll(bt);
            if (pt < 0) {
                if (rank < c) { pt = t; mine = bt; }
                else rank -= c;
            }
            count += c;
        }
        u64 att = 0;
        int from = 0;
        if (pt >= 0) {
            for (; rank; --rank) mine &= mine - 1;
            from = lsb(mine);
            att = pt == KNIGHT ? knight_sq(from) : pt == KING ? king_att_sq(from) : 0;
            if (pt == BISHOP || pt == QUEEN) att |= bishop_att(from, occ);
            if (pt == ROOK || pt == QUEEN) att |= rook_att(from, occ);
            att &= targets;
        }
        for (int j = 0; j < count; ++j)
            add_set(list, n, __shfl_sync(0xffffffffu, att, j), __shfl_sync(0xffffffffu, from, j), 0);
    }
#else
    for (int pt = KNIGHT; pt <= KING; ++pt)
        for (u64 b = pcs(g, us, pt); b; b &= b - 1) {
            int from = lsb(b);
            for (u64 a = attacks_bb(pt, from, occ) & targets; a; a &= a - 1) add(list, n, from, lsb(a), 0, KNIGHT);
        }
#endif
    if (!noisy) {
        int base = us == 0 ? 0 : 56, king = base + 4, rights = g->states[g->nstates - 1].castling;
        if ((rights & (us == 0 ? WHITE_OO | WHITE_OOO : BLACK_OO | BLACK_OOO)) && !in_check(g)) {
            if ((rights & (us == 0 ? WHITE_OO : BLACK_OO)) && !(occ & (bit(base + 5) | bit(base + 6))) && !attacked(g, base + 5, them))
                add(list, n, king, base + 6, M_CASTLING, KNIGHT);
            if ((rights & (us == 0 ? WHITE_OOO : BLACK_OOO)) && !(occ & (bit(base + 1) | bit(base + 2) | bit(base + 3)))
                && !attacked(g, base + 3, them))
                add(list, n, king, base + 2, M_CASTLING, KNIGHT);
        }
    }
    return n;
}

// ---- TT (src/tt.cpp: one entry per index; an entry from the current search stays unless the new one,
// for another position, is at least as deep; keep the old move) ----
__device__ __forceinline__ TTEntry* tt_entry(TTEntry* tt, u64 key) { return tt + (key >> (64 - TT_BITS)); }
__device__ __forceinline__ int score_to_tt(int s, int ply) {
    return s >= VALUE_MATE_IN_MAX_PLY ? s + ply : s <= -VALUE_MATE_IN_MAX_PLY ? s - ply : s;
}
__device__ __forceinline__ int score_from_tt(int s, int ply) {
    return s >= VALUE_MATE_IN_MAX_PLY ? s - ply : s <= -VALUE_MATE_IN_MAX_PLY ? s + ply : s;
}
__device__ void tt_store(Tables* tb, u64 key, u16 move, int score, int depth, int bound) {
    TTEntry* e = tt_entry(tb->tt, key);
    __syncwarp();
    TTEntry old = *e;
    u8 gen = (u8)tb->gen;
    // A deeper result for another position, written during this search, stays (every lane agrees).
    if (old.key != key && old.gen == gen && depth < old.depth) return;
    if (move == MOVE_NONE && old.key == key) move = old.move;
    TTEntry n;
    n.key = key; n.move = move; n.score = (short)score; n.depth = (signed char)depth; n.bound = (u8)bound; n.gen = gen; n.pad = 0;
    __syncwarp();
    *e = n;
    __syncwarp();
}
// Search::clear(): an empty TT and correction history.
__device__ void clear_tables(Tables* tb) {
    TTEntry z;
    z.key = 0; z.move = 0; z.score = 0; z.depth = 0; z.bound = 0; z.gen = 0; z.pad = 0;
    for (int i = lane_id(); i < (1 << TT_BITS); i += 32) tb->tt[i] = z;
    for (int i = lane_id(); i < 2 * CORR_SIZE; i += 32) (&tb->corr[0][0])[i] = 0;
    for (int i = lane_id(); i < 4 * CORR_SIZE; i += 32) (&tb->npcorr[0][0][0])[i] = 0;
    int4* ch = reinterpret_cast<int4*>(&tb->conthist[0][0]);
    for (int i = lane_id(); i < CH_BLOCKS; i += 32) ch[i] = make_int4(0, 0, 0, 0);
    for (int i = lane_id(); i < CH_WORDS; i += 32) tb->chMask[i] = 0;
    if (lane_id() == 0) tb->gen = 0;
    __syncwarp();
}

// ---- Search (src/search.cpp) ----
__constant__ int PIECE_VALUE[7] = {100, 320, 330, 500, 900, 0, 0};
__constant__ int SEE_VALUE[6] = {100, 320, 330, 500, 900, 20000};

__device__ __forceinline__ bool is_quiet(const Game* g, u16 m) {
    int t = m & (3 << 14);
    return g->board[(m >> 6) & 63] == NO_PIECE && t != M_EN_PASSANT && t != M_PROMOTION;
}
__device__ bool see_ge(const Game* g, u16 m, int threshold);
// The continuation-history entry for quiet move m after the move `back` plies earlier (the engine's
// cont_entry), or null at the root, after a null move, or with continuation history off.
__device__ __forceinline__ short* cont_entry(Game* g, Tables* tb, int on, int ply, int back, u16 m) {
    if (!on || ply < back) return nullptr;
    u16 prev = g->moveStack[ply - back];
    if (prev == MOVE_NONE) return nullptr;
    return &tb->conthist[g->pieceStack[ply - back] * 64 + ((prev >> 6) & 63)][g->board[m & 63] * 64 + ((m >> 6) & 63)];
}
// Move order exactly as src/search.cpp scores it: the TT move, captures by MVV-LVA (in the main search those
// that lose material by SEE go below every quiet move), a queen promotion, the two killers, then quiet moves
// by history plus their two continuation entries (each within +-16384).
__device__ void score_moves(Game* g, Tables* tb, int contHist, const u16* list, int n, int* scores, u16 ttMove, int ply) {
    __syncwarp();
    for (int i = lane_id(); i < n; i += 32) { // every lane scores every 32nd move
        u16 m = list[i];
        int from = m & 63, to = (m >> 6) & 63, t = m & (3 << 14), s;
        if (m == ttMove) s = 1000000;
        else if (t == M_EN_PASSANT) s = 100000 + PIECE_VALUE[PAWN] * 10 - PAWN;
        else if (g->board[to] != NO_PIECE) {
            int mvvLva = PIECE_VALUE[type_of(g->board[to])] * 10 - type_of(g->board[from]);
            s = (ply >= 0 && !see_ge(g, m, 0) ? -100000 : 100000) + mvvLva;
        }
        else if (t == M_PROMOTION && ((m >> 12) & 3) + KNIGHT == QUEEN) s = 90000;
        else if (ply >= 0 && m == g->killers[ply][0]) s = 80000;
        else if (ply >= 0 && m == g->killers[ply][1]) s = 70000;
        else if (ply >= 0) {
            s = g->history[g->stm][from][to];
            if (const short* c = cont_entry(g, tb, contHist, ply, 1, m)) s += *c;
            if (const short* c = cont_entry(g, tb, contHist, ply, 2, m)) s += *c;
        }
        else s = 0;
        scores[i] = s;
    }
    __syncwarp();
}
// Marks the block of continuation-history entry c as possibly non-zero (see Tables::chMask). Every lane
// reads the same word, then writes the same value.
__device__ __forceinline__ void mark_cont(Tables* tb, const short* c) {
    int block = (int)(c - &tb->conthist[0][0]) >> 3;
    unsigned* w = &tb->chMask[block >> 5];
    unsigned v = *w | (1u << (block & 31));
    __syncwarp();
    *w = v;
    __syncwarp();
}
// Gravity moves history and both continuation entries toward +-16384 by the same bonus.
__device__ void update_history(Game* g, Tables* tb, int contHist, int ply, u16 m, int bonus) {
    int& h = g->history[g->stm][m & 63][(m >> 6) & 63];
    short* c1 = cont_entry(g, tb, contHist, ply, 1, m);
    short* c2 = cont_entry(g, tb, contHist, ply, 2, m);
    int v = h, v1 = c1 ? *c1 : 0, v2 = c2 ? *c2 : 0;
    v += bonus - v * abs(bonus) / 16384;
    v1 += bonus - v1 * abs(bonus) / 16384;
    v2 += bonus - v2 * abs(bonus) / 16384;
    __syncwarp();
    h = v;
    if (c1) *c1 = (short)v1;
    if (c2) *c2 = (short)v2;
    __syncwarp();
    if (c1) mark_cont(tb, c1);
    if (c2) mark_cont(tb, c2);
}
__device__ __forceinline__ int pawn_index(const Game* g) {
    u64 h = pcs(g, 0, PAWN) * 0x9E3779B97F4A7C15ULL ^ pcs(g, 1, PAWN) * 0xC2B2AE3D27D4EB4FULL;
    h ^= h >> 31;
    h *= 0xBF58476D1CE4E5B9ULL;
    return (int)(h >> 50); // top 14 bits: 0 to CORR_SIZE - 1
}
__device__ __forceinline__ int nonpawn_index(const Game* g, int c) {
    u64 h = (g->byColor[c] & ~g->byType[PAWN]) * 0x9E3779B97F4A7C15ULL;
    h ^= pcs(g, c, KNIGHT) * 0xD6E8FEB86659FD93ULL ^ pcs(g, c, BISHOP) * 0xC2B2AE3D27D4EB4FULL
       ^ pcs(g, c, ROOK) * 0x165667B19E3779F9ULL ^ pcs(g, c, QUEEN) * 0x27D4EB2F165667C5ULL;
    h ^= h >> 31;
    h *= 0xBF58476D1CE4E5B9ULL;
    h ^= h >> 29;
    return (int)(h >> 50);
}
// The network's eval plus what correction history has learned for these pawns and non-pawn pieces.
__device__ int corrected_eval(const Game* g, const Net& net, const short* acc, const Tables* tb) {
    int us = g->stm;
    int nonPawn = tb->npcorr[us][0][nonpawn_index(g, 0)] + tb->npcorr[us][1][nonpawn_index(g, 1)];
    int e = evaluate(g, net, acc) + (tb->corr[us][pawn_index(g)] + nonPawn / 2) / 16;
    return min(max(e, -VALUE_MATE_IN_MAX_PLY + 1), VALUE_MATE_IN_MAX_PLY - 1);
}
// Moves the entries toward the search result, more for deeper searches; the gravity term keeps them within
// +-CORR_LIMIT.
__device__ void update_corrhist(const Game* g, Tables* tb, int diff, int depth) {
    int us = g->stm;
    short* e = &tb->corr[us][pawn_index(g)];
    short* nw = &tb->npcorr[us][0][nonpawn_index(g, 0)];
    short* nb = &tb->npcorr[us][1][nonpawn_index(g, 1)];
    __syncwarp();
    int v = *e, vw = *nw, vb = *nb;
    int bonus = min(max(diff * depth / 4, -CORR_LIMIT / 4), CORR_LIMIT / 4);
    v += bonus - v * abs(bonus) / CORR_LIMIT;
    vw += bonus - vw * abs(bonus) / CORR_LIMIT;
    vb += bonus - vb * abs(bonus) / CORR_LIMIT;
    __syncwarp();
    *e = (short)v;
    *nw = (short)vw;
    *nb = (short)vb;
    __syncwarp();
}
__device__ u16 pick_move(u16* list, int* scores, int n, int i) {
    __syncwarp();
    // Scores lie within +-2^21 (TT move 1,000,000; history and continuation entries within +-16,384 each) and
    // indices below 256, so (score + 2^22) << 8 | (255 - index) fits 32 bits, and its maximum is the best score
    // at its first index.
    unsigned key = 0;
    for (int j = i + lane_id(); j < n; j += 32) key = max(key, ((unsigned)(scores[j] + (1 << 22)) << 8) | (unsigned)(255 - j));
    key = __reduce_max_sync(0xffffffffu, key);
    int bestS = (int)(key >> 8) - (1 << 22), bestJ = 255 - (int)(key & 255);
    u16 mi = list[i], mb = list[bestJ];
    int si = scores[i];
    __syncwarp();
    list[i] = mb; list[bestJ] = mi;
    scores[i] = bestS; scores[bestJ] = si;
    __syncwarp();
    return mb;
}
__device__ bool see_ge(const Game* g, u16 m, int threshold) {
    if ((m & (3 << 14)) != 0) return 0 >= threshold;
    int from = m & 63, to = (m >> 6) & 63, victim = g->board[to];
    int swap = (victim == NO_PIECE ? 0 : SEE_VALUE[type_of(victim)]) - threshold;
    if (swap < 0) return false;
    swap = SEE_VALUE[type_of(g->board[from])] - swap;
    if (swap <= 0) return true;
    u64 occ = occupied(g) ^ bit(from) ^ bit(to);
    u64 bishops = g->byType[BISHOP] | g->byType[QUEEN], rooks = g->byType[ROOK] | g->byType[QUEEN];
    u64 attackers = (pawn_att(to, 1) & pcs(g, 0, PAWN)) | (pawn_att(to, 0) & pcs(g, 1, PAWN))
                  | (knight_sq(to) & g->byType[KNIGHT]) | (king_att_sq(to) & g->byType[KING])
                  | (bishop_att(to, occ) & bishops) | (rook_att(to, occ) & rooks);
    int stm = color_of(g->board[from]);
    bool result = true;
    while (true) {
        stm ^= 1;
        attackers &= occ;
        u64 ours = attackers & g->byColor[stm];
        if (!ours) break;
        result = !result;
        int pt = PAWN;
        while (!(ours & g->byType[pt])) ++pt;
        if (pt == KING) return (attackers & g->byColor[stm ^ 1]) ? !result : result;
        if ((swap = SEE_VALUE[pt] - swap) < (int)result) break;
        occ ^= bit(lsb(ours & g->byType[pt]));
        if (pt == PAWN || pt == BISHOP || pt == QUEEN) attackers |= bishop_att(to, occ) & bishops;
        if (pt == ROOK || pt == QUEEN) attackers |= rook_att(to, occ) & rooks;
    }
    return result;
}
__device__ u16 first_legal_move(Game* g, const Net& net, short* acc, int ply) {
    u16* list = g->moves[ply];
    int n = generate(g, list, false);
    __syncwarp();
    for (int i = 0; i < n; ++i) {
        u16 m = list[i];
        bool legal = do_move(g, m, net, acc);
        undo_move(g, m);
        if (legal) return m;
    }
    return MOVE_NONE;
}
__device__ bool has_legal_move(Game* g, const Net& net, short* acc, int ply) {
    int us = g->stm, k = king_sq(g, us);
    u64 own = g->byColor[us], occ = occupied(g);
    for (u64 b = own & ~g->byType[KING]; b; b &= b - 1) {
        int s = lsb(b);
        int df = (s & 7) - (k & 7), dr = (s >> 3) - (k >> 3);
        if (df == 0 || dr == 0 || df == dr || df == -dr) continue;
        u64 targets;
        switch (type_of(g->board[s])) {
            case PAWN: {
                int push = us == 0 ? s + 8 : s - 8;
                targets = (pawn_att(s, us) & g->byColor[us ^ 1]) | (g->board[push] == NO_PIECE ? bit(push) : 0);
                break;
            }
            case KNIGHT: targets = knight_sq(s) & ~own; break;
            case BISHOP: targets = bishop_att(s, occ) & ~own; break;
            case ROOK: targets = rook_att(s, occ) & ~own; break;
            default: targets = (bishop_att(s, occ) | rook_att(s, occ)) & ~own; break;
        }
        if (targets) return true;
    }
    return first_legal_move(g, net, acc, ply) != MOVE_NONE;
}

// The states of a call. A search call starts in S_ENTRY, a quiescence call in Q_ENTRY; the others
// resume a call after the child named by the state returns.
enum { S_ENTRY, S_NULL_DONE, S_MOVES, S_LOOP, S_SING_DONE, S_SEARCH_MOVE, S_FIRST_DONE, S_RED_DONE, S_FULL_DONE, S_PV_DONE,
       Q_ENTRY, Q_LOOP, Q_DONE };

// The slot of a call's moves, scores and quiets (see Game::moves).
__device__ __forceinline__ int move_slot(const Frame& f) { return f.excl ? MAX_PLY + 1 + f.ply : f.ply; }

__device__ __forceinline__ Frame new_call(int state, int alpha, int beta, int depth, int ply, bool inCheck) {
    Frame f = {};
    f.inCheck = inCheck;
    f.state = state;
    f.alpha = alpha;
    f.beta = beta;
    f.depth = depth;
    f.ply = ply;
    return f;
}

// Call a child at ply + 1 (starting in ENTRY; CHK: whether it is in check) and resume this call in RESUME
// when it returns.
#define CALL(RESUME, ENTRY, A, B, D, CHK)                \
    {                                                     \
        bool _chk = (CHK);                                \
        f.state = RESUME;                                 \
        __syncwarp();                                     \
        g->frames[sp++] = f;                              \
        f = new_call(ENTRY, A, B, D, f.ply + 1, _chk);    \
        continue;                                         \
    }
// Call search(A, B, D, ply) at this call's own ply with move EXCL left out (a singular search), and resume
// this call in RESUME when it returns.
#define CALL_EXCLUDING(RESUME, A, B, D, EXCL)            \
    {                                                     \
        u16 _excl = (EXCL);                               \
        f.state = RESUME;                                 \
        __syncwarp();                                     \
        g->frames[sp++] = f;                              \
        f = new_call(S_ENTRY, A, B, D, f.ply, f.inCheck); \
        f.excl = _excl;                                   \
        continue;                                         \
    }
// Return V from the running call.
#define RETURN(V)  \
    {              \
        ret = (V); \
        break;     \
    }
// Count a node, and stop at the node limit, checked every 1,024 nodes as src/search.cpp's check_limits.
#define COUNT_NODE()                                                       \
    {                                                                      \
        ++nodes;                                                           \
        if ((nodes & 1023) == 0 && g->nodeLimit && nodes >= g->nodeLimit)  \
            stopped = 1;                                                   \
        if (stopped) RETURN(0)                                             \
    }

// Runs search(alpha, beta, depth, 0) and everything below it, in the same order as the recursive
// code, from the root call think_run put in g->cur. Returns true when the root call returns, with its
// score in *score, or false once the node count reaches stopAt: the running call goes back to g->cur,
// and the next call carries on from it.
__device__ bool search_run(Game* g, const Net& net, const Params& p, short* acc, Tables* tb, u64 stopAt, int* score) {
    __syncwarp();
    Frame f = g->cur;
    int sp = g->sp, ret = 0;
    // The node count and the stop flag stay in registers until the search pauses or returns (every
    // lane holds the same values); nothing else reads or writes them meanwhile. The node limit is read
    // only every 1,024 nodes, so it stays in memory and its registers go to the search.
    u64 nodes = g->nodes;
    int stopped = g->stopped;
    while (true) {
        if (nodes >= stopAt) {
            __syncwarp();
            g->cur = f;
            g->sp = sp;
            g->nodes = nodes;
            g->stopped = stopped;
            __syncwarp();
            return false;
        }
        switch (f.state) {
        case S_ENTRY: {
            if (f.inCheck) ++f.depth; // the caller set inCheck
            if (f.depth <= 0) { // return qsearch(alpha, beta, ply)
                f.state = Q_ENTRY;
                continue;
            }
            COUNT_NODE()
            f.root = f.ply == 0;
            f.pvNode = f.beta - f.alpha > 1;
            if (f.root) g->rootPv = 0; // pvLength[0] = 0
            if (!f.root) {
                PB(9) bool draw = is_draw(g); PE(9)
                if (draw) RETURN(0)
                if (f.ply >= MAX_PLY - 1) RETURN(evaluate(g, net, acc))
            }
            f.key = g->states[g->nstates - 1].key;
            // A singular search (one move excluded) neither reads nor writes this node's TT entry.
            bool hit = false;
            TTEntry e = {};
            if (!f.excl) {
                PB(6) e = *tt_entry(tb->tt, f.key); PE(6)
                hit = e.key == f.key && e.bound != BOUND_NONE;
            }
            f.ttMove = hit ? e.move : MOVE_NONE;
            f.ttScore = hit ? score_from_tt(e.score, f.ply) : 0;
            f.ttDepth = hit ? e.depth : -1;
            f.ttBound = hit ? e.bound : BOUND_NONE;
            if (hit && !f.pvNode && f.ttDepth >= f.depth) {
                if (f.ttBound == BOUND_EXACT || (f.ttBound == BOUND_LOWER && f.ttScore >= f.beta) || (f.ttBound == BOUND_UPPER && f.ttScore <= f.alpha))
                    RETURN(f.ttScore)
            }
            PB(5) f.staticEval = f.inCheck ? -VALUE_INF : corrected_eval(g, net, acc, tb); PE(5)
            if (!f.excl) g->evalStack[f.ply] = f.staticEval;
            f.improving = !f.inCheck && f.ply >= 2 && f.staticEval > g->evalStack[f.ply - 2];
            int us = g->stm;
            if (!f.root && !f.pvNode && !f.inCheck && !f.excl && f.depth <= p.rfpDepth && g->states[g->nstates - 1].rule50 + f.depth < 100
                && abs(f.beta) < VALUE_MATE_IN_MAX_PLY && (g->byColor[us] & ~(g->byType[PAWN] | g->byType[KING]))) {
                if (abs(f.staticEval) < VALUE_MATE_IN_MAX_PLY && f.staticEval - p.rfpMargin * (f.depth - (p.rfpImproving && f.improving)) >= f.beta)
                    RETURN(has_legal_move(g, net, acc, f.ply) ? f.staticEval : 0)
            }
            bool hasPieces = (g->byColor[us] & ~g->byType[PAWN] & ~g->byType[KING]) != 0;
            if (!f.pvNode && !f.inCheck && !f.root && !f.excl && f.depth >= p.nmpDepth && hasPieces && g->moveStack[f.ply - 1] != MOVE_NONE && f.staticEval >= f.beta) {
                int R = p.nmpBase + f.depth / p.nmpDiv + (p.nmpEvalDiv ? min((f.staticEval - f.beta) / p.nmpEvalDiv, p.nmpEvalMax) : 0);
                g->moveStack[f.ply] = MOVE_NONE;
                g->doubleExt[f.ply + 1] = g->doubleExt[f.ply];
                __syncwarp();
                do_null_move(g);
                CALL(S_NULL_DONE, S_ENTRY, -f.beta, -f.beta + 1, f.depth - 1 - R, in_check(g))
            }
            f.state = S_MOVES;
            continue;
        }
        case S_NULL_DONE: {
            int score = -f.childScore;
            undo_null_move(g);
            if (stopped) RETURN(0)
            if (score >= f.beta) RETURN(score >= VALUE_MATE_IN_MAX_PLY ? f.beta : score)
            f.state = S_MOVES;
            continue;
        }
        case S_MOVES: {
            // Internal iterative reductions: with no TT move the ordering here is poor, so search one ply
            // shallower. Not in a singular search, whose depth stays as its caller set it.
            if (!f.root && !f.excl && f.depth >= p.iirDepth && f.ttMove == MOVE_NONE) --f.depth;
            int slot = move_slot(f);
            PB(0) f.n = generate(g, g->moves[slot], false);
            __syncwarp(); PE(0)
            PB(1) score_moves(g, tb, p.contHist, g->moves[slot], f.n, g->scores[slot], f.ttMove, f.ply); PE(1)
            f.originalAlpha = f.alpha;
            f.best = -VALUE_INF;
            f.legalMoves = f.quietCount = f.i = 0;
            f.bestMove = MOVE_NONE;
            f.state = S_LOOP;
        }
        // fall through
        case S_LOOP: {
            // Make the next legal move that is not pruned, then search it below: CALL can't leave this
            // loop, since its continue would continue the loop.
            int slot = move_slot(f);
            u16* list = g->moves[slot];
            int* scores = g->scores[slot];
            bool found = false, singular = false;
            while (f.i < f.n) {
                PB(2) u16 m = pick_move(list, scores, f.n, f.i); PE(2)
                ++f.i;
                if (m == f.excl) continue;
                bool quiet = is_quiet(g, m);
                if (!f.pvNode && !f.inCheck && quiet && f.depth <= p.lmpDepth && f.best > -VALUE_MATE_IN_MAX_PLY && f.quietCount >= (p.lmpBase + f.depth * f.depth) / (p.lmpImproving && !f.improving ? 2 : 1)) continue;
                if (!f.pvNode && !f.inCheck && quiet && f.depth <= p.futDepth && f.best > -VALUE_MATE_IN_MAX_PLY && f.staticEval + p.futMargin * f.depth <= f.alpha) continue;
                if (!f.pvNode && !f.inCheck && quiet && f.depth <= p.histPruneDepth && f.best > -VALUE_MATE_IN_MAX_PLY && scores[f.i - 1] < -p.histPruneMargin * f.depth) continue;
                if (!f.root && !f.inCheck && f.depth <= p.seeDepth && f.best > -VALUE_MATE_IN_MAX_PLY) {
                    PB(7) bool seeOk = see_ge(g, m, quiet ? -p.seeQuiet * f.depth : -p.seeCapture * f.depth * f.depth); PE(7)
                    if (!seeOk) continue;
                }
                f.m = m;
                f.quiet = quiet;
                f.ext = 0;
                // Singular extension: decided by a search of this node without the TT move (below).
                if (!f.root && m == f.ttMove && f.depth >= p.singDepth && f.ttDepth >= f.depth - p.singTTMargin && f.ttBound != BOUND_UPPER
                    && abs(f.ttScore) < VALUE_MATE_IN_MAX_PLY && f.ply < 2 * g->thinkDepth) {
                    singular = true;
                    break;
                }
                PB(8) bool ok = legal(g, m, f.inCheck); PE(8)
                if (!ok) continue;
                u8 moved = g->board[m & 63];
                PB(3) do_move(g, m, net, acc, tb, PF_SEARCH, true); PE(3)
                ++f.legalMoves;
                g->moveStack[f.ply] = m;
                g->pieceStack[f.ply] = moved;
                g->doubleExt[f.ply + 1] = g->doubleExt[f.ply] + (f.ext == 2);
                __syncwarp();
                found = true;
                break;
            }
            if (singular) {
                int singularBeta = f.ttScore - p.singBeta * f.depth / 16;
                CALL_EXCLUDING(S_SING_DONE, singularBeta - 1, singularBeta, (f.depth - 1) / 2, f.m)
            }
            if (found) {
                f.state = S_SEARCH_MOVE;
                continue;
            }
            // With a move excluded, the excluded move was the only legal one.
            if (f.legalMoves == 0) RETURN(f.excl ? f.alpha : f.inCheck ? -VALUE_MATE + f.ply : 0)
            // A search with a move excluded is not this position's result, so neither the table nor the
            // correction history learns from it.
            if (!f.excl) {
                int bound = f.best >= f.beta ? BOUND_LOWER : f.alpha > f.originalAlpha ? BOUND_EXACT : BOUND_UPPER;
                if (!f.inCheck && (f.bestMove == MOVE_NONE || is_quiet(g, f.bestMove)) && abs(f.best) < VALUE_MATE_IN_MAX_PLY
                    && !(bound == BOUND_LOWER && f.best <= f.staticEval) && !(bound == BOUND_UPPER && f.best >= f.staticEval))
                    update_corrhist(g, tb, f.best - f.staticEval, f.depth);
                PB(6) tt_store(tb, f.key, f.bestMove, score_to_tt(f.best, f.ply), f.depth, bound); PE(6)
            }
            RETURN(f.best)
        }
        case S_SING_DONE: { // the singular search (this node without f.m, same side to move) returned
            int singularBeta = f.ttScore - p.singBeta * f.depth / 16;
            if (stopped) RETURN(0)
            // f.m is the only good move: search it a ply deeper (two when far below, dextLimit times a path)
            if (f.childScore < singularBeta)
                f.ext = !f.pvNode && f.childScore < singularBeta - p.dextMargin && g->doubleExt[f.ply] < p.dextLimit ? 2 : 1;
            else if (singularBeta >= f.beta) RETURN(singularBeta) // several moves beat beta: multi-cut
            else if (p.negExt && f.ttScore >= f.beta) f.ext = -1; // others likely beat beta too: a ply shallower
            PB(8) bool ok = legal(g, f.m, f.inCheck); PE(8)
            if (!ok) {
                f.state = S_LOOP;
                continue;
            }
            u8 moved = g->board[f.m & 63];
            PB(3) do_move(g, f.m, net, acc, tb, PF_SEARCH, true); PE(3)
            ++f.legalMoves;
            g->moveStack[f.ply] = f.m;
            g->pieceStack[f.ply] = moved;
            g->doubleExt[f.ply + 1] = g->doubleExt[f.ply] + (f.ext == 2);
            __syncwarp();
        }
        // fall through
        case S_SEARCH_MOVE: { // search the move just made, f.m
            int newDepth = f.depth - 1 + f.ext;
            PB(8) bool givesCheck = gives_check(g, f.m); PE(8)
            if (f.legalMoves == 1) CALL(S_FIRST_DONE, S_ENTRY, -f.beta, -f.alpha, newDepth, givesCheck)
            f.r = 0;
            if (f.depth >= p.lmrDepth && f.legalMoves > p.lmrMoves && f.quiet && !f.inCheck && !givesCheck) {
                int r = p.lmr[min(f.depth, 63)][min(f.legalMoves, 63)];
                if (p.lmrImproving && !f.improving) ++r;
                if (f.pvNode) --r;
                f.r = max(0, min(r, f.depth - 2));
            }
            CALL(S_RED_DONE, S_ENTRY, -f.alpha - 1, -f.alpha, newDepth - f.r, givesCheck)
        }
        case S_RED_DONE: // the reduced zero-window search returned
            if (-f.childScore > f.alpha && f.r > 0) CALL(S_FULL_DONE, S_ENTRY, -f.alpha - 1, -f.alpha, f.depth - 1 + f.ext, gives_check(g, f.m))
            // fall through: its score stands as the full-depth one
        case S_FULL_DONE: // the full-depth zero-window search returned
            if (-f.childScore > f.alpha && -f.childScore < f.beta) CALL(S_PV_DONE, S_ENTRY, -f.beta, -f.alpha, f.depth - 1 + f.ext, gives_check(g, f.m))
            // fall through
        case S_FIRST_DONE:
        case S_PV_DONE: {
            int score = -f.childScore;
            u16 m = f.m;
            PB(4) undo_move(g, m); PE(4)
            if (stopped) RETURN(0)
            f.state = S_LOOP;
            if (score > f.best) {
                f.best = score;
                if (score > f.alpha) {
                    f.alpha = score;
                    f.bestMove = m;
                    if (f.root) {
                        g->rootBest = m;
                        g->rootPv = 1;
                        __syncwarp();
                    }
                    if (score >= f.beta) {
                        if (f.quiet) {
                            if (m != g->killers[f.ply][0]) {
                                u16 k0 = g->killers[f.ply][0];
                                __syncwarp();
                                g->killers[f.ply][1] = k0;
                                g->killers[f.ply][0] = m;
                                __syncwarp();
                            }
                            int bonus = min(p.histLin ? p.histLin * f.depth - p.histOff : p.histMul * f.depth * f.depth, p.histMax);
                            update_history(g, tb, p.contHist, f.ply, m, bonus);
                            u16* quiets = g->quiets[move_slot(f)];
                            for (int j = 0; j < f.quietCount; ++j) update_history(g, tb, p.contHist, f.ply, quiets[j], -bonus);
                        }
                        f.i = f.n; // break
                        continue;
                    }
                }
            }
            if (f.quiet) {
                g->quiets[move_slot(f)][f.quietCount++] = m;
                __syncwarp();
            }
            continue;
        }
        case Q_ENTRY: {
            COUNT_NODE()
            PB(5) int standPat = corrected_eval(g, net, acc, tb); PE(5)
            if (f.ply >= MAX_PLY - 1 || standPat >= f.beta) RETURN(standPat)
            f.alpha = max(f.alpha, standPat);
            f.staticEval = standPat; // for delta pruning
            PB(0) f.n = generate(g, g->moves[move_slot(f)], true);
            __syncwarp(); PE(0)
            PB(1) score_moves(g, tb, 0, g->moves[move_slot(f)], f.n, g->scores[move_slot(f)], MOVE_NONE, -1); PE(1)
            f.best = standPat;
            f.i = 0;
            f.state = Q_LOOP;
        }
        // fall through
        case Q_LOOP: {
            u16* list = g->moves[move_slot(f)];
            int* scores = g->scores[move_slot(f)];
            bool found = false;
            while (f.i < f.n) {
                PB(2) u16 m = pick_move(list, scores, f.n, f.i); PE(2)
                ++f.i;
                if (p.qsDelta && (m & (3 << 14)) != M_PROMOTION && f.staticEval + p.qsDelta
                    + PIECE_VALUE[(m & (3 << 14)) == M_EN_PASSANT ? PAWN : type_of(g->board[(m >> 6) & 63])] <= f.alpha) continue;
                PB(7) bool seeOk = see_ge(g, m, p.qsSee); PE(7)
                if (!seeOk) continue;
                PB(8) bool ok = legal(g, m, f.inCheck); PE(8)
                if (!ok) continue;
                PB(3) do_move(g, m, net, acc, tb, PF_QSEARCH, true); PE(3)
                f.m = m;
                found = true;
                break;
            }
            if (found) CALL(Q_DONE, Q_ENTRY, -f.beta, -f.alpha, 0, gives_check(g, f.m))
            RETURN(f.best)
        }
        case Q_DONE: {
            int score = -f.childScore;
            PB(4) undo_move(g, f.m); PE(4)
            if (stopped) RETURN(0)
            if (score > f.best) {
                f.best = score;
                if (score > f.alpha) {
                    f.alpha = score;
                    if (score >= f.beta) RETURN(f.best)
                }
            }
            f.state = Q_LOOP;
            continue;
        }
        }
        // The running call returned ret: resume its caller, or leave if it was the root.
        if (sp == 0) {
            __syncwarp();
            g->nodes = nodes;
            g->stopped = stopped;
            __syncwarp();
            *score = ret;
            return true;
        }
        __syncwarp();
        f = g->frames[--sp];
        f.childScore = ret;
    }
}
#undef CALL
#undef RETURN
#undef COUNT_NODE

// Search::think with a node limit and one thread, over as many kernel launches as it takes.
// think_start sets up a fresh Searcher (history, killers and the move stack zeroed; the TT and the
// correction history are kept) and starts a new TT generation, and each think_run searches up to
// `budget` more nodes. Once it returns true the search is over: the best move is in g->thinkBest and
// its score in g->thinkScore.
enum { T_IDLE, T_DEPTH, T_SEARCH, T_SEARCHING };

// Two int16 entries in one int, each divided by 2 toward zero (the engine's h /= 2).
__device__ __forceinline__ int halve2(int v) {
    short lo = (short)(v & 0xffff), hi = (short)(v >> 16);
    lo = lo / 2;
    hi = hi / 2;
    return (int)(((unsigned)(u16)hi << 16) | (unsigned)(u16)lo);
}
__device__ void think_start(Game* g, Tables* tb, u64 nodeLimit) {
    int lane = lane_id();
    // Search::think halves the continuation history before each search: only the marked blocks, since
    // the rest are zero. Each lane owns whole words of marks, so no two lanes touch one block.
    int4* ch = reinterpret_cast<int4*>(&tb->conthist[0][0]);
    for (int w = lane; w < CH_WORDS; w += 32) {
        unsigned marks = tb->chMask[w], keep = marks;
        for (unsigned m = marks; m; m &= m - 1) {
            int b = __ffs(m) - 1, i = w * 32 + b;
            int4 v = ch[i];
            int4 h = make_int4(halve2(v.x), halve2(v.y), halve2(v.z), halve2(v.w));
            ch[i] = h;
            if (!(h.x | h.y | h.z | h.w)) keep &= ~(1u << b);
        }
        if (keep != marks) tb->chMask[w] = keep;
    }
    __syncwarp();
    for (int i = lane; i < MAX_PLY + 1; i += 32) g->pieceStack[i] = 0;
    for (int i = lane; i < MAX_PLY + 1; i += 32) g->evalStack[i] = 0;
    for (int i = lane; i < 2 * 64 * 64; i += 32) (&g->history[0][0][0])[i] = 0;
    for (int i = lane; i < (MAX_PLY + 1) * 2; i += 32) (&g->killers[0][0])[i] = 0;
    for (int i = lane; i < MAX_PLY + 1; i += 32) g->moveStack[i] = 0;
    for (int i = lane; i < MAX_PLY + 2; i += 32) g->doubleExt[i] = 0;
    int stm = g->stm;
    unsigned gen = tb->gen;
    __syncwarp();
    tb->gen = gen + 1; // TT.new_search()
    g->nodes = 0;
    g->nodeLimit = nodeLimit;
    g->stopped = 0;
    g->rootPv = 0;
    g->rootBest = MOVE_NONE;
    g->rootStm = stm;
    g->thinkBest = MOVE_NONE;
    g->thinkScore = 0;
    g->thinkDepth = 1;
    g->thinkState = T_DEPTH;
    __syncwarp();
}

__device__ bool think_run(Game* g, const Net& net, const Params& p, short* acc, Tables* tb, u64 budget) {
    __syncwarp();
    u64 stopAt = g->nodes + budget;
    int state = g->thinkState, depth = g->thinkDepth, bestScore = g->thinkScore;
    int alpha = g->aspAlpha, beta = g->aspBeta, delta = g->aspDelta;
    u16 best = g->thinkBest;
    while (true) {
        if (state == T_DEPTH) { // for (depth = 1; depth <= MAX_PLY - 1; ++depth): search_root(depth, bestScore)
            if (depth > MAX_PLY - 1) break;
            delta = p.aspDelta;
            alpha = -VALUE_INF;
            beta = VALUE_INF;
            if (depth >= p.aspDepth) {
                alpha = max(bestScore - delta, -VALUE_INF);
                beta = min(bestScore + delta, VALUE_INF);
            }
            state = T_SEARCH;
        }
        if (state == T_SEARCH) { // search(alpha, beta, depth, 0)
            Frame root = new_call(S_ENTRY, alpha, beta, depth, 0, in_check(g));
            __syncwarp();
            g->cur = root;
            g->sp = 0;
            g->thinkDepth = depth; // rootDepth: singular extensions stop at twice this ply
            __syncwarp();
            state = T_SEARCHING;
        }
        int score;
        if (!search_run(g, net, p, acc, tb, stopAt, &score)) {
            __syncwarp();
            g->thinkState = state;
            g->thinkDepth = depth;
            g->thinkScore = bestScore;
            g->aspAlpha = alpha;
            g->aspBeta = beta;
            g->aspDelta = delta;
            g->thinkBest = best;
            __syncwarp();
            return false;
        }
        if (g->stopped) break;
        // search_root: widen a failed aspiration window and search again
        if (score <= alpha || score >= beta) {
            if (score <= alpha) alpha = max(score - delta, -VALUE_INF);
            else beta = min(score + delta, VALUE_INF);
            delta *= 2;
            state = T_SEARCH;
            continue;
        }
        if (g->rootPv) best = g->rootBest;
        bestScore = score;
        ++depth;
        state = T_DEPTH;
    }
    if (best == MOVE_NONE) best = first_legal_move(g, net, acc, 0);
    __syncwarp();
    g->thinkBest = best;
    g->thinkScore = bestScore;
    g->thinkState = T_IDLE;
    __syncwarp();
    return true;
}

// ---- Game loop (src/datagen.cpp, play_game after the random opening) ----
__device__ bool is_noisy(const Game* g, u16 m) {
    int t = m & (3 << 14);
    return g->board[(m >> 6) & 63] != NO_PIECE || t == M_EN_PASSANT || t == M_PROMOTION;
}

// Sets up each game's accumulator and clears its TT and correction history (Search::clear()); the host
// has written the position, its single state and the counters.
extern "C" __global__ void datagen_setup(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                          short* accs, Tables* tables) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    clear_tables(tables + w);
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    g->accTop = 0;
    __syncwarp();
    refresh(g, net, acc_slot(acc, 0));
    __syncwarp();
}

// Plays one ply of every unfinished game.
extern "C" __global__ void datagen_step(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                         const Params* params, short* accs, Tables* tables, unsigned long long nodes,
                                         unsigned long long budget) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->done) return;
    PB(10)
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    Tables* tb = tables + w;
    if (g->thinkState == T_IDLE) { // a new ply
        if (g->ply >= MAX_PLIES) { g->result = 0.5f; g->done = 1; return; }
        if (first_legal_move(g, net, acc, 0) == MOVE_NONE) {
            g->result = in_check(g) ? (g->stm == 0 ? 0.0f : 1.0f) : 0.5f;
            g->done = 1;
            return;
        }
        if (is_draw(g)) { g->result = 0.5f; g->done = 1; return; }
        int ev = evaluate(g, net, acc);
        __syncwarp();
        g->rootEval = g->stm == 0 ? ev : -ev;
        think_start(g, tb, nodes);
    }
    if (!think_run(g, net, *params, acc, tb, budget)) {
        PE(10)
        return;
    }
    int whiteEval = g->rootEval, score = g->thinkScore;
    u16 best = g->thinkBest;
    int whiteScore = g->stm == 0 ? score : -score;
    int pl0 = g->ply;
    g->lastBest = best; g->lastScore = score; g->lastNodes = (int)g->nodes;
    g->plyBest[pl0] = best; g->plyScore[pl0] = score; g->plyNodes[pl0] = (int)g->nodes;
    __syncwarp();
    if (!in_check(g) && !is_noisy(g, best) && abs(score) < VALUE_MATE_IN_MAX_PLY && g->nsamples < MAX_SAMPLES) {
        Sample* s = g->samples + g->nsamples;
        int lane = lane_id();
        for (int i = lane; i < 64; i += 32) s->board[i] = g->board[i];
        const StateInfo& st = g->states[g->nstates - 1];
        s->stm = g->stm; s->castling = st.castling; s->ep = st.ep; s->rule50 = st.rule50; s->fullmove = g->fullmove;
        s->score = whiteScore; s->eval = whiteEval;
        int ns = g->nsamples;
        __syncwarp();
        g->nsamples = ns + 1;
        __syncwarp();
    }
    int ws = g->winStreak;
    if (whiteScore >= WIN_SCORE) ws = ws > 0 ? ws + 1 : 1;
    else if (whiteScore <= -WIN_SCORE) ws = ws < 0 ? ws - 1 : -1;
    else ws = 0;
    __syncwarp();
    g->winStreak = ws;
    if (ws >= WIN_PLIES) { g->result = 1.0f; g->done = 1; return; }
    if (ws <= -WIN_PLIES) { g->result = 0.0f; g->done = 1; return; }
    do_move(g, best, net, acc);
    // Keep only the new position's accumulator, in slot 0 (the values are the same at any depth).
    short* top = acc_slot(acc, g->accTop);
    int base = LANE_BASE;
    for (int persp = 0; persp < 2; ++persp)
        for (int c = 0; c < UNITS; c += 8) store8(acc + persp * H + UOFF(c), load8(top + persp * H + UOFF(c)));
    int pl = g->ply;
    __syncwarp();
    g->accTop = 0;
    g->ply = pl + 1;
    __syncwarp();
    PE(10)
}

// Rescoring (gpu/datagen.py rescore, as gpu/ref.cpp's score mode): one search per position from a cold
// start: datagen_setup has cleared the game's tables, think_start gives a fresh Searcher, and the search's
// score goes to scores[], White-relative. The game is then done.
extern "C" __global__ void score_step(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                      const Params* params, short* accs, Tables* tables, unsigned long long nodes,
                                      unsigned long long budget, int* scores) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->done) return;
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    Tables* tb = tables + w;
    if (g->thinkState == T_IDLE) think_start(g, tb, nodes);
    if (!think_run(g, net, *params, acc, tb, budget)) return;
    int score = g->thinkScore, white = g->stm == 0 ? score : -score;
    __syncwarp();
    if (lane_id() == 0) scores[w] = white;
    g->done = 1;
    __syncwarp();
}

// ---- Host interface ----
extern "C" __global__ void datagen_sizes(int* out) {
    out[0] = sizeof(Game);
    out[1] = sizeof(Sample);
    out[2] = sizeof(TTEntry);
    out[3] = sizeof(Params);
    out[4] = sizeof(Tables);
}

// Position::set from a compact start position: 64 piece codes (0-11 as make_piece, 12 empty, a1 first),
// then side to move, castling rights, en passant square (64 none), rule50, fullmove (2 bytes).
// The key is Position::compute_key. One thread per game.
#define START_BYTES 72
__device__ void init_game(Game* g, const u8* p) {
    for (int t = 0; t < 6; ++t) g->byType[t] = 0;
    g->byColor[0] = g->byColor[1] = 0;
    u64 key = 0;
    for (int sq = 0; sq < 64; ++sq) {
        int pc = p[sq];
        g->board[sq] = pc;
        if (pc != NO_PIECE) {
            g->byType[type_of(pc)] |= bit(sq);
            g->byColor[color_of(pc)] |= bit(sq);
            key ^= Z_PSQ[pc][sq];
        }
    }
    int stm = p[64], castling = p[65], ep = p[66], rule50 = p[67], fullmove = p[68] | (p[69] << 8);
    key ^= Z_CASTLING[castling];
    if (ep != SQ_NONE) key ^= Z_EP[ep & 7];
    if (stm == 1) key ^= Z_SIDE[0];
    g->stm = stm;
    g->fullmove = fullmove;
    g->nstates = 1;
    StateInfo st;
    st.key = key; st.castling = castling; st.ep = ep; st.rule50 = rule50; st.captured = NO_PIECE; st.pliesFromNull = 0; st.pad = 0;
    g->states[0] = st;
    g->accTop = 0;
    g->thinkState = T_IDLE;
    g->winStreak = 0; g->ply = 0; g->done = 0; g->nsamples = 0; g->result = 0.5f;
    for (int k = 0; k < P_COUNT; ++k) g->prof[k] = 0;
}
extern "C" __global__ void datagen_init(Game* games, int n, const u8* start) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) init_game(games + i, start + (size_t)i * START_BYTES);
}

// Copies each game's state and samples out to flat arrays.
extern "C" __global__ void datagen_collect(const Game* games, int n, int* done, float* result, int* nsamples, int* plies,
                                           Sample* samples, int* plyLog) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    const Game* g = games + i;
    done[i] = g->done; result[i] = g->result; nsamples[i] = g->nsamples; plies[i] = g->ply;
    for (int k = 0; k < g->nsamples; ++k) samples[(size_t)i * MAX_SAMPLES + k] = g->samples[k];
    for (int k = 0; k < g->ply && k < MAX_PLIES; ++k) {
        int* l = plyLog + ((size_t)i * MAX_PLIES + k) * 3;
        l[0] = g->plyBest[k]; l[1] = g->plyScore[k]; l[2] = g->plyNodes[k];
    }
}

extern "C" __global__ void datagen_done(const Game* games, int n, int* done) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) done[i] = games[i].done;
}

// ---- Continuous generation: reset finished slots with fresh random openings ----
__device__ __forceinline__ u64 splitmix64(u64& x) {
    u64 z = (x += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

// For each listed slot: the start position, then randomPlies random legal moves (as src/datagen.cpp,
// with its own RNG seeded by the game's id), a fresh accumulator and cleared tables. A game whose
// opening runs out of legal moves is marked done with result -1 and gets no samples.
extern "C" __global__ void datagen_opening(Game* games, const int* slots, int k, const u8* start, const u64* ids, u64 seed,
                                           int randomPlies, const short* ftw, const short* ftb, const short* outw, int outb,
                                           short* accs, Tables* tables) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = lane_id();
    if (w >= k) return;
    Net net = {ftw, ftb, outw, outb};
    int slot = slots[w];
    Game* g = games + slot;
    short* acc = accs + (size_t)slot * ACC_SLOTS * 2 * H;
    if (lane == 0) init_game(g, start);
    __syncwarp();
    u64 rng = seed ^ (ids[w] * 0xD1B54A32D192ED03ULL);
    bool dead = false;
    for (int i = 0; i < randomPlies && !dead; ++i) {
        u16* list = g->moves[0];
        u16* legal = g->quiets[0];
        int n = generate(g, list, false), nl = 0;
        __syncwarp();
        for (int j = 0; j < n; ++j) {
            u16 m = list[j];
            bool ok = do_move(g, m, net, acc);
            undo_move(g, m);
            if (ok) {
                legal[nl++] = m;
                __syncwarp();
            }
        }
        if (nl == 0) {
            dead = true;
            break;
        }
        u16 m = legal[splitmix64(rng) % (u64)nl];
        do_move(g, m, net, acc);
        __syncwarp();
    }
    clear_tables(tables + slot);
    g->accTop = 0;
    __syncwarp();
    refresh(g, net, acc_slot(acc, 0));
    __syncwarp();
    if (dead) {
        g->done = 1;
        g->result = -1.0f;
    }
    __syncwarp();
}

// Copies the listed (finished) slots' results and samples out.
extern "C" __global__ void datagen_collect_slots(const Game* games, const int* slots, int k, float* result, int* nsamples,
                                                 Sample* samples, int* nodes) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= k) return;
    const Game* g = games + slots[i];
    result[i] = g->result;
    nsamples[i] = g->nsamples;
    int total = 0;
    for (int p = 0; p < g->ply && p < MAX_PLIES; ++p) total += g->plyNodes[p];
    nodes[i] = total;
    for (int j = 0; j < g->nsamples; ++j) samples[(size_t)i * MAX_SAMPLES + j] = g->samples[j];
}

extern "C" __global__ void datagen_profile(const Game* games, int n, long long* out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n)
        for (int k = 0; k < P_COUNT; ++k) out[(size_t)i * P_COUNT + k] = games[i].prof[k];
}

// ---- Matches: network A against network B at a fixed node count (issue #31, testing) ----
// Each side keeps its own TT, as two engines would; the side to move refreshes its accumulator with
// its own network at every ply. Games end as in our fastchess SPRTs: checkmate, stalemate, threefold
// repetition, the fifty-move rule, insufficient material, or adjudication (resign when the scores
// from White's view stay at 400 or more, or -400 or less, for 6 plies running, i.e. 3 moves of each
// engine; a draw from move 40 when |score| <= 10 for 16 plies running); 600 plies is a draw.
__device__ bool insufficient(const Game* g) {
    u64 heavy = g->byType[PAWN] | g->byType[ROOK] | g->byType[QUEEN];
    return !heavy && __popcll(g->byType[KNIGHT] | g->byType[BISHOP]) <= 1;
}
__device__ bool threefold(Game* g) {
    __syncwarp();
    int n = g->nstates;
    const StateInfo& st = g->states[n - 1];
    u64 key = st.key;
    int lookback = min(st.rule50, n - 1), count = 0;
    for (int i = 4 + 2 * lane_id(); i <= lookback; i += 64)
        if (g->states[n - 1 - i].key == key) ++count;
    for (int off = 16; off; off >>= 1) count += __shfl_xor_sync(0xffffffffu, count, off);
    return count >= 2;
}

// Starts a game in each of k slots: from start[i], with network A playing aColor[i].
extern "C" __global__ void match_init(Game* games, const int* slots, int k, const u8* start, const int* aColor) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= k) return;
    Game* g = games + slots[i];
    init_game(g, start + (size_t)i * START_BYTES);
    g->aColor = aColor[i];
    g->resignPlies = g->drawPlies = 0;
    g->matchResult = -1;
}

// Clears both sides' tables in each of k slots (ucinewgame).
extern "C" __global__ void match_setup(const int* slots, int k, Tables* tablesA, Tables* tablesB) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= k) return;
    clear_tables(tablesA + slots[w]);
    clear_tables(tablesB + slots[w]);
}

// Whether network A is to move in g: at the root of the search under way, or in the position if none is.
__device__ __forceinline__ bool a_to_move(const Game* g) {
    return (g->thinkState == T_IDLE ? g->stm : g->rootStm) == g->aColor;
}

// One kernel launch's share of game g's current ply, for the side to move: its network, constants and tables.
__device__ void match_ply(Game* g, const Net& net, const Params& p, short* acc, Tables* tb, unsigned long long nodes,
                          unsigned long long budget) {
    bool idle = g->thinkState == T_IDLE; // otherwise a search is under way, in some position of its tree
    int result = -1;
    if (idle) { // a new ply
        if (first_legal_move(g, net, acc, 0) == MOVE_NONE) result = in_check(g) ? (g->stm == 0 ? 0 : 2) : 1;
        else if (g->states[g->nstates - 1].rule50 >= 100 || insufficient(g) || threefold(g) || g->ply >= 600) result = 1;
        if (result >= 0) {
            __syncwarp();
            g->matchResult = result;
            __syncwarp();
            return;
        }
        __syncwarp();
        g->accTop = 0;
        __syncwarp();
        refresh(g, net, acc_slot(acc, 0)); // this side's network
        __syncwarp();
        think_start(g, tb, nodes);
    }
    if (!think_run(g, net, p, acc, tb, budget)) return;
    int score = g->thinkScore;
    u16 best = g->thinkBest;
    int whiteScore = g->stm == 0 ? score : -score;
    int rp = g->resignPlies, dp = g->drawPlies, fm = g->fullmove;
    rp = whiteScore >= 400 ? (rp > 0 ? rp + 1 : 1) : whiteScore <= -400 ? (rp < 0 ? rp - 1 : -1) : 0;
    dp = (fm >= 40 && abs(whiteScore) <= 10) ? dp + 1 : 0;
    if (rp >= 6) result = 2;
    else if (rp <= -6) result = 0;
    else if (dp >= 16) result = 1;
    __syncwarp();
    g->resignPlies = rp;
    g->drawPlies = dp;
    __syncwarp();
    if (result >= 0) {
        g->matchResult = result;
        __syncwarp();
        return;
    }
    do_move(g, best, net, acc);
    int pl = g->ply;
    __syncwarp();
    g->accTop = 0;
    g->ply = pl + 1;
    __syncwarp();
}

// A ply of every game, for whichever side is to move.
extern "C" __global__ void match_step(Game* games, int n, const short* ftwA, const short* ftbA, const short* outwA, int outbA,
                                      const short* ftwB, const short* ftbB, const short* outwB, int outbB,
                                      const Params* pa, const Params* pb, int perGame,
                                      short* accs, Tables* tablesA, Tables* tablesB, unsigned long long nodes,
                                      unsigned long long budget) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->matchResult >= 0) return;
    bool aToMove = a_to_move(g);
    Net net = aToMove ? Net{ftwA, ftbA, outwA, outbA} : Net{ftwB, ftbB, outwB, outbB};
    match_ply(g, net, (aToMove ? pa : pb)[perGame ? w : 0], accs + (size_t)w * ACC_SLOTS * 2 * H,
              (aToMove ? tablesA : tablesB) + w, nodes, budget);
}

// A ply of the games where `side` (0: A, 1: B) is to move, with that side's network, constants, accumulators,
// tables and node count; the others wait. Run once per side, from a build of each side's hidden size, it plays
// what match_step plays.
extern "C" __global__ void match_side(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                      const Params* p, int perGame, short* accs, Tables* tables, int side,
                                      unsigned long long nodes, unsigned long long budget) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->matchResult >= 0 || a_to_move(g) != (side == 0)) return;
    match_ply(g, Net{ftw, ftb, outw, outb}, p[perGame ? w : 0], accs + (size_t)w * ACC_SLOTS * 2 * H, tables + w, nodes, budget);
}

extern "C" __global__ void match_results(const Game* games, int n, int* out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = games[i].matchResult;
}
