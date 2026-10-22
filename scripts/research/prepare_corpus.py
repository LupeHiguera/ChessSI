#!/usr/bin/env python3
"""Prepare history-preserving label roots from frozen, single-session PGNs.

Requires python-chess 1.11.2 (the separately pinned checkout; no installation).
Example, from the repository in its allocated CPU slot:
 PYTHONPATH=engines/dependencies/python-chess taskset -c 19 python3 -B \
   scripts/research/prepare_corpus.py --archived-inputs \
   --pgn run1=/absolute/archive/files/run.pgn --sha256 run1=FULL_SHA256 \
   --bench-source src/uci.cpp --seed 20261022 --output new-corpus

The caller asserts archival/session provenance; hashes and headers cannot prove
that an input really came from one run. Reject ambiguous or unfinished inputs.
No engines, Git, downloads, outcomes, or evaluation annotations drive selection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys

try:
    import chess
    import chess.pgn
except ImportError:
    raise SystemExit("Set PYTHONPATH to the pinned python-chess checkout (1.11.2)")

SCHEMA = 1
PINNED_VERSION = "1.11.2"
PINNED_COMMIT = "3516d7c6c0879af724c2855fac5a304a4ef40949"
RESULTS = {"1-0", "0-1", "1/2-1/2"}
TAG = re.compile(r'^\[([A-Za-z0-9][A-Za-z0-9_+#=:-]*)\s+"([^\r\n]*)"\]\s*$')
HEX = re.compile(r"[0-9a-f]{64}\Z")
SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def file_hash(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def stat_key(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def frozen_input(path, expected, maximum):
    path = Path(path).resolve(strict=True)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Not a regular archived file: {path}")
        if before.st_size > maximum:
            raise ValueError(f"Input exceeds --max-input-mib: {path}")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if stat_key(before) != stat_key(after) or stat_key(before) != stat_key(path.stat()):
        raise ValueError(f"Input changed during reading: {path}")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"Input SHA256 mismatch: {path}")
    return data.decode("utf-8-sig"), {
        "path": str(path), "sha256": actual, "bytes": len(data),
        "stat_at_read": list(stat_key(before)),
    }


def board_key(board):
    """Conservative transposition key: placement and side, ignoring all rights."""
    return board.board_fen() + (" w" if board.turn else " b")


def phase(board):
    return min(24, sum(len(board.pieces(piece, color)) * weight
                       for color in chess.COLORS
                       for piece, weight in ((chess.KNIGHT, 1), (chess.BISHOP, 1),
                                             (chess.ROOK, 2), (chess.QUEEN, 4))))


def valid_board(fen):
    fields = fen.split()
    if (len(fields) != 6 or not fields[4].isdecimal() or
            not fields[5].isdecimal() or int(fields[5]) < 1):
        raise ValueError("Initial FEN must have six fields and valid counters")
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError(f"Illegal initial board (status {int(board.status())})")
    if board.chess960 or board.has_chess960_castling_rights():
        raise ValueError("Chess960 is unsupported")
    return board


def load_bench(source=None, fen_file=None):
    path = Path(source or fen_file).resolve(strict=True)
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    if source:
        arrays = re.findall(r"\bBenchFens\s*=\s*\{(.*?)\};", text, flags=re.S)
        if len(arrays) != 1:
            raise ValueError("Require exactly one BenchFens initializer")
        fens = re.findall(r'"([^"\r\n]*)"', arrays[0])
        if re.sub(r'"[^"\r\n]*"|[\s,]', "", arrays[0]):
            raise ValueError("Unsupported BenchFens initializer syntax")
    else:
        fens = [line.strip() for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if len(fens) != 14:
        raise ValueError("Require exactly 14 frozen bench FENs")
    keys = {board_key(chess.Board(fen)) for fen in fens}
    if len(keys) != 14:
        raise ValueError("Frozen bench list contains duplicate board/side keys")
    return keys, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                  "fens": fens, "fens_sha256": digest(stable_json(fens)),
                  "exclusion_key": "piece placement + side; rights/clocks ignored"}


class StrictBuilder(chess.pgn.GameBuilder):
    def begin_game(self):
        super().begin_game()
        self.game.observed_headers = {}
        self.game.observed_results = []

    def visit_header(self, tagname, tagvalue):
        if tagname in self.game.observed_headers:
            self.game.errors.append(ValueError(f"Duplicate header {tagname}"))
        self.game.observed_headers[tagname] = tagvalue
        super().visit_header(tagname, tagvalue)

    def visit_result(self, result):
        self.game.observed_results.append(result)
        super().visit_result(result)

    def handle_error(self, error):
        self.game.errors.append(error)


def strict_movetext(fragment):
    """Close the forgiving PGN parser's skipped-token/truncated-comment gaps.

    Engine mainlines only: RAVs are deliberately unsupported. Comments and NAGs
    are discarded before selection; SAN is independently replayed below.
    """
    clean, in_comment = [], False
    for line in fragment.splitlines(keepends=True):
        if not in_comment and line.startswith("%"):
            continue
        if not in_comment and line.lstrip().startswith("["):
            # Braces/semicolons inside quoted tag values are literal text.
            clean.append(line)
            clean.append("\n")
            continue

        index = 0
        while index < len(line):
            char = line[index]
            if in_comment:
                if char == "}":
                    in_comment = False
                    clean.append(" ")
            elif char == "{":
                in_comment = True
                clean.append(" ")
            elif char == ";":
                break
            elif char == "}":
                raise ValueError("Unmatched PGN comment close")
            else:
                clean.append(char)
            index += 1
        clean.append("\n")
    if in_comment:
        raise ValueError("Unfinished PGN comment")
    lines, started, headers = [], False, {}
    for line in "".join(clean).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("["):
            match = TAG.fullmatch(line)
            if started or not match:
                raise ValueError("Malformed or misplaced PGN header")
            if match[1] in headers:
                raise ValueError("Duplicate PGN header")
            headers[match[1]] = match[2]
        else:
            started = True
            lines.append(line)
    text = " ".join(lines)
    if "(" in text or ")" in text:
        raise ValueError("PGN variations are unsupported; supply engine mainlines")
    text = re.sub(r"\$[0-9]+", " ", text)
    sans, result = [], None
    for token in text.split():
        token = re.sub(r"^[0-9]+\.(?:\.\.)?", "", token)
        token = token.rstrip("!?")
        if not token or token == "...":
            continue
        if token in RESULTS or token == "*":
            if result is not None:
                raise ValueError("Multiple result tokens in one game")
            result = token
        elif result is not None:
            raise ValueError("Movetext after game result")
        else:
            sans.append(token)
    if result not in RESULTS:
        raise ValueError("Unfinished game or tail: complete result token required")
    if headers.get("Result") != result:
        raise ValueError("Result header and movetext disagree")
    return headers, sans, result


class Groups:
    def __init__(self):
        self.parent = {}
        self.tokens = {}

    def find(self, item):
        if item not in self.parent:
            self.parent[item] = item
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while item != root:
            previous = item
            item = self.parent[item]
            self.parent[previous] = root
        return root

    def connect(self, game, token):
        root = self.find(game)
        if token in self.tokens:
            other = self.find(self.tokens[token])
            self.parent[max(root, other)] = min(root, other)
        else:
            self.tokens[token] = game

    def components(self):
        members = defaultdict(list)
        for game in self.parent:
            members[self.find(game)].append(game)
        names = {root: digest(stable_json(sorted(games))) for root, games in members.items()}
        return {game: names[self.find(game)] for game in self.parent}


def parse_session(text, session, provenance, bench_keys, groups):
    stream = io.StringIO(text)
    candidates, games, seen = [], [], set()
    signature = None
    exclusions = Counter()
    while True:
        start = stream.tell()
        game = chess.pgn.read_game(stream, Visitor=StrictBuilder)
        end = stream.tell()
        if game is None:
            if text[start:].strip():
                # Comment-only trailing text is harmless only if fully closed.
                trailing = text[start:]
                if trailing.count("{") != trailing.count("}"):
                    raise ValueError("Unfinished trailing PGN comment")
            break
        number = len(games) + 1
        context = f"{session} game {number}"
        if game.errors:
            raise ValueError(f"{context}: PGN parse errors: {game.errors}")
        try:
            headers, sans, result = strict_movetext(text[start:end])
            if game.observed_results != [result]:
                raise ValueError("Parser did not observe exactly one complete game result")
            for required in ("Event", "Site", "Round", "White", "Black"):
                if not headers.get(required):
                    raise ValueError(f"Missing {required} header")
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", headers["Round"]):
                raise ValueError("Round must be an explicit numeric identifier")
            if headers["White"] == headers["Black"]:
                raise ValueError("Distinct player identifiers required")
            if headers.get("Variant", "Standard").lower() not in ("standard", "chess"):
                raise ValueError("Variants/Chess960 unsupported")
            if headers.get("Chess960", "false").lower() not in ("false", "0"):
                raise ValueError("Chess960 unsupported")
            if ("FEN" in headers) != (headers.get("SetUp") == "1"):
                raise ValueError("Custom FEN requires SetUp 1; SetUp 1 requires FEN")
            if headers.get("SetUp", "0") not in ("0", "1"):
                raise ValueError("Invalid SetUp header")
            current_signature = {
                key: headers.get(key) for key in
                ("Event", "Site", "TimeControl", "Session", "RunId", "Variant")
            }
            current_signature["players"] = sorted((headers["White"], headers["Black"]))
            if signature is not None and signature != current_signature:
                raise ValueError("Unexplained mixed sessions: session headers/players changed")
            signature = current_signature
            key = (headers["Round"], headers["White"], headers["Black"])
            if key in seen:
                raise ValueError("Duplicate game key (Round, White, Black)")
            seen.add(key)
            game_id = digest(stable_json([session, *key]))
            raw_fen = headers.get("FEN", chess.STARTING_FEN)
            board = valid_board(raw_fen)
            if game.board().chess960:
                raise ValueError("Chess960 unsupported")
            startfen = board.fen(en_passant="xfen")
            opening_id = digest(startfen)
            groups.connect(game_id, ("opening", opening_id))
            groups.connect(game_id, ("board", board_key(board)))
            parsed_moves = list(game.mainline_moves())
            if len(sans) != len(parsed_moves):
                raise ValueError("Unrecognized/skipped movetext or move count mismatch")
            history, game_candidates = [], []
            for ply, (san, parsed) in enumerate(zip(sans, parsed_moves), 1):
                move = board.parse_san(san)
                if not move or not board.is_legal(move) or move != parsed:
                    raise ValueError(f"Illegal or inconsistent move at ply {ply}")
                history.append(move.uci())
                board.push(move)
                key_board = board_key(board)
                # Connect the full legal histories, including unsampled positions.
                groups.connect(game_id, ("board", key_board))
                if ply < 12 or (ply - 12) % 8:
                    continue
                if key_board in bench_keys:
                    exclusions["bench_roots"] += 1
                    continue
                if board.is_game_over(claim_draw=False):
                    exclusions["terminal_roots"] += 1
                    continue
                root_id = digest(stable_json([game_id, startfen, history]))
                game_candidates.append({
                    "id": root_id, "game_id": game_id, "opening_id": opening_id,
                    "startfen": startfen, "moves": history.copy(),
                    "position_fen": board.fen(en_passant="xfen"),
                    "source_raw_fen": raw_fen,
                    "history_scope": "legal prefix since initial PGN FEN only; pre-FEN history unknown",
                    "source": {"session": session, "input_sha256": provenance["sha256"],
                               "game_number": number, "round": headers["Round"],
                               "ply_from_initial_fen": ply,
                               "game_fragment_sha256": digest(text[start:end])},
                    "_board_key": key_board, "_phase": phase(board),
                })
            if "PlyCount" in headers:
                if not headers["PlyCount"].isdecimal() or int(headers["PlyCount"]) != len(history):
                    raise ValueError("PlyCount does not match legally replayed mainline")
            games.append({"id": game_id, "session": session, "game_number": number,
                          "round": headers["Round"], "opening_id": opening_id,
                          "plies": len(history), "eligible_grid_roots": len(game_candidates),
                          "raw_initial_fen": raw_fen, "canonical_initial_fen": startfen})
            candidates.extend(game_candidates)
        except (ValueError, IndexError) as error:
            raise ValueError(f"{context}: {error}") from error
    if not games:
        raise ValueError(f"{session}: no complete games")
    return candidates, games, dict(exclusions), signature


def select_roots(candidates, seed, maximum, groups):
    """Only position/provenance data enter this function; never PGN outcomes."""
    components = groups.components()
    by_game = defaultdict(list)
    for root in candidates:
        root = dict(root)
        root["group"] = components[root["game_id"]]
        by_game[root["game_id"]].append(root)
    capped = []
    for roots in by_game.values():
        capped.extend(sorted(roots, key=lambda r: (digest(f"per-game:{seed}:{r['id']}"), r["id"]))[:4])
    # One representative per conservative board/side key, independent of input order.
    unique = {}
    for root in capped:
        rank = (digest(f"representative:{seed}:{root['id']}"), root["id"])
        old = unique.get(root["_board_key"])
        if old is None or rank < old[0]:
            unique[root["_board_key"]] = (rank, root)
    pool = [entry[1] for entry in unique.values()]
    selected = sorted(pool, key=lambda r: (digest(f"global:{seed}:{r['id']}"), r["id"]))[:maximum]
    counts = Counter(root["group"] for root in selected)
    stats = {
        "eligible_grid_roots": len(candidates), "per_game_capped_roots": len(capped),
        "duplicate_board_side_roots_removed": len(capped) - len(pool),
        "unique_selection_pool_roots": len(pool), "selected_roots": len(selected),
        "selected_games": len({r["game_id"] for r in selected}),
        "selected_openings": len({r["opening_id"] for r in selected}),
        "all_game_components": len(set(components.values())),
        "selected_components": len(counts),
        "selected_component_sizes": sorted(counts.values(), reverse=True),
        "selected_phase_counts": dict(sorted(Counter(str(r["_phase"]) for r in selected).items())),
    }
    for root in selected:
        del root["_board_key"]
        del root["_phase"]
    return sorted(selected, key=lambda r: r["id"]), stats


def module_provenance():
    paths = {Path(__file__).resolve()}
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if (name == "chess" or name.startswith("chess.")) and filename:
            paths.add(Path(filename).resolve())
    return [{"path": str(path), "sha256": file_hash(path)} for path in sorted(paths)]


def prepare(inputs, output, *, seed, bench_source=None, bench_fens=None,
            max_roots=1024, max_input_mib=128, archived_inputs=False):
    if chess.__version__ != PINNED_VERSION:
        raise ValueError(f"Require python-chess {PINNED_VERSION}; found {chess.__version__}")
    if not archived_inputs:
        raise ValueError("--archived-inputs must acknowledge frozen, single-session inputs")
    if not isinstance(seed, str) or not re.fullmatch(r"[0-9]+", seed):
        raise ValueError("Seed must be an exact decimal string")
    if not 1 <= max_roots <= 1024 or max_input_mib < 1:
        raise ValueError("Require 1..1024 roots and positive input limit")
    if bool(bench_source) == bool(bench_fens):
        raise ValueError("Specify exactly one bench source or frozen FEN file")
    output = Path(output).absolute()
    if output.exists():
        raise ValueError("Output must be an exclusively new directory")
    if not inputs:
        raise ValueError("At least one PGN input required")
    bench_keys, bench_info = load_bench(bench_source, bench_fens)
    modules = module_provenance()
    groups, candidates, games, input_info = Groups(), [], [], []
    all_exclusions, sessions, hashes = Counter(), set(), set()
    for item in sorted(inputs, key=lambda item: item["session"]):
        session, expected = item["session"], item["sha256"]
        if not SESSION.fullmatch(session) or session in sessions:
            raise ValueError("Session identifiers must be unique safe names")
        if not HEX.fullmatch(expected):
            raise ValueError("Expected SHA256 must contain 64 lowercase hex digits")
        if expected in hashes:
            raise ValueError("Duplicate PGN content supplied under multiple sessions")
        sessions.add(session)
        hashes.add(expected)
        text, provenance = frozen_input(item["path"], expected, max_input_mib * 1024 * 1024)
        parsed, recorded, exclusions, signature = parse_session(text, session, provenance, bench_keys, groups)
        provenance.update(session=session, games=len(recorded), session_signature=signature)
        input_info.append(provenance)
        candidates.extend(parsed)
        games.extend(recorded)
        all_exclusions.update(exclusions)
    roots, stats = select_roots(candidates, seed, max_roots, groups)
    if not roots:
        raise ValueError("No eligible roots after bench/terminal exclusion and sampling")
    # Recheck inputs, bench, and implementation/dependency bytes before publishing.
    for item in input_info:
        path = Path(item["path"])
        if list(stat_key(path.stat())) != item["stat_at_read"] or file_hash(path) != item["sha256"]:
            raise ValueError(f"Archived input changed during preparation: {path}")
    for item in [bench_info, *modules]:
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError(f"Preparation dependency changed: {item['path']}")
    root_text = "".join(stable_json(root) + "\n" for root in roots)
    manifest = {
        "schema_version": SCHEMA, "seed_decimal": seed,
        "input_contract": {"caller_asserts_archived_immutable_inputs": True,
                           "caller_asserts_one_explicit_session_per_file": True,
                           "session_identity_provable_from_pgn": False,
                           "input_drift_checked_before_and_after": True},
        "inputs": input_info, "bench": bench_info,
        "python_chess": {"version": chess.__version__,
                         "required_checkout_commit": PINNED_COMMIT,
                         "checkout_commit_verified_by_this_tool": False},
        "modules": modules, "python_version": sys.version,
        "selection": {
            "algorithm": "fixed grid; uniform SHA256 rank within game; deduplicate; uniform SHA256 global rank",
            "first_ply_from_initial_fen": 12, "ply_spacing": 8,
            "maximum_roots_per_game": 4, "maximum_total_roots": max_roots,
            "uniformity_scope": "global rank is uniform over deduplicated per-game-capped grid pool, not all game plies",
            "no_outcome_or_evaluation_filters": True,
            "terminal_policy": "exclude forced game-over roots before labels; no claimable-draw filtering",
            "bench_policy": "exclude piece-placement/side matches even if rights/clocks differ",
            "duplicate_policy": "one representative per placement/side; rights and histories may differ",
            "grouping": "union identical canonical initial FENs and placement/side transpositions anywhere in legal mainlines",
            "independence_claim": False,
            "split_policy": "downstream label_budget.py splits whole group components",
        },
        "history_scope": "complete legal prefix since PGN initial FEN; no reconstructed pre-book history",
        "statistics": stats, "exclusions": dict(all_exclusions), "games": games,
        "roots": {"path": "roots.jsonl", "sha256": digest(root_text), "count": len(roots)},
        "limitations": ["Not a random sample of all chess positions or all game plies",
                        "FEN legality is not proof of historical reachability",
                        "Large connected groups may leave too few independent test groups",
                        "PGN mainlines only; variations, mixed sessions, and incomplete tails rejected",
                        "No engine evaluation, Elo estimate, or strength claim"],
    }
    output.mkdir()
    with open(output / "roots.jsonl", "x", encoding="utf-8", newline="\n") as stream:
        stream.write(root_text)
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    with open(output / "manifest.json", "x", encoding="utf-8", newline="\n") as stream:
        stream.write(manifest_text)
    with open(output / "manifest.sha256", "x", encoding="ascii") as stream:
        stream.write(digest(manifest_text) + "\n")
    return manifest


def named(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("Use SESSION=VALUE")
    return value.split("=", 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pgn", type=named, action="append", required=True)
    parser.add_argument("--sha256", type=named, action="append", required=True)
    parser.add_argument("--archived-inputs", action="store_true")
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", required=True)
    bench = parser.add_mutually_exclusive_group(required=True)
    bench.add_argument("--bench-source")
    bench.add_argument("--bench-fens")
    parser.add_argument("--max-roots", type=int, default=1024)
    parser.add_argument("--max-input-mib", type=int, default=128)
    args = parser.parse_args(argv)
    try:
        hashes = dict(args.sha256)
        if len(hashes) != len(args.sha256) or set(hashes) != {name for name, _ in args.pgn}:
            raise ValueError("Supply one matching --sha256 for every --pgn session")
        inputs = [{"session": name, "path": path, "sha256": hashes[name]} for name, path in args.pgn]
        manifest = prepare(inputs, args.output, seed=args.seed, bench_source=args.bench_source,
                           bench_fens=args.bench_fens, max_roots=args.max_roots,
                           max_input_mib=args.max_input_mib, archived_inputs=args.archived_inputs)
        print(json.dumps({"output": str(Path(args.output).absolute()),
                          **manifest["statistics"]}, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"prepare_corpus: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
