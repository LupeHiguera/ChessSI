import difflib, hashlib, json, shutil
from pathlib import Path
root = Path.cwd()
doc = root / 'docs/research/rejected-nnue-2026-10-25'
out = root / 'engines/rejected-nnue-audit'
evidence = doc / 'evidence'
for name in ('manifest.json','summary.json','commands.jsonl'):
    shutil.copy2(out / name, evidence / ('summary-run-v1.json' if name == 'summary.json' else name))
for path in sorted(out.glob('*.stdout')) + sorted(out.glob('*.stderr')):
    shutil.copy2(path, evidence / path.name)
summary = json.loads((out/'summary.json').read_text())
summary['datagen']['sample_rows'] = summary['datagen'].pop('rows')
rows=[]
for line in (out/'instrumented-datagen.stderr').read_text().splitlines():
    if line.startswith('REJECT_AUDIT '):
        c,t,l,m,u,o=map(int,line.split()[1:])
        rows.append(dict(parent_in_check=c,move_type=['normal','promotion','en_passant','castling'][t],legal=l,moves=m,updates=u,lane_ops=o))
assert len(rows)==16
assert sum(r['updates'] for r in rows)==summary['datagen']['attempted_updates']
assert sum(r['updates'] for r in rows if not r['legal'])==summary['datagen']['rejected_updates']
summary['datagen']['rows']=rows
summary['reporting_correction']='The original summary reused rows for sample count, replacing the datagen bucket list. Restored the list from archived stderr, named the count sample_rows. No measurement rerun or changed total.'
(evidence/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
a=(root/'src/position.cpp').read_text().splitlines(keepends=True)
b=(out/'instrumented/src/position.cpp').read_text().splitlines(keepends=True)
(evidence/'instrumentation.diff').write_text(''.join(difflib.unified_diff(a,b,fromfile='src/position.cpp',tofile='instrumented/src/position.cpp')))
hashes={str(p.relative_to(doc)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(doc.rglob('*')) if p.is_file() and p.name!='artifact-hashes.json'}
(evidence/'artifact-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
for label, data in [('bench7',summary['bench'][0]),('bench11',summary['bench'][1]),('datagen',summary['datagen'])]:
    rejected_check=sum(r['updates'] for r in data['rows'] if r['parent_in_check'] and not r['legal'])
    print(json.dumps(dict(workload=label,updates=data['attempted_updates'],rejected=data['rejected_updates'],fraction=data['rejected_fraction'],arithmetic_fraction=data['rejected_lane_ops_fraction'],rejected_while_in_check=rejected_check,check_share=rejected_check/data['rejected_updates'])))
print('datagen_rows',summary['datagen']['sample_rows'])
