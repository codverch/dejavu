# W4: an ideal creation-time prefetcher

**The question.** Every Python process a tool call creates runs almost the same 73M-instruction
creation region (W1: 99.986% identical 32-instruction sequences). Suppose a prefetcher knew,
exactly and in order, every cache line that region will touch. How much faster would the region run
than on golden_cove?

**The answer.** 1.023× at best, out of a possible 1.243×. An oracle list of every line, streamed
into the LLC 200K instructions ahead of use, removes 70% of the region's LLC demand misses and gains
2.3% IPC. Installing the list before the process starts gains 0.6-1.0%, because the list is 7 MB and the
caches it goes into are 1-2 MB. (A first version of the install had a bug that left it at 0.1%; see
"Correction" below.)

## Setup

- **Simulator.** Scarab, branch `ideal-prefetching` (`f469bb7`: `baseline` + `src/prefetcher/startup_pf.c`).
  Pod package `/localdisk/deepanjm/isca-traces/startup-prefetch/scarab/ideal-prefetching-7ca0ce1`
  (same `src/` as `f469bb7`).
- **Units.** The creation regions of W3: the 45 fully traced Python creations of the django-13809 run,
  from exec to the first `PyRun_*`, cold, on `PARAMS.golden_cove` unless marked pow2.
- **Pass 1 (record, `--spf_mode 1`).** Writes every distinct line the region touches, in first-touch order,
  to `records/<cid>.bin`. That is a median of 114,591 lines (7.0 MB) per creation.
- **Pass 2 (replay, `--spf_mode 2`).**

| config | what |
|---|---|
| `instant_{l2,llc,both}` | recorded lines installed in L2, LLC, or both before the first cycle, soonest-needed first until each set is full, no bandwidth cost |
| `stream_{l2,llc}_{2k,20k,200k}` | each line enters the L2 (`umlc`) or LLC (`ul1`) prefetch queue that many instructions before its first use; queues, MSHRs and DRAM bandwidth are modelled |
| `stream_{l2,llc}_bulk` | the same with no lookahead limit: the whole list is issued as fast as the queue accepts it |

- **Sources.**
  - `self`: replay the region's own record. This is the oracle.
  - `prev`: replay the previous creation of the same script, rebased per module for ASLR by
    `lib/rebase.py`. Heap, stack and anonymous lines cannot be rebased and are dropped (a median 49% of
    the record). 39 of the 45 creations have a previous one.
- **Speedup.** IPC(config) / IPC(golden_cove) over the same instructions. It is the
  instruction-weighted ratio over creations, with the 10th-90th percentile of per-creation speedups.
- **Pollution.** A false prediction means the prefetcher replays a creation's record while the harness
  runs instead. The first 20M instructions of 5 harness agent-loop windows are simulated with and
  without one creation's record replayed (`pollution.csv`).

## Checks
- **All runs finished.** 741/741 creation runs and 20/20 pollution runs (`ok` = 1).
- **Record does not perturb timing.** For all 45 creations the record pass's cycles equal W3's `base`
  cycles exactly (`checks.csv`).
- **Lines are streamed, not dropped.** Every stream configuration sends all but 1-2,600 of the ~114.6K
  recorded lines (`spf_sent`). The rest are skipped because their first use has already passed
  (`spf_late_skipped`).
- **Spf off is bit-identical to baseline.** With `spf_mode` 0, the `ideal-prefetching` build and the `baseline` build give identical values for all 5,814 counters on four tool-execution traces (bash, dash, find, git); see `../checks/identical.txt`. The check was run after the W4 simulations, not before them.

## Results (`summary.csv`, `coverage.csv`, `fig_*.png`)

All 45 creations; `_state_anthropic` (26) and `str_replace_editor` (13) agree to within 0.001.

| config | speedup (10th-90th pct.) | demand misses removed at dest. (median) | extra DRAM traffic (median) |
|---|---|---|---|
| perfect, all levels (W3) | 1.243× | — | — |
| perfect L2 / perfect LLC (W3) | 1.108× / 1.050× | — | — |
| instant L2 | 1.006× (1.006-1.007) | 11% | −1.0 MB |
| instant LLC | 1.010× (1.009-1.011) | 28% | −2.0 MB |
| instant L2 + LLC | 1.011× | 28% | −2.0 MB |
| stream L2 2k / 20k / 200k | 1.011× / 1.012× / 1.014× | 60% / 61% / 61% | +1.5 MB |
| stream L2 bulk | 1.001× (1.001-1.002) | 35% | +5.7 MB |
| stream LLC 2k / 20k / 200k | 1.018× / 1.019× / **1.023×** (1.022-1.024) | 62% / 61% / 70% | ≈0 |
| stream LLC bulk | 0.996× (0.993-0.999) | 21% | +3.9 MB |
| prev, stream L2 20k | 1.019× (1.015-1.022) | — | — |
| prev, stream LLC 20k | 1.014× (1.010-1.017) | — | — |
| prev, stream L2 / LLC bulk | 0.997× / 1.004× | — | — |
| pow2 caches, stream L2 / LLC bulk | 1.007× / 1.001× over pow2 base | — | — |

