# Plan: ideal prefetching for Python process creation in coding agents (repository: dejavu)

Owner: deepanjm (GitHub `codverch`). Written 2026-09-26. This file is the single source of
truth for every agent working on this study. Read all of it before starting a workstream.

---------------------------------------------------------------------------------------------
## 0. Goal, hypothesis, and what counts as success
---------------------------------------------------------------------------------------------

**Observation (prior work, `mise/results/swe-bench-traces/e2e-uarch/README.md`):**
- **Tool processes repeat themselves.** Every agent step starts Python processes (the
  `_state_anthropic` probe after every action, `str_replace_editor`, test scripts).
  Consecutive start-ups execute 99.9% identical instruction sequences.
- **Warm caches do not help much.** Keeping caches warm saves only 1-2% of start-up cycles,
  because the start-up footprint does not fit.
- **Perfect caches would.** Making the caches perfect saves 21-29% of the cycles of the first
  10M instructions of start-up (`data/perfect/results.csv`).
- **The misses have a single dominant source.** ld.so relocation is 7% of instructions but
  ~72% of L2 misses.

**Hypothesis.** The cache blocks touched while a Python process is being created are the same
every time (modulo ASLR), and whether a tool call will create one is predictable from the
tool call itself. So a prefetcher told *when* a Python process is about to be created, and
*which* blocks it will touch, can recover a large part of the perfect-cache bound.

**The study must answer, with numbers:**
- **Q1:** What exactly happens every time a Python process is created for a tool, and how
  often is it the same?
- **Q2:** How often do tool calls create Python processes, and of which kinds?
- **Q3:** How accurately, and how far ahead, can we predict that a tool call will create one?
- **Q4:** How much of the perfect-cache bound does an ideal (oracle) creation-time prefetcher
  recover? Break it down by cache level, prefetch timing and destination, and give the
  traffic cost.

If either fails, report that plainly. A negative result is a result.

---------------------------------------------------------------------------------------------
## RULE ZERO — DO NOT FABRICATE ANY RESULTS
---------------------------------------------------------------------------------------------

Read this before anything else. It overrides every deadline and every other instruction.

- **Every number, figure, table and claim must come from a file you produced or read in this
  study, with the command that produced it recorded.** No number typed from memory, estimated,
  "expected", extrapolated, or copied from a paper as if it were ours.
- **If something did not run, failed, or was skipped, write exactly that.**
  - "Not run", "failed: <error>", "excluded: <reason>, <share of data>".
  - Never fill a gap with a plausible value. Never smooth, pad or re-label data to make a
    figure look complete.
  - Never mark an acceptance check as passed without running it.
- **A result that contradicts the hypothesis is reported as prominently as one that supports
  it.** Do not tune the setup after seeing the results in order to reach a success criterion.
  If you change the method, state what changed and why, and report both versions.
- **Citations: cite only papers you actually opened.** Mark each one [read] or [abstract
  only]. Never invent a paper, an author, a venue, or a number from a paper.
- **Keep assumptions separate from findings.** Every README separates *measured* from
  *assumed* from *not verified*.
- **When unsure, stop and ask the user.** Do not guess.

Any agent that finds a fabricated or unverifiable number, including in another workstream's
output, flags it in that workstream's STATUS.md and tells the user.

---------------------------------------------------------------------------------------------
## MODELLING METHODOLOGY — learn it from top-tier architecture papers first
---------------------------------------------------------------------------------------------

Before designing any simulation (W3, W4) or characterisation (W0-W2), read how top-tier
computer-architecture papers (ISCA, MICRO, HPCA, ASPLOS) model and evaluate this kind of
thing, and write down what you adopt.

- **Deliverable:** `results/startup-prefetch/methodology/METHODOLOGY.md`, owned by W3 and
  written before any `sim-*` stage runs. For each practice: which paper it comes from (with
  the [read]/[abstract only] marker), what the practice is, and exactly how our experiment
  applies it, or why it does not apply.
- **Start from** `mise/characterization/methodology/literature_review.md`. It is already
  written and verified for the cold/warm question; extend it, don't redo it.

Read at least these (find each, confirm it exists, read its methodology and evaluation
sections):
1. **Sampling and warm-up:**
   - SMARTS (Wunderlich et al., ISCA 2003);
   - SimPoint (Sherwood et al., ASPLOS 2002).
   - What to take: warm-up bias, and why a fixed warm-up would erase the cold-start effect we
     study.
