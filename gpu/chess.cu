// Chess move generation on the GPU, for research into GPU data generation (issue #31).
//
// Compiled at run time with NVRTC (see perft.py), so it holds device code only. A position is 128
// bytes of bitboards copied on every move (copy-make). Slider attacks use hyperbola quintessence with
// a full 64-bit reversal (__brevll), which handles ranks, files and both diagonals with no lookup
// tables, and the other attacks are shifts. Squares are a1 = 0 ... h8 = 63, as in src/types.h.

typedef unsigned long long u64;
typedef unsigned short u16;

enum { PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING };
enum { WK = 1, WQ = 2, BK = 4, BQ = 8 }; // castling rights

// Move: from (6 bits) | to (6 bits) << 6 | flag (4 bits) << 12.
enum { F_NORMAL, F_DOUBLE, F_CASTLE_K, F_CASTLE_Q, F_EP, F_PROMO_N, F_PROMO_B, F_PROMO_R, F_PROMO_Q };

struct Pos {
    u64 pc[2][6]; // [color][piece type]
    u64 occ[2];   // [color]
    int stm;      // 0 White, 1 Black
    int castle;   // WK | WQ | BK | BQ
    int ep;       // en passant target square, or -1
    int pad;
};

#define NOT_A 0xFEFEFEFEFEFEFEFEULL
#define NOT_AB 0xFCFCFCFCFCFCFCFCULL
#define NOT_H 0x7F7F7F7F7F7F7F7FULL
#define NOT_GH 0x3F3F3F3F3F3F3F3FULL

__device__ __forceinline__ u64 bit(int s) { return 1ULL << s; }
__device__ __forceinline__ int lsb(u64 b) { return __ffsll((long long)b) - 1; }

