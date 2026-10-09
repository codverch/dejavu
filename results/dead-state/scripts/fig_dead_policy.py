#!/usr/bin/env python3
"""Paper figures from the LLC study summary: dead capacity-time per level x phase, and LLC policy speedups.
  fig_dead_policy.py <summary.json> <outdir>"""
import json, sys
from pathlib import Path
sys.path.insert(0, "/h/deepanjm/mise/results/swe-bench-traces/e2e-uarch/scripts")
import anish_style as st
import matplotlib.pyplot as plt

S = json.load(open(sys.argv[1])); out = Path(sys.argv[2]); st.use()
LV = [("ICACHE", "L1-I"), ("DCACHE", "L1-D"), ("MLC_CACHE", "L2"), ("L1_CACHE", "LLC")]
PH = [("harness start-up", "start-up", "s"), ("env setup", "env set-up", "^"),
      ("harness session", "session", "D"), ("tool exec", "tool exec", "o")]

# Fig: dead capacity-time. Bar = all phases (lower bound solid, unresolved range hatched); dots = phases.
fig, ax = plt.subplots(figsize=(3.3, 2.0))
d = S["dead_state_lru"]
for i, (k, name) in enumerate(LV):
    lo, hi = 100 * d["all"][k]["dead_capacity_time_lo"], 100 * d["all"][k]["dead_capacity_time_hi"]
    ax.bar(i, lo, 0.55, color="#b2182b", alpha=0.85, zorder=2)
    ax.bar(i, hi - lo, 0.55, bottom=lo, color="white", edgecolor="#b2182b", hatch="////", linewidth=0.6, zorder=2)
    ax.text(i, hi + 2, f"{lo:.0f}" + (f"–{hi:.0f}" if hi - lo >= 1 else "") + "%", ha="center", va="bottom", fontsize=7)
    for j, (p, _, m) in enumerate(PH):
        ax.plot(i + 0.36, 100 * d[p][k]["dead_capacity_time_lo"], m, ms=2.6, color=st.INK, mfc="white", mew=0.6, zorder=3)
ax.set_xticks(range(4), [n for _, n in LV]); ax.set_ylim(0, 100); ax.set_xlim(-0.5, 3.75)
ax.set_ylabel("Dead capacity-time (%)")
st.save(fig, out / "dead_capacity_time.png")

# Fig: LLC policy speedup over LRU, 95% CI, all phases.
A = S["aggregate"]["all"]
POL = [("mj", "Mockingjay"), ("oracle", "ideal dead-block eviction"), ("oracle_byp", "+ dead-on-arrival bypass"),
       ("never_byp", "never-reused oracle + bypass"), ("min", "Belady MIN + bypass")]
fig, ax = plt.subplots(figsize=(3.3, 1.45))
for y, (k, name) in enumerate(reversed(POL)):
    v, lo, hi = [100 * (A[k][x] - 1) for x in ("speedup", "sp_lo", "sp_hi")]
    ax.plot([lo, hi], [y, y], color=st.INK, lw=0.8); ax.plot(v, y, "o", ms=3, color=st.COLD)
    ax.text(max(hi, 0) + 0.12, y, f"{name}  {v:+.1f}%", va="center", fontsize=7)
ax.axvline(0, color=st.RULE, lw=0.8, zorder=0)
ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.set_xlim(-1, 5.2); ax.set_ylim(-0.6, len(POL) - 0.4)
ax.set_xlabel("IPC change over LRU at the LLC (%)")
st.save(fig, out / "llc_policy_speedup.png")
print("ok")