The golden_cove base misses 10.5 MB worth of lines in DRAM per creation.

What these numbers say:

1. **The oracle recovers under a tenth of the bound.** The best configuration (stream LLC 200k) gains
   2.3% of a possible 24.3%. That is 10% of the perfect-cache bound and 46% of the perfect-LLC bound
   (`fig_bound_recovered.png`).
2. **Installing up front is capped by capacity.** The record is 7.0 MB. golden_cove's L2 is 1 MB
   effective and its LLC 2 MB (the LOG2 set-count bug, W3). Installing soonest-needed first until every set
   is full puts exactly 16,384 lines in the L2 and 32,768 in the LLC (`spf_installed`), 43% of the record.
   It removes 11% (L2) and 28% (LLC) of the region's demand misses there, and gains 0.6-1.1%.
3. **Bulk streaming is worse than streaming ahead, for the same reason.** With no lookahead limit, lines
   arrive long before use and are evicted first. Coverage falls to 35% (L2) and 21% (LLC). Traffic rises
   by 5.7 and 3.9 MB, and LLC bulk is a net slowdown. Timeliness here is not about being early enough:
   it is about not being too early for a 1-2 MB cache.
4. **Removing 60% of L2 misses buys 1.2%.** Stream L2 20k removes 61% of the region's L2 demand misses.
   A perfect L2 is worth 10.8%, so a proportional share would be about 6.6%; the measured gain is 1.2%.
   The prefetch queues are saturated: a median of 590K queue-full stalls (`spf_queue_stalls`) against
   114K lines sent. Whether the removed misses were the cheap, overlapped ones, or demands merged into
   still-in-flight prefetches, was **not determined**.
5. **The realistic source beats the oracle into L2.** Replaying the previous creation's rebased record
   (half the lines: library code and data only) gives 1.019× into L2, against 1.012× for the full oracle
   record. Of the rebased lines, a median 99.99% are touched by the new process; they cover 51% of its
   lines (`fig_prev_vs_self.png`). Fewer, all-useful lines contend less for the queue. This supports
   point 4's queue explanation, but does not prove it.
6. **Fixing the cache sizes does not rescue bulk.** With pow2 caches (2 MB L2, 4 MB LLC), bulk streaming
   gains 1.007× (L2) and 1.001× (LLC) over the pow2 base; the pow2 perfect-cache bound is 1.189×.
   Streaming with a lookahead was not run on pow2.
7. **A false positive costs the harness 3-8% of IPC with bulk into L2.** Replaying a creation's record during a
   harness window lowers its IPC by 3-8% (stream L2 bulk) or 1-3.5% (stream LLC bulk). Instant LLC costs
   exactly 0 cycles here: the simulated window starts with cold caches, so the installed lines displace
   nothing the harness would have hit (`fig_pollution.png`).

## What the plan asked for and was not done
- **Trigger from W2's predictor.** Every replay uses the oracle trigger: the prefetcher starts at the
  creation's first instruction. Pollution is measured for a fixed donor record in 5 harness windows,
  not for W2's actual false positives.
- **Per-line accuracy** (prefetched lines used before eviction) is not instrumented in the simulator.
  `rebase.csv`'s `accuracy_upper` is the static overlap of the rebased record with the new process's
  record.
- `fig_wave_l2_spf.png` (the L2 wave, cold vs spf vs perfect) was not made.
- `fig_coverage_accuracy.png` is `fig_coverage.png`: coverage only.

## Reproduce
`./run.sh sim-ideal fetch figures` (stage `sim-ideal` runs `scripts/w4_ideal_prefetch.py` on the pod,
about 2 h on 120 jobs), or `make sim-ideal fetch figures`.

## Correction (2026-09-27)
The first version of `instant` installed every recorded line in cycle 0. All installed lines then
tied on LRU age, so each install into a full set evicted way 0, and a full set kept the lines needed
*last*. It gained 0.1% and removed 0.4-1.8% of misses. The fix (`13528f6`) installs soonest-needed first
and never evicts an installed line. A 5M-instruction test confirmed it: the full record now gives the
same speedup as a record of only those 5M instructions (1.154×). The `instant` rows above are from the
fixed build (`ideal-prefetching-13528f6`); the old runs are kept on the pod under `old_instant/`. Stream
configurations never used this path and were not rerun.
