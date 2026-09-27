#!/usr/bin/env python3
"""W3: baseline behaviour of every Python process creation, and its bounds.

  w3_baseline.py <DR run dir> <W1 dir> <out dir> --pkg <scarab package> [--jobs N]

For every Python process a tool call created (W1 creation.csv, creation region fully traced), the
creation region alone (inst_limit = region length) is simulated, cold, under:
  base         PARAMS.golden_cove as shipped (its stream prefetcher into the LLC and FDIP on)
  perfect_l1i / perfect_l1d / perfect_l2 / perfect_llc   one cache level perfect
  perfect_all  every level perfect: the bound for any prefetcher of the creation region
  pow2_base, pow2_perfect_all   the same on PARAMS.golden_cove_pow2 (power-of-two set counts)
Self-warm: the whole process is replayed twice back to back (--memtrace_repeat=2, stats every
100K instructions); the creation region's cycles in pass 2 are summed over the intervals that
end inside it (to within one 100K interval).
Also the tool-call wrapper processes (sh -c, bash -n) whole, under base and perfect_all.

Output: results.csv (one row per process x configuration), with the key counters.
"""
import argparse, csv, glob, json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sim  # noqa: E402

PERF = {"perfect_l1i": ["--perfect_icache", "1"], "perfect_l1d": ["--perfect_dcache", "1"],
        "perfect_l2": ["--perfect_mlc", "1"], "perfect_llc": ["--perfect_l1", "1"],
        "perfect_all": ["--perfect_icache", "1", "--perfect_dcache", "1", "--perfect_mlc", "1", "--perfect_l1", "1"]}
KEEP = ("ICACHE_MISS_ONPATH", "DCACHE_MISS_ONPATH", "MLC_MISS_ONPATH", "L1_MISS_ONPATH", "MAIN_ALL_RECOVER_AT_EXEC",
        "MAIN_ALL_RECOVER_AT_DECODE", "L1_MISS_ALL", "MLC_MISS_ALL", "PREF_UL1REQ_QUEUE_SENTREQ", "PREF_UMLC_REQ_QUEUE_SENTREQ")


def job(j):
    kind, u, cfg, pkg, out = j
    d = Path(out) / "runs" / f"{u['cid']}__{cfg}"
    if cfg == "self_warm":
        cache = d / "self_warm.json"
        if cache.exists():
            return json.load(open(cache))
        r = sim.run(pkg, u["trace_zip"], d, ["--memtrace_repeat=2", "--periodic_dump", "1", "--heartbeat_interval", "100000"],
                    inst_limit=10**10, keep_stats=True)
        cyc = None
        if r["ok"]:
            import re
            def val(txt, name, total=False):
                m = re.search(rf"^{name}_{'total_count' if total else 'count'},\s*\d+,\s*(-?\d+)", txt, re.M)
                return int(m.group(1)) if m else 0
            p1 = glob.glob(str(d / "core.stat.0.csv.period.*.pass.1"))
            b = val(open(p1[0]).read(), "NODE_INST_COUNT", True) if p1 else None
            rows = []
            for f in glob.glob(str(d / "core.stat.0.csv.period.*")):
                if f.endswith(".pass.1"):
                    continue
                n = f.rsplit(".", 1)[1]
                core, memf = open(f).read(), open(d / f"memory.stat.0.csv.period.{n}").read()
                rows.append((val(core, "NODE_INST_COUNT", True), val(core, "NODE_CYCLE"), val(memf, "ICACHE_MISS_ONPATH"),
                             val(memf, "DCACHE_MISS_ONPATH"), val(memf, "MLC_MISS_ONPATH"), val(memf, "L1_MISS_ONPATH")))
            rows.sort()
            # per 100K interval, both passes: cumulative instructions, cycles, L1-I/L1-D/L2/LLC misses
            np.savez_compressed(d / "series.npz", data=np.array(rows, dtype=np.int64), pass1_end=b if b is not None else -1,
                                cols=np.array(["insts_total", "cycles", "l1i_miss", "l1d_miss", "l2_miss", "llc_miss"]))
            reg = int(u["region_instrs"])
            if b is not None:
                cyc = sum(r_[1] for r_ in rows if b < r_[0] <= b + reg)
                done = max((r_[0] for r_ in rows if r_[0] <= b + reg), default=b) - b
            for f in glob.glob(str(d / "*.stat.0.*")):
                Path(f).unlink()
        row = dict(kind=kind, cid=u["cid"], script=u["script"], step=u["step"], config=cfg, ok=int(r["ok"] and cyc is not None),
                   insts=done if cyc is not None else "", cycles=cyc if cyc is not None else "")
        json.dump(row, open(cache, "w"))
        return row
    args = PERF.get(cfg.replace("pow2_", ""), [])
    params = "PARAMS.golden_cove_pow2" if cfg.startswith("pow2_") else "PARAMS.golden_cove"
    r = sim.run(pkg, u["trace_zip"], d, args, params=params, inst_limit=int(u["region_instrs"]))
    row = dict(kind=kind, cid=u["cid"], script=u["script"], step=u["step"], config=cfg, ok=int(r["ok"]),
               insts=r["insts"], cycles=r["cycles"])
    row.update({k: r["stats"].get(k, "") for k in KEEP})
    return row


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("w1"); ap.add_argument("out")
    ap.add_argument("--pkg", required=True); ap.add_argument("--jobs", type=int, default=48); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    win = {r["cid"]: r for r in csv.DictReader(open(Path(a.run) / "attribution" / "windows.csv"))}
    creations = [dict(r, trace_zip=win[r["cid"]]["trace_zip"]) for r in csv.DictReader(open(Path(a.w1) / "creation.csv"))
                 if r["complete"] == "1"]
    shells = []
    for r in csv.DictReader(open(Path(a.w1) / "shells.csv")):
        if r["cls"] in ("sh -c 'env bash -n' (tool-call wrapper)", "bash -n"):
            w = win[r["cid"]]
            shells.append(dict(cid=r["cid"], script=r["cls"], step=r["step"], trace_zip=w["trace_zip"], region_instrs=w["instrs"]))
    jobs = []
    for u in creations:
        for cfg in ["base", *PERF, "pow2_base", "pow2_perfect_all", "self_warm"]:
            jobs.append(("python", u, cfg, a.pkg, str(out)))
    for u in shells:
        for cfg in ("base", "perfect_all"):
            jobs.append(("shell", u, cfg, a.pkg, str(out)))
    jobs.sort(key=lambda j: -int(j[1]["region_instrs"]) * (3 if j[2] == "self_warm" else 1))
    print(f"{len(creations)} creations, {len(shells)} shell processes, {len(jobs)} simulations", flush=True)
    rows = []
    with ProcessPoolExecutor(a.jobs) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=1), 1):
            rows.append(r)
            if not r["ok"]:
                print("FAILED", r["cid"], r["config"], flush=True)
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(out / "results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rows)
    print(f"{sum(r['ok'] for r in rows)} of {len(rows)} ok", flush=True)


if __name__ == "__main__":
    main()
