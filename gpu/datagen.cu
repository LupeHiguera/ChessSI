// ChessSI's self-play data generation on the GPU (issue #31, stage 2): a line-by-line port of the
// search in src/search.cpp, the move generator in src/movegen.cpp (same move order), do_move /
// undo_move with the same Zobrist keys (src/position.cpp), and the game loop of src/datagen.cpp.
// The aim is the same output as the CPU for the same start positions, checked with gpu/ref.cpp.
//
// One game per warp. All 32 lanes run the same scalar code in lockstep on one copy of the game in
// global memory (same-address reads are broadcast and same-value writes merge), except the NNUE work:
// each lane owns H / 32 hidden units of both perspectives. Every launch plays one ply of every game,
// which keeps kernels well under the Windows GPU watchdog. Compiled at run time with NVRTC.

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
#define MAX_STATES 544 // 400 game plies, the start, and the deepest search
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
__constant__ int REDUCTIONS[64][64];

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
    u16 killers[MAX_PLY + 1][2];
    u16 moveStack[MAX_PLY + 1];
    int history[2][64][64];
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
__device__ void refresh(const Game* g, const Net& net, short* a) {
    int base = lane_id() * UNITS;
    for (int persp = 0; persp < 2; ++persp) {
        short v[UNITS];
        for (int j = 0; j < UNITS; ++j) v[j] = net.ftb[base + j];
        for (u64 b = occupied(g); b; b &= b - 1) {
            int s = lsb(b);
            const short* w = net.ftw + (size_t)feat(persp, g->board[s], s) * H + base;
            for (int j = 0; j < UNITS; ++j) v[j] = (short)(v[j] + w[j]);
        }
        for (int j = 0; j < UNITS; ++j) a[persp * H + base + j] = v[j];
    }
}
struct Delta {
    int n;
    int sign[4], piece[4], sq[4];
};
__device__ void apply_delta(const Net& net, const short* from, short* to, const Delta& d) {
    int base = lane_id() * UNITS;
    for (int persp = 0; persp < 2; ++persp) {
        short v[UNITS];
        for (int j = 0; j < UNITS; ++j) v[j] = from[persp * H + base + j];
        for (int k = 0; k < d.n; ++k) {
            const short* w = net.ftw + (size_t)feat(persp, d.piece[k], d.sq[k]) * H + base;
            for (int j = 0; j < UNITS; ++j) v[j] = (short)(d.sign[k] > 0 ? v[j] + w[j] : v[j] - w[j]);
        }
        for (int j = 0; j < UNITS; ++j) to[persp * H + base + j] = v[j];
    }
}
// NNUE::evaluate: the side to move's view first, SCReLU, int16 v * w times v, truncating divisions.
__device__ int evaluate(const Game* g, const Net& net, const short* acc) {
    const short* a = acc_slot((short*)acc, g->accTop);
    int base = lane_id() * UNITS, part = 0;
    for (int half = 0; half < 2; ++half) {
        int persp = half == 0 ? g->stm : g->stm ^ 1;
        for (int j = 0; j < UNITS; ++j) {
            int v = min(max((int)a[persp * H + base + j], 0), QA);
            int vw = (short)(v * net.outw[half * H + base + j]);
            part += vw * v;
        }
    }
    long long sum = part;
    for (int off = 16; off; off >>= 1) sum += __shfl_xor_sync(0xffffffffu, sum, off);
    sum = sum / QA + net.outb;
    return (int)(sum * EVAL_SCALE / (QA * QB));
}

