#!/usr/bin/env python3
"""Distance between successive start-ups of tool-call Python processes, per task: the wall-clock gap
from one process's first traced instruction to the next's (all scripts), and to the next start-up
of the same script. From the DR attribution (window 0 of each process's main thread).

  startup_gaps.py <out.csv> <task>=<DR run dir> ...
"""
import csv, sys
from pathlib import Path

rows = []
for arg in sys.argv[2:]:
    task, d = arg.split("=", 1)
    ps = sorted(((float(r["t_start"]), r["cmdline"].split()[1] if len(r["cmdline"].split()) > 1 else r["comm"])
                 for r in csv.DictReader(open(Path(d) / "attribution" / "windows.csv"))
                 if r["phase"] == "tool execution" and r["comm"].startswith("python") and r["window"] == "0"
                 and r["tid"] == r["pid"]))
    last = {}
    for (t0, s0), (t1, s1) in zip(ps, ps[1:]):
        rows.append(dict(task=task, kind="any", gap_s=round(t1 - t0, 4)))
    for t, s in ps:
        if s in last:
            rows.append(dict(task=task, kind="same script", gap_s=round(t - last[s], 4)))
        last[s] = t
with open(sys.argv[1], "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["task", "kind", "gap_s"]); w.writeheader(); w.writerows(rows)
print(len(rows), "gaps")
