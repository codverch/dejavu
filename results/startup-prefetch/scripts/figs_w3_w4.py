#!/usr/bin/env python3
"""W3 and W4 figures: bounds on Python process creation, and what the ideal prefetcher recovers.

  figs_w3_w4.py <results root>

Speedup = IPC(config) / IPC(base) over the same instructions (the creation region, exec to the
first PyRun_*), computed per creation and summarised as the instruction-weighted IPC ratio over all
creations of a script (sum instructions / sum cycles), with the 10th-90th percentile of per-creation
speedups as the whisker. base = PARAMS.golden_cove as shipped (stream prefetcher into the LLC, FDIP on).
Writes w3_baseline/fig_*, w4_ideal_prefetch/fig_*, *.png.txt captions and summary.csv files.
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import anish_style as st  # noqa: E402
st.use()
from anish_style import plt  # noqa: E402

R = Path(sys.argv[1]); W3 = R / "w3_baseline"; W4 = R / "w4_ideal_prefetch"
SHORT = {"python3.8 _state_anthropic": "_state_anthropic", "python3.8 str_replace_editor": "str_replace_editor"}


def cap(path, text):
    Path(str(path) + ".txt").write_text(" ".join(text.split()) + "\n")


def load(path):
    return [r for r in csv.DictReader(open(path)) if r["ok"] == "1"] if path.exists() else []


def agg(rows, base, cfg_key=lambda r: r["config"]):
    """{(script, cfg): (ipc ratio of sums, p10, p90, n)} relative to base {cid: row}"""
    by = defaultdict(list)
    for r in rows:
        b = base.get(r["cid"])
        if not b or not r["cycles"]:
            continue
        for s in (r["script"], "all Python creations"):
            by[(s, cfg_key(r))].append((int(r["insts"]), int(r["cycles"]), int(b["insts"]), int(b["cycles"])))
    out = {}
    for k, v in by.items():
        a = np.array(v, float)
        ratio = (a[:, 0].sum() / a[:, 1].sum()) / (a[:, 2].sum() / a[:, 3].sum())
        per = (a[:, 0] / a[:, 1]) / (a[:, 2] / a[:, 3])
        out[k] = (ratio, np.percentile(per, 10), np.percentile(per, 90), len(v))
    return out


def bars(ax, labels, vals, lo, hi, cols):
    x = np.arange(len(labels))
    ax.bar(x, vals, color=cols, edgecolor=st.INK, lw=0.4, width=0.68)
    ax.errorbar(x, vals, yerr=[np.array(vals) - lo, np.array(hi) - vals], fmt="none", ecolor=st.INK, lw=0.6, capsize=1.5)
    for xi, v, h in zip(x, vals, hi):
        ax.text(xi, max(v, h) + 0.02, f"{v:.2f}×", ha="center", va="bottom", fontsize=6.2)
    ax.axhline(1.0, color=st.INK, lw=0.6, ls=(0, (3, 2)))
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=6.5)


w3 = load(W3 / "results.csv")
py = [r for r in w3 if r["kind"] == "python"]
base = {r["cid"]: r for r in py if r["config"] == "base"}
scripts = [s for s in SHORT if any(r["script"] == s for r in py)] + ["all Python creations"]
summ = []
if py:
    a3 = agg([r for r in py if r["config"] != "base" and not r["config"].startswith("pow2")], base)
    cfgs = [("self_warm", "self-warm\n(back to back)"), ("perfect_l1i", "perfect\nL1-I"), ("perfect_l1d", "perfect\nL1-D"),
            ("perfect_l2", "perfect\nL2"), ("perfect_llc", "perfect\nLLC"), ("perfect_all", "perfect\nall levels")]
    for s in scripts:
        fig, ax = plt.subplots(figsize=(5.2, 2.5))
        ks = [(c, l) for c, l in cfgs if (s, c) in a3]
        v = [a3[(s, c)][0] for c, _ in ks]
        bars(ax, [l for _, l in ks], v, [a3[(s, c)][1] for c, _ in ks], [a3[(s, c)][2] for c, _ in ks],
             [st.WARM if c == "self_warm" else st.COLD for c, _ in ks])
        n = a3[(s, "perfect_all")][3]
        bi = np.array([(int(base[c]["insts"]), int(base[c]["cycles"])) for c in base if s == "all Python creations" or base[c]["script"] == s])
        ax.set_ylabel("IPC speedup over golden_cove (×)"); ax.set_ylim(0, max(v) * 1.3)
        ax.set_xlabel(f"{SHORT.get(s, s)}: creation region (exec to first PyRun); {n} creations; "
                      f"baseline IPC {bi[:, 0].sum() / bi[:, 1].sum():.2f}", fontsize=7.5)
        name = "fig_bounds_" + SHORT.get(s, "all").strip("_")
        st.save(fig, W3 / name)
        cap(W3 / f"{name}.png", f"""Upper bounds on speeding up Python process creation ({SHORT.get(s, s)}), Scarab golden_cove, cold:
        each cache level made perfect alone, all levels perfect, and self-warm (the same process run again immediately, every
        structure warm). Bars: instruction-weighted IPC ratio over {n} creations of the traced django-13809 run; whiskers:
        10th-90th percentile of per-creation speedups.""")
        for c, _ in ks:
            summ.append(dict(script=s, config=c, speedup=round(a3[(s, c)][0], 4), p10=round(a3[(s, c)][1], 4),
                             p90=round(a3[(s, c)][2], 4), n=a3[(s, c)][3]))
    # pow2 sensitivity
    p2 = {r["cid"]: r for r in py if r["config"] == "pow2_base"}
    a2 = agg([dict(r, config=r["config"].replace("pow2_", "")) for r in py if r["config"] == "pow2_perfect_all"], p2)
    if a2:
        fig, ax = plt.subplots(figsize=(4.2, 2.4))
        labels, v, lo, hi = [], [], [], []
        for s in scripts:
            for tag, d in (("golden_cove", a3), ("pow2 sets", a2)):
                if (s, "perfect_all") in d:
                    labels.append(f"{SHORT.get(s, 'all').strip('_')}\n{tag}")
                    v.append(d[(s, "perfect_all")][0]); lo.append(d[(s, "perfect_all")][1]); hi.append(d[(s, "perfect_all")][2])
        bars(ax, labels, v, lo, hi, [st.COLD if "golden" in l else "#6baed6" for l in labels])
        ax.set_ylabel("perfect-cache IPC speedup (×)"); ax.set_ylim(0, max(v) * 1.3)
        st.save(fig, W3 / "fig_pow2_sensitivity")
        cap(W3 / "fig_pow2_sensitivity.png", """The perfect-cache bound under PARAMS.golden_cove (whose LOG2 set indexing leaves the 3 MB
        LLC at 2 MB and the L2 at 1 MB effective) and under PARAMS.golden_cove_pow2 (L2 2 MiB/8-way, LLC 3 MiB/12-way, all sets
        used), each relative to its own baseline.""")
        for s in scripts:
            if (s, "perfect_all") in a2:
                summ.append(dict(script=s, config="pow2_perfect_all_vs_pow2_base", speedup=round(a2[(s, "perfect_all")][0], 4),
                                 p10=round(a2[(s, "perfect_all")][1], 4), p90=round(a2[(s, "perfect_all")][2], 4), n=a2[(s, "perfect_all")][3]))
    # shells
    sh = [r for r in w3 if r["kind"] == "shell"]
    sb = {r["cid"]: r for r in sh if r["config"] == "base"}
    ash = agg([r for r in sh if r["config"] == "perfect_all"], sb)
    for s in ("sh -c 'env bash -n' (tool-call wrapper)", "bash -n"):
        if (s, "perfect_all") in ash:
            summ.append(dict(script=s, config="perfect_all", speedup=round(ash[(s, "perfect_all")][0], 4),
                             p10=round(ash[(s, "perfect_all")][1], 4), p90=round(ash[(s, "perfect_all")][2], 4), n=ash[(s, "perfect_all")][3]))
    with open(W3 / "summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["script", "config", "speedup", "p10", "p90", "n"]); w.writeheader(); w.writerows(summ)

# ---------------- W4
w4 = load(W4 / "results.csv")
if w4 and py:
    selfr = [r for r in w4 if r["source"] == "self" and r["config"] != "record"]
    prevr = [r for r in w4 if r["source"] == "prev"]
    a4 = agg(selfr, base); ap = agg(prevr, base)
    order = ["instant_l2", "instant_llc", "stream_l2_2k", "stream_l2_20k", "stream_l2_200k", "stream_l2_bulk",
             "stream_llc_2k", "stream_llc_20k", "stream_llc_200k", "stream_llc_bulk"]
    lab = lambda c: c.replace("stream_", "stream\n").replace("instant_", "instant\n").replace("_", " ").replace("llc", "LLC").replace("l2", "L2")
    s4 = []
    for s in scripts:
        ks = [c for c in order if (s, c) in a4]
        if not ks:
            continue
        fig, ax = plt.subplots(figsize=(6.8, 2.7))
        v = [a4[(s, c)][0] for c in ks]
        bars(ax, [lab(c) for c in ks], v, [a4[(s, c)][1] for c in ks], [a4[(s, c)][2] for c in ks],
             [("#9ecae1" if c.startswith("instant") else st.COLD) for c in ks])
        refs = [("perfect_all", "perfect, all levels", st.INK), ("perfect_l2", "perfect L2", "#6b6b6b"), ("self_warm", "self-warm", st.WARM)]
        top = max(v)
        for c, name, col in refs:
            if (s, c) in a3:
                y = a3[(s, c)][0]; top = max(top, y)
                ax.axhline(y, color=col, lw=0.7, ls=(0, (1, 1.5)))
                ax.text(len(ks) - 0.5, y + 0.01, f"{name} {y:.2f}×", ha="right", va="bottom", fontsize=6, color=col)
        ax.set_ylim(0, top * 1.25); ax.set_ylabel("IPC speedup over golden_cove (×)")
        ax.set_xlabel(f"Ideal creation-time prefetcher (oracle record of the same run): {SHORT.get(s, s)}, {a4[(s, ks[0])][3]} creations")
        name = "fig_speedup_" + SHORT.get(s, "all").strip("_")
        st.save(fig, W4 / name)
        cap(W4 / f"{name}.png", f"""IPC speedup of Python process creation ({SHORT.get(s, s)}) with the ideal creation-time prefetcher over
        golden_cove, which keeps its own prefetchers. instant: every recorded line installed at process start with no bandwidth
        cost (a capacity bound). stream: lines issued through the normal prefetch queues 2K / 20K / 200K instructions ahead of
        first use, or all at once (bulk). Dotted lines: bounds from W3. Whiskers: 10th-90th percentile over creations.""")
        for c in ks:
            pa = a3.get((s, "perfect_all"), (np.nan,))[0]
            lvl = "perfect_l2" if "_l2" in c else "perfect_llc"
            pl = a3.get((s, lvl), (np.nan,))[0]
            s4.append(dict(script=s, source="self", config=c, speedup=round(a4[(s, c)][0], 4), p10=round(a4[(s, c)][1], 4),
                           p90=round(a4[(s, c)][2], 4), n=a4[(s, c)][3],
                           recovered_of_perfect_all=round((a4[(s, c)][0] - 1) / (pa - 1), 4) if pa > 1 else "",
                           recovered_of_perfect_level=round((a4[(s, c)][0] - 1) / (pl - 1), 4) if pl > 1 else ""))
        for c in [c for c in order if (s, c) in ap]:
            s4.append(dict(script=s, source="prev", config=c, speedup=round(ap[(s, c)][0], 4), p10=round(ap[(s, c)][1], 4),
                           p90=round(ap[(s, c)][2], 4), n=ap[(s, c)][3]))
    # share of the bound recovered
    sa = [r for r in s4 if r["script"] == "all Python creations" and r["source"] == "self" and r["recovered_of_perfect_all"] != ""]
    if sa:
        fig, ax = plt.subplots(figsize=(6.8, 2.5))
        x = np.arange(len(sa))
        v1 = [100 * r["recovered_of_perfect_all"] for r in sa]; v2 = [100 * r["recovered_of_perfect_level"] for r in sa]
        ax.bar(x - 0.18, v1, 0.36, color=st.COLD, edgecolor=st.INK, lw=0.4)
        ax.bar(x + 0.18, v2, 0.36, color="#6baed6", edgecolor=st.INK, lw=0.4)
        for xi, a, b in zip(x, v1, v2):
            ax.text(xi - 0.18, a + 1, f"{a:.0f}", ha="center", fontsize=5.8); ax.text(xi + 0.18, b + 1, f"{b:.0f}", ha="center", fontsize=5.8)
        ax.set_xticks(x); ax.set_xticklabels([lab(r["config"]) for r in sa], fontsize=6.5)
        ax.set_ylabel("Share of the bound's speedup\nrecovered (%)"); ax.set_ylim(0, max(v1 + v2) * 1.25)
        ax.text(0.0, 1.03, "■ of perfect (all levels)", color=st.COLD, transform=ax.transAxes, fontsize=6.5)
        ax.text(0.3, 1.03, "■ of perfect at the destination level (L2 or LLC)", color="#6baed6", transform=ax.transAxes, fontsize=6.5)
        st.save(fig, W4 / "fig_bound_recovered")
        cap(W4 / "fig_bound_recovered.png", """(speedup - 1) / (bound - 1) for every ideal-prefetcher configuration, all Python creations:
        against perfect caches at every level, and against a perfect cache at the level the prefetcher fills (L2 or LLC).""")
    # coverage and traffic
    covrows = []
    for r in selfr:
        b = base.get(r["cid"])
        if not b:
            continue
        lvl = "MLC_MISS_ONPATH" if "_l2" in r["config"] else "L1_MISS_ONPATH"
        bm, sm = float(b.get(lvl) or 0), float(r.get(lvl) or 0)
        covrows.append(dict(cid=r["cid"], config=r["config"], dest_level=lvl, base_misses=bm, spf_misses=sm,
                            coverage=(bm - sm) / bm if bm else np.nan,
                            extra_llc_miss_MB=64 * (float(r.get("L1_MISS_ALL") or 0) - float(b.get("L1_MISS_ALL") or 0)) / 2**20,
                            base_llc_miss_MB=64 * float(b.get("L1_MISS_ALL") or 0) / 2**20,
                            sent=r.get("spf_sent", ""), late=r.get("spf_late_skipped", ""), stalls=r.get("spf_queue_stalls", ""),
                            records=r.get("spf_records", "")))
    with open(W4 / "coverage.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(covrows[0])); w.writeheader(); w.writerows(covrows)
    ks = [c for c in order if any(x["config"] == c for x in covrows)]
    for metric, ylab, name in (("coverage", "Demand misses removed at the\ndestination level (%)", "fig_coverage"),
                               ("extra_llc_miss_MB", "Extra memory traffic per\ncreation (MB, LLC misses x 64 B)", "fig_traffic")):
        fig, ax = plt.subplots(figsize=(6.8, 2.4))
        v = [np.nanmedian([x[metric] for x in covrows if x["config"] == c]) * (100 if metric == "coverage" else 1) for c in ks]
        ax.bar(np.arange(len(ks)), v, color=st.COLD, edgecolor=st.INK, lw=0.4, width=0.68)
        for xi, y in enumerate(v):
            ax.text(xi, y + (max(v) * 0.02 if max(v) > 0 else 0.1), f"{y:.1f}", ha="center", fontsize=6)
        ax.set_xticks(np.arange(len(ks))); ax.set_xticklabels([lab(c) for c in ks], fontsize=6.5)
        ax.axhline(0, color=st.INK, lw=0.5)
        ax.set_ylabel(ylab)
        if metric == "extra_llc_miss_MB":
            bmed = np.median([x["base_llc_miss_MB"] for x in covrows])
            ax.text(0.99, 0.95, f"baseline: {bmed:.1f} MB of LLC misses per creation (median)", transform=ax.transAxes,
                    ha="right", va="top", fontsize=6.2, color=st.MUTED)
        st.save(fig, W4 / name)
        cap(W4 / f"{name}.png", ("Median over creations of the share of demand misses at the prefetcher's destination level (L2 or LLC) "
                                 "that the ideal prefetcher removes." if metric == "coverage" else
                                 "Median over creations of the extra memory traffic the ideal prefetcher causes: the increase in LLC "
                                 "misses of all kinds (demand and prefetch) x 64 B."))
    # self vs prev
    pk = [c for c in order if ("all Python creations", c) in ap]
    if pk:
        fig, ax = plt.subplots(figsize=(5.2, 2.4))
        x = np.arange(len(pk))
        vs = [a4[("all Python creations", c)][0] for c in pk]; vp = [ap[("all Python creations", c)][0] for c in pk]
        ax.bar(x - 0.18, vs, 0.36, color=st.COLD, edgecolor=st.INK, lw=0.4); ax.bar(x + 0.18, vp, 0.36, color=st.WARM, edgecolor=st.INK, lw=0.4)
        for xi, a, b in zip(x, vs, vp):
            ax.text(xi - 0.18, a + 0.01, f"{a:.2f}×", ha="center", fontsize=6); ax.text(xi + 0.18, b + 0.01, f"{b:.2f}×", ha="center", fontsize=6)
        ax.axhline(1, color=st.INK, lw=0.6, ls=(0, (3, 2)))
        ax.set_xticks(x); ax.set_xticklabels([lab(c) for c in pk], fontsize=6.5); ax.set_ylim(0, max(vs + vp) * 1.25)
        ax.set_ylabel("IPC speedup over golden_cove (×)")
        ax.text(0.0, 1.03, "■ oracle: this run's own record", color=st.COLD, transform=ax.transAxes, fontsize=6.5)
        ax.text(0.45, 1.03, "■ previous run of the script, rebased for ASLR", color=st.WARM, transform=ax.transAxes, fontsize=6.5)
        st.save(fig, W4 / "fig_prev_vs_self")
        rb = list(csv.DictReader(open(W4 / "rebase.csv")))
        cap(W4 / "fig_prev_vs_self.png", f"""The ideal prefetcher fed with the record of the previous creation of the same script, rebased to
        the new process's library addresses (heap, stack and anonymous lines cannot be rebased and are dropped: median
        {100 * np.median([int(r['dropped_private']) / int(r['lines']) for r in rb]):.0f}% of the record), against the oracle record of the
        same run. Of the rebased lines, a median {100 * np.median([float(r['accuracy_upper']) for r in rb]):.1f}% are touched by the new
        process; they cover {100 * np.median([float(r['coverage_upper']) for r in rb]):.1f}% of its own lines.""")
    # pollution
    pol = load(W4 / "pollution.csv")
    if pol:
        pb = {r["cid"]: r for r in pol if r["config"] == "base"}
        pv = defaultdict(list)
        for r in pol:
            if r["config"] != "base" and r["cid"] in pb:
                pv[r["config"]].append(100 * (int(r["cycles"]) / int(pb[r["cid"]]["cycles"]) - 1))
        ks = list(pv)
        fig, ax = plt.subplots(figsize=(4.2, 2.3))
        v = [np.median(pv[c]) for c in ks]
        ax.bar(np.arange(len(ks)), v, color=st.WARM, edgecolor=st.INK, lw=0.4, width=0.6)
        for xi, y in enumerate(v):
            ax.text(xi, y + 0.02 * (max(map(abs, v)) or 1), f"{y:+.2f}%", ha="center", fontsize=6.3)
        ax.axhline(0, color=st.INK, lw=0.5)
        ax.set_xticks(np.arange(len(ks))); ax.set_xticklabels([lab(c) for c in ks], fontsize=6.5)
        ax.set_ylabel("Harness cycles added by a\nmispredicted prefetch (%)")
        st.save(fig, W4 / "fig_pollution")
        cap(W4 / "fig_pollution.png", f"""Cost of a false prediction: harness agent-loop windows (first 20M instructions, {len(pb)} windows)
        simulated while one Python creation's record is prefetched into them, relative to the same windows without it.""")
        for c in ks:
            s4.append(dict(script="harness (false positive)", source="pollution", config=c, speedup=round(1 / (1 + np.median(pv[c]) / 100), 4), n=len(pv[c])))
    with open(W4 / "summary.csv", "w", newline="") as fh:
        keys = []
        for r in s4:
            keys += [k for k in r if k not in keys]
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(s4)
print("w3/w4 figures written")
