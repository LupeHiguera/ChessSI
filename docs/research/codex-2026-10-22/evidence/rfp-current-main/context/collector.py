#!/usr/bin/env python3
"""One preregistered local RFP context audit. prepare does not query corpus."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import time
import types
from dataclasses import replace as dc_replace

if sys.flags.optimize:
    raise RuntimeError('Python optimization disables required audit checks; run without -O/PYTHONOPTIMIZE')


ROOT=Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra')
OUT=ROOT/'engines/rfp-current-main-validation/shadow-context-01'
PLAN=json.loads((OUT/'plan.json').read_text(encoding='utf-8-sig'))
CORRECTION=json.loads((OUT/'preflight-correction.json').read_text())
assert PLAN['roots_sha256']==CORRECTION['mistyped_roots_sha256']
PLAN['roots_sha256']=CORRECTION['verified_roots_sha256']
DEADLINE=dt.datetime.fromisoformat(PLAN['deadline_utc'])
LAUNCH=ROOT/'engines/rfp-current-main-validation/launch-plan.json'
LAUNCH_SHA='21c73ab2b9de0088cff27a9c698ff3b0221bb570589ff4babb531af4612b6937'
UCI_HELPER=ROOT/'scripts/research/label_budget.py'
UCI_HELPER_SHA='12bd0bc6ac1cc3ba584f71236ad1671842db34625d563a7206e5f8a6a05ba90b'
def now(): return dt.datetime.now(dt.timezone.utc)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj): p.write_text(json.dumps(obj,indent=2)+'\n')
def time_left():
    n=(DEADLINE-now()).total_seconds()
    if n<=0: raise TimeoutError('Predeclared deadline reached')
    return n
def frozen():
    assert sha(LAUNCH)==LAUNCH_SHA
    manifest=json.loads(LAUNCH.read_bytes())['source_files_sha256']
    assert len(manifest)==21
    for path,expected in manifest.items(): assert sha(ROOT/path)==expected,path
    assert sha(UCI_HELPER)==UCI_HELPER_SHA
    assert sha(ROOT/'src/search.cpp')==PLAN['source_sha256']
    assert sha(ROOT/'engines/new')==PLAN['binary_sha256']
    assert sha(ROOT/PLAN['roots'])==PLAN['roots_sha256']
def replace(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new,1)
def run(args,label,folder,maximum=60,env=None):
    timeout=min(maximum,time_left())
    write(folder/(label+'.command.json'),{'args':list(map(str,args)),'utc':now().isoformat(),'timeout':timeout,'affinity':sorted(os.sched_getaffinity(0))})
    with (folder/(label+'.stdout')).open('w') as stdout, (folder/(label+'.stderr')).open('w') as stderr:
        r=subprocess.run(list(map(str,args)),stdout=stdout,stderr=stderr,timeout=timeout,env=env)
    if r.returncode: raise RuntimeError(f'{label} exit {r.returncode}')
    return (folder/(label+'.stdout')).read_text()
def prepare():
    frozen()
    numbers=[int(p.name.split('-')[-1]) for p in OUT.glob('attempt-*') if p.is_dir()]
    a=OUT/f'attempt-{max(numbers,default=0)+1:02}'
    a.mkdir()
    shutil.copy2(__file__,a/'collector.py')
    shutil.copy2(OUT/'plan.json',a/'plan.json')
    shutil.copy2(OUT/'preflight-correction.json',a/'preflight-correction.json')
    shutil.copy2(LAUNCH,a/'launch-plan.json')
    shutil.copy2(UCI_HELPER,a/'label_budget.py')
    shutil.copy2(OUT/'audit_members.inc',a/'audit_members.inc')
    shutil.copy2(OUT/'controls.cpp',a/'controls.cpp')
    try:
        for d in ['src','reference']:
            shutil.copytree(ROOT/'src',a/d)
            u=(a/d/'uci.cpp').read_text()
            u=replace(u,'        UCI::send("bestmove " + move_to_uci(result.best));',
                '        UCI::send("info string AUDITFINAL " + std::to_string(result.nodes));\n        UCI::send("bestmove " + move_to_uci(result.best));')
            (a/d/'uci.cpp').write_text(u)
        p=(a/'src/position.h').read_text()
        p=replace(p,'#include <string>','#include <string>\n#include <algorithm>\n#include <iterator>')
        p=replace(p,'struct StateInfo {','struct StateInfo {\n    bool operator==(const StateInfo&) const = default;')
        p=replace(p,'    static void init();',"""    static void init();
    bool audit_equal(const Position& rhs) const {
        return std::equal(std::begin(byType),std::end(byType),std::begin(rhs.byType))
            && std::equal(std::begin(byColor),std::end(byColor),std::begin(rhs.byColor))
            && std::equal(std::begin(board),std::end(board),std::begin(rhs.board))
            && stm==rhs.stm && fullmove==rhs.fullmove && states==rhs.states;
    }""")
        (a/'src/position.h').write_text(p)
        t=(a/'src/tt.h').read_text()
        t=replace(t,'struct TTEntry {','struct TTEntry {\n    bool operator==(const TTEntry&) const = default;')
        t=replace(t,'    void resize(size_t megabytes);','    bool audit_equal(const TranspositionTable& rhs) const { return table == rhs.table; }\n    void resize(size_t megabytes);')
        (a/'src/tt.h').write_text(t)
        s=(a/'src/search.cpp').read_text()
        s=replace(s,'#include <thread>','#include <thread>\n#include <cstdlib>\n#include <iostream>\n#include <stdexcept>')
        s=replace(s,'    Move pv[MAX_PLY + 1][MAX_PLY + 1];','    Move pv[MAX_PLY + 1][MAX_PLY + 1] = {};')
        s=replace(s,'    int pvLength[MAX_PLY + 1];','    int pvLength[MAX_PLY + 1] = {};')
        s=replace(s,'    Searcher(Position& p, const SearchLimits& l) : pos(p), limits(l) {}',
            '    #include "../audit_members.inc"\n    Searcher(Position& p, const SearchLimits& l) : pos(p), limits(l), auditRoot(p) {}')
        s=replace(s,'        if (!root && !pvNode && !inCheck && depth <= 3',
            '        if (!auditDisableRfp && !root && !pvNode && !inCheck && depth <= 3')
        s=replace(s,'''            if (std::abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 150 * depth >= beta)
                // A static advantage cannot override stalemate.
                return first_legal_move() == MOVE_NONE ? 0 : staticEval;''',
        '''            if (std::abs(staticEval) < VALUE_MATE_IN_MAX_PLY && staticEval - 150 * depth >= beta) {
                const bool legal = first_legal_move() != MOVE_NONE;
                audit_cutoff(alpha, beta, depth, ply, staticEval, legal);
                return legal ? staticEval : 0;
            }''')
        s=replace(s,'            int R = 3 + depth / 6;',
            '            auditNmpAtEntry += ply == auditEntryPly;\n            incomingR[ply + 1] = 0; callKind[ply + 1] = 1;\n            int R = 3 + depth / 6;')
        s=replace(s,'''            if (legalMoves == 1)
                score = -search(-beta, -alpha, depth - 1, ply + 1);
            else {''','''            if (legalMoves == 1) {
                incomingR[ply + 1] = 0; callKind[ply + 1] = 2;
                score = -search(-beta, -alpha, depth - 1, ply + 1);
            } else {''')
        s=replace(s,'''                score = -search(-alpha - 1, -alpha, depth - 1 - r, ply + 1);
                if (score > alpha && r > 0)
                    score = -search(-alpha - 1, -alpha, depth - 1, ply + 1);
                if (score > alpha && score < beta)
                    score = -search(-beta, -alpha, depth - 1, ply + 1);''',
        '''                incomingR[ply + 1] = r; callKind[ply + 1] = r > 0 ? 3 : 4;
                score = -search(-alpha - 1, -alpha, depth - 1 - r, ply + 1);
                if (score > alpha && r > 0) {
                    incomingR[ply + 1] = 0; callKind[ply + 1] = 5;
                    score = -search(-alpha - 1, -alpha, depth - 1, ply + 1);
                }
                if (score > alpha && score < beta) {
                    incomingR[ply + 1] = 0; callKind[ply + 1] = 6;
                    score = -search(-beta, -alpha, depth - 1, ply + 1);
                }''')
        s=replace(s,'    result.nodes = s.nodes;',r'''    result.nodes = s.nodes;
    if (s.auditSampling)
        std::cerr << "RFPTOTAL {\"nodes\":" << s.nodes << ",\"cutoffs\":" << s.auditCutoffs
            << ",\"reduced\":" << s.auditReduced << ",\"null_descendant\":" << s.auditNull
            << ",\"both\":" << s.auditBoth << ",\"gate_hits\":" << s.auditGateHits
            << ",\"samples\":" << s.auditSamples << ",\"shadow_nodes\":" << s.auditShadowNodes
            << ",\"control_nodes\":" << s.auditControlNodes << "}\n";''')
        (a/'src/search.cpp').write_text(s)
        compiler=['taskset','-c','19','g++','-std=c++20','-O3','-march=native','-DNDEBUG','-Wall','-Wextra','-pthread']
        for d,name in [('reference','chesssi-reference'),('src','chesssi-observer')]:
            run(compiler+list(sorted((a/d).glob('*.cpp')))+['-o',a/name],name+'-build',a,120)
            bench=run([a/name,'bench'],name+'-bench',a)
            assert bench.splitlines()[-1].startswith('609035 nodes '),bench.splitlines()[-1:]
        dependencies=[a/'src'/name for name in ['bitboard.cpp','position.cpp','movegen.cpp','eval.cpp','tt.cpp']]
        run(compiler+[a/'controls.cpp']+dependencies+['-o',a/'controls'],'controls-build',a,120)
        text=run([a/'controls'],'controls',a)
        samples=[json.loads(line[len('RFPSAMPLE '):]) for line in (a/'controls.stderr').read_text().splitlines() if line.startswith('RFPSAMPLE ')]
        assert len(samples)==2 and all(not x['shadow_stopped'] and x['shadow_score']<x['beta'] for x in samples)
        assert 'ALL CONTROLS PASSED' in text
        frozen()
        files={str(p.relative_to(a)):sha(p) for p in sorted(a.rglob('*')) if p.is_file() and p.suffix in ('.cpp','.h','.inc','.py')}
        result={'status':'ready_for_review_not_corpus','utc':now().isoformat(),'attempt':str(a),'bench':609035,
            'controls':text.splitlines(),'control_samples':samples,'files':files,
            'binaries':{n:sha(a/n) for n in ['chesssi-reference','chesssi-observer','controls']},
            'collector_sha256':sha(Path(__file__)),'plan_sha256':sha(OUT/'plan.json'),'correction_sha256':sha(OUT/'preflight-correction.json'),
            'live_hashes_unchanged':True,'affinity':[19],
            'launch_plan_sha256':LAUNCH_SHA,'uci_helper_sha256':UCI_HELPER_SHA}
        write(a/'validation.json',result)
        print(json.dumps(result,indent=2),flush=True)
    except BaseException as exc:
        write(a/'failure.json',{'utc':now().isoformat(),'error':repr(exc),'traceback':traceback.format_exc()})
        raise

def corpus(attempt):
    frozen(); time_left()
    a=OUT/attempt
    v=json.loads((a/'validation.json').read_text())
    assert v['status']=='ready_for_review_not_corpus'
    assert v['plan_sha256']==sha(OUT/'plan.json') and v['collector_sha256']==sha(Path(__file__))
    assert v['correction_sha256']==sha(OUT/'preflight-correction.json')
    for path,h in v['files'].items(): assert sha(a/path)==h,path
    for path,h in v['binaries'].items(): assert sha(a/path)==h,path
    dest=a/'corpus'; dest.mkdir(exist_ok=False)
    raw=UCI_HELPER.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==UCI_HELPER_SHA
    lb=types.ModuleType('context_uci');sys.modules[lb.__name__]=lb
    exec(compile(raw,str(UCI_HELPER),'exec'),lb.__dict__)
    class DeadlineUCI(lb.UCIProcess):
        root_deadline=None
        def until(self,predicate):
            allowed=time_left()
            if self.root_deadline is not None: allowed=min(allowed,self.root_deadline-time.monotonic())
            if allowed<=0: raise TimeoutError('Per-root or overall deadline reached')
            previous=self.config
            self.config=dc_replace(previous,timeout=min(previous.timeout,allowed))
            try: return super().until(predicate)
            finally: self.config=previous
        def search(self,root,cap):
            self.root_deadline=time.monotonic()+60
            try: return super().search(root,cap)
            finally: self.root_deadline=None
    import chess
    roots=[json.loads(x) for x in (ROOT/PLAN['roots']).read_text().splitlines()]
    assert len(roots)==128
    records={}; samples=[]
    try:
        for mode,binary in [('frozen',ROOT/'engines/new'),('reference',a/'chesssi-reference'),('observer',a/'chesssi-observer')]:
            os.environ.pop('CHESSSI_RFP_SHADOW_CONTEXT',None)
            if mode=='observer':os.environ['CHESSSI_RFP_SHADOW_CONTEXT']='1'
            rows=[]
            with DeadlineUCI([str(binary)],lb.Config(timeout=min(60,time_left()))) as runner:
                for i,root in enumerate(roots):
                    time_left()
                    runner.config=lb.Config(timeout=min(60,time_left()))
                    r=runner.search(root,131072)
                    (dest/f'{mode}-{i:03}.txt').write_text('\n'.join(r['transcript'])+'\n')
                    iteration=[{k:info.get(k) for k in ('depth','score_type','score','bounds','nodes','pv')} for info in r['infos']]
                    row={'id':root['id'],'iterations':iteration,'bestmove':r['bestmove']}
                    final=[int(line.split()[-1]) for line in r['transcript'] if line.startswith('< info string AUDITFINAL ')]
                    ss=[json.loads(line[len('< RFPSAMPLE '):]) for line in r['transcript'] if line.startswith('< RFPSAMPLE ')]
                    total=[json.loads(line[len('< RFPTOTAL '):]) for line in r['transcript'] if line.startswith('< RFPTOTAL ')]
                    if mode!='frozen': assert len(final)==1;row['final_nodes']=final[0]
                    if mode!='observer': assert not ss and not total
                    if mode=='observer':
                        assert len(total)==1 and total[0]['samples']==len(ss) and total[0]['nodes']==final[0]
                        row['totals']=total[0]
                        for sample in ss:
                            board=chess.Board(root['startfen'])
                            for text in root['moves']:
                                m=chess.Move.from_uci(text);assert m in board.legal_moves;board.push(m)
                            for text in sample['path']:
                                if text is None:
                                    assert not board.is_check()
                                    full=board.fullmove_number;board.push(chess.Move.null());board.fullmove_number=full
                                else:
                                    m=chess.Move.from_uci(text);assert m in board.legal_moves;board.push(m)
                            assert board.fen(en_passant='xfen')==sample['fen']
                            assert len(sample['path'])==sample['ply'] and sample['restored']
                            assert sample['control_nodes']==1 and not sample['control_stopped'] and sample['control_score']==sample['static_eval']
                            sample['root_id']=root['id'];samples.append(sample)
                            with (dest/'samples.jsonl').open('a') as handle:handle.write(json.dumps(sample)+'\n')
                    if mode=='reference': assert {k:row[k] for k in ('id','iterations','bestmove')}==records['frozen'][i]
                    if mode=='observer': assert {k:row[k] for k in ('id','iterations','bestmove','final_nodes')}==records['reference'][i]
                    rows.append(row)
                    with (dest/f'{mode}.jsonl').open('a') as handle:handle.write(json.dumps(row)+'\n')
                    if (i+1)%16==0: print(f'{mode} {i+1}/128',flush=True)
            records[mode]=rows
        complete=[s for s in samples if not s['shadow_stopped']]
        totals={k:sum(r['totals'][k] for r in records['observer']) for k in records['observer'][0]['totals']}
        frozen()
        result={'status':'complete','utc':now().isoformat(),'all_parent_traces_equal':True,
            'totals':totals,'samples':len(samples),'completed':len(complete),'censored':len(samples)-len(complete),
            'contradictions':sum(s['shadow_score']<s['beta'] for s in complete),
            'reduced_samples':sum(s['incoming_reduction']>0 for s in samples),
            'null_descendant_samples':sum(s['null_ancestors']>0 for s in samples),
            'reduced_contradictions':sum(s['incoming_reduction']>0 and s['shadow_score']<s['beta'] for s in complete),
            'null_descendant_contradictions':sum(s['null_ancestors']>0 and s['shadow_score']<s['beta'] for s in complete),
            'live_hashes_unchanged':True,'limitations':PLAN['limitations']}
        write(dest/'result.json',result);print(json.dumps(result,indent=2),flush=True)
    except BaseException as exc:
        if 'runner' in locals(): (dest/'failed-transcript.txt').write_text('\n'.join(runner.transcript)+'\n')
        write(dest/'failure.json',{'utc':now().isoformat(),'error':repr(exc),'traceback':traceback.format_exc(),'retained_samples':len(samples)})
        raise
if __name__=='__main__':
    os.chdir(ROOT)
    assert os.sched_getaffinity(0)=={19}
    os.environ.pop('CHESSSI_RFP_SHADOW_CONTEXT',None)
    if sys.argv[1:] == ['prepare']: prepare()
    elif len(sys.argv)==3 and sys.argv[1]=='corpus': corpus(sys.argv[2])
    else: raise SystemExit('prepare | corpus attempt-NN (corpus requires root review approval)')
