// NNUE evaluation on the GPU (issue #31, stage 1b), appended to chess.cu at compile time.
//
// One warp per position: each of the 32 lanes owns H / 32 hidden units of both perspectives, so a
// weight row (H int16) is one coalesced read by the warp, and the output sum is a warp shuffle.
// The arithmetic follows NNUE::evaluate in src/nnue.cpp step by step (int16 accumulators, SCReLU
// clamp to [0, QA], int16 v * w times v, truncating divisions), so the result is bit-exact.
// H is fixed at compile time (-DH=256). CSNN (net12, buckets <= 1) indexes feat * H. CSKB (net13,
// 8 or 16 king buckets) indexes (bucket * 768 + feat) * H. A king is not read when buckets <= 1.

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

// NNUE::king_bucket. Real square, a1 = 0. Files a-d mirror with ^ 7. Rank is not flipped.
__device__ __forceinline__ int king_bucket_sq(int king, int nBuckets) {
    if ((king & 7) < 4)
        king ^= 7;
    int file = (king & 7) - 4;
    int rank = king >> 3;
    if (nBuckets == 8)
        return file + 4 * (rank >= 4 ? 1 : 0);
    return file + 4 * (rank >> 1);
}
__device__ __forceinline__ const short* ft_row(const short* ftw, int buckets, int bucket, int feature, int base) {
    if (buckets <= 1)
        return ftw + (size_t)feature * H + base;
    return ftw + ((size_t)bucket * 768 + feature) * H + base;
}

// acc[0] White's perspective, acc[1] Black's, for this lane's units, built from scratch.
__device__ __forceinline__ void refresh(const Pos& p, const short* ftw, const short* ftb, int base, short acc[2][UNITS], int buckets) {
    int bw = 0, bb = 0;
    if (buckets > 1) {
        bw = king_bucket_sq(lsb(p.pc[0][KING]), buckets);
        bb = king_bucket_sq(lsb(p.pc[1][KING]), buckets);
    }
    for (int j = 0; j < UNITS; ++j) acc[0][j] = acc[1][j] = ftb[base + j];
    for (int c = 0; c < 2; ++c)
        for (int t = 0; t < 6; ++t)
            for (u64 b = p.pc[c][t]; b; b &= b - 1) {
                int s = lsb(b);
                const short* wa = ft_row(ftw, buckets, bw, feat_white(c, t, s), base);
                const short* wb = ft_row(ftw, buckets, bb, feat_black(c, t, s), base);
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
                                            const short* outw, int outb, int buckets, int* out) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (w >= n) return;
    short acc[2][UNITS];
    refresh(pos[w], ftw, ftb, lane * UNITS, acc, buckets);
    int e = warp_eval(acc, pos[w].stm, outw, outb, lane * UNITS);
    if (lane == 0) out[w] = e;
}

// Throughput of the per-node work in a search: iters times, move one piece (subtract its old
// feature, add the new one, both perspectives) and evaluate. out[i] keeps a checksum.
extern "C" __global__ void nnue_update_bench(const Pos* pos, int n, const short* ftw, const short* ftb,
                                             const short* outw, int outb, int buckets, int iters, int* out) {
    int w = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (w >= n) return;
    int base = lane * UNITS;
    short acc[2][UNITS];
    refresh(pos[w], ftw, ftb, base, acc, buckets);
    int bw = 0, bb = 0;
    if (buckets > 1) {
        bw = king_bucket_sq(lsb(pos[w].pc[0][KING]), buckets);
        bb = king_bucket_sq(lsb(pos[w].pc[1][KING]), buckets);
    }
    int check = 0, s = 12, t = KNIGHT;
    for (int it = 0; it < iters; ++it) {
        int from = s, to = (s + 17) & 63;
        const short* sa = ft_row(ftw, buckets, bw, feat_white(0, t, from), base);
        const short* sb = ft_row(ftw, buckets, bb, feat_black(0, t, from), base);
        const short* aa = ft_row(ftw, buckets, bw, feat_white(0, t, to), base);
        const short* ab = ft_row(ftw, buckets, bb, feat_black(0, t, to), base);
        for (int j = 0; j < UNITS; ++j) {
            acc[0][j] = (short)(acc[0][j] - sa[j] + aa[j]);
            acc[1][j] = (short)(acc[1][j] - sb[j] + ab[j]);
        }
        check += warp_eval(acc, it & 1, outw, outb, base);
        s = to;
    }
    if (lane == 0) out[w] = check;
}