2. **Cold, warm and lukewarm evaluation of short-lived code:**
   - Lukewarm serverless functions / Jukebox (Schall et al., ISCA 2022);
   - Ignite (Schall et al., MICRO 2023).
   - What to take: warmth states, flush-all vs back-to-back baselines, record/replay
     prefetching of an invocation's misses (the closest prior work to W4), and how they report
     coverage and speedup.
3. **Instruction and temporal-stream prefetching:**
   - Temporal instruction fetch streaming (Ferdman et al., MICRO 2008);
   - Proactive instruction fetch (Ferdman et al., MICRO 2011).
   - What to take: record/replay of miss streams, lookahead, and how to evaluate timeliness.
4. **Data prefetcher evaluation:**
   - Spatial memory streaming (Somogyi et al., ISCA 2006);
   - Best-Offset (Michaud, HPCA 2016);
   - Bingo (Bakhshalipour et al., HPCA 2019);
   - Feedback-directed prefetching (Srinath et al., HPCA 2007).
   - What to take: the definitions of coverage, accuracy, timeliness and extra traffic, and
     how ideal or oracle prefetchers are used as upper bounds.
5. **Simulator trust:**
   - "Architectural simulators considered harmful" (Nowatzki et al., IEEE Micro 2015);
   - Kanev et al., ISCA 2015 (profiling a warehouse-scale computer).
   - What to take: validating the simulator against hardware where possible, not quoting MPKI
     as cost, and representativeness.

Practices every modelling result must follow (derived from the above; verify them in your
reading):
- **Report bounds, not a single point.** Show cold, self-warm, perfect, and the mechanism,
  side by side on the same units.
- **Report the ideal mechanism's cost:** traffic, MSHR occupancy, late prefetches. An "ideal"
  prefetcher with free bandwidth is labelled as such.
- **Rank structures by cycles, not by MPKI.**
- **State the simulator's blind spots** (no kernel, no TLB model, the golden_cove set-count
  bug, no wrong-path fidelity), and where possible cross-check the direction of an effect on
  native hardware counters.
- **Report variation over invocations.** Give a median with a 10th-90th percentile band or a
  confidence interval; never a single run.
- **Do not reuse test data to build a predictor or choose a parameter.** Hold out by task.

---------------------------------------------------------------------------------------------
## 1. Definitions (use these words, and only these, in every figure and file)
---------------------------------------------------------------------------------------------

- **Tool call:** one action the model emits and the harness executes. It spans one
  `tool.exec` and the `tool.get_state` that follows it in `swetrace.ndjson`. Note that
  `tool.get_state` *contains* a nested `tool.exec`; always merge intervals.
- **Tool execution:** every process forked inside a tool call.
- **Python process creation:** a Python process running from its `exec` to the first
  instruction of the tool's own code, i.e. the first `PyRun_*`/`pymain_run_python` call.
  - It consists of ld.so (load and map, relocation, symbol lookup), libc init, interpreter
    init (codecs, types, `site`, `.pyc` unmarshal, ...) and the imports that happen before
    the tool script runs.
  - Find the boundary from symbols, as in
    `mise/results/swe-bench-traces/e2e-uarch/scripts/similarity.py`.
  - For static builds (python3.9/3.10) whose symbol is not exported, fall back to `.symtab`,
    then to the libc-to-exe transition; state which method was used.
- **Creation region:** the instructions of one Python process creation.
- **Phases of an agent step (native wall time):** model inference (`http.roundtrip`),
  harness (step time outside model and tool spans), tool execution.
- **Cold / self-warm / perfect:** Scarab starting from empty state / pass 2 of
  `--memtrace_repeat=2` / `--perfect_{icache,dcache,mlc,l1}`.
  - Scarab's `l1` is the LLC.
  - The perfect configurations are the upper bound for any prefetcher into that level.

---------------------------------------------------------------------------------------------
## 2. Ground rules for every agent
---------------------------------------------------------------------------------------------

### 2.1 Paths
- **Repository.** "Scarab" means the project's Scarab repository **dejavu**:
  `https://github.com/codverch/dejavu` (renamed from `codverch/mise`; the local `origin` already
  points at the new URL).
  - A fresh, clean clone of `main` (`79dadf3`) is at **`/h/deepanjm/dejavu`**. All new work starts
    from it.
  - This plan lives at `/h/deepanjm/dejavu/results/startup-prefetch/PLAN.md` and is the only
    copy (`/h/deepanjm/mise/results/startup-prefetch/plan..md` is a symlink to it).
