#!/usr/bin/env python3
"""Instructions per phase and process kind for whole SWE-bench tasks, from DR attribution.

  phase_mix.py <out.csv> <task>=<DR run dir> ...

A sampled window stands for `weight` windows of its process (period / window length), so a
phase's instructions are the sum of instrs x weight over its windows. Kinds: harness, python,
shell (bash/dash/sh), other.

One extra row per task, phase "tool execution: python start": the instructions of the first window
of every Python process a tool call created, up to 100M each. That is where its start-up runs
(W1: the creation region is ~73M instructions), and it is what W6's tool-execution Python units
simulate. These instructions are also counted in the ordinary "tool execution" python row.
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
        if kind == "python" and r["phase"] == "tool execution" and r["window"] == "0" and r["tid"] == r["pid"]:
            c[("tool execution: python start", "python")] += min(int(r["instrs"]), 100_000_000)
    rows += [dict(task=task, phase=p, kind=k, instrs=int(v)) for (p, k), v in sorted(c.items())]
with open(sys.argv[1], "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["task", "phase", "kind", "instrs"]); w.writeheader(); w.writerows(rows)
