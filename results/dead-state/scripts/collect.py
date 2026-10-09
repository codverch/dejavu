#!/usr/bin/env python3
"""Collect per-(unit, config) results and aggregate.

  collect.py <units.tsv> <sim_root> <out_dir>

Estimators (units were PPS-sampled within (task, phase) strata, inclusion prob. pi):
  represented y of a unit = y x window weight; HT total = sum(y * weight / pi)
  IPC(config) = HT(instructions) / HT(cycles); speedup vs LRU = HT(cycles_lru) / HT(cycles_cfg)
  95% CI: stratified bootstrap over units (resample n_h units with replacement per stratum), 2000 reps.
Only post-warmup ("Periodic") counts are used.
Dead state (from the LRU runs), capacity-time of each cache split into live and dead:
  removed blocks: live = fill -> last touch, dead = last touch -> eviction (exact)
  blocks resident at the window end: time since the last touch is unresolved, so it is
  reported as bounds: lower bound counts it live, upper bound counts it dead.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

CONFIGS = ["lru", "mj", "oracle", "oracle_byp", "never_byp", "min"]
CACHES = ["ICACHE", "DCACHE", "MLC_CACHE", "L1_CACHE"]
RNG = np.random.default_rng(20260926)


def periodic(path):
    for line in open(path):
        if line.startswith("Periodic:"):
            m = re.search(r"Cycles:\s*(\d+)\s+Instructions:\s*(\d+)", line)
            return int(m.group(1)), int(m.group(2))
    return None


def stat_first(path, names):
    out = {}
    for line in open(path):
        p = line.split()
        if len(p) >= 2 and p[0] in names:
            out[p[0]] = int(p[1])
    return out


def dbx(path):
    caches, pol = {}, {}
    hdr = None
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("#") or not line:
            continue
        if line.startswith("cache,"):
            hdr = line.split(",")
            continue
        if "=" in line:
            for kv in line.split():
                k, v = kv.split("=")
                pol[k] = int(v)
            continue
        f = line.split(",")
        caches[f[0]] = {k: (int(v) if v.isdigit() else v) for k, v in zip(hdr, f)}
    return caches, pol


def main():
    units_tsv, root, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    units = list(csv.DictReader(open(units_tsv), delimiter="\t"))
    rows, missing = [], []
    for u in units:
        for c in CONFIGS:
            d = root / u["task"] / u["cid"] / c
            try:
                ok = (d / "rc").read_text().strip() == "0"
                cyc, ins = periodic(d / "core.stat.0.out")
                mem = stat_first(d / "memory.stat.0.out", {"L1_DEMAND_MISS", "L1_DEMAND_ACCESS", "MLC_DEMAND_MISS"})
                caches, pol = dbx(d / "dbx.stat.out")
            except (OSError, TypeError):
                ok = False
            if not ok:
                missing.append(f"{u['task']}/{u['cid']}/{c}")
                continue
            r = dict(task=u["task"], phase=u["phase"], cid=u["cid"], comm=u["comm"], cmd=u["cmd"],
                     window=int(u["window"]), weight=float(u["weight"]), pi=float(u["pi"]), config=c,
                     cycles=cyc, instrs=ins, llc_demand_miss=mem.get("L1_DEMAND_MISS", 0),
                     llc_demand_access=mem.get("L1_DEMAND_ACCESS", 0), mlc_demand_miss=mem.get("MLC_DEMAND_MISS", 0),
                     bypasses=pol.get("bypasses", 0), unmatched=pol.get("unmatched", 0), lookups=pol.get("lookups", 0),
                     touches=pol.get("touches", 0))
            for cn in CACHES:
                a = caches.get(cn)
                if not a:
                    continue
                k = cn.split("_")[0].lower()
                r[f"{k}_fills"] = a["fills"]
                r[f"{k}_removals"] = a["evictions"] + a["invalidations"]
                r[f"{k}_zero_reuse"] = a["zero_reuse_removals"]
                r[f"{k}_live"] = a["live_time"]
                r[f"{k}_dead"] = a["dead_time"]
                r[f"{k}_end_live"] = a["end_live_time"]
                r[f"{k}_end_unres"] = a["end_resident_time"] - a["end_live_time"]
                r[f"{k}_sets_used"] = a["sets_used"]
                r[f"{k}_num_sets"] = a["num_sets"]
            rows.append(r)
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 999)
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    # ---------------- aggregation: only units complete in every config (paired design)
    by_unit = defaultdict(dict)
    for r in rows:
        by_unit[(r["task"], r["cid"])][r["config"]] = r
    complete = {k: v for k, v in by_unit.items() if all(c in v for c in CONFIGS)}
    tasks = sorted({k[0] for k in complete})
    phases = ["harness start-up", "env setup", "harness session", "tool exec"]

    def arrays(sel):
        ks = [k for k, v in complete.items() if sel(v["lru"])]
        strata = np.array([hash((complete[k]["lru"]["task"], complete[k]["lru"]["phase"])) for k in ks])
        f = np.array([complete[k]["lru"]["weight"] / complete[k]["lru"]["pi"] for k in ks])
        cyc = {c: np.array([complete[k][c]["cycles"] for k in ks], float) for c in CONFIGS}
        ins = {c: np.array([complete[k][c]["instrs"] for k in ks], float) for c in CONFIGS}
        miss = {c: np.array([complete[k][c]["llc_demand_miss"] for k in ks], float) for c in CONFIGS}
        return ks, strata, f, cyc, ins, miss

    def estimate(sel, reps=2000):
        ks, strata, f, cyc, ins, miss = arrays(sel)
        if not ks:
            return None
        res = {"units": len(ks)}
        idx_by_s = [np.where(strata == s)[0] for s in np.unique(strata)]
        boots = [np.concatenate([RNG.choice(ix, len(ix)) for ix in idx_by_s]) for _ in range(reps)]
        for c in CONFIGS:
            ipc = (f * ins[c]).sum() / (f * cyc[c]).sum()
            sp = (f * cyc["lru"]).sum() / (f * cyc[c]).sum()
            mpki = 1000 * (f * miss[c]).sum() / (f * ins[c]).sum()
            b_ipc = np.array([(f[b] * ins[c][b]).sum() / (f[b] * cyc[c][b]).sum() for b in boots])
            b_sp = np.array([(f[b] * cyc["lru"][b]).sum() / (f[b] * cyc[c][b]).sum() for b in boots])
            res[c] = dict(ipc=ipc, ipc_lo=np.percentile(b_ipc, 2.5), ipc_hi=np.percentile(b_ipc, 97.5),
                          speedup=sp, sp_lo=np.percentile(b_sp, 2.5), sp_hi=np.percentile(b_sp, 97.5),
                          llc_mpki=mpki,
                          units_faster=int((cyc[c] < cyc["lru"]).sum()),
                          units_slower=int((cyc[c] > cyc["lru"]).sum()),
                          units_identical=int((cyc[c] == cyc["lru"]).sum()))
        return res

    agg = {"all": estimate(lambda r: True)}
    for t in tasks:
        agg[t] = estimate(lambda r, t=t: r["task"] == t)
    for p in phases:
        agg[p] = estimate(lambda r, p=p: r["phase"] == p)
    for t in tasks:
        for p in phases:
            agg[f"{t} | {p}"] = estimate(lambda r, t=t, p=p: r["task"] == t and r["phase"] == p, reps=200)

    # ---------------- dead state under LRU, HT-weighted capacity-time
    dead = {}
    for scope, sel in [("all", lambda r: True)] + [(p, (lambda r, p=p: r["phase"] == p)) for p in phases]:
        d = {}
        for cn in CACHES:
            k = cn.split("_")[0].lower()
            live = dd = el = eu = fills = zr = rem = 0.0
            for v in complete.values():
                r = v["lru"]
                if not sel(r) or f"{k}_live" not in r:
                    continue
                f = r["weight"] / r["pi"]
                live += f * r[f"{k}_live"]
                dd += f * r[f"{k}_dead"]
                el += f * r[f"{k}_end_live"]
                eu += f * r[f"{k}_end_unres"]
                fills += f * r[f"{k}_fills"]
                zr += f * r[f"{k}_zero_reuse"]
                rem += f * r[f"{k}_removals"]
            tot = live + dd + el + eu
            if tot:
                d[cn] = dict(dead_capacity_time_lo=dd / tot, dead_capacity_time_hi=(dd + eu) / tot,
                             dead_capacity_time_removed_only=dd / (live + dd) if live + dd else None,
                             dead_on_arrival_of_removed=zr / rem if rem else None, fills=fills)
        dead[scope] = d

    sanity = {
        "units_selected": len(units), "units_complete": len(complete), "missing_runs": missing,
        "oracle_identical_to_lru_units": sum(v["oracle"]["cycles"] == v["lru"]["cycles"] for v in complete.values()),
        "pass2_unmatched_frac": {c: sum(v[c]["unmatched"] for v in complete.values()) /
                                 max(1, sum(v[c]["lookups"] for v in complete.values()))
                                 for c in ["oracle", "oracle_byp", "never_byp", "min"]},
        "llc_sets_used_max": max(v["lru"].get("l1_sets_used", 0) for v in complete.values()),
        "mlc_sets_used_max": max(v["lru"].get("mlc_sets_used", 0) for v in complete.values()),
    }
    json.dump(dict(aggregate=agg, dead_state_lru=dead, sanity=sanity), open(out / "summary.json", "w"),
              indent=1, default=float)
    print(json.dumps(sanity, indent=1, default=float))
    for k in ["all"] + tasks + phases:
        a = agg.get(k)
        if not a:
            continue
        print(f"{k:28s} n={a['units']:3d} " + "  ".join(
            f"{c}:{a[c]['ipc']:.3f}({100*(a[c]['speedup']-1):+.2f}%)" for c in CONFIGS))


if __name__ == "__main__":
    main()
