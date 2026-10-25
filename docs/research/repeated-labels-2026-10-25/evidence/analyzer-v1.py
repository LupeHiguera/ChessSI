#!/usr/bin/env python3
"""Bounded, latest-teacher-only repeated-label pilot (PR29 protocol).

Usage: python analyze.py MANIFEST.json OUTPUT_DIRECTORY
The caller supplies immutable original-writer prefix snapshots and enforces the
2 GiB process memory limit/CPU affinity. This program never reads original live
data paths. Source order is manifest stream order, then byte offset.
Bins: int.from_bytes(SHA256(UTF8("20261024|writer_id|start_offset")), "big") % 5.
Output-directory creation is exclusive: no existing artifacts are overwritten.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

MAX_ROWS = 2_000_000
MAX_LINE = 65536
VERSION = "repeated-label-latest-only-v1"
COMPONENTS = ("y2", "q2", "r2", "qr")


def bucket(writer, offset):
    msg = f"20261024|{writer}|{offset}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(msg).digest(), "big") % 5


def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def parse_record(raw):
    if not raw.endswith(b"\n"):
        raise ValueError("snapshot must end in a complete newline-terminated record")
    fields = [s.strip() for s in raw.decode("utf-8").split("|")]
    if len(fields) not in (3, 4):
        raise ValueError("expected FEN | score | result [| static]")
    parts = fields[0].split()
    if len(parts) != 6 or parts[1] not in ("w", "b"):
        raise ValueError("expected full six-field FEN and valid side")
    ranks = parts[0].split("/")
    if len(ranks) != 8:
        raise ValueError("invalid FEN board")
    for rank in ranks:
        if any(c not in "12345678PNBRQKpnbrqk" for c in rank):
            raise ValueError("invalid FEN board character")
        if sum(int(c) if c.isdigit() else 1 for c in rank) != 8:
            raise ValueError("invalid FEN rank length")
    if parts[2] != "-" and (
        any(c not in "KQkq" for c in parts[2]) or len(set(parts[2])) != len(parts[2])
    ):
        raise ValueError("invalid castling field")
    if parts[3] != "-" and (
        len(parts[3]) != 2 or parts[3][0] not in "abcdefgh" or parts[3][1] not in "36"
    ):
        raise ValueError("invalid en-passant field")
    half, full = int(parts[4]), int(parts[5])
    if not (0 <= half <= 2147483647 and 1 <= full <= 2147483647):
        raise ValueError("invalid move counters")
    score, result = int(fields[1]), float(fields[2])
    if result not in (0.0, 0.5, 1.0):
        raise ValueError("result must be 0, 0.5 or 1")
    static = int(fields[3]) if len(fields) == 4 else None
    if not (-2147483648 <= score <= 2147483647) or (static is not None and not -2147483648 <= static <= 2147483647):
        raise ValueError("score outside C++ int32 range")
    q, r = sigmoid(score / 400.0), result
    if parts[1] == "b":
        q, r = 1.0 - q, 1.0 - r
    return {
        "fen": " ".join(parts), "key4": " ".join(parts[:4]),
        "input_key": " ".join(parts[:2]), "half": half,
        "ply": 2 * (full - 1) + (parts[1] == "b"),
        "raw_result": result, "q": q, "r": r, "y": 0.75 * q + 0.25 * r,
        "score": score, "static": static,
    }


def validate_manifest(path):
    raw = Path(path).read_bytes()
    manifest = json.loads(raw)
    streams = manifest.get("streams")
    if not isinstance(streams, list) or not streams:
        raise ValueError("manifest needs a nonempty streams list")
    writers, paths, total = set(), set(), 0
    for stream in streams:
        writer = stream.get("writer_id")
        if not isinstance(writer, str) or not writer or "|" in writer:
            raise ValueError("writer_id must be nonempty text without |")
        if writer in writers:
            raise ValueError("duplicate writer_id")
        writers.add(writer)
        if stream.get("source_start") != 0:
            raise ValueError("only original-stream prefixes (source_start=0) qualify")
        count = stream.get("raw_rows")
        if type(count) is not int or count <= 0:
            raise ValueError("raw_rows must be a positive integer")
        total += count
        digest = stream.get("sha256", "")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        snapshot = Path(stream["snapshot_path"])
        if not snapshot.is_absolute():
            snapshot = Path(path).resolve().parent / snapshot
        snapshot = snapshot.resolve()
        if snapshot in paths:
            raise ValueError("same snapshot path assigned to more than one writer")
        paths.add(snapshot)
        stream["_snapshot"] = snapshot
    if total > MAX_ROWS:
        raise ValueError("manifest exceeds the 2,000,000 raw-row cap")
    return manifest, raw


def create_db(path):
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA temp_store=FILE")
    temporary = str(path.parent.resolve()).replace("\'", "\'\'")
    db.execute("PRAGMA temp_store_directory = \'" + temporary + "\'")
    db.execute("PRAGMA cache_size=-32768")
    db.execute("PRAGMA mmap_size=0")
    db.executescript("""
        CREATE TABLE streams(id INTEGER PRIMARY KEY, writer TEXT UNIQUE, path TEXT, digest TEXT, raw_rows INTEGER);
        CREATE TABLE groups(id INTEGER PRIMARY KEY, stream INTEGER, start_offset INTEGER,
                            bin INTEGER, complete INTEGER DEFAULT 0, raw_rows INTEGER DEFAULT 0,
                            clock_zero_rows INTEGER DEFAULT 0);
        CREATE TABLE key4_counts(key4 TEXT PRIMARY KEY, n INTEGER, min_half INTEGER,
                                 max_half INTEGER, min_ply INTEGER, max_ply INTEGER) WITHOUT ROWID;
        CREATE TABLE key4_groups(key4 TEXT, group_id INTEGER, PRIMARY KEY(key4,group_id)) WITHOUT ROWID;
        CREATE TABLE observations(id INTEGER PRIMARY KEY, fen TEXT, key4 TEXT, group_id INTEGER,
                                  source_offset INTEGER, q REAL, r REAL, y REAL,
                                  UNIQUE(fen,group_id));
        CREATE TABLE static_inputs(input_key TEXT PRIMARY KEY, n INTEGER,
                                   minimum INTEGER, maximum INTEGER) WITHOUT ROWID;
    """)
    return db


def insert_vote(db, rec, group_id, offset):
    """Earliest source offset gets the sole vote within an identity/group."""
    cur = db.execute(
        "INSERT OR IGNORE INTO observations(fen,key4,group_id,source_offset,q,r,y) VALUES(?,?,?,?,?,?,?)",
        (rec["fen"], rec["key4"], group_id, offset, rec["q"], rec["r"], rec["y"]),
    )
    return cur.rowcount == 1


def ingest(db, streams):
    next_group = 0
    duplicates = 0
    static_n = 0
    correction_sum = 0
    correction_min = correction_max = None
    for sid, stream in enumerate(streams):
        db.execute("INSERT INTO streams VALUES(?,?,?,?,?)",
                   (sid, stream["writer_id"], str(stream["_snapshot"]), stream["sha256"], stream["raw_rows"]))
        offset = count = group_rows = zero_rows = 0
        current = None
        previous_ply = previous_result = None
        digest = hashlib.sha256()
        with stream["_snapshot"].open("rb") as source:
            while True:
                raw = source.readline(MAX_LINE + 1)
                if not raw:
                    break
                if len(raw) > MAX_LINE:
                    raise ValueError("record exceeds bounded line buffer")
                count += 1
                if count > stream["raw_rows"]:
                    raise ValueError(f"{stream['writer_id']}: snapshot has extra rows")
                digest.update(raw)
                rec = parse_record(raw)
                boundary = current is None or rec["ply"] <= previous_ply or rec["raw_result"] != previous_result
                if boundary:
                    if current is not None:
                        db.execute("UPDATE groups SET complete=1,raw_rows=?,clock_zero_rows=? WHERE id=?",
                                   (group_rows, zero_rows, current))
                    current = next_group
                    next_group += 1
                    group_rows = zero_rows = 0
                    db.execute("INSERT INTO groups(id,stream,start_offset,bin) VALUES(?,?,?,?)",
                               (current, sid, offset, bucket(stream["writer_id"], offset)))
                group_rows += 1
                zero_rows += rec["half"] == 0
                db.execute("""
                    INSERT INTO key4_counts VALUES(?,1,?,?,?,?)
                    ON CONFLICT(key4) DO UPDATE SET n=n+1,
                    min_half=min(min_half,excluded.min_half), max_half=max(max_half,excluded.max_half),
                    min_ply=min(min_ply,excluded.min_ply), max_ply=max(max_ply,excluded.max_ply)
                """, (rec["key4"], rec["half"], rec["half"], rec["ply"], rec["ply"]))
                db.execute("INSERT OR IGNORE INTO key4_groups VALUES(?,?)", (rec["key4"], current))
                if rec["half"] == 0:
                    duplicates += not insert_vote(db, rec, current, offset)
                if rec["static"] is not None:
                    db.execute("""
                        INSERT INTO static_inputs VALUES(?,1,?,?)
                        ON CONFLICT(input_key) DO UPDATE SET n=n+1,
                        minimum=min(minimum,excluded.minimum), maximum=max(maximum,excluded.maximum)
                    """, (rec["input_key"], rec["static"], rec["static"]))
                    correction = rec["score"] - rec["static"]
                    static_n += 1
                    correction_sum += correction
                    correction_min = correction if correction_min is None else min(correction_min, correction)
                    correction_max = correction if correction_max is None else max(correction_max, correction)
                previous_ply, previous_result = rec["ply"], rec["raw_result"]
                offset += len(raw)
                if count % 5000 == 0:
                    db.commit()
        if count != stream["raw_rows"] or digest.hexdigest() != stream["sha256"]:
            raise ValueError(f"{stream['writer_id']}: raw-row count or SHA-256 mismatch")
        if current is not None:
            # Without a following certified boundary, even a complete-looking tail is excluded.
            db.execute("UPDATE groups SET raw_rows=?,clock_zero_rows=? WHERE id=?",
                       (group_rows, zero_rows, current))
        db.commit()
    return {"duplicate_identity_group_votes_ignored": duplicates,
            "static_rows_all_sampled": static_n,
            "white_search_minus_static_cp": {
                "count": static_n, "mean": correction_sum / static_n if static_n else None,
                "minimum": correction_min, "maximum": correction_max}}


class Metrics:
    def __init__(self):
        self.n = 0
        self.values = {a: {c: 0.0 for c in COMPONENTS} for a in ("M", "L")}

    def add_errors(self, predictions, target):
        self.n += 1
        for arm, (q, r, y) in predictions.items():
            eq, er, ey = q - target[0], r - target[1], y - target[2]
            for name, value in (("y2", ey * ey), ("q2", eq * eq), ("r2", er * er), ("qr", eq * er)):
                self.values[arm][name] += value

    def add_identity(self, metric):
        if not metric.n:
            return
        self.n += 1
        for arm in self.values:
            for component in COMPONENTS:
                self.values[arm][component] += metric.values[arm][component] / metric.n

    def report(self):
        arms = {a: {c: self.values[a][c] / self.n if self.n else None for c in COMPONENTS}
                for a in self.values}
        delta = arms["M"]["y2"] - arms["L"]["y2"] if self.n else None
        relative = -delta / arms["L"]["y2"] if self.n and arms["L"]["y2"] > 0 else None
        return {"count": self.n, "M": arms["M"], "L": arms["L"],
                "mse_delta_M_minus_L": delta, "relative_reduction": relative}


def summarize(db, output, streams):
    db.executescript("""
        CREATE INDEX observations_fen_id ON observations(fen,id);
        CREATE TABLE eligible AS
          SELECT o.fen, min(o.key4) AS key4, count(*) AS n, sum(o.q) AS sq,
                 sum(o.r) AS sr, sum(o.y) AS sy, min(o.id) AS first_id
          FROM observations o JOIN groups g ON g.id=o.group_id
          WHERE g.complete=1 GROUP BY o.fen HAVING count(*)>=3;
        CREATE UNIQUE INDEX eligible_fen ON eligible(fen);
        ALTER TABLE eligible ADD COLUMN second_id INTEGER;
        UPDATE eligible SET second_id=(
          SELECT min(o.id) FROM observations o JOIN groups g ON g.id=o.group_id
          WHERE o.fen=eligible.fen AND o.id>eligible.first_id AND g.complete=1);
    """)
    overall = Metrics()
    writers = {s["writer_id"]: Metrics() for s in streams}
    bins = {str(i): Metrics() for i in range(5)}
    active_fen = None
    local = local_writers = local_bins = None
    identity_key4 = None

    with (output / "per_identity.jsonl").open("w", encoding="utf-8", newline="\n") as sink:
        def flush():
            if active_fen is None:
                return
            overall.add_identity(local)
            for name, values in local_writers.items():
                writers[name].add_identity(values)
            for name, values in local_bins.items():
                bins[name].add_identity(values)
            record = {"fen": active_fen, "key4": identity_key4,
                      "held_out_group_count": local.n, "errors": local.report(),
                      "writers": {k: v.report() for k, v in local_writers.items()},
                      "bins": {k: v.report() for k, v in local_bins.items()}}
            sink.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")

        query = """
          SELECT e.fen,e.key4,e.n,e.sq,e.sr,e.sy,e.first_id,
                 f.q,f.r,f.y,s.q,s.r,s.y,o.id,o.q,o.r,o.y,t.writer,g.bin
          FROM eligible e JOIN observations f ON f.id=e.first_id
          JOIN observations s ON s.id=e.second_id
          JOIN observations o ON o.fen=e.fen
          JOIN groups g ON g.id=o.group_id JOIN streams t ON t.id=g.stream
          WHERE g.complete=1 ORDER BY e.fen,o.id
        """
        for row in db.execute(query):
            (fen, key4, n, sq, sr, sy, first_id, fq, fr, fy, sq2, sr2, sy2,
             oid, q, r, y, writer, group_bin) = row
            if fen != active_fen:
                flush()
                active_fen, identity_key4 = fen, key4
                local, local_writers, local_bins = Metrics(), {}, {}
            pred = {"M": ((sq - q) / (n - 1), (sr - r) / (n - 1), (sy - y) / (n - 1)),
                    "L": (sq2, sr2, sy2) if oid == first_id else (fq, fr, fy)}
            local.add_errors(pred, (q, r, y))
            local_writers.setdefault(writer, Metrics()).add_errors(pred, (q, r, y))
            local_bins.setdefault(str(group_bin), Metrics()).add_errors(pred, (q, r, y))
        flush()

    scalar = lambda sql: db.execute(sql).fetchone()[0]
    denominator = scalar("SELECT count(*) FROM key4_counts")
    numerator = scalar("SELECT count(DISTINCT key4) FROM eligible")
    held_groups = scalar("""
        SELECT count(DISTINCT o.group_id) FROM observations o
        JOIN eligible e ON e.fen=o.fen JOIN groups g ON g.id=o.group_id WHERE g.complete=1
    """)
    counts = {
        "raw_rows": scalar("SELECT coalesce(sum(raw_rows),0) FROM streams"),
        "writers": len(streams), "conservative_groups": scalar("SELECT count(*) FROM groups"),
        "complete_groups": scalar("SELECT count(*) FROM groups WHERE complete=1"),
        "excluded_final_groups": scalar("SELECT count(*) FROM groups WHERE complete=0"),
        "excluded_final_group_rows": scalar("SELECT coalesce(sum(raw_rows),0) FROM groups WHERE complete=0"),
        "retained_complete_group_rows": scalar("SELECT coalesce(sum(raw_rows),0) FROM groups WHERE complete=1"),
        "retained_clock_zero_rows": scalar("SELECT coalesce(sum(clock_zero_rows),0) FROM groups WHERE complete=1"),
        "denominator_distinct_key4_all_raw_rows": denominator,
        "repeated_key4_all_raw_rows": scalar("SELECT count(*) FROM key4_counts WHERE n>1"),
        "key4_with_halfmove_alias_all_raw_rows": scalar("SELECT count(*) FROM key4_counts WHERE min_half<>max_half"),
        "key4_with_absolute_ply_alias_all_raw_rows": scalar("SELECT count(*) FROM key4_counts WHERE min_ply<>max_ply"),
        "key4_in_three_complete_groups": scalar("""
           SELECT count(*) FROM (SELECT k.key4 FROM key4_groups k JOIN groups g ON g.id=k.group_id
                                 WHERE g.complete=1 GROUP BY k.key4 HAVING count(*)>=3)
        """),
        "eligible_full_fen_identities": overall.n, "eligible_distinct_key4": numerator,
        "held_out_conservative_groups": held_groups,
        "coverage": numerator / denominator if denominator else 0.0,
    }
    writer_reports = {k: v.report() for k, v in writers.items()}
    bin_reports = {k: v.report() for k, v in bins.items()}
    primary = overall.report()
    positive = lambda report: report["mse_delta_M_minus_L"] is not None and report["mse_delta_M_minus_L"] < 0
    qualifying = [name for name, values in writers.items() if values.n >= 100]
    gates = {
        "at_least_500_identities": overall.n >= 500,
        "at_least_200_groups": held_groups >= 200,
        "at_least_half_percent_coverage": counts["coverage"] >= 0.005,
        "at_least_two_percent_reduction": primary["relative_reduction"] is not None and primary["relative_reduction"] >= 0.02,
        "four_of_five_positive_bins": sum(positive(v) for v in bin_reports.values()) >= 4,
        "all_qualifying_writers_positive": all(positive(writer_reports[k]) for k in qualifying),
    }
    coverage_ok = all(gates[k] for k in ("at_least_500_identities", "at_least_200_groups", "at_least_half_percent_coverage"))
    status = "inconclusive_coverage" if not coverage_ok else ("passed_offline_gate" if all(gates.values()) else "failed_offline_gate")
    with (output / "static_ranges.jsonl").open("w", encoding="utf-8", newline="\n") as sink:
        for key, n, low, high in db.execute("SELECT * FROM static_inputs ORDER BY input_key"):
            sink.write(json.dumps({"input_key": key, "rows": n, "minimum_white_cp": low,
                                   "maximum_white_cp": high, "range_cp": high - low}, sort_keys=True) + "\n")
    return {"status": status, "counts": counts, "primary": primary, "writers": writer_reports,
            "bins": bin_reports, "gates": gates, "qualifying_writers": qualifying,
            "qualifying_writer_condition_vacuous": not qualifying,
            "static_inputs": scalar("SELECT count(*) FROM static_inputs"),
            "static_inputs_with_nonzero_range": scalar("SELECT count(*) FROM static_inputs WHERE minimum<>maximum")}


def run(manifest_path, output_directory):
    started, cpu_started = time.monotonic(), time.process_time()
    manifest, manifest_raw = validate_manifest(manifest_path)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)
    db = None
    try:
        db = create_db(output / "pilot.sqlite")
        diagnostics = ingest(db, manifest["streams"])
        result = summarize(db, output, manifest["streams"])
        result.update(diagnostics)
        result.update({
            "version": VERSION, "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_order": "manifest stream order, then immutable source byte offset",
            "bin_rule": "big-endian integer SHA256(UTF8('20261024|writer_id|start_offset')) modulo 5",
            "mode": "latest-teacher-only; F and teacher-refresh contrast omitted",
            "weighting": "mean held-out errors per identity, then equal identity weights; repeated separately inside each writer/bin",
            "static_population": "all sampled raw rows including excluded final groups; White-relative scores",
            "limits": {"raw_rows": MAX_ROWS, "sqlite_cache_bytes": 32 * 1024 * 1024,
                       "process_memory_cap_bytes": 2 * 1024**3, "memory_cap_enforced_by": "caller"},
            "wall_seconds": time.monotonic() - started, "cpu_seconds": time.process_time() - cpu_started,
            "no_elo_inference": True,
        })
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result["peak_rss_bytes"] = rss if sys.platform == "darwin" else rss * 1024
        except ImportError:
            result["peak_rss_bytes"] = None
        db.commit()
        (output / "manifest.json").write_bytes(manifest_raw)
        (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({"status": "invalid_run", "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if db is not None:
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("output_directory")
    args = parser.parse_args()
    try:
        result = run(args.manifest, args.output_directory)
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        print(f"invalid pilot: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "counts": result["counts"], "gates": result["gates"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
