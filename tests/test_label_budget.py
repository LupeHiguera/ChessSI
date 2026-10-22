"""No chess engines are run: protocol tests launch a tiny fake UCI subprocess."""
import copy
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research" / "label_budget.py"
spec = importlib.util.spec_from_file_location("label_budget", SCRIPT)
lb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lb
spec.loader.exec_module(lb)

FAKE_UCI = r'''
import sys, time
fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
resets = 0
for line in sys.stdin:
    command = line.strip()
    if command == "uci":
        print("id name fake-fixture", flush=True)
        print("uciok", flush=True)
    elif command == "isready":
        print("readyok", flush=True)
    elif command == "ucinewgame":
        resets += 1
        print("info string resets " + str(resets), flush=True)
    elif command.startswith("position fen "):
        fields = command.split()
        fen = " ".join(fields[2:8])
        if "a1a1" in fields:
            print("info string illegal move a1a1", flush=True)
        if "e2e4" in fields:
            fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    elif command == "d":
        print("Fen: " + fen, flush=True)
    elif command.startswith("go nodes "):
        cap = int(command.split()[-1])
        if cap == 7:
            time.sleep(10)
        elif cap == 17:
            sys.exit(0)
        elif cap == 13:
            print("info depth 1 score cp 999 lowerbound nodes 10", flush=True)
            print("bestmove b1c3", flush=True)
        elif cap == 11:
            print("info depth 1 score mate 3 nodes 5 pv b1c3", flush=True)
            print("bestmove b1c3", flush=True)
        else:
            print("info depth 1 score cp 5 nodes 8 time 1 pv e2e4", flush=True)
            print("info depth 2 score cp 999 lowerbound nodes 16 pv e2e4", flush=True)
            print("info depth 2 score cp 12 nodes 20 time 2 pv b1c3", flush=True)
            print("info depth 3 score cp -999 upperbound nodes 31 pv e2e4", flush=True)
            print("bestmove b1c3", flush=True)
    elif command == "quit":
        break
'''

def root(fen=lb.START_FEN):
    key, phase = lb.parse_fen(fen)
    return {"id": "r", "group": "g", "startfen": fen, "position_fen": fen,
            "moves": [], "board_key": key, "phase": phase}

def fixture_fen(index):
    cells = ["."] * 64
    cells[0], cells[63] = "K", "k"
    for bit in range(8):
        if (index + 1) & (1 << bit):
            cells[8 + bit] = "P"
    ranks = []
    for rank in range(7, -1, -1):
        rendered, empty = "", 0
        for char in cells[rank * 8:rank * 8 + 8]:
            if char == ".":
                empty += 1
            else:
                rendered += (str(empty) if empty else "") + char
                empty = 0
        ranks.append(rendered + (str(empty) if empty else ""))
    return "/".join(ranks) + " w - - 0 1"

def result(score, cap, drift=10, mate=False):
    kind = "mate" if mate else "cp"
    infos = [lb.parse_info(f"info depth {depth} score {kind} {score - drift * (3-depth)} nodes {depth*10} pv e2e4")
             for depth in (1, 2, 3)]
    return {"status": kind, "last": infos[-1], "infos": infos,
            "requested_nodes": cap, "charged_nodes": cap, "actual_nodes": None}

