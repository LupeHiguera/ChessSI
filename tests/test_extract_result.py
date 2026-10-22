"""Terminal evidence tests: never turn a cap, live prefix or rounded LLR into a pass."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts/research'
sys.path.insert(0, str(SCRIPTS))
import extract_result as extractor
import snapshot_run

PROTOCOL = {'sprt': {'enabled': True, 'model': 'normalized', 'alpha': .05,
                     'beta': .05, 'elo0': 0, 'elo1': 5},
            'rounds': 100, 'games_per_round': 2}


def start(ident):
    order = 'new vs base' if ident % 2 else 'base vs new'
    return f'Started game {ident} of 200 ({order})\n'


def finish(ident, result='1-0'):
    order = 'new vs base' if ident % 2 else 'base vs new'
    reason = {'1-0': 'White wins by adjudication', '0-1': 'Black wins by adjudication',
              '1/2-1/2': 'Draw by adjudication'}[result]
    return f'Finished game {ident} ({order}): {result} {{{reason}}}\n'


def report(llr='2.95'):
    return ('--------------------------------------------------\n'
            'Results of new vs base (10+0.1, 1t, 16MB, book.epd):\n'
            'Elo: 4.00 +/- 10.00, nElo: 5.00 +/- 12.00\n'
            'LOS: 50.00 %, DrawRatio: 0.00 %, PairsRatio: 1.00\n'
            'Games: 2, Wins: 1, Losses: 1, Draws: 0, Points: 1.0 (50.00 %)\n'
            'Ptnml(0-2): [0, 0, 1, 0, 0], WL/DD Ratio: 1.00\n'
            f'LLR: {llr} (100.1%) (-2.94, 2.94) [0.00, 5.00]\n'
            '--------------------------------------------------\n')


def fixture(hypothesis='H1', llr='2.95'):
    # The synthetic Elo/LLR are parser fixtures, not a numerically valid SPRT.
    # Readiness means independent audit is possible, never a statistical pass.
    return (start(1)+start(2)+finish(1)+finish(2)+report(llr)+
            f'SPRT ([0.00, 5.00]) completed - {hypothesis} was accepted\nFinished match\n')


class LogEvidenceTests(unittest.TestCase):
    def inspect(self, text=None, protocol=None):
        return extractor.inspect_log(fixture() if text is None else text,
                                     PROTOCOL if protocol is None else protocol)

    def test_explicit_claim_is_extracted_without_assigning_result(self):
        out = self.inspect()
        self.assertEqual(out['reported_hypothesis'], 'H1')
        self.assertEqual(out['issues'], [])
        self.assertNotIn('result', out)
        self.assertEqual(out['decision']['statistics']['counts'], [2, 1, 1, 0])

    def test_rejection(self):
        out = self.inspect(fixture('H0', '-2.95'))
        self.assertEqual(out['reported_hypothesis'], 'H0')
        self.assertFalse(out['issues'])

    def test_rounded_boundary_cannot_create_decision(self):
        text = fixture(llr='2.94').replace('SPRT ([0.00, 5.00]) completed - H1 was accepted\n', '')
        out = self.inspect(text)
        self.assertIsNone(out['reported_hypothesis'])
        self.assertTrue(out['issues'])

    def test_rounding_interval_may_contain_actual_boundary(self):
        self.assertFalse(self.inspect(fixture('H0', '-2.94'))['issues'])
        self.assertFalse(self.inspect(fixture('H1', '2.94'))['issues'])

    def test_claim_far_inside_boundary_is_flagged(self):
        self.assertIn('Decision contradicts displayed LLR rounding interval',
                      self.inspect(fixture(llr='0.00'))['issues'])

    def test_cap_requires_review_even_with_claim(self):
        protocol = copy.deepcopy(PROTOCOL)
        protocol['rounds'] = 1
        out = self.inspect(fixture().replace('of 200', 'of 2'), protocol)
        self.assertTrue(any('cap reached' in s for s in out['issues']))

    def test_live_prefix_has_no_terminal_evidence(self):
        out = self.inspect(start(1)+start(2)+finish(1))
        self.assertIsNone(out['reported_hypothesis'])
        self.assertEqual(out['unpaired_completed_game_ids'], [1])

    def test_duplicate_or_conflicting_decisions_unresolved(self):
        for hypothesis in ('H0', 'H1'):
            with self.subTest(hypothesis=hypothesis):
                out = self.inspect(fixture()+f'SPRT ([0.00, 5.00]) completed - {hypothesis} was accepted\n')
                self.assertIsNone(out['reported_hypothesis'])
                self.assertEqual(out['decision_messages'], 2)

    def test_unpaired_game_is_not_in_paired_statistics(self):
        text = start(3)+finish(3)+fixture()
        out = self.inspect(text)
        self.assertFalse(out['issues'])
        self.assertEqual(out['completed_log_games'], 3)
        self.assertEqual(out['final_paired_counts']['games'], 2)
        self.assertEqual(out['unpaired_completed_game_ids'], [3])

    def test_late_finish_preserves_decision_counts(self):
        text = start(3)+start(4)+fixture()+finish(3)+finish(4)
        out = self.inspect(text)
        self.assertEqual(out['decision']['statistics']['counts'][0], 2)
        self.assertEqual(out['final_paired_counts']['games'], 4)
        self.assertEqual(out['late_finished_game_ids'], [3, 4])
        self.assertTrue(out['issues'])

    def test_log_counts_must_reconcile(self):
        for before, after in [('Wins: 1', 'Wins: 2'), ('[0, 0, 1, 0, 0]', '[1, 0, 0, 0, 0]')]:
            with self.subTest(before=before):
                self.assertIn('Statistics disagree with completed pairs',
                              self.inspect(fixture().replace(before, after))['issues'])

    def test_finish_without_start_or_duplicate_is_flagged(self):
        self.assertTrue(self.inspect(fixture().replace(start(1), ''))['issues'])
        self.assertTrue(self.inspect(finish(1)+fixture())['issues'])

    def test_color_assignment_must_match_pair(self):
        self.assertTrue(self.inspect(fixture().replace('(base vs new)', '(new vs base)'))['issues'])

    def test_truncated_or_missing_statistics_are_flagged(self):
        self.assertTrue(self.inspect(fixture().rstrip())['issues'])
        self.assertTrue(self.inspect(fixture().replace(report(), ''))['issues'])
        self.assertTrue(self.inspect(fixture().replace('Ptnml(0-2): [0, 0, 1, 0, 0], WL/DD Ratio: 1.00\n', ''))['issues'])

    def test_unpaired_completion_between_statistics_and_decision_is_stale(self):
        text = start(3)+fixture().replace('SPRT ([', finish(3)+'SPRT ([')
        self.assertIn('Decision lacks adjacent complete statistics', self.inspect(text)['issues'])

    def test_terminal_marker_required(self):
        self.assertTrue(self.inspect(fixture().replace('Finished match\n', ''))['issues'])

    def test_abnormal_termination_is_flagged(self):
        out = self.inspect(fixture().replace('White wins by adjudication', 'Black loses on time'))
        self.assertIn('Abnormal or unsupported game termination', out['issues'])

    def test_missing_sprt_object_is_unresolved(self):
        for value in (None, [], 'missing'):
            with self.subTest(value=value):
                protocol = {**PROTOCOL, 'sprt': value}
                self.assertTrue(self.inspect(protocol=protocol)['issues'])

    def test_wrong_protocol_or_hypotheses_is_flagged(self):
        for change in ({'model': 'logistic'}, {'enabled': False}, {'alpha': 0}, {'elo1': 6}):
            with self.subTest(change=change):
                protocol = copy.deepcopy(PROTOCOL)
                protocol['sprt'].update(change)
                self.assertTrue(self.inspect(protocol=protocol)['issues'])


class ArchiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('source.cpp', 'source'), ('new', 'new'), ('base', 'base'),
                            ('log', fixture()), ('pgn', '')]:
            (self.root/name).write_text(value)
        config = {'sprt': PROTOCOL['sprt'], 'rounds': 100, 'games': 2}
        (self.root/'config').write_text(json.dumps(config))
        self.archive = self.root/'snapshot'
        snapshot_run.create_snapshot(self.archive, self.root, self.root,
            source_files=['source.cpp'], config=self.root/'config', log=self.root/'log',
            pgn=self.root/'pgn', binaries=[('candidate', self.root/'new'), ('baseline', self.root/'base')])
        self.state = {'status': 'archived', 'process_terminal': True,
                      'signal_sent': False, 'binary_drift': False, 'archive': str(self.archive),
                      'observed_end_utc': '2020-01-01T00:00:00+00:00',
                      'final_binary_hashes': {'candidate': snapshot_run.sha256_file(self.root/'new'),
                                              'baseline': snapshot_run.sha256_file(self.root/'base')}}
        self.state_path = self.root/'state.json'

    def inspect(self, **changes):
        state = {**self.state, **changes}
        self.state_path.write_text(json.dumps(state))
        return extractor.inspect_snapshot(self.archive, self.state_path)

    def test_readiness_is_never_benchmark_acceptance(self):
        out = self.inspect()
        self.assertEqual(out['evidence_status'], 'ready_for_independent_audit')
        self.assertEqual(out['benchmark_result'], 'not_assigned')
        self.assertTrue(out['terminal_state_sha256'])

    def test_missing_or_live_state_unresolved(self):
        self.assertEqual(extractor.inspect_snapshot(self.archive)['evidence_status'], 'unresolved')
        self.assertEqual(self.inspect(process_terminal=False)['evidence_status'], 'unresolved')

    def test_interruption_and_drift_unresolved(self):
        for change in ({'signal_sent': True}, {'binary_drift': True}, {'final_binary_hashes': {}}):
            with self.subTest(change=change):
                self.assertEqual(self.inspect(**change)['evidence_status'], 'unresolved')

    def test_state_for_another_archive_unresolved(self):
        self.assertEqual(self.inspect(archive=str(self.root))['evidence_status'], 'unresolved')

    def test_archive_before_exit_unresolved(self):
        self.assertEqual(self.inspect(observed_end_utc='2099-01-01T00:00:00+00:00')['evidence_status'], 'unresolved')

    def test_tampered_snapshot_unresolved(self):
        (self.archive/'files/0000-source.cpp').write_text('tampered')
        out = self.inspect()
        self.assertEqual(out['evidence_status'], 'unresolved')
        self.assertIn('Snapshot integrity failed', out['issues'])


if __name__ == '__main__':
    unittest.main()