- **The old clone `/h/deepanjm/mise` is read-only for this study.** It is on branch
  `warm-execution` with another session's uncommitted changes. Never modify, stash, commit, reset
  or move it. Read prior results from it (`/h/deepanjm/mise/results/...`,
  `/h/deepanjm/mise/characterization/...`); those paths are real and correct.
- **Worktrees (created by W3 as its first action, before anyone else writes results):**
  - `/h/deepanjm/dejavu-wt/baseline` on branch `baseline`
  - `/h/deepanjm/dejavu-wt/ideal-prefetching` on branch `ideal-prefetching`
- **Results.** Every result goes in
  `/h/deepanjm/dejavu-wt/ideal-prefetching/results/startup-prefetch/<workstream>/`, with the
  workstream directories `w0_benchmark`, `w1_creation`, `w2_prediction`, `w3_baseline`,
  `w4_ideal_prefetch`, `w5_report`.
  - The baseline simulation results also go in
    `/h/deepanjm/dejavu-wt/baseline/results/startup-prefetch/w3_baseline/`.
  - Copy this PLAN.md into both worktrees at `results/startup-prefetch/PLAN.md`.
- **Pod (compute).** `kubectl exec -n deepanjm deepanjm-a100 -c work -- ...`, working
  directory `/localdisk/deepanjm/isca-traces/startup-prefetch/`. The pod cannot write the NFS
  home (root is squashed) and does not mount `/h`.
  - Edit scripts on phoebe-login.
  - Send scripts with `kubectl exec -i ... bash -c 'cat > file' < local`.
  - Copy results back with `tar | tar`.
- **Share paths.** Every message an agent sends the user ends with the absolute path of every
  result it produced.

### 2.2 Provenance (non-negotiable)
Every result directory has a `README.md` that states:
- the exact command(s) that produced it, with the git SHA of the worktree;
- its inputs (absolute paths, pod or host);
- the date;
- what each file is;
- the checks that were run, with their outcome.

Every number quoted in a README must come from a file in that directory. Never type a number
from memory. **No fabricated or extrapolated results**: if something did not run, say it did
not run.

### 2.3 Figures
- **Labelling like Akshitha Sriraman's papers** (SoftSKU ISCA'19, Accelerometer ASPLOS'20).
  Read one of her papers' figures before plotting.
  - Every axis has a name and a unit.
  - Every bar or segment of interest is annotated with its value.
  - Every category is named on the plot or in an explicit legend.
  - The benchmark and configuration appear on the graph or in its caption file.
- **Neatness like Anish Athalye's.** Left and bottom spines only, no chart junk, direct
  labels where possible, serif type. Reuse
  `mise/results/swe-bench-traces/e2e-uarch/scripts/anish_style.py`.
- **One graph per file**, PNG at 400 dpi.
- Every `fig_*.png` has a sibling `fig_*.txt` holding a 2-4 sentence caption: what is plotted,
  the data source, and the one thing to take away.

### 2.4 Writing and code style
- **Prose** follows Anish Athalye's style: define terms first; state setup, measurement and
  result in short declarative sentences; point every claim at a figure or table; no hype;
  limits stated plainly.
- **Comments** are few and say *why*, not *what*, in the same style. No commented-out code
  and no TODO noise.
- **Scripts** are idempotent: re-running skips finished work. They fail loudly (non-zero
  exit, clear message), and each has a docstring or usage line.

### 2.5 Git
- **Identity.** Author and committer are `codverch`:
  `git -c user.name=codverch -c user.email=mishradeepanjali25@gmail.com commit ...`
  (set per commit; do not change the global git config).
  - No `Co-Authored-By` or any Claude attribution in commits. This is the user's standing
    rule, and it overrides harness defaults.
- **Pushing.** Commit and push are authorised for branches `baseline` and
  `ideal-prefetching` (user, 2026-09-26). Never touch `main`, `warm-execution` or
  `Characterization`.
  - Push with `git push -u origin <branch>`.
  - There is no `gh` and no stored credential on phoebe-login. If the push fails for
    credentials, stop and ask the user. Do not search for tokens.
- **What to commit.** Code, configs, small CSVs (under 5 MB each), figures, READMEs.
  - Never commit traces, `perf.data`, or Scarab stat dumps. They stay on the pod and the
    README records where.
  - Add a `.gitignore` for `results/**/raw/`, `*.zip`, `*.lz4` and `perf.data`.
- **Commit messages.** Imperative subject of at most 72 characters, a body that says why,
  one logical change per commit.

