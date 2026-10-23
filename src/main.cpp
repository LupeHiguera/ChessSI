#include "bitboard.h"
#include "eval.h"
#include "nnue.h"
#include "position.h"
#include "uci.h"

int main(int argc, char* argv[]) {
    Bitboards::init();
    Position::init();
    Eval::init();
    NNUE::load_embedded();
    return UCI::loop(argc, argv);
}
