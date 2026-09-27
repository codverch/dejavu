# W7: whole-task speedup

**The question.** What is the ideal prefetcher worth to a whole SWE-bench task?

**The answer.**
- **CPU time:** 1.03-1.04× on all five tasks. A perfect cache hierarchy would give 1.28-1.35×.
- **Wall clock:** at most 1.004-1.008×, because 75-85% of a task's wall time is model inference
  on the GPU. A perfect cache hierarchy would give at most 1.036-1.058×.

## Method (`scripts/w7_task_speedup.py`)
1. **Instruction mix.** Instructions per (phase, process kind) for each whole task come from its DR
   attribution (`phase_mix.csv`, `scripts/phase_mix.py`). Each sampled window is weighted by
   period / window length, so the harness's 10%-sampled phases count in full. Kinds are harness,
   python, shell, and other.
2. **Per-phase speedup and base CPI** come from W6, pooled over the phase's two units.
   - Python processes in tool execution take the W6 "tool execution: Python" numbers.
   - Environment setup takes W6 "environment setup"; shells take W6 "shell".
   - Harness phases take their own W6 units.
   - Work of kind "other" (git, sed, find, ...; 1.7-8.0% of a task's instructions) was not
     simulated. It keeps speedup 1 and takes the simulated CPI of its group.
   - Django has no harness-exit window, so it has no harness-exit instructions.
3. **CPU-time speedup** = Σ base cycles / Σ (base cycles / phase speedup).
4. **Wall clock.** Each of the 6 native runs per task is split by an exact innermost-span sweep over
   its swetrace spans, as in the Q1 breakdown (`wall_split.csv`):
   - model: `http.roundtrip`, `http.read_body`;
   - tool: `tool.exec`, `tool.get_state`;
   - harness: everything else.

   Model time is unchanged. Tool and harness time are divided by the CPU speedup of the tool-side
   and harness-side phases. **This is an upper bound:** it treats all tool and harness wall time as
   user-mode CPU work on the simulated core, but part of it is container exec, kernel time and I/O.
   The plotted bar is the mean over the 6 runs; min-max is in `task_speedup.csv`.

## Results (`task_speedup.csv`, `fig_task_speedup.png`)

| task | model / tool / harness wall | CPU: perfect | CPU: ideal LLC 20k | CPU: ideal L2 20k | wall: perfect | wall: ideal LLC 20k |
|---|---|---|---|---|---|---|
| django-13809 | 75 / 19 / 6% | 1.278× | 1.033× | 1.034× | ≤1.058× | ≤1.008× |
| requests-1142 | 82 / 14 / 5% | 1.346× | 1.038× | 1.041× | ≤1.048× | ≤1.006× |
| xarray-2905 | 79 / 17 / 5% | 1.322× | 1.028× | 1.026× | ≤1.053× | ≤1.005× |
| sphinx-8459 | 85 / 11 / 4% | 1.313× | 1.032× | 1.032× | ≤1.036× | ≤1.004× |
| sympy-11618 | 79 / 17 / 5% | 1.331× | 1.035× | 1.036× | ≤1.053× | ≤1.006× |

- **The simulated phases cover most of each task.** They account for 92-98% of its instructions
  (`simulated_instr_frac`).
- **Harness-side work gains more than tool-side work** (1.03-1.08× vs 1.00-1.03× across the two ideal configs). The harness
  gain comes from the agent loop and harness exit (W6).

## Caveats
- **Phase speedups rest on two units per phase** (W6). Units are at most 100M instructions of
  phases that run for billions.
- **The instruction mix is from DR-traced runs.** A traced harness waits longer for the model, and
  may execute more polling instructions than a native one. This was not corrected.
- **The wall-clock bound ignores overlap.** It assumes tool and harness time are on the critical
  path. They are, in SWE-agent's serial loop, but only their CPU-busy part can shrink.

## Reproduce
`./run.sh sim-more fetch figures` (stage `sim-more` also writes the phase mix on the pod).
