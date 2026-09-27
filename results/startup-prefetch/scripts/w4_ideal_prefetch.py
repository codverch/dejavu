#!/usr/bin/env python3
"""W4: how much of the perfect-cache bound an ideal creation-time prefetcher recovers.

  w4_ideal_prefetch.py <DR run dir> <W1 dir> <W3 dir> <out dir> --pkg <ideal-prefetching package> [--jobs N]

Two passes per Python process creation (prefetcher/startup_pf.c), creation region only:
  record   --spf_mode 1: the region's lines in first-touch order -> records/<cid>.bin. Its cycles
           must equal W3's base cycles (a record pass does not perturb timing): checked.
  replay   --spf_mode 2, source "self" (the same trace: an oracle), configurations
             instant_l2, instant_llc                every line installed at process start, no bandwidth
             stream_{l2,llc}_{2k,20k,200k,bulk}     through the prefetch queues, spf_lookahead
                                                    instructions ahead of first use (bulk = no limit)
           source "prev": the previous creation of the same script, its record rebased for ASLR
           (lib/rebase.py; heap/stack/anonymous lines dropped), stream_{l2,llc}_{20k,bulk}.
  pow2     base, perfect_all and stream_l2_bulk / stream_llc_bulk on PARAMS.golden_cove_pow2.
Pollution: a false prediction prefetches a creation's lines while the harness runs. Harness
agent-loop windows (first 20M instructions) are simulated with and without replaying one
creation's record (instant_llc, stream_l2_bulk, stream_llc_bulk).

Outputs: results.csv, rebase.csv (prev: lines rebased/dropped, overlap with the new process's own
record), pollution.csv, checks.csv.
"""
import argparse, csv, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sim  # noqa: E402
from rebase import REC, rebase  # noqa: E402

LOOK = {"2k": 2000, "20k": 20000, "200k": 200000, "bulk": 4_000_000_000}
SELF_CFGS = ["instant_l2", "instant_llc"] + [f"stream_{d}_{l}" for d in ("l2", "llc") for l in LOOK]
PREV_CFGS = [f"stream_{d}_{l}" for d in ("l2", "llc") for l in ("20k", "bulk")]
POW2_CFGS = ["stream_l2_bulk", "stream_llc_bulk"]
KEEP = ("ICACHE_MISS_ONPATH", "DCACHE_MISS_ONPATH", "MLC_MISS_ONPATH", "L1_MISS_ONPATH", "L1_MISS_ALL", "MLC_MISS_ALL",
        "PREF_UL1REQ_QUEUE_SENTREQ", "PREF_UMLC_REQ_QUEUE_SENTREQ")


def spf_args(cfg, rec):
    kind, dest = cfg.split("_")[0], cfg.split("_")[1]
    d = {"l2": "2", "llc": "3"}[dest]
    a = ["--spf_mode", "2", "--spf_file", rec, "--spf_dest", d]
    if kind == "instant":
        return a + ["--spf_timing", "0"]
    return a + ["--spf_timing", "1", "--spf_lookahead", str(LOOK[cfg.split("_")[2]])]


def job(j):
    tag, u, cfg, rec, params, inst_limit, pkg, out = j
    d = Path(out) / "runs" / f"{u['cid']}__{tag}__{cfg}"
    args = ["--spf_mode", "1", "--spf_file", rec, "--spf_region_instrs", str(inst_limit)] if cfg == "record" else \
        ([] if cfg == "base" else (["--perfect_icache", "1", "--perfect_dcache", "1", "--perfect_mlc", "1", "--perfect_l1", "1"]
                                   if cfg == "perfect_all" else spf_args(cfg, rec)))
    r = sim.run(pkg, u["trace_zip"], d, args, params=params, inst_limit=inst_limit)
    row = dict(cid=u["cid"], script=u.get("script", ""), step=u.get("step", ""), source=tag, config=cfg,
               params=params, ok=int(r["ok"]), insts=r["insts"], cycles=r["cycles"])
    row.update({k: r["stats"].get(k, "") for k in KEEP})
    row.update({f"spf_{k}": v for k, v in sim.spf_fields(r["spf"]).items()})
    return row


def pool(jobs, n):
    rows = []
    with ProcessPoolExecutor(n) as ex:
        for r in ex.map(job, jobs, chunksize=1):
            rows.append(r)
            if not r["ok"]:
                print("FAILED", r["cid"], r["source"], r["config"], flush=True)
    return rows


