#!/usr/bin/env python3
"""Summarize the fixed sparse-update screen; never infer engine strength."""
import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

path = Path(sys.argv[1])
rows = list(csv.DictReader(path.open(newline="")))
assert len(rows) == 630, f"Expected 630 raw rows, got {len(rows)}"
groups = defaultdict(dict)
for row in rows:
    assert (int(row["passes"]), int(row["operations"]), int(row["hidden"])) == (32, 65536, 256)
    key = (float(row["q"]), row["correlation"], row["kind"])
    slot = (int(row["pair"]), row["kernel"])
    assert slot not in groups[key], (key, slot)
    assert float(row["ns_per_op"]) > 0
    groups[key][slot] = row
expected = {(q, c, k) for q in (0, .125, .25, .5, 1)
            for c in ("independent", "piece_type_tied")
            for k in ("quiet_A1S1", "capture_A1S2", "castle_A2S2")}
assert set(groups) == expected
summaries = []
for (q, correlation, kind), group in sorted(groups.items()):
    assert len(group) == 21
    ratios, dense, sparse, copies = [], [], [], []
    for pair in range(1, 8):
        d, s, c = (group[(pair, k)] for k in ("dense", "sparse", "copy_only_non_equivalent"))
        assert d["checksum"] == s["checksum"], "Candidate output differs"
        assert len({x["observed_union_fraction"] for x in (d, s, c)}) == 1
        assert int(d["order"]) == (1 if pair % 2 else 2)
        assert int(s["order"]) == (2 if pair % 2 else 1)
        assert int(c["order"]) == 3
        dv, sv, cv = (float(x["ns_per_op"]) for x in (d, s, c))
        dense.append(dv); sparse.append(sv); copies.append(cv); ratios.append(sv / dv)
    summary = dict(q=q, correlation=correlation, kind=kind,
                   active_fraction=float(d["active_mask_fraction"]),
                   union_fraction=float(d["observed_union_fraction"]),
                   dense_ns_median=statistics.median(dense),
                   sparse_ns_median=statistics.median(sparse),
                   copy_ns_median=statistics.median(copies),
                   paired_ratio_median=statistics.median(ratios),
                   paired_ratios=ratios, faster_pairs=sum(x < 1 for x in ratios))
    summary["meets_threshold"] = summary["paired_ratio_median"] <= .90 and summary["faster_pairs"] >= 6
    summaries.append(summary)
primary = [s for s in summaries if s["q"] == .5 and s["correlation"] == "independent"
           and s["kind"] in ("quiet_A1S1", "capture_A1S2")]
assert len(primary) == 2
print(json.dumps(dict(raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), raw_rows=len(rows),
                     verdict="PASS" if all(s["meets_threshold"] for s in primary) else "FAIL",
                     primary=primary, summaries=summaries), indent=2))
