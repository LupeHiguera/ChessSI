#!/usr/bin/env python3
"""Execute the frozen first-pawn plan only after an explicit CPU19 release."""
import argparse
import datetime as dt
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys
import time
import traceback
import types

if sys.flags.optimize or not __debug__:
    raise RuntimeError('Run without -O/-OO/PYTHONOPTIMIZE; required checks must remain enabled')

ROOT=Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra')
HERE=ROOT/'engines/rfp-current-main-validation/first-pawn-preparation-01'
CONTEXT=ROOT/'engines/rfp-current-main-validation/shadow-context-01/attempt-02'
PYTHON_CHESS=ROOT/'engines/dependencies/python-chess'
DEADLINE=dt.datetime(2026,10,22,18,0,tzinfo=dt.timezone.utc)
PINS={
 'plan.json':'27c54545401e967a15a279fd02518f2745036ac2e0d2c66dd9861c678f7c8d4d',
 'plan-amendment-01.json':'c51c7a2300707a932c6e39fd6f0b69a86aa8e0a09e20bdba8b8be786a0202fb9',
 'candidate.patch':'bccf717052f32f2c7f1c7247a424e5655d80de0785747f130eedc2a55d1eb347',
 'Check.mk':'886d775d432e4f64943f0f840788bd38b2774daf72bb6258495fc31937f0c0f0',
 'check.cpp':'6f69c1ed1e548525c208b0ba2847b14fd468b8916aec0fd7dd2a4875a88e1ac8',
 'positions.jsonl':'58effe17580f433a74e8d9ecc550f5ebf67c7bb8c1d79c6ca0f6721c73f26dec',
 'roots.jsonl':'8a197269535824b8d6dedd978cec7988e7ec94ec3eaaa3bb3e2f7ba4ec9db505',
}
CONTEXT_PINS={
 'validation.json':'1934eb779c66da39a061ea1a6f894209ff3b33891fe5bca27b6bf4ff52ecf484',
 'collector.py':'496b5ad47703e6c6a41c98ce5e4eaccd100e809d70099bb9c27f61c63caf8f11',
 'plan.json':'127c749fd45746bcb6a25d0c2df95d4fe2aae97f22fa1d09954d17e99537f5cc',
 'preflight-correction.json':'17bdd26c83c52f8742cf4ba6c77f852b41d0a0fca8ff31d7b86533d84def27bb',
 'launch-plan.json':'21c73ab2b9de0088cff27a9c698ff3b0221bb570589ff4babb531af4612b6937',
 'label_budget.py':'12bd0bc6ac1cc3ba584f71236ad1671842db34625d563a7206e5f8a6a05ba90b',
 'corpus/frozen.jsonl':'cac094dcd6dcd655271390a0bac34b0209e53567bec5e23ebf1c3166531ae1b7',
 'corpus/result.json':'91fe93df2a354230cec4789ad98b4c88b4e1e0d6330a0c428052fb3a996f0b3c',
}
FIELDS=('depth','score_type','score','bounds','nodes','pv')
NODES=609035
CAP=131072


def require(condition,message):
    if not condition: raise ValueError(message)

def now(): return dt.datetime.now(dt.timezone.utc)

def time_left():
    remaining=(DEADLINE-now()).total_seconds()
    if remaining<=0: raise TimeoutError('Fixed 18:00 UTC deadline reached')
    return remaining

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): digest.update(block)
    return digest.hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f: f.write(raw)

def record(path,value): write(path,(json.dumps(value,indent=2,allow_nan=False)+'\n').encode())

def append(path,value):
    with path.open('a') as f: f.write(json.dumps(value,allow_nan=False)+'\n');f.flush()

def verified(path,digest):
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==digest,'Changed input: '+str(path))
    return raw

def interrupt(signum,frame): raise InterruptedError('External signal '+str(signum))


