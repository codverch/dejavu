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
START = "tool execution: python start"
SCEN = [("perfect_all", "perfect caches during start-up (bound)", "#d9d9d9"),
        ("instant_both", "ideal start-up prefetch, issued at the model call", "#1f4e79")]
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

mix, start = defaultdict(list), {}
for r in csv.DictReader(open(W7 / "phase_mix.csv")):
    if r["phase"] == START:
        start[r["task"]] = int(r["instrs"])
    else:
        mix[r["task"]].append((r["phase"], r["kind"], int(r["instrs"])))

# start-up of tool-call Python processes: django from W3/W4 (the 45 creation regions), the other
# tasks from W6's two tool-execution Python units (their first 100M instructions)
def pooled(rows_, key):
    i = sum(int(r["insts"]) for r in rows_ if key(r)); c = sum(int(r["cycles"]) for r in rows_ if key(r))
    return i / c
w3 = [r for r in csv.DictReader(open(R / "w3_baseline" / "results.csv")) if r["ok"] == "1" and r["kind"] == "python"]
w4 = [r for r in csv.DictReader(open(R / "w4_ideal_prefetch" / "results.csv")) if r["ok"] == "1" and r["source"] == "self"]
b3 = pooled(w3, lambda r: r["config"] == "base")
START_SRC = {"django__django-13809": dict(cpi=1 / b3, instant_both=pooled(w4, lambda r: r["config"] == "instant_both") / b3,
                                          perfect_all=pooled(w3, lambda r: r["config"] == "perfect_all") / b3)}
TP = "tool execution: python"
OTHER_START = dict(cpi=cpi[TP], instant_both=spd[(TP, "instant_both")], perfect_all=spd[(TP, "perfect_all")])
# W8: 5 tool-call Python processes per task, L1 scenarios
L1_SCEN = ["ideal_l1_prev", "perfect_l1d", "ideal_l1_self"]
w8 = [r for r in csv.DictReader(open(R / "w8_headroom" / "results.csv")) if r["ok"] == "1"]
W8_SRC = {}
for t_ in {r["task"] for r in w8}:
    b8 = pooled(w8, lambda r: r["task"] == t_ and r["config"] == "base")
    W8_SRC[t_] = dict(cpi=1 / b8, **{c: pooled(w8, lambda r: r["task"] == t_ and r["config"] == c) / b8 for c in L1_SCEN})

rows, walls, srows, l1rows = [], [], [], []
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
    common = dict(model_frac=f"{fr['model'].mean():.3f}", tool_frac=f"{fr['tool'].mean():.3f}",
                  harness_frac=f"{fr['harness'].mean():.3f}", runs=len(ws))

    def speedups(sp):
        """sp(phase, kind, up, n) -> [(cycles, speedup)] pieces; -> (cpu, tool side, harness side, wall array)"""
        base = defaultdict(float); new = defaultdict(float)
        for ph, kind, n in mix[task]:
            g, up = unit_phase(ph, kind)
            for c, s_ in sp(ph, kind, up, n, n * (cpi[up] if up else gcpi[g])):
                base[g] += c; new[g] += c / s_
        s_tool, s_h = base["tool"] / new["tool"], base["harness"] / new["harness"]
        wall = 1 / (fr["model"] + fr["tool"] / s_tool + fr["harness"] / s_h)
        return sum(base.values()) / sum(new.values()), s_tool, s_h, wall, base

    # every phase sped up by its W6 units
    for cfg, _ in CFGS:
        s_cpu, s_tool, s_h, wall, _ = speedups(lambda ph, kind, up, n, c: [(c, spd[(up, cfg)] if up else 1.0)])
        rows.append(dict(task=task, config=cfg, cpu_speedup=f"{s_cpu:.4f}", tool_side=f"{s_tool:.4f}",
                         harness_side=f"{s_h:.4f}", wall_speedup_upper=f"{wall.mean():.4f}",
                         wall_min=f"{wall.min():.4f}", wall_max=f"{wall.max():.4f}", **common,
                         simulated_instr_frac=f"{sum(sim_ins.values()) / tot_ins:.3f}"))
    # only the start-up of tool-call Python processes sped up; everything else as on golden_cove
    for src, cfgs, out in ((START_SRC.get(task, OTHER_START), [c for c, _, _ in SCEN], srows),
                           (W8_SRC[task], L1_SCEN, l1rows)):
      for cfg in cfgs:
        def sp(ph, kind, up, n, c, src=src, cfg=cfg):
            if up != TP:
                return [(c, 1.0)]
            n0 = min(start[task], n)
            return [(n0 * src["cpi"], src[cfg]), (c * (n - n0) / n, 1.0)]
        s_cpu, s_tool, s_h, wall, base = speedups(sp)
        out.append(dict(task=task, config=cfg, startup_speedup=f"{src[cfg]:.4f}", cpu_speedup=f"{s_cpu:.4f}",
                        wall_speedup_upper=f"{wall.mean():.4f}", wall_min=f"{wall.min():.4f}", wall_max=f"{wall.max():.4f}",
                        startup_instr_frac=f"{start[task] / tot_ins:.4f}",
                        startup_cycle_frac=f"{start[task] * src['cpi'] / sum(base.values()):.4f}", **common))

