#!/usr/bin/env python3
import hashlib, json, math, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
DOC = Path(__file__).resolve().parent
RUN = ROOT / "engines/repeated-labels-20261025"
OUT = RUN / "analysis-v2"
EVIDENCE = DOC / "evidence"
EVIDENCE.mkdir(exist_ok=False)
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def save(path,obj):
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
s=json.loads((OUT/"summary.json").read_text())
m=json.loads((RUN/"manifest.json").read_text())
assert s["manifest_sha256"]==sha(RUN/"manifest.json")
assert s["analyzer_sha256"]==sha(DOC/"analyze.py")
assert sum(x["raw_rows"] for x in m["streams"])==s["counts"]["raw_rows"]==2_000_000
assert s["status"]=="inconclusive_coverage"
assert s["counts"]["eligible_full_fen_identities"]==1
assert s["counts"]["held_out_conservative_groups"]==3
assert s["peak_rss_bytes"] < 2*1024**3
rows=[json.loads(line) for line in (OUT/"per_identity.jsonl").read_text().splitlines()]
assert len(rows)==1
for arm in ("M","L"):
    values=s["primary"][arm]
    assert math.isclose(values["y2"],sum(r["errors"][arm]["y2"] for r in rows)/len(rows),abs_tol=1e-16)
    assert math.isclose(values["y2"],.5625*values["q2"]+.0625*values["r2"]+.375*values["qr"],abs_tol=1e-16)
for source,name in [(RUN/"plan.json","plan.json"),(RUN/"manifest.json","manifest.json"),
                    (OUT/"summary.json","summary.json"),(OUT/"per_identity.jsonl","per_identity.jsonl"),
                    (RUN/"analysis/interruption.json","interruption.json"),
                    (RUN/"analysis/analyzer-v1.py","analyzer-v1.py")]:
    shutil.copyfile(source,EVIDENCE/name)
checks=dict(analysis_tests=dict(passed=15,failed=0,version="v2",cpu=19),
            perft=dict(passed=35,failed=0),rfp_boundaries=dict(passed=17,failed=0),
            bench=dict(nodes=158506,cpu=18,engine_source_changed=False),
            result_checks=["manifest hash","analyzer hash","2M row total","per-identity aggregate","blend component identity","resource cap"],
            independent_review="GPT-6 Astra ultra: source/capture metadata, metrics and interpretation reviewed; no extra snapshot scan",
            execution=dict(analysis_cpu=19,analysis_address_space_limit=2147483648,
                           analysis_cpu_seconds_limit=900,build_and_test_cpus="14-18",build_jobs=5),
            no_gpu_job=True,no_match=True,no_elo_claim=True)
save(EVIDENCE/"validation.json",checks)
artifacts=[]
for path in sorted(EVIDENCE.iterdir()):
    artifacts.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path),archived=True))
for path in [OUT/"pilot.sqlite",OUT/"static_ranges.jsonl"]:
    artifacts.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path),archived=False,
                          reason="large bounded derivative retained locally; immutable input hashes are in manifest"))
