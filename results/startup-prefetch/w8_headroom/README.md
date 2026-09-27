# W8: headroom of start-up prefetching into the L1, measured the Constable way

**The question.** Suppose a prefetcher knew, from the previous time a script started, which lines its
next start-up will touch, and could have each one in the L1 just in time. How fast would tool-call
Python processes run? This follows Constable's headroom method (Bera et al., ISCA'24 §4):
- measure the opportunity;
- run a ladder of ideal configurations that each remove one more part of the cost;
- compare against brute-force hardware;
- report geomeans per workload group and a sorted per-trace graph.

**The answer.**
- **The predictable headroom is +8.8% geomean** (7.3-10.8% per process).
- **A perfect L1 would give +32.3%.** The gap is data: history predicts every L1-I miss but only 16% of
  L1-D misses. The rest go to heap and stack lines, whose addresses change from one process to the next.
- **Prefetching into the L2 and LLC at the model call gives +0.7%.** Before `a620ec9` the LLC also
  held copies of the L2's lines (32K distinct lines instead of 48K); with that fixed the result is the same
  within 0.1 point.
- **+8.8% is an upper bound, looser than it looks.** The ideal mode never puts a predicted line in the L1,
  so the lines it does not predict keep the L1 to themselves. The ideal L1-D removes 23% of L1-D misses,
  but only 16% go to predicted lines. The other 7 points are that side effect.

## Setup (`scripts/w8_headroom.py`)
- **Units.** 25 tool-call Python processes, 5 per task (django-13809, requests-1142, xarray-2905,
  sphinx-8459, sympy-11618).
  - A candidate must have an earlier process of the same script in the same task.
  - Five are picked at the 10/30/50/70/90th percentile positions in time, fixed before any simulation
    (`selection.csv`). 20 are `_state_anthropic` and 5 are `str_replace_editor`, which follows how often
    each runs.
- **Region.** A process's first min(instrs, 100M) instructions: its start-up (~73M instructions in
  django), then the start of the script's own work.
- **Records.** Each process's own line list (self, an oracle), and the previous process's list rebased to
  this process's library addresses (prev). Heap, stack and anonymous lines cannot be rebased: 49-75% of a
  record is dropped (`rebase.csv`). 99.9-100% of the rebased lines are touched again, covering 26-51% of
  the new process's lines.
- **Configurations** (Scarab `ideal-prefetching` `2530d7e`; `install_prev` and `count_prev` `b819cfb`;
  `PARAMS.golden_cove`, cold):

| config | what |
|---|---|
| `base` | golden_cove |
| `l1d_2x`, `l2_2x` | brute force: 2× L1-D (96 KB), 2× effective L2 (2 MB) |
| `install_prev` | prev lines put in the L2 and LLC before the process starts (at the model call), soonest-needed first until sets are full; the hierarchy is exclusive, so the LLC takes the lines the L2 has no room for |
| `ideal_l1i_prev` / `ideal_l1d_prev` / `ideal_l1_prev` | `spf_mode 3`: every L1-I / L1-D / L1 miss to a prev line becomes a hit (no capacity or bandwidth cost; L1-D ports still modelled) |
| `ideal_l1_self` | the same with the process's own lines: a perfect L1 for the region |
| `count_prev` | golden_cove, counting the on-path L1 misses to prev lines (`spf_ideal 7`): they still miss |
| `perfect_all` | every level perfect |

## Checks
- 325/325 runs finished.
- For all 25 units, record-pass cycles and count-only cycles equal base cycles (`checks.csv`).
- `b819cfb` gives the same cycles as `2530d7e` for `base`, `ideal_l1_prev` and `ideal_l1d_prev` on a
  5M-instruction slice of django-532, so the other configurations were not rerun.
- With spf off, `2530d7e` is bit-identical to `baseline` on 5,814 counters, 4 traces
  (`../checks/identical-2530d7e.txt`).
