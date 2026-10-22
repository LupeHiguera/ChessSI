#pragma once

#include "position.h"

namespace Eval {
void init();
}

// Static evaluation in centipawns from the side to move's point of view.
int evaluate(const Position& pos);
