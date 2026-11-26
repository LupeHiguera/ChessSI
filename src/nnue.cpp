#include "nnue.h"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

#include "position.h"

#if defined(__AVX2__)
#include <immintrin.h>
#endif

// `make EVALFILE=<net>` compiles that network into the binary as the default evaluation.
#ifdef EVALFILE
#ifdef _WIN32 // COFF has no .previous; the compiler expects .text after top-level asm
#define NET_SECTION ".section .rdata,\"dr\"\n"
#define NET_SECTION_END ".text\n"
#else
#define NET_SECTION ".section .rodata\n"
#define NET_SECTION_END ".previous\n"
#endif
asm(NET_SECTION ".balign 64\n"
    ".globl chesssi_net\nchesssi_net:\n"
    ".incbin \"" EVALFILE "\"\n"
    ".globl chesssi_net_end\nchesssi_net_end:\n"
    NET_SECTION_END);
extern "C" const unsigned char chesssi_net[], chesssi_net_end[];
static const unsigned char* const EmbeddedNet = chesssi_net;
static const unsigned char* const EmbeddedNetEnd = chesssi_net_end;
#endif

namespace {

constexpr int Inputs = 768;
constexpr int Scale = 400;
constexpr int QA = 255, QB = 64;

// File layout written by nnue/train.py, all little-endian.
struct Network {
    int hidden = 0;
    bool mirrored = false;          // magic "CSNM"; "CSNN" otherwise
    std::vector<int16_t> ftWeights; // [Inputs][hidden]
    std::vector<int16_t> ftBias;    // [hidden]
    std::vector<int16_t> outWeights; // [2 * hidden]: side to move first, then the opponent
    int32_t outBias = 0;
};

Network net;
int loadedGeneration = 0;

// What `persp` sees on square s is s ^ orientation: ranks flipped for Black, and with a mirrored network
// files flipped while that side's king stands on files e-h.
int orientation(const Position& pos, Color persp, bool mirrored) {
    int o = persp == WHITE ? 0 : 56;
    return mirrored && file_of(pos.king_square(persp)) >= 4 ? o ^ 7 : o;
}

// Feature index from `persp`'s point of view: own pieces first.
int feature(Color persp, Piece p, Square s, int orient) {
    int side = color_of(p) == persp ? 0 : 384;
    return side + type_of(p) * 64 + (s ^ orient);
}

// Reads `count` values from a byte buffer, advancing `pos`; false if the buffer is too short.
template <typename T>
bool read(const char* data, size_t size, size_t& pos, T* out, size_t count) {
    size_t bytes = count * sizeof(T);
    if (size - pos < bytes)
        return false;
    std::memcpy(out, data + pos, bytes);
    pos += bytes;
    return true;
}

bool parse(const char* data, size_t size) {
    size_t pos = 0;
    char magic[4];
    Network n;
    if (!read(data, size, pos, magic, 4))
        return false;
    n.mirrored = std::memcmp(magic, "CSNM", 4) == 0;
    if ((!n.mirrored && std::memcmp(magic, "CSNN", 4) != 0) || !read(data, size, pos, &n.hidden, 1) || n.hidden <= 0
        || n.hidden > 4096 || n.hidden % 32 != 0)
        return false;
    n.ftWeights.resize(size_t(Inputs) * n.hidden);
    n.ftBias.resize(n.hidden);
    n.outWeights.resize(2 * size_t(n.hidden));
    if (!read(data, size, pos, n.ftWeights.data(), n.ftWeights.size())
        || !read(data, size, pos, n.ftBias.data(), n.ftBias.size())
        || !read(data, size, pos, n.outWeights.data(), n.outWeights.size()) || !read(data, size, pos, &n.outBias, 1))
        return false;
    // evaluate() needs QA * w to fit int16.
    for (int16_t w : n.outWeights)
        if (w < -128 || w > 128)
            return false;
    net = std::move(n);
    ++loadedGeneration;
    return true;
}

} // namespace

bool NNUE::load(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in)
        return false;
    std::vector<char> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    return parse(bytes.data(), bytes.size());
}

bool NNUE::load_embedded() {
#ifdef EVALFILE
    return parse(reinterpret_cast<const char*>(EmbeddedNet), size_t(EmbeddedNetEnd - EmbeddedNet));
#else
    return false;
#endif
}

bool NNUE::has_embedded() {
#ifdef EVALFILE
    return true;
#else
    return false;
#endif
}

bool NNUE::loaded() {
    return loadedGeneration != 0;
}