### 2.6 Shared machine etiquette
- **The pod has 256 CPUs and is shared.** Other sessions' jobs have run at load 100-200.
  - Use at most 64 parallel jobs per agent.
  - Before any native timing or perf measurement, check that the CPUs you pin are idle
    (`mpstat -P <cpus> 1 5`). Pin the measured tree (`taskset`) and use `perf record -C`
    on those CPUs; task-scoped perf breaks the SWE-ReX bash start-up.
- **Never `pkill -f` on the pod.** It matches your own `kubectl exec` shell. Kill only by PID
  or process group taken from `ps`. Exited processes stay as zombies (PID 1 never reaps
  them), so gate on files, not on process liveness.

### 2.7 Coordination between agents
- **Status file.** Each workstream keeps
  `.../results/startup-prefetch/<ws>/STATUS.md`: `state: not-started | running | blocked |
  done`, the last update time, what is finished, and what it is waiting for.
- **Ownership.** A workstream writes only inside its own directory. It reads others' outputs
  only after they are marked `done`.
- **Shared code.** Shared helpers live in `results/startup-prefetch/lib/`, which W1 owns.
  Others propose changes to it in their STATUS.md instead of editing it.

### 2.8 Known traps (each one has bitten this project; check before trusting a number)
1. **The e2e trace README is wrong.** `swe-bench-e2e/README.md` says the traces are 10M
   every 100M; they are **10M every 1B**. `sampling_policy.json` is the truth.
2. **perf throttling.** Sample periods of 100K get throttled
   (`kernel.perf_event_max_sample_rate` is lowered to 7000), and a throttled event stops
   counting.
   - Use a period of at least 1M, written as `instructions/period=1000000/u`, because `-c` is
     global across events.
   - Check the THROTTLE count (`perf report --stats`) and bound the loss.
   - Validate against `perf stat` counting mode: `python -c pass` is 71M instructions for
     py3.8 and 83M for py3.9.
3. **perf clock.** PMU sampling needs an NMI-safe clock. Use `-k CLOCK_MONOTONIC` and record
   the offset to wall time.
4. **Span nesting.** swetrace `tool.get_state` contains a nested `tool.exec`: merge intervals
   before counting.
5. **Scarab repeat mode.** `--memtrace_repeat` asserts on traces with no control-flow op;
   use repeat=1 for them.
6. **Undecodable instructions.** Scarab `OP_INV` asserts on some python3.14 conda/pip
   windows. Exclude them and report the excluded instruction share.
7. **Scarab stat file names.** Periodic CSV rows are `NAME_count` (interval) and
   `NAME_total_count` (cumulative). Strip the suffix, or every counter reads 0.
8. **Scarab L1-D miss counts** include accesses that merge into an in-flight MSHR. Do not
   compare them to an LRU line model without saying so.
9. **golden_cove set-count bug.** `cache_lib` masks the set index with `LOG2(num_sets)`, so
   the 3 MB/16-way LLC (3072 sets) acts as 2 MB, and the L2 (`mlc_size 2097000`, a typo)
   acts as 1 MB. See W3 for how to handle it.
10. **Tracing artefacts under DynamoRIO.**
    - `GLIBC_TUNABLES` (needed only for DR) adds `__tunables_init`, ~41K instructions per
      native process.
    - The `drpatch` sitecustomize is on `PYTHONPATH`.
    - Label both as artefacts and exclude them from "creation" counts where possible.
11. **DR slows the harness ~10×**, and SWE-agent's timeouts are wall-clock. Never use DR runs
    for time; use native runs.
12. **OpenBLAS spin threads.** The harness's numpy starts 64 OpenBLAS threads that
    spin-wait. They are real instructions, but not harness work; show them separately.
13. **Stripped python3.10.** The python3.10 binary is stripped: symbol-level attribution
    fails for 59% of its instructions. Say so.
14. **Viewing figures.** The Read tool's hook sometimes times out when viewing figures. If a
    figure could not be viewed, write that in STATUS.md.

---------------------------------------------------------------------------------------------
## 3. Workstreams
---------------------------------------------------------------------------------------------

Dependency graph:
```
W3a (worktrees, 10 min) --> everyone writes results
W0 (benchmark) --------------> W1 (creation analysis) ----------> W4 (ideal prefetch) --> W5
      \--------------------> W2 (taxonomy + prediction) --------^
W3b (baseline Scarab: build, config, regression; can build before W0 ends) --^
```

