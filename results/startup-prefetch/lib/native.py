"""Native-run accounting: processes, tool calls, and agent steps from perf + swetrace + proclog.

Inputs (one run directory): perf.data (instructions/period=1000000/u, -C pinned CPUs, task events,
CLOCK_MONOTONIC), clock_offset.txt (wall - monotonic), swetrace.ndjson (harness spans),
procs.jsonl (command lines, from proclog.py).

perf -C also sees processes that are not ours; only the harness and its descendants (by fork
events) are kept. An instruction count is samples x PERIOD: exact to within PERIOD per process or
interval, provided the event was not throttled (throttle.json bounds that).
"""
from __future__ import annotations
import bisect, collections, json, re, subprocess
from pathlib import Path

import numpy as np

PERF = "/usr/lib/linux-tools-5.15.0-190/perf"
PERIOD = 1_000_000
LINE = re.compile(r"^\s*(.*?)\s+(\d+)/(\d+)\s+\[(\d+)\]\s+([\d.]+):\s*(.*)$")


def spans(path: Path):
    t0 = None; opened = {}; out = []; hpid = None
    for l in open(path):
        r = json.loads(l)
        if r["kind"] == "meta" and r["name"] == "trace.start":
            t0, hpid = r["t0_wall"], r["pid"]
        elif r["kind"] == "start":
            opened[r["span"]] = r
        elif r["kind"] == "end" and r["span"] in opened:
            s = opened.pop(r["span"])
            out.append(dict(t0=t0 + s["t"], t1=t0 + r["t"], name=s["name"], id=s["span"], parent=s.get("parent"),
                            attrs={**s.get("attrs", {}), **r.get("attrs", {})}))
    out.sort(key=lambda s: s["t0"])
    return out, hpid


def merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def python_script(cmdline: str) -> str | None:
    """'_state_anthropic' / 'str_replace_editor' / '-c' / '-m pytest' / 'test_x.py' for a python argv, else None."""
    argv = cmdline.split()
    if not argv or not re.match(r"python[\d.]*$", Path(argv[0]).name):
        return None
    rest = argv[1:]
    while rest and rest[0].startswith("-") and rest[0] not in ("-m", "-c"):
        rest = rest[1:]
    if not rest:
        return "(interactive)"
    if rest[0] == "-m":
        return "-m " + (rest[1] if len(rest) > 1 else "")
    if rest[0] == "-c":
        return "-c"
    return Path(rest[0]).name


def tool_type(command: str) -> str:
    """Type of a tool call from its action string: first command word after leading `cd ... &&`,
    with the SWE-agent editor's subcommand."""
    c = command.strip()
    while True:
        m = re.match(r"^cd\s+\S+\s*(&&|;)\s*", c)
        if not m:
            break
        c = c[m.end():]
    w = c.split()
    while w and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[0]):   # leading VAR=value assignments
        w = w[1:]
    if not w:
        return "(empty)"
    if w[0] == "str_replace_editor":
        return "str_replace_editor " + (w[1] if len(w) > 1 else "")
    if w[0] in ("env",) and len(w) > 1:
        w = [x for x in w[1:] if "=" not in x] or w
    first = Path(w[0]).name
    if re.match(r"python[\d.]*$", first):
        if len(w) > 2 and w[1] == "-m":
            return f"python -m {w[2]}"
        if len(w) > 1 and w[1] == "-c":
            return "python -c"
        return "python <script>"
    return first


def load(run: Path):
    off = float((run / "clock_offset.txt").read_text())
    txt = subprocess.run([PERF, "script", "-i", str(run / "perf.data"), "-F", "comm,pid,tid,cpu,time",
                          "--show-task-events"], capture_output=True, text=True).stdout
    samp = collections.defaultdict(list); samp_tid = collections.defaultdict(list); scpu = collections.defaultdict(list)
    fork, exitt, ppid, execs = {}, {}, {}, collections.defaultdict(list)
    for l in txt.splitlines():
        m = LINE.match(l)
        if not m:
            continue
        pid, tid, cpu, t, rest = int(m.group(2)), int(m.group(3)), int(m.group(4)), float(m.group(5)) + off, m.group(6)
        if not rest:
            samp[pid].append(t); scpu[pid].append(cpu); samp_tid[(pid, tid)].append(t)
        elif rest.startswith("PERF_RECORD_FORK"):
            c, p = re.findall(r"\((\d+):(\d+)\)", rest)
            if c[0] != c[1]:
                continue
            if c[0] != p[0]:
                fork[int(c[0])] = t; ppid[int(c[0])] = int(p[0])
        elif rest.startswith("PERF_RECORD_EXIT"):
            c = re.findall(r"\((\d+):(\d+)\)", rest)[0]
            if c[0] == c[1]:
                exitt[int(c[0])] = t
        elif rest.startswith("PERF_RECORD_COMM exec"):
            execs[pid].append((t, rest.split("exec: ")[1].rsplit(":", 1)[0]))
    sp, hpid = spans(run / "swetrace.ndjson")
    # the harness tree: descendants of the harness pid through fork events
    kids = collections.defaultdict(list)
    for c, p in ppid.items():
        kids[p].append(c)
    tree, stack = set(), [hpid]
    while stack:
        p = stack.pop()
        if p in tree:
            continue
        tree.add(p); stack += kids.get(p, [])
    cmd = collections.defaultdict(list)
    if (run / "procs.jsonl").exists():
        for l in open(run / "procs.jsonl"):
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            cmd[r["pid"]].append((r["t"], r["cmdline"]))
    return dict(off=off, samp=samp, samp_tid=samp_tid, scpu=scpu, fork=fork, exit=exitt, ppid=ppid, execs=execs,
                spans=sp, hpid=hpid, tree=tree, cmd=cmd)


