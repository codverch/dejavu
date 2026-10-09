#!/usr/bin/env python3
"""Pass-1 touch log (dbx_log_out) -> pass-2 table (dbx_table_in).

For every touch (blk, k) of the target cache in pass 1 (LRU):
  dead = 1  if that touch was the block's last before it was evicted/invalidated
  next = global index (among touches) of the block's next touch, or 2^64-1

Blocks still resident at the end keep dead = 0: their future is unknown.

  dbx_table.py <log.bin> <table.bin> [summary.json]
"""
import json
import sys

import numpy as np

LOG = np.dtype([("blk", "<u8"), ("k", "<u4"), ("ev", "<u4")])
TAB = np.dtype([("blk", "<u8"), ("k", "<u4"), ("dead", "<u4"), ("next", "<u8")])
HIT, FILL, BYPASS, EVICT, INVAL = range(5)
INF = np.uint64(2**64 - 1)


def build(log_path, tab_path):
    rec = np.fromfile(log_path, dtype=LOG)
    is_touch = rec["ev"] <= BYPASS
    t = rec[is_touch]
    rem = rec[~is_touch]
    n = len(t)
    seq = np.arange(n, dtype=np.uint64)

    order = np.lexsort((t["k"], t["blk"]))
    blk, k, sq = t["blk"][order], t["k"][order], seq[order]

    # ordinals of each block must be exactly 0..m-1 in log order (every touch logged)
    first = np.r_[True, blk[1:] != blk[:-1]]
    start = np.maximum.accumulate(np.where(first, np.arange(n), 0))
    if n and not np.array_equal(k, (np.arange(n) - start).astype(np.uint32)):
        raise SystemExit("touch ordinals are not contiguous per block -- log is inconsistent")
    # ... and touches of one block appear in ordinal order in the log
    if n and not np.all(np.diff(sq.astype(np.int64))[~first[1:]] > 0):
        raise SystemExit("touch ordinals out of log order")

    nxt = np.full(n, INF, dtype=np.uint64)
    same = blk[1:] == blk[:-1]
    nxt[:-1][same] = sq[1:][same]

    dead = np.zeros(n, dtype=np.uint32)
    pos = np.searchsorted(blk, rem["blk"], side="left") + rem["k"].astype(np.int64)
    ok = (pos < n)
    ok[ok] &= (blk[pos[ok]] == rem["blk"][ok]) & (k[pos[ok]] == rem["k"][ok])
    if not ok.all():
        raise SystemExit(f"{(~ok).sum()} removals do not match a logged touch")
    if len(np.unique(pos)) != len(pos):
        raise SystemExit("a touch is the last touch of two removals")
    dead[pos] = 1

    out = np.empty(n, dtype=TAB)
    out["blk"], out["k"], out["dead"], out["next"] = blk, k, dead, nxt
    out.tofile(tab_path)
    ev = rec["ev"]
    return dict(touches=int(n), hits=int((ev == HIT).sum()), fills=int((ev == FILL).sum()),
                bypasses=int((ev == BYPASS).sum()), evictions=int((ev == EVICT).sum()),
                invalidations=int((ev == INVAL).sum()), dead_touches=int(dead.sum()),
                blocks=int(first.sum()), never_retouched=int((nxt == INF).sum()))


if __name__ == "__main__":
    s = build(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:
        json.dump(s, open(sys.argv[3], "w"), indent=1)
    print(json.dumps(s))
