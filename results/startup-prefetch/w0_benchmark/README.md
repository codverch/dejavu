# W0: the benchmark

One SWE-bench task, `django__django-13809`, solved by SWE-agent v1.1.0 (local deployment,
qwen3-coder-30b on vLLM, temperature 0, 50-call cap). It was run in two ways:
- **traced under DynamoRIO**, for instruction-level analysis and simulation;
- **natively under perf**, for timing and process accounting. The native runs also cover four more
  tasks, so that W2 has enough trajectories.

## The DynamoRIO run (`dr/`)

- **Policy.** Every process, from its first instruction: a 200M-instruction window every 2B
  instructions (`sampling_policy.json`). DynamoRIO follows every child process.
  - A Python tool process (`_state_anthropic` ~87M instructions, the editor ~150M) is therefore
    traced whole.
  - The harness is traced 10% of the time.
- **Outcome:** rc 0, 26 agent steps, patch submitted.
  - 948 process directories.
  - 119 of them are empty (7-byte raw files). These are processes whose image was replaced by
    `exec` before tracing produced anything, mostly `bash` that exec'd into another program. Their
    code cannot be decoded, and they are skipped.
  - 631 units, converted with 0 failures (`convert_status.json`).
- **Pod path:** `/localdisk/deepanjm/isca-traces/startup-prefetch/w0/dr/django__django-13809/dr1/`.

**Coverage of every phase** (`dr/coverage.csv`; a window's phase is the phase that holds most of
its instructions):

| phase | traced windows | traced instructions | processes |
|---|---|---|---|
| tool execution | 211 | 5.87 B | 187 |
| environment setup | 235 | 2.72 B | 187 |
| harness start-up | 126 | 1.80 B | 1 |
| harness: agent loop | 7 | 1.00 B | 1 |
| child outside tool spans | 1 | 0.3 M | 1 |

Inside the 7 agent-loop windows, the per-window phase mix attributes:
- 27.7M instructions to tool-call handling (5 windows);
- 3.9M to waiting on the model (2 windows).

So all agent-loop phases are traced. **Harness exit has no window**: at 200M every 2B, no window
fell inside it.

## The native runs (`native/<task>/run1..6/`)

- **Scale.** 30 runs: 6 each of django-13809, requests-1142, xarray-2905, sphinx-8459 and
  sympy-11618. All exited rc 0, with 25-50 agent steps each.
- **Pinning.** Each run was pinned to 4 physical cores plus their SMT siblings. The cores were
  measured idle (at most 4.8% busy over 5 s) just before the run (`cpu_idle.json`).
- **Recording.** `perf record -C <cpus> -e instructions/period=1000000/u --sample-cpu -k CLOCK_MONOTONIC`
  with task events. `native_summary.py` keeps only the harness and its descendants, found through
  fork events.
- **What is exact.**
  - Fork, exec and exit events and their times are exact.
  - Whether a process is Python comes from its exec events.
  - An instruction count is samples × 1M, exact to within 1M, *if* the event was not throttled.
- **Throttling.** The kernel throttled the event on every run (THROTTLE records in
  `perf_stats.txt`). `throttle.json` bounds the instructions lost by throttled time × the highest
  per-CPU rate observed (≈10 B instr/s, a loose bound).
  - The bound is below 5% for 23 runs.
  - **It exceeds 5% for 7 runs:** sphinx run3 15.3%, xarray run4 12.3%, sphinx run2 8.8%, sympy
    run4 7.2%, sympy run6 6.9%, sphinx run5 5.6%, requests run6 5.1%.
  - This is a failed acceptance check for instruction counts in those runs. It does not affect W2,
    which uses exec events and timestamps; task events are not throttled.
- **Command lines are mostly missing.** `procs.jsonl` (a 10 ms `/proc` poll) caught only a few
  processes, because native tool processes live for milliseconds. Which script a Python process
  ran is therefore read from the exec chain (the shebang script's name, cut to 15 characters by
  the kernel).
- **Pod path:** `/localdisk/deepanjm/isca-traces/startup-prefetch/native/`.

## Reproduce
`./run.sh trace-dr trace-native convert summarize` (see `../run.sh`, `../config.env`).
