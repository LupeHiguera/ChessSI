#pragma once

#include <cstdint>
#include <string>

namespace Datagen {

// Plays self-play games at a fixed node count and appends training positions to `path` in bullet's
// text format, one "<fen> | <score> | <result>" per line. Score is in centipawns and result is 1.0,
// 0.5 or 0.0, both from White's side. Each game opens with `randomPlies` random legal moves so games
// differ; `seed` makes a run reproducible.
void run(const std::string& path, int games, uint64_t seed, uint64_t nodes, int randomPlies);

} // namespace Datagen
