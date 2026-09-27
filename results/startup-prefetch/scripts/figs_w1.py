#!/usr/bin/env python3
"""W1 figures: what happens every time a tool call creates a Python process, and how often it is the same.

  figs_w1.py <results root>      (reads w0_benchmark/, w1_creation/, w3_baseline/; writes w1_creation/fig_*)

fig_flowchart                  the operations of one agent step's tool calls, in order, with instructions
                               (DR trace), native wall time per process, and cold cycles / L2 misses per
                               creation phase (W3 baseline, 100K-instruction resolution)
fig_identical_cdf              per consecutive pair of creations of the same script: share of the creation
                               region's positions whose 32-instruction sequence also ran in the previous one
fig_prefix_cdf                 exact common prefix length, with where the pair first differs
fig_identical_by_operation     per operation: share of creations whose instruction count equals the most
                               common count, and the coefficient of variation
fig_timeline                   the traced task: model, harness, tool lanes; every Python creation marked
                               and coloured by its identity with the previous creation of its script
fig_operation_breakdown        creation-region instructions by operation, bar chart in the form of Fig. 21
                               of 'Agentic Coding in the Wild' (the paper defines no taxonomy for the inside
                               of a tool call, so the categories are ours: lib/categories.py)
Each figure has a .txt caption next to it.
"""
import csv, json, statistics as stt, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

R = Path(sys.argv[1]); W1 = R / "w1_creation"; W0 = R / "w0_benchmark"; W3 = R / "w3_baseline"
cr = list(csv.DictReader(open(W1 / "creation.csv")))
pairs = list(csv.DictReader(open(W1 / "pairs.csv")))
shells = list(csv.DictReader(open(W1 / "shells.csv")))
SCOL = {"python3.8 _state_anthropic": st.COLD, "python3.8 str_replace_editor": st.WARM}


def cap(name, text):
    (W1 / f"{name}.png.txt").write_text(" ".join(text.split()) + "\n")


def short(s):
    return s.replace("python3.8 ", "")


# ---- identity CDF
fig, ax = plt.subplots(figsize=(4.6, 2.4))
by = defaultdict(list)
for p in pairs:
    by[p["script"]].append(100 * float(p["kgram_identity"]))
for k, (s, v) in enumerate(sorted(by.items(), key=lambda x: -len(x[1]))):
    v = np.sort(v)
    col = SCOL.get(s, "#7f7f7f")
    ax.step(np.r_[v[0], v], np.r_[0, np.arange(1, len(v) + 1) / len(v)], where="post", color=col, lw=1.1)
    ax.text(1.03, 0.95 - 0.25 * k, f"{short(s)} (n={len(v)})\nmedian {np.median(v):.3f}%, min {v.min():.3f}%",
            color=col, fontsize=6.2, ha="left", va="top", transform=ax.transAxes)   # labels beside the axes: the curves crowd 99.98
ax.set_xlabel("Creation-region positions whose 32-instruction sequence\nalso ran in the previous creation of the script (%)")
ax.set_ylabel("Fraction of pairs (CDF)"); ax.set_ylim(0, 1.02)
st.save(fig, W1 / "fig_identical_cdf")
cap("fig_identical_cdf", f"""For every Python process a tool call created in the traced django-13809 run, the share of its creation
region (exec to the first PyRun_*) whose 32-instruction sequences also appear in the previous creation of the same script,
after ASLR is removed (PC = file + link-time address). {len(pairs)} consecutive pairs.""")

# ---- prefix CDF
fig, ax = plt.subplots(figsize=(4.6, 2.2))
v = np.sort([int(p["prefix"]) / 1e3 for p in pairs])
ax.step(np.r_[v[0], v], np.r_[0, np.arange(1, len(v) + 1) / len(v)], where="post", color=st.COLD, lw=1.1)
dv = Counter(p["first_divergence"] for p in pairs).most_common(3)
ax.text(0.98, 0.35, "where the pair first differs:\n" + "\n".join(f"{f} ({n}/{len(pairs)})" for f, n in dv),
        transform=ax.transAxes, ha="right", fontsize=6.2, color=st.MUTED)
med_region = stt.median(int(p["region"]) for p in pairs) / 1e6
ax.set_xlabel(f"Instructions executed identically from exec before the first difference (thousands;\ncreation region median {med_region:.1f} M instructions)")
ax.set_ylabel("Fraction of pairs (CDF)"); ax.set_ylim(0, 1.02)
st.save(fig, W1 / "fig_prefix_cdf")
cap("fig_prefix_cdf", f"""Exact common prefix of consecutive creations of the same script: how many instructions run identically,
PC for PC, from exec before the first difference. Median {np.median(v):.1f} K of a {med_region:.1f} M-instruction region;
the rest is identical in 32-instruction sequences (fig_identical_cdf), so the difference is local, not a divergence.""")

