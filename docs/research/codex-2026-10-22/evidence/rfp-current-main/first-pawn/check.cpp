#include "src/search.cpp"
#include <iostream>
void UCI::send(const std::string&) {}
Move original_first(Position& p) {
    MoveList list; generate(p,list,ALL_MOVES);
    for(Move m:list) { const bool legal=p.do_move(m);p.undo_move(m);if(legal)return m; }
    return MOVE_NONE;
}
int main() {
    Bitboards::init();Position::init();Eval::init();TT.resize(16);
    std::string fen;int id=0;
    while(std::getline(std::cin,fen)) {
        Position p;if(!p.set(fen))return 2;
        const uint64_t key=p.key();const bool draw=p.is_draw();const std::string original=p.fen();
        SearchLimits limits;Searcher s(p,limits);
        const Move a=s.first_legal_move(),b=original_first(p);
        if(a!=b || p.fen()!=original || p.key()!=key || p.is_draw()!=draw)return 3;
        if(a!=MOVE_NONE) {if(!p.do_move(a))return 4;p.undo_move(a);}
        if(p.fen()!=original || p.key()!=key || p.is_draw()!=draw)return 5;
        std::cout << id++ << ' ' << (a==MOVE_NONE?"0000":move_to_uci(a)) << '\n';
    }
}
