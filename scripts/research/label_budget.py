#!/usr/bin/env python3
"""Standard-library label-budget pilot; no downloads, APIs, or neural training.

Input JSONL: {"id":"r1", "group":"opening-family", "startfen":"...",
              "moves":[], "position_fen":"...", "game_id":"optional",
              "opening_id":"optional"}
position_fen is required after nonempty moves: this tool has no move generator.
Replay is verified with the ChessSI d command before each search. Board-plus-side duplicates
are grouped conservatively even when rights, clocks or histories differ.
Use trusted books or legally replayed games: FEN syntax is not a legality proof.
Corpus FENs must match ChessSI canonical pseudo-capturable en passant (for
python-chess extraction use fen(en_passant="xfen"), or explicitly normalize).
Uncapturable or legal-only EP mismatches are rejected, never silently ignored.
collect requires an explicit frozen executable and a NEW output directory.
analyze never launches an engine. Use only an allocated CPU slot, for example:
 taskset -c 14 python3 scripts/research/label_budget.py collect \
   --input roots.jsonl --engine /absolute/frozen/chesssi --output pilot
 python3 scripts/research/label_budget.py analyze --collection pilot
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from typing import Any

SCHEMA = 1
MOVE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

@dataclass(frozen=True)
class Config:
    cheap: int = 2048
    replacement: int = 16384
    audit: int = 131072
    hash_mb: int = 16
    timeout: float = 30.0
    seed: int = 20261022
    fraction: float = 0.25
    score_scale: float = 400.0
    bootstrap: int = 1000
    minimum_test_groups: int = 20

    def validate(self):
        if not 0 < self.cheap < self.replacement < self.audit:
            raise ValueError("Require 0 < cheap < replacement < audit node caps")
        if self.hash_mb < 1 or self.timeout <= 0 or not math.isfinite(self.timeout):
            raise ValueError("Hash and timeout must be positive and finite")
        if not 0 < self.fraction < 1 or self.score_scale <= 0 or not math.isfinite(self.score_scale):
            raise ValueError("Invalid selection fraction or score scale")
        if self.bootstrap < 100 or self.minimum_test_groups < 2:
            raise ValueError("Need >=100 bootstrap replicates and >=2 test groups")

def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def file_hash(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def parse_fen(fen):
    """Syntax only; return conservative leakage key and PeSTO material phase."""
    if not isinstance(fen, str) or "\n" in fen or "\r" in fen:
        raise ValueError("FEN must be one line")
    parts = fen.split()
    if len(parts) != 6:
        raise ValueError("FEN must contain six fields")
    board, turn, castle, ep, halfmove, fullmove = parts
    if len(board.split("/")) != 8:
        raise ValueError("FEN must contain eight ranks")
    expanded, phase = [], 0
    for rank in board.split("/"):
        cells = ""
        for char in rank:
            if char in "12345678":
                cells += "." * int(char)
            elif char in "pnbrqkPNBRQK":
                cells += char
                phase += {"n": 1, "b": 1, "r": 2, "q": 4}.get(char.lower(), 0)
            else:
                raise ValueError("Invalid FEN board character")
        if len(cells) != 8:
            raise ValueError("Invalid FEN rank width")
        expanded.append(cells)
    if turn not in ("w", "b"):
        raise ValueError("Invalid FEN side")
    if castle != "-" and (any(c not in "KQkq" for c in castle) or len(set(castle)) != len(castle)):
        raise ValueError("Invalid castling rights")
    if ep != "-" and re.fullmatch(r"[a-h][36]", ep) is None:
        raise ValueError("Invalid en-passant field")
    if not halfmove.isdecimal() or not fullmove.isdecimal() or int(fullmove) < 1:
        raise ValueError("Invalid move counters")
    return digest("/".join(expanded) + " " + turn), min(phase, 24)

def assign_groups(roots, seed):
    """Union provenance and transposition identifiers, then deterministic split."""
    parent = list(range(len(roots)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    first = {}
    for index, root in enumerate(roots):
        for key in ("group", "game_id", "opening_id", "board_key"):
            if key in root:
                token = (key, root[key])
                if token in first:
                    parent[find(index)] = find(first[token])
                else:
                    first[token] = index
    members = defaultdict(list)
    for index, root in enumerate(roots):
        members[find(index)].append(root["id"])
    component = {key: digest(json.dumps(sorted(ids), ensure_ascii=True)) for key, ids in members.items()}
    for index, root in enumerate(roots):
        group = component[find(index)]
        value = int(digest(f"split:{seed}:{group}")[:16], 16) / 2**64
        root["component"] = group
        root["split"] = "train" if value < 0.5 else "calibration" if value < 0.75 else "test"

def load_roots(path, seed):
    roots, seen = [], set()
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError(f"Line {number}: root must be an object")
            for key in ("id", "group", "startfen"):
                if not isinstance(raw.get(key), str) or not raw[key].strip():
                    raise ValueError(f"Line {number}: nonempty {key} required")
            if raw["id"] in seen:
                raise ValueError(f"Duplicate root id {raw['id']}")
            seen.add(raw["id"])
            moves = raw.get("moves")
            if not isinstance(moves, list) or any(not isinstance(m, str) or not MOVE.fullmatch(m) for m in moves):
                raise ValueError(f"Line {number}: moves must be a list of UCI moves")
            parse_fen(raw["startfen"])
            if moves and "position_fen" not in raw:
                raise ValueError(f"Line {number}: position_fen required after moves")
            fen = raw.get("position_fen", raw["startfen"])
            board_key, phase = parse_fen(fen)
            if not moves and fen.split() != raw["startfen"].split():
                raise ValueError("position_fen disagrees with empty history")
            root = {k: raw[k] for k in ("id", "group", "startfen", "moves")}
            root.update(position_fen=fen, board_key=board_key, phase=phase)
            for key in ("game_id", "opening_id"):
                if key in raw:
                    if not isinstance(raw[key], str) or not raw[key]:
                        raise ValueError(f"Invalid {key}")
                    root[key] = raw[key]
            roots.append(root)
    if not roots:
        raise ValueError("No roots provided")
    assign_groups(roots, seed)
    return sorted(roots, key=lambda root: root["id"])

def parse_info(line):
    tokens = line.split()
    if not tokens or tokens[0] != "info" or (len(tokens) > 1 and tokens[1] == "string"):
        return None
    record = {"bounds": [], "multipv": 1}
    try:
        for index, token in enumerate(tokens):
            if token in ("depth", "nodes", "time", "multipv"):
                record[token] = int(tokens[index + 1])
            elif token == "score":
                record["score_type"], record["score"] = tokens[index + 1], int(tokens[index + 2])
            elif token in ("lowerbound", "upperbound"):
                record["bounds"].append(token)
            elif token == "pv":
                record["pv"] = tokens[index + 1:]
                break
    except (IndexError, ValueError):
        return None
    if "depth" not in record or record.get("score_type") not in ("cp", "mate"):
        return None
    if record["depth"] < 0 or any(record.get(key, 0) < 0 for key in ("nodes", "time")):
        return None
    return record

def completed_scores(infos):
    by_depth = {}
    for info in infos:
        if not info.get("bounds") and info.get("multipv", 1) == 1:
            by_depth[info["depth"]] = info
    return [by_depth[depth] for depth in sorted(by_depth)]

class UCIError(RuntimeError):
    pass

class UCIProcess:
    """Bounded synchronous UCI client; child command is an argv list, no shell."""
    def __init__(self, command, config):
        self.config, self.transcript = config, []
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.send("uci")
            self.until(lambda line: line == "uciok")
            self.send("setoption name Threads value 1")
            self.send(f"setoption name Hash value {config.hash_mb}")
            self.ready()
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line.rstrip("\r\n"))
        finally:
            self.lines.put(None)

    def send(self, command):
        self.transcript.append("> " + command)
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            raise UCIError(f"Engine input closed: {error}") from error

    def until(self, predicate):
        deadline, observed, size = time.monotonic() + self.config.timeout, [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UCIError("Engine response timed out")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise UCIError("Engine response timed out") from error
            if line is None:
                raise UCIError(f"Engine exited before response (code {self.process.poll()})")
            self.transcript.append("< " + line)
            observed.append(line)
            size += len(line)
            if len(observed) > 10000 or size > 2_000_000:
                raise UCIError("Engine response exceeded transcript limit")
            if any(message in line.lower() for message in ("invalid fen", "illegal move", "unknown command")):
                raise UCIError(f"Engine rejected input: {line}")
            if predicate(line):
                return observed

    def ready(self):
        self.send("isready")
        return self.until(lambda line: line == "readyok")

    def search(self, root, cap):
        self.transcript = []
        started = time.monotonic()
        try:
            self.send("ucinewgame")
            self.ready()
            command = "position fen " + root["startfen"]
            if root["moves"]:
                command += " moves " + " ".join(root["moves"])
            self.send(command)
            self.send("d")
            diagnostic = self.ready()
            fens = [line[4:].strip() for line in diagnostic if line.lower().startswith("fen:")]
            expected = root.get("position_fen", root["startfen"])
            if len(fens) != 1 or fens[0].split() != expected.split():
                raise UCIError("Replayed FEN does not match position_fen; ChessSI d support is required")
            self.send(f"go nodes {cap}")
            lines = self.until(lambda line: line.startswith("bestmove "))
            infos = [info for line in lines if (info := parse_info(line)) is not None]
            completed = completed_scores(infos)
            bestmove = lines[-1].split()[1]
            if bestmove not in ("0000", "(none)") and not MOVE.fullmatch(bestmove):
                raise UCIError("Malformed bestmove")
            last = completed[-1] if completed else None
            return {"status": last["score_type"] if last else "no_completed_score",
                "last": last, "infos": infos, "bestmove": bestmove,
                "requested_nodes": cap, "charged_nodes": cap,
                "last_completed_nodes": last.get("nodes") if last else None,
                "actual_nodes": None, "wall_seconds": time.monotonic() - started,
                "transcript": list(self.transcript)}
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            try:
                self.send("stop")
                self.send("quit")
            except UCIError:
                pass
            try:
                self.process.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        self.reader.join(timeout=1)
        if self.process.stdout and not self.process.stdout.closed:
            self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

def write_json(path, value):
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")

def collect(input_path, engine, output, config):
    config.validate()
    roots = load_roots(input_path, config.seed)
    engine = engine.resolve(strict=True)
    if not engine.is_file():
        raise ValueError("Engine must be a frozen executable file")
    frozen_hash = file_hash(engine)
    manifest = {"schema": SCHEMA, "status": "collecting", "config": asdict(config),
        "engine": str(engine), "engine_sha256": frozen_hash,
        "analysis_script_sha256": file_hash(Path(__file__)),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "platform": sys.platform, "concurrency": 1,
        "preregistration": "Analysis source/config frozen before labels; deterministic selections replayed after collection.",
        "input": str(input_path.resolve()), "input_sha256": file_hash(input_path), "roots": roots,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "accounting": "Requested caps are charged; exact final nodes are unavailable.",
        "position_validation": "FEN syntax plus exact six-field agreement with ChessSI d after replay.",
        "grouping": "Union of group, game_id, opening_id and board-plus-side identities."}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", manifest)
    charged, started = 0, time.monotonic()
    try:
        with (output / "labels.jsonl").open("x", encoding="utf-8") as stream:
            with UCIProcess([str(engine)], config) as runner:
                for tier, cap in (("cheap", config.cheap), ("replacement", config.replacement), ("audit", config.audit)):
                    for root in roots:
                        if tier == "audit" and root["split"] != "test":
                            continue
                        charged += cap
                        try:
                            result = runner.search(root, cap)
                        except BaseException as error:
                            result = {"status": "error", "error": str(error), "requested_nodes": cap,
                                "charged_nodes": cap, "transcript": list(runner.transcript)}
                            stream.write(json.dumps({"id": root["id"], "tier": tier, "result": result}) + "\n")
                            stream.flush()
                            raise
                        stream.write(json.dumps({"id": root["id"], "tier": tier, "result": result}) + "\n")
                        stream.flush()
        if file_hash(engine) != frozen_hash:
            raise UCIError("Executable changed during collection")
        manifest["status"] = "complete"
    except BaseException as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest["charged_nodes"] = charged
        manifest["wall_seconds"] = time.monotonic() - started
        write_json(output / "manifest.json", manifest)
    return manifest

def bounded_score(score, scale=400.0):
    x = score / scale
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 745.0)))
    exponent = math.exp(max(x, -745.0))
    return exponent / (1.0 + exponent)

def cp_score(result):
    if result and result.get("status") == "cp" and result.get("last"):
        return result["last"]["score"]
    return None

def cheap_features(root, result):
    if cp_score(result) is None:
        return None
    exact = completed_scores(result["infos"])
    current = exact[-1]
    previous = next((item for item in reversed(exact[:-1]) if item["score_type"] == "cp"), None)
    parity = next((item for item in exact if item["depth"] == current["depth"] - 2 and item["score_type"] == "cp"), None)
    adjacent = abs(current["score"] - previous["score"]) if previous else 0
    same = abs(current["score"] - parity["score"]) if parity else adjacent
    recent = exact[-3:]
    moves = [item["pv"][0] if item.get("pv") else None for item in recent]
    switches = sum(a != b for a, b in zip(moves, moves[1:]) if a is not None and b is not None)
    return [float(adjacent), float(same), float(switches), float(current["depth"]),
        float(abs(current["score"])), float(root["phase"]), float(previous is None),
        float(parity is None), float(any(m is None for m in moves))]

def transformed_volatility(result, scale):
    exact = completed_scores(result["infos"])
    current = exact[-1]
    previous = next((item for item in exact if item["depth"] == current["depth"] - 2 and item["score_type"] == "cp"), None)
    if previous is None:
        previous = next((item for item in reversed(exact[:-1]) if item["score_type"] == "cp"), None)
    return abs(bounded_score(current["score"], scale) - bounded_score(previous["score"], scale)) if previous else 0.0

def solve(matrix, rhs):
    """Small dense linear system with partial pivoting."""
    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    size = len(rhs)
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(augmented[index][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("Singular ridge system")
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row != column:
                factor = augmented[row][column]
                augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[column])]
    return [row[-1] for row in augmented]

def fit_ridge(xs, ys, alpha):
    dimension = len(xs[0])
    means = [statistics.fmean(x[j] for x in xs) for j in range(dimension)]
    scales = [max(math.sqrt(statistics.fmean((x[j] - means[j]) ** 2 for x in xs)), 1e-12) for j in range(dimension)]
    rows = [[1.0] + [(v - m) / s for v, m, s in zip(x, means, scales)] for x in xs]
    dimension += 1
    matrix = [[statistics.fmean(x[i] * x[j] for x in rows) + (alpha if i == j and i else 0.0)
        for j in range(dimension)] for i in range(dimension)]
    rhs = [statistics.fmean(x[i] * y for x, y in zip(rows, ys)) for i in range(dimension)]
    return {"alpha": alpha, "means": means, "scales": scales, "weights": solve(matrix, rhs)}

def predict(model, x):
    row = [1.0] + [(v - m) / s for v, m, s in zip(x, model["means"], model["scales"])]
    return sum(w * value for w, value in zip(model["weights"], row))

def choose_model(training, calibration, indices):
    candidates = []
    for alpha in (0.01, 1.0, 100.0):
        model = fit_ridge([[item["x"][i] for i in indices] for item in training], [item["y"] for item in training], alpha)
        error = statistics.fmean((predict(model, [item["x"][i] for i in indices]) - item["y"]) ** 2 for item in calibration)
        candidates.append((error, alpha, model))
    error, _, model = min(candidates, key=lambda item: (item[0], item[1]))
    model.update(feature_indices=list(indices), calibration_mse=error)
    return model

def model_score(model, x):
    return predict(model, [x[i] for i in model["feature_indices"]])

def percentile(values, fraction):
    ordered = sorted(values)
    where = fraction * (len(ordered) - 1)
    lower = int(where)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (where - lower)

def group_interval(values, config):
    grouped = defaultdict(list)
    for group, value in values:
        grouped[group].append(value)
    keys = sorted(grouped)
    if len(keys) < 2:
        return None
    rng, samples = random.Random(config.seed), []
    for _ in range(config.bootstrap):
        chosen = [rng.choice(keys) for _ in keys]
        samples.append(statistics.fmean(value for key in chosen for value in grouped[key]))
    return [percentile(samples, 0.025), percentile(samples, 0.975)]

def compare_policy(rows, learned_ids, control_ids, expected_fraction, config):
    """All-candidate denominator; missing bounded utility can be anywhere [-1,1]."""
    observed, lower, upper, missing_mass = [], [], [], 0.0
    for row in rows:
        control = expected_fraction if control_ids is None else float(row["id"] in control_ids)
        coefficient = float(row["id"] in learned_ids) - control
        if row["utility"] is None:
            value, bound = 0.0, abs(coefficient)
            missing_mass += bound
        else:
            value, bound = coefficient * row["utility"], 0.0
        observed.append((row["group"], value))
        lower.append((row["group"], value - bound))
        upper.append((row["group"], value + bound))
    mean = statistics.fmean(value for _, value in observed)
    mass = missing_mass / len(rows)
    lower_ci, upper_ci = group_interval(lower, config), group_interval(upper, config)
    return {"observed_improvement_contribution": mean, "missing_coefficient_mass": mass,
        "worst_case_missing_interval": [mean - mass, mean + mass],
        "sensitivity_group_bootstrap_95": [lower_ci[0], upper_ci[1]] if lower_ci and upper_ci else None}

def analyze_data(manifest, labels):
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "complete":
        raise ValueError("Analysis requires a completed collection with matching schema")
    if manifest.get("analysis_script_sha256") != file_hash(Path(__file__)):
        raise ValueError("Analysis source differs from the preregistered collection script")
    config = Config(**manifest["config"])
    config.validate()
    roots = manifest["roots"]
    if len({root["id"] for root in roots}) != len(roots):
        raise ValueError("Duplicate manifest root IDs")
    for root in roots:
        board_key, phase = parse_fen(root["position_fen"])
        if board_key != root["board_key"] or phase != root["phase"]:
            raise ValueError("Manifest position key or phase mismatch")
    checked = [dict(root) for root in roots]
    assign_groups(checked, config.seed)
    if any(a["split"] != b["split"] or a["component"] != b["component"] for a, b in zip(roots, checked)):
        raise ValueError("Stored grouping/split does not match frozen rule")
    by_id = {root["id"]: {} for root in roots}
    for label in labels:
        if label["id"] not in by_id or label["tier"] not in ("cheap", "replacement", "audit"):
            raise ValueError("Unknown root or label tier")
        if label["tier"] in by_id[label["id"]]:
            raise ValueError("Duplicate root/tier label")
        by_id[label["id"]][label["tier"]] = label["result"]
    for root in roots:
        expected = {"cheap", "replacement", "audit"} if root["split"] == "test" else {"cheap", "replacement"}
        if set(by_id[root["id"]]) != expected:
            raise ValueError(f"Incomplete or unexpected labels for {root['id']}")
        for tier, result in by_id[root["id"]].items():
            if result.get("requested_nodes") != getattr(config, tier) or result.get("charged_nodes") != getattr(config, tier):
                raise ValueError("Label node cap does not match frozen configuration")
            if result.get("status") == "error":
                raise ValueError("Failed probe in completed collection")
    training, calibration, candidates, exclusions = [], [], [], []
    for root in roots:
        record = by_id[root["id"]]
        x = cheap_features(root, record["cheap"])
        s0 = cp_score(record["cheap"])
        if x is None:
            exclusions.append({"id": root["id"], "split": root["split"], "reason": "cheap_not_cp"})
            continue
        item = {"root": root, "x": x, "s0": s0}
        if root["split"] == "test":
            item["bounded_volatility"] = transformed_volatility(record["cheap"], config.score_scale)
            candidates.append(item)  # No replacement or audit values enter selection.
        else:
            s1 = cp_score(record["replacement"])
            if s1 is None:
                exclusions.append({"id": root["id"], "split": root["split"], "reason": "replacement_not_cp"})
            else:
                item["y"] = abs(bounded_score(s1, config.score_scale) - bounded_score(s0, config.score_scale))
                (training if root["split"] == "train" else calibration).append(item)
    if len(training) < 2 or not calibration or len(candidates) < 4:
        raise ValueError("Insufficient train/calibration/test roots; preserve groups and collect more")
    model = choose_model(training, calibration, range(9))
    context_model = choose_model(training, calibration, (3, 4, 5, 6, 7, 8))
    count = int(len(candidates) * config.fraction)
    if count < 1:
        raise ValueError("Selection fraction yields no test roots")
    tie = lambda item: digest(f"tie:{config.seed}:{item['root']['id']}")
    policies = {
        "uniform": sorted(candidates, key=tie),
        "raw_volatility": sorted(candidates, key=lambda item: (-item["x"][1], tie(item))),
        "bounded_volatility": sorted(candidates, key=lambda item: (-item["bounded_volatility"], tie(item))),
        "context_only": sorted(candidates, key=lambda item: (-model_score(context_model, item["x"]), tie(item))),
        "learned": sorted(candidates, key=lambda item: (-model_score(model, item["x"]), tie(item))),
    }
    selected = {name: {item["root"]["id"] for item in items[:count]} for name, items in policies.items()}
    # Selection is now frozen. Audit exclusions never trigger refill or reranking.
    rows = []
    for item in candidates:
        root = item["root"]
        record = by_id[root["id"]]
        s1, s2 = cp_score(record["replacement"]), cp_score(record["audit"])
        row = {"id": root["id"], "group": root["component"], "utility": None}
        if s1 is None or s2 is None:
            exclusions.append({"id": root["id"], "split": "test", "reason": "replacement_or_audit_not_cp",
                "replacement_status": record["replacement"].get("status"), "audit_status": record["audit"].get("status")})
        else:
            f0, f1, f2 = [bounded_score(score, config.score_scale) for score in (item["s0"], s1, s2)]
            row.update(base_loss=(f0 - f2) ** 2, replacement_loss=(f1 - f2) ** 2,
                utility=(f0 - f2) ** 2 - (f1 - f2) ** 2)
        rows.append(row)
    available = [row for row in rows if row["utility"] is not None]
    if not available:
        raise ValueError("No common centipawn audit domain")
    base = statistics.fmean(row["base_loss"] for row in available)
    effective = count / len(candidates)
    summaries = {}
    for name, ids in selected.items():
        loss = statistics.fmean(row["replacement_loss"] if row["id"] in ids else row["base_loss"] for row in available)
        summaries[name] = {"conditional_cp_mean_loss": loss, "conditional_cp_mean_gain": base - loss,
            "selected_ids": sorted(ids), "selected_count": len(ids),
            "auditable_selected_count": sum(row["id"] in ids for row in available),
            "negative_utility_selections": sum(row["id"] in ids and row["utility"] < 0 for row in available)}
    comparisons = {name: compare_policy(rows, selected["learned"], ids, effective, config) for name, ids in
        [("uniform_expected", None)] + [(name, selected[name]) for name in ("raw_volatility", "bounded_volatility", "context_only")]}
    group_counts = defaultdict(int)
    for row in rows:
        group_counts[row["group"]] += 1
    group_count = len(group_counts)
    passed = group_count >= config.minimum_test_groups and all(
        result["worst_case_missing_interval"][0] > 0 and
        result["sensitivity_group_bootstrap_95"] is not None and
        result["sensitivity_group_bootstrap_95"][0] > 0 for result in comparisons.values())
    return {"schema": SCHEMA, "kind": "offline_label_diagnostic", "elo_claim": None,
        "score_transform": "logistic(cp / scale), not calibrated win probability", "score_scale": config.score_scale,
        "engine_sha256": manifest["engine_sha256"], "config": asdict(config),
        "counts": {"training": len(training), "calibration": len(calibration), "test_candidates": len(candidates),
            "auditable_test": len(available), "test_groups": group_count},
        "largest_test_group_fraction": max(group_counts.values()) / len(rows),
        "selector": model, "context_only_selector": context_model,
        "selection_rule": "floor(q * cheap-cp test roots); preregistered source/config; replay ignores audit values; never refill",
        "effective_selection_fraction": effective,
        "conditional_cp_no_replacement_loss": base,
        "conditional_cp_uniform_expected_loss": base - effective * statistics.fmean(row["utility"] for row in available),
        "policies": summaries, "comparisons": comparisons, "exclusions": exclusions,
        "stage_gate": "passed_screen_only" if passed else "not_passed_or_inconclusive",
        "gate_note": "All four controls must pass conservative missing-data and group-bootstrap bounds; no Elo implication.",
        "actual_consumed_nodes": None,
        "research_charged_nodes": sum(label["result"]["charged_nodes"] for label in labels),
        "counterfactual_policy_charged_nodes": sum(root["split"] == "test" for root in roots) * config.cheap + count * config.replacement,
        "candidate_domain_only_charged_nodes": len(candidates) * config.cheap + count * config.replacement,
        "accounting_note": "Counterfactual total includes screening every test root, including cheap non-cp roots; research total includes all probes and audits.",
        "utility_rows": rows}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    cp = sub.add_parser("collect", help="Collect labels with an explicit frozen executable")
    cp.add_argument("--input", type=Path, required=True)
    cp.add_argument("--engine", type=Path, required=True)
    cp.add_argument("--output", type=Path, required=True)
    cp.add_argument("--timeout", type=float, default=30.0)
    cp.add_argument("--seed", type=int, default=20261022)
    cp.add_argument("--nodes", type=int, nargs=3, default=(2048, 16384, 131072), metavar=("CHEAP", "REPLACEMENT", "AUDIT"))
    cp.add_argument("--hash-mb", type=int, default=16)
    ap = sub.add_parser("analyze", help="Analyze a completed collection without running an engine")
    ap.add_argument("--collection", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "collect":
            config = Config(cheap=args.nodes[0], replacement=args.nodes[1], audit=args.nodes[2],
                timeout=args.timeout, seed=args.seed, hash_mb=args.hash_mb)
            result = collect(args.input, args.engine, args.output, config)
            print(json.dumps({"status": result["status"], "charged_nodes": result["charged_nodes"]}))
        else:
            with (args.collection / "manifest.json").open(encoding="utf-8") as stream:
                manifest = json.load(stream)
            with (args.collection / "labels.jsonl").open(encoding="utf-8") as stream:
                labels = [json.loads(line) for line in stream if line.strip()]
            print(json.dumps(analyze_data(manifest, labels), indent=2, sort_keys=True, allow_nan=False))
    except (ValueError, UCIError, OSError, KeyError, TypeError) as error:
        print(f"label-budget error: {error}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
