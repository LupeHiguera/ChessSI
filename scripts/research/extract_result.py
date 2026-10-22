#!/usr/bin/env python3
"""Extract terminal Fastchess evidence without assigning a benchmark verdict.

Supported input: one fresh, paired new/base round-robin session using the
repository's Fastchess text format. An explicit H0/H1 message is necessary;
rounded LLR, positive Elo, process exit, and reaching a cap are insufficient.
PGN legality, source/build linkage and acceptance remain independent reviews.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import snapshot_run

NUMBER = r'-?\d+(?:\.\d+)?'
START = re.compile(r'Started game (\d+) of (\d+) \((new|base) vs (new|base)\)')
FINISH = re.compile(r'Finished game (\d+) \((new|base) vs (new|base)\): (1-0|0-1|1/2-1/2) \{(.*)\}')
DECISION = re.compile(r'SPRT \(\[(' + NUMBER + r'), (' + NUMBER + r')\]\) completed - (H[01]) was accepted')
ELO = re.compile(r'Elo: (' + NUMBER + r') \+/- (' + NUMBER + r'), nElo: (' + NUMBER + r') \+/- (' + NUMBER + r')')
COUNTS = re.compile(r'Games: (\d+), Wins: (\d+), Losses: (\d+), Draws: (\d+), Points: .*')
PENTA = re.compile(r'Ptnml\(0-2\): \[(\d+), (\d+), (\d+), (\d+), (\d+)\], .*')
LLR = re.compile(r'LLR: (' + NUMBER + r') \((' + NUMBER + r')%\) \((' + NUMBER + r'), (' + NUMBER + r')\) \[(' + NUMBER + r'), (' + NUMBER + r')\]')
NORMAL_ENDINGS = {
    'White wins by adjudication', 'Black wins by adjudication', 'Draw by adjudication',
    'Draw by 3-fold repetition', 'Draw by fifty moves rule',
    'Draw by insufficient mating material', 'Draw by stalemate', 'White mates', 'Black mates',
}


def inspect_log(text, protocol):
    """Return reported evidence plus reasons requiring review; never decide SPRT."""
    issues = []
    def issue(message):
        if message not in issues:
            issues.append(message)
    sprt = protocol.get('sprt')
    if not isinstance(sprt, dict):
        sprt = {}
    bounds = None
    try:
        alpha, beta = (float(sprt[k]) for k in ('alpha', 'beta'))
        elo0, elo1 = (float(sprt[k]) for k in ('elo0', 'elo1'))
        if not (all(map(math.isfinite, (alpha, beta, elo0, elo1))) and
                0 < alpha < 1 and 0 < beta < 1 and alpha + beta < 1 and elo0 < elo1):
            raise ValueError('invalid SPRT numbers')
        bounds = (math.log(beta / (1-alpha)), math.log((1-beta) / alpha))
        hypotheses = [round(elo0, 2), round(elo1, 2)]
    except (ValueError, TypeError, KeyError):
        hypotheses = None
        issue('Invalid or missing SPRT configuration')
    if sprt.get('enabled') is not True or sprt.get('model') != 'normalized':
        issue('Only enabled normalized SPRT is supported')
    rounds = protocol.get('rounds')
    cap = 2 * rounds if type(rounds) is int and rounds > 0 else None
    if cap is None or protocol.get('games_per_round') != 2:
        issue('Missing paired game cap')
    if not text.endswith('\n'):
        issue('Log has an incomplete final line')
    started, finished = {}, {}
    start_lines = {}
    wld, penta = [0, 0, 0], [0] * 5
    reports, decisions, endings = [], [], Counter()
    current = None
    last_game_line = 0
    finish_markers = []
    for line_no, line in enumerate(text.splitlines(), 1):
        # Retain late records as evidence, but never accept events after the
        # manager's final marker as a clean terminal session.
        if finish_markers:
            if line.startswith(('Started game ', 'Finished game ')):
                issue('Game event after final match marker')
            if line.startswith(('Results of ', 'Elo: ', 'LOS: ', 'Games: ', 'Ptnml(0-2): ', 'LLR: ')):
                issue('Statistics event after final match marker')
        match = START.fullmatch(line)
        if match:
            ident, total, white, black = match.groups()
            ident, total = int(ident), int(total)
            if (ident < 1 or ident > total or total != cap or ident in started or
                    white == black or (ident % 2 == 1) != (white == 'new')):
                issue('Invalid, duplicate or mixed-session game start')
            started[ident] = (white, black)
            start_lines[ident] = line_no
            last_game_line = line_no
        elif line.startswith('Started game '):
            issue('Unrecognized game-start record')
        match = FINISH.fullmatch(line)
        if match:
            ident, white, black, result, reason = match.groups()
            ident = int(ident)
            if ident in finished or started.get(ident) != (white, black):
                issue('Duplicate finish or finish without matching start')
                continue
            half_points = {'1-0': 2, '0-1': 0, '1/2-1/2': 1}[result]
            if white == 'base':
                half_points = 2 - half_points
            finished[ident] = {'half_points': half_points, 'line': line_no}
            partner = ident + 1 if ident % 2 else ident - 1
            if partner in finished:
                a, b = half_points, finished[partner]['half_points']
                penta[a + b] += 1
                for value in (a, b):
                    wld[{2: 0, 0: 1, 1: 2}[value]] += 1
            endings[reason] += 1
            if reason not in NORMAL_ENDINGS:
                issue('Abnormal or unsupported game termination')
            last_game_line = line_no
        elif line.startswith('Finished game '):
            issue('Unrecognized game-finish record')
        if line.startswith('Results of '):
            if not line.startswith('Results of new vs base ('):
                issue('Unexpected engine order in statistics')
            if current is not None:
                issue('Incomplete statistics block')
            current = {'header_line': line_no}
        for pattern, key in ((ELO, 'elo'), (COUNTS, 'counts'), (PENTA, 'pentanomial'), (LLR, 'llr')):
            match = pattern.fullmatch(line)
            if not match:
                continue
            if current is None or key in current:
                issue('Orphaned or duplicate statistics field')
                continue
            cast = int if key in ('counts', 'pentanomial') else float
            current[key] = list(map(cast, match.groups()))
            if key == 'counts':
                current['statistics_line'] = line_no
            if key == 'llr':
                current['end_line'] = line_no
                if not {'elo', 'counts', 'pentanomial'} <= current.keys():
                    issue('Incomplete statistics block')
                else:
                    if current['counts'] != [sum(wld), *wld] or current['pentanomial'] != penta:
                        issue('Statistics disagree with completed pairs')
                    if current['elo'][1] < 0 or current['elo'][3] < 0:
                        issue('Negative reported Elo uncertainty')
                    if hypotheses != current['llr'][4:6]:
                        issue('Statistics hypotheses disagree with configuration')
                    if bounds and any(abs(a-b) > .005001 for a,b in zip(current['llr'][2:4], bounds)):
                        issue('Printed LLR bounds disagree with configuration')
                reports.append(current)
                current = None
        if line.startswith('SPRT ('):
            match = DECISION.fullmatch(line)
            if not match:
                issue('Malformed decision message')
                continue
            low, high, hypothesis = match.groups()
            decision = {'line': line_no, 'hypothesis': hypothesis,
                        'hypotheses': [float(low), float(high)],
                        'statistics': reports[-1] if reports else None,
                        'completed_games_at_decision': len(finished)}
            decisions.append(decision)
            if decision['hypotheses'] != hypotheses:
                issue('Decision hypotheses disagree with configuration')
            report = decision['statistics']
            if current is not None or not report or report['end_line'] < last_game_line:
                issue('Decision lacks adjacent complete statistics')
            elif bounds and 'llr' in report:
                # Consistency only: the rounding interval must reach the claimed
                # boundary. Never infer acceptance from this check or the display.
                shown = report['llr'][0]
                if ((hypothesis == 'H0' and shown - .005001 > bounds[0]) or
                        (hypothesis == 'H1' and shown + .005001 < bounds[1])):
                    issue('Decision contradicts displayed LLR rounding interval')
        if line == 'Finished match':
            finish_markers.append(line_no)
    if current is not None:
        issue('Incomplete statistics block')
    if len(decisions) != 1:
        issue('Expected exactly one explicit SPRT decision')
    selected = decisions[0] if len(decisions) == 1 else None
    late_starts, late_games, late_reports = [], [], []
    if selected:
        late_starts = [ident for ident, line in start_lines.items() if line > selected['line']]
        late_games = [ident for ident, game in finished.items() if game['line'] > selected['line']]
        late_reports = [r['header_line'] for r in reports if r['header_line'] > selected['line']]
        if late_starts or late_games or late_reports:
            issue('Post-decision games or statistics require independent reconciliation')
        if len(finish_markers) != 1 or finish_markers[0] <= selected['line']:
            issue('Missing or misplaced final match marker')
    if cap is not None and len(finished) >= cap:
        issue('Game cap reached; independently verify the boundary before assigning a result')
    unpaired = sorted(i for i in finished if (i+1 if i%2 else i-1) not in finished)
    return {'reported_hypothesis': selected['hypothesis'] if selected else None,
            'decision': selected, 'decision_messages': len(decisions),
            'statistics_reports': len(reports), 'completed_log_games': len(finished),
            'final_paired_counts': {'games': sum(wld), 'wins': wld[0], 'losses': wld[1],
                                   'draws': wld[2], 'pentanomial': penta},
            'unpaired_completed_game_ids': unpaired,
            'started_without_finish': sorted(set(started)-set(finished)),
            'late_started_game_ids': late_starts,
            'late_finished_game_ids': late_games, 'late_statistics_lines': late_reports,
            'termination_reasons': dict(endings), 'issues': issues}


def inspect_snapshot(archive, terminal_state=None):
    archive = Path(archive).resolve(strict=True)
    verification = snapshot_run.verify_archive(archive)
    result = {'schema_version': 1, 'snapshot': str(archive), 'integrity': verification,
              'evidence_status': 'unresolved', 'benchmark_result': 'not_assigned',
              'scope': 'Reported manager evidence only; independent PGN, protocol, build and acceptance review required.',
              'issues': []}
    if not verification['integrity_ok']:
        result['issues'].append('Snapshot integrity failed')
        return result
    manifest = json.loads((archive/'manifest.json').read_text(encoding='utf-8'))
    result['manifest_sha256'] = snapshot_run.sha256_file(archive/'manifest.json')
    if manifest['findings']:
        result['issues'].append('Snapshot has unresolved capture findings')
    roles = {}
    for item in manifest['artifacts']:
        if item['role'] != 'source':
            if item['role'] in roles:
                result['issues'].append('Duplicate artifact role')
            roles[item['role']] = item
    for role in ('log', 'config', 'pgn', 'binary_path:candidate', 'binary_path:baseline'):
        item = roles.get(role, {})
        if (not item.get('archive_path') or item.get('status') != 'ok' or
                item.get('hash_scope') != 'initial_file' or item.get('findings')):
            result['issues'].append('Missing or incomplete artifact: '+role)
    if result['issues']:
        return result
    result['artifact_sha256'] = {role: item['sha256'] for role,item in roles.items()}
    config_text = (archive/roles['config']['archive_path']).read_text(encoding='utf-8-sig')
    protocol = snapshot_run.parse_config(config_text)
    result['protocol'] = protocol
    log = (archive/roles['log']['archive_path']).read_text(encoding='utf-8-sig')
    evidence = inspect_log(log, protocol)
    result['log_evidence'] = evidence
    result['issues'].extend(evidence['issues'])
    if terminal_state is None:
        result['issues'].append('No terminal process observation supplied')
    else:
        state_path = Path(terminal_state)
        state_bytes = state_path.read_bytes()
        state = json.loads(state_bytes)
        if not isinstance(state, dict):
            raise ValueError('Terminal observation must be a JSON object')
        result['terminal_state_sha256'] = hashlib.sha256(state_bytes).hexdigest()
        if state.get('status') != 'archived' or state.get('process_terminal') is not True:
            result['issues'].append('Process termination and archive completion are unconfirmed')
        if state.get('signal_sent') is not False:
            result['issues'].append('Signal sent or signal status unknown; review interruption ordering')
        if state.get('binary_drift') is not False:
            result['issues'].append('Binary drift detected or status unknown')
        if Path(state.get('archive', '')).resolve() != archive:
            result['issues'].append('Terminal observation names another archive')
        for name in ('candidate', 'baseline'):
            if state.get('final_binary_hashes', {}).get(name) != roles['binary_path:'+name]['sha256']:
                result['issues'].append('Terminal binary digest mismatch: '+name)
        try:
            ended = datetime.fromisoformat(state['observed_end_utc'])
            captured = datetime.fromisoformat(manifest['started_utc'])
            if ended.tzinfo is None or captured.tzinfo is None or ended > captured:
                raise ValueError('archive precedes observed termination')
        except (KeyError, ValueError, TypeError):
            result['issues'].append('Archive is not demonstrably after process termination')
    if not result['issues']:
        result['evidence_status'] = 'ready_for_independent_audit'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--terminal-state', type=Path)
    args = parser.parse_args()
    try:
        result = inspect_snapshot(args.snapshot, args.terminal_state)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'evidence_status': 'unresolved', 'benchmark_result': 'not_assigned',
                          'issues': [type(error).__name__+': '+str(error)]}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['evidence_status'] == 'ready_for_independent_audit' else 2


if __name__ == '__main__':
    raise SystemExit(main())
