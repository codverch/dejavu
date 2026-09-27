#!/usr/bin/env python3
"""W8: performance headroom of start-up prefetching into the L1, in the manner of Constable (ISCA'24 §4).

  w8_headroom.py <out dir> --pkg <ideal-prefetching package> <task>=<DR run dir> ... [--jobs N]

Units. Per task, the Python processes that tool calls created (tool-execution phase, window 0,
main thread) that have an earlier process of the same script in the same task, sorted by start
time; five are taken at the 10th, 30th, 50th, 70th and 90th percentile positions. Fixed before any
simulation. The region is a unit's first min(instrs, 100M) instructions: its start-up and, after
it, the start of the script's own work (in django the start-up is ~73M instructions).

Records (prefetcher/startup_pf.c, spf_mode 1): the lines the region touches. "self" is the unit's
own record, an oracle. "prev" is the record of the previous process of the same script, rebased to
this process's library addresses (lib/rebase.py; heap, stack and anonymous lines cannot be rebased
and are dropped): what a predictor that has seen the script start once can know.

Configurations, all on PARAMS.golden_cove, cold:
  base                  golden_cove
  ideal_l1d_prev        L1-D accesses to the previous start-up's lines always hit (spf_mode 3)
  ideal_l1i_prev        the same for L1-I fetches
  ideal_l1_prev         both: the headroom of prefetching into the L1 what history predicts
  ideal_l1_self         both, with the unit's own lines: a perfect L1 for the region
  count_prev            base, counting its L1 misses to the previous start-up's lines: the opportunity
  install_prev          the previous start-up's lines put in the L2 and LLC before the process
                        starts (issued at the model call), soonest-needed first, no eviction; the
                        LLC takes the lines the L2 has no room for (the hierarchy is exclusive)
  perfect_l1d           every L1-D access hits (Scarab --perfect_dcache)
  perfect_all           every cache level perfect: the bound for any prefetcher
  l1d_2x, l2_2x         brute force: twice the L1-D, twice the (effective) L2

Outputs: selection.csv, rebase.csv, results.csv, checks.csv.
"""
import argparse, csv, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sim  # noqa: E402
from rebase import REC, rebase  # noqa: E402

CAP, N_PER_TASK, QUANT = 100_000_000, 5, (0.1, 0.3, 0.5, 0.7, 0.9)
CFGS = {
    "base": lambda s, p: [],
    "ideal_l1d_prev": lambda s, p: ["--spf_mode", "3", "--spf_file", p, "--spf_ideal", "1"],
    "ideal_l1i_prev": lambda s, p: ["--spf_mode", "3", "--spf_file", p, "--spf_ideal", "2"],
    "ideal_l1_prev": lambda s, p: ["--spf_mode", "3", "--spf_file", p, "--spf_ideal", "3"],
    "ideal_l1_self": lambda s, p: ["--spf_mode", "3", "--spf_file", s, "--spf_ideal", "3"],
    "count_prev": lambda s, p: ["--spf_mode", "3", "--spf_file", p, "--spf_ideal", "7"],
    "install_prev": lambda s, p: ["--spf_mode", "2", "--spf_file", p, "--spf_dest", "4", "--spf_timing", "0"],
    "perfect_l1d": lambda s, p: ["--perfect_dcache", "1"],
    "perfect_all": lambda s, p: ["--perfect_icache", "1", "--perfect_dcache", "1", "--perfect_mlc", "1", "--perfect_l1", "1"],
    "l1d_2x": lambda s, p: ["--dcache_size", "98304"],
    "l2_2x": lambda s, p: ["--mlc_size", "4194000"],
}
KEEP = ("DCACHE_MISS_ONPATH", "ICACHE_MISS_ONPATH", "MLC_MISS_ONPATH", "L1_MISS_ONPATH")


def script(cmdline, comm):
    """the script a Python process runs: its first non-option argument, or -c / -m"""
    toks = cmdline.split()
    for t in toks[1:]:
        if t in ("-c", "-m"):
            return f"{comm} {t}"
        if not t.startswith("-"):
            return f"{comm} {Path(t).name}"
    return comm


def select(task, run):
    rows = [r for r in csv.DictReader(open(Path(run) / "attribution" / "windows.csv"))
            if r["phase"] == "tool execution" and r["comm"].startswith("python") and r["window"] == "0"
            and r["tid"] == r["pid"] and int(r["instrs"]) >= 1_000_000]
    rows.sort(key=lambda r: float(r["t_start"]))
    last, cand = {}, []
    for r in rows:
        s = script(r["cmdline"], r["comm"])
        if s in last:
            cand.append(dict(r, task=task, script=s, prev_cid=last[s]["cid"], prev_trace=last[s]["trace_zip"],
                             prev_instrs=last[s]["instrs"]))
        last[s] = r
    pick = sorted({round(q * (len(cand) - 1)) for q in QUANT})
    return [dict(cand[i], uid=f"{task.split('__')[1].rsplit('-', 1)[0]}-{cand[i]['cid']}", candidates=len(cand))
            for i in pick]


