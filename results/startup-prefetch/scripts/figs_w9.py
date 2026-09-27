#!/usr/bin/env python3
"""W9 motivation figures, one question each, drawn the way the SAFARI papers draw theirs (Pythia
MICRO'21 Fig. 1; Hermes MICRO'22 Figs. 2-5; Constable ISCA'24 Figs. 3, 6, 7; Athena HPCA'26 Fig. 1),
in the style of w8_headroom/fig_headroom_geomean.png (lib/safari_style.py).

  figs_w9.py <results root>

Aggregation: a speedup per phase is the geometric mean over the phase's units; a fraction per phase
is a ratio of sums over its units (every unit is at most 100M instructions). AVG weighs every phase
equally, as the SAFARI papers weigh workload categories: the mean of the phase values (the geomean,
for speedups). A sum over all units would let harness exit, with tens of times more misses than any
other phase, set the average. Writes w9_motivation/
fig_NN_*.png with captions (.png.txt) and numbers.csv (every plotted value).
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import safari_style as S  # noqa: E402
from safari_style import plt  # noqa: E402

R = Path(sys.argv[1]); W9 = R / "w9_motivation"
TASKS = {"django__django-13809": "django", "psf__requests-1142": "requests", "pydata__xarray-2905": "xarray",
         "sphinx-doc__sphinx-8459": "sphinx", "sympy__sympy-11618": "sympy"}
TN = list(TASKS.values())
PH = [("harness start-up", "harness\nstart-up"), ("environment setup", "env.\nsetup"),
      ("tool execution: python", "tool:\nPython"), ("tool execution: shell", "tool:\nshell"),
      ("harness: agent loop", "agent\nloop"), ("harness exit", "harness\nexit")]
NUM = []


def note(fig, groups, series, vals):
    for g, v in zip(groups, vals):
        NUM.append(dict(figure=fig, group=str(g).replace("\n", " "), series=series, value=f"{float(v):.4f}"))


rows = [r for r in csv.DictReader(open(W9 / "results.csv")) if r["ok"] == "1"]
by = {(r["uid"], r["config"]): r for r in rows}
units = sorted({r["uid"] for r in rows if r["config"] == "base"})
phase = {r["uid"]: r["phase"] for r in rows}
phases = [(p, l) for p, l in PH if any(phase[u] == p for u in units)]
G = [l for _, l in phases] + ["AVG"]
KEYS = [p for p, _ in phases] + ["AVG"]
U = {p: [u for u in units if phase[u] == p] for p, _ in phases}
U["AVG"] = units
f = lambda r, k: float(r.get(k) or 0)  # noqa: E731
ipc = lambda u, c: f(by[(u, c)], "insts") / f(by[(u, c)], "cycles")  # noqa: E731
gm = lambda xs: float(np.exp(np.mean(np.log(xs)))) if len(xs) else np.nan  # noqa: E731


def spd(p, c):
    if p == "AVG":
        return gm([spd(q, c) for q in KEYS[:-1]])
    return gm([ipc(u, c) / ipc(u, "base") for u in U[p] if (u, c) in by])


def avg(vals):
    """replace the AVG entry by the mean of the phase entries"""
    vals = list(vals)
    return vals[:-1] + [float(np.mean(vals[:-1]))]


def ssum(p, key, cfg="base"):
    return sum(f(by[(u, cfg)], key) for u in U[p] if (u, cfg) in by)


# 1. where wall time goes (native)
ws = list(csv.DictReader(open(R / "w7_task_speedup" / "wall_split.csv")))
tg = list(TASKS) + ["AVG"]
fr = {t: {k: np.mean([float(w[k]) / float(w["total"]) for w in ws if t == "AVG" or w["task"] == t])
          for k in ("model", "tool", "harness")} for t in tg}
fig, ax = plt.subplots(figsize=(6.2, 3.0))
parts = [("model inference (GPU)", S.C_NAVY, [fr[t]["model"] for t in tg]),
         ("tool execution", S.C_YEL, [fr[t]["tool"] for t in tg]), ("harness", S.C_LIME, [fr[t]["harness"] for t in tg])]
S.stacked(ax, TN + ["AVG"], parts); S.frame(ax, "SWE-Bench tasks", "Wall-clock time (%)"); S.legend(ax, 3)
for lab, _, v in parts:
    note(1, TN + ["AVG"], lab, v)
S.save(fig, W9 / "fig_01_wall_time", """Share of an agent run's wall-clock time spent in model inference, tool execution
       and the harness (6 native runs per task, exact innermost-span sweep over the harness's own spans).""")

# 2. where CPU time goes, by phase
mix = list(csv.DictReader(open(R / "w7_task_speedup" / "phase_mix.csv")))
cpi = {p: ssum(p, "cycles") / ssum(p, "insts") for p in KEYS}
CATS = [("tool: Python start-up", S.C_PINK), ("tool: Python, after start-up", S.C_ORANGE), ("tool: shell & other", S.C_YEL),
        ("environment setup", S.C_LIME), ("harness start-up", S.C_TEAL), ("harness loop & exit", S.C_NAVY)]
cyc = defaultdict(lambda: defaultdict(float))
for t in TASKS:
    m = [r for r in mix if r["task"] == t]
    st_ = sum(int(r["instrs"]) for r in m if r["phase"] == "tool execution: python start")
    for r in m:
        ph, k, n = r["phase"], r["kind"], int(r["instrs"])
        if ph == "tool execution: python start":
            continue
        if k == "harness":
            c = "harness start-up" if ph == "harness start-up" else "harness loop & exit"
            cyc[t][c] += n * cpi.get(ph, cpi["AVG"])
        elif ph == "tool execution" and k == "python":
            cyc[t]["tool: Python start-up"] += st_ * cpi["tool execution: python"]
            cyc[t]["tool: Python, after start-up"] += (n - st_) * cpi["tool execution: python"]
        elif ph == "environment setup":
            cyc[t]["environment setup"] += n * cpi["environment setup" if k == "python" else "AVG"]
        else:
            cyc[t]["tool: shell & other"] += n * cpi["tool execution: shell" if k == "shell" else "AVG"]
share = {t: {c: cyc[t][c] / sum(cyc[t].values()) for c, _ in CATS} for t in TASKS}
share["AVG"] = {c: np.mean([share[t][c] for t in TASKS]) for c, _ in CATS}
fig, ax = plt.subplots(figsize=(6.2, 3.3))
parts = [(c, col, [share[t][c] for t in tg]) for c, col in CATS]
S.stacked(ax, TN + ["AVG"], parts); S.frame(ax, "SWE-Bench tasks", "CPU cycles (%)"); S.legend(ax, 2)
for lab, _, v in parts:
    note(2, TN + ["AVG"], lab, v)
S.save(fig, W9 / "fig_02_cpu_by_phase", """Share of an agent run's CPU cycles (harness and every process it creates) by
       phase: each phase's instructions over the whole run (DR attribution, sampled windows weighted) times the base CPI
       of its simulated units. 'Start-up' is the first <=100M instructions of each tool-call Python process. Work of
       other kinds (git, sed, ...) takes the average CPI.""")

# 3. headroom per phase (Constable Fig. 7 / Hermes Fig. 4)
H = [("l1d_2x", "2× L1-D", S.C_YEL), ("perfect_l1i", "perfect L1-I", S.C_ORANGE), ("perfect_l1d", "perfect L1-D", S.C_LIME),
     ("perfect_l2", "perfect L2", S.C_TEAL), ("perfect_llc", "perfect LLC", S.C_PINK), ("perfect_all", "perfect caches", S.C_NAVY)]
CAP = 100
fig, ax = plt.subplots(figsize=(7.6, 3.3))
ser = [(lab, col, [100 * (spd(p, c) - 1) for p in KEYS]) for c, lab, col in H]
S.grouped(ax, G, [(l, c, np.minimum(v, CAP)) for l, c, v in ser], ymax=CAP * 1.15)
bw = 0.8 / len(ser)
for j, (l, c, v) in enumerate(ser):
    for i, vi in enumerate(v):
        if vi > CAP:
            ax.text(i + (j - (len(ser) - 1) / 2) * bw, CAP * 1.01, f"{vi:.0f}↑", ha="center", va="bottom",
                    fontsize=S.FS_VALUE, rotation=90)
S.frame(ax, "Program phase", "Geomean speedup (%)"); S.legend(ax, 3)
for lab, _, v in ser:
    note(3, G, lab, v)
S.save(fig, W9 / "fig_03_headroom_by_phase", """Speedup over golden_cove when one cache level (or all) never misses, or when the
       L1-D is doubled, per phase: geomean over the phase's units (2 per task; harness exit 1 per task, none in django).
       Bars above 100% are cut and labelled.""")

# 4. where loads are served (Hermes Figs. 2, 5)
LV = [("LD_SERVED_DCACHE", "L1-D", S.C_YEL), ("LD_SERVED_MLC", "L2", S.C_LIME), ("LD_SERVED_LLC", "LLC", S.C_TEAL),
      ("LD_SERVED_MEM", "DRAM", S.C_NAVY)]
tot = {p: sum(ssum(p, k) for k, _, _ in LV) for p in KEYS}
fig, ax = plt.subplots(figsize=(6.6, 3.0))
parts = [(lab, col, avg([ssum(p, k) / tot[p] for p in KEYS])) for k, lab, col in LV]
S.stacked(ax, G, parts, label_min=101); S.frame(ax, "Program phase", "Loads served by (%)"); S.legend(ax, 4)
ax.set_ylim(80, 100)
for i, p in enumerate(KEYS):
    ax.text(i, 80.6, f"{100 * (1 - parts[0][2][i]):.1f}% miss", ha="center", va="bottom", fontsize=S.FS_VALUE, rotation=90, zorder=5)
for lab, _, v in parts:
    note(4, G, lab, v)
S.save(fig, W9 / "fig_04_loads_served", """Where golden_cove serves each load, per phase (sum over units). The y-axis starts
       at 80%; the printed number is the share of loads that miss the L1-D.""")

# 5. where load latency goes (Hermes Fig. 3)
LL = [("LD_LAT_DCACHE", "L1-D", S.C_YEL), ("LD_LAT_MLC", "L2", S.C_LIME), ("LD_LAT_LLC", "LLC", S.C_TEAL),
      ("LD_LAT_MEM", "DRAM", S.C_NAVY)]
tl = {p: sum(ssum(p, k) for k, _, _ in LL) for p in KEYS}
fig, ax = plt.subplots(figsize=(6.6, 3.0))
parts = [(lab, col, avg([ssum(p, k) / tl[p] for p in KEYS])) for k, lab, col in LL]
S.stacked(ax, G, parts); S.frame(ax, "Program phase", "Total load latency (%)"); S.legend(ax, 4)
for lab, _, v in parts:
    note(5, G, lab, v)
for (ks, lab, _), (kl, _, _) in zip(LV, LL):
    note(5, G, f"avg latency cycles: {lab}", avg([ssum(p, kl) / max(ssum(p, ks), 1) for p in KEYS]))
S.save(fig, W9 / "fig_05_load_latency", """Share of the total load latency (sum of every load's issue-to-data cycles) spent on
       loads served by each level, per phase. Compare with fig_04: the few loads that miss the L1-D carry much of the
       latency.""")

# 6. MPKI per level
M = [("ICACHE_MISS_ONPATH", "L1-I", S.C_ORANGE), ("DCACHE_MISS_ONPATH", "L1-D", S.C_LIME), ("MLC_MISS_ONPATH", "L2", S.C_TEAL),
     ("L1_MISS_ONPATH", "LLC", S.C_NAVY)]
fig, ax = plt.subplots(figsize=(7.0, 3.0))
ser = [(lab, col, avg([1000 * ssum(p, k) / ssum(p, "insts") for p in KEYS])) for k, lab, col in M]
S.grouped(ax, G, ser, fmt="{:.1f}"); S.frame(ax, "Program phase", "Misses per kilo-instruction"); S.legend(ax, 4)
for lab, _, v in ser:
    note(6, G, lab, v)
S.save(fig, W9 / "fig_06_mpki", """Demand misses per kilo-instruction at each level on golden_cove, per phase (L1-D counts
       loads and stores; L2 and LLC count instruction and data).""")

# 7. golden_cove's data prefetcher (Pythia Fig. 1)
cov, unc, ovp = [], [], []
for p in KEYS:
    off = ssum(p, "L1_MISS_ONPATH", "no_dpref"); on = ssum(p, "L1_MISS_ONPATH")
    cov.append(max(off - on, 0) / off); unc.append(on / off)
    ovp.append(max(ssum(p, "L1_PREF_FILL") - ssum(p, "L1_PREF_HIT"), 0) / off)
x = np.arange(len(KEYS)); cov, unc, ovp = (np.array(avg(v)) for v in (cov, unc, ovp))
fig, ax = plt.subplots(figsize=(6.6, 3.0))
for lab, col, v, b in (("covered", S.C_LIME, cov, 0 * cov), ("uncovered", S.C_TEAL, unc, cov), ("overpredicted", S.C_ORANGE, ovp, cov + unc)):
    ax.bar(x, 100 * v, 0.62, bottom=100 * b, color=col, edgecolor="black", lw=0.5, label=lab, zorder=3)
    for xi, bb, vi in zip(x, b, v):
        if vi >= 0.07:
            ax.text(xi, 100 * (bb + vi / 2), f"{100 * vi:.0f}", ha="center", va="center", fontsize=S.FS_VALUE, zorder=4,
                    color="white" if col in S.DARK else "black")
ax.axvline(x[-1] - 0.5, color="black", lw=0.6, ls="--"); ax.set_xticks(x); ax.set_xticklabels(G, fontsize=S.FS_TICK)
ax.set_xlim(-0.5, x[-1] + 0.5); ax.set_ylim(0, 125)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
S.frame(ax, "Program phase", "LLC misses without\nthe prefetcher (%)"); S.legend(ax, 3)
for lab, v in (("covered", cov), ("uncovered", unc), ("overpredicted", ovp)):
    note(7, G, lab, v)
S.save(fig, W9 / "fig_07a_prefetcher_coverage", """golden_cove's data prefetcher (a stream prefetcher that fills the LLC; the L1-I FDIP
       stays on in both runs), as in Pythia Fig. 1a: of the LLC demand misses without it, the share it removes (covered),
       the share left (uncovered), and its prefetches never used (overpredicted, stacked on top).""")
gain = np.array([100 * (1 / spd(p, "no_dpref") - 1) for p in KEYS])
fig, ax = plt.subplots(figsize=(6.6, 2.8))
ax.bar(x, gain, 0.62, color=S.C_PINK, edgecolor="black", lw=0.5, zorder=3)
for xi, v in zip(x, gain):
    ax.text(xi, v + 0.2, f"{v:.1f}", ha="center", va="bottom", fontsize=S.FS_VALUE)
ax.axvline(x[-1] - 0.5, color="black", lw=0.6, ls="--")
ax.set_xticks(x); ax.set_xticklabels(G, fontsize=S.FS_TICK); ax.set_xlim(-0.5, x[-1] + 0.5); ax.set_ylim(0, gain.max() * 1.2)
S.frame(ax, "Program phase", "IPC gain from golden_cove's\ndata prefetcher (%)")
note(7, G, "IPC gain %", gain)
S.save(fig, W9 / "fig_07b_prefetcher_gain", """IPC gain of golden_cove's data prefetcher (on vs off; geomean over each phase's
       units), as in Pythia Fig. 1b.""")

# 8. footprint vs capacity
fp = {r["uid"]: r for r in csv.DictReader(open(W9 / "footprint.csv"))}
MB = 64 / 2 ** 20
fig, ax = plt.subplots(figsize=(7.2, 3.1))
ser = [(lab, col, [np.median([int(fp[u][k]) * MB for u in U[p] if u in fp]) for p in KEYS])
       for lab, col, k in (("instruction", S.C_ORANGE, "i_lines"), ("data, file-backed", S.C_TEAL, "d_file"),
                           ("data, private (heap, stack)", S.C_PINK, "d_private"))]
S.grouped(ax, G, ser, fmt="{:.2f}", log=True)
ax.set_ylim(0.005, 400)
for y, lab in ((48 / 1024, "L1-D 48 KB"), (1.0, "L2 1 MB"), (2.0, "LLC 2 MB")):
    ax.axhline(y, color="black", lw=0.8, ls=(0, (4, 2)), zorder=2)
    ax.text(len(G) - 0.52, y * 1.06, lab, fontsize=S.FS_VALUE, va="bottom", ha="right")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}"))
