#!/usr/bin/env python3
"""One figure to share: speedup of tool-call Python processes when the L1-D never misses.

  fig_perfect_l1d.py <results root>

Units are W8's 25 processes (5 per task, first <=100M instructions: start-up, then the script's own
work). Speedup = IPC with --perfect_dcache / IPC on golden_cove, same instructions; bars are the
geomean over a task's 5 processes, dots the individual processes.
"""
import csv, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

W8 = Path(sys.argv[1]) / "w8_headroom"
TASKS = {"django__django-13809": "django", "psf__requests-1142": "requests", "pydata__xarray-2905": "xarray",
         "sphinx-doc__sphinx-8459": "sphinx", "sympy__sympy-11618": "sympy"}

r = {(x["uid"], x["config"]): x for x in csv.DictReader(open(W8 / "results.csv")) if x["ok"] == "1"}
ipc = lambda u, c: int(r[(u, c)]["insts"]) / int(r[(u, c)]["cycles"])  # noqa: E731
per = {t: [100 * (ipc(u, "perfect_l1d") / ipc(u, "base") - 1)
           for (u, c), x in r.items() if c == "base" and x["task"] == t and (u, "perfect_l1d") in r] for t in TASKS}
gm = lambda v: 100 * (np.exp(np.mean(np.log1p(np.array(v) / 100))) - 1)  # noqa: E731
allv = [v for t in TASKS for v in per[t]]
labels = list(TASKS.values()) + ["geomean"]
vals = [gm(per[t]) for t in TASKS] + [gm(allv)]

fig, ax = plt.subplots(figsize=(4.4, 2.4))
x = np.arange(len(labels))
ax.bar(x, vals, 0.62, color=["#4292c6"] * len(TASKS) + ["#08519c"], edgecolor=st.INK, lw=0.5)
for i, t in enumerate(TASKS):
    ax.scatter(np.full(len(per[t]), i) + np.linspace(-0.16, 0.16, len(per[t])), per[t], s=6, color=st.INK, zorder=3,
               lw=0)
tops = [max([vals[i]] + per[t]) for i, t in enumerate(TASKS)] + [vals[-1]]
for xi, v, tp in zip(x, vals, tops):
    ax.text(xi, tp + max(vals) * 0.04, f"{v:.1f}%", ha="center", va="bottom", fontsize=7)
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylabel("Speedup with a perfect L1-D\nover golden_cove (%)")
ax.set_ylim(0, max(max(allv), max(vals)) * 1.25)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
ax.set_xlabel("SWE-bench task (5 tool-call Python processes each; dots = processes)")
st.save(fig, W8 / "fig_perfect_l1d")
(W8 / "fig_perfect_l1d.png.txt").write_text(
    "IPC speedup of the Python processes that SWE-agent's tool calls create, when every L1 data-cache access "
    "hits, over a Golden Cove-like core (Scarab, PARAMS.golden_cove). 5 processes per task, each simulated over "
    "its first 100M instructions (interpreter start-up, then the tool's own work); bars are geomeans, dots are "
    "individual processes.\n")
print("\n".join(f"{l}: {v:.1f}%" for l, v in zip(labels, vals)), "\nrange", f"{min(allv):.1f}-{max(allv):.1f}%")
