#!/usr/bin/env python3
"""Check that two Scarab builds produce bit-identical statistics on the same traces.

  check_identical.py <pkg A> <pkg B> <out dir> <trace.zip> [<trace.zip> ...] [-- extra scarab args]

Runs both packages (directories holding scarab, lib/, PARAMS.golden_cove) cold on every trace and
compares every counter of every stat file, except SIM_HOST_* (host wall-clock time). Exits 1 on any difference and prints the first few.
Used to show that an added feature, switched off, changes nothing.
"""
import os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROW = re.compile(r"^([A-Z][A-Z0-9_]*)\s+(-?[\d.]+)", re.M)


def run(pkg, trace, out, extra):
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(pkg) / "PARAMS.golden_cove", out / "PARAMS.in")
    r = subprocess.run([str(Path(pkg) / "scarab"), "--frontend", "memtrace", f"--cbp_trace_r0={trace}",
                        "--inst_limit=100000000", "--full_warmup=0", "--use_fetched_count=0", *extra],
                       cwd=out, capture_output=True, text=True, env=dict(os.environ, LD_LIBRARY_PATH=str(Path(pkg) / "lib")))
    stats = {}
    for f in sorted(out.glob("*.stat.0.out")):
        for k, v in ROW.findall(f.read_text()):
            stats[f"{f.name}:{k}"] = v
    return r.returncode, stats


def main():
    args = sys.argv[1:]
    extra = args[args.index("--") + 1:] if "--" in args else []
    args = args[:args.index("--")] if "--" in args else args
    a, b, out, traces = str(Path(args[0]).resolve()), str(Path(args[1]).resolve()), Path(args[2]).resolve(), args[3:]
    def one(i_t):
        i, t = i_t
        ra, sa = run(a, t, out / f"{i}_A", extra)
        rb, sb = run(b, t, out / f"{i}_B", extra)
        # SIM_HOST_* is the simulator's own wall-clock time on the host, not a simulated quantity
        diff = [k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k) and ":SIM_HOST_" not in k]
        return t, ra, rb, len(sa), diff
    bad = 0
    with ThreadPoolExecutor(len(traces)) as ex:
        for t, ra, rb, n, diff in ex.map(one, enumerate(traces)):
            ok = ra == 0 and rb == 0 and n > 0 and not diff
            bad += not ok
            print(f"{'IDENTICAL' if ok else 'DIFFERENT'} rc={ra}/{rb} counters={n} differing={len(diff)} {t}"
                  + (f" e.g. {sorted(diff)[:3]}" if diff else ""), flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
