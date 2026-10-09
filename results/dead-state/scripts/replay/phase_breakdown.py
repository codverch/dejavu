#!/usr/bin/env python3
"""Exclusive (self) instructions per harness phase and step from a phasewrap PHASE_LOG.
  phase_breakdown.py <phases.log> [out.csv]"""
import collections, csv, sys
NAMES = {1: "startup", 2: "setup", 3: "step_self", 4: "messages", 5: "model_query", 6: "parse", 7: "handle_action",
         8: "communicate", 9: "get_state", 10: "add_history", 11: "add_trajectory", 12: "save_trajectory",
         13: "get_traj_data", 14: "gc", 15: "run", 16: "forward", 17: "edited_files"}
rows = [tuple(map(int, l.split())) for l in open(sys.argv[1]) if l.strip()]
stack, self_i, cur_step = [], collections.defaultdict(int), 0
last = rows[0][3]
for code, edge, arg, ins, ns in rows:
    top = stack[-1] if stack else ("between", None)
    self_i[(top[1] if top[1] is not None else cur_step, NAMES.get(top[0], top[0]))] += ins - last
    last = ins
    if code == 3 and edge == 0: cur_step = arg
    if edge == 0: stack.append((code, cur_step if code != 1 else 0))
    else:
        while stack and stack[-1][0] != code: stack.pop()
        if stack: stack.pop()
steps = sorted({s for s, _ in self_i})
names = [n for n in NAMES.values()] + ["between"]
w = csv.writer(open(sys.argv[2], "w") if len(sys.argv) > 2 else sys.stdout)
w.writerow(["step"] + names)
for s in steps:
    w.writerow([s] + [self_i.get((s, n), 0) for n in names])
tot = collections.defaultdict(int)
for (s, n), v in self_i.items(): tot[n] += v
print("TOTAL (B instr):", {n: round(v / 1e9, 3) for n, v in sorted(tot.items(), key=lambda x: -x[1])}, file=sys.stderr)
