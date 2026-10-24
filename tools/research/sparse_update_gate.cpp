// Standalone synthetic gate; see docs/research/sparse-update-gate-2026-10-24/PROTOCOL.md.
// Build (root only): g++ -std=c++20 -O3 -march=native -Wall -Wextra tools/research/sparse_update_gate.cpp -o engines/sparse-update-gate
// Pin that compiler command to CPU 19 with taskset -c 19.
// Run: taskset -c 19 engines/sparse-update-gate [--hidden 256] [--passes 32] [--check-only]
// --passes accepts 1..128 for bounded checks; the predeclared measurement uses 32.
// No legal positions, trained network, search-frequency assumptions, or strength claims.
// Broad sparse/delta updates are Known; this is only a full-write runtime feasibility screen.
#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <vector>

#if defined(__GNUC__) && !defined(__clang__)
#define KERNEL __attribute__((noinline, noipa))
#elif defined(__clang__)
#define KERNEL __attribute__((noinline))
#else
#error "This standalone gate requires GCC or Clang (compiler memory barrier)."
#endif

namespace {
constexpr int Inputs = 768, Block = 32, Slots = 64, Ops = 2048, Rounds = 7;
constexpr int16_t Guard = 23130, Poison = 21930;
constexpr uint64_t Seed = 0x81936a42b7d5e0c1ULL;
volatile uint64_t consumed = 0;

void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
struct Random {
    uint64_t state;
    uint64_t next() { // Fixed SplitMix64; independent of standard-library distributions.
        uint64_t z = (state += 0x9e3779b97f4a7c15ULL);
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
        return z ^ (z >> 31);
    }
};
struct PieceAt { int color = 0, type = 0, square = 0; };
struct Delta { std::array<PieceAt, 2> add{}, sub{}; };
struct Network {
    int hidden;
    std::vector<int16_t> weights;
    std::array<uint8_t, Inputs> masks{};
    explicit Network(int h) : hidden(h), weights(size_t(Inputs) * h) {}
};
struct Buffer {
    size_t count;
    std::vector<int16_t> storage;
    explicit Buffer(size_t n) : count(n), storage(n + 2 * Block, Guard) { poison(); }
    int16_t* data() { return storage.data() + Block; }
    const int16_t* data() const { return storage.data() + Block; }
    void poison() { std::fill(data(), data() + count, Poison); }
    void guards() const {
        for (int i = 0; i < Block; ++i)
            require(storage[i] == Guard && storage[Block + count + i] == Guard, "guard overwritten");
    }
};
int feature(int perspective, const PieceAt& p) {
    return (p.color == perspective ? 0 : 384) + p.type * 64
         + (perspective == 0 ? p.square : p.square ^ 56);
}
template<int A, int S>
KERNEL void dense(const Network& net, const int16_t* prev, int16_t* child, const Delta& d) {
    const int h = net.hidden; // Runtime, as in NNUE::apply_both; not an H template.
    for (int perspective = 0; perspective < 2; ++perspective) {
        const int16_t* add[2];
        const int16_t* sub[2];
        for (int k = 0; k < A; ++k) add[k] = &net.weights[size_t(feature(perspective, d.add[k])) * h];
        for (int k = 0; k < S; ++k) sub[k] = &net.weights[size_t(feature(perspective, d.sub[k])) * h];
        for (int i = 0; i < h; ++i) {
            int16_t v = prev[perspective * h + i];
            for (int k = 0; k < A; ++k) v += add[k][i];
            for (int k = 0; k < S; ++k) v -= sub[k][i];
            child[perspective * h + i] = v;
        }
    }
}
template<int A, int S>
KERNEL void sparse(const Network& net, const int16_t* prev, int16_t* child, const Delta& d) {
    const int h = net.hidden;
    for (int perspective = 0; perspective < 2; ++perspective) {
        const int16_t* add[2];
        const int16_t* sub[2];
        unsigned changed = 0;
        for (int k = 0; k < A; ++k) {
            const int f = feature(perspective, d.add[k]);
            add[k] = &net.weights[size_t(f) * h];
            changed |= net.masks[f]; // Metadata reads and union are inside the timed call.
        }
        for (int k = 0; k < S; ++k) {
            const int f = feature(perspective, d.sub[k]);
            sub[k] = &net.weights[size_t(f) * h];
            changed |= net.masks[f];
        }
        for (int start = 0; start < h; start += Block) {
            if (!(changed & (1u << (start / Block)))) {
                std::copy(prev + perspective * h + start, prev + perspective * h + start + Block,
                          child + perspective * h + start);
            } else {
                for (int i = start; i < start + Block; ++i) {
                    int16_t v = prev[perspective * h + i];
                    for (int k = 0; k < A; ++k) v += add[k][i];
                    for (int k = 0; k < S; ++k) v -= sub[k][i];
                    child[perspective * h + i] = v; // Includes zero rows; no per-row oracle.
                }
            }
        }
    }
}
KERNEL void copy_only(const Network& net, const int16_t* prev, int16_t* child, const Delta&) {
    std::copy(prev, prev + 2 * net.hidden, child); // Non-equivalent optimistic reference only.
}
using Kernel = void (*)(const Network&, const int16_t*, int16_t*, const Delta&);
void barrier(const void* p) { asm volatile("" : : "g"(p) : "memory"); }

Network make_network(int h, int eighths, bool tied) {
    Network net(h);
    Random maskRng{Seed ^ 0x3a8e2716ULL}, valueRng{Seed ^ 0x119ce55bULL};
    std::array<uint8_t, 12> typeMasks{};
    auto mask = [&]() {
        unsigned m = 0;
        for (int b = 0; b < h / Block; ++b)
            if (int(maskRng.next() & 7) < eighths) m |= 1u << b;
        return uint8_t(m);
    };
    if (tied) for (auto& m : typeMasks) m = mask();
    for (int f = 0; f < Inputs; ++f) {
        net.masks[f] = tied ? typeMasks[f / 64] : mask();
        for (int i = 0; i < h; ++i) {
            const int magnitude = 1 + int(valueRng.next() & 63);
            const int value = (valueRng.next() & 1) ? magnitude : -magnitude;
            net.weights[size_t(f) * h + i] = (net.masks[f] & (1u << (i / Block))) ? value : 0;
        }
    }
    return net;
}
std::vector<Delta> make_operations(int kind) {
    Random rng{Seed ^ (uint64_t(kind + 1) * 0xd45a07ULL)};
    std::vector<Delta> ops(Ops);
    for (int i = 0; i < Ops; ++i) {
        const int color = i % 2, type = (i / 2) % 6; // Both colors and all six types.
        const int from = int(rng.next() % 64);
        const int to = (from + 1 + int(rng.next() % 63)) % 64;
        auto& d = ops[i];
        d.add[0] = {color, type, to};
        d.sub[0] = {color, type, from};
        if (kind == 1) d.sub[1] = {1 - color, (i / 12) % 5, to};
        if (kind == 2) {
            const int rank = color * 56;
            const bool kingside = (i / 2) % 2;
            d.sub[0] = {color, 5, rank + 4}; // King and rook, orthodox castle shape.
            d.sub[1] = {color, 3, rank + (kingside ? 7 : 0)};
            d.add[0] = {color, 5, rank + (kingside ? 6 : 2)};
            d.add[1] = {color, 3, rank + (kingside ? 5 : 3)};
        }
    }
    return ops;
}
uint64_t checksum(const Buffer& b) {
    uint64_t hash = 14695981039346656037ULL;
    for (size_t i = 0; i < b.count; ++i) hash = (hash ^ uint16_t(b.data()[i])) * 1099511628211ULL;
    consumed = hash;
    return hash;
}
void run_passes(Kernel kernel, const Network& net, const Buffer& parents, Buffer& children,
                const std::vector<Delta>& ops, int passes) {
    const size_t stride = size_t(2) * net.hidden;
    for (int pass = 0; pass < passes; ++pass)
        for (int i = 0; i < Ops; ++i) {
            int16_t* out = children.data() + size_t((i * 17) % Slots) * stride;
            kernel(net, parents.data() + size_t(i % Slots) * stride, out, ops[i]);
            barrier(out); // Each call's complete writes observable even across repeated passes.
        }
}
void bounded(int value) {
    require(value >= std::numeric_limits<int16_t>::min()
         && value <= std::numeric_limits<int16_t>::max(), "intermediate outside int16");
}
template<int A, int S>
void case_run(int h, int passes, bool checkOnly, int eighths, bool tied, const char* kind,
              const std::vector<Delta>& ops, size_t& checked) {
    Network net = make_network(h, eighths, tied);
    Buffer parents(size_t(Slots) * 2 * h), children(parents.count), expectedFinal(parents.count);
    Buffer copyFinal(parents.count), denseChild(2 * h), sparseChild(2 * h), copyChild(2 * h);
    Random rng{Seed ^ 0x32f017ULL};
    for (size_t i = 0; i < parents.count; ++i) parents.data()[i] = int(rng.next() % 4097) - 2048;
    const auto originalParents = parents.storage;
    const auto originalWeights = net.weights;
    const auto originalMasks = net.masks;
    auto readonly = [&]() {
        require(parents.storage == originalParents, "parent changed");
        require(net.weights == originalWeights && net.masks == originalMasks, "network changed");
        parents.guards();
    };
    std::vector<int16_t> expected(2 * h);
    uint64_t unionBlocks = 0, activeBlocks = 0;
    for (uint8_t m : net.masks) activeBlocks += std::popcount(unsigned(m));
    for (int j = 0; j < Ops; ++j) {
        const auto& d = ops[j];
        const int16_t* prev = parents.data() + size_t(j % Slots) * 2 * h;
        for (int perspective = 0; perspective < 2; ++perspective) {
            // Algebraically equivalent independent index formula for the scalar oracle.
            auto index = [&](const PieceAt& p) { return (p.color ^ perspective) * 384
                                                     + p.type * 64 + (p.square ^ (56 * perspective)); };
            unsigned u = 0;
            for (int k = 0; k < A; ++k) u |= net.masks[index(d.add[k])];
            for (int k = 0; k < S; ++k) u |= net.masks[index(d.sub[k])];
            unionBlocks += std::popcount(u);
            for (int i = 0; i < h; ++i) {
                int value = prev[perspective * h + i]; // Widened arithmetic, checked at every step.
                bounded(value);
                for (int k = 0; k < A; ++k) { value += net.weights[size_t(index(d.add[k])) * h + i]; bounded(value); }
                for (int k = 0; k < S; ++k) { value -= net.weights[size_t(index(d.sub[k])) * h + i]; bounded(value); }
                expected[perspective * h + i] = int16_t(value);
            }
        }
        denseChild.poison(); sparseChild.poison(); copyChild.poison();
        dense<A, S>(net, prev, denseChild.data(), d);
        sparse<A, S>(net, prev, sparseChild.data(), d);
        copy_only(net, prev, copyChild.data(), d);
        const size_t bytes = size_t(2) * h * sizeof(int16_t);
        require(std::memcmp(expected.data(), denseChild.data(), bytes) == 0, "dense/oracle mismatch");
        require(std::memcmp(expected.data(), sparseChild.data(), bytes) == 0, "sparse/oracle mismatch");
        require(std::memcmp(denseChild.data(), sparseChild.data(), bytes) == 0, "dense/sparse mismatch");
        require(std::memcmp(prev, copyChild.data(), bytes) == 0, "copy reference incomplete");
        require(std::memcmp(prev, originalParents.data() + Block + size_t(j % Slots) * 2 * h, bytes) == 0,
                "selected parent changed");
        denseChild.guards(); sparseChild.guards(); copyChild.guards();
        std::copy(expected.begin(), expected.end(), expectedFinal.data() + size_t((j * 17) % Slots) * 2 * h);
        std::copy(prev, prev + 2 * h, copyFinal.data() + size_t((j * 17) % Slots) * 2 * h);
        ++checked;
    }
    readonly();
    if (checkOnly) return;
    const double unionFraction = double(unionBlocks) / (Ops * 2 * (h / Block));
    const double activeFraction = double(activeBlocks) / (Inputs * (h / Block));
    const std::array<Kernel, 3> kernels{dense<A, S>, sparse<A, S>, copy_only};
    const std::array<const char*, 3> names{"dense", "sparse", "copy_only_non_equivalent"};
    for (int pair = 0; pair < Rounds; ++pair) {
        const std::array<int, 3> order = (pair % 2 == 0) ? std::array<int, 3>{0, 1, 2}
                                                       : std::array<int, 3>{1, 0, 2};
        for (int ordinal = 0; ordinal < 3; ++ordinal) {
            const int k = order[ordinal];
            children.poison();
            run_passes(kernels[k], net, parents, children, ops, 1); // One warmup per sample.
            checksum(children);
            barrier(children.data());
            const auto start = std::chrono::steady_clock::now();
            run_passes(kernels[k], net, parents, children, ops, passes);
            barrier(children.data());
            const auto end = std::chrono::steady_clock::now();
            const double ns = std::chrono::duration<double, std::nano>(end - start).count() / (Ops * passes);
            const uint64_t hash = checksum(children);
            readonly(); children.guards();
            const Buffer& wanted = k == 2 ? copyFinal : expectedFinal;
            require(std::memcmp(children.data(), wanted.data(), children.count * sizeof(int16_t)) == 0,
                    "timed output mismatch");
            std::cout << double(eighths) / 8 << ',' << (tied ? "piece_type_tied" : "independent")
                      << ',' << kind << ',' << pair + 1 << ',' << ordinal + 1 << ',' << names[k]
                      << ',' << passes << ',' << Ops * passes << ',' << h << ',' << Seed
                      << ',' << activeFraction << ',' << unionFraction << ',' << ns << ',' << hash << '\n';
        }
    }
}
int positive(std::string_view text) {
    int value = 0;
    auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
    require(parsed.ec == std::errc{} && parsed.ptr == text.data() + text.size() && value > 0, "invalid integer");
    return value;
}
} // namespace