# ---- identity per operation
OPS = [("i_loader", "loader (exec to ELF entry point)"), ("i_proc_init", "process init (_start to Py_BytesMain)"),
       ("i_rt_init", "interpreter init (to first PyRun)")]
cats = [c for c in cr[0] if c.startswith("cat_")]
st8 = [r for r in cr if r["script"] == "python3.8 _state_anthropic" and r["complete"] == "1"]
rows = []
for col, name in OPS + [(c, "  " + c[4:]) for c in cats]:
    vals = [int(r[col]) for r in st8]
    if not vals or max(vals) < 20000:
        continue
    mode, n = Counter(vals).most_common(1)[0]
    rows.append((name, 100 * n / len(vals), 100 * np.std(vals) / max(np.mean(vals), 1), np.mean(vals)))
fig, ax = plt.subplots(figsize=(5.4, 0.24 * len(rows) + 0.7))
y = np.arange(len(rows))[::-1]
ax.barh(y, [r[1] for r in rows], color=[st.COLD if not r[0].startswith("  ") else "#6baed6" for r in rows], height=0.65,
        edgecolor=st.INK, lw=0.4)
for yy, r in zip(y, rows):
    ax.text(r[1] + 1, yy, f"{r[3] / 1e6:.2f} M instr., CV {r[2]:.3f}%", va="center", fontsize=6)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=6.4); ax.tick_params(axis="y", length=0)
ax.set_xlim(0, 140); ax.set_xticks(range(0, 101, 20))
ax.set_xlabel(f"Creations with exactly the most common instruction count (%)\npython3.8 _state_anthropic, {len(st8)} creations")
st.save(fig, W1 / "fig_identical_by_operation")
cap("fig_identical_by_operation", f"""For each operation of the creation region of python3.8 _state_anthropic ({len(st8)} creations, one per
agent step): the share of creations whose instruction count in that operation equals the most common count exactly, the mean
count, and the coefficient of variation. Dark bars: phases cut at symbol boundaries; light bars: activity categories within the
region (lib/categories.py).""")

# ---- operation breakdown (Fig. 21 form)
tot = defaultdict(int)
for r in cr:
    if r["complete"] == "1":
        for c in cats:
            tot[c[4:]] += int(r[c])
T = sum(tot.values())
items = sorted(tot.items(), key=lambda x: -x[1])
top = [(k, v) for k, v in items if v / T >= 0.01]
rest = T - sum(v for _, v in top)
names = [k for k, _ in top] + (["Others"] if rest else [])
vals = [100 * v / T for _, v in top] + ([100 * rest / T] if rest else [])
fig, ax = plt.subplots(figsize=(6.6, 2.8))
x = np.arange(len(names))
ax.bar(x, vals, color=[st.CAT_COLOUR.get(n, "#9e9e9e") for n in names], edgecolor=st.INK, lw=0.4, width=0.7)
for xi, v in zip(x, vals):
    ax.text(xi, v + 0.4, f"{v:.1f}", ha="center", va="bottom", fontsize=6.3)
ax.set_xticks(x); ax.set_xticklabels(names, rotation=45, ha="right", fontsize=6.5)
ax.set_ylabel("Creation-region instructions (%)"); ax.set_ylim(0, max(vals) * 1.15)
ax.set_xlabel(f"Operation ({sum(1 for r in cr if r['complete'] == '1')} Python creations, django-13809, "
              f"{T / 1e9:.2f} B instructions)")
st.save(fig, W1 / "fig_operation_breakdown")
cap("fig_operation_breakdown", """Where the instructions of Python process creation go, drawn in the form of Fig. 21 of 'Agentic Coding in
the Wild' (sorted bars, value above each, long tail as Others). That paper records only tool names and defines no taxonomy of the
work inside a tool call, so the operation categories are this study's (lib/categories.py: function -> category rules).""")

# ---- timeline of the traced run (DR: wall time inflated)
spans = []
t0 = None; opened = {}
for l in open(W0 / "dr" / "swetrace.ndjson"):
    r = json.loads(l)
    if r["kind"] == "meta" and r["name"] == "trace.start":
        t0 = r["t0_wall"]
    elif r["kind"] == "start":
        opened[r["span"]] = r
    elif r["kind"] == "end" and r["span"] in opened:
        s = opened.pop(r["span"]); spans.append((t0 + s["t"], t0 + r["t"], s["name"]))
