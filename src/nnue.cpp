#include "nnue.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

#include "position.h"

// `make EVALFILE=<net>` compiles that network into the binary as the default evaluation.
#ifdef EVALFILE
#ifdef _WIN32
#define NET_SECTION ".section .rdata,\"dr\"\n"
#else
#define NET_SECTION ".section .rodata\n"
#endif
asm(NET_SECTION ".balign 64\n"
    ".globl chesssi_net\nchesssi_net:\n"
    ".incbin \"" EVALFILE "\"\n"
    ".globl chesssi_net_end\nchesssi_net_end:\n"
    ".previous\n");
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
    std::vector<int16_t> ftWeights; // [Inputs][hidden]
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

bool parse(const char* data, size_t size) {
    size_t pos = 0;
    char magic[4];
    Network n;
    if (!read(data, size, pos, magic, 4) || std::memcmp(magic, "CSNN", 4) != 0 || !read(data, size, pos, &n.hidden, 1)
        || n.hidden <= 0 || n.hidden > 4096)
        return false;
    n.ftWeights.resize(size_t(Inputs) * n.hidden);
    n.ftBias.resize(n.hidden);
    n.outWeights.resize(2 * size_t(n.hidden));
    if (!read(data, size, pos, n.ftWeights.data(), n.ftWeights.size())
        || !read(data, size, pos, n.ftBias.data(), n.ftBias.size())
        || !read(data, size, pos, n.outWeights.data(), n.outWeights.size()) || !read(data, size, pos, &n.outBias, 1))
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

void NNUE::refresh(const Position& pos, int16_t* acc) {
    const int h = net.hidden;
    std::copy(net.ftBias.begin(), net.ftBias.end(), acc);
    std::copy(net.ftBias.begin(), net.ftBias.end(), acc + h);
    for (Bitboard b = pos.pieces(); b;) {
        Square s = pop_lsb(b);
        add(acc, pos.piece_on(s), s);
    }
}

// The trainer clips weights to +-1.98, so 32 pieces plus the bias stay within int16.
void NNUE::add(int16_t* acc, Piece p, Square s) {
    const int h = net.hidden;
    const int16_t* w = &net.ftWeights[size_t(feature(WHITE, p, s)) * h];
    const int16_t* b = &net.ftWeights[size_t(feature(BLACK, p, s)) * h];
    for (int i = 0; i < h; ++i) {
        acc[i] += w[i];
        acc[h + i] += b[i];
    }
}

void NNUE::sub(int16_t* acc, Piece p, Square s) {
    const int h = net.hidden;
    const int16_t* w = &net.ftWeights[size_t(feature(WHITE, p, s)) * h];
    const int16_t* b = &net.ftWeights[size_t(feature(BLACK, p, s)) * h];
    for (int i = 0; i < h; ++i) {
        acc[i] -= w[i];
        acc[h + i] -= b[i];
    }
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
    const int16_t* us = acc + (pos.side_to_move() == WHITE ? 0 : h);
    const int16_t* them = acc + (pos.side_to_move() == WHITE ? h : 0);

    // SCReLU: clamp to [0, QA] and square, so the sum carries QA * QA * QB; dividing by QA once
    // leaves QA * QB, the scale of the output bias.
    int64_t sum = 0;
    for (int i = 0; i < h; ++i) {
        int32_t x = std::clamp<int32_t>(us[i], 0, QA), y = std::clamp<int32_t>(them[i], 0, QA);
        sum += int64_t(x * x) * net.outWeights[i] + int64_t(y * y) * net.outWeights[h + i];
    }
    sum = sum / QA + net.outBias;
    return int(sum * Scale / (QA * QB));
}
