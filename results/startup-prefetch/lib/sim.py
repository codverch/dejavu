"""Run one Scarab simulation and read its counters.

A package is a directory with scarab, lib/ and PARAMS.* (scripts/build_scarab.sh makes them).
Every run gets its own directory; the stat files are parsed into one dict and deleted, the
simulator log is kept. Counters come from the final dump (cumulative over the whole run).
"""
from __future__ import annotations
import gzip, json, os, re, shutil, subprocess
from pathlib import Path

FIN = re.compile(r"Core 0 Finished:\s+insts:(\d+)\s+cycles:(\d+)")
ROW = re.compile(r"^([A-Z][A-Z0-9_]*)\s+(-?\d+)\s", re.M)
STAT = ("core", "memory", "bp", "fetch", "pref")


def run(pkg: str, trace: str, out: Path, args: list[str], params: str = "PARAMS.golden_cove",
        inst_limit: int = 1_000_000_000, keep_stats: bool = False) -> dict:
    """-> {ok, insts, cycles, stats: {counter: value}, spf: '...' line or ''}; cached in out/result.json.gz"""
    res_f = out / "result.json.gz"
    if res_f.exists():
        return json.load(gzip.open(res_f, "rt"))
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    shutil.copy(Path(pkg) / params, out / "PARAMS.in")
    cmd = [str(Path(pkg) / "scarab"), "--frontend", "memtrace", f"--cbp_trace_r0={trace}",
           f"--inst_limit={inst_limit}", "--full_warmup=0", "--use_fetched_count=0", *args]
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True,
                       env=dict(os.environ, LD_LIBRARY_PATH=str(Path(pkg) / "lib")))
    (out / "sim.log").write_text(r.stdout[-20000:] + r.stderr[-5000:])
    m = FIN.search(r.stdout)
    ok = r.returncode == 0 and m is not None and "ASSERT" not in r.stdout
    stats = {}
    for s in STAT:
        f = out / f"{s}.stat.0.out"
        if f.exists():
            for k, v in ROW.findall(f.read_text(errors="replace")):
                stats.setdefault(k, int(v))
    spf = re.search(r"SPF (record|replay): .*", r.stdout)
    res = dict(ok=ok, rc=r.returncode, insts=int(m.group(1)) if m else None, cycles=int(m.group(2)) if m else None,
               spf=spf.group(0) if spf else "", stats=stats, args=args, params=params, trace=trace)
    if not keep_stats:
        for p in out.iterdir():
            if p.name not in ("sim.log", "PARAMS.in"):
                p.unlink() if p.is_file() else shutil.rmtree(p)
    json.dump(res, gzip.open(res_f, "wt"))
    return res


def spf_fields(line: str) -> dict:
    return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
