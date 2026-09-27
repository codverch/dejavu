#!/usr/bin/env python3
"""Tables of one native run: procs.csv, calls.csv, gaps.csv, harness_spans.csv, throttle.json.

  native_summary.py <run dir>

procs.csv   every process of the harness tree: fork/exit, exec chain, command line, python script
            (if any), instructions, CPUs
calls.csv   every tool call (setup / action / state): type, command, prediction point (end of the
            step's response.parse), processes, python creations, first python exec time, instructions
gaps.csv    per step: from the end of step k's last tool span to the start of step k+1's action --
            wall, model wall, harness instructions (main thread and all threads), other instructions
harness_spans.csv  harness main-thread instructions by innermost span
throttle.json      perf throttling: pairs, seconds, upper bound on lost instructions
"""
import csv, json, re, subprocess, sys
from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from native import PERF, PERIOD, analyse, merge  # noqa: E402


def cnt(arr, a, b):
    return (bisect_right(arr, b) - bisect_left(arr, a)) * PERIOD


def throttle(run):
    txt = subprocess.run([PERF, "script", "-i", str(run / "perf.data"), "-D"], capture_output=True, text=True).stdout
    op, s, n, last, mx, ns = {}, 0.0, 0, {}, 0.0, 0
    for m in re.finditer(r"^(\d+) (\d+) 0x[0-9a-f]+ \[0x[0-9a-f]+\]: PERF_RECORD_(UNTHROTTLE|THROTTLE|SAMPLE)", txt, re.M):
        cpu, t, k = int(m.group(1)), int(m.group(2)) / 1e9, m.group(3)
        if k == "THROTTLE":
            op[cpu] = t
        elif k == "UNTHROTTLE" and cpu in op:
            s += t - op.pop(cpu); n += 1
        else:
            ns += 1
            if cpu in last and t - last[cpu] > 1e-4:
                mx = max(mx, PERIOD / (t - last[cpu]))
            last[cpu] = t
    return dict(throttle_pairs=n, throttled_seconds=round(s, 6), max_rate_instr_per_s=round(mx),
                counted_instrs_all_cpus=ns * PERIOD, lost_instr_upper_bound=round(s * mx),
                lost_share_upper_bound=round(s * mx / max(ns * PERIOD, 1), 5))


def main(run: Path):
    d, calls, procs, hmain, hall = analyse(run)
    sp = d["spans"]
    others = np.sort(np.concatenate([np.array(d["samp"][p]) for p in d["tree"] if p != d["hpid"] and p in d["samp"]] or [np.empty(0)]))
    rts = merge([(s["t0"], s["t1"]) for s in sp if s["name"] == "http.roundtrip"])
    def w(name, rows):
        keys = []
        for r in rows:
            keys += [k for k in r if k not in keys]
        with open(run / name, "w", newline="") as fh:
            x = csv.DictWriter(fh, fieldnames=keys, restval=""); x.writeheader(); x.writerows(rows)
    w("procs.csv", procs)
    crow = []
    for c in calls:
        crow.append({k: c[k] for k in ("i", "kind", "step", "type", "command", "t0", "t1", "t_predict", "n_procs", "n_python",
                                        "python_scripts", "t_first_python_exec", "instrs_procs", "instrs_python")})
        crow[-1]["command"] = crow[-1]["command"][:200]
        crow[-1]["harness_instrs_main"] = cnt(hmain, c["t0"], c["t1"])
        if c["t_predict"] != "" and c["t_first_python_exec"] != "":
            lo, hi = sorted((c["t_predict"], c["t_first_python_exec"]))
            crow[-1]["lead_s"] = c["t_first_python_exec"] - c["t_predict"]
            crow[-1]["lead_instrs_tree"] = cnt(np.sort(np.concatenate([hall, others])), lo, hi)
    w("calls.csv", crow)
    grow = []
    acts = [c for c in calls if c["kind"] == "action"]
    for a, b in zip(acts, acts[1:]):
        end_a = max([c["t1"] for c in calls if c["step"] == a["step"] and c["kind"] in ("action", "state")])
        ga, gb = end_a, b["t0"]
        mw = sum(min(y, gb) - max(x, ga) for x, y in rts if y > ga and x < gb)
        grow.append(dict(step=a["step"], next_step=b["step"], wall=gb - ga, model_wall=mw,
                         harness_instrs_main=cnt(hmain, ga, gb), harness_instrs_all=cnt(hall, ga, gb),
                         other_instrs=cnt(others, ga, gb)))
    w("gaps.csv", grow)
    tot = [s for s in sp if s["name"] == "run.total"][0]
    c = Counter()
    for t in hmain:
        if not (tot["t0"] <= t <= tot["t1"]):
            continue
        best = None
        for s in sp:
            if s["t0"] > t:
                break
            if s["t1"] >= t and (best is None or s["t0"] >= best["t0"]):
                best = s
        c[best["name"] if best else "none"] += PERIOD
    w("harness_spans.csv", [dict(innermost_span=k, instrs=v) for k, v in c.most_common()])
    json.dump(throttle(run), open(run / "throttle.json", "w"), indent=1)
    print(f"{run}: {len(procs)} procs, {len(calls)} calls, {sum(1 for x in calls if x['n_python'])} with python", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
