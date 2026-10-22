"""Small, deterministic fixtures for the read-only run snapshot tool."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts/research/snapshot_run.py'
SPEC = importlib.util.spec_from_file_location('snapshot_run', MODULE_PATH)
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


def game(round_number=1, white='new', black='base', result='1-0', extra=''):
    return ('[Event "Fixture"]\n[Round "%s"]\n[White "%s"]\n[Black "%s"]\n'
            '[Result "%s"]\n[FEN "fixture position"]\n[TimeControl "10+0.1"]\n\n'
            '1. e4 %s e5 2. Nf3 %s\n\n' %
            (round_number, white, black, result, extra, result))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source with spaces'
        self.source.mkdir()
        (self.source / 'src').mkdir()
        (self.source / 'src/test.cpp').write_bytes(b'int example = 1;\n')
        self.run = self.root / 'run'
        self.run.mkdir()
        self.archive = self.root / 'archive'

    def capture(self, **kwargs):
        return snapshot.create_snapshot(self.archive, self.source, self.run,
                                        source_files=['src/test.cpp'], **kwargs)

    def write_config(self, text):
        path = self.run / 'config.json'
        path.write_text(text, encoding='utf-8')
        return path

    def test_exact_seed_and_copied_hashes(self):
        config = self.write_config('{"seed":2592085357017269485,"sprt":{"model":"normalized"}}')
        before = config.read_bytes()
        manifest = self.capture(config=config)
        self.assertEqual(manifest['protocol_observed']['seed_decimal'], '2592085357017269485')
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(manifest['result']['decision'], 'not_evaluated')
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])
        with self.assertRaises(FileExistsError):
            self.capture()

    def test_seed_float_rejected_and_raw_config_retained(self):
        config = self.write_config('{"seed":2.5920853570172695e18}')
        manifest = self.capture(config=config)
        self.assertNotIn('protocol_observed', manifest)
        self.assertTrue(any(f['code'] == 'ANALYSIS_ERROR' for f in manifest['findings']))
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_truncated_config_is_explicit(self):
        config = self.write_config('{"seed":123,')
        manifest = self.capture(config=config)
        self.assertTrue(any(f['code'] == 'ANALYSIS_ERROR' for f in manifest['findings']))
        self.assertNotIn('protocol_observed', manifest)

    def test_initial_length_stays_bounded_during_append(self):
        path = self.run / 'growing.log'
        path.write_bytes(b'original')
        original_reader = snapshot.read_prefix

        def append_then_read(handle, destination, limit):
            if os.fstat(handle.fileno()).st_ino == path.stat().st_ino:
                with open(path, 'ab') as writer:
                    writer.write(b' appended after open')
            return original_reader(handle, destination, limit)

        with mock.patch.object(snapshot, 'read_prefix', side_effect=append_then_read):
            manifest = self.capture(log=path)
        artifact = next(a for a in manifest['artifacts'] if a['role'] == 'log')
        self.assertEqual(artifact['bytes_hashed'], len(b'original'))
        self.assertEqual(artifact['sha256'], hashlib.sha256(b'original').hexdigest())
        self.assertEqual((self.archive / artifact['archive_path']).read_bytes(), b'original')
        self.assertIn('SOURCE_CHANGED_DURING_READ', artifact['findings'])

    def test_limit_does_not_mislabel_prefix_as_full_hash(self):
        path = self.run / 'book.epd'
        path.write_bytes(b'0123456789abcdef')
        manifest = self.capture(book=path, read_limit=8, copy_limit=4)
        artifact = next(a for a in manifest['artifacts'] if a['role'] == 'book')
        self.assertEqual(artifact['hash_scope'], 'prefix')
        self.assertEqual(artifact['bytes_hashed'], 8)
        self.assertIsNone(artifact['archive_path'])
        self.assertIn('READ_LIMIT_REACHED', artifact['findings'])

    def test_pgn_multiple_sessions_and_tail_never_produce_elo(self):
        path = self.run / 'games.pgn'
        content = game() + game(white='base', black='new') + game() + '[Event "unfinished"]\n\n1. e4 {'
        path.write_text(content, encoding='utf-8')
        manifest = self.capture(pgn=path)
        observed = manifest['pgn_observed']
        self.assertEqual(observed['completed_games_observed'], 3)
        self.assertEqual(observed['segmentation'], 'ambiguous')
        self.assertFalse(observed['statistics_eligible'])
        self.assertGreater(observed['incomplete_records_observed'], 0)
        self.assertIsNone(manifest['result']['elo_claim'])
        self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_comments_variations_and_out_of_order_pairing(self):
        text = (game(1, extra='{ fake 0-1 } (1... c5 0-1)') + game(2) +
                game(1, white='base', black='new'))
        observed = snapshot.inspect_pgn(text)
        self.assertEqual(observed['completed_games_observed'], 3)
        self.assertEqual(observed['structurally_paired_rounds'], 1)
        self.assertEqual(observed['incomplete_records_observed'], 0)

    def test_missing_input_preserves_partial_archive(self):
        manifest = self.capture(book=self.run / 'missing.epd')
        self.assertTrue(any(f['code'] == 'INPUT_READ_ERROR' for f in manifest['findings']))
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_source_escape_rejected_before_output(self):
        with self.assertRaises(ValueError):
            snapshot.create_snapshot(self.archive, self.source, self.run,
                                     source_files=['../../outside.cpp'])
        self.assertFalse(self.archive.exists())

    def test_missing_initial_config_is_optional_evidence(self):
        manifest = self.capture(config=self.run / 'not-created-yet.json')
        self.assertNotIn('protocol_observed', manifest)
        self.assertEqual(manifest['result']['decision'], 'not_evaluated')
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_valid_json_prefix_cannot_stand_in_for_whole_config(self):
        config = self.write_config('{"seed":1} some unread invalid content')
        manifest = self.capture(config=config, read_limit=10, copy_limit=10)
        self.assertNotIn('protocol_observed', manifest)
        self.assertTrue(any(f['code'] == 'CONFIG_INCOMPLETE_CAPTURE'
                            for f in manifest['findings']))

    @unittest.skipUnless(os.name == 'posix', 'named-pipe fixture requires POSIX')
    def test_named_pipe_is_rejected_without_waiting_for_writer(self):
        pipe = self.run / 'pipe'
        os.mkfifo(pipe)
        manifest = self.capture(book=pipe)
        artifact = next(a for a in manifest['artifacts'] if a['role'] == 'book')
        self.assertEqual(artifact['status'], 'read_error')
        self.assertIn('not a regular file', artifact['error'])
    def test_missing_source_root_rejected(self):
        with self.assertRaises(ValueError):
            snapshot.create_snapshot(self.archive, self.root / 'absent', self.run)
        self.assertFalse(self.archive.exists())

    def test_source_change_is_reported(self):
        original_capture = snapshot.capture_file

        def change_after_capture(*args, **kwargs):
            entry = original_capture(*args, **kwargs)
            if entry['role'] == 'source':
                Path(entry['source_path']).write_bytes(b'changed after copying\n')
            return entry

        with mock.patch.object(snapshot, 'capture_file', side_effect=change_after_capture):
            manifest = self.capture()
        self.assertTrue(any(f['code'] == 'SOURCE_CHANGED_DURING_CAPTURE'
                            for f in manifest['findings']))
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_archive_tampering_is_detected(self):
        manifest = self.capture()
        artifact = manifest['artifacts'][0]
        (self.archive / artifact['archive_path']).write_bytes(b'tampered')
        self.assertFalse(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_manifest_tampering_is_detected(self):
        self.capture()
        with open(self.archive / 'manifest.json', 'a', encoding='utf-8') as handle:
            handle.write(' ')
        self.assertFalse(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_archive_path_traversal_is_rejected(self):
        manifest = self.capture()
        manifest['artifacts'][0]['archive_path'] = '../outside'
        file = self.archive / 'manifest.json'
        file.write_text(json.dumps(manifest), encoding='utf-8')
        (self.archive / 'manifest.sha256').write_text(snapshot.sha256_file(file), encoding='ascii')
        result = snapshot.verify_archive(self.archive)
        self.assertFalse(result['integrity_ok'])
        self.assertTrue(any('Unsafe archive member' in error for error in result['errors']))

    @unittest.skipUnless(os.name == 'posix', 'procfs fixture uses symbolic links')
    def test_process_executable_is_distinct_from_current_path(self):
        proc = self.root / 'proc/123'
        proc.mkdir(parents=True)
        fields = ['S', '1'] + ['0'] * 17 + ['9999999999999999']
        (proc / 'stat').write_text('123 (engine fixture) ' + ' '.join(fields))
        (proc / 'status').write_text('Cpus_allowed_list:\t14-19\n')
        old = self.run / 'old-inode'
        current = self.run / 'new'
        old.write_bytes(b'old running bytes')
        current.write_bytes(b'new path bytes')
        (proc / 'exe').symlink_to(old)
        (proc / 'cwd').symlink_to(self.run)
        manifest = self.capture(binaries=[('new', current)], pids=[123], proc_root=proc.parent)
        process = manifest['processes'][0]
        self.assertEqual(process['status'], 'observed')
        self.assertEqual(process['start_ticks_decimal'], '9999999999999999')
        self.assertEqual(process['guest_cpu_list'], '14-19')
        self.assertEqual(process['matches_current_binary_digests'], [])
        actual = manifest['artifacts'][process['executable_artifact']]
        self.assertEqual(actual['sha256'], hashlib.sha256(old.read_bytes()).hexdigest())
        self.assertTrue(snapshot.verify_archive(self.archive)['integrity_ok'])

    def test_unavailable_process_does_not_invent_identity(self):
        manifest = self.capture(pids=[123], proc_root=self.root / 'no-proc')
        self.assertEqual(manifest['processes'][0]['status'], 'unavailable')
        self.assertNotIn('executable_target', manifest['processes'][0])


if __name__ == '__main__':
    unittest.main()
