#!/usr/bin/env python3
"""Harness instructions per agent step, by SWE-agent component (replayed django-11333, 41 steps)."""
import csv, sys
sys.path.insert(0, "/h/deepanjm/mise/results/swe-bench-traces/e2e-uarch/scripts")
import anish_style as st
import matplotlib.pyplot as plt
from pathlib import Path
R = [r for r in csv.DictReader(open(sys.argv[1])) if int(r["step"]) > 0]
G = [("model_query", "LLM request/response (litellm)", "#1f4e79"),
     ("save_trajectory", "save trajectory (json.dumps)", "#c55a11"),
     ("get_traj_data", "copy trajectory (deepcopy)", "#e6ab02"),
     ("forward", "query snapshot (deepcopy) + parse", "#7570b3"),
     ("gc", "cyclic GC", "#66a61e")]
st.use(); fig, ax = plt.subplots(figsize=(3.4, 2.1))
x = [int(r["step"]) for r in R]; base = [0.0] * len(R)
known = {g for g, _, _ in G}; labels = []
for g, lab, c in G:
    y = [int(r[g]) / 1e6 for r in R]
    ax.fill_between(x, base, [b + v for b, v in zip(base, y)], color=c, lw=0, step="mid")
    top = [b + v for b, v in zip(base, y)]
    labels.append(((base[-1] + top[-1]) / 2, lab, c))
    base = top
rest = [sum(int(v) for k, v in r.items() if k not in known and k != "step") / 1e6 for r in R]
ax.fill_between(x, base, [b + v for b, v in zip(base, rest)], color="#d9d9d9", lw=0, step="mid")
labels.append((base[-1] + rest[-1] / 2, "other", st.MUTED))
ys = []
for y, lab, c in labels:                          # keep direct labels at least 55M apart
    y = max(y, ys[-1] + 55) if ys else y; ys.append(y)
    ax.text(x[-1] + 0.6, y, lab, fontsize=6, va="center", color=c)
ax.set_xlim(1, x[-1]); ax.set_ylim(0, None)
ax.set_xlabel("Agent step"); ax.set_ylabel("Harness instructions\nper step (millions)")
st.save(fig, Path(sys.argv[2]))
