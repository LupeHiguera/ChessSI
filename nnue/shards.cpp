// Converts datagen text into binary shards for `train.py --shards` (see nnue/shards.py).
//
//   g++ -O2 -o shards nnue/shards.cpp
//   shards <out dir> <name> <data.txt> [max lines (0 = all)] [positions per shard]
//
// Each line is parsed as nnue/train.py's parse_lines parses it: the same rules for malformed lines and
// the same position key (blake2b with an 8-byte digest of the first four FEN fields, top bit cleared).
// Boards are stored as encode() stores them: an occupancy mask (a1 = bit 0) and a 4-bit piece code
// (0-5 White, 6-11 Black) per occupied square in ascending square order. Only newline-terminated lines
// are read, like load_file; [max lines] reads only the first lines of a file, like `head -n`.
//
// A shard holds whole games: a game starts where the ply goes back or the result changes, as in
// per_file. So per_file, run on one shard at a time, gives the same targets as on the whole file.
// Files per shard <name>-NNNNN: .occ (u64), .pcs (u8 x 16), .white (i8), .scores (f32), .results (f32),
// .ply (i16), .keys (i64), all little-endian; and one line per shard in <name>.manifest:
// "<shard> <positions> <first line> <last line> <malformed lines>", line numbers counted from 1.
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

namespace {

// BLAKE2b (RFC 7693), unkeyed, 8-byte digest: Python's hashlib.blake2b(data, digest_size=8).
constexpr uint64_t IV[8] = {0x6a09e667f3bcc908ull, 0xbb67ae8584caa73bull, 0x3c6ef372fe94f82bull,
                            0xa54ff53a5f1d36f1ull, 0x510e527fade682d1ull, 0x9b05688c2b3e6c1full,
                            0x1f83d9abfb41bd6bull, 0x5be0cd19137e2179ull};
constexpr uint8_t SIGMA[12][16] = {
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}, {14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3},
    {11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4}, {7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8},
    {9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13}, {2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9},
    {12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11}, {13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10},
    {6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5}, {10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0},
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}, {14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3}};

inline uint64_t rotr(uint64_t x, int n) { return (x >> n) | (x << (64 - n)); }

void compress(uint64_t h[8], const uint8_t block[128], uint64_t t, bool last) {
    uint64_t m[16], v[16];
    for (int i = 0; i < 16; ++i)
        std::memcpy(&m[i], block + 8 * i, 8); // little-endian host (x86-64)
    for (int i = 0; i < 8; ++i)
        v[i] = h[i], v[i + 8] = IV[i];
    v[12] ^= t;
    if (last)
        v[14] = ~v[14];
    auto g = [&](int a, int b, int c, int d, uint64_t x, uint64_t y) {
        v[a] = v[a] + v[b] + x;
        v[d] = rotr(v[d] ^ v[a], 32);
        v[c] = v[c] + v[d];
        v[b] = rotr(v[b] ^ v[c], 24);
        v[a] = v[a] + v[b] + y;
        v[d] = rotr(v[d] ^ v[a], 16);
        v[c] = v[c] + v[d];
        v[b] = rotr(v[b] ^ v[c], 63);
    };
    for (int r = 0; r < 12; ++r) {
        const uint8_t* s = SIGMA[r];
        g(0, 4, 8, 12, m[s[0]], m[s[1]]);
        g(1, 5, 9, 13, m[s[2]], m[s[3]]);
        g(2, 6, 10, 14, m[s[4]], m[s[5]]);
        g(3, 7, 11, 15, m[s[6]], m[s[7]]);
        g(0, 5, 10, 15, m[s[8]], m[s[9]]);
        g(1, 6, 11, 12, m[s[10]], m[s[11]]);
        g(2, 7, 8, 13, m[s[12]], m[s[13]]);
        g(3, 4, 9, 14, m[s[14]], m[s[15]]);
    }
    for (int i = 0; i < 8; ++i)
        h[i] ^= v[i] ^ v[i + 8];
}

uint64_t blake2b64(const uint8_t* data, size_t len) {
    uint64_t h[8];
    std::memcpy(h, IV, sizeof h);
    h[0] ^= 0x01010000ull ^ 8; // no key, 8-byte digest
    uint8_t block[128];
    uint64_t t = 0;
    while (len > 128) {
        t += 128;
        compress(h, data, t, false);
        data += 128, len -= 128;
    }
    std::memset(block, 0, sizeof block);
    std::memcpy(block, data, len);
    compress(h, block, t + len, true);
    return h[0]; // the first 8 bytes of the digest, read little-endian
}