int NNUE::generation() {
    return loadedGeneration;
}

int NNUE::hidden() {
    return net.hidden;
}

namespace {

// One perspective's half of an accumulator from scratch: the bias plus the row of every piece. The trainer
// clips weights to +-1.98, so 32 pieces plus the bias stay within int16.
void refresh_half(const Position& pos, Color persp, int16_t* half) {
    const int h = net.hidden, o = orientation(pos, persp, net.mirrored);
    std::copy(net.ftBias.begin(), net.ftBias.end(), half);
    for (Bitboard b = pos.pieces(); b;) {
        Square s = pop_lsb(b);
        const int16_t* row = &net.ftWeights[size_t(feature(persp, pos.piece_on(s), s, o)) * h];
        for (int i = 0; i < h; ++i)
            half[i] += row[i];
    }
}

// Whether the move d that led to pos changed how `persp` sees the board, with a mirrored network: when that
// side's king left a square on the other side of the d/e line from where it stands now.
bool reoriented(const NNUE::Delta& d, const Position& pos, Color persp) {
    const Piece king = make_piece(persp, KING);
    const Square now = pos.king_square(persp);
    for (int k = 0; k < d.subs; ++k)
        if (d.subPiece[k] == king && ((d.subSq[k] ^ now) & 4))
            return true;
    return false;
}

// acc[i] = prev[i] + the added rows - the removed rows, in one pass; A and S are known at compile
// time so the loop vectorizes.
template <int A, int S>
void apply_rows(const int16_t* prev, int16_t* acc, const int16_t* const* add, const int16_t* const* sub, int n) {
    for (int i = 0; i < n; ++i) {
        int16_t v = prev[i];
        for (int k = 0; k < A; ++k)
            v += add[k][i];
        for (int k = 0; k < S; ++k)
            v -= sub[k][i];
        acc[i] = v;
    }
}

template <bool Mirrored, int A, int S>
void apply_both(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, const Position& pos) {
    const int h = net.hidden;
    for (int persp = 0; persp < 2; ++persp) {
        const Color c = Color(persp);
        if (Mirrored && reoriented(d, pos, c)) {
            refresh_half(pos, c, acc + persp * h);
            continue;
        }
        const int o = orientation(pos, c, Mirrored);
        const int16_t* add[2];
        const int16_t* sub[2];
        for (int k = 0; k < A; ++k)
            add[k] = &net.ftWeights[size_t(feature(c, d.addPiece[k], d.addSq[k], o)) * h];
        for (int k = 0; k < S; ++k)
            sub[k] = &net.ftWeights[size_t(feature(c, d.subPiece[k], d.subSq[k], o)) * h];
        apply_rows<A, S>(prev + persp * h, acc + persp * h, add, sub, h);
    }
}

#ifdef CHECK_ACC
// With -DCHECK_ACC added to CXXFLAGS, every updated accumulator is compared with one built from scratch, and the
// counts print at exit, so a run shows how many updates it checked and how many halves were rebuilt.
std::atomic<uint64_t> checkedUpdates{0}, checkedRebuilds{0};
struct CheckReport {
    ~CheckReport() {
        std::fprintf(stderr, "accumulator check: %llu updates, %llu half rebuilds, all equal to a full refresh\n",
                     (unsigned long long)checkedUpdates, (unsigned long long)checkedRebuilds);
    }
} checkReport;

void check(const int16_t* acc, const NNUE::Delta& d, const Position& pos) {
    const int h = net.hidden;
    std::vector<int16_t> fresh(2 * size_t(h));
    for (int persp = 0; persp < 2; ++persp) {
        refresh_half(pos, Color(persp), fresh.data() + persp * h);
        checkedRebuilds += net.mirrored && reoriented(d, pos, Color(persp));
    }
    if (!std::equal(fresh.begin(), fresh.end(), acc)) {
        std::fprintf(stderr, "accumulator differs from a full refresh after a move to %s\n", pos.fen().c_str());
        std::abort();
    }
    ++checkedUpdates;
}
#endif

} // namespace

void NNUE::refresh(const Position& pos, int16_t* acc) {
    refresh_half(pos, WHITE, acc);
    refresh_half(pos, BLACK, acc + net.hidden);
}

