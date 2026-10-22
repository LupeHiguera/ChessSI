"""Publish a selected, bound LTC evidence subset only after explicit terminal audit."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra')
RUN = ROOT / 'engines/rfp-current-main-ltc-validation'
STC = ROOT / 'engines/rfp-current-main-validation'
DEST = ROOT / 'engines/research-worktree/docs/research/codex-2026-10-22/evidence/rfp-current-main-ltc-terminal'
COLLECTOR = STC / 'ltc-preparation-01/audit_ltc_terminal.py'
COLLECTOR_SHA = 'f41e03be1f2e07fa88bcba0c1a1109a14e5997a7185b7ebcbbe5fe4f663c9a4f'
REPRODUCTION_SHA = 'c4f986d61018da38400c290b216402767511585cbb0fa10b1b9f1ef70b1534e6'
PROVENANCE = {
    'launch-plan.json': 'cc230c37a70388f7249900cb72c3b1c40fcc208731ee07db91393e325330c6c5',
    'runner-identity.json': '461f577377a9681a558d4f16d324582f6ab6f93fadcf004078a89e772c58d5cf',
    'guard-attachment.json': 'dc47e739d3739b19366591571cc40fcd8ade8ccf61845fac8dac62b571bc80c1',
    'live-watch-01/plan.json': '8da101c8637ae9cb16a017c2742241b19748fe7a2439b1239a954b4718d73652',
}
IMPLEMENTATIONS = {
    'scripts/research/extract_result.py': 'a54c652046f74f0b8209d7fa66a00568a1f11a1af0ee0706025c877f52b9785c',
    'scripts/research/snapshot_run.py': 'e502f4982165c4e1833d66c97a9d521b55f2a23740f64765deef10a309e73991',
    'scripts/research/prepare_corpus.py': 'bca6c249dbe68ec127c09e749acf05b4e947dbf32ddbd1420322c7d6ed9578b3',
    'engines/qsearch-validation/audit_match.py': 'e67123fa57194ed4dc700a4614ec3a73fc2bf3a7b23f094e6485c2f284a1dac9',
}
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def safe(path, exists=True):
    require(path.is_absolute() and path.is_relative_to(ROOT), 'Path outside Astra: ' + str(path))
    require(path.resolve(strict=exists) == path, 'Redirected/noncanonical path: ' + str(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink: ' + str(path))
    return path

def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()

def prepare():
    require(sys.flags.optimize == 0 and os.sched_getaffinity(0) == {19}, 'Unoptimized Python on CPU19 required')
    require(not DEST.exists() and not DEST.is_symlink(), 'Destination already exists')
    safe(DEST.parent)
    safe(DEST, exists=False)
    observed, copies, absent = {}, {}, []
    def read(path, expected=None):
        safe(path)
        require(path.is_file() and path.stat().st_size <= MAX_FILE, 'Missing/oversize record: ' + str(path))
        raw = path.read_bytes()
        require(len(raw) <= MAX_FILE, 'Record grew beyond size bound')
        if expected is not None:
            require(digest(raw) == expected, 'Record hash differs: ' + str(path))
        if path in observed:
            require(observed[path] == raw, 'Record changed during preparation: ' + str(path))
        observed[path] = raw
        return raw
    def add(name, path, expected=None):
        require(name not in copies and not Path(name).is_absolute() and '..' not in Path(name).parts, 'Duplicate/unsafe bundle name')
        copies[name] = (path, read(path, expected))
        return copies[name][1]
    state_raw = read(RUN / 'live-watch-01/state.json')
    state = json.loads(state_raw)
    require(state.get('status') == 'archived' and state.get('process_terminal') is True,
            'Refusing publication: actual terminal guard archive is not ready')
    binding_raw = read(RUN / 'terminal-audit-binding.json')
    binding = json.loads(binding_raw)
    require(binding['collector_sha256'] == COLLECTOR_SHA, 'Collector identity differs')
    require(binding['implementation_sha256'] == IMPLEMENTATIONS, 'Audit helper identities differ')
    require(binding['launch_guard_provenance_sha256'] == PROVENANCE, 'Frozen launch/guard bindings differ')
    require(binding['terminal_state_sha256'] == digest(state_raw), 'Terminal state binding differs')
    require(binding['benchmark_result'] == 'not_assigned', 'Unexpected benchmark assignment')
    require(binding['audit_status'] in ('succeeded', 'replay_failed', 'missing_result', 'invalid_result'), 'Unknown audit status')
    succeeded = binding['audit_status'] == 'succeeded'
    require(binding['collector_exit_code'] == (0 if succeeded else 2), 'Audit completion code differs')
    require(not succeeded or (binding['audit_exit_code'] == 0 and not binding['audit_issues']), 'Inconsistent successful replay')
    provenance = {}
    for name, expected in PROVENANCE.items():
        target = 'ltc/guard-plan.json' if name.startswith('live-watch-01/') else 'ltc/' + name
        provenance[name] = json.loads(add(target, RUN / name, expected))
    plan, guard = provenance['launch-plan.json'], provenance['live-watch-01/plan.json']
    attachment = provenance['guard-attachment.json']
    for key in ('manager', 'boot_id', 'watcher_pid', 'watcher_affinity', 'started_utc', 'deadline_utc', 'script_sha256'):
        require(state[key] == guard[key], 'Terminal guard identity differs: ' + key)
    require(state['manager'] == attachment['manager'] and state['watcher_pid'] == attachment['watcher']['pid'], 'Attachment identity differs')
    require(state['manager']['pid'] == 2739252 and state['manager']['start_ticks'] == '5479196', 'Wrong LTC manager')
    require(state['binary_drift'] is False and state['final_binary_hashes'] == {
        'candidate': plan['candidate_binary_sha256'], 'baseline': plan['expected_baseline_binary_sha256']}, 'Terminal binary identity differs')
    archive = RUN / 'live-watch-01/terminal-snapshot'
    require(Path(state['archive']) == archive, 'Unexpected terminal archive')
    safe(archive)
    manifest_raw = add('ltc/terminal-manifest.json', archive / 'manifest.json')
    manifest_sha = digest(manifest_raw)
    require(add('ltc/terminal-manifest.sha256', archive / 'manifest.sha256').decode().split()[0] == manifest_sha, 'Snapshot manifest digest differs')
    snapshot = json.loads(manifest_raw)
    extraction = json.loads(add('ltc/terminal-extraction.json', RUN / 'terminal-extraction.json', binding['extraction_sha256']))
    require(extraction['integrity']['integrity_ok'] is True and extraction['manifest_sha256'] == manifest_sha, 'Extraction integrity/manifest differs')
    add('ltc/terminal-state.json', RUN / 'live-watch-01/state.json', binding['terminal_state_sha256'])
    add('ltc/terminal-audit-binding.json', RUN / 'terminal-audit-binding.json', digest(binding_raw))
    add('ltc/terminal-audit.log', RUN / 'terminal-audit-01.log', binding['audit_log_sha256'])
    add('ltc/audit_ltc_terminal.py', COLLECTOR, COLLECTOR_SHA)
    for name, expected in IMPLEMENTATIONS.items():
        read(ROOT / name, expected)
    add('ltc/audit_match.py', ROOT / 'engines/qsearch-validation/audit_match.py', IMPLEMENTATIONS['engines/qsearch-validation/audit_match.py'])
    audited_source = RUN / 'terminal-audit-01/audit_match.py'
    if audited_source.exists() or audited_source.is_symlink():
        read(audited_source, IMPLEMENTATIONS['engines/qsearch-validation/audit_match.py'])
    role_hashes = {}
    copied_archive_paths = set()
    for role in ('log', 'config', 'pgn'):
        matches = [item for item in snapshot['artifacts'] if item['role'] == role]
        require(len(matches) == 1, 'Ambiguous/missing terminal role: ' + role)
        item = matches[0]
        require(item['status'] == 'ok' and item['archive_path'], 'Incomplete terminal artifact: ' + role)
        require(item['sha256'] == extraction['artifact_sha256'][role], 'Extraction role binding differs: ' + role)
        role_hashes[role] = item['sha256']
        if role != 'pgn':
            path = archive / item['archive_path']
            require(path.is_relative_to(archive), 'Archive path escapes')
            raw = add('ltc/terminal.log' if role == 'log' else 'ltc/terminal-config.json', path, item['sha256'])
            require(len(raw) == item['bytes_hashed'], 'Terminal artifact size differs')
            copied_archive_paths.add(item['archive_path'])
    audit_path = RUN / 'terminal-audit-01/result.json'
    audit = None
    if binding['audit_result_sha256'] is not None:
        raw = add('ltc/audit-result.json', audit_path, binding['audit_result_sha256'])
        try:
            audit = json.loads(raw)
        except (ValueError, UnicodeError):
            require(not succeeded, 'Malformed successful audit result')
    else:
        require(not audit_path.exists() and not audit_path.is_symlink() and not succeeded, 'Unexpected/missing audit result')
        absent.append(audit_path)
    if succeeded:
        require(isinstance(audit, dict) and audit['snapshot_manifest_sha256'] == manifest_sha, 'Successful audit manifest differs')
        require(audit['audited_artifact_sha256'] == role_hashes and audit['input_bindings_rechecked'] is True, 'Successful replay bindings differ')
    optional = {'ltc/audit-reports.json': RUN / 'terminal-audit-01/reports.json',
                'ltc/runner-exit.json': RUN / 'runner-exit.json', 'ltc/guard-exit.json': RUN / 'guard-exit.json'}
    for name, path in optional.items():
        expected = binding['terminal_control_sha256'].get(path.name)
        if path.exists() or path.is_symlink():
            add(name, path, expected)
        else:
            require(expected is None, 'Collector-bound control record disappeared')
            absent.append(path)
    reproduction_path = STC / 'candidate-review-preparation-01/run-01/result.json'
    reproduction = json.loads(add('reproduction/result.json', reproduction_path, REPRODUCTION_SHA))
    require(reproduction['source_files_sha256'] == plan['source_files_sha256'] and reproduction['candidate_binary_sha256'] == plan['candidate_binary_sha256'], 'Candidate reproduction differs')
    add('package_terminal.py', Path(__file__).resolve())
    omitted = []
    for item in snapshot['artifacts']:
        if item.get('archive_path') in copied_archive_paths:
            continue
        omitted.append({'role': item['role'], 'archive_path': str(archive / item['archive_path']) if item.get('archive_path') else None,
            'original_source_path': item['source_path'], 'bytes': item.get('bytes_hashed'), 'sha256': item.get('sha256'),
            'hash_scope': item.get('hash_scope'), 'status': item.get('status'), 'identity_source': 'ltc/terminal-manifest.json',
            'verification': 'Recorded snapshot identity; not rehashed or recopied by this packaging'})
    omitted.append({'role': 'opening_book', 'configured_path': plan['environment']['BOOK'], 'bytes': None,
        'sha256': plan['book_sha256'], 'identity_source': 'ltc/launch-plan.json',
        'verification': 'Declared frozen launch hash; no book read or historical loaded-bytes attestation during packaging'})
    dependencies = {name: {'path': str(ROOT / name), 'sha256': sha} for name, sha in IMPLEMENTATIONS.items()
                    if not name.endswith('/audit_match.py')}
    if isinstance(audit, dict):
        dependencies.update({name: value for name, value in audit.get('implementation_sources', {}).items()
                             if isinstance(value, dict) and value.get('path') != str(ROOT / 'engines/qsearch-validation/audit_match.py')})
    local = {'schema_version': 1, 'scope': 'Omitted local material; recorded identities are not fresh verification',
        'artifacts': omitted, 'implementation_dependencies': dependencies,
        'dependency_scope': 'Helper pins from collector binding; optional audit implementation records are unvalidated if replay failed',
        'other_local_outputs': {'path': str(RUN / 'terminal-audit-01'), 'description': 'Additional replay intermediates, including any pgn-games.json, are omitted'},
        'reproduction_logs': [{'path': str(reproduction_path.parent / (command['name'] + '.' + stream)),
                              'sha256': command[stream + '_sha256']} for command in reproduction['commands'] for stream in ('stdout', 'stderr')]}
    readme = """# Updated-main RFP LTC terminal evidence subset

