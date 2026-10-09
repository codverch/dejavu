#!/usr/bin/env python3
"""Methodology-audit simulations for the dead-state paper. Same dbx Scarab binary and PARAMS.study as
the LLC study (run_sims.py); resumable (a config whose rc file says 0 is skipped).

Per agent unit (units_a.tsv, 160 PPS units, same warm-up as the study):
  dlog / mlog     LRU, two-pass log at the L1-D / L2      -> dtable / mtable (dbx_table.py)
  dmin / mmin     Belady MIN at the L1-D / L2 (no bypass: dbx bypass exists only on the LLC fill path)
  dnever / mnever evict never-reused-again blocks first, LRU otherwise
  l1i2x l1d2x l22x  LRU with 2x capacity (sets doubled, associativity kept)
  nopref          LRU with the prefetch framework off
  perfi perfd     perfect L1-I / perfect L1-D (ceilings)
  agent20         LRU, 10M warm-up + 10M measured from the unit's start (matches the baselines' window)
Baselines (taxonomy jobs, warm mode only): LRU, 10M warm-up + 10M measured on the simpoint/self traces.

  audit_sims.py <units.tsv> <out_root> [--jobs N] [--only cfg,cfg] [--smoke]
"""
import argparse, csv, json, subprocess, sys, time
from pathlib import Path

D = Path("/localdisk/deepanjm/deadblock")
SCARAB = D / "scarab/src/build/opt/scarab"
PARAMS = D / "PARAMS.study"
PY = D / "tools-venv/bin/python"
TABLE = Path("/home/deepanjm/deadblock-src/dbx_table.py")
TAX = Path("/localdisk/deepanjm/isca-traces/taxonomy")
SEG = 10_000_000

LRU_VARIANTS = {"l1i2x": ["--icache_size=65536"], "l1d2x": ["--dcache_size=98304"], "l22x": ["--mlc_size=4194304"],
                "nopref": ["--pref_framework_on=0"], "perfi": ["--perfect_icache=1"], "perfd": ["--perfect_dcache=1"]}
ORACLE = {"min": "3", "never": "4"}
CACHE = {"d": "DCACHE", "m": "MLC_CACHE"}


def done(d):
    try:
        return (d / "rc").read_text().strip() == "0"
    except OSError:
        return False


def sim(trace, d, extra, warm, smoke):
    cmd = [str(SCARAB), "--frontend", "memtrace", f"--cbp_trace_r0={trace}", f"--dbx_stat_out={d}/dbx.stat.out"]
    if smoke:
        return cmd + ["--inst_limit=3000000"] + extra
    return cmd + warm + extra


def jobs_for_unit(u, root, smoke):
    ud = root / u["task"] / u["cid"]
    warm = [f"--full_warmup={u['warmup']}"] if int(u["warmup"]) else []
    J = []
    for c, name in CACHE.items():
        log = ud / f"{c}log"
        J.append((f"{c}log", log, sim(u["zip"], log, [f"--dbx_cache={name}", "--dbx_policy=0",
                                                         f"--dbx_log_out={log}/touch.log"], warm, smoke), None))
        tab = ud / f"{c}table"
        J.append((f"{c}table", tab, ["bash", "-c", f"{PY} {TABLE} {log}/touch.log {tab}/table.bin {tab}/table.json"
                                     f" && rm -f {log}/touch.log"], log))
        for o, pol in ORACLE.items():
            od = ud / f"{c}{o}"
            J.append((f"{c}{o}", od, sim(u["zip"], od, [f"--dbx_cache={name}", f"--dbx_policy={pol}",
                                                          "--dbx_min_bypass=0", f"--dbx_table_in={tab}/table.bin"],
                                         warm, smoke), tab))
    for v, extra in LRU_VARIANTS.items():
        J.append((v, ud / v, sim(u["zip"], ud / v, extra, warm, smoke), None))
    J.append(("agent20", ud / "agent20", sim(u["zip"], ud / "agent20", [], [f"--full_warmup={SEG}",
                                                                            f"--inst_limit={2 * SEG}"], smoke), None))
    return J


def baseline_jobs(root, smoke):
    J = []
    for f in ("jobs_simp.json", "jobs_self_redis_memcached_node_gap_bfs_gap_pr.json"):
        for j in json.load(open(TAX / f)):
            if j["mode"] != "warm":
                continue
            b = j.get("roi_begin", SEG + 1)
            d = root / "base" / j["job"]
            warm = [f"--memtrace_roi_begin={b}", f"--memtrace_roi_end={b + 2 * SEG - 1}", f"--full_warmup={SEG}",
                    f"--inst_limit={2 * SEG}", "--use_fetched_count=0"]
            J.append(("base", d, sim(j["trace"], d, [], warm, smoke), None))
            (d.parent).mkdir(parents=True, exist_ok=True)
            json.dump(j, open(root / "base" / f"{j['job']}.json", "w"))
    return J


def launch(cmd, d):
    d.mkdir(parents=True, exist_ok=True)
    if cmd[0] == str(SCARAB):
        (d / "PARAMS.in").write_bytes(PARAMS.read_bytes())
        sh = f"cd {d} && {' '.join(cmd)} > sim.log 2>&1; echo $? > rc"
    else:
        sh = f"cd {d} && {' '.join(cmd[2:]) if cmd[:2] == ['bash', '-c'] else ' '.join(cmd)} > run.log 2>&1; echo $? > rc"
    return subprocess.Popen(["bash", "-c", sh])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units"); ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=160); ap.add_argument("--only"); ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    root = Path(a.out)
    units = list(csv.DictReader(open(a.units), delimiter="\t"))
    if a.smoke:
        units = units[:1]
    jobs = baseline_jobs(root, a.smoke) if not a.smoke else baseline_jobs(root, True)[:1]
    for u in units:
        jobs += jobs_for_unit(u, root, a.smoke)
    if a.only:
        keep = set(a.only.split(","))
        jobs = [j for j in jobs if j[0] in keep or (j[0].endswith("table") and j[0][0] + "table" in keep)]
    pending = [j for j in jobs if not done(j[1])]
    running, failed, t0, total = {}, set(), time.time(), len(pending)
    print(f"{len(units)} units, {len(jobs)} jobs, {total} to run, {a.jobs} slots", flush=True)
    last = 0
    while pending or running:
        for p, j in list(running.items()):
            if p.poll() is not None:
                del running[p]
                if not done(j[1]):
                    failed.add(j[1]); print(f"FAIL {j[1]}", flush=True)
        i = 0
        while len(running) < a.jobs and i < len(pending):
            name, d, cmd, pre = pending[i]
            if pre is not None and not done(pre):
                if pre in failed:
                    pending.pop(i); failed.add(d); print(f"SKIP {d}", flush=True); continue
                i += 1; continue
            pending.pop(i); running[launch(cmd, d)] = (name, d, cmd, pre)
        if time.time() - last > 300:
            last = time.time()
            print(f"[{time.time() - t0:7.0f}s] done {total - len(pending) - len(running)}/{total} running {len(running)} "
                  f"failed {len(failed)}", flush=True)
        time.sleep(5)
    print(f"finished: {total - len(failed)} ok, {len(failed)} failed", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
