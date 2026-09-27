# The motivation story: what an agent's CPU work does to a Golden Cove core

Written like the motivation section of a SAFARI paper (Pythia MICRO'21, Hermes MICRO'22, Constable
ISCA'24, Athena HPCA'26): one question per figure, in order, each answer a measured number. Every
value is in `numbers.csv`.

## Setup in one paragraph
- **Workload.** 5 SWE-bench tasks (django-13809, requests-1142, xarray-2905, sphinx-8459, sympy-11618),
  solved by SWE-agent with qwen3-coder-30b.
- **Units.** 2 traced windows per task for each of 6 program phases, fixed by position in the run
  (1/3 and 2/3), 54 in all. Harness exit has 1 window per task, and django has none. Each unit is its
  first ≤100M instructions.
- **Simulator.** Scarab `PARAMS.golden_cove`, cold, with 9 configurations per unit: 486 runs.
  - All finished, and all record passes matched base cycles.
  - 7 units stop early at an instruction Scarab cannot decode (`limits.csv`): 5 environment-setup
    python3.14 units at ~5.8M instructions, and 2 agent-loop units at 51.8M and 19.8M.
- **Averages.** AVG weighs each phase equally (geomean for speedups).
- **Other data.** Wall time comes from 30 native runs. Figs. 10, 11 and 14 use W8's 25 tool-call
  Python processes.

## The story

**Q1. Where does an agent's time go?** (`fig_01_wall_time.png`, Hermes-style breakdown)
- 80% is model inference on the GPU (75-85% per task), 15% tool execution, 5% harness.
- The CPU side is a fifth of the wall clock. Whatever we do on the CPU is bounded by that, so the rest of
  the story is about the CPU side.

**Q2. Where do the CPU's cycles go, by phase?** (`fig_02_cpu_by_phase.png`)
- Tool-call Python processes take 47% of CPU cycles: 7.3% in their start-up (first ≤100M instructions)
  and 40% after it.
- Environment setup takes 19%, harness start-up 18%, and the harness loop and exit 16%.
- Start-up of tool processes is a real but small slice: 6.5-8.5% per task.

**Q3. Is the CPU side memory-bound, and at which level?** (`fig_03_headroom_by_phase.png`, Constable Fig. 7 / Hermes Fig. 4)
- Yes. Perfect caches make the phases 22-71% faster, and harness exit 4.3× faster.
- The perfect L1-D alone gives most of that: +18-42%, and +327% at exit.
- A perfect L1-I gives only 2-11%, and doubling the L1-D only 0.4-2%.
- Geomean over the phases other than exit: perfect caches +36%, perfect L1-D +28%, 2× L1-D +1.3%.
- The problem is data, not code, and not the L1-D's size.
- Harness exit (interpreter teardown walking an 80 MB heap) is an outlier that lifts the phase AVG to +65%.

**Q4. Where are loads served?** (`fig_04_loads_served.png`, Hermes Fig. 2/5)
- 91% of loads hit the L1-D (80-98% by phase).
- 3.5% go to the L2, 1.9% to the LLC, and 3.2% to DRAM. DRAM is 7% of loads for shell wrappers and 10%
  at harness exit.

**Q5. Where does load latency go?** (`fig_05_load_latency.png`, Hermes Fig. 3)
- The 9% of loads that miss the L1-D carry 51% of all load latency. DRAM loads alone carry 34%, because
  one costs ~200 cycles against 4 for an L1-D hit (L2 19, LLC 54).
- In tool Python start-up windows, L1-D misses carry 45% of load latency.

**Q6. How many misses per kilo-instruction?** (`fig_06_mpki.png`)
- L1-D MPKI is 9-61 (29 on the phase average). L1-I MPKI is 0.2-1.8.
- L2 MPKI is 1.3-25 and LLC 0.5-17. Exit and shell wrappers are the most memory-intensive.

**Q7. Doesn't golden_cove's prefetcher already handle this?** (`fig_07a/b`, Pythia Fig. 1)
- The stream prefetcher covers 24-56% of LLC misses (40% average) and overpredicts 3-20%.
- It gains only 1.2-3.5% IPC, and 10% at exit. The existing prefetcher helps little in every phase.

**Q8. Why not simply prefetch a start-up's whole footprint early?** (`fig_08_footprint.png`)
- A tool Python process's first 100M instructions touch a median 7.4 MB: 0.8 MB instructions, 2.6 MB
  file-backed data and 4.0 MB private heap/stack.
- That is 150× the L1-D and 2.5× golden_cove's effective L2 + LLC (3 MB).
- Every phase except the shell wrappers exceeds the L2. What is fetched early is evicted before use; W4
  and W8 measured this.