void NNUE::apply(const int16_t* prev, int16_t* acc, const Delta& d, const Position& pos) {
    switch (net.mirrored * 16 + d.adds * 4 + d.subs) {
    case 1 * 4 + 1: apply_both<false, 1, 1>(prev, acc, d, pos); break; // quiet move, promotion
    case 1 * 4 + 2: apply_both<false, 1, 2>(prev, acc, d, pos); break; // capture
    case 2 * 4 + 2: apply_both<false, 2, 2>(prev, acc, d, pos); break; // castling
    case 16 + 1 * 4 + 1: apply_both<true, 1, 1>(prev, acc, d, pos); break;
    case 16 + 1 * 4 + 2: apply_both<true, 1, 2>(prev, acc, d, pos); break;
    case 16 + 2 * 4 + 2: apply_both<true, 2, 2>(prev, acc, d, pos); break;
    default: std::abort(); // do_move makes no other delta
    }
#ifdef CHECK_ACC
    check(acc, d, pos);
#endif
}

int NNUE::evaluate(const Position& pos) {
    const int h = net.hidden;
    const int16_t* acc = pos.accumulator();
    std::vector<int16_t> fresh;
    if (!acc) {
        fresh.resize(2 * size_t(h));
        refresh(pos, fresh.data());
        acc = fresh.data();
    }
    const int16_t* halves[2] = {acc + (pos.side_to_move() == WHITE ? 0 : h), acc + (pos.side_to_move() == WHITE ? h : 0)};

    // SCReLU: clamp to [0, QA] and square, so the sum carries QA * QA * QB; dividing by QA once
    // leaves QA * QB, the scale of the output bias. x * w fits int16 (255 * 128 at most, checked on
    // load), so x * (x * w) can be summed in int32 over chunks of 32 and then widened: the int16
    // products vectorize to twice the lanes of the plain x * x * w form, with the same result.
    int64_t sum = 0;
#if defined(__AVX2__)
    // The same integer sum, vectorized by hand: v * w with vpmullw, then (v * w) * v added in pairs
    // into int32 lanes with vpmaddwd (vpdpwssd with AVX-VNNI). A product is at most 255 * 32640, so
    // a block of 256 values sums to under 2^31 in int32 before it is widened. Four accumulators keep
    // four independent chains in flight; with one, each vpdpwssd waited for the previous.
    const __m256i lo = _mm256_setzero_si256(), hi = _mm256_set1_epi16(QA);
    auto term = [&](const int16_t* x, const int16_t* w, int i, __m256i acc) {
        __m256i xv = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(x + i));
        __m256i v = _mm256_min_epi16(_mm256_max_epi16(xv, lo), hi);
        __m256i vw = _mm256_mullo_epi16(v, _mm256_loadu_si256(reinterpret_cast<const __m256i*>(w + i)));
#if defined(__AVXVNNI__)
        return _mm256_dpwssd_avx_epi32(acc, vw, v);
#else
        return _mm256_add_epi32(acc, _mm256_madd_epi16(vw, v));
#endif
    };
    for (int half = 0; half < 2; ++half) {
        const int16_t* x = halves[half];
        const int16_t* w = &net.outWeights[size_t(half) * h];
        for (int b = 0; b < h; b += 256) {
            __m256i a0 = _mm256_setzero_si256(), a1 = a0, a2 = a0, a3 = a0;
            int i = b;
            const int end = std::min(h, b + 256);
            for (; i + 64 <= end; i += 64) {
                a0 = term(x, w, i, a0);
                a1 = term(x, w, i + 16, a1);
                a2 = term(x, w, i + 32, a2);
                a3 = term(x, w, i + 48, a3);
            }
            for (; i < end; i += 16)
                a0 = term(x, w, i, a0);
            __m256i lanes = _mm256_add_epi32(_mm256_add_epi32(a0, a1), _mm256_add_epi32(a2, a3));
            __m128i s = _mm_add_epi32(_mm256_castsi256_si128(lanes), _mm256_extracti128_si256(lanes, 1));
            s = _mm_add_epi32(s, _mm_shuffle_epi32(s, 0x4E));
            s = _mm_add_epi32(s, _mm_shuffle_epi32(s, 0xB1));
            sum += _mm_cvtsi128_si32(s);
        }
    }
#else
    for (int half = 0; half < 2; ++half) {
        const int16_t* x = halves[half];
        const int16_t* w = &net.outWeights[size_t(half) * h];
        for (int c = 0; c < h; c += 32) {
            int32_t chunk = 0;
            for (int i = c; i < c + 32; ++i) {
                int16_t v = std::clamp<int16_t>(x[i], 0, QA);
                chunk += int32_t(int16_t(v * w[i])) * v;
            }
            sum += chunk;
        }
    }
#endif
    sum = sum / QA + net.outBias;
    return int(sum * Scale / (QA * QB));
}
