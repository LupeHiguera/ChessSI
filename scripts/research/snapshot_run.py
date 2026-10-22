#!/usr/bin/env python3
"""Read-only, bounded snapshots of chess runs; no engines or Git are executed.

Capture writes a new archive and never reuses it. Verification checks archived
bytes, not the current source files. This tool deliberately does not calculate
Elo or infer a final experiment decision from a live or mixed-session PGN.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

CHUNK = 64 * 1024
SCHEMA_VERSION = 1
DEFAULT_READ_LIMIT = 64 * 1024 * 1024
DEFAULT_COPY_LIMIT = 16 * 1024 * 1024
TAG = re.compile(r'^\[([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\]$')
# This is a structural PGN scanner, not a chess legality checker. Comments and
# recursive annotation variations cannot contribute top-level result tokens.
TOKENS = re.compile(r'\{[^}]*\}|\{[\s\S]*\Z|;[^\r\n]*|\[[^\]\r\n]*\]|\(|\)|[^\s\[\]{}();]+')
RESULTS = {'1-0', '0-1', '1/2-1/2', '*'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_stat(value):
    return {'device': value.st_dev, 'inode': str(value.st_ino),
            'size': value.st_size, 'mtime_ns': str(value.st_mtime_ns),
            'ctime_ns': str(value.st_ctime_ns)}


def same_identity(left, right):
    return (left['device'], left['inode']) == (right['device'], right['inode'])


def read_prefix(handle, destination, limit):
    """Hash exactly at most limit bytes, even when the source keeps growing."""
    digest = hashlib.sha256()
    count = 0
    while count < limit:
        block = handle.read(min(CHUNK, limit - count))
        if not block:
            break
        digest.update(block)
        count += len(block)
        if destination is not None:
            destination.write(block)
    return digest.hexdigest(), count


def sha256_file(path):
    with open(path, 'rb') as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
        return digest.hexdigest()


def finding(code, message, artifact=None):
    result = {'code': code, 'message': message}
    if artifact is not None:
        result['artifact'] = artifact
    return result


def capture_file(path, role, output, index, copy_limit, read_limit):
    # Do not resolve /proc/PID/exe: the symlink can name a deleted inode which
    # remains readable through procfs even though its textual target is gone.
    path = Path(os.path.abspath(path))
    entry = {'role': role, 'source_path': str(path), 'archive_path': None,
             'sha256': None, 'hash_scope': None, 'bytes_hashed': 0,
             'captured_utc': utc_now(), 'status': 'read_error', 'findings': []}
    destination = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'rb') as source:
            before_raw = os.fstat(source.fileno())
            if not stat.S_ISREG(before_raw.st_mode):
                raise ValueError('Input is not a regular file')
            before = file_stat(before_raw)
            entry['source_stat_before'] = before
            wanted = min(before['size'], read_limit)
            if wanted <= copy_limit:
                filename = re.sub(r'[^A-Za-z0-9_.-]', '_', path.name)[:90]
                relative = Path('files') / ('%04d-%s' % (index, filename))
                destination = open(output / relative, 'xb')
                entry['archive_path'] = relative.as_posix()
            entry['sha256'], count = read_prefix(source, destination, wanted)
            entry['bytes_hashed'] = count
            after = file_stat(os.fstat(source.fileno()))
            entry['source_stat_after_handle'] = after
        if destination is not None:
            destination.close()
            destination = None
        entry['hash_scope'] = ('initial_file' if count == before['size'] else 'prefix')
        entry['status'] = 'ok' if count == wanted else 'short_read'
        if count < wanted:
            entry['findings'].append('SOURCE_TRUNCATED_DURING_READ')
        if before['size'] > read_limit:
            entry['findings'].append('READ_LIMIT_REACHED')
        if before != after:
            entry['findings'].append('SOURCE_CHANGED_DURING_READ')
        try:
            final = file_stat(path.stat())
            entry['source_stat_after_path'] = final
            if not same_identity(before, final):
                entry['findings'].append('SOURCE_PATH_REPLACED')
            elif final != after:
                entry['findings'].append('SOURCE_CHANGED_AFTER_READ')
        except OSError as error:
            entry['findings'].append('SOURCE_PATH_UNAVAILABLE_AFTER_READ')
            entry['path_error'] = type(error).__name__ + ': ' + str(error)
    except (OSError, ValueError) as error:
        entry['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if destination is not None:
            destination.close()
        entry['finished_utc'] = utc_now()
    return entry


def parse_config(text):
    config = json.loads(text)
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a JSON object')
    seed = config.get('seed')
    if seed is not None and (isinstance(seed, bool) or
                            not isinstance(seed, (int, str)) or
                            not re.fullmatch(r'[0-9]+', str(seed))):
        raise ValueError('Seed must be an exact nonnegative integer or decimal string')
    return {'seed_decimal': None if seed is None else str(seed),
            'sprt': config.get('sprt'), 'concurrency': config.get('concurrency'),
            'games_per_round': config.get('games'), 'rounds': config.get('rounds'),
            'opening': config.get('opening'), 'engines': config.get('engines'),
            'resign': config.get('resign'), 'draw': config.get('draw'),
            'pgn': config.get('pgn'), 'recover': config.get('recover'),
            'stats_observed': config.get('stats')}


def inspect_pgn(text):
    """Only structural counts. No WDL/Elo claims, no assumption of file adjacency."""
    records, headers = [], {}
    variation = 0
    started_moves = False
    incomplete = 0
    unclosed = False
    for match in TOKENS.finditer(text):
        token = match.group(0)
        if token.startswith('{'):
            unclosed |= not token.endswith('}')
            continue
        if token.startswith(';'):
            continue
        if token == '(':
            variation += 1
            continue
        if token == ')':
            variation = max(0, variation - 1)
            continue
        if variation:
            continue
        tag = TAG.fullmatch(token)
        if tag:
            if started_moves or (tag.group(1) == 'Event' and 'Event' in headers):
                incomplete += 1
                headers = {}
                started_moves = False
            headers[tag.group(1)] = tag.group(2)
        elif token in RESULTS:
            if token == '*':
                incomplete += 1
            else:
                records.append({**headers, 'movetext_result': token})
            headers = {}
            started_moves = False
        else:
            started_moves = True
    incomplete += int(bool(headers or started_moves or variation or unclosed))
    keys, rounds = {}, {}
    for game in records:
        key = (game.get('Round'), game.get('White'), game.get('Black'))
        if all(key):
            keys[key] = keys.get(key, 0) + 1
        round_key = (game.get('Event'), game.get('Round'), game.get('FEN'),
                     game.get('TimeControl'))
        rounds.setdefault(round_key, []).append(game)
    duplicates = sum(count - 1 for count in keys.values() if count > 1)
    paired = 0
    for group in rounds.values():
        if (len(group) == 2 and group[0].get('Round') is not None and
                group[0].get('White') and group[0].get('Black') and
                group[0].get('White') != group[0].get('Black') and
                group[0].get('White') == group[1].get('Black') and
                group[0].get('Black') == group[1].get('White')):
            paired += 1
    findings = []
    if duplicates:
        findings.append('PGN_POSSIBLE_MULTIPLE_SESSIONS')
    if incomplete:
        findings.append('PGN_INCOMPLETE_GAMES_OR_TAIL')
    times = [game['GameStartTime'] for game in records if 'GameStartTime' in game]
    return {'completed_games_observed': len(records), 'incomplete_records_observed': incomplete,
            'structurally_paired_rounds': paired, 'duplicate_game_keys': duplicates,
            'first_observed_start': times[0] if times else None,
            'last_observed_start': times[-1] if times else None,
            'segmentation': 'ambiguous' if duplicates else 'not_verified',
            'statistics_eligible': False, 'findings': findings}


def read_process_stat(path):
    text = path.read_text(encoding='utf-8')
    left, right = text.find('('), text.rfind(')')
    fields = text[right + 1:].split()
    if left < 0 or right < left or len(fields) <= 19:
        raise ValueError('Malformed process stat')
    return {'comm': text[left + 1:right], 'ppid': int(fields[1]),
            'start_ticks_decimal': fields[19]}


def capture_process(pid, proc_root, add_artifact):
    folder = Path(proc_root) / str(pid)
    result = {'pid': pid, 'observed_utc': utc_now(), 'status': 'unavailable'}
    try:
        before = read_process_stat(folder / 'stat')
        result.update(before)
        result['executable_target'] = os.readlink(folder / 'exe')
        result['cwd'] = os.readlink(folder / 'cwd')
        status_text = (folder / 'status').read_text(encoding='utf-8')
        result['guest_cpu_list'] = next((line.split(':', 1)[1].strip()
                                        for line in status_text.splitlines()
                                        if line.startswith('Cpus_allowed_list:')), None)
        entry = add_artifact(folder / 'exe', 'process_executable:%d' % pid)
        result['executable_artifact'] = entry['index']
        after = read_process_stat(folder / 'stat')
        result['status'] = ('observed' if before == after else 'identity_changed')
        if before != after:
            result['finding'] = 'PROCESS_IDENTITY_CHANGED'
    except (OSError, ValueError) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    return result


def selected_sources(root, explicit):
    if explicit is None:
        names = ['Makefile', 'tests/perft.epd']
        names += [str(path.relative_to(root)) for pattern in ('*.cpp', '*.h')
                  for path in sorted((root / 'src').glob(pattern))]
    else:
        names = explicit
    result = []
    for name in names:
        path = (root / name).resolve()
        if path != root and root not in path.parents:
            raise ValueError('Source path escapes source root: ' + str(name))
        result.append(path)
    return result


def create_snapshot(output, source_root, run_dir, *, config=None, log=None, pgn=None,
                    binaries=(), book=None, pids=(), proc_root='/proc',
                    copy_limit=DEFAULT_COPY_LIMIT, read_limit=DEFAULT_READ_LIMIT,
                    source_files=None, label='', baseline=None):
    output, source_root, run_dir = map(lambda p: Path(p).resolve(),
                                     (output, source_root, run_dir))
    if not source_root.is_dir() or not run_dir.is_dir():
        raise ValueError('Source root and run directory must exist')
    if read_limit <= 0 or copy_limit < 0:
        raise ValueError('Read limit must be positive and copy limit nonnegative')
    if baseline is not None and not re.fullmatch('[0-9a-fA-F]{40}', baseline):
        raise ValueError('Declared baseline must be a full 40-character SHA')
    sources = selected_sources(source_root, source_files)
    # Existence is checked atomically by mkdir; no previous archive is reused.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'files').mkdir()
    manifest = {'schema_version': SCHEMA_VERSION, 'capture_id': output.name,
                'label': label, 'started_utc': utc_now(), 'source_root': str(source_root),
                'run_dir': str(run_dir), 'mode': 'observation-time-read-only',
                'declared_baseline': baseline, 'baseline_verified': False,
                'source_linkage': 'captured-source-not-linked-to-running-binary',
                'limits': {'read_bytes_per_file': read_limit,
                           'copy_bytes_per_file': copy_limit},
                'artifacts': [], 'processes': [], 'findings': [],
                'result': {'decision': 'not_evaluated', 'elo_claim': None},
                'host_core_type_verified': False}

    def add_artifact(path, role):
        entry = capture_file(path, role, output, len(manifest['artifacts']),
                             copy_limit, read_limit)
        entry['index'] = len(manifest['artifacts'])
        manifest['artifacts'].append(entry)
        if entry['status'] == 'read_error':
            manifest['findings'].append(finding('INPUT_READ_ERROR', entry.get('error', ''),
                                                entry['index']))
        for code in entry['findings']:
            manifest['findings'].append(finding(code, entry['source_path'], entry['index']))
        return entry

    source_entries = [add_artifact(path, 'source') for path in sources]
    for entry in source_entries:
        try:
            final = file_stat(Path(entry['source_path']).stat())
            if entry.get('source_stat_before') != final:
                manifest['findings'].append(finding('SOURCE_CHANGED_DURING_CAPTURE',
                                                    entry['source_path'], entry['index']))
        except OSError as error:
            manifest['findings'].append(finding('SOURCE_UNAVAILABLE_AFTER_CAPTURE',
                                                str(error), entry['index']))
    source_descriptor = [(str(Path(e['source_path']).relative_to(source_root)),
                          e['sha256'], e['hash_scope']) for e in source_entries]
    manifest['captured_source_digest'] = hashlib.sha256(
        json.dumps(source_descriptor, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    path_entries = []
    for name, path in binaries:
        entry = add_artifact(path, 'binary_path:' + name)
        path_entries.append(entry)
    if book is not None:
        add_artifact(book, 'book')
    for role, path in (('config', config), ('log', log), ('pgn', pgn)):
        if path is None:
            continue
        entry = add_artifact(path, role)
        if role in ('config', 'pgn'):
            if entry['archive_path'] is None or entry['status'] == 'read_error':
                manifest['findings'].append(finding('ANALYSIS_UNAVAILABLE', role, entry['index']))
                continue
            if role == 'config' and (entry['hash_scope'] != 'initial_file' or
                                     entry['status'] != 'ok'):
                manifest['findings'].append(finding('CONFIG_INCOMPLETE_CAPTURE',
                                                    'Protocol not inferred from a prefix', entry['index']))
                continue
            try:
                text = (output / entry['archive_path']).read_text(encoding='utf-8-sig')
                if role == 'config':
                    manifest['protocol_observed'] = parse_config(text)
                else:
                    manifest['pgn_observed'] = inspect_pgn(text)
                    for code in manifest['pgn_observed']['findings']:
                        manifest['findings'].append(finding(code, 'Observed PGN prefix', entry['index']))
            except (ValueError, UnicodeError) as error:
                manifest['findings'].append(finding('ANALYSIS_ERROR', str(error), entry['index']))
    for pid in pids:
        process = capture_process(pid, proc_root, add_artifact)
        manifest['processes'].append(process)
        if process.get('status') != 'observed':
            manifest['findings'].append(finding('PROCESS_OBSERVATION_INCOMPLETE',
                                                'PID %d: %s' % (pid, process.get('status'))))
        process_entry = next((e for e in manifest['artifacts']
                              if e['index'] == process.get('executable_artifact')), None)
        if process_entry is not None:
            process['matches_current_binary_digests'] = [e['role'] for e in path_entries
                if process_entry['sha256'] is not None and
                process_entry['hash_scope'] == e['hash_scope'] == 'initial_file' and
                process_entry['sha256'] == e['sha256']]
            target = process.get('executable_target', '').removesuffix(' (deleted)')
            for entry in path_entries:
                if (os.path.abspath(target) == entry['source_path'] and
                        process_entry['sha256'] and entry['sha256'] and
                        process_entry['hash_scope'] == entry['hash_scope'] == 'initial_file' and
                        process_entry['sha256'] != entry['sha256']):
                    manifest['findings'].append(finding('RUNNING_BINARY_DIFFERS_FROM_PATH',
                                                        'PID %d' % pid, entry['index']))
    manifest['finished_utc'] = utc_now()
    manifest_path = output / 'manifest.json'
    with open(manifest_path, 'x', encoding='utf-8', newline='\n') as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=True)
        handle.write('\n')
    with open(output / 'manifest.sha256', 'x', encoding='ascii') as handle:
        handle.write(sha256_file(manifest_path) + '\n')
    return manifest


def verify_archive(archive):
    archive = Path(archive).resolve()
    errors, verified, unarchived = [], 0, 0
    try:
        expected = (archive / 'manifest.sha256').read_text(encoding='ascii').strip()
        if not re.fullmatch('[0-9a-f]{64}', expected) or sha256_file(archive / 'manifest.json') != expected:
            errors.append('Manifest digest mismatch')
        manifest = json.loads((archive / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('schema_version') != SCHEMA_VERSION:
            errors.append('Unsupported schema version')
        for entry in manifest['artifacts']:
            relative = entry.get('archive_path')
            if relative is None:
                unarchived += 1
                continue
            name = PurePosixPath(relative)
            path = (archive / relative).resolve()
            if (name.is_absolute() or '..' in name.parts or
                    '\\' in relative or archive not in path.parents):
                errors.append('Unsafe archive member: ' + relative)
                continue
            try:
                if path.stat().st_size != entry['bytes_hashed']:
                    errors.append('Size mismatch: ' + relative)
                elif sha256_file(path) != entry['sha256']:
                    errors.append('Digest mismatch: ' + relative)
                else:
                    verified += 1
            except OSError as error:
                errors.append(str(error))
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    return {'integrity_ok': not errors, 'archived_files_verified': verified,
            'unarchived_artifacts': unarchived, 'errors': errors,
            'scope': 'Archive integrity only; no experiment validity or Elo claim'}


def binary_argument(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('Use NAME=PATH')
    name, path = value.split('=', 1)
    if not re.fullmatch('[A-Za-z0-9_.-]+', name) or not path:
        raise argparse.ArgumentTypeError('Use a simple name and nonempty path')
    return name, path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('capture')
    for name in ('source-root', 'run-dir', 'output'):
        capture.add_argument('--' + name, required=True)
    for name in ('config', 'log', 'pgn', 'book', 'label', 'baseline'):
        capture.add_argument('--' + name)
    capture.add_argument('--source-file', action='append')
    capture.add_argument('--binary', action='append', type=binary_argument, default=[])
    capture.add_argument('--pid', action='append', type=int, default=[])
    capture.add_argument('--proc-root', default='/proc')
    capture.add_argument('--read-limit-mib', type=int, default=64)
    capture.add_argument('--copy-limit-mib', type=int, default=16)
    verify = commands.add_parser('verify')
    verify.add_argument('archive')
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            result = verify_archive(args.archive)
            print(json.dumps(result, indent=2))
            return 0 if result['integrity_ok'] else 1
        if any(pid <= 0 for pid in args.pid):
            raise ValueError('PIDs must be positive')
        manifest = create_snapshot(args.output, args.source_root, args.run_dir,
            config=args.config, log=args.log, pgn=args.pgn, binaries=args.binary,
            book=args.book, pids=args.pid, proc_root=args.proc_root,
            read_limit=args.read_limit_mib * 1024 * 1024,
            copy_limit=args.copy_limit_mib * 1024 * 1024,
            source_files=args.source_file, label=args.label or '', baseline=args.baseline)
        print(json.dumps({'archive': str(Path(args.output).resolve()),
                          'artifacts': len(manifest['artifacts']),
                          'findings': len(manifest['findings']),
                          'decision': 'not_evaluated'}, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print('snapshot_run: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