// Attacks along one line through s (mask excludes s), stopping at the first blocker each way.
__device__ __forceinline__ u64 line_attacks(u64 occ, u64 mask, int s) {
    u64 b = bit(s);
    u64 f = occ & mask;
    u64 r = __brevll(f);
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
__device__ __forceinline__ u64 rook_att(int s, u64 occ) {
    return line_attacks(occ, file_mask(s), s) | line_attacks(occ, rank_mask(s), s);
}
__device__ __forceinline__ u64 bishop_att(int s, u64 occ) {
    return line_attacks(occ, diag_mask(s), s) | line_attacks(occ, anti_mask(s), s);
}
__device__ __forceinline__ u64 knight_att(u64 b) {
    return ((b << 17) & NOT_A) | ((b << 15) & NOT_H) | ((b << 10) & NOT_AB) | ((b << 6) & NOT_GH)
         | ((b >> 17) & NOT_H) | ((b >> 15) & NOT_A) | ((b >> 10) & NOT_GH) | ((b >> 6) & NOT_AB);
}
__device__ __forceinline__ u64 king_att(u64 b) {
    u64 lr = ((b << 1) & NOT_A) | ((b >> 1) & NOT_H);
    u64 row = b | lr;
    return lr | (row << 8) | (row >> 8);
}
// Squares attacked by pawns of color c standing on b.
__device__ __forceinline__ u64 pawn_att(u64 b, int c) {
    return c == 0 ? ((b << 9) & NOT_A) | ((b << 7) & NOT_H) : ((b >> 7) & NOT_A) | ((b >> 9) & NOT_H);
}

__device__ bool attacked(const Pos& p, int s, int by) {
    u64 b = bit(s), occ = p.occ[0] | p.occ[1];
    if (pawn_att(b, by ^ 1) & p.pc[by][PAWN]) return true;
    if (knight_att(b) & p.pc[by][KNIGHT]) return true;
    if (king_att(b) & p.pc[by][KING]) return true;
    u64 bq = p.pc[by][BISHOP] | p.pc[by][QUEEN], rq = p.pc[by][ROOK] | p.pc[by][QUEEN];
    if (bq && (bishop_att(s, occ) & bq)) return true;
    if (rq && (rook_att(s, occ) & rq)) return true;
    return false;
}

__device__ __forceinline__ u16 mv(int from, int to, int flag) { return (u16)(from | (to << 6) | (flag << 12)); }

// Pseudo-legal moves (the mover's king may be left in check; make() callers test that).
__device__ int generate(const Pos& p, u16* moves) {
    int us = p.stm, them = us ^ 1, n = 0;
    u64 own = p.occ[us], opp = p.occ[them], occ = own | opp, empty = ~occ;
    u64 pawns = p.pc[us][PAWN];
    u64 promoRank = us == 0 ? 0xFF00000000000000ULL : 0xFFULL;
    u64 single = us == 0 ? (pawns << 8) & empty : (pawns >> 8) & empty;
    u64 dbl = us == 0 ? ((single & 0xFF0000ULL) << 8) & empty : ((single & 0xFF0000000000ULL) >> 8) & empty;
    int up = us == 0 ? 8 : -8;
    for (u64 b = single; b; b &= b - 1) {
        int to = lsb(b), from = to - up;
        if (bit(to) & promoRank)
            for (int f = F_PROMO_N; f <= F_PROMO_Q; ++f) moves[n++] = mv(from, to, f);
        else
            moves[n++] = mv(from, to, F_NORMAL);
    }
    for (u64 b = dbl; b; b &= b - 1) {
        int to = lsb(b);
        moves[n++] = mv(to - 2 * up, to, F_DOUBLE);
    }
    for (u64 b = pawns; b; b &= b - 1) {
        int from = lsb(b);
        for (u64 t = pawn_att(bit(from), us) & opp; t; t &= t - 1) {
            int to = lsb(t);
            if (bit(to) & promoRank)
                for (int f = F_PROMO_N; f <= F_PROMO_Q; ++f) moves[n++] = mv(from, to, f);
            else
                moves[n++] = mv(from, to, F_NORMAL);
        }
    }
    if (p.ep >= 0)
        for (u64 b = pawn_att(bit(p.ep), them) & pawns; b; b &= b - 1) moves[n++] = mv(lsb(b), p.ep, F_EP);
    for (u64 b = p.pc[us][KNIGHT]; b; b &= b - 1) {
        int from = lsb(b);
        for (u64 t = knight_att(bit(from)) & ~own; t; t &= t - 1) moves[n++] = mv(from, lsb(t), F_NORMAL);
    }
    for (u64 b = p.pc[us][BISHOP] | p.pc[us][QUEEN]; b; b &= b - 1) {
        int from = lsb(b);
        for (u64 t = bishop_att(from, occ) & ~own; t; t &= t - 1) moves[n++] = mv(from, lsb(t), F_NORMAL);
    }
    for (u64 b = p.pc[us][ROOK] | p.pc[us][QUEEN]; b; b &= b - 1) {
        int from = lsb(b);
        for (u64 t = rook_att(from, occ) & ~own; t; t &= t - 1) moves[n++] = mv(from, lsb(t), F_NORMAL);
    }
    int k = lsb(p.pc[us][KING]);
    for (u64 t = king_att(bit(k)) & ~own; t; t &= t - 1) moves[n++] = mv(k, lsb(t), F_NORMAL);
    // Castling: the squares between king and rook empty, and the king not in check and not
    // passing through an attacked square (its destination is tested after the move, like any other).
    if (us == 0) {
        if ((p.castle & WK) && !(occ & 0x60ULL) && !attacked(p, 4, 1) && !attacked(p, 5, 1)) moves[n++] = mv(4, 6, F_CASTLE_K);
        if ((p.castle & WQ) && !(occ & 0x0EULL) && !attacked(p, 4, 1) && !attacked(p, 3, 1)) moves[n++] = mv(4, 2, F_CASTLE_Q);
    } else {
        if ((p.castle & BK) && !(occ & 0x6000000000000000ULL) && !attacked(p, 60, 0) && !attacked(p, 61, 0)) moves[n++] = mv(60, 62, F_CASTLE_K);
        if ((p.castle & BQ) && !(occ & 0x0E00000000000000ULL) && !attacked(p, 60, 0) && !attacked(p, 59, 0)) moves[n++] = mv(60, 58, F_CASTLE_Q);
    }
    return n;
}

// Castling rights kept after a move touches square s.
__device__ __forceinline__ int castle_keep(int s) {
    switch (s) {
        case 0: return ~WQ;
        case 4: return ~(WK | WQ);
        case 7: return ~WK;
        case 56: return ~BQ;
        case 60: return ~(BK | BQ);
        case 63: return ~BK;
        default: return ~0;
    }
}

// Plays m on p (copy-make). Returns whether it was legal (the mover's king not attacked).
__device__ bool make(Pos& p, u16 m) {
    int from = m & 63, to = (m >> 6) & 63, flag = m >> 12;
    int us = p.stm, them = us ^ 1;
    u64 fb = bit(from), tb = bit(to);
    int pt = PAWN;
    while (!(p.pc[us][pt] & fb)) ++pt;
    if (p.occ[them] & tb) {
        for (int t = PAWN; t <= KING; ++t) p.pc[them][t] &= ~tb;
        p.occ[them] &= ~tb;
    }
    p.pc[us][pt] ^= fb | tb;
    p.occ[us] ^= fb | tb;
    if (flag == F_EP) {
        u64 cb = bit(us == 0 ? to - 8 : to + 8);
        p.pc[them][PAWN] &= ~cb;
        p.occ[them] &= ~cb;
    } else if (flag == F_CASTLE_K || flag == F_CASTLE_Q) {
        int rf = flag == F_CASTLE_K ? from + 3 : from - 4, rt = flag == F_CASTLE_K ? from + 1 : from - 1;
        u64 rb = bit(rf) | bit(rt);
        p.pc[us][ROOK] ^= rb;
        p.occ[us] ^= rb;
    } else if (flag >= F_PROMO_N) {
        p.pc[us][PAWN] &= ~tb;
        p.pc[us][KNIGHT + flag - F_PROMO_N] |= tb;
    }
    p.ep = flag == F_DOUBLE ? (from + to) >> 1 : -1;
    p.castle &= castle_keep(from) & castle_keep(to);
    p.stm = them;
    return !attacked(p, lsb(p.pc[us][KING]), them);
}

__device__ u64 perft(const Pos& p, int depth) {
    u16 moves[256];
    int n = generate(p, moves);
    u64 nodes = 0;
    for (int i = 0; i < n; ++i) {
        Pos c = p;
        if (!make(c, moves[i])) continue;
        nodes += depth <= 1 ? 1 : perft(c, depth - 1);
    }
    return nodes;
}

extern "C" __global__ void perft_kernel(const Pos* roots, int n, int depth, u64* out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = depth == 0 ? 1 : perft(roots[i], depth);
}

// Every legal child of each position: in[i]'s children go to out[i * 256 ...], their number to count[i].
extern "C" __global__ void expand_kernel(const Pos* in, int n, Pos* out, int* count) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    u16 moves[256];
    int m = generate(in[i], moves), k = 0;
    for (int j = 0; j < m; ++j) {
        Pos c = in[i];
        if (make(c, moves[j])) out[(size_t)i * 256 + k++] = c;
    }
    count[i] = k;
}