- On a 5M-instruction slice, `ideal_l1d_self` gives 1.561× against Scarab's `perfect_dcache` 1.572×. The
  difference is L1-D port contention, which the ideal mode keeps.

## Results (`summary.csv`: geomean speedup over golden_cove)

| task | 2× L1-D | 2× L2 | L2+LLC at model call | ideal L1-I | ideal L1-D | **ideal L1** | perfect L1 | perfect all |
|---|---|---|---|---|---|---|---|---|
| django | +1.9% | +6.6% | +0.8% | +4.0% | +6.2% | **+10.6%** | +32.3% | +33.2% |
| requests | +1.8% | +5.9% | +0.7% | +3.8% | +4.5% | **+8.6%** | +31.1% | +31.9% |
| xarray | +1.8% | +7.0% | +0.9% | +3.8% | +3.4% | **+7.6%** | +33.7% | +34.6% |
| sphinx | +1.9% | +6.3% | +0.6% | +3.7% | +4.4% | **+8.4%** | +33.3% | +34.0% |
| sympy | +1.9% | +5.9% | +0.7% | +3.8% | +4.5% | **+8.6%** | +31.2% | +31.9% |
| **GEOMEAN** | +1.8% | +6.3% | +0.7% | +3.8% | +4.6% | **+8.8%** | +32.3% | +33.1% |

Opportunity (`fig_opportunity.png`, from `count_prev`): of golden_cove's on-path L1 misses, 100% of L1-I
misses and 10-20% of L1-D misses (16% overall) go to lines the previous start-up touched. The ideal L1-D
mode removes more, 15-29% (23% overall), because predicted lines never take L1 capacity from the rest.

What these numbers say:
1. **History predicts code completely and data poorly.** Every instruction line a start-up fetches was
   fetched by the previous start-up at the same (rebased) address. Only about a sixth of L1-D misses go
   to such lines. The rest are heap and stack, rebuilt at new addresses every time.
2. **Where the lines sit matters more than knowing them.** The same predicted lines give +0.7% when put in
   L2/LLC ahead of time and +8.8% when they are in the L1 at use. The cost of start-up is L1 misses that
   hit in L2, and golden_cove's own prefetchers and L2 already serve those. That is the same finding as
   W4, now with a bound.
3. **The ideal beats brute force.** +8.8% is more than doubling the L1-D (+1.8%) or the L2 (+6.3%).
4. **The largest remaining headroom is data at unpredictable addresses:** 32.3% − 8.8%. Whether heap lines
   are predictable relative to the heap's base (allocation is deterministic across start-ups) was **not
   tested**; `lib/rebase.py` drops them.

## Limits
- **This is an ideal.** No real L1 prefetcher gets lines in just in time with no port, MSHR or capacity
  cost. Capacity matters: a third of the L1-D misses the ideal removes are not to predicted lines (see
  Opportunity). A just-in-time mode that also fills the L1 would bound this more tightly; it was not built. Streaming into the L1-D stalled Scarab's forward-progress watchdog in W4, so no realistic L1
  prefetcher was simulated.
- **5 units per task,** mostly `_state_anthropic`. Per-process spread is small (7.3-10.8%).

## Figures
- `fig_headroom_geomean.png`: per-task geomean bars (Constable Fig. 7).
- `fig_headroom_per_trace.png`: all 25 processes, sorted (Constable Fig. 11).
- `fig_opportunity.png`: share of L1 misses removed (Constable Fig. 3a).

## Perfect L1-D alone (`fig_perfect_l1d.png`, config `perfect_l1d`)
Every L1-D access hits (Scarab `--perfect_dcache`); nothing else changes. Geomean +27.8% (per task
+26.7% to +29.2%). By script: `_state_anthropic` +28.5% to +32.8%, `str_replace_editor` +15.0% to
+21.0%. The editor's lower gain lowers each task's geomean, since there is one editor process in four
of the five tasks' samples.
