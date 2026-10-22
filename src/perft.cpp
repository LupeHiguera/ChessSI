#include "perft.h"

#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>

#include "movegen.h"

uint64_t perft(Position& pos, int depth) {
    if (depth == 0)
        return 1;

    MoveList list;
    generate(pos, list, ALL_MOVES);
    uint64_t nodes = 0;
    for (Move m : list) {
        if (pos.do_move(m))
            nodes += depth == 1 ? 1 : perft(pos, depth - 1);
        pos.undo_move(m);
    }
    return nodes;
}

void perft_divide(Position& pos, int depth) {
    auto start = std::chrono::steady_clock::now();
    MoveList list;
    generate(pos, list, ALL_MOVES);
    uint64_t total = 0;
    for (Move m : list) {
        if (pos.do_move(m)) {
            uint64_t nodes = depth <= 1 ? 1 : perft(pos, depth - 1);
            std::cout << move_to_uci(m) << ": " << nodes << "\n";
            total += nodes;
        }
        pos.undo_move(m);
    }
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
    std::cout << "\nNodes searched: " << total << "\nTime: " << ms << " ms\nNPS: "
              << total * 1000 / (ms + 1) << std::endl;
}

bool perft_suite(const std::string& path, int maxDepth) {
    std::ifstream file(path);
    if (!file) {
        std::cout << "cannot open " << path << std::endl;
        return false;
    }

    int passed = 0, failed = 0;
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#')
            continue;

        std::istringstream is(line);
        std::string fen, field;
        std::getline(is, fen, ';');
        Position pos;
        if (!pos.set(fen)) {
            std::cout << "FAIL bad fen: " << fen << std::endl;
            ++failed;
            continue;
        }

        while (std::getline(is, field, ';')) {
            int depth;
            uint64_t expected;
            if (sscanf(field.c_str(), " D%d %llu", &depth, (unsigned long long*)&expected) != 2 || depth > maxDepth)
                continue;
            uint64_t nodes = perft(pos, depth);
            bool ok = nodes == expected;
            std::cout << (ok ? "ok   " : "FAIL ") << "D" << depth << " " << nodes;
            if (!ok)
                std::cout << " (expected " << expected << ")";
            std::cout << "  " << fen << std::endl;
            ok ? ++passed : ++failed;
        }
    }

    std::cout << "\n" << passed << " passed, " << failed << " failed" << std::endl;
    return failed == 0 && passed > 0;
}
