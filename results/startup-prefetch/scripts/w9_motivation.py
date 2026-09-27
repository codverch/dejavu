#!/usr/bin/env python3
"""W9: motivation characterization of every phase of an agent run, in the manner of the SAFARI
papers (Pythia MICRO'21, Hermes MICRO'22, Constable ISCA'24): where time goes, where loads are
served, what the existing prefetchers do, and what each cache level is worth, per phase.

  w9_motivation.py <out dir> --pkg <ideal-prefetching package> <task>=<DR run dir> ... [--jobs N]

Units. Per task and phase, two units, fixed before any simulation: the candidates at 1/3 and 2/3 of
the task's run (by start time), so the pair spans the run. A unit is one thread's window, >= 1M
instructions, of:
  harness start-up, harness: agent loop, harness exit   harness main thread, any window
  environment setup                                     a Python process's first window
  tool execution: python                                a Python process a tool call created, first window
  tool execution: shell                                 a bash a tool call created, first window
The region is the unit's first min(instrs, 100M) instructions. Scarab asserts on some instructions
it cannot decode (OP_INV); such a unit is simulated up to 100K instructions before the assertion,
for every configuration (limits.csv).

Configurations (PARAMS.golden_cove, cold): base; no_dpref (golden_cove's L1-D stream prefetcher
off; the L1-I FDIP stays); perfect_{l1i,l1d,l2,llc,all}; l1d_2x; record (spf_mode 1: the region's
distinct lines, i.e. its footprint; its cycles must equal base).

Outputs: selection.csv, limits.csv, results.csv (every counter needed by figs_w9.py), checks.csv.
"""
import argparse, csv, gzip, json, re, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sim  # noqa: E402

CAP = 100_000_000
PHASES = ["harness start-up", "environment setup", "tool execution: python", "tool execution: shell",
          "harness: agent loop", "harness exit"]
CFGS = {
    "base": [],
    "no_dpref": ["--pref_framework_on", "0"],
    "perfect_l1i": ["--perfect_icache", "1"],
    "perfect_l1d": ["--perfect_dcache", "1"],
    "perfect_l2": ["--perfect_mlc", "1"],
    "perfect_llc": ["--perfect_l1", "1"],
    "perfect_all": ["--perfect_icache", "1", "--perfect_dcache", "1", "--perfect_mlc", "1", "--perfect_l1", "1"],
    "l1d_2x": ["--dcache_size", "98304"],
}
# Scarab names: "MLC" is the L2, "L1" is the LLC
KEEP = re.compile(r"^(LD_SERVED_|LD_LAT_|INST_LOST_|DCACHE_(MISS|HIT)(_LD|_ST)?_ONPATH$|ICACHE_MISS_ONPATH$|"
                  r"MLC_MISS_ONPATH$|L1_MISS_ONPATH$|L1_MISS_ALL$|L1_PREF_(FILL|HIT|LATE|REQ_MISS)$|"
                  r"BUS_(DEMAND|PREF)_ACCESS$|EXEC_ON_PATH_INST(_MEM)?$|FULL_WINDOW_(STALL|MEM_OP)$|"
                  r"BP_ON_PATH_(CORRECT|MISPREDICT)$|ICACHE_MISS_NOT_PREFETCHED_ONPATH$|"
                  r"ICACHE_MISS_MSHR_HIT_PREFETCHED_ONPATH$)")
INV = re.compile(r"ASSERT FAILED \(P=\d+\s+O=\d+\s+I=(\d+).*OP_INV")


def phase_of(r):
    main, w0 = r["tid"] == r["pid"], r["window"] == "0"
    if r["is_harness"] == "1":
        return r["phase"] if main and r["phase"] in ("harness start-up", "harness: agent loop", "harness exit") else None
    if not (w0 and main):
        return None
    py = r["comm"].startswith("python")
    if r["phase"] == "environment setup" and py:
        return "environment setup"
    if r["phase"] == "tool execution" and py:
        return "tool execution: python"
    if r["phase"] == "tool execution" and r["comm"] == "bash":
        return "tool execution: shell"
    return None


