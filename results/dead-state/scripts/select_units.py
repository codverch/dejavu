#!/usr/bin/env python3
"""Pick the units (process, window, thread) to simulate: PPS systematic sampling within
(task, phase) strata, size measure = represented instructions (instrs x window weight).
Every sampled unit carries its inclusion probability pi, so totals are estimated with
Horvitz-Thompson (sum y/pi) and IPC as a ratio of HT totals.

Excluded, and reported: OpenBLAS busy-wait threads (100% of the unit's instructions in
libscipy_openblas; numpy's pool spinning during harness start-up -- a 15-instruction
loop, not program work) and units whose phase could not be attributed.

  select_units.py <out.tsv> <n_per_stratum> <run_dir>...
"""
import csv
import json
import random
import zlib
import sys
from collections import defaultdict
from pathlib import Path

PHASE = {"harness start-up": "harness start-up", "environment setup": "env setup",
         "harness: agent loop": "harness session", "harness exit": "harness session",
         "tool execution": "tool exec", "child outside tool spans": "tool exec"}
SEED = 20260926


def is_spin(r):
    top = r["top_modules"].split(";")[0].strip()
    return top.startswith("100% libscipy_openblas")


def pps_systematic(units, n, rng):
    """units: list of (size, row). Returns [(row, pi)]. Certainty units (n*x/X >= 1) first."""
    chosen, rest = [], list(units)
    while True:
        tot = sum(x for x, _ in rest)
        k = n - len(chosen)
        if k <= 0 or not rest:
            return chosen
        cert = [(x, r) for x, r in rest if k * x / tot >= 1]
        if not cert:
            break
        chosen += [(r, 1.0) for _, r in cert]
        ids = {id(r) for _, r in cert}
        rest = [(x, r) for x, r in rest if id(r) not in ids]
    rng.shuffle(rest)
    step = tot / k
    start = rng.uniform(0, step)
    marks = [start + i * step for i in range(k)]
    acc, j = 0.0, 0
    for x, r in rest:
        lo, acc = acc, acc + x
        hit = False
        while j < k and marks[j] < acc:
            j += 1
            hit = True
        if hit:
            chosen.append((r, k * x / tot))
    return chosen


def main():
    out, n = sys.argv[1], int(sys.argv[2])
    rows, report = [], {}
    for run in sys.argv[3:]:
        run = Path(run)
        task = run.parent.name
        rng = random.Random(SEED ^ zlib.crc32(task.encode()))  # per-task stream: batches reproduce
        wc = list(csv.DictReader(open(run / "attribution" / "windows.csv")))
        strata = defaultdict(list)
        rep = dict(units=len(wc), spin_units=0, spin_repr=0, unattributed_units=0, unattributed_repr=0,
                   total_repr=0, strata={})
        for r in wc:
            x = int(r["instrs"]) * int(r["weight"])
            rep["total_repr"] += x
            if is_spin(r):
                rep["spin_units"] += 1
                rep["spin_repr"] += x
                continue
            ph = PHASE.get(r["phase"])
            if ph is None or x == 0:
                rep["unattributed_units"] += 1
                rep["unattributed_repr"] += x
                continue
            strata[ph].append((x, r))
        for ph, us in sorted(strata.items()):
            pick = pps_systematic(us, n, rng)
            rep["strata"][ph] = dict(units=len(us), repr=sum(x for x, _ in us), sampled=len(pick),
                                     sampled_traced_instrs=sum(int(r["instrs"]) for r, _ in pick))
            for r, pi in pick:
                zip_ = r["trace_zip"] if r["trace_zip"].startswith("/") else str(run / r["trace_zip"])
                rows.append(dict(task=task, phase=ph, cid=r["cid"], comm=r["comm"], pid=r["pid"], tid=r["tid"],
                                 window=r["window"], instrs=r["instrs"], weight=r["weight"], pi=f"{pi:.6g}",
                                 warmup=0 if int(r["window"]) == 0 else 20000000, zip=zip_,
                                 cmd=(r["tool_command"] or r["cmdline"])[:80].replace("\t", " ")))
        report[task] = rep
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    json.dump(report, open(out.replace(".tsv", ".report.json"), "w"), indent=1)
    tot = sum(int(r["instrs"]) for r in rows)
    print(f"{len(rows)} units, {tot/1e9:.2f} B traced instrs to simulate per config")
    for t, rep in report.items():
        print(t, f"spin {rep['spin_repr']/rep['total_repr']:.1%}",
              {k: (v["units"], v["sampled"], f"{v['repr']/1e9:.1f}B") for k, v in rep["strata"].items()})


if __name__ == "__main__":
    main()