def analyse(run: Path):
    d = load(run)
    sp, hpid, tree = d["spans"], d["hpid"], d["tree"]
    get_state = [s for s in sp if s["name"] == "tool.get_state"]

    def nested_in_state(s):
        return any(g["t0"] <= s["t0"] and s["t1"] <= g["t1"] for g in get_state)

    steps = [s for s in sp if s["name"] == "agent.step"]
    step_of = lambda t: next((s["attrs"].get("step") for s in steps if s["t0"] <= t <= s["t1"]), "")
    calls = []
    for s in sp:
        if s["name"] == "tool.exec" and not nested_in_state(s):
            kind = "action" if step_of(s["t0"]) != "" else "setup"
            calls.append(dict(kind=kind, t0=s["t0"], t1=s["t1"], command=s["attrs"].get("command", ""), span=s))
        elif s["name"] == "tool.get_state":
            calls.append(dict(kind="state", t0=s["t0"], t1=s["t1"], command="_state_anthropic", span=s))
    calls.sort(key=lambda c: c["t0"])
    parse = [s for s in sp if s["name"] == "response.parse"]
    # processes of the tree
    procs = []
    for p in sorted(tree - {hpid}, key=lambda p: d["fork"].get(p, 0)):
        ts = d["samp"].get(p, []); cpus = collections.Counter(d["scpu"].get(p, []))
        cl = [c for _, c in d["cmd"].get(p, [])]
        names = [n for _, n in d["execs"].get(p, [])]
        chain = ">".join(names)
        # Whether a process is Python comes from exec events, which are exact. Which script: the
        # shebang script exec'd just before the interpreter (comm, cut to 15 characters by the
        # kernel), else the command line if proclog's 10 ms poll caught the process.
        py = None
        ip = next((i for i, n in enumerate(names) if re.match(r"python[\d.]*$", n)), None)
        if ip is not None:
            py = names[ip - 1] if ip > 0 and names[ip - 1] not in ("env", "sh", "bash", "dash") else None
            py = py or next((x for x in (python_script(c) for c in cl) if x), None) or "(script not captured)"
        py_exec_t = next((t for t, n in d["execs"].get(p, []) if re.match(r"python[\d.]*$", n)), "")
        f = d["fork"].get(p)
        call = next((i for i, c in enumerate(calls) if f is not None and c["t0"] <= f <= c["t1"]), "")
        procs.append(dict(pid=p, ppid=d["ppid"].get(p, ""), t_fork=f or "", t_exit=d["exit"].get(p, ""), exec_chain=chain,
                          cmdline=(cl[-1] if cl else "")[:300], python_script=py or "", t_python_exec=py_exec_t,
                          instrs=len(ts) * PERIOD, top_cpu=cpus.most_common(1)[0][0] if cpus else "",
                          n_cpus=len(cpus), call=call, step=step_of(f) if f else ""))
    # tool calls: python creations and the prediction point
    for i, c in enumerate(calls):
        pr = [p for p in procs if p["call"] == i]
        pys = [p for p in pr if p["python_script"]]
        st = step_of(c["t0"])
        pp = [s for s in parse if s["t1"] <= c["t0"] and (not steps or step_of(s["t0"]) == st)]
        c.update(i=i, step=st, type=("state: _state_anthropic" if c["kind"] == "state" else tool_type(c["command"])),
                 n_procs=len(pr), n_python=len(pys), python_scripts="|".join(p["python_script"] for p in pys),
                 t_first_python_exec=min((p["t_python_exec"] or p["t_fork"] for p in pys), default=""),
                 t_predict=(pp[-1]["t1"] if pp else ""), instrs_procs=sum(p["instrs"] for p in pr),
                 instrs_python=sum(p["instrs"] for p in pys))
    hmain = np.sort(np.array(d["samp_tid"].get((hpid, hpid), [])))
    hall = np.sort(np.array(d["samp"].get(hpid, [])))
    return d, calls, procs, hmain, hall
