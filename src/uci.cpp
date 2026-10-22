#include "uci.h"

#include <chrono>
#include <iostream>
#include <mutex>
#include <sstream>
#include <thread>
#include <vector>

#include "eval.h"
#include "movegen.h"
#include "perft.h"
#include "search.h"
#include "tt.h"

namespace {

constexpr int DefaultHashMB = 16;
constexpr int BenchDepth = 7;

// Fixed positions for the bench command. Its node count is the engine's
// signature: a change that should not alter search must leave it unchanged.
const std::vector<std::string> BenchFens = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 1 5",
    "r2q1rk1/ppp2ppp/2n1bn2/2bpp3/4P3/2PP1N2/PP1NBPPP/R1BQ1RK1 w - - 0 8",
    "2r3k1/pp3ppp/4p3/3pP3/3P4/P4N2/1P3PPP/2R3K1 w - - 0 25",
    "8/5pk1/6p1/7p/7P/6P1/5PK1/8 w - - 0 40",
    "8/8/4k3/8/2p5/8/B1PK4/8 w - - 0 50",
    "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 30",
};

std::mutex outputMutex;
std::thread searchThread;

void wait_for_search() {
    if (searchThread.joinable())
        searchThread.join();
}

void bench(int depth) {
    uint64_t totalNodes = 0;
    auto start = std::chrono::steady_clock::now();

    for (const std::string& fen : BenchFens) {
        Position pos;
        pos.set(fen);
        Search::clear();
        SearchLimits limits;
        limits.depth = depth;
        totalNodes += Search::think(pos, limits, false).nodes;
    }

    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
    // OpenBench reads the last line: "<nodes> nodes <nps> nps".
    std::cout << "Time: " << ms << " ms\n"
              << totalNodes << " nodes " << totalNodes * 1000 / (ms + 1) << " nps" << std::endl;
}

void set_position(Position& pos, std::istringstream& is) {
    std::string token, fen;
    is >> token;
    if (token == "startpos") {
        fen = StartFEN;
        is >> token; // "moves", if present
    } else if (token == "fen") {
        while (is >> token && token != "moves")
            fen += token + " ";
    } else
        return;

    if (!pos.set(fen)) {
        UCI::send("info string invalid fen");
        pos.set(StartFEN);
        return;
    }

    while (is >> token) {
        Move m = parse_uci_move(pos, token);
        if (m == MOVE_NONE) {
            UCI::send("info string illegal move " + token);
            return;
        }
        pos.do_move(m);
    }
}

void go(Position pos, std::istringstream& is) {
    SearchLimits limits;
    std::string token;
    while (is >> token) {
        if (token == "wtime") is >> limits.time[WHITE];
        else if (token == "btime") is >> limits.time[BLACK];
        else if (token == "winc") is >> limits.inc[WHITE];
        else if (token == "binc") is >> limits.inc[BLACK];
        else if (token == "movestogo") is >> limits.movestogo;
        else if (token == "movetime") is >> limits.movetime;
        else if (token == "depth") is >> limits.depth;
        else if (token == "nodes") is >> limits.nodes;
        else if (token == "infinite") limits.infinite = true;
    }

    Search::stop = false;
    searchThread = std::thread([pos = std::move(pos), limits]() mutable {
        SearchResult result = Search::think(pos, limits, true);
        UCI::send("bestmove " + move_to_uci(result.best));
    });
}

void set_option(std::istringstream& is) {
    std::string token, name, value;
    is >> token; // "name"
    while (is >> token && token != "value")
        name += (name.empty() ? "" : " ") + token;
    is >> value;

    if (name == "Hash" && !value.empty())
        TT.resize(std::max(1, std::stoi(value)));
    // Threads is accepted for OpenBench but the search is single-threaded.
}

} // namespace

void UCI::send(const std::string& line) {
    std::lock_guard<std::mutex> lock(outputMutex);
    std::cout << line << std::endl;
}

int UCI::loop(int argc, char* argv[]) {
    TT.resize(DefaultHashMB);
    Position pos;
    pos.set(StartFEN);

    if (argc > 1) {
        std::string cmd = argv[1];
        if (cmd == "bench") {
            bench(argc > 2 ? std::atoi(argv[2]) : BenchDepth);
            return 0;
        }
        if (cmd == "perftsuite") {
            bool ok = perft_suite(argc > 2 ? argv[2] : "tests/perft.epd", argc > 3 ? std::atoi(argv[3]) : 5);
            return ok ? 0 : 1;
        }
    }

    std::string line, token;
    while (std::getline(std::cin, line)) {
        std::istringstream is(line);
        token.clear();
        is >> token;

        if (token == "quit")
            break;
        else if (token == "uci") {
            send("id name ChessSI");
            send("id author Lupe Higuera");
            send("option name Hash type spin default " + std::to_string(DefaultHashMB) + " min 1 max 65536");
            send("option name Threads type spin default 1 min 1 max 1");
            send("uciok");
        } else if (token == "isready")
            send("readyok");
        else if (token == "ucinewgame") {
            wait_for_search();
            Search::clear();
        } else if (token == "setoption") {
            wait_for_search();
            set_option(is);
        } else if (token == "position") {
            wait_for_search();
            set_position(pos, is);
        } else if (token == "go") {
            wait_for_search();
            go(pos, is);
        } else if (token == "stop") {
            Search::stop = true;
            wait_for_search();
        } else if (token == "perft") {
            int depth = 1;
            is >> depth;
            perft_divide(pos, depth);
        } else if (token == "bench") {
            int depth = BenchDepth;
            is >> depth;
            bench(depth);
        } else if (token == "d")
            std::cout << pos.pretty() << std::endl;
        else if (token == "eval")
            std::cout << "eval " << evaluate(pos) << " cp (side to move)" << std::endl;
        else if (!token.empty())
            send("info string unknown command " + token);
    }

    Search::stop = true;
    wait_for_search();
    return 0;
}