def modlog(trace):
    return str(Path(trace).parent.parent / "raw" / "modules.log")


def job(j):
    uid, trace, cfg, args, n, pkg, out = j
    r = sim.run(pkg, trace, Path(out) / "runs" / f"{uid}__{cfg}", args, inst_limit=n)
    row = dict(uid=uid, config=cfg, ok=int(r["ok"]), insts=r["insts"], cycles=r["cycles"])
    row.update({k: r["stats"].get(k, "") for k in KEEP})
    row.update({f"spf_{k}": v for k, v in sim.spf_fields(r["spf"]).items()})
    return row


def pool(jobs, n):
    with ProcessPoolExecutor(n) as ex:
        rows = list(ex.map(job, jobs, chunksize=1))
    for r in rows:
        if not r["ok"]:
            print("FAILED", r["uid"], r["config"], flush=True)
    return rows


def write(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("runs", nargs="+", metavar="task=run_dir")
    ap.add_argument("--pkg", required=True); ap.add_argument("--jobs", type=int, default=100); a = ap.parse_args()
    out = Path(a.out).resolve(); (out / "records").mkdir(parents=True, exist_ok=True)
    units = [u for x in a.runs for u in select(*x.split("=", 1))]
    write(out / "selection.csv", [{k: u[k] for k in ("uid", "task", "cid", "step", "script", "instrs", "prev_cid",
                                                    "prev_instrs", "candidates", "cmdline", "trace_zip", "prev_trace")}
                                  for u in units])
    # pass 1: own record, and the previous process's record over the same number of instructions
    rec = lambda uid, who: str(out / "records" / f"{uid}__{who}.bin")  # noqa: E731
    rj = []
    for u in units:
        n = min(int(u["instrs"]), CAP)
        rj.append((u["uid"], u["trace_zip"], "record_self", ["--spf_mode", "1", "--spf_file", rec(u["uid"], "self"),
                                                            "--spf_region_instrs", str(n)], n, a.pkg, str(out)))
        m = min(int(u["prev_instrs"]), CAP)
        rj.append((u["uid"], u["prev_trace"], "record_prevproc", ["--spf_mode", "1", "--spf_file", rec(u["uid"], "prevproc"),
                                                                 "--spf_region_instrs", str(m)], m, a.pkg, str(out)))
    rows = pool(rj, a.jobs)
    rb = []
    for u in units:
        src = np.fromfile(rec(u["uid"], "prevproc"), dtype=REC)
        moved, st = rebase(src, modlog(u["prev_trace"]), modlog(u["trace_zip"]))
        moved.tofile(rec(u["uid"], "prev"))
        own = set((np.fromfile(rec(u["uid"], "self"), dtype=REC)["line"] & ~np.uint64(63)).tolist())
        ml = set((moved["line"] & ~np.uint64(63)).tolist())
        rb.append(dict(uid=u["uid"], **st, own_lines=len(own), prev_lines_in_own=len(ml & own) / max(len(ml), 1),
                       own_lines_predicted=len(ml & own) / max(len(own), 1)))
    write(out / "rebase.csv", rb)
    # pass 2
    jobs = [(u["uid"], u["trace_zip"], c, f(rec(u["uid"], "self"), rec(u["uid"], "prev")), min(int(u["instrs"]), CAP),
             a.pkg, str(out)) for u in units for c, f in CFGS.items()]
    rows += pool(sorted(jobs, key=lambda j: -j[4]), a.jobs)
    by = {(r["uid"], r["config"]): r for r in rows}
    checks = [dict(check="record pass cycles == base cycles", uid=u["uid"],
                   ok=int(by[(u["uid"], "record_self")]["ok"] == 1
                          and by[(u["uid"], "record_self")]["cycles"] == by[(u["uid"], "base")]["cycles"]))
              for u in units]
    checks += [dict(check="count-only cycles == base cycles", uid=u["uid"],
                    ok=int(by[(u["uid"], "count_prev")]["ok"] == 1
                           and by[(u["uid"], "count_prev")]["cycles"] == by[(u["uid"], "base")]["cycles"]))
               for u in units]
    task = {u["uid"]: u["task"] for u in units}
    for r in rows:
        r["task"] = task[r["uid"]]
    write(out / "results.csv", rows); write(out / "checks.csv", checks)
    print(f"{len(units)} units; {sum(c['ok'] for c in checks)}/{len(checks)} record==base checks passed; "
          f"{sum(r['ok'] for r in rows)}/{len(rows)} runs ok", flush=True)


if __name__ == "__main__":
    main()
