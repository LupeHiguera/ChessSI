#pragma once

#include <bit>

#include "types.h"

constexpr Bitboard FILE_A = 0x0101010101010101ULL;
constexpr Bitboard FILE_H = FILE_A << 7;
constexpr Bitboard RANK_1 = 0xFFULL;
constexpr Bitboard RANK_2 = RANK_1 << 8;
constexpr Bitboard RANK_3 = RANK_1 << 16;
constexpr Bitboard RANK_6 = RANK_1 << 40;
constexpr Bitboard RANK_7 = RANK_1 << 48;
constexpr Bitboard RANK_8 = RANK_1 << 56;

constexpr Bitboard square_bb(Square s) { return 1ULL << s; }
constexpr Bitboard file_bb(Square s) { return FILE_A << file_of(s); }
constexpr Bitboard rank_bb(Square s) { return RANK_1 << (8 * rank_of(s)); }

inline int popcount(Bitboard b) { return std::popcount(b); }
inline Square lsb(Bitboard b) { return std::countr_zero(b); }
inline Square pop_lsb(Bitboard& b) {
    Square s = lsb(b);
    b &= b - 1;
    return s;
}

extern Bitboard PawnAttacks[2][64];
extern Bitboard KnightAttacks[64];
extern Bitboard KingAttacks[64];

// Fancy magic bitboards; magics are searched for at startup with a fixed seed.
struct Magic {
    Bitboard mask;
    Bitboard magic;
    Bitboard* attacks;
    unsigned shift;
    unsigned index(Bitboard occ) const { return unsigned(((occ & mask) * magic) >> shift); }
};

extern Magic RookMagics[64];
extern Magic BishopMagics[64];

inline Bitboard rook_attacks(Square s, Bitboard occ) { return RookMagics[s].attacks[RookMagics[s].index(occ)]; }
inline Bitboard bishop_attacks(Square s, Bitboard occ) { return BishopMagics[s].attacks[BishopMagics[s].index(occ)]; }
inline Bitboard queen_attacks(Square s, Bitboard occ) { return rook_attacks(s, occ) | bishop_attacks(s, occ); }

inline Bitboard attacks_bb(PieceType pt, Square s, Bitboard occ) {
    switch (pt) {
    case KNIGHT: return KnightAttacks[s];
    case BISHOP: return bishop_attacks(s, occ);
    case ROOK:   return rook_attacks(s, occ);
    case QUEEN:  return queen_attacks(s, occ);
    default:     return KingAttacks[s];
    }
}

namespace Bitboards {
void init();
}
