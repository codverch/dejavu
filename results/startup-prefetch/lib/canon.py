"""Trace reading and address canonicalisation shared by xproc.py and similarity.py.

A converted drmemtrace unit is a zip of chunk.NNNN files of 12-byte entries
(u16 type, u16 size, u64 addr). Instruction entries carry the PC and length,
READ/WRITE entries the data address and size.

Canonical ("physical-like") addresses, from the unit's modules.log and the ELF
program headers of each mapped file:
  shared  -- inside a module segment whose ELF PT_LOAD is NOT writable (text,
             rodata): the same page-cache page in every process that maps the
             file. Key = (file id, link-time address). ASLR is removed.
  private -- everything else: heap, stack, anonymous mmaps, and writable
             segments (.data/.bss/GOT/.data.rel.ro, which are COW-private once
             written; relocation writes them in every process). Key = (pid, VA).
"""
from __future__ import annotations
import re, subprocess, zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np

ENT = np.dtype([("type", "<u2"), ("size", "<u2"), ("addr", "<u8")])
INSTR = np.array([10, 11, 12, 13, 14, 15, 16, 31, 48, 49], dtype=np.uint16)   # as e2e_post.py
READ, WRITE = 0, 1
PRIV = np.uint64(1 << 63)
LOAD = re.compile(r"^\s*LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+([RWE ]+?)\s+0x", re.M)


def entries(trace_zip: str) -> np.ndarray:
    zf = zipfile.ZipFile(trace_zip)
    parts = [np.frombuffer(zf.read(n), dtype=ENT) for n in sorted(zf.namelist()) if n.startswith("chunk.")]
    return np.concatenate(parts) if parts else np.empty(0, ENT)


@lru_cache(maxsize=None)
def elf_loads(path: str) -> tuple:
    """PT_LOAD (vaddr page start, vaddr end, writable) of an ELF file; () if unreadable."""
    try:
        txt = subprocess.run(["readelf", "-lW", path], capture_output=True, text=True, timeout=30).stdout
    except Exception:  # noqa: BLE001
        return ()
    out = []
    for off, va, fsz, msz, flg in LOAD.findall(txt):
        va = int(va, 16)
        out.append((va & ~0xFFF, va + int(msz, 16), "W" in flg))
    return tuple(out)


class Canon:
    """Per task: file ids and per-modules.log segment tables."""
    def __init__(self):
        self.fid: dict[str, int] = {}
        self.unknown_files: set[str] = set()

    def file_id(self, path: str) -> int:
        if path not in self.fid:
            self.fid[path] = len(self.fid) + 1
        return self.fid[path]

    def segments(self, modlog: str):
        """-> starts, ends, delta (link addr - VA), fid, shared  (sorted by start)"""
        rows = []
        for line in open(modlog, errors="replace"):
            f = [x.strip() for x in line.split(",")]
            if len(f) < 9 or not f[0].isdigit():
                continue
            start, end, pref, path = int(f[2], 16), int(f[3], 16), int(f[6], 16), f[-1]
            if not path.startswith("/"):
                continue                                   # [vdso] etc.: private
            loads = elf_loads(path)
            w = None
            for lo, hi, wr in loads:
                if lo <= pref < hi:
                    w = wr
                    break
            if w is None:                                  # not resolvable: keep private
                self.unknown_files.add(path)
                continue
            rows.append((start, end, pref - start, self.file_id(path), not w))
        rows.sort()
        a = np.array(rows, dtype=object) if rows else np.empty((0, 5), dtype=object)
        return (np.array([r[0] for r in rows], np.uint64), np.array([r[1] for r in rows], np.uint64),
                np.array([r[2] for r in rows], np.int64), np.array([r[3] for r in rows], np.uint64),
                np.array([r[4] for r in rows], bool))

    def lines(self, addr: np.ndarray, segs, pid: int):
        """byte addresses -> (line key u64, shared bool)"""
        starts, ends, delta, fid, shared = segs
        i = np.searchsorted(starts, addr, side="right") - 1
        ok = i >= 0
        ic = np.where(ok, i, 0)
        inside = ok & (addr < ends[ic]) if len(starts) else np.zeros(len(addr), bool)
        sh = inside & shared[ic] if len(starts) else inside
        link = (addr.astype(np.int64) + delta[ic]).astype(np.uint64) if len(starts) else addr
        key_sh = (fid[ic] << np.uint64(29)) | (link >> np.uint64(6)) if len(starts) else addr
        key_pr = PRIV | (np.uint64(pid) << np.uint64(41)) | (addr >> np.uint64(6))
        return np.where(sh, key_sh, key_pr), sh

    def pcs(self, pc: np.ndarray, segs, pid: int):
        """instruction PCs -> canonical code address (file id << 40 | link addr) or private"""
        starts, ends, delta, fid, shared = segs
        i = np.searchsorted(starts, pc, side="right") - 1
        ok = i >= 0
        ic = np.where(ok, i, 0)
        inside = ok & (pc < ends[ic])
        link = (pc.astype(np.int64) + delta[ic]).astype(np.uint64)
        return np.where(inside, (fid[ic] << np.uint64(40)) | link,
                        PRIV | (np.uint64(pid) << np.uint64(41)) | (pc & np.uint64((1 << 41) - 1)))


def tool_class(comm: str, cmdline: str, is_harness: bool) -> str:
    """Which 'same tool' a process is: same binary + same script/subcommand."""
    if is_harness:
        return "harness (SWE-agent python3.12)"
    argv = cmdline.split()
    if not argv:
        return comm
    if comm.startswith("python"):
        rest = argv[1:]
        while rest and rest[0].startswith("-") and rest[0] not in ("-m", "-c"):
            rest = rest[1:]
        if rest and rest[0] == "-m":
            return f"{comm} -m {rest[1] if len(rest) > 1 else ''}"
        if rest and rest[0] == "-c":
            return f"{comm} -c"
        return f"{comm} {Path(rest[0]).name}" if rest else comm
    if comm in ("dash", "sh") and "-c" in argv:
        if "bash -n << 'SOUNIQUEEOF'" in cmdline:
            return "sh -c 'env bash -n' (tool-call wrapper)"
        j = argv.index("-c")
        return f"sh -c {Path(argv[j + 1]).name}" if len(argv) > j + 1 else "sh -c"
    if comm == "git":
        sub = [a for a in argv[1:] if not a.startswith("-")]
        return f"git {sub[0]}" if sub else "git"
    if comm == "bash":
        return "bash " + " ".join(argv[1:2])
    return comm
