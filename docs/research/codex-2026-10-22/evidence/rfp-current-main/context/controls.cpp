
#include "src/search.cpp"
void UCI::send(const std::string&) {}
Move play(Position& p, const char* text) {
    MoveList list; generate(p, list, ALL_MOVES);
    for (Move m : list) if (move_to_uci(m) == text) {
        Searcher::require(p.do_move(m), "illegal control move"); return m;
    }
    throw std::runtime_error("control move absent");
}
int main() {
    Bitboards::init(); Position::init(); Eval::init(); TT.resize(16);
    Search::stop = false;
    const char* fens[] = {"8/4p2k/4P3/p3P3/P3P3/P1b5/1Rb5/K7 b - - 0 1",
                         "k7/1rB5/p1B5/p3p3/P3p3/4p3/4P2K/8 w - - 0 1"};
    const char* moves[] = {"h7h8","h2h1"};
    for (int i=0; i<2; ++i) {
        Position p; Searcher::require(p.set(fens[i]), "bad fixture");
        const Position root = p; Move previous = play(p, moves[i]);
        TT.clear(); SearchLimits lim; Searcher s(p, lim);
        s.auditRoot = root; s.auditSampling = true; s.moveStack[0] = previous;
        uint64_t event = 1;
        while ((Searcher::audit_mix(p.key() ^ (uint64_t(1)<<32)
             ^ (uint64_t(1+VALUE_INF)<<16) ^ event ^ 0x6a09e667f3bcc909ULL) & 255) != 0) ++event;
        s.nodes = event-1;
        Searcher::require(s.search(0,1,1,1)==182 && s.auditSamples==1 && !s.stopped, "contradiction fixture failed");
        std::cout << "CONTROL contradiction " << i << " passed\n";
    }
    {
        Position p; Searcher::require(p.set("5k2/8/2K5/8/8/8/8/R7 b - - 0 1"), "bad NMP fixture");
        Position root = p; Move previous = play(p, "f8e8");
        SearchLimits lim; Searcher source(p, lim); source.auditRoot = root;
        source.moveStack[0] = previous; source.auditDisableRfp = true;
        source.auditSampling = false; source.auditEntryPly = 1;
        source.killers[1][0] = make_move(0, 8);
        source.killers[2][1] = make_move(0, 1);
        source.pvLength[0] = 1; source.pv[0][0] = previous;
        source.incomingR[1] = 1; source.callKind[1] = 3;
        Position a = p, b = p; Searcher good(a,lim), reset(b,lim);
        source.copy_context(good); source.copy_context(reset);
        Searcher::require(source.context_equal(good) && source.replay_equal(1), "copy/replay NMP fixture");
        reset.killers[1][0] = MOVE_NONE;
        Searcher::require(!source.context_equal(reset), "reset killer was undetected");
        source.copy_context(reset); reset.moveStack[0] = MOVE_NONE;
        Searcher::require(!source.context_equal(reset), "reset predecessor was undetected");
        good.auditDisableRfp = reset.auditDisableRfp = true;
        good.auditSampling = reset.auditSampling = false;
        good.auditEntryPly = reset.auditEntryPly = 1;
        TT.clear(); const auto original = TT;
        const int sourceScore = source.search(0,1,3,1); TT = original;
        const int goodScore = good.search(0,1,3,1); TT = original;
        const int resetScore = reset.search(0,1,3,1); TT = original;
        Searcher::require(good.auditNmpAtEntry == 1 && reset.auditNmpAtEntry == 0, "NMP predecessor control failed");
        Searcher::require(sourceScore == goodScore && source.nodes == good.nodes
            && source.auditNmpAtEntry == good.auditNmpAtEntry, "source-clone NMP execution mismatch");
        std::cout << "CONTROL independent source versus clone NMP execution passed score " << sourceScore
                  << " nodes " << source.nodes << " entry_NMP " << source.auditNmpAtEntry << "\n";
        Searcher::require(a.audit_equal(p) && b.audit_equal(p), "NMP Position not restored");
        std::cout << "CONTROL NMP predecessor passed good_score " << goodScore
                  << " reset_score " << resetScore << " good_nodes " << good.nodes
                  << " reset_nodes " << reset.nodes << "\n";
        std::cout << "CONTROL nonzero killers and active PV copied passed\n";
    }
    const char* nullFens[] = {"5k2/8/2K5/8/8/8/8/R7 w - - 0 1",
                             "r7/8/8/8/8/2k5/8/5K2 b - - 0 1"};
    const char* afterNull[] = {"f8e8", "f1e1"};
    for(int i=0; i<2; ++i) {
        Position p; Searcher::require(p.set(nullFens[i]), "bad null fixture"); Position root = p;
        p.do_null_move(); Move m = play(p, afterNull[i]);
        SearchLimits lim; Searcher s(p,lim); s.auditRoot=root;
        s.moveStack[0]=MOVE_NONE; s.moveStack[1]=m;
        Searcher::require(s.replay_equal(2), "null typed path did not replay");
        Position copied=p; Searcher dst(copied,lim); s.copy_context(dst);
        Searcher::require(s.context_equal(dst), "null context copy failed");
        p.undo_move(m); p.undo_null_move();
        Searcher::require(p.audit_equal(root), "null path undo history failed");
        std::cout << "CONTROL null replay " << i << " passed\n";
    }
    Searcher::require(!Search::stop, "global stop changed");
    std::cout << "ALL CONTROLS PASSED\n";
}
