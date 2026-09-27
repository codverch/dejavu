#!/usr/bin/env python3
"""Run a list of native SWE-agent runs, each pinned to 4 idle physical cores (+ SMT siblings).

  native_batch.py --out <root> --runs task:run_id[,task:run_id...] [--parallel K] [--cores LO-HI]

--cores restricts the physical cores runs may use (default 8-95), leaving the rest for simulation
and trace conversion, which then must be pinned there.

A core set is used only if all 8 logical CPUs were <5% busy over 5 s just before the run
(measured, written to <run>/cpu_idle.json). With none idle, the run waits. Runs share vLLM, which
changes model latency but not CPU-side instruction counts or the prediction lead time.
"""
import argparse, json, os, subprocess, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NCPU = 128                      # physical cores 0-127; sibling of c is c+128
lock = threading.Lock(); taken = set()


def busy(sec=5.0):
    def rd():
        d = {}
        for l in open("/proc/stat"):
            if l.startswith("cpu") and l[3].isdigit():
                f = l.split(); d[int(f[0][3:])] = list(map(int, f[1:]))
        return d
    a = rd(); time.sleep(sec); b = rd()
    return {c: 1 - ((b[c][3] + b[c][4]) - (a[c][3] + a[c][4])) / max(sum(b[c]) - sum(a[c]), 1) for c in a}


def pick(lo, hi):
    while True:
        u = busy()
        with lock:
            for base in range(lo - lo % 4, hi + 1, 4):   # 4-core groups inside one CCX
                if base < lo or base + 3 > hi:
                    continue
                cores = list(range(base, base + 4))
                cpus = cores + [c + 128 for c in cores]
                if not (set(cpus) & taken) and all(u.get(c, 1) < 0.05 for c in cpus):
                    taken.update(cpus)
                    return cpus, {c: round(u[c], 4) for c in cpus}
        time.sleep(20)


def one(task, rid, out, lo, hi):
    cpus, idle = pick(lo, hi)
    rd = Path(out) / task / rid
    try:
        env = dict(os.environ, IID=task, RUN_ID=rid, CPUS=",".join(map(str, cpus)), OUT=out)
        r = subprocess.run(["bash", str(HERE / "native_run.sh")], env=env, capture_output=True, text=True)
        rd.mkdir(parents=True, exist_ok=True)
        json.dump({"cpus": cpus, "busy_before": idle}, open(rd / "cpu_idle.json", "w"))
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else f"{task} {rid} rc={r.returncode} {r.stderr[-300:]}", flush=True)
    finally:
        with lock:
            taken.difference_update(cpus)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--runs", required=True)
    ap.add_argument("--parallel", type=int, default=1); ap.add_argument("--cores", default="8-95"); a = ap.parse_args()
    lo, hi = map(int, a.cores.split("-"))
    jobs = [r.split(":") for r in a.runs.split(",")]
    ths = []
    for task, rid in jobs:
        while sum(t.is_alive() for t in ths) >= a.parallel:
            time.sleep(5)
        t = threading.Thread(target=one, args=(task, rid, a.out, lo, hi)); t.start(); ths.append(t); time.sleep(30)
    for t in ths:
        t.join()
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