// Board edits on local copies of the bitboards. All lanes take the same snapshot after a
// __syncwarp(), compute the same result, and only then write it, so no lane can see another's
// half-done update (the lanes of a warp are not guaranteed to run in lockstep).
struct Board {
    u64 bt[6], bc[2];
    int nw, wsq[6], wpc[6]; // board[] writes to make, in order
};
__device__ __forceinline__ void b_put(Board& b, int p, int s) {
    b.bt[type_of(p)] |= bit(s); b.bc[color_of(p)] |= bit(s);
    b.wsq[b.nw] = s; b.wpc[b.nw++] = p;
}
__device__ __forceinline__ void b_remove(Board& b, int p, int s) {
    b.bt[type_of(p)] &= ~bit(s); b.bc[color_of(p)] &= ~bit(s);
    b.wsq[b.nw] = s; b.wpc[b.nw++] = NO_PIECE;
}
__device__ __forceinline__ void b_move(Board& b, int p, int from, int to) {
    b.bt[type_of(p)] = (b.bt[type_of(p)] & ~bit(from)) | bit(to);
    b.bc[color_of(p)] = (b.bc[color_of(p)] & ~bit(from)) | bit(to);
    b.wsq[b.nw] = from; b.wpc[b.nw++] = NO_PIECE;
    b.wsq[b.nw] = to; b.wpc[b.nw++] = p;
}
__device__ __forceinline__ void b_load(const Game* g, Board& b) {
    for (int i = 0; i < 6; ++i) b.bt[i] = g->byType[i];
    b.bc[0] = g->byColor[0]; b.bc[1] = g->byColor[1];
    b.nw = 0;
}
__device__ __forceinline__ void b_store(Game* g, const Board& b) {
    for (int i = 0; i < 6; ++i) g->byType[i] = b.bt[i];
    g->byColor[0] = b.bc[0]; g->byColor[1] = b.bc[1];
    for (int k = 0; k < b.nw; ++k) g->board[b.wsq[k]] = (u8)b.wpc[k];
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
    d.n = 0;
    if (st.ep != SQ_NONE) {
        st.key ^= Z_EP[st.ep & 7];
        st.ep = SQ_NONE;
    }
    if (type == M_CASTLING) {
        bool kingside = to > from;
        int rookFrom = kingside ? from + 3 : from - 4, rookTo = kingside ? from + 1 : from - 1;
        int rook = g->board[rookFrom];
        b_move(b, pc, from, to);
        b_move(b, rook, rookFrom, rookTo);
        d.sign[0] = -1; d.piece[0] = pc; d.sq[0] = from;
        d.sign[1] = 1; d.piece[1] = pc; d.sq[1] = to;
        d.sign[2] = -1; d.piece[2] = rook; d.sq[2] = rookFrom;
        d.sign[3] = 1; d.piece[3] = rook; d.sq[3] = rookTo;
        d.n = 4;
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to] ^ Z_PSQ[rook][rookFrom] ^ Z_PSQ[rook][rookTo];
    } else {
        int capSq = type == M_EN_PASSANT ? (us == 0 ? to - 8 : to + 8) : to;
        int captured = g->board[capSq];
        if (captured != NO_PIECE) {
            b_remove(b, captured, capSq);
            d.sign[d.n] = -1; d.piece[d.n] = captured; d.sq[d.n] = capSq; ++d.n;
            st.key ^= Z_PSQ[captured][capSq];
            st.captured = captured;
            st.rule50 = 0;
        }
        b_move(b, pc, from, to);
        d.sign[d.n] = -1; d.piece[d.n] = pc; d.sq[d.n] = from; ++d.n;
        d.sign[d.n] = 1; d.piece[d.n] = pc; d.sq[d.n] = to; ++d.n;
        st.key ^= Z_PSQ[pc][from] ^ Z_PSQ[pc][to];
        if (type_of(pc) == PAWN) {
            st.rule50 = 0;
            if (type == M_PROMOTION) {
                int promo = us * 6 + ((m >> 12) & 3) + KNIGHT;
                b_remove(b, pc, to);
                b_put(b, promo, to);
                d.piece[d.n - 1] = promo; // the pawn arrives as the new piece
                st.key ^= Z_PSQ[pc][to] ^ Z_PSQ[promo][to];
            } else if (to - from == 16 || from - to == 16) {
                int ep = (from + to) / 2;
                if (pawn_att(ep, us) & b.bc[them] & b.bt[PAWN]) {
                    st.ep = ep;
                    st.key ^= Z_EP[ep & 7];
                }
            }
        }
    }
    int castling = st.castling & castling_mask(from) & castling_mask(to);
    if (castling != st.castling) {
        st.key ^= Z_CASTLING[st.castling] ^ Z_CASTLING[castling];
        st.castling = castling;
    }
    st.key ^= Z_SIDE[0];
    __syncwarp();
    b_store(g, b);
    g->states[n] = st;
    g->nstates = n + 1;
    g->stm = them;
    g->fullmove = fm + (us == 1);
    g->accTop = top + 1;
    apply_delta(net, acc_slot(acc, top), acc_slot(acc, top + 1), d);
    __syncwarp();
    return !attacked(g, king_sq(g, us), them);
}