S.frame(ax, "Program phase", "Distinct lines touched (MB)"); S.legend(ax, 3)
for lab, _, v in ser:
    note(8, G, lab, v)
S.save(fig, W9 / "fig_08_footprint", """Footprint of a unit (median per phase): distinct 64-B lines its first <=100M
       instructions touch, split into instruction lines, data lines inside a mapped file, and private data lines (heap,
       stack, anonymous), against golden_cove's cache capacities (L2 and LLC as effective under its LOG2 set-count bug).
       Log scale.""")

# 9. cold misses
cold_d, cold_2 = [], []
for p in KEYS:
    us = [u for u in U[p] if u in fp]
    cold_d.append(min(1, sum(int(fp[u]["d_file"]) + int(fp[u]["d_private"]) for u in us) / max(sum(f(by[(u, "base")], "DCACHE_MISS_ONPATH") for u in us), 1)))
    cold_2.append(min(1, sum(int(fp[u]["lines"]) for u in us) / max(sum(f(by[(u, "base")], "MLC_MISS_ONPATH") for u in us), 1)))
fig, ax = plt.subplots(figsize=(6.6, 3.0))
ser = [("L1-D misses", S.C_LIME, avg([100 * v for v in cold_d])), ("L2 misses", S.C_TEAL, avg([100 * v for v in cold_2]))]
S.grouped(ax, G, ser, fmt="{:.0f}", label_all=True, ymax=118)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%" if y <= 100 else ""))
S.frame(ax, "Program phase", "First-touch (cold) misses (%)"); S.legend(ax, 2)
for lab, _, v in ser:
    note(9, G, lab, v)
