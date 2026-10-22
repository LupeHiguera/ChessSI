#!/usr/bin/env python3
"""Independent read-only verification. Never imports collector or launches engines."""
import ast
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import traceback

if sys.flags.optimize:
    raise RuntimeError('Required checks must not be optimized away')
ROOT=Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra')
HERE=ROOT/'engines/rfp-current-main-validation/first-pawn-preparation-01'
RUN=HERE/'run-01'
OUT=RUN/'peer-verification-01'
COLLECTOR_SHA='d0038130673266340d22dab30ad6eeab526c3c94ddaeebe4f1ea1d42ef064d58'
REFERENCE_SHA='b10c68c9870eb589b89ccab8d860cdeed91aeeddcff1618ecfa37aff35f6a6ab'
VARIANT_SHA='de5f32537455352cd7ee5fb191fd52e6e91cc6dceac4cf1be321e1d103477a56'
NODES=609035
inputs={}
def require(ok,message):
    if not ok: raise ValueError(message)
def raw(path):
    value=path.read_bytes()
    inputs[str(path.relative_to(ROOT))]=hashlib.sha256(value).hexdigest()
    return value
def read(path):return json.loads(raw(path))
def lines(path):return [json.loads(line) for line in raw(path).decode().splitlines()]
def pin(path,digest):
    value=raw(path);require(hashlib.sha256(value).hexdigest()==digest,'Hash mismatch: '+str(path));return value
def save(path,obj):
    with path.open('x') as f:json.dump(obj,f,indent=2,allow_nan=False);f.write('\n')
def equal(a,b,label):require(a==b,'Mismatch: '+label)
def close(a,b,label):require(math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-12),'Float mismatch: '+label)

def transcript(path,root):
    text=raw(path).decode().splitlines()
    position='> position fen '+root['startfen']
    if root['moves']:position+=' moves '+' '.join(root['moves'])
    equal(text.count(position),1,'exact position history')
    equal(text.count('> ucinewgame'),1,'new game')
    equal(text.count('> go nodes 131072'),1,'node budget')
    equal([s[6:].strip() for s in text if s.lower().startswith('< fen:')],[root['position_fen']],'FEN replay')
    best=[s.split()[2] for s in text if s.startswith('< bestmove ')]
    equal(len(best),1,'unique bestmove')
    infos=[]
    for line in text:
        if not line.startswith('< info depth '):continue
        tokens=line[2:].split()
        require(tokens[:2]==['info','depth'],'depth info grammar')
        s=tokens.index('score')
        pv=tokens.index('pv')
        require(tokens[s+1] in ('cp','mate'),'score type')
        infos.append({'depth':int(tokens[2]),'score_type':tokens[s+1],'score':int(tokens[s+2]),
           'bounds':[x for x in tokens if x in ('lowerbound','upperbound')],
           'nodes':int(tokens[tokens.index('nodes')+1]),'pv':tokens[pv+1:]})
    require(infos,'missing iterations')
    equal([i['depth'] for i in infos],list(range(1,len(infos)+1)),'consecutive completed depths')
    return {'id':root['id'],'iterations':infos,'bestmove':best[0]}