def dataset():
    cfg = lb.Config(bootstrap=100)
    roots = []
    for index in range(160):
        item = root(fixture_fen(index))
        item.update(id=f"r{index}", group=f"g{index}")
        roots.append(item)
    lb.assign_groups(roots, cfg.seed)
    labels = []
    for index, item in enumerate(roots):
        s0, delta = 3 * index - 240, 20 + (index % 7) * 25
        labels.append({"id": item["id"], "tier": "cheap", "result": result(s0, cfg.cheap, delta // 3)})
        labels.append({"id": item["id"], "tier": "replacement", "result": result(s0 + delta, cfg.replacement)})
        if item["split"] == "test":
            s2 = s0 if index % 3 == 0 else s0 + delta + 10
            labels.append({"id": item["id"], "tier": "audit", "result": result(s2, cfg.audit)})
    return {"schema": lb.SCHEMA, "protocol": lb.PROTOCOL, "status": "complete", "config": asdict(cfg),
            "engine_sha256": "fixture-only", "analysis_script_sha256": lb.file_hash(SCRIPT), "roots": roots}, labels

class ParsingAndGroups(unittest.TestCase):
    def test_bound_and_multipv_are_not_exact_labels(self):
        infos = [lb.parse_info(line) for line in (
            "info depth 2 score cp 7 nodes 20 pv a2a3",
            "info depth 3 score cp 999 lowerbound nodes 31",
            "info depth 4 multipv 2 score cp 400 nodes 40")]
        self.assertEqual([i["score"] for i in lb.completed_scores(infos)], [7])
        self.assertIsNone(lb.parse_info("info string score cp 5"))
        self.assertIsNone(lb.parse_info("info depth x score cp 5"))

    def test_fen_and_command_injection_rejected(self):
        with self.assertRaises(ValueError):
            lb.parse_fen(lb.START_FEN + "\ngo infinite")
        with self.assertRaises(ValueError):
            lb.parse_fen("8/8/8/8/8/8/8/7 w - - 0 1")
        self.assertEqual(lb.parse_fen(lb.START_FEN)[1], 24)

    def test_union_crosses_game_opening_and_board_identifiers(self):
        roots = [{"id": str(i), "group": str(i), "board_key": str(i)} for i in range(4)]
        roots[0]["game_id"] = roots[1]["game_id"] = "game"
        roots[1]["opening_id"] = roots[2]["opening_id"] = "opening"
        roots[2]["board_key"] = roots[3]["board_key"] = "transposition"
        lb.assign_groups(roots, 7)
        self.assertEqual(len({r["component"] for r in roots}), 1)
        reversed_roots = list(reversed(copy.deepcopy(roots)))
        lb.assign_groups(reversed_roots, 7)
        self.assertEqual({r["id"]: r["split"] for r in roots}, {r["id"]: r["split"] for r in reversed_roots})

    def test_input_preserves_history_requires_final_fen(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "roots.jsonl"
            item = root()
            item["moves"] = ["e2e4"]
            del item["position_fen"]
            p.write_text(json.dumps(item) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "position_fen required"):
                lb.load_roots(p, 1)
            item["position_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
            p.write_text(json.dumps(item) + "\n", encoding="utf-8")
            self.assertEqual(lb.load_roots(p, 1)[0]["moves"], ["e2e4"])
            item["moves"] = ["e2e4\ngo infinite"]
            p.write_text(json.dumps(item) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                lb.load_roots(p, 1)

class FakeProtocol(unittest.TestCase):
    def open_runner(self, timeout=1):
        return lb.UCIProcess([sys.executable, "-u", "-c", FAKE_UCI], lb.Config(timeout=timeout))

    def test_fresh_tt_exact_score_and_cap_accounting(self):
        with self.open_runner() as runner:
            first = runner.search(root(), 32)
            second = runner.search(root(), 32)
            self.assertEqual(first["last"]["score"], 12)
            self.assertEqual(first["last_completed_nodes"], 20)
            self.assertEqual(first["charged_nodes"], 32)
            self.assertIsNone(first["actual_nodes"])
            self.assertIn("< info string resets 2", second["transcript"])
            self.assertEqual(second["transcript"][0:2], ["> ucinewgame", "> isready"])
        self.assertIsNotNone(runner.process.poll())

    def test_mates_and_bound_only_have_separate_status(self):
        with self.open_runner() as runner:
            self.assertEqual(runner.search(root(), 11)["status"], "mate")
            self.assertEqual(runner.search(root(), 13)["status"], "no_completed_score")

    def test_replayed_fen_mismatch_aborts(self):
        with self.open_runner() as runner:
            item = root()
            item["moves"] = ["e2e4"]
            with self.assertRaisesRegex(lb.UCIError, "Replayed FEN"):
                runner.search(item, 32)
        self.assertIsNotNone(runner.process.poll())

    def test_history_replay_and_validation(self):
        with self.open_runner() as runner:
            item = root()
            item["moves"] = ["e2e4"]
            item["position_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
            answer = runner.search(item, 32)
            self.assertTrue(any(line.endswith("moves e2e4") for line in answer["transcript"]))

    def test_en_passant_normalization_mismatch_is_rejected(self):
        with self.open_runner() as runner:
            item = root()
            item["moves"] = ["e2e4"]
            item["position_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
            with self.assertRaisesRegex(lb.UCIError, "Replayed FEN"):
                runner.search(item, 32)
    def test_timeout_kills_child_and_returns_promptly(self):
        started = time.monotonic()
        with self.open_runner(timeout=0.15) as runner:
            with self.assertRaisesRegex(lb.UCIError, "timed out"):
                runner.search(root(), 7)
        self.assertIsNotNone(runner.process.poll())
        self.assertLess(time.monotonic() - started, 3)

    def test_illegal_move_and_unexpected_exit_abort(self):
        with self.open_runner() as runner:
            item = root()
            item["moves"] = ["a1a1"]
            with self.assertRaisesRegex(lb.UCIError, "illegal move"):
                runner.search(item, 32)
        with self.open_runner() as runner:
            with self.assertRaisesRegex(lb.UCIError, "exited"):
                runner.search(root(), 17)

class OfflineAnalysis(unittest.TestCase):
    def test_bounded_transform_and_ridge(self):
        self.assertEqual(lb.bounded_score(0), 0.5)
        self.assertEqual(lb.bounded_score(1e10), 1)
        self.assertGreaterEqual(lb.bounded_score(-1e10), 0)
        self.assertLess(lb.bounded_score(-1e10), 1e-300)
        model = lb.fit_ridge([[0], [1], [2]], [2, 4, 6], 0.01)
        self.assertAlmostEqual(lb.predict(model, [1]), 4, places=10)

    def test_analysis_keeps_negative_utility_and_all_controls(self):
        manifest, labels = dataset()
        report = lb.analyze_data(manifest, labels)
        self.assertTrue(any(row["utility"] < 0 for row in report["utility_rows"]))
        self.assertIn("bounded_volatility", report["policies"])
        self.assertIn("context_only", report["policies"])
        self.assertEqual(report["effective_selection_fraction"],
            report["policies"]["learned"]["selected_count"] / report["counts"]["test_candidates"])
        self.assertEqual(report["research_charged_nodes"], sum(label["result"]["charged_nodes"] for label in labels))
        self.assertIsNone(report["elo_claim"])

    def test_heldout_labels_never_change_training_or_selection(self):
        manifest, labels = dataset()
        first = lb.analyze_data(manifest, labels)
        selected = first["policies"]["learned"]["selected_ids"][0]
        heldout = {r["id"] for r in manifest["roots"] if r["split"] == "test"}
        for tier in ("replacement", "audit"):
            with self.subTest(tier=tier):
                changed = copy.deepcopy(labels)
                for label in changed:
                    if label["tier"] == tier and label["id"] in heldout:
                        label["result"] = result(500, getattr(lb.Config(), tier), mate=label["id"] == selected)
                second = lb.analyze_data(manifest, changed)
                self.assertEqual(first["selector"], second["selector"])
                self.assertEqual(first["context_only_selector"], second["context_only_selector"])
                for name in first["policies"]:
                    self.assertEqual(first["policies"][name]["selected_ids"], second["policies"][name]["selected_ids"])
                self.assertEqual(first["counterfactual_policy_charged_nodes"], second["counterfactual_policy_charged_nodes"])
                self.assertLess(second["counts"]["auditable_test"], first["counts"]["auditable_test"])
                for control in ("uniform_expected", "no_replacement"):
                    self.assertGreater(second["comparisons"][control]["missing_coefficient_mass"], 0)

    def test_less_harmful_than_other_selectors_cannot_pass(self):
        # Adversarial synthetic evidence, not a claim about engine behavior.
        manifest, labels = dataset()
        manifest["config"]["bootstrap"] = 1000
        for label in labels:
            index = int(label["id"][1:])
            switches, drift = index % 3, 1 + (index * 7) % 19
            if label["tier"] == "cheap":
                label["result"] = result(0, lb.Config().cheap, drift)
                moves = (("e2e4", "e2e4", "e2e4"), ("e2e4", "d2d4", "d2d4"),
                         ("e2e4", "d2d4", "e2e4"))[switches]
                for info, move in zip(label["result"]["infos"], moves):
                    info["pv"] = [move]
            else:
                label["result"] = result(20 + 100 * switches, getattr(lb.Config(), label["tier"]))
        initial = lb.analyze_data(manifest, labels)
        learned = set(initial["policies"]["learned"]["selected_ids"])
        heldout = {r["id"] for r in manifest["roots"] if r["split"] == "test"}
        for label in labels:
            if label["id"] in heldout and label["tier"] in ("replacement", "audit"):
                value = 0 if label["tier"] == "audit" else 1 if label["id"] in learned else 400
                label["result"] = result(value, getattr(lb.Config(), label["tier"]))
        report = lb.analyze_data(manifest, labels)
        self.assertGreaterEqual(report["counts"]["test_groups"], lb.Config().minimum_test_groups)
        self.assertTrue(all(row["utility"] < 0 for row in report["utility_rows"]))
        for name in ("uniform_expected", "raw_volatility", "bounded_volatility", "context_only"):
            self.assertGreater(report["comparisons"][name]["worst_case_missing_interval"][0], 0)
            self.assertGreater(report["comparisons"][name]["sensitivity_group_bootstrap_95"][0], 0)
        self.assertLess(report["comparisons"]["no_replacement"]["worst_case_missing_interval"][1], 0)
        self.assertEqual(report["stage_gate"], "not_passed_or_inconclusive")
        self.assertEqual(report["policies"]["no_replacement"]["selected_count"], 0)
        self.assertEqual(report["no_replacement_charged_nodes"], len(heldout) * lb.Config().cheap)
        self.assertEqual(report["research_charged_nodes"], sum(l["result"]["charged_nodes"] for l in labels))
        self.assertEqual(initial["selector"], report["selector"])
        self.assertEqual(learned, set(report["policies"]["learned"]["selected_ids"]))

    def test_missing_data_worst_case_uses_all_root_denominator(self):
        rows = [{"id": "a", "group": "a", "utility": 0.2},
                {"id": "b", "group": "b", "utility": None}]
        answer = lb.compare_policy(rows, {"a"}, {"b"}, 0.5, lb.Config(bootstrap=100))
        self.assertAlmostEqual(answer["observed_improvement_contribution"], 0.1)
        self.assertAlmostEqual(answer["missing_coefficient_mass"], 0.5)
        self.assertAlmostEqual(answer["worst_case_missing_interval"][0], -0.4)

    def test_changed_analysis_source_or_protocol_is_rejected(self):
        manifest, labels = dataset()
        manifest["analysis_script_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "preregistered"):
            lb.analyze_data(manifest, labels)
        manifest, labels = dataset()
        manifest["protocol"] = "earlier-protocol"
        with self.assertRaisesRegex(ValueError, "protocol"):
            lb.analyze_data(manifest, labels)

    def test_excluded_cheap_roots_still_cost_screening(self):
        manifest, labels = dataset()
        target = next(r["id"] for r in manifest["roots"] if r["split"] == "test")
        for label in labels:
            if label["id"] == target and label["tier"] == "cheap":
                label["result"] = result(3, lb.Config().cheap, mate=True)
        report = lb.analyze_data(manifest, labels)
        self.assertEqual(report["counterfactual_policy_charged_nodes"] - report["candidate_domain_only_charged_nodes"], lb.Config().cheap)
    def test_duplicate_and_missing_labels_rejected(self):
        manifest, labels = dataset()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            lb.analyze_data(manifest, labels + [labels[0]])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            lb.analyze_data(manifest, labels[:-1])
        changed = copy.deepcopy(manifest)
        changed["roots"][0]["split"] = "impossible"
        with self.assertRaisesRegex(ValueError, "grouping"):
            lb.analyze_data(changed, labels)

    def test_collection_accounting_and_nonoverwrite_with_mock_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source, executable, output = tmp / "roots.jsonl", tmp / "frozen", tmp / "pilot"
            source.write_text(json.dumps(root()) + "\n", encoding="utf-8")
            executable.write_bytes(b"not executed; mocked runner")
            runner = unittest.mock.MagicMock()
            runner.search.side_effect = lambda r, cap: result(10, cap)
            runner.__enter__.return_value = runner
            with patch.object(lb, "UCIProcess", return_value=runner):
                manifest = lb.collect(source, executable, output, lb.Config())
                self.assertEqual(manifest["status"], "complete")
                lines = [json.loads(line) for line in (output / "labels.jsonl").read_text().splitlines()]
                self.assertEqual(manifest["charged_nodes"], sum(line["result"]["charged_nodes"] for line in lines))
                with self.assertRaises(FileExistsError):
                    lb.collect(source, executable, output, lb.Config())

if __name__ == "__main__":
    unittest.main()
