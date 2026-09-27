#!/usr/bin/env python3
"""W6: ideal prefetching on other SWE-bench tasks, two units per phase.

  w6_more_traces.py <traces dir> <out dir> --pkg <ideal-prefetching package> [--jobs N]

The traces are the sampled DR runs of four tasks other than W0's django task (100M
instructions of every 1B, all processes). A unit is one thread of one window. Phases:

  harness start-up          harness main thread, window 0
  harness: agent loop       harness main thread, a later window
  harness exit              harness main thread
  environment setup         a Python process, window 0
  tool execution: python    a Python process, window 0 (its creation)
  tool execution: shell     bash, window 0

Selection, fixed before any simulation: per phase, the two tasks with the most candidate units
(ties alphabetical); in each, the unit of median length (lower median, ties by cid). Units under
1M instructions are not candidates. The simulated region is the unit's first min(instrs, 100M)
instructions, or fewer where --limit is given: Scarab asserts on an instruction it cannot decode
(OP_INV), and such a unit is simulated up to just before it rather than replaced (limits.csv).

Per unit, on PARAMS.golden_cove: base, perfect_all, a record pass (its cycles must equal base),
and replays of the unit's own record (an oracle: every line the region will touch, in order):
instant_{l2,llc,both}, stream_{l2,llc}_bulk, stream_{l2,llc}_20k. Speedup is IPC over base.

Outputs: selection.csv, results.csv, checks.csv.
"""
import argparse, csv, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w4_ideal_prefetch import pool, write  # noqa: E402

TASKS = ["psf__requests-1142", "pydata__xarray-2905", "sphinx-doc__sphinx-8459", "sympy__sympy-11618"]
CFGS = ["base", "perfect_all", "instant_l2", "instant_llc", "instant_both",
        "stream_l2_bulk", "stream_llc_bulk", "stream_l2_20k", "stream_llc_20k"]
CAP, MIN = 100_000_000, 1_000_000


def phase_of(r):
    main, w0 = r["tid"] == r["pid"], r["window"] == "0"
    if r["is_harness"] == "1":
        if not main:
            return None
        if r["phase"] == "harness start-up" and w0:
            return "harness start-up"
        if r["phase"] == "harness: agent loop" and not w0:
            return "harness: agent loop"
        if r["phase"] == "harness exit":
            return "harness exit"
        return None
    if not w0:
        return None
    py = r["comm"].startswith("python")
    if r["phase"] == "environment setup" and py:
        return "environment setup"
    if r["phase"] == "tool execution" and py:
        return "tool execution: python"
    if r["phase"] == "tool execution" and r["comm"] == "bash":
        return "tool execution: shell"
    return None


def select(traces):
    cand = defaultdict(lambda: defaultdict(list))
    for t in TASKS:
        for r in csv.DictReader(open(Path(traces) / t / "trace1" / "attribution" / "windows.csv")):
            p = phase_of(r)
            if p and int(r["instrs"]) >= MIN:
                cand[p][t].append(dict(r, task=t, unit_phase=p))
    sel = []
    for p in ("harness start-up", "environment setup", "tool execution: python",
              "tool execution: shell", "harness: agent loop", "harness exit"):
        tasks = sorted(cand[p], key=lambda t: (-len(cand[p][t]), t))[:2]
        for t in tasks:
            us = sorted(cand[p][t], key=lambda r: (int(r["instrs"]), int(r["cid"])))
            u = us[(len(us) - 1) // 2]
            sel.append(dict(u, uid=f"{t.split('__')[0]}-{u['cid']}", candidates=len(us)))
    return sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces"); ap.add_argument("out")
    ap.add_argument("--pkg", required=True); ap.add_argument("--jobs", type=int, default=48)
    ap.add_argument("--limit", action="append", default=[], metavar="UID=N",
                    help="simulate only the unit's first N instructions (Scarab cannot decode an instruction after them)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    (out / "records").mkdir(parents=True, exist_ok=True)
    sel = select(a.traces)
    write(out / "selection.csv", [{k: u[k] for k in ("uid", "task", "unit_phase", "cid", "comm", "pid", "tid", "window",
                                                    "instrs", "candidates", "step", "tool_command", "trace_zip")}
                                  for u in sel])
    G = "PARAMS.golden_cove"
    units = [dict(cid=u["uid"], trace_zip=u["trace_zip"], script=u["unit_phase"], step=u["task"]) for u in sel]
    n = {u["uid"]: min(int(u["instrs"]), CAP) for u in sel}
    for x in a.limit:
        k, v = x.split("="); n[k] = min(n[k], int(v))
    write(out / "limits.csv", [dict(uid=k, sim_instrs=v, truncated=int(v < min(int(u["instrs"]), CAP)))
                               for u in sel for k, v in [(u["uid"], n[u["uid"]])]])
    rec = {u["cid"]: str(out / "records" / f"{u['cid']}.bin") for u in units}
    rows = pool([("self", u, c, rec[u["cid"]], G, n[u["cid"]], a.pkg, str(out)) for u in units for c in ("record", "base")], a.jobs)
    by = {(r["cid"], r["config"]): r for r in rows}
    checks = [dict(check="record pass cycles == base cycles", cid=u["cid"],
                   ok=int(by[(u["cid"], "record")]["ok"] == 1 and by[(u["cid"], "record")]["cycles"] == by[(u["cid"], "base")]["cycles"]),
                   record_cycles=by[(u["cid"], "record")]["cycles"], base_cycles=by[(u["cid"], "base")]["cycles"]) for u in units]
    jobs = [("self", u, c, rec[u["cid"]], G, n[u["cid"]], a.pkg, str(out))
            for u in units if by[(u["cid"], "record")]["ok"] for c in CFGS if c != "base"]
    rows += pool(sorted(jobs, key=lambda j: -j[5]), a.jobs)
    for r in rows:
        r["phase"] = r.pop("script"); r["task"] = r.pop("step")
    write(out / "results.csv", rows)
    write(out / "checks.csv", checks)
    print(f"{len(units)} units; {sum(c['ok'] for c in checks)}/{len(checks)} record==base checks passed; "
          f"{sum(r['ok'] for r in rows)}/{len(rows)} runs ok", flush=True)


if __name__ == "__main__":
    main()
