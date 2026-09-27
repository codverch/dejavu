#!/usr/bin/env python3
"""W6 figure: IPC speedup of the ideal prefetcher over golden_cove, two units per phase.

  figs_w6.py <results root>

Speedup = IPC(config) / IPC(base) over the same instructions of the same unit. Every config's
bar is drawn for every unit; none is the best-of. Writes w6_more_traces/summary.csv and fig_*.png.
"""
import csv, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

W6 = Path(sys.argv[1]) / "w6_more_traces"
PHASES = ["harness start-up", "environment setup", "tool execution: python",
          "tool execution: shell", "harness: agent loop", "harness exit"]
SHOW = [("perfect_all", "perfect caches (bound)", "#d9d9d9"),
        ("stream_llc_20k", "ideal prefetch, LLC", st.COLD),
        ("stream_l2_20k", "ideal prefetch, L2", st.WARM)]
YMAX = 2.0                                           # harness exit's perfect-cache bars (3.6x, 7.0x) are cut and labelled

rows = [r for r in csv.DictReader(open(W6 / "results.csv")) if r["ok"] == "1"]
sel = {r["uid"]: r for r in csv.DictReader(open(W6 / "selection.csv"))}
ipc = {(r["cid"], r["config"]): int(r["insts"]) / int(r["cycles"]) for r in rows}
units = [u for p in PHASES for u in sel if sel[u]["unit_phase"] == p and (u, "base") in ipc]

summ = []
for u in units:
    d = dict(uid=u, phase=sel[u]["unit_phase"], task=sel[u]["task"], comm=sel[u]["comm"],
             instrs=next(r["insts"] for r in rows if r["cid"] == u and r["config"] == "base"),
             base_ipc=f"{ipc[(u, 'base')]:.3f}")
    for c in sorted({r["config"] for r in rows} - {"base", "record"}):
        if (u, c) in ipc:
            d[c] = f"{ipc[(u, c)] / ipc[(u, 'base')]:.3f}"
    summ.append(d)
keys = list(dict.fromkeys(k for d in summ for k in d))
with open(W6 / "summary.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(summ)

fig, ax = plt.subplots(figsize=(7.0, 2.6))
bw, gap = 0.26, 0.0
x = []
pos = 0.0
for i, u in enumerate(units):
    if i and sel[u]["unit_phase"] != sel[units[i - 1]]["unit_phase"]:
        pos += 0.6
    x.append(pos); pos += 1.0
x = np.array(x)
for j, (c, lab, col) in enumerate(SHOW):
    v = np.array([ipc.get((u, c), np.nan) / ipc[(u, "base")] for u in units])
    xs = x + (j - 1) * bw
    ax.bar(xs, np.minimum(v, YMAX) - 1, bw, bottom=1, color=col, edgecolor=st.INK, lw=0.4)
    for xi, vi in zip(xs, v):
        if np.isfinite(vi):
            y = min(vi, YMAX) if vi >= 1 else 1
            ax.text(xi, y + 0.01, f"{vi:.2f}" + ("↑" if vi > YMAX else ""), ha="center", va="bottom", fontsize=4.6, rotation=90)
ax.set_xticks(x)
TASK = {"psf": "requests", "pydata": "xarray", "sphinx-doc": "sphinx", "sympy": "sympy"}
ax.set_xticklabels([f"{TASK[sel[u]['task'].split('__')[0]]}\n{sel[u]['comm'].replace('python', 'py')}" for u in units], fontsize=5.5)
for p in PHASES:
    xp = [xi for xi, u in zip(x, units) if sel[u]["unit_phase"] == p]
    if xp:
        ax.text(np.mean(xp), -0.16, p, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6.5)
ax.set_ylim(1.0, YMAX * 1.08)
ax.set_ylabel("IPC speedup over golden_cove (×)")
for j, (c, lab, col) in enumerate(SHOW):
    ax.bar([np.nan], [np.nan], color=col, edgecolor=st.INK, lw=0.4, label=lab)
ax.legend(frameon=False, fontsize=6.5, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.2)
st.save(fig, W6 / "fig_speedup_by_phase")
print("wrote", W6 / "fig_speedup_by_phase.png", "and summary.csv;", len(units), "units")