This selected subset preserves exact recorded evidence for the independent `60+0.6` RFP comparison against accepted main `f801f8c519b0fe5b3d009b8f0664b049409a1188`. The launch used candidate/base bench signatures `609035` / `864538`, five concurrent games on WSL CPUs 14-19, Hash 16 and Threads 1, and the fixed 2026-10-22 19:53 UTC deadline. It contains no first-pawn optimization.

The collector records replay status **`AUDIT_STATUS`** and collector exit **`COLLECTOR_EXIT`**. This is the replay-completion status, not a match verdict. Read the unchanged extraction, guard state, replay log and audit binding together. An unsuccessful replay may leave an absent, malformed or partial result/report; copied failure artifacts remain unvalidated. A terminal process or `Finished match` does not supply an SPRT hypothesis. Interrupted or unresolved evidence stays unresolved. `benchmark_result` remains `not_assigned`; this packager assigns no Passed/Failed decision or repository acceptance.

**This is a selected evidence subset, not a standalone full-replay package.** PGN, engine/manager binaries, book, full source archives, dependency implementations and intermediate game records remain local. `local-artifacts.json` identifies omitted snapshot artifacts with their recorded paths, sizes, hash scopes and digests, plus declared book and dependency identities. Omitted bytes are not rehashed during packaging. Book provenance is a recorded configured path and declared digest, not proof of bytes historically loaded by the manager.

