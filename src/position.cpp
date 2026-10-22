#include "position.h"

#include <sstream>

namespace {

namespace Zobrist {
uint64_t psq[12][64];
uint64_t castling[16];
uint64_t epFile[8];
uint64_t side;
} // namespace Zobrist

// Castling rights kept after a move touches a square.
int CastlingMask[64];

const std::string PieceChars = "PNBRQKpnbrqk";

} // namespace

void Position::init() {
    uint64_t s = 1070372;
    auto rand64 = [&] {
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        return s * 2685821657736338717ULL;
    };
    for (auto& piece : Zobrist::psq)
        for (auto& key : piece)
            key = rand64();
    for (auto& key : Zobrist::castling)
        key = rand64();
    for (auto& key : Zobrist::epFile)
        key = rand64();
    Zobrist::side = rand64();

    for (int& mask : CastlingMask)
        mask = 15;
    CastlingMask[make_square(0, 0)] &= ~WHITE_OOO;
    CastlingMask[make_square(7, 0)] &= ~WHITE_OO;
    CastlingMask[make_square(4, 0)] &= ~(WHITE_OO | WHITE_OOO);
    CastlingMask[make_square(0, 7)] &= ~BLACK_OOO;
    CastlingMask[make_square(7, 7)] &= ~BLACK_OO;
    CastlingMask[make_square(4, 7)] &= ~(BLACK_OO | BLACK_OOO);
}

void Position::put_piece(Piece p, Square s) {
    board[s] = p;
    byType[type_of(p)] |= square_bb(s);
    byColor[color_of(p)] |= square_bb(s);
}

void Position::remove_piece(Square s) {
    Piece p = board[s];
    byType[type_of(p)] &= ~square_bb(s);
    byColor[color_of(p)] &= ~square_bb(s);
    board[s] = NO_PIECE;
}

void Position::move_piece(Square from, Square to) {
    Piece p = board[from];
    Bitboard fromTo = square_bb(from) | square_bb(to);
    byType[type_of(p)] ^= fromTo;
    byColor[color_of(p)] ^= fromTo;
    board[from] = NO_PIECE;
    board[to] = p;
}

uint64_t Position::compute_key() const {
    uint64_t k = 0;
    for (Square s = 0; s < 64; ++s)
        if (board[s] != NO_PIECE)
            k ^= Zobrist::psq[board[s]][s];
    k ^= Zobrist::castling[castling_rights()];
    if (ep_square() != SQ_NONE)
        k ^= Zobrist::epFile[file_of(ep_square())];
    if (stm == BLACK)
        k ^= Zobrist::side;
    return k;
}

bool Position::set(const std::string& fen) {
    std::istringstream is(fen);
    std::string placement, side, castle, ep;
    int rule50 = 0;
    fullmove = 1;
    if (!(is >> placement >> side >> castle >> ep))
        return false;
    is >> rule50 >> fullmove;

    byType[0] = byType[1] = byType[2] = byType[3] = byType[4] = byType[5] = 0;
    byColor[WHITE] = byColor[BLACK] = 0;
    for (Piece& p : board)
        p = NO_PIECE;

    int file = 0, rank = 7;
    for (char c : placement) {
        if (c == '/') {
            file = 0;
            --rank;
        } else if (c >= '1' && c <= '8')
            file += c - '0';
        else {
            size_t idx = PieceChars.find(c);
            if (idx == std::string::npos || file > 7 || rank < 0)
                return false;
            put_piece(Piece(idx), make_square(file++, rank));
        }
    }
    if (popcount(pieces(WHITE, KING)) != 1 || popcount(pieces(BLACK, KING)) != 1)
        return false;

    stm = side == "b" ? BLACK : WHITE;

    StateInfo st{};
    for (char c : castle) {
        // Only keep rights whose king and rook are on their home squares.
        Square king = c == 'K' || c == 'Q' ? make_square(4, 0) : make_square(4, 7);
        Color owner = c == 'K' || c == 'Q' ? WHITE : BLACK;
        Square rook = make_square(c == 'K' || c == 'k' ? 7 : 0, rank_of(king));
        if (c != 'K' && c != 'Q' && c != 'k' && c != 'q')
            continue;
        if (board[king] != make_piece(owner, KING) || board[rook] != make_piece(owner, ROOK))
            continue;
        st.castling |= c == 'K' ? WHITE_OO : c == 'Q' ? WHITE_OOO : c == 'k' ? BLACK_OO : BLACK_OOO;
    }

    // An en passant square only counts if a pawn can actually capture there.
    st.ep = SQ_NONE;
    if (ep.size() == 2 && ep[0] >= 'a' && ep[0] <= 'h' && (ep[1] == '3' || ep[1] == '6')) {
        Square s = make_square(ep[0] - 'a', ep[1] - '1');
        if (PawnAttacks[~stm][s] & pieces(stm, PAWN))
            st.ep = s;
    }
    st.rule50 = rule50;
    st.captured = NO_PIECE;

    states.clear();
    states.reserve(1024);
    states.push_back(st);
    states.back().key = compute_key();
    return true;
}

