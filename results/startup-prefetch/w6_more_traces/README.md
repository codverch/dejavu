# W6: the ideal prefetcher on four more SWE-bench tasks, two units per phase

**The question.** W4 measured one task and one phase (Python creation in django-13809). Does the
ideal prefetcher do better on other tasks, or in other phases of a task?

**The answer.** Mostly no. On the Python-heavy phases (harness start-up, environment setup, tool
execution) the oracle gains 1-2%, against a perfect-cache bound of 1.28-1.38×. It gains more
where the base IPC is low and the footprint small: bash wrappers (1.35-1.52×) and the harness
agent loop (1.07-1.11×). Harness exit gains the most (1.12-1.84×), but it is about 1% of a task's
instructions.

## Setup
- **Traces.** Sampled DR runs of `psf__requests-1142`, `pydata__xarray-2905`,
  `sphinx-doc__sphinx-8459` and `sympy__sympy-11618`: 100M instructions of every 1B, all processes
  (pod `/localdisk/deepanjm/deadblock/traces/<task>/trace1`). A unit is one thread of one window.
- **Selection** (`scripts/w6_more_traces.py`, fixed before any simulation).
  - The six phases are those in `selection.csv`.
  - Per phase, the two tasks with the most candidate units are used. In each, the unit of median
    length is chosen.
  - Units under 1M instructions are not candidates.
  - No sympy unit was chosen by this rule.
- **Region.** A unit's first min(instrs, 100M) instructions: the whole unit, not only a process's
  creation region as in W4. Two units hit an instruction Scarab cannot decode (`OP_INV`: sphinx-678
  at 52.3M, xarray-1524 at 5.89M). They are simulated up to 52.0M and 5.8M instead of being
  replaced (`limits.csv`).
- **Configs** (ideal-prefetching package `7ca0ce1`, `PARAMS.golden_cove`, cold):
  - `base`, `perfect_all`, and a record pass;
  - replays of the unit's own record (the oracle) as in W4: `instant_{l2,llc}`,
    `stream_{l2,llc}_{20k,bulk}`.

## Checks
- 108/108 runs finished.
- For all 12 units, the record pass's cycles equal base cycles (`checks.csv`).

## Results (`summary.csv` per unit, `fig_speedup_by_phase.png`)

The table pools each phase's two units: the ratio of sums of instructions over sums of cycles.

| phase | base IPC | perfect caches | ideal, LLC 20k | ideal, L2 20k | ideal, L2 instant | ideal, L2 bulk |
|---|---|---|---|---|---|---|
| harness start-up | 1.75 | 1.276× | 1.018× | 1.009× | 1.001× | 0.992× |
| environment setup (Python) | 1.75 | 1.364× | 1.016× | 1.008× | 1.005× | 1.002× |
| tool execution: Python | 1.80 | 1.295× | 1.012× | 1.002× | 1.001× | 0.998× |
| tool execution: shell (bash) | 1.29 | 1.718× | 1.355× | 1.515× | 1.530× | 1.495× |
| harness: agent loop | 2.57 | 1.231× | 1.075× | 1.109× | 1.014× | 1.009× |
| harness exit | 0.44 | 5.292× | 1.228× | 1.350× | 1.000× | 0.961× |

- **The Python phases reproduce W4.** This holds across Python 3.9-3.14, other tasks, and
  whole 100M windows rather than creation regions. The oracle recovers under a tenth of the bound;
  installing everything at the start recovers nothing.
- **Small footprints are where the oracle works.** A bash wrapper is 1.2M instructions. Its lines
  fit, so even `instant` gives 1.53×.
- **Harness exit is memory-bound** (IPC 0.44): the interpreter tears down its heap. Its bound is
  5.3×, and the oracle recovers 1.23-1.35×.
- **Two units per phase is a small sample.** The harness start-up units are the first 100M of an
  ~18B-instruction phase. How representative any unit is of its phase was not measured.

## Reproduce
`./run.sh sim-more fetch figures`.
