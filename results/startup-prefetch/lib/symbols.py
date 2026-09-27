"""Symbols of mapped files and exact phase boundaries of one process's instruction stream.

Canonical PCs are (file id << 40) | link-time address (canon.Canon.pcs), so a boundary is the first
position where the PC equals a symbol's link-time address in the right file.
"""
import bisect, re, subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

from canon import INSTR, Canon, entries

K = 32                                   # k-gram length for instruction-sequence identity
M = np.uint64(0x9E3779B97F4A7C15)

PHASES = ("loader", "proc_init", "rt_init", "work", "teardown")
MARKS = {"proc_init_end": ("Py_BytesMain", "Py_RunMain", "Py_Main"),
         "rt_init_end": ("PyRun_AnyFileExFlags", "PyRun_SimpleFileExFlags", "PyRun_SimpleStringFlags",
                         "_PyRun_AnyFileObject", "_PyRun_SimpleFileObject"),
         "work_end": ("Py_FinalizeEx",)}


DEBUG = Path("/localdisk/deepanjm/isca-traces/uarch-e2e/debug/x/usr/lib/debug/.build-id")


@lru_cache(maxsize=None)
def symfile(path: str) -> str:
    """The separate debug file with the same build-id, if we have it (ld.so and libc, from
    libc6-dbg 2.35-0ubuntu3.8); otherwise the binary itself."""
    txt = subprocess.run(["readelf", "-n", path], capture_output=True, text=True).stdout
    m = re.search(r"Build ID: ([0-9a-f]+)", txt)
    if m:
        f = DEBUG / m.group(1)[:2] / (m.group(1)[2:] + ".debug")
        if f.exists():
            return str(f)
    return path


@lru_cache(maxsize=None)
def dynsyms(path: str) -> dict:
    """function name -> link-time address: exported (nm -D) plus the full symbol
    table where one exists (a static python exports few of the markers)."""
    out = subprocess.run(["nm", "-D", "--defined-only", path], capture_output=True, text=True).stdout
    out += subprocess.run(["nm", "--defined-only", symfile(path)], capture_output=True, text=True).stdout
    # nm -D prints versioned names (exit@@GLIBC_2.2.5): strip the version
    return {m.group(2).split("@")[0]: int(m.group(1), 16)
            for m in re.finditer(r"^([0-9a-f]+) [TtWi] (\S+)$", out, re.M)}


@lru_cache(maxsize=None)
def fulltable(path: str):
    """(addrs, sizes, names) of every defined function (symtab, else dynsym)."""
    for opt in ([], ["-D"]):
        txt = subprocess.run(["nm", "-C", "-S", "--defined-only", *opt, symfile(path) if not opt else path],
                             capture_output=True, text=True).stdout
        out = []
        for l in txt.splitlines():
            a = l.split(" ", 3)
            try:
                if len(a) == 4 and a[2] in "tTwWiI":
                    out.append((int(a[0], 16), int(a[1], 16), a[3]))
            except ValueError:
                pass
        if out:
            out.sort()
            return [x[0] for x in out], [x[1] for x in out], [x[2] for x in out]
    return [], [], []


def fn_of(path: str, link: int) -> str:
    addrs, sizes, names = fulltable(path)
    j = bisect.bisect_right(addrs, link) - 1
    if j >= 0 and link < addrs[j] + max(sizes[j], 1):
        return re.sub(r"\.(llvm\.\d+|cold|isra\.\d+|part\.\d+|constprop\.\d+)$", "", names[j])
    return "<no symbol>"


def seq(u):
    """canonical PC sequence of one unit, plus the file table it uses."""
    c = Canon()
    e = entries(u["trace_zip"])
    pcs = e["addr"][np.isin(e["type"], INSTR)]
    segs = c.segments(u["modlog"])
    cp = c.pcs(pcs, segs, int(u["pid"]))
    return cp, {v: k for k, v in c.fid.items()}


def kgrams(cp):
    n = len(cp) - K + 1
    if n <= 0:
        return np.empty(0, np.uint64)
    h = np.zeros(n, np.uint64)
    with np.errstate(over="ignore"):
        for j in range(K):
            h = h * M + cp[j:j + n]
    return h


@lru_cache(maxsize=None)
def elf_entry(path: str):
    """link-time entry point of an executable (not of a shared library), else None"""
    txt = subprocess.run(["readelf", "-h", path], capture_output=True, text=True).stdout
    m = re.search(r"Entry point address:\s+0x([0-9a-f]+)", txt)
    if not m or ".so" in Path(path).name or int(m.group(1), 16) == 0:
        return None
    return int(m.group(1), 16)


def phases(cp, files):
    """instruction index where each phase starts; files: local fid -> path."""
    fid = (cp >> np.uint64(40)).astype(np.int64)
    link = (cp & np.uint64((1 << 40) - 1)).astype(np.int64)
    priv = cp >= np.uint64(1 << 63)
    ldso = [f for f, p in files.items() if "ld-linux" in p]
    in_ld = np.isin(fid, ldso) & ~priv
    n = len(cp)
    b = {"loader": 0}
    # The loader hands control to the program at the executable's ELF entry point (_start). The first
    # instruction outside ld.so is not that point: ld.so calls libc's ifunc resolvers while it relocates.
    b["proc_init"] = n
    for f, pth in files.items():
        e = elf_entry(pth)
        if e is not None:
            hit = np.nonzero((fid == f) & (link == e) & ~priv)[0]
            if len(hit):
                b["proc_init"] = min(b["proc_init"], int(hit[0]))
    if b["proc_init"] == n:                         # no entry point found: fall back
        nz = np.nonzero(~in_ld)[0]
        b["proc_init"] = int(nz[0]) if len(nz) else n
    def first_of(names):
        best = n
        for f, p in files.items():
            s = dynsyms(p)
            for nm in names:
                if nm in s:
                    hit = np.nonzero((fid == f) & (link == s[nm]) & ~priv)[0]
                    if len(hit):
                        best = min(best, int(hit[0]))
        return best
    py = any("python" in Path(p).name for p in files.values())
    if py:
        b["rt_init"] = max(first_of(MARKS["proc_init_end"]), b["proc_init"])
        b["work"] = max(first_of(MARKS["rt_init_end"]), b["rt_init"])
        b["teardown"] = max(first_of(MARKS["work_end"]), b["work"])
    else:
        b["rt_init"] = b["proc_init"]              # native: no interpreter
        b["work"] = b["proc_init"]
        libc = {f: p for f, p in files.items() if Path(p).name.startswith("libc.so")}
        ex = n
        for f, p in libc.items():
            s = dynsyms(p)
            if "exit" in s:
                hit = np.nonzero((fid == f) & (link == s["exit"]) & ~priv)[0]
                if len(hit):
                    ex = int(hit[0])
        b["teardown"] = max(ex, b["work"])
    return b