**Q9. Are L1-D misses first touches, or re-misses?** (`fig_09_cold_misses.png`)
- At most 4-7% of L1-D misses in the Python phases are a line's first touch (about 20% for shell
  wrappers and exit); the rest are re-misses of lines already touched (capacity/conflict).
- At the L2, at most 27-73% are first touches.
- The L1-D's problem is not unknown lines but too many live lines. A prefetcher must deliver data just
  in time, again and again, not once.

**Q10. How much of a start-up repeats the previous start-up of the same script?** (`fig_10_repetition.png`, Constable Fig. 3a)
- 43% of a start-up's lines were touched, at the same library-relative address, by the previous
  start-up of the script (31-48% by task).
- Those lines cover 100% of its L1-I misses but only 23% of its L1-D misses (15-29%).
- Code repeats completely; data mostly does not, at least not at the same address.

**Q11. What are the lines that do not repeat?** (`fig_11_line_kinds.png`, Constable Fig. 3b)
- 57% of a start-up's lines are private heap and stack, 32% file-backed data, and 11% instructions.
- The private part is rebuilt at new addresses in every process, so history cannot name it by address.
  Whether it is predictable relative to the heap's base (allocation is likely deterministic) was not
  tested.

**Q12. How long must a remembered start-up wait before it is reused?** (`fig_12_restart_distance.png`, Constable Fig. 3c)
- A script starts again 0.5-2 s later in 48% of cases, 2-10 s in 43%, and 10 s or more in 10%.
  The median is 2.2 s, over 1,760 gaps in 30 native runs.
- No gap is under 0.5 s: between two start-ups of the same script there is always a model call.
- Any state kept for reuse must survive seconds of other activity, which rules out keeping it in the
  caches.

**Q13. Is the headroom broad, or a few outliers?** (`fig_13_per_unit.png`, Athena Fig. 1)
- Across all 54 units, perfect caches give +13.5% to +605%, and 52 of 54 give over +15%.
- The perfect-L1-D line tracks perfect caches closely; 2× L1-D stays near zero throughout.
- The headroom is broad and L1-D-shaped.

**Q14. How much of the start-up headroom can an ideal history-based prefetcher reach?** (`fig_14_startup_ladder.png`, Constable Fig. 7)
The ladder, on tool-call Python processes:

| rung | speedup |
|---|---|
| into L2+LLC at the model call | +0.7% |
| ideal L1-I prefetch | +3.8% |
| ideal L1-D prefetch | +4.6% |
| **both** | **+8.8%** |
| perfect L1 | +32.3% |
| 2× L1-D | +1.8% |

- The ideal predictable prefetcher beats brute force 5×, but reaches only 27% of the perfect-L1 bound.
- The rest is the private data of Q11.

**Q15. What is that worth to a whole task?** (`fig_15_task_worth.png`)
- Start-up is 6.6-8.0% of task CPU cycles.
  - The ideal start-up prefetch saves 0.57% of task CPU time (0.47-0.73%).
  - A perfect L1-D during start-up saves 1.6%, and a perfect L1 1.8%.
- On the wall clock, which is model-dominated (Q1), the upper bounds are 0.15%, 0.39% and 0.44%.

## The one-paragraph version
- An agent's CPU side is a fifth of its wall time. On a Golden Cove core it is strongly L1-D-bound: a
  perfect L1-D is worth +28% outside teardown, while doubling the L1-D is worth 1%.
- The misses are re-misses of a working set 150× the L1-D, not cold misses. golden_cove's prefetcher
  recovers 1-3%.
- Tool-process start-up repeats every few seconds: its code exactly, its file-backed data at the same
  relative place, and its heap at new addresses.
- An ideal prefetcher that knows everything history can predict gains +8.8% on start-up, a quarter of
  the perfect-L1 bound. But start-up is 7% of CPU time, so it is worth 0.6% of a task's CPU time.
- The larger opportunities these graphs point at:
  - the L1-D behaviour of all the Python phases (40% of CPU cycles are tool Python after start-up);
  - whether the heap is predictable relative to its base.

## Files
- **Figures:** `fig_01` … `fig_15` (`.png`, with a caption in `.png.txt`) and `numbers.csv` (every plotted value).
- **Data:** `results.csv`, `selection.csv`, `limits.csv`, `checks.csv`, `footprint.csv`.
- **Scripts:** `../scripts/w9_motivation.py` (runs), `../scripts/figs_w9.py` (figures),
  `../lib/safari_style.py` (style), `../scripts/records_summary.py`, `../scripts/w7_task_speedup.py`
  (Q15).
