#!/usr/bin/env python3
"""Freeze bounded original writer prefixes without interpreting label values."""
import datetime, hashlib, json, os, resource, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "engines" / "repeated-labels-20261025"
DATA = Path("/home/lupe/nnue/data/dg7")
BIN = Path("/home/lupe/nnue/data/bin/dg7-chesssi")
ARCHIVE = Path("/home/lupe/nnue/data/bin/dg7-src")
LAUNCH = Path("/mnt/c/Users/Lupe/claude-work/gen7-run.sh")
CAP = 2_000_000
SEEDS = list(range(9291611100, 9291611113))
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
if set(os.sched_getaffinity(0)) != {19}:
    raise RuntimeError("Run exactly on CPU 19")
def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
def metadata(path):
    s = path.stat()
    return dict(path=str(path), size=s.st_size, inode=s.st_ino, device=s.st_dev,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
def normalized(path):
    return path.read_bytes().replace(b"\r\n", b"\n")
source = {}
for relative in ["Makefile"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").glob("*") if p.suffix in (".cpp", ".h")):
    a, b = ROOT / relative, ARCHIVE / relative
    if normalized(a) != normalized(b):
        raise RuntimeError("Archived source differs from pinned worktree: " + relative)
    source[relative] = dict(archive_sha256=digest(b), worktree_sha256=digest(a),
                           normalized_sha256=hashlib.sha256(normalized(a)).hexdigest())
net_rel = "nets/net10-h256.nnue"
if digest(ROOT / net_rel) != digest(ARCHIVE / net_rel):
    raise RuntimeError("Network identity mismatch")
binary_hash = digest(BIN)
processes = {}
for p in Path("/proc").iterdir():
    if not p.name.isdigit():
        continue
    try:
        args = (p / "cmdline").read_bytes().split(b"\0")
        args = [x.decode() for x in args if x]
    except (OSError, UnicodeError):
        continue
    if len(args) != 7 or args[0] != str(BIN) or args[1] != "datagen":
        continue
    seed = int(args[4])
    if seed not in SEEDS:
        continue
    expected = [str(BIN), "datagen", str(DATA / ("dg7-" + str(seed) + ".txt")),
                "1000000", str(seed), "5000", "8"]
    if args != expected or seed in processes:
        raise RuntimeError("Writer arguments or uniqueness mismatch")
    if digest(p / "exe") != binary_hash:
        raise RuntimeError("Running binary mismatch")
    fds = []
    for fd in (p / "fd").iterdir():
        try:
            if os.readlink(fd) == args[2]:
                fds.append(dict(fd=fd.name, info=(p / "fdinfo" / fd.name).read_text()))
        except OSError:
            pass
    if not fds:
        raise RuntimeError("Writer has no descriptor for its declared stream")
    status = (p / "status").read_text()
    affinity = next(x for x in status.splitlines() if x.startswith("Cpus_allowed_list:"))
    processes[seed] = dict(pid=int(p.name), argv=args, proc_stat=(p / "stat").read_text(),
                           affinity=affinity, output_descriptors=fds)
if sorted(processes) != SEEDS:
    raise RuntimeError("Expected all 13 documented writers")
OUT.mkdir(parents=True, exist_ok=False)
(OUT / "snapshots").mkdir()
streams = []
for i, seed in enumerate(SEEDS):
    p = DATA / ("dg7-" + str(seed) + ".txt")
    streams.append(dict(writer_id="dg7-" + str(seed), seed=seed, source_path=str(p),
                        source_start=0, source_stat=metadata(p),
                        row_allowance=CAP // len(SEEDS) + (i < CAP % len(SEEDS)),
                        process=processes[seed]))
plan = dict(schema=1, phase="pre-label-examination", timestamp=now(), source_commit="35cb09b31fc1efae63e13c1da17a9285623e1cb5",
            branch="astra/repeated-label-pilot-20261025",
            protocol_commit="4a5091ff06de55a9c7d98c920db7ff57f38f99c6",
            source_sha256=source, binary_sha256=binary_hash,
            network_sha256=digest(ARCHIVE / net_rel), network=net_rel, nodes=5000, random_plies=8,
            adjudication=dict(max_searched_plies=400, win_score_cp=2500, win_plies=6),
            launch_path=str(LAUNCH), launch_sha256=digest(LAUNCH), launch_text=LAUNCH.read_text(),
            source_record=(DATA / "SOURCE").read_text(), latest_cohort="dg7-net10-5000-8",
            earlier_cohort=None, earlier_omission_reason="Historical dg6 node/random-opening launch provenance was not established; use latest-only allocation permitted by protocol.",
            raw_row_cap=CAP, memory_cap_bytes=2*1024**3, cpu_affinity=[19],
            bin_rule="int.from_bytes(SHA256(UTF8('20261024|writer_id|group_start_offset')), 'big') % 5",
            streams=streams)
write_json(OUT / "plan.json", plan)
(OUT / "PROTOCOL.md").write_text((ROOT / "docs/research/repeated-labels-2026-10-25/PROTOCOL.md").read_text())
total = 0
for stream in streams:
    src = Path(stream["source_path"])
    dst = OUT / "snapshots" / (stream["writer_id"] + ".snapshot.txt")
    rows = end = 0
    h = hashlib.sha256()
    with src.open("rb") as fi, dst.open("xb") as fo:
        start_stat = os.fstat(fi.fileno())
        expected = stream["source_stat"]
        if (start_stat.st_dev, start_stat.st_ino) != (expected["device"], expected["inode"]):
            raise RuntimeError("Source replaced before capture")
        while rows < stream["row_allowance"] and end < expected["size"]:
            remaining = expected["size"] - end
            line = fi.readline(min(8192, remaining))
            if not line.endswith(b"\n"):
                if len(line) == 8192:
                    raise RuntimeError("Unexpected oversized record")
                break
            fo.write(line)
            h.update(line)
            rows += 1
            end += len(line)
        after = os.fstat(fi.fileno())
        if after.st_size < expected["size"]:
            raise RuntimeError("Source truncated during capture")
    stream.update(snapshot_path=str(dst), sha256=h.hexdigest(), raw_rows=rows,
                  source_end=end, source_after=metadata(src))
    total += rows
    print(stream["writer_id"], rows, "rows", end, "bytes", flush=True)
if total > CAP:
    raise RuntimeError("Row cap exceeded")
manifest = dict(plan)
manifest.update(phase="frozen-before-label-analysis", completed=now(), total_raw_rows=total,
                streams=streams, plan_sha256=digest(OUT / "plan.json"),
                protocol_sha256=digest(OUT / "PROTOCOL.md"))
write_json(OUT / "manifest.json", manifest)
print(json.dumps(dict(manifest=str(OUT / "manifest.json"), rows=total,
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)), flush=True)
