#!/usr/bin/env python3
"""W2: which tool calls create a Python process, and how well it can be predicted, how early.

  w2_prediction.py <out dir> <run dir> [<run dir> ...]

Each run dir holds calls.csv from native_summary.py. A tool call "creates Python" if at least one
process forked inside it exec'd a Python interpreter (perf exec events, command lines from proclog).

Prediction point: the end of the step's response.parse, when the action string is known and before
tool.exec starts. Predictors (fixed before looking at results):
  P0  always "creates Python"
  P1  rule on the call's type (first command word; editor subcommand): predict yes iff at least half
      of the training calls of that type created Python. Trained leave-one-task-out: the rule for a
      task's runs is learned only from the other tasks' runs. Unseen type -> no.
  P2  the previous tool call of the same kind (previous action for an action, previous state
      probe for a state probe) in the same run created Python
  P3  P1 or P2
Scopes: all tool calls; actions only (the state probe after every action always runs python3).

Outputs: tool_taxonomy.csv, type_summary.csv, per_run_metrics.csv, lead.csv, which_script.csv,
fig_tool_types.png, fig_python_per_step.png, fig_accuracy_cdf.png (+ precision/recall variants),
fig_leadtime_cdf.png, each with a .txt caption.
"""
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
from native import tool_type  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

PRED = ("P0", "P1", "P2", "P3")
PNAME = {"P0": "P0: always yes", "P1": "P1: rule on call type (leave-one-task-out)",
         "P2": "P2: previous call of the same kind created Python", "P3": "P3: P1 or P2"}
PCOL = {"P0": "#9ecae1", "P1": st.COLD, "P2": st.WARM, "P3": "#2ca25f"}