S.save(fig, W9 / "fig_09_cold_misses", """Upper bound on the share of misses that are a line's first touch in the unit: distinct
       lines / misses at that level (a line can miss once cold and again later, so the true cold share is at most this).""")

# 10. repetition across start-ups (Constable Fig. 3a)
w8fp = {r["uid"]: r for r in csv.DictReader(open(R / "w8_headroom" / "footprint.csv"))}
w8rb = {r["uid"]: r for r in csv.DictReader(open(R / "w8_headroom" / "rebase.csv"))}
w8r = {(r["uid"], r["config"]): r for r in csv.DictReader(open(R / "w8_headroom" / "results.csv")) if r["ok"] == "1"}
w8task = {k[0]: r["task"] for k, r in w8r.items()}


def w8sum(t, fn):
    return sum(fn(u) for u in w8rb if t == "AVG" or w8task.get(u) == t)


rep = defaultdict(list)
for t in tg:
    rep["lines"].append(w8sum(t, lambda u: float(w8rb[u]["own_lines_predicted"]) * int(w8rb[u]["own_lines"])) /
                        w8sum(t, lambda u: int(w8rb[u]["own_lines"])))
    for k, key in (("i", "ICACHE_MISS_ONPATH"), ("d", "DCACHE_MISS_ONPATH")):
        rep[k].append(w8sum(t, lambda u: f(w8r[(u, "base")], key) - f(w8r[(u, "ideal_l1_prev")], key)) /
                      w8sum(t, lambda u: f(w8r[(u, "base")], key)))
