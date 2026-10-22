import datetime as dt, hashlib, json, os
from pathlib import Path
if os.sched_getaffinity(0)!={19}:raise RuntimeError('CPU 19 required')
run=Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra/engines/rfp-current-main-validation/first-pawn-preparation-01/run-01')
out=run/'peer-verification-01'
rows=[json.loads(x) for x in (run/'progress.jsonl').read_text().splitlines()]
labels=['release','sanitizer','witness-build','witness-oracle','validation-bench','warmup-reference','warmup-variant']
for pair in range(6):
    for name in (['reference','variant'] if pair%2==0 else ['variant','reference']):
        labels.extend(f'timing-{pair}-{name}-{i:02}' for i in range(32))
if [r['command'] for r in rows]!=labels:raise ValueError('Actual command order mismatch')
for previous,current in zip(rows,rows[1:]):
    if dt.datetime.fromisoformat(previous['finished_utc'])>dt.datetime.fromisoformat(current['started_utc']):
        raise ValueError('Commands overlap or timestamps are not ordered')
result={'status':'passed','actual_command_order_verified':len(rows),
 'six_alternating_pairs_with_32_contiguous_invocations_per_binary':True,
 'all_command_utc_intervals_nonoverlapping_and_ordered':True,'new_engine_queries':0,
 'progress_sha256':hashlib.sha256((run/'progress.jsonl').read_bytes()).hexdigest(),
 'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(out/'execution-order-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
