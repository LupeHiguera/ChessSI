"""Audit the frozen updated-main RFP terminal archive; never launch or accept a match."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra').resolve(strict=True)
RUN = ROOT / 'engines/rfp-current-main-validation'
EXPECTED = {
    'scripts/research/extract_result.py': 'a54c652046f74f0b8209d7fa66a00568a1f11a1af0ee0706025c877f52b9785c',
    'scripts/research/snapshot_run.py': 'e502f4982165c4e1833d66c97a9d521b55f2a23740f64765deef10a309e73991',
    'scripts/research/prepare_corpus.py': 'bca6c249dbe68ec127c09e749acf05b4e947dbf32ddbd1420322c7d6ed9578b3',
    'engines/qsearch-validation/audit_match.py': 'e67123fa57194ed4dc700a4614ec3a73fc2bf3a7b23f094e6485c2f284a1dac9',
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
    require(state['manager']['pid'] == 2319846 and state['manager']['start_ticks'] == '4928613',
            'Wrong manager identity')
    require(state.get('binary_drift') is False, 'Terminal binary drift')
    require(state['final_binary_hashes'] == {
        'candidate': 'b10c68c9870eb589b89ccab8d860cdeed91aeeddcff1618ecfa37aff35f6a6ab',
        'baseline': '819333c372d911c46c341091ed46f0872753b18d5dd39c094383139598e1f8da'},
        'Unexpected terminal binaries')
    archive = (RUN / 'live-watch-01/terminal-snapshot').resolve(strict=True)
    require(Path(state['archive']).resolve(strict=True) == archive, 'Unexpected archive path')
    for output in ('terminal-extraction.json', 'terminal-audit-01', 'terminal-audit-01.log',
                   'terminal-audit-binding.json'):
        require(not (RUN / output).exists(), 'Refusing to overwrite ' + output)
    sys.path.insert(0, str(ROOT / 'scripts/research'))
    import extract_result
    result = extract_result.inspect_snapshot(archive, state_path)
    require(result['integrity']['integrity_ok'], 'Terminal archive integrity failed')
    # Unresolved/interrupt status is preserved. A legal replay can still inform an Inconclusive handoff.
    write_new(RUN / 'terminal-extraction.json', result)
    print(json.dumps({'evidence_status': result['evidence_status'],
                      'reported_hypothesis': result['log_evidence']['reported_hypothesis'],
                      'issues': result['issues']}), flush=True)
    environment = dict(os.environ, PYTHONPATH=str(ROOT / 'engines/dependencies/python-chess'))
    with (RUN / 'terminal-audit-01.log').open('x', encoding='utf-8') as stream:
        subprocess.run([sys.executable, '-B', 'engines/qsearch-validation/audit_match.py',
                        '--snapshot', str(archive), '--output', str(RUN / 'terminal-audit-01')],
                       cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=True)
    audit = json.loads((RUN / 'terminal-audit-01/result.json').read_text())
    require(audit['snapshot_manifest_sha256'] == result['manifest_sha256'], 'Audit manifest differs')
    require(audit['audited_artifact_sha256'] == {
        name: result['artifact_sha256'][name] for name in ('log', 'pgn', 'config')},
        'Audit artifact hashes differ')
    require(audit['input_bindings_rechecked'] is True, 'Audit did not recheck inputs')
    require(state_path.read_bytes() == state_bytes, 'Terminal state changed during audit')
    for name, digest in EXPECTED.items():
        require(sha(ROOT / name) == digest, 'Audit implementation changed during replay: ' + name)
    binding = {'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'collector_sha256': sha(Path(__file__)), 'implementation_sha256': EXPECTED,
               'terminal_state_sha256': hashlib.sha256(state_bytes).hexdigest(),
               'extraction_sha256': sha(RUN / 'terminal-extraction.json'),
               'audit_result_sha256': sha(RUN / 'terminal-audit-01/result.json'),
               'benchmark_result': 'not_assigned',
               'scope': 'Bound extraction and independent replay; no protocol promotion or LTC launch'}
    write_new(RUN / 'terminal-audit-binding.json', binding)
    print(json.dumps({key: audit[key] for key in (
        'pgn_games_legally_replayed', 'legal_plies', 'log_reports_checked',
        'log_report_count_mismatches', 'cross_source_game_results_compared',
        'log_games_not_in_pgn_snapshot', 'pgn_games_not_in_log_snapshot',
        'suspect_termination_reasons')}, indent=2), flush=True)

if __name__ == '__main__':
    main()