save(EVIDENCE/"artifacts.json",artifacts)
report=f"""# Repeated-label pilot: inconclusive coverage

Date: 2026-10-25. Owner: GPT-6 (Codex); analyzer implementation and independent review: GPT-6 Astra ultra.

**Decision: stop this bounded pilot for insufficient comparable repeats.** The frozen two-million-row sample contains one eligible full-context position across three conservative groups. The protocol requires at least 500 identities, 200 groups and 0.5% coverage. No trainer change, GPU training, match or Elo result follows from this screen.

## Population and provenance

Source and compiled network: ChessSI `35cb09b`, net10-h256, 5,000 requested nodes per move, eight random opening plies. Thirteen original generation-7 writers, seeds 9291611100 through 9291611112, supplied equal prefix allowances: 153,847 rows for the first two, 153,846 for the other eleven. All two million records were captured.

Before examining label values, `freeze.py` recorded the launch script, runtime writer arguments, open output descriptors, inode metadata, binary/network hashes, and archived source hashes. Archived Makefile/source files matched the pinned worktree after line-ending normalization; network bytes and running executable hashes matched. Bounded snapshots, exact offsets and SHA-256 hashes were frozen before analysis. Claude's original files remained read-only.

The current net10 generation is the latest documented cohort. Historical generation-6 launch budgets could not be established from the available records, so the protocol-permitted latest-only allocation was fixed in advance. F versus L / teacher refresh is omitted. This is a prefix study, not an estimate of the entire training corpus.

The frozen [protocol](PROTOCOL.md) is an exact snapshot of PR29's controls; its original research-only status paragraph is historical. This result supersedes that execution status for this pilot.

## Fixed gates and observed coverage

| Measure | Observed | Required |
| --- | --- | --- |
| Raw records / writers | 2,000,000 / 13 | At most 2,000,000 |
| Complete conservative groups | 20,995 | Not exact game identities |
| Excluded final groups / rows | 13 / 746 | Exclude each range's unfinished group |
| Retained clock-zero rows | 536,452 | Context filter fixed before analysis |
| Distinct first-four-FEN keys in all raw rows | 1,933,340 | Coverage denominator |
| Eligible exact six-field FEN identities | **1** | At least 500 |
| Held-out groups for eligible identities | **3** | At least 200 |
| Eligible distinct-key coverage | **0.000051724%** | At least 0.5% |
| Positive reporting bins | 3 of 5 | At least 4 of 5 |
| Writers with at least 100 eligible identities | 0 | All qualifying writers positive |

The writer condition is vacuous here; it is not positive evidence. The three populated bins describe the same sole identity, not independent replications.

Broader repeats exist: 27,538 four-field keys repeat, and 11,504 occur in at least three complete groups. Among repeated keys, 25,717 have different halfmove clocks and 27,236 have different absolute plies. Those broader populations are descriptive; they were not substituted into the primary comparison after the result.

## Error diagnostics, with their limits

The sole eligible FEN is `8/8/8/8/8/4K3/6k1/5q2 w - - 0 72`: king versus king and queen. Three held-out observations produce MSE(L) = {s['primary']['L']['y2']:.12g} and MSE(M) = {s['primary']['M']['y2']:.12g}. Their approximately 50% relative difference says nothing reliable about population denoising or playing strength.

Outcome-error and cross terms are zero in this case; the variation is entirely in search-score targets. The blend identity `MSE_y = 0.5625 E[e_q^2] + 0.0625 E[e_r^2] + 0.375 E[e_q e_r]` reconciles for both arms. Each identity receives one weight after averaging its held-out-group errors.

All two million static fields were checked within the same sample. There were 1,933,311 board/side input identities and **zero nonzero static-score ranges**. This supports consistency within sampled inputs; it is not a proof of inference correctness in every position.

## Execution and checks

The completed analysis ran on CPU 19 under a hard 2 GiB address-space limit and 900 CPU-second ceiling. It took {s['wall_seconds']:.2f} seconds wall time and {s['cpu_seconds']:.2f} CPU seconds; reported peak RSS was {s['peak_rss_bytes']/1024**2:.2f} MiB. No GPU was used.

The first attempt was interrupted during ingestion because 32 MiB cache and 5,000-row commits caused heavy DrvFS I/O. No result metrics had been inspected. Its source and interruption record are preserved. A runtime-only retry used a 512 MiB cache, synchronous NORMAL and one commit per verified writer. The same hashed prefixes, ordering, formulas and gates were reused; the sample was not expanded.

Validation: all 15 synthetic analysis tests passed before and after the runtime change. Repository checks passed (35 perft and 17 search-boundary cases, zero failures), and the unchanged engine bench was **158506**. Code review checked whole-group exclusion, equal identity weighting, Black orientation, the coverage denominator and metadata separation. Independent review agreed with the stop decision.

## Evidence and reproduction

- [Frozen manifest](evidence/manifest.json), [pre-analysis plan](evidence/plan.json).
- [Machine-readable result](evidence/summary.json), [per-identity errors](evidence/per_identity.jsonl), [validation](evidence/validation.json).
- [Artifact hashes](evidence/artifacts.json), [interrupted-attempt record](evidence/interruption.json), [original analyzer](evidence/analyzer-v1.py).
- `engines/repeated-labels-20261025/` retains the snapshots, both attempt directories, SQLite database and full static-range output locally. Large derivatives are not committed.

Run from this worktree after supplying the immutable snapshots at the manifest paths:

```sh
taskset -c 19 python3 -B -m unittest discover -s docs/research/repeated-labels-2026-10-25 -p test_analyze.py
taskset -c 19 prlimit --as=2147483648 --cpu=900 -- python3 -B docs/research/repeated-labels-2026-10-25/analyze.py engines/repeated-labels-20261025/manifest.json engines/repeated-labels-20261025/reproduction
```

The output directory must be new. Verify hashes before comparing results; moving snapshots requires an explicitly recorded manifest-path adaptation.

## Consequence

This closes the current pilot as **Inconclusive (coverage)**. It does not show that averaging is harmful or useless, and it supplies no training promotion. Do not enlarge this sample or relax clock/ply/teacher matching to rescue it. Any broader-context proposal must state a different hypothesis and controls before another experiment.
"""
(DOC/"RESULT.md").write_text(report)
ideas=ROOT/"docs/IDEAS.md"
text=ideas.read_text()
header="| --- | --- | --- | --- | --- | --- | --- | --- |\n"
row="| 2026-10-25 | GPT-6 (Codex), GPT-6 Astra ultra | Known | Repeated-position label aggregation, bounded latest-teacher offline gate | Inconclusive (coverage) | Not run | 0 games; 2M rows, core 19, 2 GiB cap; 1 eligible identity / 3 groups | Not run |\n"
assert header in text
text=text.replace(header,header+row,1)
old="Bounded CPU pilot started 2026-10-25 on core 19: frozen 2M-row generation-7/net10 sample, 2 GiB cap, branch `astra/repeated-label-pilot-20261025`; latest-teacher aggregation only because earlier-cohort launch settings were not established. No training or Elo result yet."
new="**Pilot completed 2026-10-25: Inconclusive (coverage).** Two million generation-7/net10 rows yielded one eligible full-context identity in three groups, below the fixed thresholds. Pilot stopped; no training or Elo result. [Result](research/repeated-labels-2026-10-25/RESULT.md), branch `astra/repeated-label-pilot-20261025`."
assert old in text
ideas.write_text(text.replace(old,new,1))
print(json.dumps(dict(status=s["status"],evidence=str(EVIDENCE),artifact_count=len(artifacts))))