fig, ax = plt.subplots(figsize=(6.6, 3.0))
ser = [("lines touched", S.C_YEL, [100 * v for v in rep["lines"]]), ("L1-I misses", S.C_ORANGE, [100 * v for v in rep["i"]]),
       ("L1-D misses", S.C_LIME, [100 * v for v in rep["d"]])]
S.grouped(ax, TN + ["AVG"], ser, fmt="{:.0f}", ymax=118)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%" if y <= 100 else ""))
S.frame(ax, "SWE-Bench tasks", "Predictable from the previous\nstart-up of the script (%)"); S.legend(ax, 3)
for lab, _, v in ser:
    note(10, TN + ["AVG"], lab, v)
S.save(fig, W9 / "fig_10_repetition", """For tool-call Python processes (5 per task, W8): the share of a process's distinct lines,
       and of its golden_cove L1-I and L1-D misses, that fall on lines the previous process of the same script touched at
       the same library-relative address (after rebasing for ASLR).""")

# 11. what kind of lines (Constable Fig. 3b)
fig, ax = plt.subplots(figsize=(6.2, 3.0))
tot8 = {t: sum(int(w8fp[u]["lines"]) for u in w8fp if t == "AVG" or w8task.get(u) == t) for t in tg}
parts = [(lab, col, [sum(int(w8fp[u][k]) for u in w8fp if t == "AVG" or w8task.get(u) == t) / tot8[t] for t in tg])
         for lab, col, k in (("instruction", S.C_ORANGE, "i_lines"), ("data, file-backed", S.C_TEAL, "d_file"),
                             ("data, private (heap, stack)", S.C_PINK, "d_private"))]