for name, data in (("task_speedup.csv", rows), ("startup_prefetch.csv", srows), ("startup_l1.csv", l1rows),
                   ("wall_split.csv", walls)):
    with open(W7 / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

tasks = list(mix)
pct = lambda v: 100 * (v - 1)  # noqa: E731


def panels(data, cfgs, name, ylabs, caption):
    """two panels of percentage speedup, one group of bars per task"""
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.5), gridspec_kw=dict(wspace=0.3))
    bw = 0.8 / len(cfgs)
    top = max(pct(float(r["cpu_speedup"])) for r in data)
    for ax, key, ylab in zip(axes, ("cpu_speedup", "wall_speedup_upper"), ylabs):
        x = np.arange(len(tasks))
        for j, (cfg, lab, col) in enumerate(cfgs):
            v = np.array([pct(float(next(r[key] for r in data if r["task"] == t and r["config"] == cfg))) for t in tasks])
            xs = x + (j - (len(cfgs) - 1) / 2) * bw
            ax.bar(xs, v, bw, color=col, edgecolor=st.INK, lw=0.4, label=lab)
            for xi, vi in zip(xs, v):
                ax.text(xi, vi + top * 0.012, (f"{vi:.2f}%" if vi < 1 else f"{vi:.1f}%"), ha="center", va="bottom", fontsize=5, rotation=90)
        ax.set_xticks(x); ax.set_xticklabels([SHORT(t) for t in tasks], fontsize=6, rotation=20)
        ax.set_ylabel(ylab); ax.set_ylim(0, top * 1.15)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:g}%"))
    axes[0].legend(frameon=False, fontsize=6.5, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=len(cfgs),
                   handlelength=1.2, columnspacing=1.2)
    st.save(fig, W7 / name)
    (W7 / f"{name}.png.txt").write_text(" ".join(caption.split()) + "\n")


panels(rows, [(c, l, k) for (c, l), k in zip(CFGS, ["#d9d9d9", st.COLD, st.WARM])], "fig_task_speedup",
       ("CPU-time speedup\nover golden_cove", "Task wall-clock speedup\nover golden_cove (upper bound)"),
       """Whole-task speedup of five SWE-bench tasks with every phase prefetched. Left: user-mode CPU time of the
       harness and every process it creates, from each task's DR instruction mix and W6's per-phase simulated
       speedups. Right: task wall clock, model inference unchanged, tool and harness time divided by their CPU
       speedup (an upper bound); mean over 6 native runs.""")
panels(srows, SCEN, "fig_startup_prefetch",
       ("CPU-time speedup\nover golden_cove", "Task wall-clock speedup\nover golden_cove (upper bound)"),
       """Whole-task speedup when only the start-up of the Python processes that tool calls create is prefetched:
       the start-up is predicted perfectly, and every cache line it will touch is put in the L2 and the LLC while
       the harness waits for the model (no bandwidth cost; lines needed soonest first, until each set is full).
       Grey: the same start-ups with perfect caches, the most any start-up prefetcher can give. Left: CPU time of
       the harness and its processes. Right: task wall clock, model inference unchanged (an upper bound); mean
       over 6 native runs. django: W4's 45 creation regions; other tasks: W6's tool-execution Python units.""")
print("wrote", W7 / "fig_task_speedup.png", W7 / "fig_startup_prefetch.png")
