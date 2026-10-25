// NNUE evaluation on the GPU (issue #31, stage 1b), appended to chess.cu at compile time.
//
// One warp per position: each of the 32 lanes owns H / 32 hidden units of both perspectives, so a
// weight row (H int16) is one coalesced read by the warp, and the output sum is a warp shuffle.
// The arithmetic follows NNUE::evaluate in src/nnue.cpp step by step (int16 accumulators, SCReLU
// clamp to [0, QA], int16 v * w times v, truncating divisions), so the result is bit-exact.
// H is fixed at compile time (-DH=256).

#ifndef H
#define H 256
#endif
#define QA 255
#define QB 64
#define EVAL_SCALE 400
#define UNITS (H / 32)

// Feature index of a piece from each perspective (White's view; Black's: colors swapped, ranks flipped).
__device__ __forceinline__ int feat_white(int c, int t, int s) { return (c * 6 + t) * 64 + s; }
__device__ __forceinline__ int feat_black(int c, int t, int s) { return ((c ^ 1) * 6 + t) * 64 + (s ^ 56); }

// acc[0] White's perspective, acc[1] Black's, for this lane's units, built from scratch.
__device__ __forceinline__ void refresh(const Pos& p, const short* ftw, const short* ftb, int base, short acc[2][UNITS]) {
    for (int j = 0; j < UNITS; ++j) acc[0][j] = acc[1][j] = ftb[base + j];
    for (int c = 0; c < 2; ++c)
        for (int t = 0; t < 6; ++t)
            for (u64 b = p.pc[c][t]; b; b &= b - 1) {
                int s = lsb(b);
                const short* wa = ftw + (size_t)feat_white(c, t, s) * H + base;
                const short* wb = ftw + (size_t)feat_black(c, t, s) * H + base;
                for (int j = 0; j < UNITS; ++j) {
                    acc[0][j] = (short)(acc[0][j] + wa[j]);
                    acc[1][j] = (short)(acc[1][j] + wb[j]);
                }
            }
}

// The side to move's eval in centipawns; every lane of the warp must call it, lane 0's result counts.
__device__ __forceinline__ int warp_eval(const short acc[2][UNITS], int stm, const short* outw, int outb, int base) {
    int part = 0;
    for (int half = 0; half < 2; ++half) {
        int persp = half == 0 ? stm : stm ^ 1; // the first half of the output weights reads the mover's view
        const short* w = outw + half * H + base;
        for (int j = 0; j < UNITS; ++j) {
            int v = min(max((int)acc[persp][j], 0), QA);
            int vw = (short)(v * w[j]);
            part += vw * v;
        }
    }
    long long sum = part;
    for (int off = 16; off; off >>= 1) sum += __shfl_down_sync(0xffffffffu, sum, off);
    sum = sum / QA + outb;
    return (int)(sum * EVAL_SCALE / (QA * QB));
}

// Evaluates every position from scratch: out[i] = side to move's eval of pos[i].
extern "C" __global__ void nnue_eval_kernel(const Pos* pos, int n, const short* ftw, const short* ftb,
                                            const short* outw, int outb, int* out) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (w >= n) return;
    short acc[2][UNITS];
    refresh(pos[w], ftw, ftb, lane * UNITS, acc);
    int e = warp_eval(acc, pos[w].stm, outw, outb, lane * UNITS);
    if (lane == 0) out[w] = e;
}

// Throughput of the per-node work in a search: iters times, move one piece (subtract its old
// feature, add the new one, both perspectives) and evaluate. out[i] keeps a checksum.
extern "C" __global__ void nnue_update_bench(const Pos* pos, int n, const short* ftw, const short* ftb,
                                             const short* outw, int outb, int iters, int* out) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (w >= n) return;
    int base = lane * UNITS;
    short acc[2][UNITS];
    refresh(pos[w], ftw, ftb, base, acc);
    int check = 0, s = 12, t = KNIGHT;
    for (int it = 0; it < iters; ++it) {
        int from = s, to = (s + 17) & 63;
        const short* sa = ftw + (size_t)feat_white(0, t, from) * H + base;
        const short* sb = ftw + (size_t)feat_black(0, t, from) * H + base;
        const short* aa = ftw + (size_t)feat_white(0, t, to) * H + base;
        const short* ab = ftw + (size_t)feat_black(0, t, to) * H + base;
        for (int j = 0; j < UNITS; ++j) {
            acc[0][j] = (short)(acc[0][j] - sa[j] + aa[j]);
            acc[1][j] = (short)(acc[1][j] - sb[j] + ab[j]);
        }
        check += warp_eval(acc, it & 1, outw, outb, base);
        s = to;
    }
    if (lane == 0) out[w] = check;
}
