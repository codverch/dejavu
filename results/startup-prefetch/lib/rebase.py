"""Move a start-up record from one process's address space into another's.

A record (prefetcher/startup_pf.c) is a list of (line | flags, first-use index) in the virtual
addresses of the process that was recorded. Under ASLR the next process maps the same files at
different bases, so a line inside a mapped file moves by that file's base difference, while heap,
stack and anonymous lines have no counterpart that can be known in advance and are dropped.
"""
from __future__ import annotations
import re

import numpy as np

REC = np.dtype([("line", "<u8"), ("idx", "<u8")])


def bases(modlog: str) -> tuple[dict, list]:
    """-> {path: load base}, [(start, end, path)] from a DynamoRIO modules.log"""
    base, segs = {}, []
    for line in open(modlog, errors="replace"):
        f = [x.strip() for x in line.split(",")]
        if len(f) < 9 or not f[0].isdigit():
            continue
        start, end, path = int(f[2], 16), int(f[3], 16), f[-1]
        if not path.startswith("/") or "dynamorio" in path.lower() or "drmemtrace" in path:
            continue
        pref = int(f[6], 16)
        base.setdefault(path, start - pref)          # start - link-time address of the segment
        segs.append((start, end, path))
    segs.sort()
    return base, segs


def rebase(rec: np.ndarray, modlog_from: str, modlog_to: str) -> tuple[np.ndarray, dict]:
    bf, segs = bases(modlog_from)
    bt, _ = bases(modlog_to)
    starts = np.array([s[0] for s in segs], np.uint64); ends = np.array([s[1] for s in segs], np.uint64)
    paths = [s[2] for s in segs]
    addr = rec["line"] & ~np.uint64(63); flags = rec["line"] & np.uint64(63)
    i = np.searchsorted(starts, addr, side="right") - 1
    ok = (i >= 0) & (addr < ends[np.maximum(i, 0)])
    out, n_file, n_missing = [], 0, 0
    for k in np.nonzero(ok)[0]:
        p = paths[i[k]]
        if p not in bt:
            n_missing += 1; continue
        a = int(addr[k]) - bf[p] + bt[p]
        out.append((a | int(flags[k]), int(rec["idx"][k]))); n_file += 1
    res = np.array(out, dtype=REC)
    return res, dict(lines=len(rec), rebased=n_file, dropped_private=int((~ok).sum()), dropped_unmapped_file=n_missing)
