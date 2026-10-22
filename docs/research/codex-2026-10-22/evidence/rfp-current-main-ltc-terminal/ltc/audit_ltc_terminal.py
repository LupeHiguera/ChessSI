"""Audit the frozen updated-main RFP LTC terminal archive; never launch or accept a match."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra').resolve(strict=True)
RUN = ROOT / 'engines/rfp-current-main-ltc-validation'
EXPECTED = {
    'scripts/research/extract_result.py': 'a54c652046f74f0b8209d7fa66a00568a1f11a1af0ee0706025c877f52b9785c',
    'scripts/research/snapshot_run.py': 'e502f4982165c4e1833d66c97a9d521b55f2a23740f64765deef10a309e73991',
    'scripts/research/prepare_corpus.py': 'bca6c249dbe68ec127c09e749acf05b4e947dbf32ddbd1420322c7d6ed9578b3',
    'engines/qsearch-validation/audit_match.py': 'e67123fa57194ed4dc700a4614ec3a73fc2bf3a7b23f094e6485c2f284a1dac9',
}

PROVENANCE = {
    'launch-plan.json': 'cc230c37a70388f7249900cb72c3b1c40fcc208731ee07db91393e325330c6c5',
    'runner-identity.json': '461f577377a9681a558d4f16d324582f6ab6f93fadcf004078a89e772c58d5cf',
    'guard-attachment.json': 'dc47e739d3739b19366591571cc40fcd8ade8ccf61845fac8dac62b571bc80c1',
    'live-watch-01/plan.json': '8da101c8637ae9cb16a017c2742241b19748fe7a2439b1239a954b4718d73652',
}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

SUMMARY_FIELDS = (
    'pgn_games_legally_replayed', 'legal_plies', 'log_reports_checked',
    'log_report_count_mismatches', 'cross_source_game_results_compared',
    'log_games_not_in_pgn_snapshot', 'pgn_games_not_in_log_snapshot',
    'suspect_termination_reasons')


def replay_outcome(returncode, result_path, extraction):
    """Describe success or retained incomplete evidence without weakening replay."""
    outcome = {'status': 'replay_failed' if returncode else 'missing_result',
               'audit_exit_code': returncode, 'result_sha256': None,
               'collector_exit_code': 2, 'issues': []}
    if returncode:
        outcome['issues'].append('Independent replay exited with code ' + str(returncode))
    audit = None
    try:
        if not result_path.is_file():
            outcome['issues'].append('Independent replay produced no result.json')
            return None, outcome
        raw = result_path.read_bytes()
        outcome['result_sha256'] = hashlib.sha256(raw).hexdigest()
        audit = json.loads(raw)
        require(isinstance(audit, dict), 'Audit result is not an object')
        if returncode:
            return None, outcome  # A partial result cannot override a failed replay.
        require(audit['snapshot_manifest_sha256'] == extraction['manifest_sha256'], 'Audit manifest differs')
        require(audit['audited_artifact_sha256'] == {
            name: extraction['artifact_sha256'][name] for name in ('log', 'pgn', 'config')},
            'Audit artifact hashes differ')
        require(audit['input_bindings_rechecked'] is True, 'Audit did not recheck inputs')
        require(all(field in audit for field in SUMMARY_FIELDS), 'Audit result lacks required summary fields')
        outcome.update(status='succeeded', collector_exit_code=0)
        return audit, outcome
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        outcome['status'] = 'replay_failed' if returncode else 'invalid_result'
        outcome['issues'].append(type(error).__name__ + ': ' + str(error))
        return None, outcome

def main():
    require(sys.flags.optimize == 0, 'Python optimization is prohibited for audit')
    require(os.sched_getaffinity(0) == {19}, 'CPU 19 required')
    os.chdir(ROOT)
    for name, digest in EXPECTED.items():
        require(sha(ROOT / name) == digest, 'Audit implementation changed: ' + name)
    state_path = RUN / 'live-watch-01/state.json'
    state_bytes = state_path.read_bytes()
    state = json.loads(state_bytes)
    require(state.get('status') == 'archived' and state.get('process_terminal') is True,
            'Terminal guard archive is not ready; no output written')
    require(state['manager']['pid'] == 2739252 and state['manager']['start_ticks'] == '5479196',
            'Wrong manager identity')
    require(state.get('binary_drift') is False, 'Terminal binary drift')
    require(state['final_binary_hashes'] == {
        'candidate': 'b10c68c9870eb589b89ccab8d860cdeed91aeeddcff1618ecfa37aff35f6a6ab',
        'baseline': '819333c372d911c46c341091ed46f0872753b18d5dd39c094383139598e1f8da'},
        'Unexpected terminal binaries')
    provenance = {}
    for name, digest in PROVENANCE.items():
        raw = (RUN / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'LTC provenance changed: ' + name)
        provenance[name] = json.loads(raw)
    guard, attachment = provenance['live-watch-01/plan.json'], provenance['guard-attachment.json']
    for key in ('manager', 'boot_id', 'watcher_pid', 'watcher_affinity', 'started_utc', 'deadline_utc', 'script_sha256'):
        require(state[key] == guard[key], 'Terminal guard identity differs: ' + key)
    require(state['manager'] == attachment['manager'] and state['watcher_pid'] == attachment['watcher']['pid']
            and state['boot_id'] == attachment['boot_id'], 'Guard attachment identity differs')
    require(attachment['launch_plan_sha256'] == PROVENANCE['launch-plan.json']
            and attachment['runner_identity_sha256'] == PROVENANCE['runner-identity.json']
            and provenance['runner-identity.json']['launch_plan_sha256'] == PROVENANCE['launch-plan.json'],
            'LTC launcher/runner/guard bindings differ')
    require(state['deadline_utc'] == provenance['launch-plan.json']['deadline_utc'] == '2026-10-22T19:53:00+00:00',
            'LTC deadline differs')
    terminal_control_hashes = {name: sha(RUN / name) for name in ('runner-exit.json', 'guard-exit.json')
                              if (RUN / name).is_file()}
    archive = (RUN / 'live-watch-01/terminal-snapshot').resolve(strict=True)
    require(Path(state['archive']).resolve(strict=True) == archive, 'Unexpected archive path')
    for output in ('terminal-extraction.json', 'terminal-audit-01', 'terminal-audit-01.log',
                   'terminal-audit-binding.json'):
        require(not (RUN / output).exists() and not (RUN / output).is_symlink(), 'Refusing to overwrite ' + output)
    sys.path.insert(0, str(ROOT / 'scripts/research'))
    import extract_result
    result = extract_result.inspect_snapshot(archive, state_path)
    require(result['integrity']['integrity_ok'], 'Terminal archive integrity failed')
    # Unresolved/interrupt status is preserved. A legal replay can still inform an Inconclusive handoff.
    write_new(RUN / 'terminal-extraction.json', result)
    print(json.dumps({'evidence_status': result['evidence_status'],
                      'reported_hypothesis': result.get('log_evidence', {}).get('reported_hypothesis'),
                      'issues': result['issues']}), flush=True)
    environment = dict(os.environ, PYTHONPATH=str(ROOT / 'engines/dependencies/python-chess'))
    with (RUN / 'terminal-audit-01.log').open('x', encoding='utf-8') as stream:
        replay = subprocess.run([sys.executable, '-B', 'engines/qsearch-validation/audit_match.py',
                        '--snapshot', str(archive), '--output', str(RUN / 'terminal-audit-01')],
                       cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False)
    audit_path = RUN / 'terminal-audit-01/result.json'
    audit, outcome = replay_outcome(replay.returncode, audit_path, result)
    require(state_path.read_bytes() == state_bytes, 'Terminal state changed during audit')
    for name, digest in EXPECTED.items():
        require(sha(ROOT / name) == digest, 'Audit implementation changed during replay: ' + name)
    for name, digest in {**PROVENANCE, **terminal_control_hashes}.items():
        require(sha(RUN / name) == digest, 'LTC provenance/control record changed during audit: ' + name)
    if outcome['result_sha256'] is not None:
        require(sha(audit_path) == outcome['result_sha256'], 'Audit result changed during final binding checks')
    binding = {'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'collector_sha256': sha(Path(__file__)), 'implementation_sha256': EXPECTED,
               'launch_guard_provenance_sha256': PROVENANCE, 'terminal_control_sha256': terminal_control_hashes,
               'terminal_state_sha256': hashlib.sha256(state_bytes).hexdigest(),
               'extraction_sha256': sha(RUN / 'terminal-extraction.json'),
               'audit_status': outcome['status'], 'audit_exit_code': outcome['audit_exit_code'],
               'audit_issues': outcome['issues'], 'collector_exit_code': outcome['collector_exit_code'],
               'audit_log_sha256': sha(RUN / 'terminal-audit-01.log'),
               'audit_result_sha256': outcome['result_sha256'],
               'audit_result_scope': 'Validated replay result' if outcome['status'] == 'succeeded' else 'Unvalidated partial result or absent',
               'benchmark_result': 'not_assigned',
               'scope': 'Bound LTC extraction and independent replay; interrupted/unresolved evidence is retained; no result promotion or launch'}
    write_new(RUN / 'terminal-audit-binding.json', binding)
    if audit is not None:
        print(json.dumps({key: audit[key] for key in SUMMARY_FIELDS}, indent=2), flush=True)
    else:
        print(json.dumps(outcome, indent=2), flush=True)
    return outcome['collector_exit_code']

if __name__ == '__main__':
    raise SystemExit(main())