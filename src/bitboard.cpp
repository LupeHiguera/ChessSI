#include "bitboard.h"

Bitboard PawnAttacks[2][64];
Bitboard KnightAttacks[64];
Bitboard KingAttacks[64];
Magic RookMagics[64];
Magic BishopMagics[64];

namespace {

Bitboard RookTable[0x19000];
Bitboard BishopTable[0x1480];

// xorshift64*; a fixed seed keeps the magics identical on every run.
struct PRNG {
    uint64_t s;
    uint64_t rand() {
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        return s * 2685821657736338717ULL;
    }
    uint64_t sparse_rand() { return rand() & rand() & rand(); }
};

Bitboard leaper_attacks(Square s, const int (*deltas)[2], int count) {
    Bitboard attacks = 0;
    for (int i = 0; i < count; ++i) {
        int f = file_of(s) + deltas[i][0], r = rank_of(s) + deltas[i][1];
        if (f >= 0 && f < 8 && r >= 0 && r < 8)
            attacks |= square_bb(make_square(f, r));
    }
    return attacks;
}

Bitboard sliding_attacks(Square s, Bitboard occ, bool rook) {
    static constexpr int RookDirs[4][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    static constexpr int BishopDirs[4][2] = {{1, 1}, {1, -1}, {-1, 1}, {-1, -1}};
    const auto& dirs = rook ? RookDirs : BishopDirs;
    Bitboard attacks = 0;
    for (const auto& d : dirs) {
        int f = file_of(s) + d[0], r = rank_of(s) + d[1];
        while (f >= 0 && f < 8 && r >= 0 && r < 8) {
            Square t = make_square(f, r);
            attacks |= square_bb(t);
            if (occ & square_bb(t))
                break;
            f += d[0];
            r += d[1];
        }
    }
    return attacks;
}

void init_magics(Magic magics[], Bitboard table[], bool rook) {
    static Bitboard occupancy[4096], reference[4096];
    static int epoch[4096];
    int attempt = 0;
    Bitboard* next = table;
    PRNG rng{rook ? 0x2545F4914F6CDD1DULL : 0x9E3779B97F4A7C15ULL};

    for (Square s = 0; s < 64; ++s) {
        Magic& m = magics[s];
        Bitboard edges = ((RANK_1 | RANK_8) & ~rank_bb(s)) | ((FILE_A | FILE_H) & ~file_bb(s));
        m.mask = sliding_attacks(s, 0, rook) & ~edges;
        m.shift = 64 - popcount(m.mask);
        m.attacks = next;

        // Enumerate every subset of the mask (Carry-Rippler).
        int size = 0;
        Bitboard b = 0;
        do {
            occupancy[size] = b;
            reference[size] = sliding_attacks(s, b, rook);
            ++size;
            b = (b - m.mask) & m.mask;
        } while (b);
        next += size;

        for (int i = 0; i < size;) {
            do
                m.magic = rng.sparse_rand();
            while (popcount((m.mask * m.magic) >> 56) < 6);

            ++attempt;
            for (i = 0; i < size; ++i) {
                unsigned idx = m.index(occupancy[i]);
                if (epoch[idx] < attempt) {
                    epoch[idx] = attempt;
                    m.attacks[idx] = reference[i];
                } else if (m.attacks[idx] != reference[i])
                    break;
            }
        }
    }
}

} // namespace

void Bitboards::init() {
    static constexpr int KnightDeltas[8][2] = {{1, 2}, {2, 1}, {2, -1}, {1, -2}, {-1, -2}, {-2, -1}, {-2, 1}, {-1, 2}};
    static constexpr int KingDeltas[8][2] = {{1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1}, {0, -1}, {1, -1}};
    static constexpr int WhitePawnDeltas[2][2] = {{-1, 1}, {1, 1}};
    static constexpr int BlackPawnDeltas[2][2] = {{-1, -1}, {1, -1}};

    for (Square s = 0; s < 64; ++s) {
        KnightAttacks[s] = leaper_attacks(s, KnightDeltas, 8);
        KingAttacks[s] = leaper_attacks(s, KingDeltas, 8);
        PawnAttacks[WHITE][s] = leaper_attacks(s, WhitePawnDeltas, 2);
        PawnAttacks[BLACK][s] = leaper_attacks(s, BlackPawnDeltas, 2);
    }

    init_magics(RookMagics, RookTable, true);
    init_magics(BishopMagics, BishopTable, false);
}