`ltc/` contains launch/runner/guard provenance, terminal state and original snapshot manifest/digest, extraction, audit binding/log, exact collector/auditor source and frozen terminal log/config. Audit result/reports and runner/guard exits are included only when present. Exit records that appeared after collection are newly hash-bound by this bundle, not retrospectively by the collector. `reproduction/result.json` is the later clean-candidate reproduction result; its 21 inputs and binary match the launch plan. It is not a retrospective launch commit or another strength test.

`manifest.json` inventories each copied/generated file, byte count, SHA-256 and original source path; `manifest.sha256` binds it. JSON, logs and source copies retain their original bytes and local paths. Archived Python scripts have local path dependencies and are not portable replay tools. Generated README/inventory files are marked separately. No engine query, build, game or legal-replay rerun creates this bundle. The bundle makes no novelty or AGI claim and does not pool separate STC/LTC results. See the [research record](../../rfp.md).
""".replace('AUDIT_STATUS', binding['audit_status']).replace('COLLECTOR_EXIT', str(binding['collector_exit_code']))
    generated = {'README.md': readme.encode(), 'local-artifacts.json': encoded(local)}
    require(sum(len(raw) for _, raw in copies.values()) + sum(map(len, generated.values())) <= MAX_TOTAL, 'Selected bundle exceeds bound; no truncation performed')
    return copies, generated, observed, absent, binding

def main():
    require(sys.argv[1:] in (['--check-only'], ['--write']), 'Use --check-only or explicitly authorized --write')
    copies, generated, observed, absent, binding = prepare()
    for path, raw in observed.items():
        safe(path)
        require(path.read_bytes() == raw, 'Source changed before publication: ' + str(path))
    for path in absent:
        require(not path.exists() and not path.is_symlink(), 'Optional record appeared; retry clean preparation')
    summary = {'destination': str(DEST), 'exact_copies': len(copies), 'generated_files': len(generated),
               'audit_status': binding['audit_status'], 'benchmark_result': 'not_assigned', 'write_requested': sys.argv[1] == '--write'}
    if sys.argv[1] == '--check-only':
        print(json.dumps(summary, indent=2))
        return
    safe(DEST.parent)
    safe(DEST, exists=False)
    DEST.mkdir(exist_ok=False)
    entries = []
    for name, (source, raw) in copies.items():
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        safe(target, exists=False)
        with target.open('xb') as stream:
            stream.write(raw)
        require(target.read_bytes() == raw, 'Copied bytes differ: ' + name)
        entries.append({'path': name, 'kind': 'exact_byte_copy', 'bytes': len(raw), 'sha256': digest(raw), 'source_path': str(source)})
    for name, raw in generated.items():
        with (DEST / name).open('xb') as stream:
            stream.write(raw)
        entries.append({'path': name, 'kind': 'generated_bundle_document', 'bytes': len(raw), 'sha256': digest(raw), 'source_path': None})
    for path, raw in observed.items():
        require(safe(path).read_bytes() == raw, 'Source changed during packaging; preserve incomplete bundle: ' + str(path))
    for entry in entries:
        require(digest((DEST / entry['path']).read_bytes()) == entry['sha256'], 'Bundle hash differs')
    manifest = {'schema_version': 1, 'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'scope': 'Selected exact terminal evidence; no new statistical interpretation or benchmark acceptance',
                'copied_files': len(copies), 'audit_status': binding['audit_status'], 'benchmark_result': 'not_assigned', 'files': entries}
    raw = encoded(manifest)
    with (DEST / 'manifest.json').open('xb') as stream:
        stream.write(raw)
    with (DEST / 'manifest.sha256').open('x') as stream:
        stream.write(digest(raw) + '\n')
    summary.update(manifest_sha256=digest(raw), total_files=len(entries) + 2)
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()