S.stacked(ax, TN + ["AVG"], parts); S.frame(ax, "SWE-Bench tasks", "Lines a start-up touches (%)"); S.legend(ax, 3)
for lab, _, v in parts:
    note(11, TN + ["AVG"], lab, v)
S.save(fig, W9 / "fig_11_line_kinds", """What a tool-call Python process's footprint is made of (5 processes per task):
       instruction lines, data lines inside a mapped file (library data, mapped files), and private data lines (heap,
       stack, anonymous memory). Only the first two sit at the same place, relative to their file, in every process.""")

# 12. distance between start-ups of the same script (Constable Fig. 3c), native
B = [(0, 0.5, "< 0.5 s"), (0.5, 2, "0.5-2 s"), (2, 10, "2-10 s"), (10, 1e9, "≥ 10 s")]
gaps = defaultdict(list)
for t in TASKS:
    for pc in sorted((R / "w0_benchmark" / "native" / t).glob("run*/procs.csv")):
        ps = sorted((float(r["t_python_exec"]), r["python_script"]) for r in csv.DictReader(open(pc))
                    if r["python_script"] and r["call"] and r["t_python_exec"])
        last = {}
        for tt, s in ps:
            if s in last:
                gaps[t].append(tt - last[s]); gaps["AVG"].append(tt - last[s])
            last[s] = tt