### W0 — Benchmark: one SWE-bench task, every phase (plan step 1)

**Task.** `django__django-13809`, with SWE-agent v1.1.0 as in
`swe-bench-e2e/scripts/trace_e2e.sh` (the deployment/model/call-cap settings below).
Reasons: it has the most prior data (e2e, phase-block-locality, native runs), and it uses
python3.8 with an unstripped libpython, so attribution is exact.
- Settings: `deployment=local`, qwen3-coder-30b on vLLM :8000, temperature 0, 50-call cap,
  60k max input tokens.

**Produce three things, all under `w0_benchmark/`:**

1. **`native/run{1..5}/`: five native runs**, with no tracer, run sequentially on an idle,
   pinned CPU set.
   - Record `swetrace.ndjson` and a per-process perf record:
     `instructions/period=1000000/u`, `--sample-cpu`, `-k CLOCK_MONOTONIC`,
     `--show-task-events`, on pinned CPUs with `-C`.
   - Post-process with
     `mise/results/swe-bench-traces/e2e-uarch/scripts/native_post.py` and
     `native_throttle.py`.
   - These give wall time per phase, the process tree (fork/exec/exit), and instructions per
     process and per interval.
   - Five runs give the run-to-run spread; the trajectory can differ between runs even at
     temperature 0.
2. **`dr/`: one DynamoRIO-traced run** that covers every phase.
   - Harness start-up, environment setup, and the agent loop: model wait, tool-call handling,
     tool execution, exit.
   - Policy: `-trace_for_instrs 200000000 -retrace_every_instrs 1800000000
     -no_split_windows`, following children.
     - Every Python tool process under 200M instructions is traced whole from its first
       instruction; `_state_anthropic` is ~85M and `str_replace_editor` ~150M natively.
     - The harness is sampled at 200M per 2B.
   - Split and convert with the e2e pipeline (`swe-bench-e2e/scripts/e2e_post.py` and its
     raw splitter). Note that only window 0 of a multi-window raw directory converts
     directly.
   - Record `procs.jsonl` and `pyspy.jsonl` as in `trace_e2e.sh`.
   - **Coverage table** (`dr/coverage.csv`): for each phase, the number of traced windows
     and traced instructions. Every phase must have at least one window; if one does not,
     say which and why.
3. **`README.md`**:
   - the trajectory: steps, tool calls, submitted or not;
   - native vs DR comparison of the number of steps and tool calls;
   - the exact commands;
   - the pod paths of all raw data.

**Acceptance.**
- Five native runs with rc=0, throttle-loss bound under 5% each.
- One DR run with rc=0 and every phase covered.
- Every Python tool process of the DR run traced whole, or its truncation listed.

### W1 — What happens at Python process creation, and how often it is the same (plan steps 2 and 3)

**Input:** W0's DR run (instruction-level), and W0's native runs (timing and the process tree).

**Figures (`w1_creation/`):**

