# W3: baseline and bounds for Python process creation

## Setup

- **Simulator:** Scarab, branch `baseline` (`235b8cf`: `main` + `--memtrace_repeat` +
  `PARAMS.golden_cove_pow2`). Pod package `/localdisk/deepanjm/isca-traces/startup-prefetch/scarab/baseline-235b8cf`.
- **What is simulated:** the creation region of each of the 45 fully traced Python creations
  (exec to the first `PyRun_*`, a median of 73.0M instructions), cold, with `--inst_limit` = region
  length. Configurations:

| config | what |
|---|---|
| `base` | `PARAMS.golden_cove` as shipped: stream prefetcher (fills the LLC), FDIP |
| `perfect_l1i`, `perfect_l1d`, `perfect_l2`, `perfect_llc` | one cache level perfect (every access hits) |
| `perfect_all` | all four levels perfect: the bound for any prefetcher of the creation region |
| `pow2_base`, `pow2_perfect_all` | the same on `PARAMS.golden_cove_pow2`. `golden_cove`'s LOG2 set indexing leaves its 3 MB LLC at 2 MB and its L2 at 1 MB effective |
| `self_warm` | the whole process run twice back to back (`--memtrace_repeat=2`, stats every 100K instructions); the creation region's cycles in pass 2 |

- **Also:** the 104 tool-call wrapper processes (52 `sh -c 'env bash -n'`, 52 `bash -n`), whole,
  under `base` and `perfect_all`.
- **Speedup:** IPC(config) / IPC(base) over the same instructions. It is summarised as the
  instruction-weighted ratio over all creations of a script, with the 10th-90th percentile of
  per-creation speedups.

## Checks
- All 613 simulations finished (`results.csv`, every `ok` = 1).
- **Self-warm accounting.** For every creation, pass 1 of the self-warm run is a cold run. Its
  creation-region cycles (summed over the 100K intervals) match the separate `base` run to within
  0.2% (median ratio 0.9989, range 0.9979-1.0000).

## Results (`summary.csv`, `fig_bounds_*.png`, `fig_pow2_sensitivity.png`)

- **Baseline:** IPC of the creation region 1.825, with a per-creation 10th-90th percentile of
  1.821-1.831. Every creation behaves alike.
- **Bounds** (all 45 creations; `_state_anthropic` and `str_replace_editor` agree to within 0.001):

| config | speedup (10th-90th pct.) |
|---|---|
| perfect L1-I | 1.045× (1.044-1.046) |
| perfect L1-D | 1.189× (1.187-1.190) |
| perfect L2 | 1.108× (1.107-1.109) |
| perfect LLC | 1.050× (1.049-1.051) |
| **perfect, all levels** | **1.243× (1.242-1.244)** |
| self-warm | 0.994× (0.992-0.998) |

- **Self-warm is no faster than cold.** Running the same process again immediately, with every
  structure left as the previous run left it, gives 0.994×. Its pass-2 region has 1.2% fewer L2
  misses and 3.2% fewer LLC misses, yet takes 0.7% more cycles. Why was not determined: dirty-line
  writebacks and predictor state trained on the previous run's end are candidates, and neither was
  measured.
  - Either way, warm caches from a previous identical run buy nothing for creation. The ~73M
    instructions stream more state than the caches keep from one run to the next.
  - The earlier study reached the same conclusion on 10M-instruction windows (1-2%).
- **Sensitivity to the set-count bug.** On `golden_cove_pow2`:
  - the baseline IPC rises to 1.909, since the full 2 MiB L2 and 3 MiB LLC are used;
  - the perfect-cache bound over that baseline falls to 1.189×.
  - Headline numbers are reported on `golden_cove` as the plan specifies, with this bracket.
- **Wrapper shells.** They are almost entirely start-up and miss much more, so the bound is higher:

| process | baseline IPC | perfect-cache speedup (p10-p90) |
|---|---|---|
| `sh -c 'env bash -n'` | 0.88 | 2.04× (2.03-2.09) |
| `bash -n` | 1.35 | 1.66× (1.66-1.70) |

## Limits
- User-level traces only. There is no kernel work (exec, page faults, COW copies), and Scarab
  models no TLBs.
- Self-warm uses the identical trace, so it is the literature's optimistic back-to-back reference.
- One task, python3.8.
