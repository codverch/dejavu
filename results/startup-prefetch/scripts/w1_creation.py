#!/usr/bin/env python3
"""W1: what happens every time a tool call creates a Python process, and how often it is the same.

  w1_creation.py <DR run dir> <out dir> [--jobs N]

Input: a DR run post-processed by swe-bench-e2e/scripts/e2e_post.py (windows/, attribution/windows.csv).
Every Python process started inside a tool call (window 0, main thread) is analysed from its first
instruction. Its instruction stream is canonicalised (PC -> file + link-time address, so ASLR does
not hide identical code) and cut at exact symbol boundaries:

  loader         exec .. first instruction outside ld.so
  process init   .. Py_BytesMain / Py_RunMain
  interp. init   .. first PyRun_{AnyFile,SimpleFile,SimpleString}Flags
  tool code      .. Py_FinalizeEx
  teardown       .. end of process

The creation region is loader + process init + interpreter init. Each instruction is also given an
activity category (lib/categories.py), so the region is broken down by operation.

Outputs (out dir):
  creation.csv   one row per Python process: script, boundaries, per-operation instructions,
                 complete (region fully inside the traced window)
  pairs.csv      each creation vs the previous creation of the same script: exact common prefix,
                 share of the region's positions whose 32-instruction sequence also occurs in the
                 previous region, and the function where they first differ
  shells.csv     the non-Python processes of the same tool calls (sh -c, env, bash -n, ...)
"""
import argparse, csv, json, sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from canon import INSTR, Canon, entries, tool_class  # noqa: E402
from categories import CATS, RULES, category  # noqa: E402
from symbols import K, fn_of, kgrams, phases  # noqa: E402

OPS = ["loader", "proc_init", "rt_init", "work", "teardown"]


def load_seq(u):
    c = Canon()
    e = entries(u["trace_zip"])
    pcs = e["addr"][np.isin(e["type"], INSTR)]
    segs = c.segments(u["modlog"])
    return c.pcs(pcs, segs, int(u["pid"])), {v: k for k, v in c.fid.items()}


def one(u):
    cp, files = load_seq(u)
    b = phases(cp, files)
    n = len(cp)
    up, inv = np.unique(cp, return_inverse=True)
    ucat = np.zeros(len(up), np.int16); ufn = []
    for k, pc in enumerate(up.tolist()):
        if pc >= 1 << 63:
            ucat[k] = len(CATS) - 1; ufn.append("<private>"); continue
        p = files.get(pc >> 40, "?"); fn = fn_of(p, pc & ((1 << 40) - 1))
        ucat[k] = category(Path(p).name, fn); ufn.append(f"{Path(p).name}:{fn}")
    cat = ucat[inv]
    region_end = b["work"]
    row = dict(task=u["task"], cid=u["cid"], pid=u["pid"], script=u["script"], step=u["step"], t_start=u["t_start"],
               instrs_traced=n, window_full=int(n >= u["window_instrs"]), region_instrs=region_end,
               complete=int(region_end < n))
    edges = [b[p] for p in OPS] + [n]
    for i, p in enumerate(OPS):
        row[f"i_{p}"] = edges[i + 1] - edges[i]
    rc = np.bincount(cat[:region_end], minlength=len(CATS))
    for i, c in enumerate(CATS):
        row[f"cat_{c}"] = int(rc[i])
    return row, cp[:region_end], files, ufn, inv[:region_end]


def global_keys(cp, files, gfid):
    fid = (cp >> np.uint64(40)).astype(np.int64)
    priv = cp >= np.uint64(1 << 63)
    lut = np.zeros(max(files) + 1 if files else 1, np.uint64)
    for f, p in files.items():
        lut[f] = gfid[p]
    out = cp.copy()
    out[~priv] = (lut[fid[~priv]] << np.uint64(40)) | (cp[~priv] & np.uint64((1 << 40) - 1))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=32)
    ap.add_argument("--no-pairs", action="store_true", help="recompute creation.csv only; keep pairs.csv")
    a = ap.parse_args()
    run, out = Path(a.run), Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pol = json.load(open(run / "sampling_policy.json"))
    rows = list(csv.DictReader(open(run / "attribution" / "windows.csv")))
    py, shells = [], []
    for r in rows:
        if r["window"] != "0" or r["is_harness"] == "1" or r["tid"] != r["pid"] or r["phase"] != "tool execution":
            continue
        r["task"] = run.parent.name
        r["modlog"] = str(Path(r["trace_zip"]).parent.parent / "raw" / "modules.log")
        r["window_instrs"] = pol["window_instrs"]
        cls = tool_class(r["comm"], r["cmdline"], False)
        if r["comm"].startswith("python"):
            r["script"] = cls
            py.append(r)
        else:
            shells.append(dict(cid=r["cid"], pid=r["pid"], comm=r["comm"], cls=cls, step=r["step"], t_start=r["t_start"],
                               instrs=r["instrs"], tool_command=r["tool_command"][:160]))
    py.sort(key=lambda r: float(r["t_start"]))
    with ProcessPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, py, chunksize=1))
    gfid = {}
    for _, _, files, _, _ in res:
        for p in files.values():
            gfid.setdefault(p, len(gfid) + 1)
    crow, prow, last = [], [], {}
    for u, (row, reg, files, ufn, inv) in zip(py, res):
        crow.append(row)
        g = None if a.no_pairs else global_keys(reg, files, gfid)
        s = u["script"]
        if not a.no_pairs and s in last and row["complete"] and last[s][0]["complete"]:
            prev_row, pg = last[s]
            m = min(len(g), len(pg))
            neq = np.nonzero(g[:m] != pg[:m])[0]
            prefix = int(neq[0]) if len(neq) else m
            hb, ha = kgrams(g), kgrams(pg)
            ident = float(np.isin(hb, ha).mean()) if len(hb) else float("nan")
            div = ufn[inv[prefix]] if prefix < len(inv) else "(identical to the end)"
            prow.append(dict(script=s, cid_prev=prev_row["cid"], cid=row["cid"], step_prev=prev_row["step"], step=row["step"],
                             region_prev=len(pg), region=len(g), prefix=prefix, kgram_identity=round(ident, 6),
                             first_divergence=div))
        last[s] = (row, g)
    for name, data in (("creation.csv", crow), ("pairs.csv", [] if a.no_pairs else prow), ("shells.csv", shells)):
        if data:
            with open(out / name, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    print(f"{len(crow)} python creations ({sum(r['complete'] for r in crow)} complete), {len(prow)} pairs, "
          f"{len(shells)} other tool processes", flush=True)


if __name__ == "__main__":
    main()