1. **`fig_flowchart.png` (+ `.dot`/`.svg` source): the sequence of operations of one tool
   call, from the harness writing the command to the tool's first instruction.**
   - Nodes: the harness write, `sh -c`, `env`, `bash -n`, `exec python3`, ld.so load and
     map, relocation, symbol lookup, libc init, interpreter init (codec/locale, type setup,
     `site`, `.pyc` unmarshal, pre-script imports), then the tool's own code, and teardown;
     the same again for `_state_anthropic`.
   - Every node is annotated with its median instructions and wall time (native), and its
     share of creation-region L2 misses (from W3's cold baseline, once available).
   - Build it from data (exact phase boundaries from symbols; the process chain from
     fork/exec events). Do not draw it by hand.
2. **`fig_identical_cdf.png`: how often the sequence is the same.**
   - For every pair of consecutive creations of the same tool class, plot the CDF of the
     share of creation-region instruction positions whose 32-instruction sequence appears in
     the previous creation, after ASLR is removed (canonical PC = file + link-time address).
   - Also plot a CDF of the exact common prefix length.
3. **`fig_identical_by_operation.png`: identity per flowchart operation.** For each
   operation, the share of invocations whose instruction count equals the most common count
   exactly, and the coefficient of variation.
4. **`fig_timeline.png`: the task timeline.**
   - x is native wall time.
   - Lanes: model inference, harness, tool execution.
   - Below them, every Python process creation is a mark coloured by its identical-sequence
     share with the previous creation.
   - A counter shows the cumulative instructions of repeated creation work.
5. **`fig_operation_breakdown.png`: breakdown of the types of operations.**
   - Follow the taxonomy of the paper "Agentic coding in the wild". Find it (arXiv or ACL
     Anthology), read how it categorises agent operations and how it plots them, and apply
     the same categories to our tool calls and creation-region operations.
   - If the paper cannot be found or does not define a usable taxonomy, stop this item and
     report it. Do not invent its categories.

**Tables:** `creation_regions.csv` (one row per creation: boundaries, instructions per
operation) and `pairs.csv`.

**Acceptance.**
- Creation-region boundaries are found for at least 95% of Python creations; the rest are
  listed with the reason.
- The flowchart's node sums match the whole creation region to within 1%.

### W2 — Which tool calls create Python processes, and can we predict it (plan steps 4 and 5)

**Input.** W0's native runs, plus every existing native trajectory with a `procs.csv` and
spans, to get enough trajectories for a CDF:
- `/localdisk/deepanjm/isca-traces/uarch-e2e/native/*/run2/` (5 tasks);
- the 30 native runs used by `hint-vs-zygote`
  (`/localdisk/deepanjm/agentic-core/dsx_runs/`, 5 tasks).

Check which of these have fork/exec events; if some lack them, run additional native runs of
the same five tasks with the W0 native recipe. Target at least 30 trajectories.

**Step 4 (`w2_prediction/`):**
- `tool_taxonomy.csv`: every tool call, with its type (derived from the action: the first
  command word, or the tool name for SWE-agent tools), whether it created at least one
  Python process (from exec events), which interpreter and script, and how many.
- `fig_tool_types.png`: per tool type, the number of calls and the share that create Python,
  annotated.
- `fig_python_per_step.png`: Python creations per agent step.
- **`fig_most_invoked_tools.png`: "Most invoked tools and their frequency"**, drawn like Fig. 21
  of "Agentic coding in the wild" (arXiv 2608.00101): vertical bars sorted by descending share,
  y-axis "Invocation %", the value above every bar, the top 15 plus a grey "Others" bar, names
  rotated 45°. Count model-invoked tool calls only (actions), not the harness's automatic state
  probe or setup commands.
  - The paper's unit is a named tool. SWE-agent has three (`bash`, `str_replace_editor`,
    `submit`), so also draw `fig_most_invoked_tools_by_name.png` at exactly that granularity.
  - The main figure splits the editor by subcommand, since it corresponds to Copilot's separate
    edit tools, and `bash` by its first command word. The caption must say so.
- State the trivial fact explicitly: `tool.get_state` runs `_state_anthropic` (Python) after
  every action. Report creation rates with and without it.

**Step 5 (`w2_prediction/`):**
- **Prediction point.** The end of `response.parse`, when the action string is known and
  before `tool.exec` starts.
- **Predictors** (define them before measuring; report all):
  - (P0) always predict "creates Python";
  - (P1) a rule on the action string, e.g. the first word is in
    {`python*`, `pytest`, `str_replace_editor`, `submit`, ...}. Learn the rule
    leave-one-task-out: fit on four tasks, test on the fifth. No test data in the rule.
  - (P2) the previous tool call's outcome;
  - (P3) P1 or P2.
- **Figures:**
  - `fig_accuracy_cdf.png`: CDF over trajectories of per-trajectory accuracy, with precision
    and recall as separate CDFs.
  - `fig_leadtime_cdf.png`: CDF of the lead time from the prediction point to the Python
    `exec`, in µs and in harness instructions. Mark on it the time needed to issue the
    creation region's prefetches, from W4's traffic numbers once available.
- **Also:** predicting *which* script (`_state` / editor / other), with a confusion matrix.

**Acceptance.** At least 30 trajectories, or the reason why not. Leave-one-task-out is
enforced in code.

### W3 — Scarab baseline branch and the one-click infrastructure (plan step 6, first half)

**W3a (first, about 10 minutes):**
```
cd /h/deepanjm/dejavu
git worktree add /h/deepanjm/dejavu-wt/baseline -b baseline main
git worktree add /h/deepanjm/dejavu-wt/ideal-prefetching -b ideal-prefetching main
```
- Copy `results/startup-prefetch/PLAN.md` from `/h/deepanjm/dejavu` into both worktrees. After
  that, the copy on `ideal-prefetching` is the one agents update, and commits carry it.
- Announce the worktrees in STATUS.md.
- `ideal-prefetching` is later rebased onto `baseline`, so it contains the infrastructure.

