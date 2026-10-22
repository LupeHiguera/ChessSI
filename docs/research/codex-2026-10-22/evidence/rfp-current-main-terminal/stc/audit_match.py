#!/usr/bin/env python3
"""Audit a frozen single-session two-engine match; never accepts/rejects SPRT."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path('/mnt/c/Users/Lupe/CLionProjects/ChessSI-astra')
SCHEMA_VERSION = 2
AUDITOR_SOURCE = Path(__file__).read_bytes()
LOADED_HELPER_SOURCES = {}


class AuditError(ValueError):
    """Invalid or insufficient audit evidence; never a benchmark verdict."""


def require(condition, message='Audit validation failed'):
    if not condition:
        raise AuditError(str(message))


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def module(name, relative, identity):
    path = ROOT / relative
    source = path.read_bytes()
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    # Execute the exact source bytes being recorded; do not use cached bytecode.
    exec(compile(source, str(path), 'exec'), value.__dict__)
    LOADED_HELPER_SOURCES[identity] = {'path': str(path.resolve()), 'sha256': sha_bytes(source)}
    require(sha_file(path) == sha_bytes(source), 'Helper changed while loading: ' + identity)
    return value


snap = module('audit_snapshot', 'scripts/research/snapshot_run.py', 'snapshot_run')
corpus = module('audit_corpus', 'scripts/research/prepare_corpus.py', 'prepare_corpus')
import chess
import chess.pgn


def runtime_record():
    require(sys.flags.optimize == 0 and __debug__,
            'Optimized Python is unsupported: unset PYTHONOPTIMIZE and omit -O/-OO')
    require(os.sched_getaffinity(0) == {19}, 'Auditor must run only on CPU 19')
    require(chess.__version__ == corpus.PINNED_VERSION, 'Unexpected python-chess version')
    return {
        'python_version': sys.version, 'executable': sys.executable,
        'flags': {name: getattr(sys.flags, name) for name in
                  ('optimize', 'dont_write_bytecode', 'debug', 'isolated', 'no_site', 'ignore_environment')},
        'assertions_enabled': bool(__debug__),
    }


def implementation_sources():
    sources = {
        'audit_match': {'path': str(Path(__file__).resolve()), 'sha256': sha_bytes(AUDITOR_SOURCE)},
        **LOADED_HELPER_SOURCES,
    }
    for name, value in sorted(sys.modules.copy().items()):
        if name == 'chess' or name.startswith('chess.'):
            path = getattr(value, '__file__', None)
            if path:
                path = Path(path).resolve()
                require(path.suffix == '.py', 'Dependency source unavailable: ' + name)
                sources[name] = {'path': str(path), 'sha256': sha_file(path)}
    recheck_sources(sources)
    return sources


def recheck_sources(sources):
    for name, record in sources.items():
        require(sha_file(record['path']) == record['sha256'],
                'Implementation source changed during audit: ' + name)


def bind_inputs(snapshot):
    verified = snap.verify_archive(snapshot)
    require(verified['integrity_ok'], 'Snapshot integrity failed: ' + str(verified))
    manifest_path = snapshot / 'manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = sha_bytes(manifest_bytes)
    require((snapshot / 'manifest.sha256').read_text(encoding='ascii').strip() == manifest_digest,
            'Snapshot manifest changed after integrity verification')
    manifest = json.loads(manifest_bytes)
    data, bindings = {}, {}
    for role in ('log', 'pgn', 'config'):
        entries = [item for item in manifest['artifacts'] if item['role'] == role]
        require(len(entries) == 1, 'Require one archived artifact for role: ' + role)
        item = entries[0]
        require(item.get('archive_path') and item.get('status') == 'ok',
                'Missing or unreadable archived artifact: ' + role)
        relative = Path(item['archive_path'])
        path = (snapshot / relative).resolve(strict=True)
        require(not relative.is_absolute() and '..' not in relative.parts and
                '\\' not in item['archive_path'] and snapshot in path.parents,
                'Unsafe archived artifact path: ' + role)
        raw = path.read_bytes()
        require(sha_bytes(raw) == item['sha256'] and len(raw) == item['bytes_hashed'],
                'Archived artifact changed after integrity verification: ' + role)
        data[role] = raw.decode('utf-8-sig')
        bindings[role] = {'path': str(path), 'sha256': sha_bytes(raw)}
    return verified, manifest_digest, data, bindings


def recheck_inputs(snapshot, manifest_digest, bindings):
    require(sha_file(snapshot / 'manifest.json') == manifest_digest,
            'Snapshot manifest changed during audit')
    require((snapshot / 'manifest.sha256').read_text(encoding='ascii').strip() == manifest_digest,
            'Snapshot manifest digest file changed during audit')
    for role, record in bindings.items():
        require(sha_file(record['path']) == record['sha256'],
                'Audited artifact changed during audit: ' + role)


def score(white, result):
    value = {'1-0': 2, '1/2-1/2': 1, '0-1': 0}[result]
    return value if white == 'new' else 2-value


def aggregate(games):
    pairs = defaultdict(list)
    for row in games.values():
        pairs[row['round']].append(row)
    penta = [0]*5
    wld = [0]*3
    counted, unpaired = [], []
    for number, rows in sorted(pairs.items()):
        require(len(rows) <= 2, ('Too many games in pair', number))
        if len(rows) == 1:
            unpaired.append(rows[0]['id'])
            continue
        require({r['white'] for r in rows} == {'new', 'base'}, ('Invalid pair colors', number))
        penta[sum(r['half_points'] for r in rows)] += 1
        for row in rows:
            wld[{2: 0, 0: 1, 1: 2}[row['half_points']]] += 1
            counted.append(row['id'])
    return {'games': sum(wld), 'wins': wld[0], 'losses': wld[1], 'draws': wld[2], 'pentanomial': penta,
            'completed_pairs': sum(penta), 'unpaired_game_ids': unpaired, 'counted_game_ids': sorted(counted)}


def audit(snapshot, output):
    snapshot = snapshot.resolve(strict=True)
    output = output.resolve()
    snapshot.relative_to(ROOT)
    output.relative_to(ROOT)
    runtime = runtime_record()
    sources = implementation_sources()
    output.mkdir(exist_ok=False)
    (output / 'audit_match.py').write_bytes(AUDITOR_SOURCE)
    verified, manifest_digest, data, bindings = bind_inputs(snapshot)
    pgn, log, config = data['pgn'], data['log'], json.loads(data['config'])
    require(config['stats'].keys() == {'new vs base'}, 'Unexpected engine statistics keys')
    stream = io.StringIO(pgn)
    games, signature, plies, terminations = {}, None, 0, Counter()
    while True:
        begin = stream.tell()
        game = chess.pgn.read_game(stream, Visitor=corpus.StrictBuilder)
        end = stream.tell()
        if game is None:
            require(not pgn[begin:].strip(), 'Unparsed trailing PGN bytes')
            break
        require(not game.errors, game.errors)
        headers, sans, result = corpus.strict_movetext(pgn[begin:end])
        require(game.observed_results == [result], 'Incomplete or inconsistent PGN result')
        require(re.fullmatch('[1-9][0-9]*', headers['Round']), 'Unsupported PGN round')
        require({headers['White'], headers['Black']} == {'new', 'base'}, 'Unexpected PGN players')
        require(headers.get('SetUp') == '1' and 'FEN' in headers, 'Initial book FEN required')
        require(headers.get('Variant', 'Standard').lower() in ('standard', 'chess'), 'Unsupported variant')
        require(headers.get('Chess960', 'false').lower() in ('false', '0'), 'Chess960 unsupported')
        current = {k: headers.get(k) for k in ('Event', 'Site', 'TimeControl', 'Session', 'RunId', 'Variant')}
        require(signature is None or current == signature, 'Mixed session headers')
        signature = current
        number, white = int(headers['Round']), headers['White']
        ident = 2*number - (1 if white == 'new' else 0)
        require(ident not in games, ('Duplicate Round/color game', ident))
        board = corpus.valid_board(headers['FEN'])
        fen = board.fen(en_passant='xfen')
        parsed = list(game.mainline_moves())
        require(len(sans) == len(parsed), 'Parsed move count mismatch')
        for san, expected in zip(sans, parsed):
            move = board.parse_san(san)
            require(move and move == expected and board.is_legal(move), ('Illegal or inconsistent move', ident, san))
            board.push(move)
        require(headers.get('PlyCount', '').isdecimal() and int(headers['PlyCount']) == len(parsed),
                ('PlyCount mismatch', ident))
        if board.is_checkmate():
            require(result == ('0-1' if board.turn == chess.WHITE else '1-0'), ('Checkmate result mismatch', ident))
        if board.is_stalemate() or board.is_insufficient_material():
            require(result == '1/2-1/2', ('Draw result mismatch', ident))
        termination = headers.get('Termination', 'missing')
        terminations[termination] += 1
        games[ident] = {'id': ident, 'round': number, 'white': white, 'result': result,
            'half_points': score(white, result), 'initial_fen': fen, 'plies': len(parsed),
            'termination': termination, 'fragment_sha256': sha_bytes(pgn[begin:end].encode()),
            'last_comment': game.end().comment, 'checkmate': board.is_checkmate(), 'stalemate': board.is_stalemate(),
            'insufficient_material': board.is_insufficient_material(), 'rule50': board.halfmove_clock,
            'threefold_from_recorded_history': board.is_repetition(3)}
        plies += len(parsed)
        if len(games) % 400 == 0:
            print('Legally replayed ' + str(len(games)) + ' games', flush=True)
    require(games, 'No games')
    for row in games.values():
        partner = games.get(row['id']+1 if row['white'] == 'new' else row['id']-1)
        if partner:
            require(partner['initial_fen'] == row['initial_fen'], ('Opening pair mismatch', row['round']))
    (output / 'pgn-games.json').write_text(json.dumps(list(games.values()), indent=2)+'\n')
    print('All PGN games legally replayed; checking report boundaries', flush=True)
    stats = config['stats']['new vs base']
    config_counts = {'games': sum(stats[k] for k in ('wins', 'losses', 'draws')),
        **{k: stats[k] for k in ('wins', 'losses', 'draws')},
        'pentanomial': [stats['penta_LL'], stats['penta_LD'], stats['penta_WL']+stats['penta_DD'],
                        stats['penta_WD'], stats['penta_WW']]}
    started, finished, reports, reasons = {}, {}, [], Counter()
    current_stats, last_elo, failures, config_event_matches = None, None, [], []
    for line_no, line in enumerate(log.splitlines(), 1):
        match = re.fullmatch(r'Started game (\d+) of (\d+) \((new|base) vs (new|base)\)', line)
        if match:
            ident, total, white, black = match.groups()
            ident = int(ident)
            require(ident not in started, ('Repeated game start', ident))
            require({white, black} == {'new', 'base'}, 'Unexpected log players')
            started[ident] = (white, black)
        match = re.fullmatch(r'Finished game (\d+) \((new|base) vs (new|base)\): (1-0|0-1|1/2-1/2) \{(.*)\}', line)
        if match:
            ident, white, black, result, reason = match.groups()
            ident = int(ident)
            require(ident not in finished and started.get(ident) == (white, black),
                    ('Duplicate finish or missing matching start', ident))
            require(ident % 2 == (1 if white == 'new' else 0), ('Log pair color mismatch', ident))
            finished[ident] = {'id': ident, 'round': (ident+1)//2, 'white': white, 'result': result,
                              'half_points': score(white, result), 'reason': reason}
            reasons[reason] += 1
            if (ident-1 if ident % 2 == 0 else ident+1) in finished:
                observed = aggregate(finished)
                if {k: observed[k] for k in config_counts} == config_counts:
                    config_event_matches.append({'line': line_no, 'just_finished_game': ident,
                                                 'counted_game_ids': observed['counted_game_ids']})
            if ident in games:
                pg = games[ident]
                require(pg['white'] == white and pg['result'] == result, ('PGN/log game result mismatch', ident))
                if reason == 'Draw by 3-fold repetition':
                    require(pg['threefold_from_recorded_history'], ('Repetition mismatch', ident))
                elif reason == 'Draw by fifty moves rule':
                    require(pg['rule50'] >= 100 and not pg['checkmate'], ('Fifty-move rule mismatch', ident))
                elif reason == 'Draw by insufficient mating material':
                    require(pg['insufficient_material'], ('Insufficient-material mismatch', ident))
                elif reason == 'Draw by stalemate':
                    require(pg['stalemate'], ('Stalemate mismatch', ident))
                elif 'mate' in reason.lower() and 'material' not in reason.lower():
                    require(pg['checkmate'], ('Checkmate mismatch', ident, reason))
        match = re.fullmatch(r'Elo: ([-\d.]+) \+/- ([\d.]+), nElo: ([-\d.]+) \+/- ([\d.]+)', line)
        if match:
            last_elo = list(map(float, match.groups()))
        match = re.match(r'Games: (\d+), Wins: (\d+), Losses: (\d+), Draws: (\d+),', line)
        if match:
            n, w, l, d = map(int, match.groups())
            require(n == w+l+d, 'Reported WLD total mismatch')
            require(current_stats is None, 'New statistics overwrite an incomplete block')
            current_stats = {'line': line_no, 'reported': {'games': n, 'wins': w, 'losses': l, 'draws': d},
                             'reconstructed': aggregate(finished), 'shown_elo': last_elo}
        match = re.match(r'Ptnml\(0-2\): \[([^]]+)\]', line)
        if match:
            require(current_stats is not None, 'Orphaned pentanomial report')
            current_stats['reported']['pentanomial'] = list(map(int, match.group(1).split(',')))
            for key, value in current_stats['reported'].items():
                if current_stats['reconstructed'][key] != value:
                    failures.append({'line': line_no, 'field': key, 'reported': value,
                                     'reconstructed': current_stats['reconstructed'][key]})
            reports.append(current_stats)
            current_stats = None
    require(current_stats is None, 'Truncated statistics block')
    pgn_aggregate, log_aggregate = aggregate(games), aggregate(finished)
    config_matches = [r['line'] for r in reports if r['reported'] == config_counts]
    overlap = set(games) & set(finished)
    quality_reasons = {reason: n for reason, n in reasons.items()
                       if re.search(r'time.?out|time.?forfeit|disconnect|crash|illegal|stalled|time loss', reason, re.I)}
    recheck_inputs(snapshot, manifest_digest, bindings)
    recheck_sources(sources)
    result = {'schema_version': SCHEMA_VERSION,
        'observed_utc': datetime.now(timezone.utc).isoformat(), 'model': 'GPT-6 (Codex)',
        'snapshot': str(snapshot), 'snapshot_integrity': verified,
        'snapshot_manifest_sha256': manifest_digest,
        'audited_artifact_sha256': {role: record['sha256'] for role, record in bindings.items()},
        'implementation_sources': sources, 'runtime': runtime, 'input_bindings_rechecked': True,
        'cpu_affinity': sorted(os.sched_getaffinity(0)), 'python_chess_version': chess.__version__,
        'single_session_signature': signature, 'pgn_games_legally_replayed': len(games), 'legal_plies': plies,
        'pgn_termination_counts': dict(terminations), 'pgn_pair_aggregate': pgn_aggregate,
        'log_finished_games': len(finished), 'log_pair_aggregate': log_aggregate,
        'log_reports_checked': len(reports), 'log_report_count_mismatches': failures,
        'config_counts': config_counts, 'config_matching_report_lines': config_matches,
        'config_matching_event_boundaries': config_event_matches,
        'cross_source_game_results_compared': len(overlap),
        'log_games_not_in_pgn_snapshot': sorted(set(finished)-set(games)),
        'pgn_games_not_in_log_snapshot': sorted(set(games)-set(finished)),
        'log_finished_reasons': dict(reasons), 'suspect_termination_reasons': quality_reasons,
        'current_manager_verdict': 'not_interpreted',
        'scope': 'Frozen prefixes; each file can represent a different observation instant. No SPRT decision or adjudication calibration.',
        'source_sha256': sources['audit_match']['sha256']}
    (output / 'reports.json').write_text(json.dumps(reports, indent=2)+'\n')
    (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items()
                     if k not in ('pgn_pair_aggregate', 'log_pair_aggregate', 'config_matching_event_boundaries')},
                     indent=2), flush=True)
    if config_counts['games'] <= log_aggregate['games'] and not config_event_matches:
        raise AuditError('Autosave counts do not match any completed-pair event boundary')
    if failures:
        raise AuditError('Statistics report/count disagreement; inspect retained evidence')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.snapshot, args.output)