class Collector:
    def __init__(self,out):
        self.out=out
        self.build=out/'candidate'
        self.completed={}
        self.binary_hashes={}
        self.commands=0
        self.script_bytes=Path(__file__).read_bytes()
        self.script_sha=hashlib.sha256(self.script_bytes).hexdigest()
        self.plan=json.loads(verified(HERE/'plan.json',PINS['plan.json']))
        self.amendment=json.loads(verified(HERE/'plan-amendment-01.json',PINS['plan-amendment-01.json']))
        self.env=dict(os.environ)
        self.env.pop('MAKEFLAGS',None)
        self.env.pop('CHESSSI_RFP_SHADOW_CONTEXT',None)
        self.env['PYTHONPATH']=str(PYTHON_CHESS)
        self.env['ASAN_OPTIONS']='abort_on_error=1'
        self.env['UBSAN_OPTIONS']='halt_on_error=1:print_stacktrace=1'
        self.reference=ROOT/'engines/rfp-current-main-validation/source-snapshot-01/files/0031-new'
        self.frozen()
        helper=self.plan['query_helper']
        raw=verified(Path(helper['path']),helper['sha256'])
        self.lb=types.ModuleType('first_pawn_uci');self.lb.__file__=helper['path']
        sys.modules[self.lb.__name__]=self.lb
        exec(compile(raw,helper['path'],'exec'),self.lb.__dict__)
        self.roots=[json.loads(line) for line in (HERE/'roots.jsonl').read_text().splitlines()]
        self.positions=[json.loads(line) for line in (HERE/'positions.jsonl').read_text().splitlines()]
        require(len(self.roots)==128 and len(self.positions)==2203,'Unexpected fixed corpus counts')
        require(len({r['id'] for r in self.roots})==128,'Duplicate root IDs')
        for relative in self.plan['variant_build_inputs_sha256']:
            write(self.build/relative,(HERE/relative).read_bytes())
        for relative in ('check.cpp','Check.mk'):
            write(self.build/relative,(HERE/relative).read_bytes())
        for relative in PINS:
            write(out/'inputs'/relative,(HERE/relative).read_bytes())
        write(out/'collect.py',self.script_bytes)
        write(out/'inputs/label_budget.py',raw)
        reference_bytes=verified(self.reference,self.plan['expected_reference_binary_sha256'])
        self.reference=out/'reference-chesssi'
        write(self.reference,reference_bytes)
        self.reference.chmod(0o755)
        self.binary_hashes['reference']=sha(self.reference)
        record(out/'execution-plan.json',{
            'started_utc':now().isoformat(),'deadline_utc':DEADLINE.isoformat(),
            'cpu19_release_flag':True,'collector_sha256':self.script_sha,'plan_pins':PINS,
            'source_sha256':self.plan['variant_build_inputs_sha256'],
            'reference_binary':str(self.reference),'reference_binary_sha256':self.binary_hashes['reference'],
            'helper_sha256':helper['sha256'],'python':sys.version,'python_executable':sys.executable,
            'python_flags':{'optimize':sys.flags.optimize,'dont_write_bytecode':sys.flags.dont_write_bytecode},
            'collector_affinity':sorted(os.sched_getaffinity(0)),
            'environment_overrides':{k:self.env[k] for k in ('PYTHONPATH','ASAN_OPTIONS','UBSAN_OPTIONS')},
            'build_location':'An exact copy of the prepared source under this exclusive run directory; no prepared/live sources modified.',
            'make_policy':'taskset -c14-19 make -j6, CXX=taskset -c19 g++; make-test recipes inherit14-19, not CPU19-only.',
            'direct_policy':'taskset -c19 for witness, UCI and bench processes.',
            'bounds':'No retries.128 variant trace roots; at most128 fallback reference roots.6 paired bundles of32 default benches per binary plus1 warmup per binary. Stop on failure or18:00UTC.'})

    def frozen(self):
        time_left()
        require(os.sched_getaffinity(0)=={19},'Collector must remain on CPU19')
        for relative,digest in PINS.items(): verified(HERE/relative,digest)
        for relative,digest in self.plan['variant_build_inputs_sha256'].items(): verified(HERE/relative,digest)
        for relative,digest in self.plan['reference_build_inputs_sha256'].items(): verified(ROOT/relative,digest)
        verified(ROOT/'engines/new',self.plan['expected_reference_binary_sha256'])
        verified(self.reference,self.plan['expected_reference_binary_sha256'])
        verified(Path(self.plan['query_helper']['path']),self.plan['query_helper']['sha256'])
        verified(Path(self.plan['dependency']['path']),self.plan['dependency']['sha256'])
        require(sha(Path(__file__))==self.script_sha,'Collector changed during run')
        if self.build.exists():
            for relative,digest in self.plan['variant_build_inputs_sha256'].items(): verified(self.build/relative,digest)
            for relative in ('check.cpp','Check.mk'): verified(self.build/relative,PINS[relative])
        for name,digest in self.binary_hashes.items():
            verified(self.reference if name=='reference' else self.build/'chesssi',digest)

    def command(self,label,argv,*,stdin=None,timeout=90,make=False):
        time_left()
        folder=self.out/'commands';folder.mkdir(exist_ok=True)
        base=folder/label
        metadata={'argv':argv,'cwd':str(self.build),'started_utc':now().isoformat(),
            'collector_affinity':sorted(os.sched_getaffinity(0)),
            'configured_process_affinity':list(range(14,20)) if make else [19],
            'affinity_scope':'make and test recipes inherit CPUs14-19; compiler is explicitly wrapped onto19. No claim of CPU19-only recipes.' if make else 'Direct taskset-c19 child of CPU19 collector.',
            'exit_code':None,'timed_out':False,'observed_process_affinity':None,
            'affinity_samples':[],'recipe_affinity_observation':'Only observed own-child samples are attested; very short recipes may not be sampled.'}
        started=time.monotonic();process=None
        input_handle=None
        try:
            if stdin is not None: input_handle=stdin.open('rb')
            with base.with_suffix('.stdout').open('xb') as stdout,base.with_suffix('.stderr').open('xb') as stderr:
                process=subprocess.Popen(argv,cwd=self.build,env=self.env,stdin=input_handle or subprocess.DEVNULL,
                                         stdout=stdout,stderr=stderr,start_new_session=True)
                metadata['pid']=process.pid
                # Read only the child we just created. For very short commands observation may race exit.
                try: metadata['observed_process_affinity']=sorted(os.sched_getaffinity(process.pid))
                except ProcessLookupError: pass
                try:
                    allowed_until=time.monotonic()+min(timeout,time_left())
                    observed=set()
                    while make and process.poll() is None:
                        pending=[process.pid]
                        while pending:
                            pid=pending.pop()
                            try:
                                proc=Path('/proc')/str(pid)
                                stat=(proc/'stat').read_text().rsplit(')',1)[1].split()
                                executable=os.readlink(proc/'exe')
                                affinity=tuple(sorted(os.sched_getaffinity(pid)))
                                key=(pid,stat[19],executable,affinity)
                                if key not in observed:
                                    observed.add(key)
                                    metadata['affinity_samples'].append({'pid':pid,'start_ticks':stat[19],
                                        'exe':executable,'affinity':list(affinity)})
                                pending.extend(int(x) for x in (proc/'task'/str(pid)/'children').read_text().split())
                            except (OSError,ProcessLookupError): pass
                        remaining=min(allowed_until-time.monotonic(),time_left())
                        if remaining<=0: raise subprocess.TimeoutExpired(argv,timeout)
                        try: process.wait(timeout=min(0.02,remaining))
                        except subprocess.TimeoutExpired: pass
                    metadata['exit_code']=process.wait(timeout=min(allowed_until-time.monotonic(),time_left()))
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait(timeout=5)
                    raise
            require(metadata['exit_code']==0,'Command failed: '+label)
        except subprocess.TimeoutExpired:
            metadata['timed_out']=True
            raise TimeoutError('Command timeout: '+label)
        finally:
            if input_handle is not None: input_handle.close()
            metadata['wall_seconds']=time.monotonic()-started
            metadata['finished_utc']=now().isoformat()
            if process is not None: metadata['exit_code']=process.poll()
            record(base.with_suffix('.json'),metadata)
            self.commands+=1
            append(self.out/'progress.jsonl',{'command':label,**metadata})
        time_left()
        return base.with_suffix('.stdout').read_text(),base.with_suffix('.stderr').read_text(),metadata

    def correctness(self):
        self.frozen()
        for stage,counts in (('release',('35 passed, 0 failed','17 passed, 0 failed')),
                             ('sanitizer',('17 passed, 0 failed',))):
            item=next(x for x in self.amendment['build_commands'] if x['stage']==stage)
            stdout,stderr,_=self.command(stage,item['argv'],make=True)
            for text in counts: require(stdout.count(text)==1,'Missing/ambiguous '+stage+' summary: '+text)
            require('runtime error:' not in stderr and 'ERROR: AddressSanitizer' not in stderr,'Sanitizer diagnostic')
            self.completed[stage]=list(counts)
            self.frozen()
        item=next(x for x in self.amendment['build_commands'] if x['stage']=='witness_oracle_build')
        self.command('witness-build',item['argv'],make=True)
        self.binary_hashes['variant']=sha(self.build/'chesssi')
        record(self.out/'binary-hashes.json',self.binary_hashes)
        fen_input=self.out/'witness-fens.txt'
        write(fen_input,(''.join(p['fen']+'\n' for p in self.positions)).encode())
        stdout,_,_=self.command('witness-oracle',['taskset','-c','19',str(self.build/'check')],stdin=fen_input,timeout=60)
        lines=stdout.splitlines()
        require(len(lines)==2203,'Witness output count differs')
        for i,(line,position) in enumerate(zip(lines,self.positions)):
            ident,move=line.split()
            require(int(ident)==i,'Witness index differs')
            legal=position['legal_oracle']
            require((move=='0000')==(not legal),'Witness terminal status differs')
            require(move=='0000' or move in legal,'Witness not in independent stored legal oracle')
        self.completed['witness_positions']=2203
        self.bench('variant','validation-bench')
        self.completed['bench']=NODES
        self.frozen()

    def bench(self,name,label):
        binary=self.reference if name=='reference' else self.build/'chesssi'
        require(sha(binary)==self.binary_hashes[name],'Binary drift before '+label)
        stdout,stderr,metadata=self.command(label,['taskset','-c','19',str(binary),'bench'],timeout=60)
        nodes=re.fullmatch(r'(\d+) nodes (\d+) nps',stdout.splitlines()[-1])
        ms=re.findall(r'^Time: (\d+) ms$',stdout+'\n'+stderr,re.MULTILINE)
        require(nodes is not None and int(nodes.group(1))==NODES,'Benchmark node signature differs: '+label)
        require(len(ms)==1,'Missing/ambiguous reported search time: '+label)
        result={'label':label,'binary':name,'binary_sha256':self.binary_hashes[name],
                'nodes':int(nodes.group(1)),'reported_search_ms':int(ms[0]),'wall_seconds':metadata['wall_seconds'],
                'stdout':'commands/'+label+'.stdout','stderr':'commands/'+label+'.stderr',
                'command_record':'commands/'+label+'.json'}
        append(self.out/'bench-invocations.jsonl',result)
        return result

    def transcript_row(self,root,lines):
        expected='> position fen '+root['startfen']
        if root['moves']: expected+=' moves '+' '.join(root['moves'])
        require(lines.count(expected)==1 and lines.count('> go nodes '+str(CAP))==1,'Wrong UCI history or node budget')
        require(lines.count('> ucinewgame')==1,'Missing new-game reset')
        fens=[line[6:].strip() for line in lines if line.lower().startswith('< fen:')]
        require(fens==[root['position_fen']],'Reference replayed FEN differs')
        best=[line.split()[2] for line in lines if line.startswith('< bestmove ')]
        require(len(best)==1,'Missing/duplicate bestmove')
        infos=[info for line in lines if line.startswith('< ') and (info:=self.lb.parse_info(line[2:])) is not None]
        require(infos,'No completed search iterations')
        return {'id':root['id'],'iterations':[{k:info.get(k) for k in FIELDS} for info in infos],'bestmove':best[0]}

    def existing_reference(self):
        try:
            files={rel:verified(CONTEXT/rel,digest) for rel,digest in CONTEXT_PINS.items()}
            validation=json.loads(files['validation.json']);launch=json.loads(files['launch-plan.json'])
            require(validation['status']=='ready_for_review_not_corpus' and validation['bench']==NODES,'Context validation incomplete')
            require(validation['collector_sha256']==CONTEXT_PINS['collector.py'],'Context collector not bound')
            require(validation['launch_plan_sha256']==CONTEXT_PINS['launch-plan.json'],'Context launch not bound')
            require(validation['uci_helper_sha256']==self.plan['query_helper']['sha256'],'Context helper differs')
            require(launch['candidate_binary_sha256']==self.plan['expected_reference_binary_sha256'],'Context used another candidate')
            require(launch['source_files_sha256']==self.plan['reference_build_inputs_sha256'],'Context source differs')
            result_bytes=files['corpus/result.json'];result=json.loads(result_bytes)
            require(result.get('status')=='complete' and result.get('all_parent_traces_equal') is True and result.get('live_hashes_unchanged') is True,'Context pass has not completed cleanly')
            rows=[json.loads(line) for line in files['corpus/frozen.jsonl'].decode().splitlines()]
            require(len(rows)==128,'Frozen reference pass incomplete')
            transcript_bytes={}
            for i,(row,root) in enumerate(zip(rows,self.roots)):
                time_left()
                rel=f'corpus/frozen-{i:03}.txt';raw=(CONTEXT/rel).read_bytes()
                require(self.transcript_row(root,raw.decode().splitlines())==row,'Reference transcript disagrees: '+str(i))
                transcript_bytes[rel]=raw
            # Copy and bind the verified bytes before any variant query. These are observations, not old-baseline traces.
            for rel,raw in {**files,**transcript_bytes,'corpus/result.json':result_bytes}.items():
                write(self.out/'reused-reference'/rel,raw)
            record(self.out/'reference-selection.json',{'mode':'verified-existing-current-reference','source':str(CONTEXT),
                'sha256':{rel:hashlib.sha256(raw).hexdigest() for rel,raw in {**files,**transcript_bytes,'corpus/result.json':result_bytes}.items()},
                'binary_sha256':self.plan['expected_reference_binary_sha256'],'roots_sha256':PINS['roots.jsonl'],
                'trace_roots':128,'requested_nodes_per_root':CAP})
            return rows
        except (OSError,ValueError,KeyError,TypeError) as error:
            record(self.out/'reference-reuse-unavailable.json',{'reason':str(error),'action':'One bounded current-reference pass; no retries.'})
            return None

    def trace_pass(self,name,expected=None):
        self.frozen()
        lb=self.lb
        class DeadlineUCI(lb.UCIProcess):
            root_deadline=None
            def until(inner,predicate):
                allowance=time_left()
                if inner.root_deadline is not None: allowance=min(allowance,inner.root_deadline-time.monotonic())
                if allowance<=0: raise TimeoutError('UCI root/overall deadline')
                previous=inner.config;inner.config=replace(previous,timeout=min(previous.timeout,allowance))
                try: return super().until(predicate)
                finally: inner.config=previous
            def search(inner,root,cap):
                inner.root_deadline=time.monotonic()+45
                try: return super().search(root,cap)
                finally: inner.root_deadline=None
        binary=self.reference if name=='reference' else self.build/'chesssi'
        rows=[];engine=None
        try:
            engine=DeadlineUCI(['taskset','-c','19',str(binary)],lb.Config(timeout=min(45,time_left())))
            require(os.sched_getaffinity(engine.process.pid)=={19},'UCI engine affinity differs')
            write(self.out/f'{name}-startup.txt',('\n'.join(engine.transcript)+'\n').encode())
            for i,root in enumerate(self.roots):
                time_left()
                result=engine.search(root,CAP)
                write(self.out/f'{name}-{i:03}.txt',('\n'.join(result['transcript'])+'\n').encode())
                row=self.transcript_row(root,result['transcript'])
                append(self.out/(name+'-traces.jsonl'),row)
                if expected is not None: require(row==expected[i],'Full-history search trace mismatch at '+str(i))
                rows.append(row)
                if (i+1)%32==0: print(name+' traces '+str(i+1)+'/128',flush=True)
        except BaseException:
            if engine is not None: write(self.out/(name+'-failed-transcript.txt'),('\n'.join(engine.transcript)+'\n').encode())
            raise
        finally:
            if engine is not None: engine.close()
        self.frozen()
        return rows

    def traces(self):
        expected=self.existing_reference()
        if expected is None:
            expected=self.trace_pass('reference')
            record(self.out/'reference-selection.json',{'mode':'one-new-current-reference-pass','trace_roots':128,
                'binary_sha256':self.binary_hashes['reference'],'roots_sha256':PINS['roots.jsonl'],
                'transcript_sha256':{f'reference-{i:03}.txt':sha(self.out/f'reference-{i:03}.txt') for i in range(128)},
                'trace_sha256':sha(self.out/'reference-traces.jsonl'),'requested_nodes_per_root':CAP})
        self.trace_pass('variant',expected)
        self.completed['exact_history_traces']=128
        record(self.out/'correctness.json',{'status':'passed','completed':self.completed,'binary_sha256':self.binary_hashes,
                                           'scope':'Finite development validation only; no universal-equivalence or strength claim.'})

    def timing(self):
        self.frozen()
        for name in ('reference','variant'): self.bench(name,'warmup-'+name)
        pairs=[]
        for pair_index in range(6):
            self.frozen()
            order=['reference','variant'] if pair_index%2==0 else ['variant','reference']
            pair={'pair':pair_index,'order':order}
            for name in order:
                records=[self.bench(name,f'timing-{pair_index}-{name}-{i:02}') for i in range(32)]
                total=sum(r['reported_search_ms'] for r in records)
                nodes=sum(r['nodes'] for r in records)
                require(nodes==32*NODES and total>0,'Invalid timing bundle total')
                pair[name]={'invocations':32,'reported_search_ms':total,'nodes':nodes,
                            'wall_seconds':sum(r['wall_seconds'] for r in records)}
                append(self.out/'timing-bundles.jsonl',{'pair':pair_index,'binary':name,**pair[name]})
            pairs.append(pair);append(self.out/'timing-pairs.jsonl',pair)
            print('Completed timing pair '+str(pair_index+1)+'/6',flush=True)
        self.frozen()
        reference=statistics.median(p['reference']['reported_search_ms'] for p in pairs)
        variant=statistics.median(p['variant']['reported_search_ms'] for p in pairs)
        return {'pairs':pairs,'measured_invocations':384,'warmup_invocations':2,
            'measured_nodes':384*NODES,'median_reference_bundle_ms':reference,'median_variant_bundle_ms':variant,
            'median_bundle_time_change_percent':100*(variant/reference-1),
            'variant_faster_pairs':sum(p['variant']['reported_search_ms']<p['reference']['reported_search_ms'] for p in pairs),
            'scope':'Six fixed alternating within-machine bundles; raw reported search milliseconds. No Elo claim or adaptive repetitions.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cpu19-released',action='store_true',help='Set only after root explicitly releases CPU19 and authorizes this run')
    args=parser.parse_args()
    require(args.cpu19_released,'Root CPU19 release and execution authorization required')
    require(os.sched_getaffinity(0)=={19},'Run collector under taskset -c19')
    require(sys.flags.dont_write_bytecode,'Use python3 -B')
    require(str(PYTHON_CHESS) in os.environ.get('PYTHONPATH','').split(os.pathsep),'Set the prescribed absolute PYTHONPATH')
    time_left()
    out=args.output.resolve();out.relative_to(HERE)
    require(out.parent==HERE and out!=HERE,'Use a new direct child output directory')
    out.mkdir(exist_ok=False)
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    collector=None
    try:
        collector=Collector(out)
        collector.correctness()
        collector.traces()
        timing=collector.timing()
        record(out/'result.json',{'status':'complete','finished_utc':now().isoformat(),'correctness':collector.completed,
            'timing':timing,'binary_sha256':collector.binary_hashes,'collector_sha256':collector.script_sha,
            'plan_sha256':PINS['plan.json'],'amendment_sha256':PINS['plan-amendment-01.json'],
            'commands_executed':collector.commands,'source_inputs_rechecked':True,
            'disposition':'Isolated only. No live change, strength test, Elo estimate or promotion.'})
        return 0
    except BaseException as error:
        record(out/'failure.json',{'status':'incomplete_or_failed','recorded_utc':now().isoformat(),
            'error':repr(error),'traceback':traceback.format_exc(),'completed':collector.completed if collector else {},
            'commands_executed':collector.commands if collector else 0,
            'scope':'All partial artifacts retained. No retries or inferred success.'})
        print('Stopped with preserved failure: '+repr(error),file=sys.stderr,flush=True)
        return 2


if __name__=='__main__': raise SystemExit(main())