def verify():
    equal(os.sched_getaffinity(0),{19},'verifier CPU')
    collector=pin(RUN/'collect.py',COLLECTOR_SHA)
    constants={}
    for statement in ast.parse(collector).body:
        if isinstance(statement,ast.Assign) and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name):
            name=statement.targets[0].id
            if name in ('PINS','CONTEXT_PINS'):constants[name]=ast.literal_eval(statement.value)
    require(set(constants)=={'PINS','CONTEXT_PINS'},'collector pin declarations')
    for rel,digest in constants['PINS'].items():
        pin(HERE/rel,digest);pin(RUN/'inputs'/rel,digest)
    result=read(RUN/'result.json');plan=read(RUN/'inputs/plan.json')
    execution=read(RUN/'execution-plan.json')
    equal(result['status'],'complete','run status')
    equal(result['collector_sha256'],COLLECTOR_SHA,'result collector')
    equal(execution['collector_sha256'],COLLECTOR_SHA,'execution collector')
    equal(execution['plan_pins'],constants['PINS'],'execution pins')
    equal(execution['source_sha256'],plan['variant_build_inputs_sha256'],'execution source pins')
    equal(execution['collector_affinity'],[19],'execution affinity')
    equal(execution['python_flags'],{'optimize':0,'dont_write_bytecode':1},'execution Python flags')
    for rel,digest in plan['reference_build_inputs_sha256'].items():pin(ROOT/rel,digest)
    for rel,digest in plan['variant_build_inputs_sha256'].items():
        pin(HERE/rel,digest);pin(RUN/'candidate'/rel,digest)
    equal(set(plan['reference_build_inputs_sha256']),set(plan['variant_build_inputs_sha256']),'source input file sets')
    changed=[rel for rel in plan['reference_build_inputs_sha256'] if plan['reference_build_inputs_sha256'][rel]!=plan['variant_build_inputs_sha256'][rel]]
    equal(changed,['src/search.cpp'],'sole source change')
    for rel in ['check.cpp','Check.mk']:pin(RUN/'candidate'/rel,constants['PINS'][rel])
    for field in ['query_helper','dependency']:pin(Path(plan[field]['path']),plan[field]['sha256'])
    pin(RUN/'inputs/label_budget.py',plan['query_helper']['sha256'])
    pin(RUN/'reference-chesssi',REFERENCE_SHA);pin(RUN/'candidate/chesssi',VARIANT_SHA)
    pin(ROOT/'engines/new',REFERENCE_SHA)
    equal(result['binary_sha256'],{'reference':REFERENCE_SHA,'variant':VARIANT_SHA},'result binaries')
    equal(read(RUN/'binary-hashes.json'),result['binary_sha256'],'binary record')
    equal(result['plan_sha256'],constants['PINS']['plan.json'],'result plan')
    equal(result['amendment_sha256'],constants['PINS']['plan-amendment-01.json'],'result amendment')
    commands={p.stem:read(p) for p in sorted((RUN/'commands').glob('*.json'))}
    equal(len(commands),391,'command count')
    equal(result['commands_executed'],391,'reported command count')
    progress=lines(RUN/'progress.jsonl')
    equal(len(progress),391,'progress count')
    equal(len({p['command'] for p in progress}),391,'unique commands')
    for p in progress:
        q=dict(p);label=q.pop('command');equal(q,commands[label],'progress command '+label)
    for label,m in commands.items():
        equal(m['exit_code'],0,'command exit '+label)
        equal(m['timed_out'],False,'command timeout '+label)
        equal(m['collector_affinity'],[19],'command collector affinity '+label)
        require(m['wall_seconds']>0,'command elapsed '+label)
        require(dt.datetime.fromisoformat(m['finished_utc'])>=dt.datetime.fromisoformat(m['started_utc']),'command timestamps '+label)
        require((RUN/'commands'/f'{label}.stdout').is_file() and (RUN/'commands'/f'{label}.stderr').is_file(),'missing command output '+label)
    require(not (RUN/'failure.json').exists(),'run failure exists')
    bench=lines(RUN/'bench-invocations.jsonl')
    expected=['validation-bench','warmup-reference','warmup-variant']
    for pair in range(6):
        for binary in (['reference','variant'] if pair%2==0 else ['variant','reference']):
            expected.extend(f'timing-{pair}-{binary}-{i:02}' for i in range(32))
    equal([b['label'] for b in bench],expected,'exact 387 invocation schedule')
    equal(len(bench),387,'bench invocation count')
    equal(set(commands)-set(expected),{'release','sanitizer','witness-build','witness-oracle'},'no extra commands')
    for b in bench:
        label=b['label'];m=commands[label]
        equal(b['stdout'],'commands/'+label+'.stdout','stdout path')
        equal(b['stderr'],'commands/'+label+'.stderr','stderr path')
        equal(b['command_record'],'commands/'+label+'.json','command path')
        binary=RUN/'reference-chesssi' if b['binary']=='reference' else RUN/'candidate/chesssi'
        equal(m['argv'],['taskset','-c','19',str(binary),'bench'],'bench argv '+label)
        equal(m['configured_process_affinity'],[19],'configured bench affinity')
        equal(m['observed_process_affinity'],[19],'observed bench affinity')
        equal(b['binary_sha256'],result['binary_sha256'][b['binary']],'bench binary hash')
        stdout=raw(RUN/b['stdout']).decode();stderr=raw(RUN/b['stderr']).decode()
        signatures=re.findall(r'^(\d+) nodes (\d+) nps$',stdout,re.M)
        times=re.findall(r'^Time: (\d+) ms$',stdout+'\n'+stderr,re.M)
        equal(len(signatures),1,'bench unique signature '+label);equal(len(times),1,'bench unique time '+label)
        equal(int(signatures[0][0]),NODES,'raw bench nodes '+label)
        equal(b['nodes'],NODES,'recorded bench nodes '+label)
        equal(b['reported_search_ms'],int(times[0]),'raw bench time '+label)
        close(b['wall_seconds'],m['wall_seconds'],'bench wall time '+label)
    observed_pairs=[];observed_bundles=[]
    for pair in range(6):
        order=['reference','variant'] if pair%2==0 else ['variant','reference']
        p={'pair':pair,'order':order}
        for binary in order:
            selected=[b for b in bench if b['label'].startswith(f'timing-{pair}-{binary}-')]
            equal(len(selected),32,'bundle count')
            bundle={'invocations':32,'reported_search_ms':sum(b['reported_search_ms'] for b in selected),
                    'nodes':sum(b['nodes'] for b in selected),'wall_seconds':sum(b['wall_seconds'] for b in selected)}
            p[binary]=bundle;observed_bundles.append({'pair':pair,'binary':binary,**bundle})
        observed_pairs.append(p)
    equal(lines(RUN/'timing-pairs.jsonl'),observed_pairs,'raw paired sums')
    equal(lines(RUN/'timing-bundles.jsonl'),observed_bundles,'raw bundle sums')
    equal(result['timing']['pairs'],observed_pairs,'reported paired sums')
    ref=[p['reference']['reported_search_ms'] for p in observed_pairs]
    var=[p['variant']['reported_search_ms'] for p in observed_pairs]
    reference=statistics.median(ref);variant=statistics.median(var)
    close(result['timing']['median_reference_bundle_ms'],reference,'reference median')
    close(result['timing']['median_variant_bundle_ms'],variant,'variant median')
    delta=100*(variant/reference-1)
    close(result['timing']['median_bundle_time_change_percent'],delta,'median percentage')
    equal(result['timing']['measured_invocations'],384,'measured invocations')
    equal(result['timing']['warmup_invocations'],2,'warmups')
    equal(result['timing']['measured_nodes'],384*NODES,'measured nodes')
    faster=sum(v<r for r,v in zip(ref,var));equal(result['timing']['variant_faster_pairs'],faster,'faster pairs')
    selection=read(RUN/'reference-selection.json')
    equal(selection['mode'],'verified-existing-current-reference','reference reuse mode')
    equal(selection['binary_sha256'],REFERENCE_SHA,'reference reuse binary')
    equal(selection['roots_sha256'],constants['PINS']['roots.jsonl'],'reference reuse roots')
    equal(selection['trace_roots'],128,'reference count')
    equal(selection['requested_nodes_per_root'],131072,'reference node cap')
    for rel,digest in constants['CONTEXT_PINS'].items():equal(selection['sha256'][rel],digest,'reference context pin '+rel)
    for rel,digest in selection['sha256'].items():pin(RUN/'reused-reference'/rel,digest)
    roots=lines(RUN/'inputs/roots.jsonl');equal(len(roots),128,'root input count')
    variants=lines(RUN/'variant-traces.jsonl')
    references=lines(RUN/'reused-reference/corpus/frozen.jsonl')
    equal(len(variants),128,'variant row count');equal(len(references),128,'reference row count')
    iterations=0
    for i,root in enumerate(roots):
        v=transcript(RUN/f'variant-{i:03}.txt',root)
        r=transcript(RUN/f'reused-reference/corpus/frozen-{i:03}.txt',root)
        equal(v,variants[i],'variant transcript row '+str(i));equal(r,references[i],'reference transcript row '+str(i))
        equal(v,r,'current-reference versus variant '+str(i));iterations+=len(v['iterations'])
    for stage,phrases in [('release',['35 passed, 0 failed','17 passed, 0 failed']),('sanitizer',['17 passed, 0 failed'])]:
        text=raw(RUN/'commands'/f'{stage}.stdout').decode()
        error=raw(RUN/'commands'/f'{stage}.stderr').decode()
        for phrase in phrases:equal(text.count(phrase),1,'test summary '+phrase)
        require('runtime error:' not in error and 'ERROR: AddressSanitizer' not in error,'sanitizer error')
    report={'status':'passed','verified_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'cpu_affinity':[19],
       'engines_launched':0,'builds_run':0,'bench_invocations_verified':387,'measured_invocations':384,
       'warmup_invocations':2,'validation_invocations':1,'all_bench_nodes':NODES,
       'measured_nodes':384*NODES,'all_invocation_nodes':387*NODES,
       'commands_verified':len(commands),'failed_commands':0,'timing_pairs':6,'bundle_size':32,
       'reference_bundle_search_ms':ref,'variant_bundle_search_ms':var,
       'reference_total_search_ms':sum(ref),'variant_total_search_ms':sum(var),
       'aggregate_search_time_change_percent':100*(sum(var)/sum(ref)-1),
       'median_reference_bundle_search_ms':reference,'median_variant_bundle_search_ms':variant,
       'median_bundle_search_time_change_percent':delta,
       'pair_search_ms_differences_variant_minus_reference':[v-r for r,v in zip(ref,var)],
       'variant_faster_search_ms_pairs':faster,
       'median_reference_bundle_wall_seconds':statistics.median(p['reference']['wall_seconds'] for p in observed_pairs),
       'median_variant_bundle_wall_seconds':statistics.median(p['variant']['wall_seconds'] for p in observed_pairs),
       'variant_faster_wall_time_pairs':sum(p['variant']['wall_seconds']<p['reference']['wall_seconds'] for p in observed_pairs),
       'exact_current_reference_trace_roots':128,'completed_iterations_compared':iterations,
       'reference_binary_sha256':REFERENCE_SHA,'variant_binary_sha256':VARIANT_SHA,
       'source_input_count_per_build':len(plan['reference_build_inputs_sha256']),
       'collector_sha256':COLLECTOR_SHA,'collected_result_sha256':inputs[str((RUN/'result.json').relative_to(ROOT))],
       'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'limits':'Finite saved cases, integer-millisecond reported search times and shared machine load. Six alternating bundles, not independent rating evidence. One pair differs by only 3 ms. Wall times include process/startup overhead and do not show the same direction; no reruns, engine queries, strength claim or promotion.'}
    save(OUT/'input-hashes.json',inputs);save(OUT/'result.json',report)
    print(json.dumps(report,indent=2))
try:
    verify()
except BaseException as e:
    save(OUT/'failure.json',{'error':repr(e),'traceback':traceback.format_exc(),'input_hashes':inputs})
    raise