def write(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    for x in ("run", "w1", "w3", "out"):
        ap.add_argument(x)
    ap.add_argument("--pkg", required=True); ap.add_argument("--jobs", type=int, default=48); a = ap.parse_args()
    out = Path(a.out); (out / "records").mkdir(parents=True, exist_ok=True)
    win = {r["cid"]: r for r in csv.DictReader(open(Path(a.run) / "attribution" / "windows.csv"))}
    cr = [dict(r, trace_zip=win[r["cid"]]["trace_zip"],
               modlog=str(Path(win[r["cid"]]["trace_zip"]).parent.parent / "raw" / "modules.log"))
          for r in csv.DictReader(open(Path(a.w1) / "creation.csv")) if r["complete"] == "1"]
    cr.sort(key=lambda r: float(r["t_start"]))
    w3 = {(r["cid"], r["config"]): r for r in csv.DictReader(open(Path(a.w3) / "results.csv"))}
    G, P2 = "PARAMS.golden_cove", "PARAMS.golden_cove_pow2"
    rec = {u["cid"]: str(out / "records" / f"{u['cid']}.bin") for u in cr}
    # pass 1
    rows = pool([("self", u, "record", rec[u["cid"]], G, int(u["region_instrs"]), a.pkg, str(out)) for u in cr], a.jobs)
    checks = []
    for r in rows:
        b = w3.get((r["cid"], "base"))
        same = b is not None and r["ok"] and str(r["cycles"]) == b["cycles"] and str(r["insts"]) == b["insts"]
        checks.append(dict(check="record pass cycles == W3 base cycles", cid=r["cid"], ok=int(same),
                           record_cycles=r["cycles"], base_cycles=b["cycles"] if b else ""))
    # prev records, rebased
    rb_rows, last, prev_rec = [], {}, {}
    for u in cr:
        s = u["script"]
        if s in last:
            p = last[s]
            src = np.fromfile(rec[p["cid"]], dtype=REC)
            moved, st = rebase(src, p["modlog"], u["modlog"])
            f = out / "records" / f"{u['cid']}__prev.bin"; moved.tofile(f); prev_rec[u["cid"]] = str(f)
            own = np.fromfile(rec[u["cid"]], dtype=REC)
            ol = set((own["line"] & ~np.uint64(63)).tolist()); ml = set((moved["line"] & ~np.uint64(63)).tolist())
            inter = len(ol & ml)
            rb_rows.append(dict(cid=u["cid"], prev_cid=p["cid"], script=s, **st, own_lines=len(ol),
                                accuracy_upper=inter / max(len(ml), 1), coverage_upper=inter / max(len(ol), 1)))
        last[s] = u
    write(out / "rebase.csv", rb_rows)
    # pass 2
    jobs = []
    for u in cr:
        n = int(u["region_instrs"])
        jobs += [("self", u, c, rec[u["cid"]], G, n, a.pkg, str(out)) for c in SELF_CFGS]
        if u["cid"] in prev_rec:
            jobs += [("prev", u, c, prev_rec[u["cid"]], G, n, a.pkg, str(out)) for c in PREV_CFGS]
        jobs += [("pow2", u, c, rec[u["cid"]], P2, n, a.pkg, str(out)) for c in POW2_CFGS]
    jobs.sort(key=lambda j: -j[5])
    rows += pool(jobs, a.jobs)
    write(out / "results.csv", rows)
    # pollution: harness agent-loop windows with a creation's lines prefetched into them
    hw = [r for r in win.values() if r["is_harness"] == "1" and r["tid"] == r["pid"] and r["phase"] in ("harness: agent loop",)]
    hw = sorted(hw, key=lambda r: float(r["t_start"]))[:8]
    donor = rec[cr[len(cr) // 2]["cid"]] if cr else None
    pj = []
    for h in hw:
        u = dict(cid=h["cid"], trace_zip=h["trace_zip"], script="harness", step=h["step"])
        n = min(int(h["instrs"]), 20_000_000)
        pj += [("harness", u, c, donor, G, n, a.pkg, str(out)) for c in ("base", "instant_llc", "stream_l2_bulk", "stream_llc_bulk")]
    write(out / "pollution.csv", pool(pj, a.jobs) if pj and donor else [])
    write(out / "checks.csv", checks)
    print(f"{len(cr)} creations; {sum(c['ok'] for c in checks)}/{len(checks)} record==base checks passed; "
          f"{sum(r['ok'] for r in rows)}/{len(rows)} runs ok", flush=True)


if __name__ == "__main__":
    main()
