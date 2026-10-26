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
#define TT_BITS 16     // 65,536 entries of 16 bytes: 1 MB per game, like gpu/ref.cpp
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
    u8 bound;
    u16 pad;
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
    int originalAlpha, best, legalMoves, quietCount, staticEval, n, i, r, childScore;
    u64 key;
    u16 ttMove, bestMove, m;
    bool inCheck, pvNode, root, quiet;
};

// The search's constants (src/search.cpp has them inline), so that matches can give each side its own.
// gpu/datagen.py fills in src/search.cpp's values.
struct Params {
    int rfpDepth, rfpMargin;       // reverse futility pruning: depth <= 3, staticEval - 150 * depth >= beta
    int nmpDepth, nmpBase, nmpDiv; // null move: depth >= 3, R = 3 + depth / 6
    int lmpDepth, lmpBase;         // late move pruning: depth <= 8, quietCount >= 3 + depth * depth
    int futDepth, futMargin;       // futility pruning: depth <= 6, staticEval + 120 * depth <= alpha
    int lmrDepth, lmrMoves;        // late move reductions: depth >= 3, legalMoves > 3
    int histMax;                   // history bonus min(depth * depth, 1200)
    int aspDepth, aspDelta;        // aspiration windows from depth 5, delta 25
    int qsSee;                     // quiescence skips captures that fail see_ge(m, 0)
    u8 lmr[64][64];                // the reduction: int(0.75 + log(depth) * log(moves) / 2.25)
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
    int history[2][64][64];
    Frame frames[MAX_PLY + 1];
    u16 moves[MAX_PLY + 1][256];
    int scores[MAX_PLY + 1][256];
    u16 quiets[MAX_PLY + 1][256];
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
__device__ __forceinline__ u64 diag_mask(int s) {
    int d = (s >> 3) - (s & 7);
    u64 m = 0x8040201008040201ULL;
    return (d >= 0 ? m << (8 * d) : m >> (-8 * d)) ^ bit(s);
}
__device__ __forceinline__ u64 anti_mask(int s) {
    int d = (s >> 3) + (s & 7) - 7;
    u64 m = 0x0102040810204080ULL;
    return (d >= 0 ? m << (8 * d) : m >> (-8 * d)) ^ bit(s);
}
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
__device__ __forceinline__ u64 pawn_att(int s, int c) {
    u64 b = bit(s);
    return c == 0 ? ((b << 9) & NOT_A) | ((b << 7) & NOT_H) : ((b >> 7) & NOT_A) | ((b >> 9) & NOT_H);
}
__device__ __forceinline__ u64 attacks_bb(int pt, int s, u64 occ) {
    switch (pt) {
        case KNIGHT: return knight_att(bit(s));
        case BISHOP: return bishop_att(s, occ);
        case ROOK: return rook_att(s, occ);
        case QUEEN: return bishop_att(s, occ) | rook_att(s, occ);
        default: return king_att(bit(s));
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
    return (pawn_att(s, by ^ 1) & pcs(g, by, PAWN)) || (knight_att(bit(s)) & pcs(g, by, KNIGHT))
        || (king_att(bit(s)) & pcs(g, by, KING))
        || (bishop_att(s, occ) & (pcs(g, by, BISHOP) | pcs(g, by, QUEEN)))
        || (rook_att(s, occ) & (pcs(g, by, ROOK) | pcs(g, by, QUEEN)));
}
__device__ __forceinline__ bool in_check(const Game* g) { return attacked(g, king_sq(g, g->stm), g->stm ^ 1); }

// ---- NNUE (one warp per game; this lane's units) ----
__device__ __forceinline__ short* acc_slot(short* acc, int slot) { return acc + (size_t)slot * 2 * H; }
__device__ __forceinline__ int feat(int persp, int p, int s) { // White's view, or Black's (colors swapped, ranks flipped)
    return persp == 0 ? p * 64 + s : ((color_of(p) ^ 1) * 6 + type_of(p)) * 64 + (s ^ 56);
}
// A lane's units move in groups of 8 int16 values, one 16-byte load or store each (rows and
// accumulators are 16-byte aligned). __vadd2 and __vsub2 add two int16 values per 32-bit word with
// the same wrap-around as (short)(a + b).
static_assert(UNITS % 8 == 0, "each lane's units must be whole groups of 8");
__device__ __forceinline__ uint4 load8(const short* p) { return *(const uint4*)p; }
__device__ __forceinline__ void store8(short* p, uint4 v) { *(uint4*)p = v; }
__device__ __forceinline__ uint4 add8(uint4 a, uint4 b) {
    return make_uint4(__vadd2(a.x, b.x), __vadd2(a.y, b.y), __vadd2(a.z, b.z), __vadd2(a.w, b.w));
}
__device__ __forceinline__ uint4 sub8(uint4 a, uint4 b) {
    return make_uint4(__vsub2(a.x, b.x), __vsub2(a.y, b.y), __vsub2(a.z, b.z), __vsub2(a.w, b.w));
}

__device__ void refresh(const Game* g, const Net& net, short* a) {
    int base = lane_id() * UNITS;
    for (int persp = 0; persp < 2; ++persp) {
        for (int c = 0; c < UNITS; c += 8) {
            uint4 v = load8(net.ftb + base + c);
            for (u64 b = occupied(g); b; b &= b - 1) {
                int s = lsb(b);
                v = add8(v, load8(net.ftw + (size_t)feat(persp, g->board[s], s) * H + base + c));
            }
            store8(a + persp * H + base + c, v);
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
__device__ void apply_delta(const Net& net, const short* from, short* to, const Delta& d) {
    int base = lane_id() * UNITS;
    for (int c = 0; c < UNITS; c += 8) {
        // Every load first, both perspectives and all (up to 4) features, so their latencies overlap.
        uint4 v[2], w[2][4];
#pragma unroll
        for (int persp = 0; persp < 2; ++persp) {
            v[persp] = load8(from + persp * H + base + c);
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) w[persp][k] = load8(net.ftw + (size_t)feat(persp, d.piece[k], d.sq[k]) * H + base + c);
        }
#pragma unroll
        for (int persp = 0; persp < 2; ++persp) {
#pragma unroll
            for (int k = 0; k < 4; ++k)
                if (k < d.n) v[persp] = k % 2 ? add8(v[persp], w[persp][k]) : sub8(v[persp], w[persp][k]);
            store8(to + persp * H + base + c, v[persp]);
        }
    }
}
// NNUE::evaluate: the side to move's view first, SCReLU, int16 v * w times v, truncating divisions.
__device__ int evaluate(const Game* g, const Net& net, const short* acc) {
    const short* a = acc_slot((short*)acc, g->accTop);
    int base = lane_id() * UNITS, part = 0;
    for (int half = 0; half < 2; ++half) {
        int persp = half == 0 ? g->stm : g->stm ^ 1;
        for (int c = 0; c < UNITS; c += 8) {
            uint4 av = load8(a + persp * H + base + c), wv = load8(net.outw + half * H + base + c);
            unsigned aw[4] = {av.x, av.y, av.z, av.w}, ww[4] = {wv.x, wv.y, wv.z, wv.w};
            for (int j = 0; j < 8; ++j) { // unit j of the group: half j % 2 of word j / 2
                int v = min(max((int)(short)(aw[j / 2] >> (16 * (j % 2))), 0), QA);
                int vw = (short)(v * (short)(ww[j / 2] >> (16 * (j % 2))));
                part += vw * v;
            }
        }
    }
    long long sum = part;
    for (int off = 16; off; off >>= 1) sum += __shfl_xor_sync(0xffffffffu, sum, off);
    sum = sum / QA + net.outb;
    return (int)(sum * EVAL_SCALE / (QA * QB));
}

// Board edits on local copies of the bitboards. All lanes take the same snapshot after a
// __syncwarp(), compute the same result, and only then write it, so no lane can see another's
// half-done update (the lanes of a warp are not guaranteed to run in lockstep). The copies are only
// ever indexed by constants (the loops unroll): an index known only at run time would put them in
// local memory, a copy per lane.
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

// Position::do_move: plays a pseudo-legal move and returns whether it was legal.
__device__ bool do_move(Game* g, u16 m, const Net& net, short* acc) {
    __syncwarp();
    int n = g->nstates, top = g->accTop, us = g->stm, them = us ^ 1, fm = g->fullmove;
    StateInfo st = g->states[n - 1];
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14);
    int pc = g->board[from];
    Board b;
    b_load(g, b);
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
        b_xor(b, pc, bit(from) | bit(to));
        b_xor(b, rook, bit(rookFrom) | bit(rookTo));
        d.piece[2] = rook; d.sq[2] = rookFrom;
        d.piece[3] = rook; d.sq[3] = rookTo;
        d.n = 4;
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to] ^ Z_PSQ[rook][rookFrom] ^ Z_PSQ[rook][rookTo];
    } else {
        if (type == M_EN_PASSANT) capSq = us == 0 ? to - 8 : to + 8;
        int captured = g->board[capSq];
        if (captured != NO_PIECE) {
            b_xor(b, captured, bit(capSq));
            d.piece[2] = captured; d.sq[2] = capSq;
            d.n = 3;
            st.key ^= Z_PSQ[captured][capSq];
            st.captured = captured;
            st.rule50 = 0;
        }
        b_xor(b, pc, bit(from) | bit(to));
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to];
        if (type_of(pc) == PAWN) {
            st.rule50 = 0;
            if (type == M_PROMOTION) {
                arriving = us * 6 + ((m >> 12) & 3) + KNIGHT; // the pawn arrives as the new piece
                b_xor(b, pc, bit(to));
                b_xor(b, arriving, bit(to));
                st.key ^= Z_PSQ[pc][to] ^ Z_PSQ[arriving][to];
            } else if (to - from == 16 || from - to == 16) {
                int ep = (from + to) / 2;
                if (pawn_att(ep, us) & (them ? b.bc[1] : b.bc[0]) & b.bt[PAWN]) {
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
    b_store(g, b);
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
    // Legal first: the caller undoes an illegal move at once, and nothing ever reads its
    // accumulator, so it is only computed for legal ones (about a quarter of updates are not).
    bool legal = !attacked(g, king_sq(g, us), them);
    if (legal) apply_delta(net, acc_slot(acc, top), acc_slot(acc, top + 1), d);
    __syncwarp();
    return legal;
}

__device__ void undo_move(Game* g, u16 m) {
    __syncwarp();
    int n = g->nstates, top = g->accTop, us = g->stm ^ 1, fm = g->fullmove;
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14);
    int captured = g->states[n - 1].captured;
    Board b;
    b_load(g, b);
    int moved = g->board[to], back = moved, capSq = to, rookFrom = SQ_NONE, rookTo = SQ_NONE, rook = NO_PIECE;
    if (type == M_CASTLING) {
        bool kingside = to > from;
        rookFrom = kingside ? from + 3 : from - 4;
        rookTo = kingside ? from + 1 : from - 1;
        rook = g->board[rookTo];
        b_xor(b, moved, bit(to) | bit(from));
        b_xor(b, rook, bit(rookTo) | bit(rookFrom));
    } else {
        if (type == M_PROMOTION) {
            back = us * 6 + PAWN; // the new piece goes, a pawn returns
            b_xor(b, moved, bit(to));
            b_xor(b, back, bit(to));
        }
        b_xor(b, back, bit(to) | bit(from));
        if (captured != NO_PIECE) {
            if (type == M_EN_PASSANT) capSq = us == 0 ? to - 8 : to + 8;
            b_xor(b, captured, bit(capSq));
        }
    }
    __syncwarp();
    b_store(g, b);
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

// Counters shared by the warp: read, sync, write, sync.
__device__ __forceinline__ void count_node(Game* g) {
    __syncwarp();
    u64 v = g->nodes + 1;
    __syncwarp();
    g->nodes = v;
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
__device__ int generate(Game* g, u16* list, bool noisy) {
    int us = g->stm, them = us ^ 1, n = 0;
    u64 pawns = pcs(g, us, PAWN), empty = ~occupied(g), enemies = g->byColor[them];
    u64 seventh = us == 0 ? 0x00FF000000000000ULL : 0xFF00ULL, third = us == 0 ? 0xFF0000ULL : 0xFF0000000000ULL;
    int up = us == 0 ? 8 : -8;
#define PUSH(b) (us == 0 ? (b) << 8 : (b) >> 8)
    if (!noisy) {
        u64 single = PUSH(pawns & ~seventh) & empty, twice = PUSH(single & third) & empty;
        for (; single; single &= single - 1) { int to = lsb(single); add(list, n, to - up, to, 0, KNIGHT); }
        for (; twice; twice &= twice - 1) { int to = lsb(twice); add(list, n, to - 2 * up, to, 0, KNIGHT); }
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
    for (int pt = KNIGHT; pt <= KING; ++pt)
        for (u64 b = pcs(g, us, pt); b; b &= b - 1) {
            int from = lsb(b);
            for (u64 a = attacks_bb(pt, from, occ) & targets; a; a &= a - 1) add(list, n, from, lsb(a), 0, KNIGHT);
        }
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

// ---- TT (src/tt.cpp: one entry per index, always replace, keep the old move) ----
__device__ __forceinline__ TTEntry* tt_entry(TTEntry* tt, u64 key) { return tt + (key >> (64 - TT_BITS)); }
__device__ __forceinline__ int score_to_tt(int s, int ply) {
    return s >= VALUE_MATE_IN_MAX_PLY ? s + ply : s <= -VALUE_MATE_IN_MAX_PLY ? s - ply : s;
}
__device__ __forceinline__ int score_from_tt(int s, int ply) {
    return s >= VALUE_MATE_IN_MAX_PLY ? s - ply : s <= -VALUE_MATE_IN_MAX_PLY ? s + ply : s;
}
__device__ void tt_store(TTEntry* tt, u64 key, u16 move, int score, int depth, int bound) {
    TTEntry* e = tt_entry(tt, key);
    __syncwarp();
    TTEntry old = *e;
    if (move == MOVE_NONE && old.key == key) move = old.move;
    TTEntry n;
    n.key = key; n.move = move; n.score = (short)score; n.depth = (signed char)depth; n.bound = (u8)bound; n.pad = 0;
    __syncwarp();
    *e = n;
    __syncwarp();
}

// ---- Search (src/search.cpp) ----
__constant__ int PIECE_VALUE[7] = {100, 320, 330, 500, 900, 0, 0};
__constant__ int SEE_VALUE[6] = {100, 320, 330, 500, 900, 20000};

__device__ __forceinline__ void check_limits(Game* g) {
    if ((g->nodes & 1023) != 0) return;
    if (g->nodeLimit && g->nodes >= g->nodeLimit) g->stopped = 1;
}
__device__ __forceinline__ bool is_quiet(const Game* g, u16 m) {
    int t = m & (3 << 14);
    return g->board[(m >> 6) & 63] == NO_PIECE && t != M_EN_PASSANT && t != M_PROMOTION;
}
__device__ void score_moves(Game* g, const u16* list, int n, int* scores, u16 ttMove, int ply) {
    __syncwarp();
    for (int i = lane_id(); i < n; i += 32) { // every lane scores every 32nd move
        u16 m = list[i];
        int from = m & 63, to = (m >> 6) & 63, t = m & (3 << 14), s;
        if (m == ttMove) s = 1000000;
        else if (t == M_EN_PASSANT) s = 100000 + PIECE_VALUE[PAWN] * 10 - PAWN;
        else if (g->board[to] != NO_PIECE) s = 100000 + PIECE_VALUE[type_of(g->board[to])] * 10 - type_of(g->board[from]);
        else if (t == M_PROMOTION && ((m >> 12) & 3) + KNIGHT == QUEEN) s = 90000;
        else if (ply >= 0 && m == g->killers[ply][0]) s = 80000;
        else if (ply >= 0 && m == g->killers[ply][1]) s = 70000;
        else if (ply >= 0) s = g->history[g->stm][from][to];
        else s = 0;
        scores[i] = s;
    }
    __syncwarp();
}
__device__ void update_history(Game* g, u16 m, int bonus) {
    int& h = g->history[g->stm][m & 63][(m >> 6) & 63];
    int v = h;
    v += bonus - v * abs(bonus) / 16384;
    __syncwarp();
    h = v;
    __syncwarp();
}
__device__ u16 pick_move(u16* list, int* scores, int n, int i) {
    __syncwarp();
    int bestS = -2147483647 - 1, bestJ = n;
    for (int j = i + lane_id(); j < n; j += 32) {
        int sj = scores[j];
        if (sj > bestS) { bestS = sj; bestJ = j; } // a lane's first maximum: its indices only grow
    }
    for (int off = 16; off; off >>= 1) {
        int s2 = __shfl_xor_sync(0xffffffffu, bestS, off), j2 = __shfl_xor_sync(0xffffffffu, bestJ, off);
        if (s2 > bestS || (s2 == bestS && j2 < bestJ)) { bestS = s2; bestJ = j2; }
    }
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
                  | (knight_att(bit(to)) & g->byType[KNIGHT]) | (king_att(bit(to)) & g->byType[KING])
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
            case KNIGHT: targets = knight_att(bit(s)) & ~own; break;
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
enum { S_ENTRY, S_NULL_DONE, S_MOVES, S_LOOP, S_FIRST_DONE, S_RED_DONE, S_FULL_DONE, S_PV_DONE, Q_ENTRY, Q_LOOP, Q_DONE };

__device__ __forceinline__ Frame new_call(int state, int alpha, int beta, int depth, int ply) {
    Frame f = {};
    f.state = state;
    f.alpha = alpha;
    f.beta = beta;
    f.depth = depth;
    f.ply = ply;
    return f;
}

// Call a child at ply + 1 (starting in ENTRY) and resume this call in RESUME when it returns.
#define CALL(RESUME, ENTRY, A, B, D)                     \
    {                                                     \
        f.state = RESUME;                                 \
        __syncwarp();                                     \
        g->frames[sp++] = f;                              \
        f = new_call(ENTRY, A, B, D, f.ply + 1);          \
        continue;                                         \
    }
// Return V from the running call.
#define RETURN(V)  \
    {              \
        ret = (V); \
        break;     \
    }

// Runs search(alpha, beta, depth, 0) and everything below it, in the same order as the recursive
// code, from the root call think_run put in g->cur. Returns true when the root call returns, with its
// score in *score, or false once the node count reaches stopAt: the running call goes back to g->cur,
// and the next call carries on from it.
__device__ bool search_run(Game* g, const Net& net, const Params& p, short* acc, TTEntry* tt, u64 stopAt, int* score) {
    __syncwarp();
    Frame f = g->cur;
    int sp = g->sp, ret = 0;
    while (true) {
        if (g->nodes >= stopAt) {
            __syncwarp();
            g->cur = f;
            g->sp = sp;
            __syncwarp();
            return false;
        }
        switch (f.state) {
        case S_ENTRY: {
            PB(8) f.inCheck = in_check(g); PE(8)
            if (f.inCheck) ++f.depth;
            if (f.depth <= 0) { // return qsearch(alpha, beta, ply)
                f.state = Q_ENTRY;
                continue;
            }
            count_node(g);
            check_limits(g);
            __syncwarp();
            if (g->stopped) RETURN(0)
            f.root = f.ply == 0;
            f.pvNode = f.beta - f.alpha > 1;
            if (f.root) g->rootPv = 0; // pvLength[0] = 0
            if (!f.root) {
                PB(9) bool draw = is_draw(g); PE(9)
                if (draw) RETURN(0)
                if (f.ply >= MAX_PLY - 1) RETURN(evaluate(g, net, acc))
            }
            f.key = g->states[g->nstates - 1].key;
            PB(6) TTEntry e = *tt_entry(tt, f.key); PE(6)
            bool hit = e.key == f.key && e.bound != BOUND_NONE;
            f.ttMove = hit ? e.move : MOVE_NONE;
            if (hit && !f.pvNode && e.depth >= f.depth) {
                int ttScore = score_from_tt(e.score, f.ply);
                if (e.bound == BOUND_EXACT || (e.bound == BOUND_LOWER && ttScore >= f.beta) || (e.bound == BOUND_UPPER && ttScore <= f.alpha))
                    RETURN(ttScore)
            }
            PB(5) f.staticEval = f.inCheck ? -VALUE_INF : evaluate(g, net, acc); PE(5)
            int us = g->stm;
            if (!f.root && !f.pvNode && !f.inCheck && f.depth <= p.rfpDepth && g->states[g->nstates - 1].rule50 + f.depth < 100
                && abs(f.beta) < VALUE_MATE_IN_MAX_PLY && (g->byColor[us] & ~(g->byType[PAWN] | g->byType[KING]))) {
                if (abs(f.staticEval) < VALUE_MATE_IN_MAX_PLY && f.staticEval - p.rfpMargin * f.depth >= f.beta)
                    RETURN(has_legal_move(g, net, acc, f.ply) ? f.staticEval : 0)
            }
            bool hasPieces = (g->byColor[us] & ~g->byType[PAWN] & ~g->byType[KING]) != 0;
            if (!f.pvNode && !f.inCheck && !f.root && f.depth >= p.nmpDepth && hasPieces && g->moveStack[f.ply - 1] != MOVE_NONE && f.staticEval >= f.beta) {
                int R = p.nmpBase + f.depth / p.nmpDiv;
                g->moveStack[f.ply] = MOVE_NONE;
                __syncwarp();
                do_null_move(g);
                CALL(S_NULL_DONE, S_ENTRY, -f.beta, -f.beta + 1, f.depth - 1 - R)
            }
            f.state = S_MOVES;
            continue;
        }
        case S_NULL_DONE: {
            int score = -f.childScore;
            undo_null_move(g);
            if (g->stopped) RETURN(0)
            if (score >= f.beta) RETURN(score >= VALUE_MATE_IN_MAX_PLY ? f.beta : score)
            f.state = S_MOVES;
            continue;
        }
        case S_MOVES: {
            PB(0) f.n = generate(g, g->moves[f.ply], false);
            __syncwarp(); PE(0)
            PB(1) score_moves(g, g->moves[f.ply], f.n, g->scores[f.ply], f.ttMove, f.ply); PE(1)
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
            u16* list = g->moves[f.ply];
            int* scores = g->scores[f.ply];
            bool found = false;
            while (f.i < f.n) {
                PB(2) u16 m = pick_move(list, scores, f.n, f.i); PE(2)
                ++f.i;
                bool quiet = is_quiet(g, m);
                if (!f.pvNode && !f.inCheck && quiet && f.depth <= p.lmpDepth && f.best > -VALUE_MATE_IN_MAX_PLY && f.quietCount >= p.lmpBase + f.depth * f.depth) continue;
                if (!f.pvNode && !f.inCheck && quiet && f.depth <= p.futDepth && f.best > -VALUE_MATE_IN_MAX_PLY && f.staticEval + p.futMargin * f.depth <= f.alpha) continue;
                PB(3) bool legal = do_move(g, m, net, acc); PE(3)
                if (!legal) {
                    PB(4) undo_move(g, m); PE(4)
                    continue;
                }
                ++f.legalMoves;
                g->moveStack[f.ply] = m;
                __syncwarp();
                f.m = m;
                f.quiet = quiet;
                found = true;
                break;
            }
            if (found) {
                if (f.legalMoves == 1) CALL(S_FIRST_DONE, S_ENTRY, -f.beta, -f.alpha, f.depth - 1)
                f.r = 0;
                PB(8) bool givesCheck = f.depth >= p.lmrDepth && f.legalMoves > p.lmrMoves && f.quiet && !f.inCheck && in_check(g); PE(8)
                if (f.depth >= p.lmrDepth && f.legalMoves > p.lmrMoves && f.quiet && !f.inCheck && !givesCheck) {
                    int r = p.lmr[min(f.depth, 63)][min(f.legalMoves, 63)];
                    if (f.pvNode) --r;
                    f.r = max(0, min(r, f.depth - 2));
                }
                CALL(S_RED_DONE, S_ENTRY, -f.alpha - 1, -f.alpha, f.depth - 1 - f.r)
            }
            if (f.legalMoves == 0) RETURN(f.inCheck ? -VALUE_MATE + f.ply : 0)
            int bound = f.best >= f.beta ? BOUND_LOWER : f.alpha > f.originalAlpha ? BOUND_EXACT : BOUND_UPPER;
            { PB(6) tt_store(tt, f.key, f.bestMove, score_to_tt(f.best, f.ply), f.depth, bound); PE(6) }
            RETURN(f.best)
        }
        case S_RED_DONE: // the reduced zero-window search returned
            if (-f.childScore > f.alpha && f.r > 0) CALL(S_FULL_DONE, S_ENTRY, -f.alpha - 1, -f.alpha, f.depth - 1)
            // fall through: its score stands as the full-depth one
        case S_FULL_DONE: // the full-depth zero-window search returned
            if (-f.childScore > f.alpha && -f.childScore < f.beta) CALL(S_PV_DONE, S_ENTRY, -f.beta, -f.alpha, f.depth - 1)
            // fall through
        case S_FIRST_DONE:
        case S_PV_DONE: {
            int score = -f.childScore;
            u16 m = f.m;
            PB(4) undo_move(g, m); PE(4)
            if (g->stopped) RETURN(0)
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
                            int bonus = min(f.depth * f.depth, p.histMax);
                            update_history(g, m, bonus);
                            u16* quiets = g->quiets[f.ply];
                            for (int j = 0; j < f.quietCount; ++j) update_history(g, quiets[j], -bonus);
                        }
                        f.i = f.n; // break
                        continue;
                    }
                }
            }
            if (f.quiet) {
                g->quiets[f.ply][f.quietCount++] = m;
                __syncwarp();
            }
            continue;
        }
        case Q_ENTRY: {
            count_node(g);
            check_limits(g);
            __syncwarp();
            if (g->stopped) RETURN(0)
            PB(5) int standPat = evaluate(g, net, acc); PE(5)
            if (f.ply >= MAX_PLY - 1 || standPat >= f.beta) RETURN(standPat)
            f.alpha = max(f.alpha, standPat);
            PB(0) f.n = generate(g, g->moves[f.ply], true);
            __syncwarp(); PE(0)
            PB(1) score_moves(g, g->moves[f.ply], f.n, g->scores[f.ply], MOVE_NONE, -1); PE(1)
            f.best = standPat;
            f.i = 0;
            f.state = Q_LOOP;
        }
        // fall through
        case Q_LOOP: {
            u16* list = g->moves[f.ply];
            int* scores = g->scores[f.ply];
            bool found = false;
            while (f.i < f.n) {
                PB(2) u16 m = pick_move(list, scores, f.n, f.i); PE(2)
                ++f.i;
                PB(7) bool seeOk = see_ge(g, m, p.qsSee); PE(7)
                if (!seeOk) continue;
                PB(3) bool legal = do_move(g, m, net, acc); PE(3)
                if (!legal) {
                    PB(4) undo_move(g, m); PE(4)
                    continue;
                }
                f.m = m;
                found = true;
                break;
            }
            if (found) CALL(Q_DONE, Q_ENTRY, -f.beta, -f.alpha, 0)
            RETURN(f.best)
        }
        case Q_DONE: {
            int score = -f.childScore;
            PB(4) undo_move(g, f.m); PE(4)
            if (g->stopped) RETURN(0)
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

// Search::think with a node limit and one thread, over as many kernel launches as it takes.
// think_start sets up a fresh Searcher (history, killers and the move stack zeroed; the TT is kept),
// and each think_run searches up to `budget` more nodes. Once it returns true the search is over:
// the best move is in g->thinkBest and its score in g->thinkScore.
enum { T_IDLE, T_DEPTH, T_SEARCH, T_SEARCHING };

__device__ void think_start(Game* g, u64 nodeLimit) {
    int lane = lane_id();
    for (int i = lane; i < 2 * 64 * 64; i += 32) (&g->history[0][0][0])[i] = 0;
    for (int i = lane; i < (MAX_PLY + 1) * 2; i += 32) (&g->killers[0][0])[i] = 0;
    for (int i = lane; i < MAX_PLY + 1; i += 32) g->moveStack[i] = 0;
    int stm = g->stm;
    __syncwarp();
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

__device__ bool think_run(Game* g, const Net& net, const Params& p, short* acc, TTEntry* tt, u64 budget) {
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
            Frame root = new_call(S_ENTRY, alpha, beta, depth, 0);
            __syncwarp();
            g->cur = root;
            g->sp = 0;
            __syncwarp();
            state = T_SEARCHING;
        }
        int score;
        if (!search_run(g, net, p, acc, tt, stopAt, &score)) {
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

// Sets up each game's accumulator and clears its TT (Search::clear()); the host has written the
// position, its single state and the counters.
extern "C" __global__ void datagen_setup(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                          short* accs, TTEntry* tts) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = lane_id();
    if (w >= n) return;
    Game* g = games + w;
    TTEntry* tt = tts + ((size_t)w << TT_BITS);
    for (int i = lane; i < (1 << TT_BITS); i += 32) tt[i].key = 0, tt[i].move = 0, tt[i].score = 0, tt[i].depth = 0, tt[i].bound = 0, tt[i].pad = 0;
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    g->accTop = 0;
    __syncwarp();
    refresh(g, net, acc_slot(acc, 0));
    __syncwarp();
}

// Plays one ply of every unfinished game.
extern "C" __global__ void datagen_step(Game* games, int n, const short* ftw, const short* ftb, const short* outw, int outb,
                                         const Params* params, short* accs, TTEntry* tts, unsigned long long nodes,
                                         unsigned long long budget) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->done) return;
    PB(10)
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    TTEntry* tt = tts + ((size_t)w << TT_BITS);
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
        think_start(g, nodes);
    }
    if (!think_run(g, net, *params, acc, tt, budget)) {
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
    int base = lane_id() * UNITS;
    for (int persp = 0; persp < 2; ++persp)
        for (int c = 0; c < UNITS; c += 8) store8(acc + persp * H + base + c, load8(top + persp * H + base + c));
    int pl = g->ply;
    __syncwarp();
    g->accTop = 0;
    g->ply = pl + 1;
    __syncwarp();
    PE(10)
}

// ---- Host interface ----
extern "C" __global__ void datagen_sizes(int* out) {
    out[0] = sizeof(Game);
    out[1] = sizeof(Sample);
    out[2] = sizeof(TTEntry);
    out[3] = sizeof(Params);
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
// with its own RNG seeded by the game's id), a fresh accumulator and a cleared TT. A game whose
// opening runs out of legal moves is marked done with result -1 and gets no samples.
extern "C" __global__ void datagen_opening(Game* games, const int* slots, int k, const u8* start, const u64* ids, u64 seed,
                                           int randomPlies, const short* ftw, const short* ftb, const short* outw, int outb,
                                           short* accs, TTEntry* tts) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = lane_id();
    if (w >= k) return;
    Net net = {ftw, ftb, outw, outb};
    int slot = slots[w];
    Game* g = games + slot;
    short* acc = accs + (size_t)slot * ACC_SLOTS * 2 * H;
    TTEntry* tt = tts + ((size_t)slot << TT_BITS);
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
    for (int i = lane; i < (1 << TT_BITS); i += 32) {
        TTEntry z; z.key = 0; z.move = 0; z.score = 0; z.depth = 0; z.bound = 0; z.pad = 0;
        tt[i] = z;
    }
    __syncwarp();
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

// Clears both sides' TTs in each of k slots (ucinewgame).
extern "C" __global__ void match_setup(const int* slots, int k, TTEntry* ttsA, TTEntry* ttsB) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = lane_id();
    if (w >= k) return;
    TTEntry* ta = ttsA + ((size_t)slots[w] << TT_BITS);
    TTEntry* tb = ttsB + ((size_t)slots[w] << TT_BITS);
    for (int i = lane; i < (1 << TT_BITS); i += 32) {
        TTEntry z; z.key = 0; z.move = 0; z.score = 0; z.depth = 0; z.bound = 0; z.pad = 0;
        ta[i] = z; tb[i] = z;
    }
    __syncwarp();
}

extern "C" __global__ void match_step(Game* games, int n, const short* ftwA, const short* ftbA, const short* outwA, int outbA,
                                      const short* ftwB, const short* ftbB, const short* outwB, int outbB,
                                      const Params* pa, const Params* pb, int perGame,
                                      short* accs, TTEntry* ttsA, TTEntry* ttsB, unsigned long long nodes,
                                      unsigned long long budget) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->matchResult >= 0) return;
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    bool idle = g->thinkState == T_IDLE; // otherwise a search is under way, in some position of its tree
    bool aToMove = (idle ? g->stm : g->rootStm) == g->aColor;
    Net net = aToMove ? Net{ftwA, ftbA, outwA, outbA} : Net{ftwB, ftbB, outwB, outbB};
    TTEntry* tt = (aToMove ? ttsA : ttsB) + ((size_t)w << TT_BITS);
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
        think_start(g, nodes);
    }
    if (!think_run(g, net, (aToMove ? pa : pb)[perGame ? w : 0], acc, tt, budget)) return;
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

extern "C" __global__ void match_results(const Game* games, int n, int* out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = games[i].matchResult;
}
