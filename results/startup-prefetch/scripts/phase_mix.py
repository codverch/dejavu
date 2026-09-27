#!/usr/bin/env python3
"""Instructions per phase and process kind for whole SWE-bench tasks, from DR attribution.

  phase_mix.py <out.csv> <task>=<DR run dir> ...

A sampled window stands for `weight` windows of its process (period / window length), so a
phase's instructions are the sum of instrs x weight over its windows. Kinds: harness, python,
shell (bash/dash/sh), other.
"""
import csv, sys
from collections import Counter
from pathlib import Path

rows = []
for arg in sys.argv[2:]:
    task, d = arg.split("=", 1)
    c = Counter()
    for r in csv.DictReader(open(Path(d) / "attribution" / "windows.csv")):
        kind = "harness" if r["is_harness"] == "1" else "python" if r["comm"].startswith("python") else \
            "shell" if r["comm"] in ("bash", "dash", "sh") else "other"
        c[(r["phase"], kind)] += int(r["instrs"]) * float(r["weight"])
    rows += [dict(task=task, phase=p, kind=k, instrs=int(v)) for (p, k), v in sorted(c.items())]
with open(sys.argv[1], "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["task", "phase", "kind", "instrs"]); w.writeheader(); w.writerows(rows)