// Python's str.split() / str.strip() whitespace, for the ASCII the data holds.
inline bool space(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f'; }

std::string_view strip(std::string_view s) {
    while (!s.empty() && space(s.front()))
        s.remove_prefix(1);
    while (!s.empty() && space(s.back()))
        s.remove_suffix(1);
    return s;
}

// Python's int() on a stripped field, for what datagen writes: an optional sign and decimal digits.
bool parse_int(std::string_view s, long long& out) {
    size_t i = 0;
    bool neg = false;
    if (i < s.size() && (s[i] == '+' || s[i] == '-'))
        neg = s[i++] == '-';
    if (i == s.size())
        return false;
    long long v = 0;
    for (; i < s.size(); ++i) {
        if (s[i] < '0' || s[i] > '9' || v > 100000000000000ll)
            return false;
        v = v * 10 + (s[i] - '0');
    }
    out = neg ? -v : v;
    return true;
}

// Python's float() for what datagen writes ("0", "0.5", "1"): the whole field must be a number.
bool parse_float(std::string_view s, double& out) {
    if (s.empty() || s.size() > 63)
        return false;
    char buf[64];
    std::memcpy(buf, s.data(), s.size());
    buf[s.size()] = 0;
    char* end = nullptr;
    errno = 0;
    out = std::strtod(buf, &end);
    return end == buf + s.size() && errno == 0;
}

struct Row {
    uint64_t occ;
    uint8_t pcs[16];
    int8_t white;
    float score, result;
    int16_t ply;
    int64_t key;
};

// parse_lines for one line: false where parse_lines counts the line as malformed.
bool parse(std::string_view line, Row& r) {
    size_t p1 = line.find('|');
    if (p1 == std::string_view::npos)
        return false;
    size_t p2 = line.find('|', p1 + 1);
    if (p2 == std::string_view::npos)
        return false;
    size_t p3 = line.find('|', p2 + 1);
    std::string_view fen = strip(line.substr(0, p1));
    std::string_view score = strip(line.substr(p1 + 1, p2 - p1 - 1));
    std::string_view result = strip(p3 == std::string_view::npos ? line.substr(p2 + 1) : line.substr(p2 + 1, p3 - p2 - 1));

    std::string_view parts[8];
    int n = 0;
    for (size_t i = 0; i < fen.size() && n < 8;) {
        while (i < fen.size() && space(fen[i]))
            ++i;
        size_t j = i;
        while (j < fen.size() && !space(fen[j]))
            ++j;
        if (j > i)
            parts[n++] = fen.substr(i, j - i);
        i = j;
    }
    if (n == 0)
        return false;

    // white_features(parts[0]); a character that is no piece letter is a KeyError there.
    int code[64];
    std::fill(code, code + 64, -1);
    int rank = 7, file = 0, pieces = 0;
    for (char ch : parts[0]) {
        if (ch == '/') {
            --rank;
            file = 0;
        } else if (ch >= '0' && ch <= '9') {
            file += ch - '0';
        } else {
            int pt;
            switch (ch & ~0x20) { // upper case
            case 'P': pt = 0; break;
            case 'N': pt = 1; break;
            case 'B': pt = 2; break;
            case 'R': pt = 3; break;
            case 'Q': pt = 4; break;
            case 'K': pt = 5; break;
            default: return false;
            }
            int sq = rank * 8 + file;
            if (sq < 0 || sq > 63 || ++pieces > 32)
                return false; // parse_lines would fail later on such a board
            code[sq] = (ch >= 'a' ? 6 : 0) + pt;
            ++file;
        }
    }
    long long cp, fullmove;
    double res;
    if (!parse_int(score, cp) || !parse_float(result, res) || n < 6 || !parse_int(parts[5], fullmove))
        return false;

    std::string key(parts[0]);
    for (int i = 1; i < 4; ++i)
        key.append(1, ' ').append(parts[i]);
    r.key = int64_t(blake2b64(reinterpret_cast<const uint8_t*>(key.data()), key.size()) & 0x7FFFFFFFFFFFFFFFull);

    r.occ = 0;
    std::memset(r.pcs, 0, sizeof r.pcs);
    int k = 0;
    for (int sq = 0; sq < 64; ++sq)
        if (code[sq] >= 0) {
            r.occ |= 1ull << sq;
            r.pcs[k / 2] |= uint8_t(code[sq] << (4 * (k % 2)));
            ++k;
        }
    r.white = parts[1] == "w";
    r.score = float(cp);
    r.result = float(res);
    long long p = 2 * (fullmove - 1) + (parts[1] == "b");
    r.ply = int16_t(std::min(p, 4095ll));
    return true;
}

struct Writer {
    std::string dir, name;
    std::vector<Row> rows;
    int index = 0;
    long long firstLine = 0, lastLine = 0, bad = 0;
    FILE* manifest = nullptr;

    template <typename F>
    void column(const std::string& stem, const char* ext, F get, size_t bytes) {
        std::string path = stem + ext;
        FILE* f = std::fopen(path.c_str(), "wb");
        if (!f) {
            std::perror(path.c_str());
            std::exit(1);
        }
        std::vector<uint8_t> buf(rows.size() * bytes);
        for (size_t i = 0; i < rows.size(); ++i)
            get(rows[i], buf.data() + i * bytes);
        if (std::fwrite(buf.data(), 1, buf.size(), f) != buf.size() || std::fclose(f) != 0) {
            std::perror(path.c_str());
            std::exit(1);
        }
    }

    void flush() {
        if (rows.empty())
            return;
        char suffix[16];
        std::snprintf(suffix, sizeof suffix, "-%05d", index++);
        std::string shard = name + suffix, stem = dir + "/" + shard;
        column(stem, ".occ", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.occ, 8); }, 8);
        column(stem, ".pcs", [](const Row& r, uint8_t* o) { std::memcpy(o, r.pcs, 16); }, 16);
        column(stem, ".white", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.white, 1); }, 1);
        column(stem, ".scores", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.score, 4); }, 4);
        column(stem, ".results", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.result, 4); }, 4);
        column(stem, ".ply", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.ply, 2); }, 2);
        column(stem, ".keys", [](const Row& r, uint8_t* o) { std::memcpy(o, &r.key, 8); }, 8);
        std::fprintf(manifest, "%s %zu %lld %lld %lld\n", shard.c_str(), rows.size(), firstLine, lastLine, bad);
        std::fflush(manifest);
        rows.clear();
        bad = 0;
    }
};

} // namespace