**W3b (`baseline` branch):**
- **Warm execution first.** Cold vs self-warm needs `--memtrace_repeat`, which is not on
  `main`. It exists only as uncommitted changes in the old clone, saved as
  `/h/deepanjm/dejavu/results/startup-prefetch/memtrace_repeat.diff.txt` (first line: base SHA;
  the rest: a `git diff` that applies cleanly to `79dadf3`, checked 2026-09-26).
  - Apply it to `baseline` as its own commit, with a message that says what it does (replay one
    trace N times without resetting micro-architectural state; stats per pass as `.pass.<k>`).
  - Verify that with `--memtrace_repeat=1` the results are bit-identical to `main`.
- **Build.** Build on phoebe-login with `/h/deepanjm/agentic-stuff/env.sh`, `SCARAB_ROOT`
  set to the worktree, `ASM=as` (see the memory note on the native install), and
  `make -j4 -C src/build/opt`.
  - The CMake cache holds absolute paths, so every worktree needs its own build.
  - Package the binary with its conda libraries for the pod, as in
    `/localdisk/deepanjm/isca-traces/uarch-e2e/mise-scarab/` (run with
    `LD_LIBRARY_PATH=lib`).
- **Configs.** `PARAMS.golden_cove` unchanged is the primary configuration, for
  comparability with prior results and upstream. Also add `PARAMS.golden_cove_pow2`, where
  the set counts are powers of two so the nominal sizes are real (L2 2 MiB/8-way, LLC
  4 MiB/16-way, or 3 MiB/12-way at 4096 sets). Report every headline number under both,
  and state the LOG2 bug in the README.
- **One-click runner** in `results/startup-prefetch/`:
  - `config.env`: task, trace paths, Scarab package, job count, configurations.
  - `run.sh <stage>|all`, with stages `trace-native`, `trace-dr`, `convert`, `analyze`,
    `build`, `sim-baseline`, `sim-ideal`, `figures`, `report`. It is idempotent, logs to
    `logs/<stage>.log`, and exits non-zero on any check failure.
  - `Makefile` targets that call the same stages (`make all`).
  - A `README.md` that explains how to launch everything with one command:
    `./run.sh all`.
- **Methodology first.** Write `methodology/METHODOLOGY.md` (see MODELLING METHODOLOGY) and
  have it in STATUS.md before any `sim-*` stage runs.
- **Baseline simulations** (`w3_baseline/`): every creation region of the W0 DR run, plus the
  harness windows (each phase), cold and self-warm, periodic every 10K instructions (reuse
  `e2e-uarch/scripts/run_waves.py`). Also every perfect configuration:
  `--perfect_icache`, `--perfect_dcache`, `--perfect_mlc`, `--perfect_l1` (LLC), and all
  four together.
- **Regression checks** in `run.sh` (they fail loudly):
  - Scarab's instruction count equals the trace's to within 0.1%.
  - Cold IPC of python3.8 `_state` creation windows matches `e2e-uarch` (1.68 ± 0.05).
  - Cycles with all four perfect ≤ cycles with any one perfect ≤ baseline cycles.
- **Commit and push** `baseline`.

### W4 — `ideal-prefetching` branch: two-pass ideal creation-time prefetcher (plan step 6, second half)

Start from `baseline`: `git rebase baseline` on the `ideal-prefetching` branch.

First read the prior hint patch: the script
`/h/deepanjm/agentic-stuff/hintvszyg/sim/hint_patch.py` (`HINT_REPLAY`, `HINT_KFILL`; pod copy
`/localdisk/deepanjm/agentic-stuff/hintvszyg/sim/`) and the patched tree
`/localdisk/deepanjm/agentic-stuff/scarab-hint/`. Reuse what fits; do not copy blindly.

**Design (implement in C in the mise tree, not as a patch script).** New parameters in
`src/memory/memory.param.def` (or a new `src/prefetcher/startup_pf.param.def`):
- `--spf_mode off|record|replay`
- `--spf_file <path>` (the record output or the replay input)
- `--spf_region_end <n>`: the creation region's last instruction, from W1's boundaries
- `--spf_dest l1d|l2|llc` (and l1i for instruction lines)
- `--spf_timing instant|stream:<d>`
  - `instant`: every recorded line is installed at process start, with no bandwidth cost.
    This is the ideal bound.
  - `stream:<d>`: each line is issued through the normal prefetch path (the prefetch
    request queue and MSHRs, so bandwidth and occupancy are real) when the demand stream is
    `d` accesses before its first use.