def caption(path, text):
    Path(str(path) + ".txt").write_text(text.strip() + "\n")


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    runs = [Path(p) for p in sys.argv[2:]]
    calls = []
    for r in runs:
        task, rid = r.parent.name, r.name
        for c in csv.DictReader(open(r / "calls.csv")):
            if c["kind"] not in ("action", "state"):
                continue
            c.update(task=task, run=f"{task}/{rid}", y=int(int(c["n_python"]) > 0))
            if c["kind"] == "action":
                c["type"] = tool_type(c["command"])      # the parser in lib/native.py is the reference
            calls.append(c)
    calls.sort(key=lambda c: (c["run"], float(c["t0"])))
    with open(out / "tool_taxonomy.csv", "w", newline="") as fh:
        keys = ["run", "task", "kind", "step", "type", "command", "n_procs", "n_python", "python_scripts", "y",
                "instrs_procs", "instrs_python"]
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(calls)
    # types
    ty = defaultdict(lambda: [0, 0])
    for c in calls:
        ty[c["type"]][0] += 1; ty[c["type"]][1] += c["y"]
    trows = sorted(({"type": k, "calls": v[0], "create_python": v[1], "share": v[1] / v[0]} for k, v in ty.items()),
                   key=lambda r: -r["calls"])
    with open(out / "type_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trows[0])); w.writeheader(); w.writerows(trows)
    # predictors
    tasks = sorted({c["task"] for c in calls})
    rule = {}
    for t in tasks:
        tr = defaultdict(lambda: [0, 0])
        for c in calls:
            if c["task"] != t:
                tr[c["type"]][0] += 1; tr[c["type"]][1] += c["y"]
        rule[t] = {k for k, (n, y) in tr.items() if y >= n / 2}
    prev = {}
    for c in calls:
        p2 = prev.get((c["run"], c["kind"]), 0)
        c["P0"] = 1; c["P1"] = int(c["type"] in rule[c["task"]]); c["P2"] = p2; c["P3"] = int(c["P1"] or c["P2"])
        prev[(c["run"], c["kind"])] = c["y"]
    mrows = []
    for scope, sel in (("all calls", lambda c: True), ("actions only", lambda c: c["kind"] == "action")):
        byrun = defaultdict(list)
        for c in calls:
            if sel(c):
                byrun[c["run"]].append(c)
        for run, cs in byrun.items():
            y = np.array([c["y"] for c in cs])
            for p in PRED:
                yh = np.array([c[p] for c in cs])
                tp = int(((yh == 1) & (y == 1)).sum()); fp = int(((yh == 1) & (y == 0)).sum())
                fn = int(((yh == 0) & (y == 1)).sum()); tn = int(((yh == 0) & (y == 0)).sum())
                mrows.append(dict(scope=scope, run=run, predictor=p, n=len(cs), tp=tp, fp=fp, fn=fn, tn=tn,
                                  accuracy=(tp + tn) / len(cs), precision=tp / (tp + fp) if tp + fp else float("nan"),
                                  recall=tp / (tp + fn) if tp + fn else float("nan")))
    with open(out / "per_run_metrics.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mrows[0])); w.writeheader(); w.writerows(mrows)
    # which script
    wrows = Counter((c["type"], c["python_scripts"] or "(none)") for c in calls)
    with open(out / "which_script.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["type", "python_scripts", "calls"])
        for (t, s), n in wrows.most_common():
            w.writerow([t, s, n])
    # lead time
    lrows = [dict(run=c["run"], kind=c["kind"], type=c["type"], lead_s=float(c["lead_s"]),
                  lead_instrs_tree=int(float(c["lead_instrs_tree"])))
             for c in calls if c["y"] and c.get("lead_s") not in (None, "")]
    with open(out / "lead.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "kind", "type", "lead_s", "lead_instrs_tree"]); w.writeheader(); w.writerows(lrows)

    nruns = len({c["run"] for c in calls})
    # --- figures
    top = [r for r in trows if r["calls"] >= 5][:14]
    fig, ax = plt.subplots(figsize=(6.6, 0.26 * len(top) + 0.7))
    y = np.arange(len(top))[::-1]
    ax.barh(y, [r["calls"] for r in top], color="#d9d9d9", edgecolor=st.INK, lw=0.4, height=0.7)
    ax.barh(y, [r["create_python"] for r in top], color=st.COLD, edgecolor=st.INK, lw=0.4, height=0.7)
    for yy, r in zip(y, top):
        ax.text(r["calls"] * 1.01 + 1, yy, f"{r['create_python']}/{r['calls']} create Python ({100 * r['share']:.0f}%)",
                va="center", fontsize=6.3)
    ax.set_yticks(y); ax.set_yticklabels([r["type"] for r in top], fontsize=6.8); ax.tick_params(axis="y", length=0)
    ax.set_xlabel(f"Tool calls ({nruns} native runs, {len(tasks)} tasks); blue = the call created a Python process")
    ax.set_xlim(0, max(r["calls"] for r in top) * 1.45)
    st.save(fig, out / "fig_tool_types")
    caption(out / "fig_tool_types.png", f"Tool calls by type over {nruns} native SWE-agent runs of {len(tasks)} SWE-bench tasks. "
            "Grey: all calls of the type; blue: calls during which a Python interpreter was exec'd (perf exec events). "
            "'state: _state_anthropic' is SWE-agent's state probe after every action.")
    # python creations per step
    per = defaultdict(int)
    steps = {(c["run"], c["step"]) for c in calls if c["kind"] == "action"}
    for c in calls:
        if c["kind"] in ("action", "state"):
            per[(c["run"], c["step"])] += int(c["n_python"])
    v = np.array([per[s] for s in steps])
    fig, ax = plt.subplots(figsize=(4.6, 2.2))
    ks = np.arange(0, v.max() + 1)
    h = np.array([(v == k).sum() for k in ks])
    ax.bar(ks, 100 * h / len(v), color=st.COLD, edgecolor=st.INK, lw=0.4)
    for k, hh in zip(ks, h):
        if hh:
            ax.text(k, 100 * hh / len(v) + 1, f"{100 * hh / len(v):.0f}%", ha="center", fontsize=6.3)
    ax.set_xlabel("Python processes created per agent step (action + state probe)")
    ax.set_ylabel("Agent steps (%)"); ax.set_xticks(ks)
    st.save(fig, out / "fig_python_per_step")
    caption(out / "fig_python_per_step.png", f"Distribution over {len(v)} agent steps ({nruns} runs) of the number of Python "
            f"processes created in the step's tool calls. Median {np.median(v):.0f}, mean {v.mean():.2f}.")
    # accuracy/precision/recall CDFs
    for metric in ("accuracy", "precision", "recall"):
        for scope in ("all calls", "actions only"):
            fig, ax = plt.subplots(figsize=(4.6, 2.4))
            for p in PRED:
                vals = np.sort([m[metric] for m in mrows if m["scope"] == scope and m["predictor"] == p and m[metric] == m[metric]])
                if not len(vals):
                    continue
                ax.step(np.r_[vals[0], vals], np.r_[0, np.arange(1, len(vals) + 1) / len(vals)], where="post",
                        color=PCOL[p], lw=1.1)
                ax.text(vals[len(vals) // 2], 0.5 + 0.1 * PRED.index(p) - 0.15, f"{p} (median {np.median(vals):.2f})",
                        color=PCOL[p], fontsize=6.3)
            ax.set_xlim(-0.02, 1.02); ax.set_ylim(0, 1.02)
            ax.set_xlabel(f"Per-run prediction {metric} ({scope})"); ax.set_ylabel("Fraction of runs (CDF)")
            name = f"fig_{metric}_cdf" + ("" if scope == "all calls" else "_actions")
            st.save(fig, out / name)
            caption(out / f"{name}.png", f"CDF over {nruns} native runs of the per-run {metric} of predicting, at the end of "
                    f"response.parse, whether a tool call will create a Python process ({scope}). " +
                    "; ".join(f"{p}: {PNAME[p]}" for p in PRED) + ".")
    # lead time CDF
    if lrows:
        fig, ax = plt.subplots(figsize=(4.6, 2.4))
        for kind, col in (("action", st.COLD), ("state", st.WARM)):
            vals = np.sort([1e3 * r["lead_s"] for r in lrows if r["kind"] == kind])
            if len(vals):
                ax.step(vals, np.arange(1, len(vals) + 1) / len(vals), where="post", color=col, lw=1.1)
                ax.text(np.median(vals), 0.52 if kind == "action" else 0.3, f"{kind} calls (median {np.median(vals):.1f} ms, n={len(vals)})",
                        color=col, fontsize=6.3)
        ax.set_xscale("log"); ax.set_ylim(0, 1.02)
        ax.set_xlabel("Lead time: prediction point to the Python exec (ms)"); ax.set_ylabel("Fraction of Python-creating calls (CDF)")
        st.save(fig, out / "fig_leadtime_cdf")
        caption(out / "fig_leadtime_cdf.png", "CDF of the time from the prediction point (end of response.parse) to the first "
                "Python exec of a tool call, native runs. It bounds how early a prefetch for the process's start-up can be issued.")

    # most invoked tools, as in "Agentic coding in the wild" (arXiv 2608.00101) Fig. 21
    def by_name(c):
        t = c["type"]
        return "str_replace_editor" if t.startswith("str_replace_editor") else ("submit" if t == "submit" else "bash")
    acts = [c for c in calls if c["kind"] == "action"]
    for suffix, key, note in (("", lambda c: c["type"], "Tools are SWE-agent's editor subcommands and, for the bash tool, the "
                               "command's first word (after a leading 'cd <dir> &&')."),
                              ("_by_name", by_name, "Tools are SWE-agent's registered tool names, the paper's granularity.")):
        cnt = Counter(key(c) for c in acts)
        top = cnt.most_common(15)
        rest = sum(cnt.values()) - sum(v for _, v in top)
        names = [k for k, _ in top] + (["Others"] if rest else [])
        vals = [100 * v / len(acts) for _, v in top] + ([100 * rest / len(acts)] if rest else [])
        fig, ax = plt.subplots(figsize=(6.6, 2.8))
        x = np.arange(len(names))
        cols = [st.COLD] * len(top) + (["#9e9e9e"] if rest else [])
        ax.bar(x, vals, color=cols, edgecolor=st.INK, lw=0.4, width=0.7)
        for xi, v in zip(x, vals):
            ax.text(xi, v + max(vals) * 0.015, f"{v:.1f}", ha="center", va="bottom", fontsize=6.3)
        ax.set_xticks(x); ax.set_xticklabels(names, rotation=45, ha="right", fontsize=6.5)
        ax.set_ylabel("Invocation %"); ax.set_ylim(0, max(vals) * 1.15)
        ax.set_xlabel(f"Tool ({len(acts)} model-invoked tool calls, {nruns} native runs, {len(tasks)} tasks)")
        st.save(fig, out / f"fig_most_invoked_tools{suffix}")
        caption(out / f"fig_most_invoked_tools{suffix}.png", "Most invoked tools and their frequency, drawn like Fig. 21 of "
                "'Agentic Coding in the Wild' (Liu et al., arXiv 2608.00101): share of all model-invoked tool calls per tool, "
                "sorted, long tail as 'Others'. SWE-agent's automatic state probe and setup commands are excluded. " + note)
    print(f"{nruns} runs, {len(calls)} calls, {sum(c['y'] for c in calls)} create Python", flush=True)


if __name__ == "__main__":
    main()