__device__ void undo_move(Game* g, u16 m) {
    __syncwarp();
    int n = g->nstates, top = g->accTop, us = g->stm ^ 1, fm = g->fullmove;
    int from = m & 63, to = (m >> 6) & 63, type = m & (3 << 14);
    int captured = g->states[n - 1].captured;
    Board b;
    b_load(g, b);
    if (type == M_CASTLING) {
        bool kingside = to > from;
        int rookFrom = kingside ? from + 3 : from - 4, rookTo = kingside ? from + 1 : from - 1;
        int king = g->board[to], rook = g->board[rookTo];
        b_move(b, king, to, from);
        b_move(b, rook, rookTo, rookFrom);
    } else {
        int p = g->board[to];
        if (type == M_PROMOTION) {
            b_remove(b, p, to);
            p = us * 6 + PAWN;
            b_put(b, p, to);
        }
        b_move(b, p, to, from);
        if (captured != NO_PIECE) b_put(b, captured, type == M_EN_PASSANT ? (us == 0 ? to - 8 : to + 8) : to);
    }
    __syncwarp();
    b_store(g, b);
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

__device__ int qsearch(Game* g, const Net& net, short* acc, TTEntry* tt, int alpha, int beta, int ply) {
    count_node(g);
    check_limits(g);
    __syncwarp();
    if (g->stopped) return 0;
    int standPat = evaluate(g, net, acc);
    if (ply >= MAX_PLY - 1 || standPat >= beta) return standPat;
    alpha = max(alpha, standPat);
    u16* list = g->moves[ply];
    int* scores = g->scores[ply];
    int n = generate(g, list, true);
    __syncwarp();
    score_moves(g, list, n, scores, MOVE_NONE, -1);
    int best = standPat;
    for (int i = 0; i < n; ++i) {
        u16 m = pick_move(list, scores, n, i);
        if (!see_ge(g, m, 0)) continue;
        if (!do_move(g, m, net, acc)) {
            undo_move(g, m);
            continue;
        }
        int score = -qsearch(g, net, acc, tt, -beta, -alpha, ply + 1);
        undo_move(g, m);
        if (g->stopped) return 0;
        if (score > best) {
            best = score;
            if (score > alpha) {
                alpha = score;
                if (score >= beta) break;
            }
        }
    }
    return best;
}

__device__ int search(Game* g, const Net& net, short* acc, TTEntry* tt, int alpha, int beta, int depth, int ply) {
    bool inCheck = in_check(g);
    if (inCheck) ++depth;
    if (depth <= 0) return qsearch(g, net, acc, tt, alpha, beta, ply);
    count_node(g);
    check_limits(g);
    __syncwarp();
    if (g->stopped) return 0;
    bool root = ply == 0, pvNode = beta - alpha > 1;
    if (root) g->rootPv = 0; // pvLength[0] = 0
    if (!root) {
        if (is_draw(g)) return 0;
        if (ply >= MAX_PLY - 1) return evaluate(g, net, acc);
    }
    u64 key = g->states[g->nstates - 1].key;
    TTEntry e = *tt_entry(tt, key);
    bool hit = e.key == key && e.bound != BOUND_NONE;
    u16 ttMove = hit ? e.move : MOVE_NONE;
    if (hit && !pvNode && e.depth >= depth) {
        int ttScore = score_from_tt(e.score, ply);
        if (e.bound == BOUND_EXACT || (e.bound == BOUND_LOWER && ttScore >= beta) || (e.bound == BOUND_UPPER && ttScore <= alpha))
            return ttScore;
    }
    int staticEval = inCheck ? -VALUE_INF : evaluate(g, net, acc);
    int us = g->stm;
    if (!root && !pvNode && !inCheck && depth <= 3 && g->states[g->nstates - 1].rule50 + depth < 100 && abs(beta) < VALUE_MATE_IN_MAX_PLY
        && (g->byColor[us] & ~(g->byType[PAWN] | g->byType[KING]))) {
        if (abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 150 * depth >= beta)
            return has_legal_move(g, net, acc, ply) ? staticEval : 0;
    }
    bool hasPieces = (g->byColor[us] & ~g->byType[PAWN] & ~g->byType[KING]) != 0;
    if (!pvNode && !inCheck && !root && depth >= 3 && hasPieces && g->moveStack[ply - 1] != MOVE_NONE && staticEval >= beta) {
        int R = 3 + depth / 6;
        g->moveStack[ply] = MOVE_NONE;
        __syncwarp();
        do_null_move(g);
        int score = -search(g, net, acc, tt, -beta, -beta + 1, depth - 1 - R, ply + 1);
        undo_null_move(g);
        if (g->stopped) return 0;
        if (score >= beta) return score >= VALUE_MATE_IN_MAX_PLY ? beta : score;
    }
    u16* list = g->moves[ply];
    int* scores = g->scores[ply];
    u16* quiets = g->quiets[ply];
    int n = generate(g, list, false);
    __syncwarp();
    score_moves(g, list, n, scores, ttMove, ply);
    int originalAlpha = alpha, best = -VALUE_INF, legalMoves = 0, quietCount = 0;
    u16 bestMove = MOVE_NONE;
    for (int i = 0; i < n; ++i) {
        u16 m = pick_move(list, scores, n, i);
        bool quiet = is_quiet(g, m);
        if (!pvNode && !inCheck && quiet && depth <= 8 && best > -VALUE_MATE_IN_MAX_PLY && quietCount >= 3 + depth * depth) continue;
        if (!pvNode && !inCheck && quiet && depth <= 6 && best > -VALUE_MATE_IN_MAX_PLY && staticEval + 120 * depth <= alpha) continue;
        if (!do_move(g, m, net, acc)) {
            undo_move(g, m);
            continue;
        }
        ++legalMoves;
        g->moveStack[ply] = m;
        __syncwarp();
        int score;
        if (legalMoves == 1)
            score = -search(g, net, acc, tt, -beta, -alpha, depth - 1, ply + 1);
        else {
            int r = 0;
            if (depth >= 3 && legalMoves > 3 && quiet && !inCheck && !in_check(g)) {
                r = REDUCTIONS[min(depth, 63)][min(legalMoves, 63)];
                if (pvNode) --r;
                r = max(0, min(r, depth - 2));
            }
            score = -search(g, net, acc, tt, -alpha - 1, -alpha, depth - 1 - r, ply + 1);
            if (score > alpha && r > 0) score = -search(g, net, acc, tt, -alpha - 1, -alpha, depth - 1, ply + 1);
            if (score > alpha && score < beta) score = -search(g, net, acc, tt, -beta, -alpha, depth - 1, ply + 1);
        }
        undo_move(g, m);
        if (g->stopped) return 0;
        if (score > best) {
            best = score;
            if (score > alpha) {
                alpha = score;
                bestMove = m;
                if (root) {
                    g->rootBest = m;
                    g->rootPv = 1;
                    __syncwarp();
                }
                if (score >= beta) {
                    if (quiet) {
                        if (m != g->killers[ply][0]) {
                            u16 k0 = g->killers[ply][0];
                            __syncwarp();
                            g->killers[ply][1] = k0;
                            g->killers[ply][0] = m;
                            __syncwarp();
                        }
                        int bonus = min(depth * depth, 1200);
                        update_history(g, m, bonus);
                        for (int j = 0; j < quietCount; ++j) update_history(g, quiets[j], -bonus);
                    }
                    break;
                }
            }
        }
        if (quiet) {
            quiets[quietCount++] = m;
            __syncwarp();
        }
    }
    if (legalMoves == 0) return inCheck ? -VALUE_MATE + ply : 0;
    int bound = best >= beta ? BOUND_LOWER : alpha > originalAlpha ? BOUND_EXACT : BOUND_UPPER;
    tt_store(tt, key, bestMove, score_to_tt(best, ply), depth, bound);
    return best;
}

__device__ int search_root(Game* g, const Net& net, short* acc, TTEntry* tt, int depth, int prevScore) {
    int delta = 25, alpha = -VALUE_INF, beta = VALUE_INF;
    if (depth >= 5) {
        alpha = max(prevScore - delta, -VALUE_INF);
        beta = min(prevScore + delta, VALUE_INF);
    }
    while (true) {
        int score = search(g, net, acc, tt, alpha, beta, depth, 0);
        if (g->stopped) return score;
        if (score <= alpha) alpha = max(score - delta, -VALUE_INF);
        else if (score >= beta) beta = min(score + delta, VALUE_INF);
        else return score;
        delta *= 2;
    }
}

// Search::think with a node limit and one thread: a fresh Searcher (history, killers and the
// move stack zeroed); the TT is kept. Returns the best move; the score goes to *score.
__device__ u16 think(Game* g, const Net& net, short* acc, TTEntry* tt, u64 nodeLimit, int* score) {
    int lane = lane_id();
    for (int i = lane; i < 2 * 64 * 64; i += 32) (&g->history[0][0][0])[i] = 0;
    for (int i = lane; i < (MAX_PLY + 1) * 2; i += 32) (&g->killers[0][0])[i] = 0;
    for (int i = lane; i < MAX_PLY + 1; i += 32) g->moveStack[i] = 0;
    g->nodes = 0;
    g->nodeLimit = nodeLimit;
    g->stopped = 0;
    g->rootPv = 0;
    g->rootBest = MOVE_NONE;
    __syncwarp();
    u16 best = MOVE_NONE;
    int bestScore = 0;
    for (int depth = 1; depth <= MAX_PLY - 1; ++depth) {
        int s = search_root(g, net, acc, tt, depth, bestScore);
        if (g->stopped) break;
        if (g->rootPv) best = g->rootBest;
        bestScore = s;
    }
    if (best == MOVE_NONE) best = first_legal_move(g, net, acc, 0);
    *score = bestScore;
    return best;
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
                                         short* accs, TTEntry* tts, unsigned long long nodes) {
    Net net = {ftw, ftb, outw, outb};
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5;
    if (w >= n) return;
    Game* g = games + w;
    if (g->done) return;
    short* acc = accs + (size_t)w * ACC_SLOTS * 2 * H;
    TTEntry* tt = tts + ((size_t)w << TT_BITS);
    if (g->ply >= MAX_PLIES) { g->result = 0.5f; g->done = 1; return; }
    if (first_legal_move(g, net, acc, 0) == MOVE_NONE) {
        g->result = in_check(g) ? (g->stm == 0 ? 0.0f : 1.0f) : 0.5f;
        g->done = 1;
        return;
    }
    if (is_draw(g)) { g->result = 0.5f; g->done = 1; return; }
    int ev = evaluate(g, net, acc);
    int whiteEval = g->stm == 0 ? ev : -ev;
    int score;
    u16 best = think(g, net, acc, tt, nodes, &score);
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
        for (int j = 0; j < UNITS; ++j) acc[persp * H + base + j] = top[persp * H + base + j];
    int pl = g->ply;
    __syncwarp();
    g->accTop = 0;
    g->ply = pl + 1;
    __syncwarp();
}

// ---- Host interface ----
extern "C" __global__ void datagen_sizes(int* out) {
    out[0] = sizeof(Game);
    out[1] = sizeof(Sample);
    out[2] = sizeof(TTEntry);
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
    g->winStreak = 0; g->ply = 0; g->done = 0; g->nsamples = 0; g->result = 0.5f;
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
