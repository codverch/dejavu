#!/usr/bin/env python3
"""W7: what the per-phase speedups of W6 are worth to a whole SWE-bench task.

  w7_task_speedup.py <results root>

Inputs:
  w6_more_traces/results.csv      simulated speedup and base IPC of two units per phase
  w7_task_speedup/phase_mix.csv   instructions per (phase, process kind) of each whole task, from
                                  the DR runs (scripts/phase_mix.py)
  w0_benchmark/native/<task>/run*/swetrace.ndjson
                                  wall-clock time of 6 native runs per task

CPU side. A phase's base cycles are its instructions x the base CPI of its simulated units, and its
cycles under a config are those / the units' speedup (both pooled over the two units: sum of
instructions / sum of cycles). Instructions of kind "other" (git, sed, find, ...) were not
simulated: they keep speedup 1 and take the instruction-weighted base CPI of the simulated work in
the same group. The CPU speedup of a task is its base cycles / its config cycles.

Wall clock. Each native run's wall time is split by an exact sweep over its swetrace spans,
innermost span wins (as in the Q1 breakdown): model (http.roundtrip, http.read_body), tool
(tool.exec, tool.get_state), harness (the rest). Model time is the GPU and does not change. Tool
and harness time are divided by the CPU speedup of the tool-side and harness-side phases. That
assumes every second of tool and harness wall time is user-mode CPU work on the simulated core; it
is not (container exec, kernel, I/O), so the wall-clock speedup is an upper bound.

Outputs: w7_task_speedup/task_speedup.csv, wall_split.csv, fig_task_speedup.png.
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

R = Path(sys.argv[1]); W6 = R / "w6_more_traces"; W7 = R / "w7_task_speedup"
MODEL, TOOL = {"http.roundtrip", "http.read_body"}, {"tool.exec", "tool.get_state"}
CFGS = [("perfect_all", "perfect caches (bound)"), ("stream_llc_20k", "ideal prefetch, LLC"),
        ("stream_l2_20k", "ideal prefetch, L2")]
SHORT = lambda t: t.split("__")[1].rsplit("-", 1)[0] + "-" + t.rsplit("-", 1)[1]  # noqa: E731


def unit_phase(phase, kind):
    """(DR phase, kind) -> (group, W6 unit phase or None if not simulated)"""
    if kind == "harness":
        return "harness", phase
    if kind == "shell":
        return "tool", "tool execution: shell"
    if kind == "python":
        return "tool", "environment setup" if phase == "environment setup" else "tool execution: python"
    return "tool", None


def wall_split(path):
    opened, spans = {}, []
    for line in open(path):
        r = json.loads(line)
        if r["kind"] == "start":
            opened[r["span"]] = r
        elif r["kind"] == "end" and r["span"] in opened:
            s = opened.pop(r["span"]); spans.append((s["t"], r["t"], s["name"], s["span"]))
    a0, a1 = next((a, b) for a, b, n, _ in spans if n == "run.total")
    pts = sorted({x for a, b, _, _ in spans for x in (a, b) if a0 <= x <= a1} | {a0, a1})
    out = defaultdict(float)
    for x0, x1 in zip(pts, pts[1:]):
        m = (x0 + x1) / 2
        inner = max((s for s in spans if s[0] <= m <= s[1]), key=lambda s: (s[0], s[3]))[2]
        out["model" if inner in MODEL else "tool" if inner in TOOL else "harness"] += x1 - x0
    return dict(out, total=a1 - a0)


# per-phase base CPI and speedup, pooled over the phase's units
res = [r for r in csv.DictReader(open(W6 / "results.csv")) if r["ok"] == "1"]
agg = defaultdict(lambda: [0, 0])
for r in res:
    agg[(r["phase"], r["config"])][0] += int(r["insts"]); agg[(r["phase"], r["config"])][1] += int(r["cycles"])
cpi = {p: c / i for (p, cfg), (i, c) in agg.items() if cfg == "base"}
spd = {(p, cfg): (i / c) / (agg[(p, "base")][0] / agg[(p, "base")][1]) for (p, cfg), (i, c) in agg.items()}

mix = defaultdict(list)
for r in csv.DictReader(open(W7 / "phase_mix.csv")):
    mix[r["task"]].append((r["phase"], r["kind"], int(r["instrs"])))

rows, walls = [], []
for task in mix:
    runs = sorted((R / "w0_benchmark" / "native" / task).glob("run*/swetrace.ndjson"))
    ws = [wall_split(p) for p in runs]
    for p, w in zip(runs, ws):
        walls.append(dict(task=task, run=p.parent.name, **{k: round(v, 3) for k, v in w.items()}))
    fr = {k: np.array([w[k] / w["total"] for w in ws]) for k in ("model", "tool", "harness")}
    # base cycles per group; "other" work gets the group's simulated CPI
    ins = defaultdict(float); cyc = defaultdict(float); sim_ins = defaultdict(float)
    for ph, kind, n in mix[task]:
        g, up = unit_phase(ph, kind)
        if up:
            cyc[g] += n * cpi[up]; sim_ins[g] += n
        ins[g] += n
    gcpi = {g: cyc[g] / sim_ins[g] for g in cyc}
    tot_ins = sum(ins.values())
    for cfg, _ in CFGS:
        base = defaultdict(float); new = defaultdict(float)
        for ph, kind, n in mix[task]:
            g, up = unit_phase(ph, kind)
            c = n * (cpi[up] if up else gcpi[g])
            base[g] += c; new[g] += c / (spd[(up, cfg)] if up else 1.0)
        s_tool, s_h = base["tool"] / new["tool"], base["harness"] / new["harness"]
        s_cpu = sum(base.values()) / sum(new.values())
        wall = 1 / (fr["model"] + fr["tool"] / s_tool + fr["harness"] / s_h)
        rows.append(dict(task=task, config=cfg, cpu_speedup=f"{s_cpu:.4f}", tool_side=f"{s_tool:.4f}",
                         harness_side=f"{s_h:.4f}", wall_speedup_upper=f"{wall.mean():.4f}",
                         wall_min=f"{wall.min():.4f}", wall_max=f"{wall.max():.4f}",
                         model_frac=f"{fr['model'].mean():.3f}", tool_frac=f"{fr['tool'].mean():.3f}",
                         harness_frac=f"{fr['harness'].mean():.3f}", runs=len(ws),
                         simulated_instr_frac=f"{sum(sim_ins.values()) / tot_ins:.3f}"))

for name, data in (("task_speedup.csv", rows), ("wall_split.csv", walls)):
    with open(W7 / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

# figure: CPU work (left) and wall clock (right), one group of bars per task
tasks = list(mix)
cols = ["#d9d9d9", st.COLD, st.WARM]
fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.5), gridspec_kw=dict(wspace=0.28))
for ax, key, ylab in ((axes[0], "cpu_speedup", "CPU-time speedup\nover golden_cove (×)"),
                      (axes[1], "wall_speedup_upper", "Task wall-clock speedup\nover golden_cove (×, upper bound)")):
    x = np.arange(len(tasks)); bw = 0.26
    for j, (cfg, lab) in enumerate(CFGS):
        v = np.array([float(next(r[key] for r in rows if r["task"] == t and r["config"] == cfg)) for t in tasks])
        ax.bar(x + (j - 1) * bw, v - 1, bw, bottom=1, color=cols[j], edgecolor=st.INK, lw=0.4, label=lab)
        for xi, vi in zip(x + (j - 1) * bw, v):
            ax.text(xi, vi + 0.004, f"{vi:.3f}", ha="center", va="bottom", fontsize=4.6, rotation=90)
    ax.set_xticks(x); ax.set_xticklabels([SHORT(t) for t in tasks], fontsize=6, rotation=20)
    ax.set_ylabel(ylab)
top = max(float(r["cpu_speedup"]) for r in rows)
for ax in axes:
    ax.set_ylim(1.0, top * 1.06)                      # bars grow from 1.0, the golden_cove baseline
axes[0].legend(frameon=False, fontsize=6.5, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=3,
               handlelength=1.2, columnspacing=1.2)
st.save(fig, W7 / "fig_task_speedup")
(W7 / "fig_task_speedup.png.txt").write_text(
    "Whole-task speedup of five SWE-bench tasks. Left: user-mode CPU time of the harness and every process it "
    "creates, from each task's DR instruction mix and W6's per-phase simulated speedups. Right: task wall clock, "
    "model inference unchanged, tool and harness time divided by their CPU speedup (an upper bound); bars are the "
    "mean over 6 native runs.\n")
print("wrote", W7 / "fig_task_speedup.png")
