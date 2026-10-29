#include "nnue.h"

#include <algorithm>
#include <cstdint>
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

// File layout written by nnue/train.py (nnue/arch.py), all little-endian.
// CSNN: magic, hidden, ft int16[768][H], bias int16[H], out int16[2H], out bias int32.
// CSKB: magic, hidden, buckets (8 or 16), ft int16[buckets][768][H], then the CSNN bias and output.
// A CSNN file does not parse as CSKB. net13 is the bucketed file; net12 stays CSNN.
struct Network {
    int hidden = 0;
    int buckets = 1;
    std::vector<int16_t> ftWeights; // [buckets][Inputs][hidden]
    std::vector<int16_t> ftBias;    // [hidden]
    std::vector<int16_t> outWeights; // [2 * hidden]: side to move first, then the opponent
    int32_t outBias = 0;
};

Network net;
int loadedGeneration = 0;

// Feature index from `persp`'s point of view: own pieces first, squares mirrored for Black.
int feature(Color persp, Piece p, Square s) {
    int side = color_of(p) == persp ? 0 : 384;
    return side + type_of(p) * 64 + (persp == WHITE ? s : s ^ 56);
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

bool out_weights_fit(const std::vector<int16_t>& w) {
    // evaluate() needs QA * w to fit int16.
    for (int16_t x : w)
        if (x < -128 || x > 128)
            return false;
    return true;
}

bool parse(const char* data, size_t size) {
    size_t pos = 0;
    char magic[4];
    Network n;
    if (!read(data, size, pos, magic, 4) || !read(data, size, pos, &n.hidden, 1)
        || n.hidden <= 0 || n.hidden > 4096 || n.hidden % 32 != 0)
        return false;
    const bool csnn = std::memcmp(magic, "CSNN", 4) == 0;
    const bool cskb = std::memcmp(magic, "CSKB", 4) == 0;
    if (cskb) {
        if (!read(data, size, pos, &n.buckets, 1) || (n.buckets != 8 && n.buckets != 16))
            return false;
    } else if (!csnn)
        return false;
    n.ftWeights.resize(size_t(n.buckets) * Inputs * n.hidden);
    n.ftBias.resize(n.hidden);
    n.outWeights.resize(2 * size_t(n.hidden));
    if (!read(data, size, pos, n.ftWeights.data(), n.ftWeights.size())
        || !read(data, size, pos, n.ftBias.data(), n.ftBias.size())
        || !read(data, size, pos, n.outWeights.data(), n.outWeights.size()) || !read(data, size, pos, &n.outBias, 1)
        || !out_weights_fit(n.outWeights))
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

// acc[i] = prev[i] + the added rows - the removed rows, in one pass; A and S are known at compile
// time so the loop vectorizes. prev may equal acc.
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

const int16_t* ft_row(int bucket, int featureIndex) {
    return &net.ftWeights[(size_t(bucket) * Inputs + featureIndex) * net.hidden];
}

template <int A, int S>
void apply_both(const int16_t* prev, int16_t* acc, const NNUE::Delta& d) {
    const int h = net.hidden;
    for (int persp = 0; persp < 2; ++persp) {
        const int16_t* add[2];
        const int16_t* sub[2];
        for (int k = 0; k < A; ++k)
            add[k] = ft_row(0, feature(Color(persp), d.addPiece[k], d.addSq[k]));
        for (int k = 0; k < S; ++k)
            sub[k] = ft_row(0, feature(Color(persp), d.subPiece[k], d.subSq[k]));
        apply_rows<A, S>(prev + persp * h, acc + persp * h, add, sub, h);
    }
}

// One perspective, rows taken from `bucket`. Used when the king did not move.
template <int A, int S>
void apply_one(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, Color persp, int bucket) {
    const int16_t* add[2];
    const int16_t* sub[2];
    for (int k = 0; k < A; ++k)
        add[k] = ft_row(bucket, feature(persp, d.addPiece[k], d.addSq[k]));
    for (int k = 0; k < S; ++k)
        sub[k] = ft_row(bucket, feature(persp, d.subPiece[k], d.subSq[k]));
    apply_rows<A, S>(prev, acc, add, sub, net.hidden);
}

void apply_plain(const int16_t* prev, int16_t* acc, const NNUE::Delta& d) {
    switch (d.adds * 4 + d.subs) {
    case 1 * 4 + 1: apply_both<1, 1>(prev, acc, d); break; // quiet move, promotion
    case 1 * 4 + 2: apply_both<1, 2>(prev, acc, d); break; // capture
    case 2 * 4 + 2: apply_both<2, 2>(prev, acc, d); break; // castling
    case 1 * 4 + 0: apply_both<1, 0>(prev, acc, d); break;
    case 0 * 4 + 1: apply_both<0, 1>(prev, acc, d); break;
    case 0: if (prev != acc) std::copy(prev, prev + 2 * net.hidden, acc); break;
    default: // never produced by do_move
        apply_both<0, 0>(prev, acc, d);
        for (int k = 0; k < d.adds; ++k) {
            NNUE::Delta one;
            one.add(d.addPiece[k], d.addSq[k]);
            apply_plain(acc, acc, one);
        }
        for (int k = 0; k < d.subs; ++k) {
            NNUE::Delta one;
            one.sub(d.subPiece[k], d.subSq[k]);
            apply_plain(acc, acc, one);
        }
    }
}

// Rebuild one perspective from the position. `half` is that perspective's H values.
void refresh_side(const Position& pos, int16_t* half, Color persp) {
    const int h = net.hidden;
    const int bucket = NNUE::king_bucket(pos.king_square(persp), net.buckets);
    std::copy(net.ftBias.begin(), net.ftBias.end(), half);
    for (Bitboard b = pos.pieces(); b;) {
        Square s = pop_lsb(b);
        const int16_t* row = ft_row(bucket, feature(persp, pos.piece_on(s), s));
        const int16_t* add[1] = {row};
        apply_rows<1, 0>(half, half, add, nullptr, h);
    }
}

bool king_moved(const NNUE::Delta& d, Color c) {
    for (int k = 0; k < d.subs; ++k)
        if (type_of(d.subPiece[k]) == KING && color_of(d.subPiece[k]) == c)
            return true;
    for (int k = 0; k < d.adds; ++k)
        if (type_of(d.addPiece[k]) == KING && color_of(d.addPiece[k]) == c)
            return true;
    return false;
}

void apply_one_shaped(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, Color persp, int bucket) {
    switch (d.adds * 4 + d.subs) {
    case 1 * 4 + 1: apply_one<1, 1>(prev, acc, d, persp, bucket); break;
    case 1 * 4 + 2: apply_one<1, 2>(prev, acc, d, persp, bucket); break;
    case 2 * 4 + 2: apply_one<2, 2>(prev, acc, d, persp, bucket); break;
    case 1 * 4 + 0: apply_one<1, 0>(prev, acc, d, persp, bucket); break;
    case 0 * 4 + 1: apply_one<0, 1>(prev, acc, d, persp, bucket); break;
    case 0: if (prev != acc) std::copy(prev, prev + net.hidden, acc); break;
    default: break; // caller refreshes
    }
}

void apply_buckets(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, const Position& pos) {
    const int h = net.hidden;
    const int shape = d.adds * 4 + d.subs;
    const bool known = shape == 0 || shape == 1 || shape == 4 || shape == 5 || shape == 6 || shape == 10;
    for (int p = 0; p < 2; ++p) {
        Color persp = Color(p);
        int16_t* dst = acc + p * h;
        const int16_t* src = prev + p * h;
        // A king move changes every row of that perspective. Rebuild it. The other
        // perspective still has the same bucket, so it stays one add and one sub.
        if (king_moved(d, persp) || !known) {
            refresh_side(pos, dst, persp);
            continue;
        }
        apply_one_shaped(src, dst, d, persp, NNUE::king_bucket(pos.king_square(persp), net.buckets));
    }
}

} // namespace

void NNUE::refresh(const Position& pos, int16_t* acc) {
    const int h = net.hidden;
    if (net.buckets > 1) {
        refresh_side(pos, acc, WHITE);
        refresh_side(pos, acc + h, BLACK);
        return;
    }
    std::copy(net.ftBias.begin(), net.ftBias.end(), acc);
    std::copy(net.ftBias.begin(), net.ftBias.end(), acc + h);
    for (Bitboard b = pos.pieces(); b;) {
        Square s = pop_lsb(b);
        add(acc, pos.piece_on(s), s);
    }
}

// The trainer clips weights to +-1.98, so 32 pieces plus the bias stay within int16.
// Single-piece updates are the unbucketed refresh. A bucketed net uses refresh_side.
void NNUE::add(int16_t* acc, Piece p, Square s) {
    Delta d;
    d.add(p, s);
    apply_plain(acc, acc, d);
}

void NNUE::sub(int16_t* acc, Piece p, Square s) {
    Delta d;
    d.sub(p, s);
    apply_plain(acc, acc, d);
}

void NNUE::apply(const int16_t* prev, int16_t* acc, const Delta& d, const Position& pos) {
    if (net.buckets > 1)
        apply_buckets(prev, acc, d, pos);
    else
        apply_plain(prev, acc, d);
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
    // a block of 256 values sums to under 2^31 in int32 before it is widened.
    const __m256i lo = _mm256_setzero_si256(), hi = _mm256_set1_epi16(QA);
    for (int half = 0; half < 2; ++half) {
        const int16_t* x = halves[half];
        const int16_t* w = &net.outWeights[size_t(half) * h];
        for (int b = 0; b < h; b += 256) {
            __m256i lanes = _mm256_setzero_si256();
            for (int i = b, end = std::min(h, b + 256); i < end; i += 16) {
                __m256i xv = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(x + i));
                __m256i v = _mm256_min_epi16(_mm256_max_epi16(xv, lo), hi);
                __m256i vw = _mm256_mullo_epi16(v, _mm256_loadu_si256(reinterpret_cast<const __m256i*>(w + i)));
#if defined(__AVXVNNI__)
                lanes = _mm256_dpwssd_avx_epi32(lanes, vw, v);
#else
                lanes = _mm256_add_epi32(lanes, _mm256_madd_epi16(vw, v));
#endif
            }
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
