#!/usr/bin/env python3
"""Simulate every selected unit under every LLC policy. Resumable: a config whose
rc file says 0 is skipped.

Per unit:   lru (pass 1, writes the LLC touch log)   mj (Mockingjay)
            -> dbx_table.py  -> oracle | oracle_byp | never_byp | min   (pass 2)

  run_sims.py <units.tsv> <out_root> [--jobs N]
Run with trace_env.sh sourced (LD_LIBRARY_PATH for Scarab's DynamoRIO reader).
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

D = Path("/localdisk/deepanjm/deadblock")
SCARAB = D / "scarab/src/build/opt/scarab"
PARAMS = D / "PARAMS.study"
PY = D / "tools-venv/bin/python"
TABLE = Path("/home/deepanjm/deadblock-src/dbx_table.py")

PASS2 = {
    "oracle": ["--dbx_policy=2"],
    "oracle_byp": ["--dbx_policy=2", "--dbx_oracle_bypass=1"],
    "never_byp": ["--dbx_policy=4", "--dbx_oracle_bypass=1"],
    "min": ["--dbx_policy=3", "--dbx_min_bypass=1"],
}


def done(d):
    try:
        return (d / "rc").read_text().strip() == "0"
    except OSError:
        return False


def scarab_cmd(u, d, extra):
    cmd = [str(SCARAB), "--frontend", "memtrace", f"--cbp_trace_r0={u['zip']}", "--dbx_cache=L1_CACHE",
           f"--dbx_stat_out={d}/dbx.stat.out"]
    if int(u["warmup"]):
        cmd.append(f"--full_warmup={u['warmup']}")
    return cmd + extra


def launch(cmd, d):
    d.mkdir(parents=True, exist_ok=True)
    (d / "PARAMS.in").write_bytes(PARAMS.read_bytes())
    sh = f"cd {d} && {' '.join(cmd)} > sim.log 2>&1; echo $? > rc"
    return subprocess.Popen(["bash", "-c", sh])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=96)
    a = ap.parse_args()
    units = list(csv.DictReader(open(a.units), delimiter="\t"))
    root = Path(a.out)

    # job = (name, dir, argv-or-callable, prerequisite dir or None)
    jobs = []
    for u in units:
        ud = root / u["task"] / u["cid"]
        lru = ud / "lru"
        jobs.append(("lru", lru, scarab_cmd(u, lru, [f"--dbx_policy=0", f"--dbx_log_out={lru}/touch.log"]), None))
        jobs.append(("mj", ud / "mj", scarab_cmd(u, ud / "mj", ["--dbx_policy=1"]), None))
        jobs.append(("table", ud / "table",
                     [str(PY), str(TABLE), f"{lru}/touch.log", f"{ud}/table/table.bin", f"{ud}/table/table.json"], lru))
        for name, extra in PASS2.items():
            jobs.append((name, ud / name, scarab_cmd(u, ud / name, extra + [f"--dbx_table_in={ud}/table/table.bin"]),
                         ud / "table"))

    pending = [j for j in jobs if not done(j[1])]
    running = {}
    failed = set()
    t0 = time.time()
    total = len(pending)
    print(f"{len(units)} units, {len(jobs)} jobs, {total} to run, {a.jobs} slots", flush=True)
    while pending or running:
        for p, j in list(running.items()):
            if p.poll() is not None:
                del running[p]
                if not done(j[1]):
                    failed.add(j[1])
                    print(f"FAIL {j[1]}", flush=True)
        progressed = True
        while len(running) < a.jobs and progressed:
            progressed = False
            for i, j in enumerate(pending):
                name, d, cmd, pre = j
                if pre is not None and not done(pre):
                    if pre in failed or any(f in failed for f in [pre.parent / "lru"]):
                        pending.pop(i)
                        failed.add(d)
                        print(f"SKIP {d} (prerequisite failed)", flush=True)
                        progressed = True
                        break
                    continue
                pending.pop(i)
                running[launch(cmd, d)] = j
                progressed = True
                break
        n_done = total - len(pending) - len(running)
        if int(time.time() - t0) % 300 < 5:
            print(f"[{time.time()-t0:7.0f}s] done {n_done}/{total} running {len(running)} failed {len(failed)}",
                  flush=True)
        time.sleep(5)
    print(f"finished: {total - len(failed)} ok, {len(failed)} failed", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
