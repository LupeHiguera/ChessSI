import collections, hashlib, json, os, sys
from pathlib import Path
assert os.sched_getaffinity(0)=={19}
r=Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra'); a=r/'engines/rfp-current-main-validation/shadow-context-01/attempt-02'; c=a/'corpus'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def lines(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
v=read(a/'validation.json'); result=read(c/'result.json')
assert v['collector_sha256']=='496b5ad47703e6c6a41c98ce5e4eaccd100e809d70099bb9c27f61c63caf8f11'
for name,h in {**v['files'],**v['binaries']}.items(): assert sha(a/name)==h,name
assert sha(a/'collector.py')==v['collector_sha256']
for name,h in read(a/'launch-plan.json')['source_files_sha256'].items(): assert sha(r/name)==h,name
roots=lines(r/'engines/qsearch-validation/game-profile-01/roots.jsonl'); assert len(roots)==128
assert sha(r/'engines/qsearch-validation/game-profile-01/roots.jsonl')=='8a197269535824b8d6dedd978cec7988e7ec94ec3eaaa3bb3e2f7ba4ec9db505'
rows={mode:lines(c/(mode+'.jsonl')) for mode in ['frozen','reference','observer']}; samples=lines(c/'samples.jsonl'); raw_samples=[]
for mode,rr in rows.items():
 assert len(rr)==128
 for i,(root,row) in enumerate(zip(roots,rr)):
  assert row['id']==root['id']; t=(c/f'{mode}-{i:03}.txt').read_text().splitlines()
  command='> position fen '+root['startfen']+(' moves '+' '.join(root['moves']) if root['moves'] else '')
  assert command in t and t.count('> go nodes 131072')==1 and t.count('> ucinewgame')==1
  infos=[]
  for line in t:
   if line.startswith('< info depth '):
    z=line.split(); get=lambda name:z[z.index(name)+1]; j=z.index('score')
    infos.append(dict(depth=int(get('depth')),score_type=z[j+1],score=int(z[j+2]),bounds=[w for w in z if w in ('upperbound','lowerbound')],nodes=int(get('nodes')),pv=z[z.index('pv')+1:]))
  assert infos==row['iterations'],(mode,i)
  assert [x for x in t if x.startswith('< bestmove ')]==['< bestmove '+row['bestmove']]
  if mode!='frozen': assert [int(x.split()[-1]) for x in t if x.startswith('< info string AUDITFINAL ')]==[row['final_nodes']]
  if mode=='observer':
   assert [json.loads(x[len('< RFPTOTAL '):]) for x in t if x.startswith('< RFPTOTAL ')]==[row['totals']]
   ss=[dict(json.loads(x[len('< RFPSAMPLE '):]),root_id=root['id']) for x in t if x.startswith('< RFPSAMPLE ')]; raw_samples+=ss
   assert len(ss)==row['totals']['samples']<=8
   for k in ['shadow_nodes','control_nodes']: assert sum(x[k] for x in ss)==row['totals'][k]
for f,ref,obs in zip(*[rows[x] for x in ('frozen','reference','observer')]):
 assert f=={k:ref[k] for k in f}; assert ref=={k:obs[k] for k in ref}
assert raw_samples==samples
assert {k:sum(row['totals'][k] for row in rows['observer']) for k in rows['observer'][0]['totals']}==result['totals']
dep=r/'engines/dependencies/python-chess'; assert sha(dep/'chess/__init__.py')=='1fde6a8e932508d14b31f6a584497b49c2969fc3c7cdc675347f819f0d667a5b'
sys.path.insert(0,str(dep)); import chess
by_id={x['id']:x for x in roots}; real_plies=0; null_plies=0
for s in samples:
 root=by_id[s['root_id']]; b=chess.Board(root['startfen'])
 for text in root['moves']:
  m=chess.Move.from_uci(text); assert m in b.legal_moves; b.push(m); real_plies+=1
 for text in s['path']:
  if text is None:
   assert not b.is_check(); full=b.fullmove_number; b.push(chess.Move.null()); b.fullmove_number=full; null_plies+=1
  else:
   m=chess.Move.from_uci(text); assert m in b.legal_moves; b.push(m); real_plies+=1
 assert b.fen(en_passant='xfen')==s['fen']
 assert len(s['path'])==s['ply'] and s['null_ancestors']==s['path'].count(None)
 assert s['polling_offset']==s['parent_nodes']-1 and int(s['sample_key'])&255==0
 assert s['restored'] and s['control_nodes']==1 and not s['control_stopped'] and s['control_score']==s['static_eval']
 assert (s['incoming_reduction']>0)==(s['call_kind']==3)
 assert 1<=s['depth']<=3 and s['beta']==s['alpha']+1 and not b.is_check()
 assert b.halfmove_clock+s['depth']<100 and s['static_eval']-150*s['depth']>=s['beta']
 assert any(b.pieces(t,b.turn) for t in (chess.KNIGHT,chess.BISHOP,chess.ROOK,chess.QUEEN))
complete=[s for s in samples if not s['shadow_stopped']]
assert len(samples)==result['samples'] and len(complete)==result['completed']
assert len(samples)-len(complete)==result['censored']
assert sum(s['shadow_score']<s['beta'] for s in complete)==result['contradictions']
for k,pred in [('reduced',lambda s:s['incoming_reduction']>0),('null_descendant',lambda s:s['null_ancestors']>0)]:
 assert sum(pred(s) for s in samples)==result[k+'_samples']
 assert sum(pred(s) and s['shadow_score']<s['beta'] for s in complete)==result[k+'_contradictions']
summary=dict(verified=True,roots=128,transcripts=384,samples=len(samples),completed=len(complete),censored=len(samples)-len(complete),cross_beta=sum(s['shadow_score']<s['beta'] for s in complete),sampled_roots=len({s['root_id'] for s in samples}),sampled_openings=len({by_id[s['root_id']]['opening_id'] for s in samples}),roots_at_cap=sum(x['totals']['samples']==8 for x in rows['observer']),both_samples=sum(s['incoming_reduction']>0 and s['null_ancestors']>0 for s in samples),null_context_roots=len({s['root_id'] for s in samples if s['null_ancestors']>0}),by_depth=dict(collections.Counter(s['depth'] for s in samples)),call_kinds=dict(collections.Counter(s['call_kind'] for s in samples)),samples_with_killers=sum(s['killer_slots']>0 for s in samples),real_plies_replayed=real_plies,null_edges_replayed=null_plies,reference_parent_nodes=sum(x['final_nodes'] for x in rows['reference']),observer_parent_nodes=sum(x['final_nodes'] for x in rows['observer']),max_parent_overshoot=max(x['final_nodes']-131072 for x in rows['observer']),max_probe_nodes=max(s['shadow_nodes'] for s in samples),hashes={name:sha(c/name) for name in ['result.json','samples.jsonl','frozen.jsonl','reference.jsonl','observer.jsonl']},affinity=list(os.sched_getaffinity(0)))
print(json.dumps(summary,indent=2))
