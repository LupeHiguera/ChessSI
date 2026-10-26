#!/usr/bin/env python3
"""Bounded instrumentation-only research; never modifies repository engine sources."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "engines/rejected-nnue-audit"
COPY = OUT / "instrumented"
DOC = Path(__file__).resolve().parent

PROBE = r'''
#include <cstdio>
namespace {
struct RejectedMoveAudit {
    unsigned long long moves[2][4][2]{};
    unsigned long long updates[2][4][2]{};
    unsigned long long laneOps[2][4][2]{};
    ~RejectedMoveAudit() {
        for (int c = 0; c < 2; ++c)
            for (int t = 0; t < 4; ++t)
                for (int l = 0; l < 2; ++l)
                    std::fprintf(stderr, "REJECT_AUDIT %d %d %d %llu %llu %llu\n",
                                 c, t, l, moves[c][t][l], updates[c][t][l], laneOps[c][t][l]);
    }
} rejectedMoveAudit;
}
'''


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1 << 20), b""):
            h.update(data)
    return h.hexdigest()


def invoke(label, command, cwd=ROOT, timeout=180):
    start = time.monotonic()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    (OUT / (label + ".stdout")).write_text(result.stdout)
    (OUT / (label + ".stderr")).write_text(result.stderr)
    record = {"label": label, "command": [str(x) for x in command], "cwd": str(cwd),
              "returncode": result.returncode, "wall_seconds": time.monotonic() - start,
              "stdout_sha256": sha(OUT / (label + ".stdout")),
              "stderr_sha256": sha(OUT / (label + ".stderr"))}
    with (OUT / "commands.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps({"label": label, "returncode": result.returncode,
                      "wall_seconds": round(record["wall_seconds"], 3)}), flush=True)
    if result.returncode:
        raise RuntimeError(label + ": " + result.stderr[-2000:] + result.stdout[-2000:])
    return result


def counters(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("REJECT_AUDIT "):
            c, t, legal, moves, updates, ops = map(int, line.split()[1:])
            rows.append(dict(parent_in_check=c, move_type=["normal", "promotion", "en_passant", "castling"][t],
                             legal=legal, moves=moves, updates=updates, lane_ops=ops))
    assert len(rows) == 16
    assert all(r["moves"] == r["updates"] for r in rows), "Pinned embedded network required"
    n = sum(r["updates"] for r in rows)
    bad = sum(r["updates"] for r in rows if not r["legal"])
    ops = sum(r["lane_ops"] for r in rows)
    bad_ops = sum(r["lane_ops"] for r in rows if not r["legal"])
    return dict(rows=rows, attempted_updates=n, rejected_updates=bad,
                rejected_fraction=bad/n, lane_ops=ops, rejected_lane_ops=bad_ops,
                rejected_lane_ops_fraction=bad_ops/ops)


def main():
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite an existing audit")
    OUT.mkdir(parents=True)
    git_pointer = (ROOT / ".git").read_text().strip().removeprefix("gitdir: ")
    if re.match(r"^[A-Za-z]:[/\\]", git_pointer):
        git_pointer = "/mnt/" + git_pointer[0].lower() + "/" + git_pointer[3:].replace("\\", "/")
    initial = subprocess.check_output(["git", "--git-dir=" + git_pointer,
                                       "--work-tree=" + str(ROOT), "rev-parse", "HEAD"],
                                      cwd=ROOT, text=True).strip()
    assert initial == "35cb09b31fc1efae63e13c1da17a9285623e1cb5", initial
    source_paths = sorted(list((ROOT / "src").glob("*")) + [ROOT / "Makefile"])
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths if p.is_file()}
    manifest = dict(source_commit=initial, source_hashes=source_hashes, script_sha256=sha(__file__),
                    protocol_sha256=sha(DOC / "PROTOCOL.md"), network_sha256=sha(ROOT / "nets/net10-h256.nnue"),
                    affinity=sorted(os.sched_getaffinity(0)), build_cpus="14-19", runtime_cpu=19,
                    compiler=subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                    source_changes="Instrumentation in ignored copy only; no NNUE work skipped")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copytree(ROOT / "src", COPY / "src")
    shutil.copytree(ROOT / "tests", COPY / "tests")
    shutil.copy2(ROOT / "Makefile", COPY / "Makefile")
    path = COPY / "src/position.cpp"
    code = path.read_text()
    anchor = 'bool Position::do_move(Move m) {\n'
    assert code.count(anchor) == 1
    code = code.replace(anchor, anchor + '    const bool auditParentCheck = in_check();\n')
    anchor = '    push_accumulator(delta);\n    return !attacked(king_square(us), them);'
    assert code.count(anchor) == 1
    code = code.replace(anchor, '''    push_accumulator(delta);
    const bool auditLegal = !attacked(king_square(us), them);
    const int auditType = type >> 14;
    ++rejectedMoveAudit.moves[auditParentCheck][auditType][auditLegal];
    if (accGeneration) {
        ++rejectedMoveAudit.updates[auditParentCheck][auditType][auditLegal];
        rejectedMoveAudit.laneOps[auditParentCheck][auditType][auditLegal]
            += 2ULL * accHidden * (delta.adds + delta.subs);
    }
    return auditLegal;''')
    path.write_text(PROBE + code)
    invoke("base-build-test", ["taskset", "-c", "14-19", "make", "-j6", "test"])
    invoke("instrumented-build-test", ["taskset", "-c", "14-19", "make", "-j6", "test",
                                      "EVALFILE=" + str(ROOT / "nets/net10-h256.nnue")], cwd=COPY)
    summary = {"bench": [], "datagen": None, "interpretation": None}
    for depth in (7, 11):
        base = invoke("base-bench-" + str(depth), ["taskset", "-c", "19", str(ROOT / "chesssi"), "bench", str(depth)], timeout=120)
        probe = invoke("instrumented-bench-" + str(depth), ["taskset", "-c", "19", str(COPY / "chesssi"), "bench", str(depth)], timeout=120)
        base_nodes = int(re.search(r"(\d+) nodes \d+ nps", base.stdout).group(1))
        probe_nodes = int(re.search(r"(\d+) nodes \d+ nps", probe.stdout).group(1))
        assert base_nodes == probe_nodes
        if depth == 7:
            assert base_nodes == 158506
        summary["bench"].append(dict(depth=depth, nodes=base_nodes, **counters(probe.stderr)))
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name, binary in (("base", ROOT / "chesssi"), ("instrumented", COPY / "chesssi")):
        result = invoke(name + "-datagen", ["taskset", "-c", "19", str(binary), "datagen",
                        str(OUT / (name + "-datagen.txt")), "16", "20261025", "5000", "8"], timeout=600)
        if name == "instrumented":
            summary["datagen"] = counters(result.stderr)
    base_data = OUT / "base-datagen.txt"
    probe_data = OUT / "instrumented-datagen.txt"
    assert sha(base_data) == sha(probe_data), "Self-play output changed"
    summary["datagen"].update(games=16, seed=20261025, requested_nodes=5000, random_plies=8,
                              rows=sum(1 for _ in base_data.open()), sha256=sha(base_data), byte_identical=True)
    fractions = [summary["bench"][1]["rejected_fraction"], summary["datagen"]["rejected_fraction"]]
    summary["interpretation"] = ("Park" if max(fractions) < .01 else
                                  "Justifies later implementation/timing trial" if max(fractions) >= .05 else
                                  "Inconclusive, low priority")
    summary["source_unchanged"] = all(sha(ROOT / p) == h for p, h in source_hashes.items())
    assert summary["source_unchanged"]
    summary["binaries"] = {"base": sha(ROOT / "chesssi"), "instrumented": sha(COPY / "chesssi")}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"complete": True, "result": summary["interpretation"], "fractions": fractions}), flush=True)


if __name__ == "__main__":
    main()
