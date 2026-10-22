#pragma once

#include <string>

namespace UCI {

// Reads UCI commands from stdin until "quit". Command-line arguments run a
// single command instead, e.g. "chesssi bench" (needed by OpenBench).
int loop(int argc, char* argv[]);

// Thread-safe line output to stdout.
void send(const std::string& line);

} // namespace UCI