fig, ax = plt.subplots(figsize=(6.2, 3.0))
parts = [(lab, col, [np.mean([(lo <= g < hi) for g in gaps[t]]) for t in tg])
         for (lo, hi, lab), col in zip(B, [S.C_YEL, S.C_LIME, S.C_TEAL, S.C_NAVY])]
S.stacked(ax, TN + ["AVG"], parts); S.frame(ax, "SWE-Bench tasks", "Start-ups (%)"); S.legend(ax, 4)
for lab, _, v in parts:
    note(12, TN + ["AVG"], lab, v)
note(12, TN + ["AVG"], "n gaps", [len(gaps[t]) for t in tg])
note(12, TN + ["AVG"], "median gap s", [np.median(gaps[t]) for t in tg])
S.save(fig, W9 / "fig_12_restart_distance", """Time from one start-up of a tool-call Python script to the next start-up of the same
       script (native runs, 6 per task, exec to exec). Anything that kept the previous start-up's lines would have to keep
       them this long, while the model runs in between.""")

# 13. per unit, sorted (Athena Fig. 1)
L = [("perfect_all", "perfect caches", S.C_NAVY, "s"), ("perfect_l1d", "perfect L1-D", S.C_LIME, "o"),
     ("l1d_2x", "2× L1-D", S.C_ORANGE, "^")]
order = sorted(units, key=lambda u: ipc(u, "perfect_all") / ipc(u, "base"))
fig, ax = plt.subplots(figsize=(7.6, 3.0))
xi = np.arange(1, len(order) + 1)
for c, lab, col, m in L:
    ax.plot(xi, [100 * (ipc(u, c) / ipc(u, "base") - 1) for u in order], color=col, marker=m, ms=3.5, lw=1.0, label=lab,
            markeredgecolor="black", markeredgewidth=0.4, zorder=3)