std::string Position::fen() const {
    std::string out;
    for (int rank = 7; rank >= 0; --rank) {
        int empty = 0;
        for (int file = 0; file < 8; ++file) {
            Piece p = board[make_square(file, rank)];
            if (p == NO_PIECE)
                ++empty;
            else {
                if (empty)
                    out += char('0' + empty);
                empty = 0;
                out += PieceChars[p];
            }
        }
        if (empty)
            out += char('0' + empty);
        if (rank)
            out += '/';
    }
    out += stm == WHITE ? " w " : " b ";
    int cr = castling_rights();
    if (!cr)
        out += '-';
    if (cr & WHITE_OO) out += 'K';
    if (cr & WHITE_OOO) out += 'Q';
    if (cr & BLACK_OO) out += 'k';
    if (cr & BLACK_OOO) out += 'q';
    out += ' ';
    out += ep_square() == SQ_NONE ? "-" : square_to_string(ep_square());
    out += " " + std::to_string(rule50()) + " " + std::to_string(fullmove);
    return out;
}

std::string Position::pretty() const {
    std::string out = " +---+---+---+---+---+---+---+---+\n";
    for (int rank = 7; rank >= 0; --rank) {
        for (int file = 0; file < 8; ++file) {
            Piece p = board[make_square(file, rank)];
            out += " | ";
            out += p == NO_PIECE ? ' ' : PieceChars[p];
        }
        out += " | " + std::to_string(rank + 1) + "\n +---+---+---+---+---+---+---+---+\n";
    }
    out += "   a   b   c   d   e   f   g   h\n\nFen: " + fen() + "\n";
    return out;
}

bool Position::attacked(Square s, Color by) const {
    Bitboard occ = pieces();
    return (PawnAttacks[~by][s] & pieces(by, PAWN))
        || (KnightAttacks[s] & pieces(by, KNIGHT))
        || (KingAttacks[s] & pieces(by, KING))
        || (bishop_attacks(s, occ) & (pieces(by, BISHOP) | pieces(by, QUEEN)))
        || (rook_attacks(s, occ) & (pieces(by, ROOK) | pieces(by, QUEEN)));
}

