"""Hand-computed fixtures only; run with: python -m unittest -v test_analyze.py"""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

import analyze

BOARD_A = "4k3/8/8/8/8/8/4P3/4K3"
BOARD_B = "4k3/8/8/8/8/4P3/8/4K3"
BOARD_C = "4k3/8/8/8/4P3/8/8/4K3"


def line(result=0, *, board=BOARD_A, full=10, half=0, side="w", score=0, static=0):
    return f"{board} {side} - - {half} {full} | {score} | {result} | {static}\n".encode()


def tail():
    return line(board=BOARD_C, full=1)


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_manifest(self, sources):
        streams = []
        for i, content in enumerate(sources):
            path = self.home / f"writer-{i}.txt"
            path.write_bytes(content)
            streams.append({"writer_id": f"writer-{i}", "snapshot_path": str(path),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "raw_rows": len(content.splitlines()), "source_start": 0})
        manifest = self.home / "manifest.json"
        manifest.write_text(json.dumps({"streams": streams}), encoding="utf-8")
        return manifest

    def execute(self, sources):
        result = analyze.run(self.make_manifest(sources), self.home / "output")
        records = [json.loads(x) for x in (self.home / "output" / "per_identity.jsonl").read_text().splitlines()]
        return result, records

    def test_three_groups_hand_computed_leave_one_group_out(self):
        result, records = self.execute([line(0) + line(0.5) + line(1) + tail()])
        self.assertEqual(result["counts"]["eligible_full_fen_identities"], 1)
        self.assertEqual(result["counts"]["held_out_conservative_groups"], 3)
        self.assertEqual(result["counts"]["excluded_final_group_rows"], 1)
        self.assertEqual(records[0]["held_out_group_count"], 3)
        self.assertAlmostEqual(result["primary"]["M"]["y2"], 0.0234375)
        self.assertAlmostEqual(result["primary"]["L"]["y2"], 0.03125)
        self.assertAlmostEqual(result["primary"]["relative_reduction"], 0.25)
        self.assertAlmostEqual(result["primary"]["M"]["r2"], 0.375)
        self.assertAlmostEqual(result["primary"]["L"]["r2"], 0.5)
        for arm in ("M", "L"):
            self.assertEqual(result["primary"][arm]["q2"], 0)
            self.assertEqual(result["primary"][arm]["qr"], 0)
        self.assertEqual(result["status"], "inconclusive_coverage")

    def test_black_complements_score_and_result_without_changing_squared_errors(self):
        parsed = analyze.parse_record(line(1, side="b", score=400))
        self.assertAlmostEqual(parsed["q"], 1 / (1 + math.e))
        self.assertEqual(parsed["r"], 0)
        result, _ = self.execute([line(0, side="b") + line(0.5, side="b") + line(1, side="b") + tail()])
        self.assertAlmostEqual(result["primary"]["M"]["y2"], 0.0234375)
        self.assertAlmostEqual(result["primary"]["L"]["y2"], 0.03125)

    def test_identity_weighting_not_pooled_row_weighting(self):
        source = line(0) + line(0.5) + line(1)
        source += line(0, board=BOARD_B, full=12) * 4 + tail()
        result, records = self.execute([source])
        self.assertEqual(sorted(x["held_out_group_count"] for x in records), [3, 4])
        self.assertAlmostEqual(result["primary"]["M"]["y2"], 0.0234375 / 2)
        self.assertAlmostEqual(result["primary"]["L"]["y2"], 0.03125 / 2)
        self.assertNotAlmostEqual(result["primary"]["M"]["y2"], 0.0234375 * 3 / 7)

    def test_writer_strata_use_held_out_writer_and_identity_means(self):
        result, _ = self.execute([line(r) + tail() for r in (0, 0.5, 1)])
        self.assertEqual(result["counts"]["held_out_conservative_groups"], 3)
        self.assertEqual([result["writers"][f"writer-{i}"]["count"] for i in range(3)], [1, 1, 1])
        self.assertAlmostEqual(result["writers"]["writer-0"]["M"]["y2"], 0.1875**2)
        self.assertAlmostEqual(result["writers"]["writer-1"]["M"]["y2"], 0)
        self.assertAlmostEqual(result["writers"]["writer-2"]["L"]["y2"], 0.25**2)
        self.assertAlmostEqual(result["primary"]["M"]["y2"], 0.0234375)
        self.assertTrue(result["qualifying_writer_condition_vacuous"])

    def test_increasing_ply_constant_result_is_one_conservative_group(self):
        source = line(0, full=10) + line(0, board=BOARD_B, full=11)
        source += line(0, board=BOARD_C, full=12) + line(0, full=1)
        result, _ = self.execute([source])
        self.assertEqual(result["counts"]["conservative_groups"], 2)
        self.assertEqual(result["counts"]["complete_groups"], 1)
        self.assertEqual(result["counts"]["retained_complete_group_rows"], 3)
        self.assertEqual(result["counts"]["eligible_full_fen_identities"], 0)

    def test_result_change_is_boundary_even_when_ply_increases(self):
        source = line(0, full=10) + line(1, board=BOARD_B, full=11)
        source += line(1, board=BOARD_C, full=12)
        result, _ = self.execute([source])
        self.assertEqual(result["counts"]["conservative_groups"], 2)
        self.assertEqual(result["counts"]["retained_complete_group_rows"], 1)
        self.assertEqual(result["counts"]["excluded_final_group_rows"], 2)

    def test_final_group_drop_prevents_false_three_group_eligibility(self):
        result, records = self.execute([line(0) + line(0.5) + line(1)])
        self.assertEqual(result["counts"]["complete_groups"], 2)
        self.assertEqual(result["counts"]["eligible_full_fen_identities"], 0)
        self.assertEqual(records, [])

    def test_storage_one_vote_keeps_first_source_offset(self):
        # Defensive database invariant. In a valid raw stream, a repeated exact
        # full FEN itself certifies a new group because absolute ply repeats.
        db = analyze.create_db(self.home / "defensive.sqlite")
        try:
            first, later = analyze.parse_record(line(0)), analyze.parse_record(line(1))
            self.assertTrue(analyze.insert_vote(db, first, 7, 10))
            self.assertFalse(analyze.insert_vote(db, later, 7, 90))
            value = db.execute("SELECT source_offset,r,y FROM observations").fetchone()
            self.assertEqual(value, (10, 0, 0.375))
        finally:
            db.close()

    def test_alias_denominator_includes_nonzero_clock_and_excluded_tail(self):
        source = line(0, full=10, half=0)
        source += line(0, full=11, half=1) + line(0, full=12, half=0)
        source += line(0, board=BOARD_B, full=1) + line(0, board=BOARD_C, full=2)
        result, _ = self.execute([source])
        c = result["counts"]
        self.assertEqual(c["denominator_distinct_key4_all_raw_rows"], 3)
        self.assertEqual(c["key4_with_halfmove_alias_all_raw_rows"], 1)
        self.assertEqual(c["key4_with_absolute_ply_alias_all_raw_rows"], 1)
        self.assertEqual(c["retained_clock_zero_rows"], 2)
        self.assertEqual(c["excluded_final_group_rows"], 2)
        self.assertEqual(c["eligible_full_fen_identities"], 0)

    def test_static_consistency_and_blend_component_identity(self):
        source = line(0, score=-400, static=7) + line(0.5, score=0, static=7)
        source += line(1, score=400, static=8) + tail()
        result, _ = self.execute([source])
        self.assertEqual(result["static_inputs_with_nonzero_range"], 1)
        for arm in ("M", "L"):
            m = result["primary"][arm]
            self.assertAlmostEqual(m["y2"], 0.5625 * m["q2"] + 0.0625 * m["r2"] + 0.375 * m["qr"])
        ranges = [json.loads(x) for x in (self.home / "output" / "static_ranges.jsonl").read_text().splitlines()]
        row = next(x for x in ranges if x["input_key"] == BOARD_A + " w")
        self.assertEqual(row["range_cp"], 1)

    def test_bin_rule_uses_full_big_endian_sha256(self):
        value = int(hashlib.sha256(b"20261024|alpha|123").hexdigest(), 16) % 5
        self.assertEqual(analyze.bucket("alpha", 123), value)

    def test_hash_mismatch_invalidates_run(self):
        path = self.make_manifest([line(0) + tail()])
        obj = json.loads(path.read_text())
        obj["streams"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "mismatch"):
            analyze.run(path, self.home / "output")
        self.assertFalse((self.home / "output" / "summary.json").exists())
        self.assertEqual(json.loads((self.home / "output" / "failure.json").read_text())["status"], "invalid_run")

    def test_wrong_row_count_and_missing_hash_rejected(self):
        path = self.make_manifest([line(0) + tail()])
        obj = json.loads(path.read_text())
        obj["streams"][0]["raw_rows"] = 1
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "extra rows"):
            analyze.run(path, self.home / "output")
        del obj["streams"][0]["sha256"]
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "sha256"):
            analyze.validate_manifest(path)

    def test_bad_records_nonfinite_values_and_incomplete_line_rejected(self):
        bad = [
            line(0).replace(b" | 0 | 0 |", b" | nan | 0 |"),
            line(0).replace(b" | 0 | 0 |", b" | 0 | nan |"),
            line(0).replace(b" | 0 | 0 |", b" | 0 | inf |"),
            line(0).replace(b" | 0 | 0 |", b" | 0 | 0.2 |"),
            line(0)[:-1], b"not a fen | 0 | 0\n",
            line(0, half=-1), line(0, full=0), line(0, score=2**40),
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    analyze.parse_record(raw)

    def test_manifest_boundaries_and_cap_are_checked_before_output(self):
        path = self.make_manifest([line(0) + tail()])
        obj = json.loads(path.read_text())
        obj["streams"][0]["source_start"] = 9
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "source_start"):
            analyze.run(path, self.home / "output")
        obj["streams"][0]["source_start"] = 0
        obj["streams"][0]["raw_rows"] = analyze.MAX_ROWS + 1
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "cap"):
            analyze.run(path, self.home / "output")
        self.assertFalse((self.home / "output").exists())


if __name__ == "__main__":
    unittest.main()
