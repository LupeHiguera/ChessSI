#include "nnue.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
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
constexpr int MaxHidden = 4096;

// The pairwise tail's integers. Its activations are bytes in [0, 127] whose 1.0 is QA * QA >> PairShift (127.0):
// the pairwise products, and each layer's sum shifted down by WeightShift and clamped. 127 is the cap because two
// products of an activation and an int8 weight then sum to at most 2 * 127 * 128, inside int16, so maddubs never
// saturates and equals vpdpbusd and the GPU's __dp4a.
constexpr int L1Size = 16, L2Size = 32;
constexpr int PairShift = 9;   // two values in [0, QA], multiplied, to [0, 127]
constexpr int WeightShift = 6; // L1 and L2 weights are int8 at 1 << WeightShift, their biases int32 at 127.0 times that
constexpr int OutQ = 1024;     // L3 weights are int16 at OutQ, its bias int32 at 127.0 * OutQ

enum class Tail : int32_t { SCReLU, Pairwise };

// File layout written by nnue/train.py, all little-endian.
struct Network {
    int hidden = 0;
    bool mirrored = false;
    Tail tail = Tail::SCReLU;
    std::vector<int16_t> ftWeights; // [Inputs][hidden]
    std::vector<int16_t> ftBias;    // [hidden]
    std::vector<int16_t> outWeights; // SCReLU: [2 * hidden], side to move first, then the opponent
    int32_t outBias = 0;
    // Pairwise: L1's inputs are the side to move's hidden / 2 products, then the opponent's. L1 and L2 weights are
    // in input-major groups of four, input i's weight for output o at (i / 4) * outputs * 4 + o * 4 + i % 4, so a
    // group of four inputs reads one block of outputs * 4 bytes.
    alignas(64) std::array<int8_t, (MaxHidden + 4) * L1Size> l1Weights{}; // and the padding group's, see pairwise_avx2
    alignas(32) std::array<int32_t, L1Size> l1Bias{};
    alignas(32) std::array<int8_t, L1Size * L2Size> l2Weights{};
    alignas(32) std::array<int32_t, L2Size> l2Bias{};
    alignas(32) std::array<int32_t, L2Size> l3Weights{}; // int16 in the file
    int32_t l3Bias = 0;
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

// "CSNN" <hidden> <first layer> <SCReLU tail>; "CSNM" the same, mirrored. "CSN2" <hidden> <mirrored: 0 or 1>
// <tail: 0 SCReLU, 1 pairwise> <first layer> <that tail>, all int32 fields. An older binary knows only the first
// two magics, so it refuses a CSN2 file.
bool parse(const char* data, size_t size) {
    size_t pos = 0;
    char magic[4];
    Network n;
    if (!read(data, size, pos, magic, 4) || !read(data, size, pos, &n.hidden, 1))
        return false;
    if (std::memcmp(magic, "CSN2", 4) == 0) {
        int32_t mirrored, tail;
        if (!read(data, size, pos, &mirrored, 1) || !read(data, size, pos, &tail, 1) || mirrored < 0 || mirrored > 1
            || tail < 0 || tail > 1)
            return false;
        n.mirrored = mirrored;
        n.tail = Tail(tail);
    } else if (std::memcmp(magic, "CSNM", 4) == 0)
        n.mirrored = true;
    else if (std::memcmp(magic, "CSNN", 4) != 0)
        return false;
    // The pairwise step takes 32 units of each half at a time.
    if (n.hidden <= 0 || n.hidden > MaxHidden || n.hidden % (n.tail == Tail::Pairwise ? 64 : 32) != 0)
        return false;
    n.ftWeights.resize(size_t(Inputs) * n.hidden);
    n.ftBias.resize(n.hidden);
    if (!read(data, size, pos, n.ftWeights.data(), n.ftWeights.size())
        || !read(data, size, pos, n.ftBias.data(), n.ftBias.size()))
        return false;
    if (n.tail == Tail::SCReLU) {
        n.outWeights.resize(2 * size_t(n.hidden));
        if (!read(data, size, pos, n.outWeights.data(), n.outWeights.size()) || !read(data, size, pos, &n.outBias, 1))
            return false;
        // evaluate() needs QA * w to fit int16.
        for (int16_t w : n.outWeights)
            if (w < -128 || w > 128)
                return false;
    } else {
        int16_t l3[L2Size];
        if (!read(data, size, pos, n.l1Weights.data(), size_t(n.hidden) * L1Size)
            || !read(data, size, pos, n.l1Bias.data(), L1Size) || !read(data, size, pos, n.l2Weights.data(), L1Size * L2Size)
            || !read(data, size, pos, n.l2Bias.data(), L2Size) || !read(data, size, pos, l3, L2Size)
            || !read(data, size, pos, &n.l3Bias, 1) || pos != size)
            return false;
        std::copy(l3, l3 + L2Size, n.l3Weights.begin());
    }
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

// A mirrored network's refresh cache, per thread: for each perspective and each of its two orientations, the
// half last built for it and the pieces it was built from. A rebuild starts from that entry and adds or removes
// only the pieces that differ, usually a few where a full refresh adds all of them. Integer sums come out the
// same in any order, so the result equals refresh_half's.
struct CacheEntry {
    std::vector<int16_t> half;
    Bitboard pieces[12] = {}; // by Piece
};
thread_local struct {
    int generation = 0;
    CacheEntry entries[2][2]; // [perspective][files flipped]
} cache;

void rebuild_half(const Position& pos, Color persp, int16_t* half) {
    if (cache.generation != loadedGeneration) {
        for (auto& side : cache.entries)
            for (CacheEntry& e : side)
                e = {net.ftBias, {}};
        cache.generation = loadedGeneration;
    }
    const int h = net.hidden, o = orientation(pos, persp, true);
    CacheEntry& e = cache.entries[persp][o & 7 ? 1 : 0];
    for (Piece p = 0; p < 12; ++p) {
        const Bitboard now = pos.pieces(color_of(p), type_of(p));
        for (Bitboard b = e.pieces[p] & ~now; b;) {
            const int16_t* row = &net.ftWeights[size_t(feature(persp, p, pop_lsb(b), o)) * h];
            for (int i = 0; i < h; ++i)
                e.half[i] -= row[i];
        }
        for (Bitboard b = now & ~e.pieces[p]; b;) {
            const int16_t* row = &net.ftWeights[size_t(feature(persp, p, pop_lsb(b), o)) * h];
            for (int i = 0; i < h; ++i)
                e.half[i] += row[i];
        }
        e.pieces[p] = now;
    }
    std::copy(e.half.begin(), e.half.end(), half);
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
            rebuild_half(pos, c, acc + persp * h);
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

template <bool Mirrored>
void apply_delta(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, const Position& pos) {
    switch (d.adds * 4 + d.subs) {
    case 1 * 4 + 1: apply_both<Mirrored, 1, 1>(prev, acc, d, pos); break; // quiet move, promotion
    case 1 * 4 + 2: apply_both<Mirrored, 1, 2>(prev, acc, d, pos); break; // capture
    case 2 * 4 + 2: apply_both<Mirrored, 2, 2>(prev, acc, d, pos); break; // castling
    default: std::abort();                                                 // do_move makes no other delta
    }
}

// Out of line, so the mirrored code stays out of the plain update's function body: inlined beside it, it left
// plain networks 0.4% slower.
[[gnu::noinline]] void apply_mirrored(const int16_t* prev, int16_t* acc, const NNUE::Delta& d, const Position& pos) {
    apply_delta<true>(prev, acc, d, pos);
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

// The pairwise tail in plain integer arithmetic, the reference for the vectorized version. Each perspective's
// unit j times its unit hidden / 2 + j, both clipped to [0, QA] and the product shifted to a byte, side to move
// first; L1 and L2 sum, shift down and clamp; L3's sum is scaled to centipawns in 64 bits. liveGroups, if given,
// gets the number of groups of four products with a non-zero byte.
[[maybe_unused]] int pairwise_scalar(const int16_t* const halves[2], uint64_t* liveGroups = nullptr) {
    const int h = net.hidden, half = h / 2;
    uint8_t in[MaxHidden];
    for (int p = 0; p < 2; ++p)
        for (int j = 0; j < half; ++j)
            in[p * half + j] = uint8_t(std::clamp<int>(halves[p][j], 0, QA) * std::clamp<int>(halves[p][half + j], 0, QA)
                                       >> PairShift);
    if (liveGroups)
        for (int g = 0; g < h / 4; ++g)
            *liveGroups += (in[4 * g] | in[4 * g + 1] | in[4 * g + 2] | in[4 * g + 3]) != 0;
    int l1[L1Size];
    for (int o = 0; o < L1Size; ++o) {
        int sum = net.l1Bias[o];
        for (int i = 0; i < h; ++i)
            sum += in[i] * net.l1Weights[i / 4 * L1Size * 4 + o * 4 + i % 4];
        l1[o] = std::clamp(sum >> WeightShift, 0, 127);
    }
    int64_t out = net.l3Bias;
    for (int o = 0; o < L2Size; ++o) {
        int sum = net.l2Bias[o];
        for (int i = 0; i < L1Size; ++i)
            sum += l1[i] * net.l2Weights[i / 4 * L2Size * 4 + o * 4 + i % 4];
        out += std::clamp(sum >> WeightShift, 0, 127) * net.l3Weights[o];
    }
    return int(out * Scale * (1 << PairShift) / (int64_t(QA) * QA * OutQ));
}

#if defined(__AVX2__)
inline __m256i load(const void* p) {
    return _mm256_loadu_si256(static_cast<const __m256i*>(p));
}

// Four bytes from p in every int32 lane.
inline __m256i broadcast4(const uint8_t* p) {
    int32_t v;
    std::memcpy(&v, p, 4);
    return _mm256_set1_epi32(v);
}

// Unsigned bytes u times signed bytes w, summed in fours into sum's int32 lanes.
inline __m256i dpbusd(__m256i sum, __m256i u, __m256i w) {
#if defined(__AVXVNNI__)
    return _mm256_dpbusd_avx_epi32(sum, u, w);
#else
    return _mm256_add_epi32(sum, _mm256_madd_epi16(_mm256_maddubs_epi16(u, w), _mm256_set1_epi16(1)));
#endif
}

inline __m256i activate(__m256i sum) {
    const __m256i v = _mm256_srai_epi32(sum, WeightShift);
    return _mm256_min_epi32(_mm256_max_epi32(v, _mm256_setzero_si256()), _mm256_set1_epi32(127));
}

// For each 8-bit mask, the positions of its set bits (the rest 0).
alignas(64) constexpr auto SetBits = [] {
    std::array<std::array<uint16_t, 8>, 256> t{};
    for (int m = 0; m < 256; ++m)
        for (int b = 0, k = 0; b < 8; ++b)
            if (m >> b & 1)
                t[m][k++] = uint16_t(b);
    return t;
}();

// pairwise_scalar's integers, vectorized. The pairwise step also lists the groups of four products with a non-zero
// byte, and L1 reads only those: zeros add nothing to an integer sum.
int pairwise_avx2(const int16_t* const halves[2]) {
    const int h = net.hidden, half = h / 2;
    // One more group of four zero bytes, group h / 4, pads the list of live groups to a multiple of four.
    alignas(32) uint8_t in[MaxHidden + 4];
    std::memset(in + h, 0, 4);
    uint16_t live[MaxHidden / 4 + 8]; // a store writes 8 entries however few are live
    int count = 0;
    const __m256i zero = _mm256_setzero_si256(), qa = _mm256_set1_epi16(QA);
    __m128i first = _mm_setzero_si128(); // the index of the first of the next eight groups
    for (int p = 0; p < 2; ++p)
        for (int j = 0; j < half; j += 32) {
            const int16_t* x = halves[p] + j;
            // mulhi of a << 7 and b is a * b >> 9. b needs no clip at 0: a negative product packs to 0.
            const __m256i a0 = _mm256_slli_epi16(_mm256_min_epi16(_mm256_max_epi16(load(x), zero), qa), 7);
            const __m256i a1 = _mm256_slli_epi16(_mm256_min_epi16(_mm256_max_epi16(load(x + 16), zero), qa), 7);
            const __m256i p0 = _mm256_mulhi_epi16(a0, _mm256_min_epi16(load(x + half), qa));
            const __m256i p1 = _mm256_mulhi_epi16(a1, _mm256_min_epi16(load(x + half + 16), qa));
            // packus works within 128-bit lanes; the permute puts the bytes back in unit order.
            const __m256i bytes = _mm256_permute4x64_epi64(_mm256_packus_epi16(p0, p1), 0xD8);
            _mm256_store_si256(reinterpret_cast<__m256i*>(in + p * half + j), bytes);
            const int mask = _mm256_movemask_ps(_mm256_castsi256_ps(_mm256_cmpgt_epi32(bytes, zero)));
            const __m128i bits = _mm_load_si128(reinterpret_cast<const __m128i*>(SetBits[mask].data()));
            _mm_storeu_si128(reinterpret_cast<__m128i*>(live + count), _mm_add_epi16(bits, first));
            count += std::popcount(unsigned(mask));
            first = _mm_add_epi16(first, _mm_set1_epi16(8));
        }
    _mm_storeu_si128(reinterpret_cast<__m128i*>(live + count), _mm_set1_epi16(int16_t(h / 4)));
    // Four groups per step into eight sums: vpdpbusd's result is ready five cycles later on this CPU and it can start
    // two a cycle, so it takes eight independent sums to keep it busy. Unsigned 64-bit indices: with int ones GCC spent
    // seven instructions per address.
    const int8_t* const weights = net.l1Weights.data();
    auto add_group = [&](size_t g, __m256i& lo, __m256i& hi) {
        const __m256i u = broadcast4(in + 4 * g);
        lo = dpbusd(lo, u, load(weights + L1Size * 4 * g));
        hi = dpbusd(hi, u, load(weights + L1Size * 4 * g + 32));
    };
    __m256i a0 = zero, a1 = zero, b0 = zero, b1 = zero, c0 = zero, c1 = zero, d0 = zero, d1 = zero;
    for (int i = 0; i < count; i += 4) {
        add_group(live[i], a0, a1);
        add_group(live[i + 1], b0, b1);
        add_group(live[i + 2], c0, c1);
        add_group(live[i + 3], d0, d1);
    }
    const __m256i sumLo = _mm256_add_epi32(_mm256_add_epi32(a0, b0), _mm256_add_epi32(c0, d0));
    const __m256i sumHi = _mm256_add_epi32(_mm256_add_epi32(a1, b1), _mm256_add_epi32(c1, d1));
    const __m256i lo = activate(_mm256_add_epi32(sumLo, load(net.l1Bias.data())));
    const __m256i hi = activate(_mm256_add_epi32(sumHi, load(net.l1Bias.data() + 8)));
    const __m256i words = _mm256_permute4x64_epi64(_mm256_packs_epi32(lo, hi), 0xD8);
    alignas(16) uint8_t l1[L1Size];
    _mm_store_si128(reinterpret_cast<__m128i*>(l1),
                    _mm_packus_epi16(_mm256_castsi256_si128(words), _mm256_extracti128_si256(words, 1)));
    __m256i l2[L2Size / 8];
    for (int q = 0; q < L2Size / 8; ++q)
        l2[q] = load(net.l2Bias.data() + 8 * q);
    for (int g = 0; g < L1Size / 4; ++g) {
        const __m256i u = broadcast4(l1 + 4 * g);
        for (int q = 0; q < L2Size / 8; ++q)
            l2[q] = dpbusd(l2[q], u, load(net.l2Weights.data() + (g * L2Size + 8 * q) * 4));
    }
    __m256i sum = zero;
    for (int q = 0; q < L2Size / 8; ++q)
        sum = _mm256_add_epi32(sum, _mm256_mullo_epi32(activate(l2[q]), load(net.l3Weights.data() + 8 * q)));
    __m128i s = _mm_add_epi32(_mm256_castsi256_si128(sum), _mm256_extracti128_si256(sum, 1));
    s = _mm_add_epi32(s, _mm_shuffle_epi32(s, 0x4E));
    s = _mm_add_epi32(s, _mm_shuffle_epi32(s, 0xB1));
    const int64_t out = int64_t(net.l3Bias) + _mm_cvtsi128_si32(s);
    return int(out * Scale * (1 << PairShift) / (int64_t(QA) * QA * OutQ));
}
#endif

#ifdef CHECK_EVAL
// With -DCHECK_EVAL added to CXXFLAGS, every pairwise evaluation is also computed by pairwise_scalar and must be
// equal; the count and the share of live groups of four print at exit.
std::atomic<uint64_t> checkedEvals{0}, liveGroups{0}, groups{0};
struct EvalReport {
    ~EvalReport() {
        std::fprintf(stderr, "pairwise check: %llu evaluations equal to the scalar tail; %.2f%% of groups of four live\n",
                     (unsigned long long)checkedEvals, groups ? 100.0 * liveGroups / groups : 0.0);
    }
} evalReport;
#endif

// Out of line, so the SCReLU path keeps its code layout.
[[gnu::noinline]] int evaluate_pairwise(const int16_t* const halves[2]) {
#if defined(__AVX2__)
    const int v = pairwise_avx2(halves);
#else
    const int v = pairwise_scalar(halves);
#endif
#ifdef CHECK_EVAL
    uint64_t live = 0;
    if (pairwise_scalar(halves, &live) != v) {
        std::fprintf(stderr, "pairwise evaluation %d differs from the scalar tail's %d\n", v, pairwise_scalar(halves));
        std::abort();
    }
    ++checkedEvals;
    liveGroups += live;
    groups += net.hidden / 4;
#endif
    return v;
}

} // namespace

void NNUE::refresh(const Position& pos, int16_t* acc) {
    refresh_half(pos, WHITE, acc);
    refresh_half(pos, BLACK, acc + net.hidden);
}

void NNUE::apply(const int16_t* prev, int16_t* acc, const Delta& d, const Position& pos) {
    if (net.mirrored)
        apply_mirrored(prev, acc, d, pos);
    else
        apply_delta<false>(prev, acc, d, pos);
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
    if (net.tail == Tail::Pairwise)
        return evaluate_pairwise(halves);

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
