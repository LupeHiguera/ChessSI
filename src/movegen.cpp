#include "movegen.h"

namespace {

void add_promotions(MoveList& list, Square from, Square to, bool queenOnly) {
    list.add(make_move(from, to, PROMOTION, QUEEN));
    if (!queenOnly) {
        list.add(make_move(from, to, PROMOTION, KNIGHT));
        list.add(make_move(from, to, PROMOTION, ROOK));
        list.add(make_move(from, to, PROMOTION, BISHOP));
    }
}

void generate_pawn_moves(const Position& pos, MoveList& list, GenType type) {
    Color us = pos.side_to_move(), them = ~us;
    Bitboard pawns = pos.pieces(us, PAWN);
    Bitboard empty = ~pos.pieces();
    Bitboard enemies = pos.pieces(them);
    Bitboard seventh = us == WHITE ? RANK_7 : RANK_2;
    Bitboard third = us == WHITE ? RANK_3 : RANK_6;
    int up = us == WHITE ? 8 : -8;
    bool queenOnly = type == NOISY_MOVES;
    auto push = [us](Bitboard b) { return us == WHITE ? b << 8 : b >> 8; };

    if (type == ALL_MOVES) {
        Bitboard single = push(pawns & ~seventh) & empty;
        Bitboard twice = push(single & third) & empty;
        while (single) {
            Square to = pop_lsb(single);
            list.add(make_move(to - up, to));
        }
        while (twice) {
            Square to = pop_lsb(twice);
            list.add(make_move(to - 2 * up, to));
        }
    }

    Bitboard promoPushes = push(pawns & seventh) & empty;
    while (promoPushes) {
        Square to = pop_lsb(promoPushes);
        add_promotions(list, to - up, to, queenOnly);
    }

    for (Bitboard b = pawns; b;) {
        Square from = pop_lsb(b);
        Bitboard captures = PawnAttacks[us][from] & enemies;
        while (captures) {
            Square to = pop_lsb(captures);
            if (square_bb(from) & seventh)
                add_promotions(list, from, to, queenOnly);
            else
                list.add(make_move(from, to));
        }
    }

    if (pos.ep_square() != SQ_NONE) {
        Bitboard attackers = PawnAttacks[them][pos.ep_square()] & pawns;
        while (attackers)
            list.add(make_move(pop_lsb(attackers), pos.ep_square(), EN_PASSANT));
    }
}

void generate_castling(const Position& pos, MoveList& list) {
    Color us = pos.side_to_move(), them = ~us;
    Square base = us == WHITE ? 0 : 56;
    Square king = base + 4;
    int rights = pos.castling_rights();
    Bitboard occ = pos.pieces();

    if (!(rights & (us == WHITE ? WHITE_OO | WHITE_OOO : BLACK_OO | BLACK_OOO)) || pos.in_check())
        return;

    if ((rights & (us == WHITE ? WHITE_OO : BLACK_OO))
        && !(occ & (square_bb(base + 5) | square_bb(base + 6)))
        && !pos.attacked(base + 5, them))
        list.add(make_move(king, base + 6, CASTLING));

    if ((rights & (us == WHITE ? WHITE_OOO : BLACK_OOO))
        && !(occ & (square_bb(base + 1) | square_bb(base + 2) | square_bb(base + 3)))
        && !pos.attacked(base + 3, them))
        list.add(make_move(king, base + 2, CASTLING));
}

} // namespace

void generate(const Position& pos, MoveList& list, GenType type) {
    Color us = pos.side_to_move();
    Bitboard occ = pos.pieces();
    Bitboard targets = type == NOISY_MOVES ? pos.pieces(~us) : ~pos.pieces(us);

    generate_pawn_moves(pos, list, type);

    for (PieceType pt : {KNIGHT, BISHOP, ROOK, QUEEN, KING}) {
        for (Bitboard b = pos.pieces(us, pt); b;) {
            Square from = pop_lsb(b);
            Bitboard attacks = attacks_bb(pt, from, occ) & targets;
            while (attacks)
                list.add(make_move(from, pop_lsb(attacks)));
        }
    }

    if (type == ALL_MOVES)
        generate_castling(pos, list);
}

Move parse_uci_move(Position& pos, const std::string& str) {
    MoveList list;
    generate(pos, list, ALL_MOVES);
    for (Move m : list) {
        if (move_to_uci(m) != str)
            continue;
        bool legal = pos.do_move(m);
        pos.undo_move(m);
        return legal ? m : MOVE_NONE;
    }
    return MOVE_NONE;
}
