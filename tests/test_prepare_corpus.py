"""Small legal fixtures only; never launch an engine or touch a real corpus."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_corpus", ROOT / "scripts/research/prepare_corpus.py")
corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus)

OPENING = ("e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1 f8e7 "
           "f1e1 b7b5 a4b3 d7d6 c2c3 e8g8 h2h3 c6b8 d2d4 b8d7").split()


def make_game(round_id="1.1", *, fen=chess.STARTING_FEN, prefix=None, plies=60,
              result="1/2-1/2", white="new", black="base", event="fixture", seed=11):
    board = chess.Board(fen)
    game = chess.pgn.Game()
    game.setup(board)
    if fen != chess.STARTING_FEN:
        game.headers['FEN'] = fen
    game.headers.update(Event=event, Site="local", Date="2026.10.22", Round=round_id,
                        White=white, Black=black, Result=result, TimeControl="10+0.1")
    node = game
    moves = list(prefix if prefix is not None else (OPENING if fen == chess.STARTING_FEN else []))
    rng = random.Random(seed)
    for ply in range(plies):
        if ply < len(moves):
            move = chess.Move.from_uci(moves[ply])
            if not board.is_legal(move):
                raise AssertionError(f"Bad fixture move {move}")
        else:
            options = list(board.legal_moves)
            rng.shuffle(options)
            move = None
            for candidate in options:
                board.push(candidate)
                terminal = board.is_game_over(claim_draw=False)
                board.pop()
                if not terminal:
                    move = candidate
                    break
            if move is None:
                break
        board.push(move)
        node = node.add_variation(move)
    game.headers["PlyCount"] = str(board.ply() - chess.Board(fen).ply())
    return game


def pgn_text(*games):
    return "\n\n".join(str(game) for game in games) + "\n\n"


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.serial = 0
        self.bench_fens = []
        for square in list(chess.SquareSet(chess.BB_RANK_2 | chess.BB_RANK_3))[:14]:
            board = chess.Board(None)
            board.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
            board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
            board.set_piece_at(square, chess.Piece(chess.PAWN, chess.WHITE))
            self.bench_fens.append(board.fen())
        self.bench = self.folder / "bench.fens"
        self.write_bench()

    def tearDown(self):
        self.temp.cleanup()

    def write_bench(self):
        self.bench.write_text("\n".join(self.bench_fens) + "\n", encoding="utf-8")

    def input(self, text, session="run"):
        self.serial += 1
        path = self.folder / f"pgn-{self.serial}.pgn"
        path.write_text(text, encoding="utf-8", newline="\n")
        return {"session": session, "path": str(path), "sha256": corpus.file_hash(path)}

    def prepare(self, inputs, **options):
        self.serial += 1
        output = self.folder / f"output-{self.serial}"
        defaults = {"seed": "14069920903512239839", "bench_fens": self.bench,
                    "archived_inputs": True}
        defaults.update(options)
        manifest = corpus.prepare(inputs, output, **defaults)
        roots = [json.loads(line) for line in (output / "roots.jsonl").read_text().splitlines()]
        self.assertEqual(corpus.file_hash(output / "roots.jsonl"), manifest["roots"]["sha256"])
        self.assertEqual(corpus.file_hash(output / "manifest.json"),
                         (output / "manifest.sha256").read_text().strip())
        return roots, manifest, output

    def assert_invalid(self, text, message):
        item = self.input(text)
        with self.assertRaisesRegex(ValueError, message):
            self.prepare([item])

    def test_history_castling_and_replay(self):
        roots, manifest, _ = self.prepare([self.input(pgn_text(make_game()))])
        self.assertGreater(len(roots), 0)
        self.assertLessEqual(len(roots), 4)
        self.assertEqual(manifest["seed_decimal"], "14069920903512239839")
        for root in roots:
            board = chess.Board(root["startfen"])
            self.assertIn("e1g1", root["moves"])
            for uci in root["moves"]:
                move = chess.Move.from_uci(uci)
                self.assertTrue(board.is_legal(move))
                board.push(move)
            self.assertEqual(board.fen(en_passant="xfen"), root["position_fen"])
            self.assertGreaterEqual(len(root["moves"]), 12)
            self.assertEqual((len(root["moves"]) - 12) % 8, 0)
            self.assertIn("pre-FEN history unknown", root["history_scope"])
        plies = sorted(len(root["moves"]) for root in roots)
        self.assertTrue(all(b - a >= 8 for a, b in zip(plies, plies[1:])))

    def test_en_passant_capture_prefix(self):
        fen = "4k2r/8/8/3pP3/8/8/8/R3K3 w Qk d6 0 1"
        roots, _, _ = self.prepare([self.input(pgn_text(make_game(fen=fen, prefix=["e5d6"], plies=28)))])
        self.assertTrue(all(root["moves"][0] == "e5d6" for root in roots))
        self.assertTrue(all(root["source_raw_fen"] == fen for root in roots))

    def test_promotion_prefix(self):
        fen = "6k1/P7/8/8/8/8/8/4K2R w K - 0 1"
        roots, _, _ = self.prepare([self.input(pgn_text(make_game(fen=fen, prefix=["a7a8q"], plies=28)))])
        self.assertTrue(all(root["moves"][0] == "a7a8q" for root in roots))

    def test_pseudo_legal_pinned_ep_uses_xfen(self):
        fen = "k3r3/8/8/3pP3/8/8/8/4K2R w K d6 0 2"
        board = chess.Board(fen)
        self.assertTrue(board.has_pseudo_legal_en_passant())
        self.assertFalse(board.has_legal_en_passant())
        roots, _, _ = self.prepare([self.input(pgn_text(make_game(fen=fen, prefix=["e5e6"], plies=28)))])
        self.assertTrue(all(root["startfen"].split()[3] == "d6" for root in roots))

    def test_raw_fen_preserved_when_uncapturable_ep_normalized(self):
        board = chess.Board()
        board.push_uci("e2e4")
        fen = board.fen(en_passant="fen")
        game = make_game(fen=fen, plies=28)
        # Game.setup() defaults to legal-only FEN serialization; restore source bytes.
        game.headers["FEN"] = fen
        roots, _, _ = self.prepare([self.input(pgn_text(game))])
        self.assertTrue(all(root["source_raw_fen"].split()[3] == "e3" for root in roots))
        self.assertTrue(all(root["startfen"].split()[3] == "-" for root in roots))

    def test_paired_openings_and_cross_file_groups(self):
        one = make_game("1.1", seed=11)
        two = make_game("1.2", white="base", black="new", seed=31)
        three = make_game("8.1", seed=59)
        roots, manifest, _ = self.prepare([
            self.input(pgn_text(one, two), "first"),
            self.input(pgn_text(three), "second"),
        ])
        self.assertEqual(len({root["group"] for root in roots}), 1)
        self.assertEqual(manifest["statistics"]["all_game_components"], 1)
        self.assertEqual(len(manifest["games"]), 3)
        keys = [corpus.board_key(chess.Board(root["position_fen"])) for root in roots]
        self.assertEqual(len(keys), len(set(keys)))

    def test_transposed_histories_connect_different_initial_fens(self):
        one = make_game("1.1", plies=36)
        board = chess.Board()
        for uci in OPENING[:2]:
            board.push_uci(uci)
        two = make_game("2.1", fen=board.fen(en_passant="xfen"), prefix=OPENING[2:], plies=34, seed=19)
        roots, manifest, _ = self.prepare([self.input(pgn_text(one, two))])
        self.assertEqual(len({game["opening_id"] for game in manifest["games"]}), 2)
        self.assertEqual(len({root["group"] for root in roots}), 1)

    def test_duplicate_game_key_rejected(self):
        game = make_game()
        self.assert_invalid(pgn_text(game, game), "Duplicate game key")

    def test_mixed_sessions_rejected(self):
        self.assert_invalid(pgn_text(make_game(), make_game("2.1", event="another")),
                            "mixed sessions")
        self.assert_invalid(pgn_text(make_game(), make_game("2.1", white="other")),
                            "mixed sessions")

    def test_incomplete_tail_missing_token_and_star_rejected(self):
        complete = pgn_text(make_game(plies=20))
        tail = pgn_text(make_game("2.1", plies=12))
        truncated = tail.rsplit("1/2-1/2", 1)[0]
        self.assert_invalid(complete + truncated, "Unfinished|complete")
        unfinished = pgn_text(make_game("2.1", plies=12, result="*"))
        self.assert_invalid(complete + unfinished, "Unfinished")

    def test_unclosed_comment_and_skipped_garbage_rejected(self):
        text = pgn_text(make_game(plies=20))
        self.assert_invalid(text.rstrip() + " {unfinished", "Unfinished")
        self.assert_invalid(text.replace("1. e4", "1. flibberty e4"), "skipped|mismatch|parse errors")

    def test_illegal_move_and_initial_board_rejected(self):
        text = pgn_text(make_game(plies=20))
        self.assert_invalid(text.replace("1. e4", "1. e5"), "parse errors|Illegal")
        bad = text.replace('[Result "1/2-1/2"]',
                           '[Result "1/2-1/2"]\n[SetUp "1"]\n[FEN "8/8/8/8/8/8/8/K7 w - - 0 1"]')
        self.assert_invalid(bad, "parse errors|Illegal initial")

    def test_variant_and_bad_plycount_rejected(self):
        text = pgn_text(make_game(plies=20))
        self.assert_invalid(text.replace('[Event "fixture"]',
                                        '[Event "fixture"]\n[Variant "Chess960"]'), "Variants|Chess960")
        self.assert_invalid(text.replace('[PlyCount "20"]', '[PlyCount "19"]'), "PlyCount")

    def test_result_mismatch_and_duplicate_header_rejected(self):
        text = pgn_text(make_game(plies=20))
        self.assert_invalid(text.replace('[Result "1/2-1/2"]', '[Result "1-0"]'), "disagree")
        self.assert_invalid(text.replace('[Round "1.1"]', '[Round "1.1"]\n[Round "2.1"]'),
                            "Duplicate")

    def test_bench_exclusion_ignores_rights_and_clocks(self):
        game = make_game(plies=20)
        board = game.board()
        for move in list(game.mainline_moves())[:12]:
            board.push(move)
        fields = board.fen(en_passant="xfen").split()
        fields[2:] = ["-", "-", "99", "99"]
        self.bench_fens[0] = " ".join(fields)
        self.write_bench()
        roots, manifest, _ = self.prepare([self.input(pgn_text(game))])
        self.assertTrue(all(len(root["moves"]) != 12 for root in roots))
        self.assertEqual(manifest["exclusions"]["bench_roots"], 1)

    def test_bench_source_extracts_only_fixed_initializer(self):
        source = self.folder / "uci.cpp"
        source.write_text('const char* unrelated = "not a FEN";\n'
                          'const std::vector<std::string> BenchFens = {\n' +
                          "".join(json.dumps(fen) + ",\n" for fen in self.bench_fens) +
                          '};\nconst char* another = "also ignored";\n', encoding="utf-8")
        keys, info = corpus.load_bench(source=source)
        self.assertEqual(len(keys), 14)
        self.assertEqual(info["fens"], self.bench_fens)
        source.write_text(source.read_text().replace("BenchFens", "ChangedFens"))
        with self.assertRaisesRegex(ValueError, "BenchFens"):
            corpus.load_bench(source=source)

    def test_determinism_and_outcomes_annotations_do_not_select(self):
        game = make_game(plies=60)
        text = pgn_text(game)
        item = self.input(text)
        first, _, _ = self.prepare([item], max_roots=3)
        repeated, _, _ = self.prepare([item], max_roots=3)
        self.assertEqual(first, repeated)
        changed = text.replace("1/2-1/2", "1-0").replace("1. e4", "1. e4 { [%eval -9.99] }")
        other, _, _ = self.prepare([self.input(changed)], max_roots=3)
        self.assertEqual([(r["id"], r["moves"], r["group"]) for r in first],
                         [(r["id"], r["moves"], r["group"]) for r in other])
        self.assertNotEqual(first[0]["source"]["input_sha256"], other[0]["source"]["input_sha256"])

    def test_input_order_invariance(self):
        inputs = [self.input(pgn_text(make_game(seed=11)), "a"),
                  self.input(pgn_text(make_game(seed=31)), "b")]
        one, _, _ = self.prepare(inputs)
        two, _, _ = self.prepare(list(reversed(inputs)))
        self.assertEqual(one, two)

    def test_expected_hash_archive_ack_output_and_seed_validation(self):
        item = self.input(pgn_text(make_game(plies=20)))
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.prepare([{**item, "sha256": "0" * 64}])
        with self.assertRaisesRegex(ValueError, "archived"):
            self.prepare([item], archived_inputs=False)
        with self.assertRaisesRegex(ValueError, "decimal"):
            self.prepare([item], seed=14069920903512239839)
        with self.assertRaisesRegex(ValueError, "new directory"):
            corpus.prepare([item], self.folder, seed="1", bench_fens=self.bench, archived_inputs=True)

    def test_same_content_under_different_sessions_rejected(self):
        item = self.input(pgn_text(make_game(plies=20)), "a")
        with self.assertRaisesRegex(ValueError, "Duplicate PGN content"):
            self.prepare([item, {**item, "session": "b"}])

    def test_input_drift_detected_before_output(self):
        item = self.input(pgn_text(make_game(plies=20)))
        original = corpus.select_roots
        def mutate(*args):
            result = original(*args)
            with open(item["path"], "a") as stream:
                stream.write("\n")
            return result
        with mock.patch.object(corpus, "select_roots", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during preparation"):
                self.prepare([item])

    def test_label_runner_accepts_generated_histories_and_groups(self):
        roots, _, output = self.prepare([self.input(pgn_text(
            make_game("1.1", seed=11), make_game("1.2", white="base", black="new", seed=31)))])
        spec = importlib.util.spec_from_file_location("label_budget_fixture",
            ROOT / "scripts/research/label_budget.py")
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolves the defining module through sys.modules.
        import sys
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            loaded = module.load_roots(output / "roots.jsonl", 20261022)
        finally:
            del sys.modules[spec.name]
        self.assertEqual({r["id"] for r in loaded}, {r["id"] for r in roots})
        self.assertEqual(len({r["component"] for r in loaded}), 1)
        self.assertEqual(len({r["split"] for r in loaded}), 1)

    def test_header_comment_characters_remain_literal(self):
        game = make_game(plies=20, event="fixture; {literal}")
        roots, manifest, _ = self.prepare([self.input(pgn_text(game))])
        self.assertTrue(roots)
        self.assertEqual(manifest["inputs"][0]["session_signature"]["Event"], "fixture; {literal}")

    def test_cli_uses_new_output_and_records_dependency_hashes(self):
        import contextlib
        import io
        item = self.input(pgn_text(make_game(plies=20)))
        output = self.folder / "cli-output"
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = corpus.main(["--pgn", f"run={item['path']}",
                "--sha256", f"run={item['sha256']}", "--archived-inputs",
                "--bench-fens", str(self.bench), "--seed", "000123",
                "--output", str(output)])
        self.assertEqual(result, 0)
        self.assertGreater(json.loads(stdout.getvalue())["selected_roots"], 0)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["seed_decimal"], "000123")
        self.assertTrue(any(item["path"].endswith("/chess/pgn.py") for item in manifest["modules"]))
        for item in manifest["modules"]:
            self.assertEqual(corpus.file_hash(item["path"]), item["sha256"])


    def test_invalid_source_and_no_eligible_roots(self):
        with self.assertRaises(OSError):
            self.prepare([{"session": "a", "path": self.folder / "missing", "sha256": "0" * 64}])
        with self.assertRaisesRegex(ValueError, "No eligible roots"):
            self.prepare([self.input(pgn_text(make_game(plies=8)))])
        self.bench.write_text("not a fourteen-position bench\n")
        with self.assertRaisesRegex(ValueError, "14 frozen"):
            self.prepare([self.input(pgn_text(make_game(plies=20)))])


if __name__ == "__main__":
    unittest.main()