def select(task, run):
    cand = {p: [] for p in PHASES}
    for r in csv.DictReader(open(Path(run) / "attribution" / "windows.csv")):
        p = phase_of(r)
        if p and int(r["instrs"]) >= 1_000_000:
            cand[p].append(r)
    out = []
    for p in PHASES:
        c = sorted(cand[p], key=lambda r: float(r["t_start"]))
        for i in sorted({round(q * (len(c) - 1)) for q in (1 / 3, 2 / 3)}) if c else []:
            u = c[i]
            out.append(dict(u, task=task, unit_phase=p, candidates=len(c),
                            uid=f"{task.split('__')[1].rsplit('-', 1)[0]}-{u['cid']}"))
    return out


def run1(j):
    uid, trace, cfg, n, pkg, out, rec = j
    args = ["--spf_mode", "1", "--spf_file", rec, "--spf_region_instrs", str(n)] if cfg == "record" else CFGS[cfg]
    r = sim.run(pkg, trace, Path(out) / "runs" / f"{uid}__{cfg}", args, inst_limit=n)
    log = (Path(out) / "runs" / f"{uid}__{cfg}" / "sim.log").read_text(errors="replace")
    m = INV.search(log)
    row = dict(uid=uid, config=cfg, ok=int(r["ok"]), insts=r["insts"], cycles=r["cycles"], inv_at=m.group(1) if m else "")
    row.update({k: v for k, v in r["stats"].items() if KEEP.match(k)})
    row.update({f"spf_{k}": v for k, v in sim.spf_fields(r["spf"]).items()})
    return row


def pool(jobs, n):
    with ProcessPoolExecutor(n) as ex:
        return list(ex.map(run1, jobs, chunksize=1))


def write(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("runs", nargs="+", metavar="task=run_dir")
    ap.add_argument("--pkg", required=True); ap.add_argument("--jobs", type=int, default=110); a = ap.parse_args()
    out = Path(a.out).resolve(); (out / "records").mkdir(parents=True, exist_ok=True)
    units = [u for x in a.runs for u in select(*x.split("=", 1))]
    write(out / "selection.csv", [{k: u[k] for k in ("uid", "task", "unit_phase", "cid", "comm", "window", "step",
                                                    "instrs", "candidates", "tool_command", "trace_zip")} for u in units])
    rec = lambda u: str(out / "records" / f"{u}.bin")  # noqa: E731
    n = {u["uid"]: min(int(u["instrs"]), CAP) for u in units}
    tr = {u["uid"]: u["trace_zip"] for u in units}
    # base first: it finds the units Scarab cannot finish, which are then cut short for every config
    base = pool([(u, tr[u], "base", n[u], a.pkg, str(out), rec(u)) for u in n], a.jobs)
    lim = []
    for b in base:
        if not b["ok"] and b["inv_at"]:
            new = int(b["inv_at"]) - 100_000
            lim.append(dict(uid=b["uid"], planned=n[b["uid"]], simulated=new, reason="OP_INV at " + b["inv_at"]))
            n[b["uid"]] = new
            d = out / "runs" / f"{b['uid']}__base"
            (d / "result.json.gz").unlink(missing_ok=True)
    write(out / "limits.csv", lim or [dict(uid="", planned="", simulated="", reason="")])
    cut = {x["uid"] for x in lim}
    jobs = [(u, tr[u], c, n[u], a.pkg, str(out), rec(u)) for u in n for c in list(CFGS) + ["record"]
            if c != "base" or u in cut]
    rows = [b for b in base if b["uid"] not in cut] + pool(sorted(jobs, key=lambda j: -j[3]), a.jobs)
    by = {(r["uid"], r["config"]): r for r in rows}
    checks = [dict(check="record cycles == base cycles", uid=u,
                   ok=int(by[(u, "record")]["ok"] == 1 and by[(u, "record")]["cycles"] == by[(u, "base")]["cycles"]))
              for u in n]
    meta = {u["uid"]: u for u in units}
    for r in rows:
        r["task"], r["phase"] = meta[r["uid"]]["task"], meta[r["uid"]]["unit_phase"]
    write(out / "results.csv", rows); write(out / "checks.csv", checks)
    print(f"{len(units)} units; {sum(c['ok'] for c in checks)}/{len(checks)} record==base; "
          f"{sum(r['ok'] for r in rows)}/{len(rows)} runs ok; {len(lim)} truncated", flush=True)


if __name__ == "__main__":
    main()