tot_span = [s for s in spans if s[2] == "run.total"][0]
T0 = tot_span[0]


def merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


model = merge([(a, b) for a, b, n in spans if n == "http.roundtrip"])
tools = merge([(a, b) for a, b, n in spans if n in ("tool.exec", "tool.get_state") and a >= T0])
fig, ax = plt.subplots(figsize=(7.0, 2.4))
for yy, iv, col, lab in ((2, model, st.CAT_COLOUR["Python: dict / hash / str"], "Model inference"),
                         (1, tools, "#e6ab02", "Tool execution")):
    ax.broken_barh([(a - T0, b - a) for a, b in iv], (yy - 0.35, 0.7), facecolors=col)
    ax.text(-0.01, yy, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=6.8)
ident = {p["cid"]: 100 * float(p["kgram_identity"]) for p in pairs}
cum = 0
xs, ys, cs = [], [], []
for r in sorted(cr, key=lambda r: float(r["t_start"])):
    xs.append(float(r["t_start"]) - T0); cum += int(r["region_instrs"]); ys.append(cum / 1e9)
    cs.append(ident.get(r["cid"], np.nan))
cs = np.array(cs)
first = np.isnan(cs)
ax.scatter(np.array(xs)[first], np.zeros(first.sum()), marker="|", s=90, color="#7f7f7f", lw=1.2)
sc = ax.scatter(np.array(xs)[~first], np.zeros((~first).sum()), c=cs[~first], cmap="viridis", vmin=99.8, vmax=100.0,
                marker="|", s=90, lw=1.4)
ax.text(-0.01, 0, "Python creations", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=6.8)
cb = fig.colorbar(sc, ax=ax, pad=0.01, fraction=0.03); cb.set_label("identity with previous\ncreation of the script (%)", fontsize=6.3)
cb.ax.tick_params(labelsize=6)
ax.text(0.99, 0.93, f"{len(cr)} creations, {cum / 1e9:.2f} B instructions of creation region in total "
        "(grey: first creation of its script)", transform=ax.transAxes, ha="right", fontsize=6.2, color=st.MUTED)
ax.set_yticks([]); ax.set_ylim(-0.6, 2.6); ax.spines["left"].set_visible(False)
ax.set_xlabel("Seconds since the agent session started (DynamoRIO-traced run: wall time is inflated; see native timelines)")
st.save(fig, W1 / "fig_timeline")
cap("fig_timeline", """The traced django-13809 run: model inference and tool execution over time, and every Python process a tool
call created, coloured by the identity of its creation region with the previous creation of the same script. Times are from the
DynamoRIO-traced run, which is slower than native; the order and the identity are exact.""")

# ---- flowchart
nat = defaultdict(list)
for p in sorted((W0 / "native").glob("django__django-13809/run*/procs.csv")):
    for r in csv.DictReader(open(p)):
        if r["t_fork"] and r["t_exit"] and r["call"] != "":
            nat[r["exec_chain"]].append(1e3 * (float(r["t_exit"]) - float(r["t_fork"])))
med = lambda xs: stt.median(xs) if xs else float("nan")
sh = [int(s["instrs"]) for s in shells if s["cls"] == "sh -c 'env bash -n' (tool-call wrapper)"]
bn = [int(s["instrs"]) for s in shells if s["cls"] == "bash -n"]
phase_cyc = {}
ser = sorted(W3.glob("runs/*__self_warm/series.npz")) if W3.exists() else []
bounds = {r["cid"]: r for r in st8}
agg = defaultdict(list)
for f in ser:
    cid = f.parent.name.split("__")[0]
    if cid not in bounds:
        continue
    z = np.load(f); d = z["data"]; b = int(z["pass1_end"])
    r = bounds[cid]
    e1 = int(r["i_loader"]); e2 = e1 + int(r["i_proc_init"]); e3 = e2 + int(r["i_rt_init"])
    p1 = d[d[:, 0] <= b]
    mid = p1[:, 0] - 50_000                       # each 100K interval goes to the phase holding its midpoint
    for name, lo, hi in (("loader", 0, e1), ("proc_init", e1, e2), ("rt_init", e2, e3)):
        m = (mid >= lo) & (mid < hi)
        agg[name].append((p1[m, 1].sum(), p1[m, 4].sum(), p1[m, 5].sum()))
for k, v in agg.items():
    phase_cyc[k] = tuple(np.median(np.array(v), axis=0))