int main(int argc, char** argv) {
    try {
        int h = 256, passes = 32;
        bool checkOnly = false;
        for (int i = 1; i < argc; ++i) {
            const std::string_view arg = argv[i];
            if (arg == "--check-only") checkOnly = true;
            else if ((arg == "--hidden" || arg == "--passes") && i + 1 < argc) {
                const int value = positive(argv[++i]);
                (arg == "--hidden" ? h : passes) = value;
            } else throw std::runtime_error("usage: sparse-update-gate [--hidden 256] [--passes 1..128] [--check-only]");
        }
        require(h == 256, "this declared gate supports only --hidden 256");
        require(passes <= 128, "--passes must be <= 128");
        std::array<std::vector<Delta>, 3> ops{make_operations(0), make_operations(1), make_operations(2)};
        size_t checked = 0;
        if (!checkOnly)
            std::cout << "q,correlation,kind,pair,order,kernel,passes,operations,hidden,seed,"
                         "active_mask_fraction,observed_union_fraction,ns_per_op,checksum\n" << std::setprecision(12);
        for (bool tied : {false, true})
            for (int eighths : {0, 1, 2, 4, 8}) {
                case_run<1, 1>(h, passes, checkOnly, eighths, tied, "quiet_A1S1", ops[0], checked);
                case_run<1, 2>(h, passes, checkOnly, eighths, tied, "capture_A1S2", ops[1], checked);
                case_run<2, 2>(h, passes, checkOnly, eighths, tied, "castle_A2S2", ops[2], checked);
            }
        std::cerr << "Correctness: " << checked << " operations; both perspectives, dense/sparse/oracle, "
                     "full writes, guards, unchanged inputs, intermediate int16 bounds; "
                     "parents [-2048,2048], nonzero weights +/-[1,64]; check_only=" << checkOnly << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 2;
    }
}
