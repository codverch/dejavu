#!/usr/bin/env python3
"""W8 figures, laid out as in Constable (Bera et al., ISCA'24): per-task geomean bars of the ideal
configurations (their Fig. 7), a per-trace line graph sorted by gain (their Fig. 11), and the
opportunity per task (their Fig. 3a).

  figs_w8.py <results root>

Speedup = IPC(config) / IPC(base) over the same instructions of the same unit, shown as a
percentage; a task's value is the geometric mean over its five units.
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

W8 = Path(sys.argv[1]) / "w8_headroom"
LADDER = [("l1d_2x", "2× L1-D", "#e6e6e6"),
          ("install_prev", "prefetch into L2+LLC at the model call", "#bdbdbd"),
          ("ideal_l1i_prev", "ideal L1-I start-up prefetch", "#9ecae1"),
          ("ideal_l1d_prev", "ideal L1-D start-up prefetch", "#4292c6"),
          ("ideal_l1_prev", "ideal L1-I + L1-D start-up prefetch", "#08519c"),
          ("ideal_l1_self", "perfect L1 (oracle)", "#252525")]
SHORT = {"django__django-13809": "django", "psf__requests-1142": "requests", "pydata__xarray-2905": "xarray",
         "sphinx-doc__sphinx-8459": "sphinx", "sympy__sympy-11618": "sympy"}

rows = [r for r in csv.DictReader(open(W8 / "results.csv")) if r["ok"] == "1"]
ipc = {(r["uid"], r["config"]): int(r["insts"]) / int(r["cycles"]) for r in rows}
task = {r["uid"]: r["task"] for r in rows}
units = sorted({u for u, c in ipc if c == "base"}, key=lambda u: (list(SHORT).index(task[u]), u))
tasks = [t for t in SHORT if any(task[u] == t for u in units)]
spd = {(u, c): ipc[(u, c)] / ipc[(u, "base")] for (u, c) in ipc}
gm = lambda xs: float(np.exp(np.mean(np.log(xs))))  # noqa: E731
pct = lambda v: 100 * (v - 1)  # noqa: E731

summ = []
for t in tasks + ["GEOMEAN"]:
    us = [u for u in units if t == "GEOMEAN" or task[u] == t]
    d = dict(task=t, units=len(us))
    for c in sorted({c for _, c in spd} - {"base", "record_self", "record_prevproc"}):
        v = [spd[(u, c)] for u in us if (u, c) in spd]
        if len(v) == len(us):
            d[c] = f"{gm(v):.4f}"
    summ.append(d)
with open(W8 / "summary.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(dict.fromkeys(k for d in summ for k in d)), restval="")
    w.writeheader(); w.writerows(summ)

# 1. geomean per task (Constable Fig. 7)
groups = tasks + ["GEOMEAN"]
fig, ax = plt.subplots(figsize=(7.0, 2.6))
bw = 0.8 / len(LADDER); x = np.arange(len(groups)) * 1.0
top = 0
for j, (c, lab, col) in enumerate(LADDER):
    v = np.array([pct(float(next(d[c] for d in summ if d["task"] == g))) for g in groups])
    xs = x + (j - (len(LADDER) - 1) / 2) * bw
    ax.bar(xs, v, bw, color=col, edgecolor=st.INK, lw=0.4, label=lab)
    ax.text(xs[-1], v[-1] + 0.6, f"{v[-1]:.1f}%", ha="center", va="bottom", fontsize=5.2, rotation=90)
    top = max(top, v.max())
ax.axvline(x[-1] - 0.55, color=st.RULE, lw=0.6)
ax.set_xticks(x); ax.set_xticklabels([SHORT.get(g, g) for g in groups])
ax.set_ylabel("Geomean speedup\nover golden_cove (%)"); ax.set_ylim(0, top * 1.18)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
ax.legend(frameon=False, fontsize=6.2, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.2,
          columnspacing=1.0)
st.save(fig, W8 / "fig_headroom_geomean")
(W8 / "fig_headroom_geomean.png.txt").write_text(
    "Speedup of tool-call Python processes (first <=100M instructions: start-up, then the script's own work) "
    "over golden_cove, geomean of 5 processes per task. 'Start-up prefetch' uses only lines the previous process "
    "of the same script touched, rebased for ASLR (heap/stack lines dropped): what history can predict. "
    "Ideal: those lines always hit in the L1, no capacity or bandwidth cost. Perfect L1: every L1 miss hits.\n")

# 2. per trace, sorted (Constable Fig. 11)
LINES = [("perfect_all", "perfect caches, all levels", "#969696", "s"),
         ("ideal_l1_self", "perfect L1 (oracle)", "#252525", "D"),
         ("ideal_l1_prev", "ideal L1-I + L1-D start-up prefetch", "#08519c", "o"),
         ("ideal_l1d_prev", "ideal L1-D start-up prefetch", "#4292c6", "^"),
         ("install_prev", "prefetch into L2+LLC at the model call", "#bdbdbd", "v")]
order = sorted(units, key=lambda u: spd[(u, "ideal_l1_prev")])
fig, ax = plt.subplots(figsize=(7.0, 2.6))
xi = np.arange(1, len(order) + 1)
for c, lab, col, m in LINES:
    ax.plot(xi, [pct(spd.get((u, c), np.nan)) for u in order], color=col, marker=m, ms=3, lw=0.9, label=lab,
            markeredgecolor=st.INK, markeredgewidth=0.3)
ax.set_xticks(xi); ax.set_xticklabels([f"{SHORT[task[u]]}\n{u.rsplit('-', 1)[1]}" for u in order], fontsize=4.6)
ax.set_xlabel("Tool-call Python process (sorted by ideal L1 start-up prefetch speedup)")
ax.set_ylabel("Speedup over golden_cove (%)"); ax.set_ylim(0, None)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
ax.grid(axis="y", color=st.RULE, lw=0.4, ls=(0, (1, 2)))
ax.legend(frameon=False, fontsize=6.2, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.6)
st.save(fig, W8 / "fig_headroom_per_trace")
(W8 / "fig_headroom_per_trace.png.txt").write_text(
    "Every simulated tool-call Python process (5 per task), sorted by the speedup of the ideal L1-I + L1-D "
    "start-up prefetch of lines predicted from the previous process of the same script.\n")

# 3. opportunity (Constable Fig. 3a): share of L1 misses to lines the previous start-up predicts
# removed = base misses - misses with the predicted lines made hits, on the same instructions
by = {(r["uid"], r["config"]): r for r in rows}
op = defaultdict(lambda: [0, 0, 0, 0])
for u in units:
    b, i = by[(u, "base")], by.get((u, "ideal_l1_prev"))
    if i:
        for k in (task[u], "AVG"):
            o = op[k]
            o[0] += int(b["DCACHE_MISS_ONPATH"]) - int(i["DCACHE_MISS_ONPATH"]); o[1] += int(b["DCACHE_MISS_ONPATH"])
            o[2] += int(b["ICACHE_MISS_ONPATH"]) - int(i["ICACHE_MISS_ONPATH"]); o[3] += int(b["ICACHE_MISS_ONPATH"])
fig, ax = plt.subplots(figsize=(4.6, 2.2))
g2 = tasks + ["AVG"]; x = np.arange(len(g2)); bw = 0.36
for j, (a_, b_, lab, col) in enumerate(((0, 1, "L1-D misses", "#4292c6"), (2, 3, "L1-I misses", "#9ecae1"))):
    v = np.array([100 * op[g][a_] / max(op[g][b_], 1) for g in g2])
    ax.bar(x + (j - 0.5) * bw, v, bw, color=col, edgecolor=st.INK, lw=0.4, label=lab)
    for xx, vv in zip(x + (j - 0.5) * bw, v):
        ax.text(xx, vv + 1, f"{vv:.0f}%", ha="center", va="bottom", fontsize=5.2)
ax.set_xticks(x); ax.set_xticklabels([SHORT.get(g, g) for g in g2])
ax.set_ylabel("golden_cove L1 misses removed by\nideal start-up prefetch (%)"); ax.set_ylim(0, 110)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
ax.legend(frameon=False, fontsize=6.2, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
st.save(fig, W8 / "fig_opportunity")
(W8 / "fig_opportunity.png.txt").write_text(
    "Of each process's L1-D and L1-I misses on golden_cove, the share removed when every line the previous process "
    "of the same script touched (rebased) hits in the L1: the misses a history-based start-up prefetcher could "
    "remove. Sums over the 5 processes per task.\n")
print("wrote", W8 / "fig_headroom_geomean.png", W8 / "fig_headroom_per_trace.png", W8 / "fig_opportunity.png")