int main(int argc, char** argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: shards <out dir> <name> <data.txt> [max lines] [positions per shard]\n");
        return 2;
    }
    Writer w;
    w.dir = argv[1];
    w.name = argv[2];
    long long maxLines = argc > 4 ? std::atoll(argv[4]) : 0;
    size_t perShard = argc > 5 ? size_t(std::atoll(argv[5])) : 8'000'000;
    FILE* in = std::fopen(argv[3], "rb");
    std::string manifestPath = w.dir + "/" + w.name + ".manifest";
    w.manifest = std::fopen(manifestPath.c_str(), "w");
    if (!in || !w.manifest) {
        std::perror(!in ? argv[3] : manifestPath.c_str());
        return 1;
    }

    std::vector<char> buf(64 << 20);
    size_t have = 0;
    long long lineNo = 0, totalBad = 0, total = 0;
    int16_t prevPly = 0;
    float prevResult = 0;
    bool any = false, done = false;
    Row r;
    while (!done) {
        size_t got = std::fread(buf.data() + have, 1, buf.size() - have, in);
        if (got == 0)
            break; // a last line without a newline is left out, as in load_file
        have += got;
        size_t start = 0;
        for (;;) {
            const char* nl = static_cast<const char*>(std::memchr(buf.data() + start, '\n', have - start));
            if (!nl)
                break;
            size_t end = size_t(nl - buf.data());
            ++lineNo;
            if (parse(std::string_view(buf.data() + start, end - start), r)) {
                // per_file: a new game starts where the ply goes back or the result changes.
                bool newGame = !any || r.ply <= prevPly || r.result != prevResult;
                if (newGame && w.rows.size() >= perShard)
                    w.flush();
                if (w.rows.empty())
                    w.firstLine = lineNo;
                w.rows.push_back(r);
                w.lastLine = lineNo;
                prevPly = r.ply, prevResult = r.result, any = true;
                ++total;
            } else {
                ++w.bad, ++totalBad;
            }
            start = end + 1;
            if (maxLines && lineNo >= maxLines) {
                done = true;
                break;
            }
        }
        std::memmove(buf.data(), buf.data() + start, have - start);
        have -= start;
        if (have == buf.size()) {
            std::fprintf(stderr, "line %lld is longer than the buffer\n", lineNo + 1);
            return 1;
        }
    }
    w.flush();
    std::fclose(w.manifest);
    std::fprintf(stderr, "%s: %lld lines, %lld positions in %d shards, %lld malformed\n", argv[3], lineNo, total,
                 w.index, totalBad);
    return 0;
}