- `--spf_source self|prev`
  - `self`: record and replay on the same trace. This is the oracle.
  - `prev`: replay the previous creation of the same class, rebased for ASLR per module. The
    rebasing happens outside the simulator, in Python, from `modules.log`; the simulator
    reads plain virtual-address lists.

**Two passes, one script** (`results/startup-prefetch/w4_ideal_prefetch/run_spf.sh`):
- Pass 1 (`record`) prints every distinct cache line the creation region touches, split
  I/D, in first-touch order, with the level that served it.
- Pass 2 (`replay`) prefetches them at the predicted creation point.
- **Trigger from W2.** Use the best predictor's decisions.
  - A false positive injects the prefetches into the harness window that follows; measure
    the pollution there.
  - A false negative gets no prefetch.
  - Report the oracle trigger (always correct) and the W2 trigger separately.

**Metrics (`w4_ideal_prefetch/results.csv`, one row per creation × configuration):**
- cycles and IPC;
- speedup vs cold baseline;
- the share of the perfect-cache bound recovered: (base − spf) / (base − perfect), for the
  matching level;
- coverage: recorded demand misses turned into hits;
- accuracy: prefetched lines used before eviction;
- timeliness: late prefetches (the line arrives after the demand);
- traffic: extra bytes from memory.

**Figures:**
- `fig_speedup_by_config.png`: bars per destination × timing, with perfect and self-warm
  marked;
- `fig_bound_recovered.png`;
- `fig_coverage_accuracy.png`;
- `fig_traffic.png`;
- `fig_wave_l2_spf.png`: the L2 wave of the creation region, cold vs spf vs perfect, using
  the W1 activity labels;
- `fig_pollution.png`: the harness window after a false positive.

**Correctness checks** (in the script; they fail loudly):
- With `spf_mode=off`, results are bit-identical to `baseline`.
- `record` does not perturb timing: cycles are identical to a normal run.
- With `instant` + `self`, recorded lines never miss at the destination level unless they
  were evicted; count the evictions.
- The replay file's line count equals the record count.

**Deliverables.** Commit and push `ideal-prefetching`. Running `./run.sh all` from a fresh
checkout must reproduce every W4 number.

### W5 — Integration and report
- **`w5_report/REPORT.md`** (Anish style): the setup, then one section per question Q1-Q4,
  each with its figures, the numbers taken from CSVs, the limits, and the success criteria
  (section 0) marked met or not met.
- **`w5_report/INDEX.md`**: every figure and table with its absolute path and one line on
  what it shows.
- **Verify from a clean checkout on the pod** that `./run.sh all` runs, or runs up to the
  stage that needs a new trace, and that every stage's checks pass.
- **Final message to the user**: the key numbers and every path.

---------------------------------------------------------------------------------------------
## 4. Open questions for the user (agents: do not guess these)
---------------------------------------------------------------------------------------------
1. (answered 2026-09-26) Commit email: mishradeepanjali25@gmail.com.
2. Push credentials on phoebe-login. There is no `gh` and no stored credential.
3. (answered 2026-09-26) Repository renamed to `dejavu` on GitHub; fresh clone at `/h/deepanjm/dejavu`.
4. Whether python3.9 (sympy/sphinx/requests) creations should be added later as a second
   benchmark. The plan fixes one task (django, python3.8) first, as requested.

---------------------------------------------------------------------------------------------
## 5. Prior results and code to reuse (read before re-implementing)
---------------------------------------------------------------------------------------------
- `mise/results/swe-bench-traces/e2e-uarch/`: README.md (method and validation),
  `scripts/{canon.py, similarity.py, activity.py, run_waves.py, figs_waves.py, native_*.py,
  run_perfect.py, anish_style.py}`, `fig/startup_waves/` (creation waves of 7 classes).
- `mise/results/swe-bench-traces/e2e/`: the e2e trace pipeline and attribution tables.
- `mise/characterization/methodology/literature_review.md`: warm/cold methodology
  (Lukewarm, Ignite, SMARTS, Full-Speed-Ahead), which the W4 evaluation must follow.
- Pod: `/localdisk/deepanjm/isca-traces/uarch-e2e/` (Scarab package `mise-scarab/`, all
  prior simulations) and `/localdisk/deepanjm/agentic-stuff/scarab-hint/` (the tree with
  the prior record/replay hint patch applied; the patch script is
  `/h/deepanjm/agentic-stuff/hintvszyg/sim/hint_patch.py`).