bool Position::do_move(Move m) {
    StateInfo prev = states.back();
    states.push_back(prev);
    StateInfo& st = states.back();
    st.captured = NO_PIECE;
    ++st.rule50;
    ++st.pliesFromNull;

    Color us = stm, them = ~us;
    Square from = from_sq(m), to = to_sq(m);
    Piece pc = board[from];
    int type = move_type(m);

    if (st.ep != SQ_NONE) {
        st.key ^= Zobrist::epFile[file_of(st.ep)];
        st.ep = SQ_NONE;
    }

    if (type == CASTLING) {
        bool kingside = to > from;
        Square rookFrom = kingside ? from + 3 : from - 4;
        Square rookTo = kingside ? from + 1 : from - 1;
        Piece rook = board[rookFrom];
        move_piece(from, to);
        move_piece(rookFrom, rookTo);
        st.key ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];
        st.key ^= Zobrist::psq[rook][rookFrom] ^ Zobrist::psq[rook][rookTo];
    } else {
        Square capSq = type == EN_PASSANT ? (us == WHITE ? to - 8 : to + 8) : to;
        Piece captured = board[capSq];
        if (captured != NO_PIECE) {
            remove_piece(capSq);
            st.key ^= Zobrist::psq[captured][capSq];
            st.captured = captured;
            st.rule50 = 0;
        }

        move_piece(from, to);
        st.key ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];

        if (type_of(pc) == PAWN) {
            st.rule50 = 0;
            if (type == PROMOTION) {
                Piece promo = make_piece(us, promotion_type(m));
                remove_piece(to);
                put_piece(promo, to);
                st.key ^= Zobrist::psq[pc][to] ^ Zobrist::psq[promo][to];
            } else if (to - from == 16 || from - to == 16) {
                Square ep = (from + to) / 2;
                if (PawnAttacks[us][ep] & pieces(them, PAWN)) {
                    st.ep = ep;
                    st.key ^= Zobrist::epFile[file_of(ep)];
                }
            }
        }
    }

    int castling = st.castling & CastlingMask[from] & CastlingMask[to];
    if (castling != st.castling) {
        st.key ^= Zobrist::castling[st.castling] ^ Zobrist::castling[castling];
        st.castling = castling;
    }

    stm = them;
    st.key ^= Zobrist::side;
    if (us == BLACK)
        ++fullmove;

    return !attacked(king_square(us), them);
}

void Position::undo_move(Move m) {
    stm = ~stm;
    Color us = stm;
    if (us == BLACK)
        --fullmove;

    Square from = from_sq(m), to = to_sq(m);
    int type = move_type(m);
    const StateInfo& st = states.back();

    if (type == CASTLING) {
        bool kingside = to > from;
        Square rookFrom = kingside ? from + 3 : from - 4;
        Square rookTo = kingside ? from + 1 : from - 1;
        move_piece(to, from);
        move_piece(rookTo, rookFrom);
    } else {
        if (type == PROMOTION) {
            remove_piece(to);
            put_piece(make_piece(us, PAWN), to);
        }
        move_piece(to, from);
        if (st.captured != NO_PIECE) {
            Square capSq = type == EN_PASSANT ? (us == WHITE ? to - 8 : to + 8) : to;
            put_piece(st.captured, capSq);
        }
    }

    states.pop_back();
}

void Position::do_null_move() {
    StateInfo prev = states.back();
    states.push_back(prev);
    StateInfo& st = states.back();
    st.captured = NO_PIECE;
    ++st.rule50;
    st.pliesFromNull = 0;
    if (st.ep != SQ_NONE) {
        st.key ^= Zobrist::epFile[file_of(st.ep)];
        st.ep = SQ_NONE;
    }
    stm = ~stm;
    st.key ^= Zobrist::side;
}

void Position::undo_null_move() {
    stm = ~stm;
    states.pop_back();
}

bool Position::is_draw() const {
    const StateInfo& st = states.back();
    if (st.rule50 >= 100)
        return true;

    int lookback = std::min(std::min(st.rule50, st.pliesFromNull), int(states.size()) - 1);
    for (int i = 4; i <= lookback; i += 2)
        if (states[states.size() - 1 - i].key == st.key)
            return true;
    return false;
}

std::string square_to_string(Square s) {
    return {char('a' + file_of(s)), char('1' + rank_of(s))};
}

std::string move_to_uci(Move m) {
    if (m == MOVE_NONE)
        return "0000";
    std::string out = square_to_string(from_sq(m)) + square_to_string(to_sq(m));
    if (move_type(m) == PROMOTION)
        out += "nbrq"[promotion_type(m) - KNIGHT];
    return out;
}
