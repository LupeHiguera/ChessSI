
    Position auditRoot;
    bool auditShadow = false, auditDisableRfp = false;
    bool auditSampling = std::getenv("CHESSSI_RFP_SHADOW_CONTEXT") != nullptr;
    int incomingR[MAX_PLY + 1] = {}, callKind[MAX_PLY + 1] = {};
    int auditEntryPly = -1, auditNmpAtEntry = 0;
    uint64_t auditCutoffs = 0, auditReduced = 0, auditNull = 0, auditBoth = 0;
    uint64_t auditGateHits = 0, auditSamples = 0, auditShadowNodes = 0, auditControlNodes = 0;

    static void require(bool ok, const char* why) {
        if (!ok) throw std::runtime_error(why);
    }
    static uint64_t audit_mix(uint64_t x) {
        x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
        x ^= x >> 27; x *= 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }
    static bool limits_equal(const SearchLimits& a, const SearchLimits& b) {
        return a.depth == b.depth && a.nodes == b.nodes && a.movetime == b.movetime
            && a.time[0] == b.time[0] && a.time[1] == b.time[1]
            && a.inc[0] == b.inc[0] && a.inc[1] == b.inc[1]
            && a.movestogo == b.movestogo && a.infinite == b.infinite;
    }
    void copy_context(Searcher& dst) const {
        dst.limits = limits; dst.start = start;
        dst.softLimit = softLimit; dst.hardLimit = hardLimit;
        dst.nodes = nodes; dst.stopped = stopped;
        dst.auditRoot = auditRoot;
        dst.auditShadow = auditShadow; dst.auditDisableRfp = auditDisableRfp;
        dst.auditSampling = auditSampling; dst.auditEntryPly = auditEntryPly;
        for (int row = 0; row <= MAX_PLY; ++row) {
            dst.killers[row][0] = killers[row][0]; dst.killers[row][1] = killers[row][1];
        }
        std::copy(std::begin(moveStack), std::end(moveStack), std::begin(dst.moveStack));
        std::copy(std::begin(incomingR), std::end(incomingR), std::begin(dst.incomingR));
        std::copy(std::begin(callKind), std::end(callKind), std::begin(dst.callKind));
        for (int row = 0; row <= MAX_PLY; ++row) {
            require(pvLength[row] >= 0 && pvLength[row] <= MAX_PLY + 1, "invalid PV length");
            dst.pvLength[row] = pvLength[row];
            std::copy(pv[row], pv[row] + pvLength[row], dst.pv[row]);
        }
    }
    bool context_equal(const Searcher& rhs) const {
        if (!pos.audit_equal(rhs.pos) || !auditRoot.audit_equal(rhs.auditRoot)
            || !limits_equal(limits, rhs.limits) || start != rhs.start
            || softLimit != rhs.softLimit || hardLimit != rhs.hardLimit
            || nodes != rhs.nodes || stopped != rhs.stopped
            || auditShadow != rhs.auditShadow || auditDisableRfp != rhs.auditDisableRfp
            || auditSampling != rhs.auditSampling || auditEntryPly != rhs.auditEntryPly) return false;
        for (int row = 0; row <= MAX_PLY; ++row) {
            if (killers[row][0] != rhs.killers[row][0] || killers[row][1] != rhs.killers[row][1]
                || moveStack[row] != rhs.moveStack[row] || incomingR[row] != rhs.incomingR[row]
                || callKind[row] != rhs.callKind[row] || pvLength[row] != rhs.pvLength[row])
                return false;
            for (int j = 0; j < pvLength[row]; ++j)
                if (pv[row][j] != rhs.pv[row][j]) return false;
        }
        return true;
    }
    bool replay_equal(int ply) const {
        Position replay = auditRoot;
        for (int i = 0; i < ply; ++i) {
            if (moveStack[i] == MOVE_NONE) {
                if (replay.in_check()) return false;
                replay.do_null_move();
            } else {
                MoveList list; generate(replay, list, ALL_MOVES);
                bool generated = false;
                for (Move m : list) generated |= m == moveStack[i];
                if (!generated || !replay.do_move(moveStack[i])) return false;
            }
        }
        return replay.audit_equal(pos);
    }
    void audit_cutoff(int alpha, int beta, int depth, int ply, int staticEval, bool legal) {
        if (auditShadow) return;
        int nulls = 0, killerSlots = 0;
        for (int i = 0; i < ply; ++i) nulls += moveStack[i] == MOVE_NONE;
        for (const auto& row : killers) for (Move m : row) killerSlots += m != MOVE_NONE;
        ++auditCutoffs;
        auditReduced += incomingR[ply] > 0;
        auditNull += nulls > 0;
        auditBoth += incomingR[ply] > 0 && nulls > 0;
        if (!auditSampling || !legal) return;
        const uint64_t sampleKey = audit_mix(pos.key() ^ (uint64_t(depth) << 32)
            ^ (uint64_t(beta + VALUE_INF) << 16) ^ nodes ^ 0x6a09e667f3bcc909ULL);
        if ((sampleKey & 255) != 0) return;
        ++auditGateHits;
        if (auditSamples >= 8) return;
        ++auditSamples;
        require(!Search::stop, "external stop before probe");
        require(replay_equal(ply), "native typed path mismatch");
        const TranspositionTable originalTT = TT;
        Position parentPos = pos;
        Searcher parent(parentPos, limits); copy_context(parent);
        const uint64_t offset = nodes - 1;
        Position disabledPos = pos, enabledPos = pos;
        Searcher disabled(disabledPos, limits), enabled(enabledPos, limits);
        copy_context(disabled); copy_context(enabled);
        require(context_equal(disabled) && context_equal(enabled), "copied context mismatch");
        auto configure = [&](Searcher& target, bool disable) {
            target.auditShadow = true; target.auditSampling = false; target.auditDisableRfp = disable;
            target.nodes = offset; target.limits = SearchLimits{};
            target.limits.nodes = offset + 131072;
            target.softLimit = target.hardLimit = 0;
        };
        configure(disabled, true); configure(enabled, false);
        const int score = disabled.search(alpha, beta, depth, ply);
        const bool disabledRestored = disabledPos.audit_equal(pos);
        TT = originalTT;
        require(TT.audit_equal(originalTT), "TT restore before control");
        const int controlScore = enabled.search(alpha, beta, depth, ply);
        const bool enabledRestored = enabledPos.audit_equal(pos);
        TT = originalTT;
        require(TT.audit_equal(originalTT), "TT restore before parent");
        require(context_equal(parent), "parent fields changed");
        require(disabledRestored && enabledRestored, "probe Position history changed");
        require(!Search::stop, "external stop during probe");
        const uint64_t delta = disabled.nodes - offset, controlDelta = enabled.nodes - offset;
        require(!enabled.stopped && controlDelta == 1 && controlScore == staticEval, "enabled probe mismatch");
        auditShadowNodes += delta; auditControlNodes += controlDelta;
        std::cerr << "RFPSAMPLE {\"depth\":" << depth << ",\"ply\":" << ply
            << ",\"alpha\":" << alpha << ",\"beta\":" << beta << ",\"static_eval\":" << staticEval
            << ",\"shadow_score\":" << score << ",\"shadow_nodes\":" << delta
            << ",\"shadow_stopped\":" << int(disabled.stopped)
            << ",\"control_score\":" << controlScore << ",\"control_nodes\":" << controlDelta
            << ",\"control_stopped\":" << int(enabled.stopped)
            << ",\"restored\":1,\"incoming_reduction\":" << incomingR[ply]
            << ",\"call_kind\":" << callKind[ply] << ",\"null_ancestors\":" << nulls
            << ",\"killer_slots\":" << killerSlots << ",\"parent_nodes\":" << nodes
            << ",\"polling_offset\":" << offset << ",\"sample_key\":\"" << sampleKey
            << "\",\"fen\":\"" << pos.fen() << "\",\"path\":[";
        for (int i = 0; i < ply; ++i) {
            if (i) std::cerr << ',';
            if (moveStack[i] == MOVE_NONE) std::cerr << "null";
            else std::cerr << '"' << move_to_uci(moveStack[i]) << '"';
        }
        std::cerr << "]}\n";
    }
