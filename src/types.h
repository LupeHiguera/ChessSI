#pragma once

#include <cstdint>

using Bitboard = uint64_t;

enum Color : int { WHITE, BLACK };
constexpr Color operator~(Color c) { return Color(c ^ 1); }

enum PieceType : int { PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING };

// Piece = color * 6 + type.
using Piece = int;
constexpr Piece NO_PIECE = 12;
constexpr Piece make_piece(Color c, PieceType pt) { return c * 6 + pt; }
constexpr PieceType type_of(Piece p) { return PieceType(p % 6); }
constexpr Color color_of(Piece p) { return Color(p / 6); }

// Squares run a1 = 0, b1 = 1, ..., h8 = 63.
using Square = int;
constexpr Square SQ_NONE = 64;
constexpr int file_of(Square s) { return s & 7; }
constexpr int rank_of(Square s) { return s >> 3; }
constexpr Square make_square(int file, int rank) { return rank * 8 + file; }

enum CastlingRight : int { WHITE_OO = 1, WHITE_OOO = 2, BLACK_OO = 4, BLACK_OOO = 8 };

// Move layout: bits 0-5 from, 6-11 to, 12-13 promotion piece (knight..queen), 14-15 move type.
// Castling is encoded as the king's two-square move (e1g1, e1c1, ...).
using Move = uint16_t;
constexpr Move MOVE_NONE = 0;
enum MoveType : int { NORMAL = 0, PROMOTION = 1 << 14, EN_PASSANT = 2 << 14, CASTLING = 3 << 14 };

constexpr Move make_move(Square from, Square to, int type = NORMAL, PieceType promo = KNIGHT) {
    return Move(from | (to << 6) | ((promo - KNIGHT) << 12) | type);
}
constexpr Square from_sq(Move m) { return m & 63; }
constexpr Square to_sq(Move m) { return (m >> 6) & 63; }
constexpr int move_type(Move m) { return m & (3 << 14); }
constexpr PieceType promotion_type(Move m) { return PieceType(((m >> 12) & 3) + KNIGHT); }

constexpr int MAX_PLY = 128;
constexpr int VALUE_INF = 32001;
constexpr int VALUE_MATE = 32000;
constexpr int VALUE_MATE_IN_MAX_PLY = VALUE_MATE - MAX_PLY;
// No static eval stored. Outside the mate band, so it cannot be a search score or a raw eval.
constexpr int VALUE_NONE = 32767;