boxes = [
    ("Harness sends the command to the SWE-ReX shell", None),
    (f"sh -c 'env bash -n'  (tool-call wrapper)\n{med(sh) / 1e6:.2f} M instr.   {med(nat.get('sh', [])):.1f} ms native", None),
    (f"env → bash -n  (runs the command)\n{med(bn) / 1e6:.2f} M instr.   {med(nat.get('env>bash', [])):.1f} ms native", None),
    ("exec python3 _state_anthropic  (after every action; the editor tool runs the same sequence)", None),
    ("loader", "loader: ld.so maps libraries, relocates, resolves symbols (exec to the ELF entry point)"),
    ("proc_init", "process init: _start, libc start-up, to Py_BytesMain"),
    ("rt_init", "interpreter init: codecs, types, site, unmarshal .pyc, imports"),
    (f"tool code: {med([int(r['i_work']) for r in st8]) / 1e6:.1f} M instr.", None),
    (f"teardown: {med([int(r['i_teardown']) for r in st8]) / 1e6:.1f} M instr.   whole process "
     f"{med(nat.get('_state_anthropi>python3', [])):.0f} ms native", None),
]
col_ops = {"loader": "i_loader", "proc_init": "i_proc_init", "rt_init": "i_rt_init"}
fig, ax = plt.subplots(figsize=(6.2, 6.4)); ax.axis("off")
yy = 1.0
for i, (a, b) in enumerate(boxes):
    if a in col_ops:
        n = med([int(r[col_ops[a]]) for r in st8])
        ntxt = f"{n / 1e6:.2f} M instr." if n >= 100_000 else f"{n / 1e3:.1f} K instr."
        extra = ""
        if a in phase_cyc and n >= 100_000:
            c, l2, llc = phase_cyc[a]
            extra = f"\ncold: {c / 1e6:.2f} M cycles, {l2 / 1e3:.0f} K L2 misses, {llc / 1e3:.0f} K LLC misses"
        elif a in phase_cyc:
            extra = "\ncold cycles: below the 100K-instruction resolution of the interval data"
        text = f"{b}\n{ntxt}{extra}"
        fc = "#dbe9f6"
    else:
        text, fc = a, "#f2f2f2"
    h = 0.075 if "\n" in text else 0.05
    if text.count("\n") >= 2:
        h = 0.095
    ax.add_patch(FancyBboxPatch((0.08, yy - h), 0.84, h, boxstyle="round,pad=0.006,rounding_size=0.01", fc=fc,
                                ec=st.INK, lw=0.6, transform=ax.transAxes))
    ax.text(0.5, yy - h / 2, text, ha="center", va="center", fontsize=6.6, transform=ax.transAxes, linespacing=1.15)
    if i < len(boxes) - 1:
        ax.annotate("", xy=(0.5, yy - h - 0.03), xytext=(0.5, yy - h), xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color=st.INK, lw=0.7))
    yy -= h + 0.035
ax.text(0.5, yy - 0.01, f"creation region (exec to first PyRun): median {med([int(r['region_instrs']) for r in st8]) / 1e6:.1f} M "
        f"instructions, identical to the previous step's in {stt.median(float(p['kgram_identity']) for p in pairs if p['script'].endswith('_state_anthropic')) * 100:.3f}% of 32-instruction sequences",
        ha="center", fontsize=6.3, color=st.MUTED, transform=ax.transAxes)
st.save(fig, W1 / "fig_flowchart")
cap("fig_flowchart", f"""The operations that run every agent step when SWE-agent refreshes its state: the harness writes a command,
a wrapper shell and bash start, and python3 _state_anthropic is exec'd and builds its interpreter from scratch. Instructions:
DynamoRIO trace of django-13809 ({len(st8)} creations, median). Native wall time: median fork-to-exit over 6 native runs.
Cold cycles and misses per phase: Scarab golden_cove, pass 1 of the W3 self-warm runs, summed over 100K-instruction intervals
({len(agg.get('loader', []))} creations){'' if phase_cyc else ' (not yet available: W3 has not finished)'}.""")
dot = ["digraph creation {", "  rankdir=TB; node [shape=box, style=rounded, fontname=serif];"]
for i, (a, b) in enumerate(boxes):
    dot.append(f'  n{i} [label="{(b or a).replace(chr(10), " ")}"];')
    if i:
        dot.append(f"  n{i - 1} -> n{i};")
(W1 / "fig_flowchart.dot").write_text("\n".join(dot + ["}"]) + "\n")
print("w1 figures written")