ax.set_yscale("symlog", linthresh=10)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
ax.set_xlim(0, len(order) + 1)
S.frame(ax, f"All {len(order)} units, every phase, sorted by perfect-cache speedup", "Speedup (%)"); S.legend(ax, 3)
for c, lab, _, _ in L:
    for u in order:
        NUM.append(dict(figure=13, group=u, series=lab, value=f"{ipc(u, c) / ipc(u, 'base'):.4f}"))
S.save(fig, W9 / "fig_13_per_unit", """Every simulated unit, all phases, sorted by its perfect-cache speedup (y-axis linear up
       to 10%, logarithmic above).""")

# 14. start-up ideal ladder (Constable Fig. 7), W8
w8s_ = {r["task"]: r for r in csv.DictReader(open(R / "w8_headroom" / "summary.csv"))}
LAD = [("l1d_2x", "2× L1-D", S.C_YEL), ("install_prev", "prefetch into L2+LLC at the model call", S.C_ORANGE),
       ("ideal_l1i_prev", "ideal L1-I start-up prefetch", S.C_LIME), ("ideal_l1d_prev", "ideal L1-D start-up prefetch", S.C_TEAL),
       ("ideal_l1_prev", "ideal L1-I + L1-D start-up prefetch", S.C_PINK), ("ideal_l1_self", "perfect L1 (oracle)", S.C_NAVY)]
tg8 = list(TASKS) + ["GEOMEAN"]
fig, ax = plt.subplots(figsize=(7.6, 3.4))
ser = [(lab, col, [100 * (float(w8s_[t][c]) - 1) for t in tg8]) for c, lab, col in LAD]
S.grouped(ax, TN + ["GEOMEAN"], ser); S.frame(ax, "SWE-Bench tasks", "Geomean speedup (%)"); S.legend(ax, 2)
for lab, _, v in ser:
    note(14, TN + ["GEOMEAN"], lab, v)
S.save(fig, W9 / "fig_14_startup_ladder", """Tool-call Python processes (5 per task, W8): the ladder of ideal start-up prefetchers
       fed with the previous start-up's lines, against brute force (2× L1-D) and a perfect L1.""")

# 15. worth to a whole task
l1 = list(csv.DictReader(open(R / "w7_task_speedup" / "startup_l1.csv")))
T15 = [("ideal_l1_prev", "ideal L1-I + L1-D start-up prefetch", S.C_PINK), ("perfect_l1d", "perfect L1-D in start-up", S.C_LIME),
       ("ideal_l1_self", "perfect L1 in start-up", S.C_NAVY)]
fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.0), gridspec_kw=dict(wspace=0.3))
for ax, key, yl in ((axes[0], "cpu_speedup", "Task CPU-time speedup (%)"), (axes[1], "wall_speedup_upper", "Task wall-clock speedup (%)")):
    ser = []
    for c, lab, col in T15:
        v = [100 * (float(next(r[key] for r in l1 if r["task"] == t and r["config"] == c)) - 1) for t in TASKS]
        ser.append((lab, col, v + [100 * (gm([1 + y / 100 for y in v]) - 1)]))
    S.grouped(ax, TN + ["AVG"], ser, fmt="{:.2f}"); S.frame(ax, None, yl)
    ax.set_xticklabels(TN + ["AVG"], fontsize=S.FS_TICK - 1, rotation=20)
    for lab, _, v in ser:
        note(15, TN + ["AVG"], f"{key}: {lab}", v)
S.legend(axes[0], 3)
axes[0].get_legend().set_bbox_to_anchor((0, 1.06, 2.3, 0.2))
S.save(fig, W9 / "fig_15_task_worth", """What speeding up only the start-up of tool-call Python processes is worth to a whole
       task. Left: CPU time of the harness and all its processes (start-up is 6.6-8.0% of it). Right: wall clock, model
       time unchanged; an upper bound (all tool and harness time treated as CPU work).""")

with open(W9 / "numbers.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["figure", "group", "series", "value"]); w.writeheader(); w.writerows(NUM)
print("wrote", len(list(W9.glob("fig_*.png"))), "figures and numbers.csv")
