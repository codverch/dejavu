#!/usr/bin/env python3
"""Footprint of each simulated unit, from its spf record: distinct instruction lines, and data lines
split into file-backed (inside a mapped file: the same place in every process, so predictable from
history after rebasing) and private (heap, stack, anonymous: new addresses in every process).

  records_summary.py <dir> <record suffix>     e.g.  w9 ""   or   w8 __self
reads <dir>/selection.csv (uid, trace_zip) and <dir>/records/<uid><suffix>.bin; -> <dir>/footprint.csv
"""
import csv, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from rebase import REC, bases  # noqa: E402

d, suf = Path(sys.argv[1]), sys.argv[2]
rows = []
for u in csv.DictReader(open(d / "selection.csv")):
    f = d / "records" / f"{u['uid']}{suf}.bin"
    if not f.exists():
        continue
    r = np.fromfile(f, dtype=REC)
    _, segs = bases(str(Path(u["trace_zip"]).parent.parent / "raw" / "modules.log"))
    starts = np.array([s[0] for s in segs], np.uint64); ends = np.array([s[1] for s in segs], np.uint64)
    addr = r["line"] & ~np.uint64(63); inst = (r["line"] & np.uint64(1)) == 1
    i = np.searchsorted(starts, addr, side="right") - 1
    filed = (i >= 0) & (addr < ends[np.maximum(i, 0)])
    rows.append(dict(uid=u["uid"], lines=len(r), i_lines=int(inst.sum()), d_file=int((~inst & filed).sum()),
                     d_private=int((~inst & ~filed).sum()), d_written=int(((r["line"] & np.uint64(2)) != 0).sum())))
with open(d / "footprint.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "records")
