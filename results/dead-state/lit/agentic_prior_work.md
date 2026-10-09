# Prior work on the host-side systems behaviour of agentic execution

Survey date: 2026-10-09. Scope: 2023 to Oct 2026 agentic-systems work, plus the older serverless,
managed-runtime and dead-block papers the paper will be compared against.

Rule zero: every entry below was checked against its arXiv abstract page, publisher page or PDF
during this survey. Numbers in quotes are copied from the abstract, HTML or PDF. Numbers without
quotes are paraphrased from those same sources. A blank "numbers" cell means the source has no
host-side number worth quoting, not that we lost it. Many 2026 arXiv preprints have no venue yet,
so treat them as unreviewed.

---

## 1. Table

### 1a. Agentic execution: host or CPU characterization (the closest prior work)

| Paper | Venue / year | Link | Measures (host vs GPU) | Key host-side findings (quoted where possible) | Relevance to dead state |
|---|---|---|---|---|---|
| Raj, Kundu, Vohra, Wang, Krishna. *Towards Understanding, Analyzing, and Optimizing Agentic AI Execution: A CPU-Centric Perspective* (v1/v2 titled "A CPU-Centric Perspective on Agentic AI") | arXiv 2511.00739, 2025 (v3 Apr 2026) | https://arxiv.org/abs/2511.00739 | Both. End-to-end latency, throughput and energy per component. No per-structure uarch metrics | "Tool processing on CPUs can take up to 90.6% of the total latency". SWE-Agent Bash/Python execution takes 25-65% of latency depending on the platform. Throughput saturates on "core over-subscription, cache-coherence, synchronization". Gives "LLC pressure" as a limit but reports no LLC miss rates. CPU is 42-61% of dynamic energy | Shows the host CPU is on the critical path. It does **not** ask what the host caches or memory hold, or whether that state is ever reused |
| Yang, Liu, Zhang, Stojkovic. *Architectural Implications of Agentic AI Workflows* (Agora) | arXiv 2608.04458, Aug 2026 | https://arxiv.org/abs/2608.04458 | Host CPU uarch (IPC, MPKI, top-down) plus utilization. SWE-Agent, Trae, CORAL, Owl on a 96-core EPYC 7V12 with 8xA100 | IPC "1.2-1.6". "L1-data MPKI reaches 14-20, while L2 and branch-misprediction MPKI also remain elevated". "43-47% of pipeline slots to backend stalls". Host CPU utilization "6% (Owl) to 31% (CORAL)", about 11% median with spikes to about 100% at stage boundaries. SWE-Agent "context switches grow from 71 to 660 per second" from 1 to 32 concurrent tasks. "Multiplexing many agents onto shared cores degrades microarchitectural locality" | **Closest architecture paper.** It measures miss rates but not reuse: it does not separate useful misses from fills that are never touched again, and it does not attribute misses to harness, tool or start-up phases |
| Zheng, Fan, Fu, Yang, Zhang, Quinn. *AgentCgroup: Understanding and Controlling OS Resources of AI Agents* | arXiv 2602.09345, Feb 2026 | https://arxiv.org/abs/2602.09345 | Host OS level: memory, CPU, timing. 144 SWE-rebench tasks in Podman containers | "~185 MB framework baseline". "15.4x peak-to-average ratio" in memory. "98.5% of memory bursts occurring during tool calls". OS-level work is "56-74% of end-to-end task latency" and "initialization overhead 31-48%" of the task lifecycle. Average CPU is "Haiku 13.2%, GLM 7.6%" of one core. Images are "2.9-17.3 GB". Retries happen in 85-97% of tasks, with "up to 502 MB unreleased" from progressive retention | **Strongest prior evidence for memory dead state.** It shows a constant harness baseline, memory that tools allocate in bursts, and memory that stays resident after use ("unreleased"). The measurement is cgroup RSS, though: no liveness, no reuse, no caches |
| Yuan, Nayak, Kundu, Talati. *Agentic AI Workload Characteristics* | arXiv 2605.26297, May 2026 | https://arxiv.org/abs/2605.26297 | Mostly the LLM side (prefix cache, decode vs prefill) plus a tool-time breakdown | Prefix "cache-hit ratios 84.6-99.5%". Decode is "91.0-98.6% of LLM time". Tools take "2-29% of total runtime". SWE-bench Pro context means are "68.7K-80.1K tokens", with a maximum of "146K-166K". Edit failures run "37.2-77.8%" on SWE-bench Pro and bash failures "28.4-39.8%" | Context grows every turn and is mostly reused, so host-side re-serialization of the full history may be repeated work. High tool-failure rates point to a large share of tool invocations whose outputs are thrown away |
| Chang et al. *From LLM Inference to Agentic Workloads: Characterization and Implications for Serving Systems* (AgentSysBench) | arXiv 2608.15127, Aug 2026 | https://arxiv.org/abs/2608.15127 | Both, at system level | "Non-LLM components dominating latency in 5 of 10 applications". "Sandbox memory reaching 28 GB per session" (median sandbox peak about 0.8 GB). "Idle state holding": sessions keep state "for minutes to hours". Tool-result caching cuts 35.2% of redundant calls | Documents idle resident state between turns, the system-level form of "resident past last use" |
| Choi, Park, Niu, Xiong, Yoo, Yang. *Not All AI Agents Are Equal: Characterizing Resource and Performance Dynamics* | arXiv 2609.19947, Sep 2026 | https://arxiv.org/abs/2609.19947 | Host CPU, disk and memory under concurrency; RAG, web search and coding agents | Bottlenecks depend on the task (CPU, disk I/O, memory). "Faster LLM responses or more CPU cores do not always accelerate agents" | Concurrency and contention context only |
| Luo, Li, Wang, Chen. *Where Does the Energy Go? Profiling LLM Agent Inference on Blackwell GPUs* | arXiv 2609.29707, Aug 2026 | https://arxiv.org/abs/2609.29707 | System energy, including the non-GPU share | "GPU-only telemetry misses 41-45% of system energy". A sequential agent uses "63x more system energy per output token than saturated serving", partly from "tool-induced idle periods". About 2,989 kJ per SWE-bench task | Host energy is large. Dead resident state costs static and refresh energy during idle periods |
| Tripathy, Harshit, Vaidhyanathan. *SWEnergy* | AGENT '26 workshop @ ICSE 2026; arXiv 2512.09543 | https://arxiv.org/abs/2512.09543 | Energy per framework (SWE-Agent, OpenHands, Mini-SWE-Agent, AutoCodeRover) | "AutoCodeRover (Gemma) consumed 9.4x more energy on average than ... OpenHands (Gemma)". "Framework architecture is the primary driver of energy consumption" | The harness, not the model, sets the energy cost, which supports studying the harness on its own |

### 1b. Agent serving: GPU KV cache and scheduling across tool calls (GPU-side analogue of "dead state")

| Paper | Venue / year | Link | Measures | Key findings | Relevance |
|---|---|---|---|---|---|
| Abhyankar, He, Srivatsa, Zhang, Zhang. *InferCept* | ICML 2024; arXiv 2402.01869 | https://arxiv.org/abs/2402.01869 | GPU KV memory waste during interceptions (tool calls) | Discarding context at every interception and recomputing it accounts for "37-40% of total model forwarding time". Improves throughput 1.6-2x | Defines "GPU memory waste" for KV held during a tool call. This is the GPU twin of host state kept resident through the model gap |
| Li et al. *Continuum: Efficient and Robust Multi-Turn LLM Agent Scheduling with KV Cache Time-to-Live* | arXiv 2511.02230, 2025 (v5 May 2026) | https://arxiv.org/abs/2511.02230 | GPU KV retention policy; also measures tool-time distributions | SWE-bench tool time "(925, 3,550)" ms (mean, std) over "(10.9, 2.1)" turns. "Slowest 10% of fetch_url account for 52.5% of the total delay, while slowest 10% of cd account for 94.1%" | Gives tool-gap lengths in seconds with a heavy tail. That sets how long host state sits idle between uses |
| Luo, Shi, et al. *Autellix* | arXiv 2502.13965, 2025 | https://arxiv.org/abs/2502.13965 | Program-level scheduling of LLM calls | BFCL ReAct agents average "10.75" LLM calls per program and LATS "159.7". "Interceptions" (tool time) are a named component of latency | Turn counts tell us how many harness wake-ups a task has |
| Lin et al. *Parrot* | OSDI 2024; arXiv 2405.19888 | https://www.usenix.org/conference/osdi24/presentation/lin-chaofan | Multi-request LLM application serving | Shares common prompt prefixes and does DAG-aware scheduling | Prefix sharing on the GPU. Says nothing about the host |
| Zheng et al. *SGLang* (RadixAttention) | NeurIPS 2024; arXiv 2312.07104 | https://arxiv.org/abs/2312.07104 | KV prefix reuse | "Up to 6.4x higher throughput", including agent-control tasks | Baseline for prefix reuse across turns |
| Gao et al. *CachedAttention / AttentionStore* | USENIX ATC 2024; arXiv 2403.19708 | https://www.usenix.org/conference/atc24/presentation/gao-bin-cost | Multi-turn KV saved to host DRAM and SSD | TTFT down "up to 87%", prefill throughput up to "7.8x" | Puts KV in **host DRAM**, a new host resident whose liveness is set by turn gaps |
| Pan et al. *KVFlow* | arXiv 2507.07400, 2025 | https://arxiv.org/abs/2507.07400 | KV eviction in multi-agent workflows | LRU "often discards KV caches shortly before their reuse"; uses steps-to-execution to guide eviction | Same argument as dead-block prediction, applied to KV. Recency is a poor predictor when reuse follows the program's structure |
| Bian, Wu, Li, Ma, Zhuo. *TokenCake* | EuroSys '27 (per authors' repo); arXiv 2510.18586 | https://arxiv.org/abs/2510.18586 | GPU KV idle during function calls | Caches of agents "stalled on long-running function calls idling in GPU memory". Latency down "up to 47.06%" | Names temporally idle cache state during tool calls. GPU only |
| Xu et al. *Conveyor* | arXiv 2406.00059, 2024 | https://arxiv.org/abs/2406.00059 | Overlapping tool execution with decoding | Partial tool execution improves completion latency "by up to 38.8%" | Tools and decoding are serialized; idle gaps exist on both sides |
| Gim, Lee, Zhong. *AsyncLM* | arXiv 2412.07017, 2024 | https://arxiv.org/abs/2412.07017 | Asynchronous function calls | Latency "1.6x-5.4x" lower than synchronous calling on BFCL | Same serialization point |
| Kim et al. *LLMCompiler* | ICML 2024; arXiv 2312.04511 | https://arxiv.org/abs/2312.04511 | Parallel function calling | Up to "3.7x" latency speedup over ReAct | Parallel tools mean several short processes at once, so more interleaving on the host |
| Bai, Lv, Zheng, Lu, Shu. *SPORK* | arXiv 2607.03333, Jul 2026 | https://arxiv.org/abs/2607.03333 | Speculative tool execution | Tool waits are "16-37% of wall time". Predicts upcoming tool calls with 74.6-99.6% accuracy | High predictability of the *next tool* points to a possible trigger for prefetching or reclaim |

### 1c. Agent sandboxes and execution infrastructure

| Paper | Venue / year | Link | Measures | Key findings | Relevance |
|---|---|---|---|---|---|
| Graviet, Pesut, Dagelic, Jukic, Burazin. *The Rollout Infrastructure Tax in Coding-Agent RL* | arXiv 2607.01415, Jul 2026 | https://arxiv.org/abs/2607.01415 | Sandbox cold start across 4 substrates | "Up to 110x variation in cold-start latency". "1.8x spread in projected worker-hours" | Sandbox start-up is a first-order cost. This is a start-up/warm-up behaviour |
| Dong et al. *DeltaBox* | arXiv 2605.22781, May 2026 | https://arxiv.org/abs/2605.22781 | Firecracker sandbox checkpoint/rollback for agents | Checkpoint 14 ms, rollback 5 ms. "Subsequent checkpoints in AI agents are highly similar" | Consecutive sandbox states share most of their content, so most state is either never touched again or reused unchanged |
| Zhang, Wo, Wang, et al. *SpecBox* | arXiv 2607.23933, Jul 2026 | https://arxiv.org/abs/2607.23933 | Sandbox prewarming | "Persistent long-lived sandbox reservations incur excessive memory overhead". Peak memory down 45.9% vs always-reserved; P99 up to 2.9x lower | A prewarmed sandbox is memory held in case of reuse: explicitly speculative resident state |
| Huang et al. (DeepSeek). *DSec* | arXiv 2609.22978, Sep 2026 | https://arxiv.org/abs/2609.22978 | Production sandbox fleet | About 3M sandboxes/day, ">380,000 concurrent", ">5,000 new sandboxes per second" | Churn at fleet scale: sandbox lifetimes are short and there are a lot of them |
| *Fault-Tolerant Sandboxing for AI Coding Agents: A Transactional Approach* (authors not checked in this survey) | arXiv 2512.12806, 2025 | https://arxiv.org/abs/2512.12806 | Transactional sandbox | Ephemeral containers per command bring orchestration overhead; VMs bring tens of seconds of start-up | Process and container churn per command |

### 1d. Serverless and short-lived-process characterization (the closest conventional counterpart)

| Paper | Venue / year | Link | Measures | Key findings | Relevance |
|---|---|---|---|---|---|
| Shahrad, Balkind, Wentzlaff. *Architectural Implications of Function-as-a-Service Computing* | MICRO 2019 | https://doi.org/10.1145/3352460.3358296 | Host uarch of FaaS (OpenWhisk) | From the paper's Fig. 1: "20x MPKI for short functions" (branch), cold start ">10x exec time for short functions (500ms cold start)", containers "up to 20x slowdown", "6x variation" in memory bandwidth from the invocation pattern, "35% decrease in IPC due to interference" | Closest uarch analogue to agent tool calls: short functions interleaved on the same server |
| Schall, Margaritov, Ustiugov, Sandberg, Grot. *Lukewarm Serverless Functions: Characterization and Optimization* (Jukebox) | ISCA 2022 | https://doi.org/10.1145/3470496.3527390 | Host uarch, warm-but-cold instances | Interleaving "causing a 31-114% increase in CPI compared to execution with warm microarchitectural state". On-chip instruction misses are "a major contributor". Jukebox needs "32KB of metadata per function instance", "+18.7%" | Cross-invocation state is evicted *before* its reuse. That is the opposite failure from dead state, and both come from interleaving |
| Schall, Sandberg, Grot. *Warming Up a Cold Front-End with Ignite* | MICRO 2023 | https://doi.org/10.1145/3613424.3614258 | Front-end state restoration | "Improving performance by an average of 43% by significantly reducing instruction, BTB and branch predictor MPKI" | Shows record-and-replay of front-end state works for repeated short invocations |
| Ustiugov, Petrov, Kogias, Bugnion, Grot. *Benchmarking, Analysis, and Optimization of Serverless Function Snapshots* (REAP, vHive) | ASPLOS 2021; arXiv 2101.09355 | https://arxiv.org/abs/2101.09355 | Page-level working set of snapshot-restored functions | Snapshot-started functions run 95% slower on average than memory-resident ones. A "stable working set" of pages across invocations. REAP removes up to 97% of page faults, 3.7x cold start | The touched set is small and stable and the restored image is large, which means most restored pages are dead. Method template for page-level liveness |
| Oakes et al. *SOCK* | USENIX ATC 2018 | https://www.usenix.org/conference/atc18/presentation/oakes | Container primitives plus Python import cost | "Importing many popular libraries adds about 100 ms to startup". Zygotes give "an additional 3x" | Python import is the start-up cost. A zygote is the conventional fix |
| Du et al. *Catalyzer* | ASPLOS 2020 | https://dblp.org/rec/conf/asplos/DuYXZYQWC20.html | Init-less sandbox restore, sfork | "<1ms" best-case start-up | Skips initialization, the phase that creates start-up dead state |
| Ao, Porter, Voelker. *FaaSnap* | EuroSys 2022 | https://cns.ucsd.edu/virtual-machine-snapshots-with-faasnap/ | Snapshot loading | Up to 3.5x end-to-end; 3.5% slower than in-memory snapshots | Loading-set files: only the touched pages are worth loading |
| Shahrad et al. *Serverless in the Wild* | USENIX ATC 2020; arXiv 2003.03423 | https://arxiv.org/abs/2003.03423 | Azure Functions production trace | "Most functions are invoked very infrequently, but there is an 8-order-of-magnitude range of invocation frequencies" | Keep-alive policy is a liveness policy for warm instances |
| Tariq et al. *SLIMSTART* | ICDCS 2025; arXiv 2504.19283 | https://arxiv.org/abs/2504.19283 | Python library init in serverless | "Many serverless functions initialize libraries that are rarely or never used". 2.30x init speedup, "1.51x reduction in memory usage" | **Direct prior evidence for import-induced dead memory in Python.** Measured at library granularity, not cache blocks |
| Liu et al. *FaaSLight* | arXiv 2207.08175 (TOSEM) | https://arxiv.org/abs/2207.08175 | Code loading in cold start | "Application code loading latency is a significant overhead". Code loading down up to 78.95% (28.78% avg) | Same point: code that is loaded but optional |

### 1e. Managed-runtime bloat, Python and interpreter characterization

| Paper | Venue / year | Link | Measures | Key findings | Relevance |
|---|---|---|---|---|---|
| Mitchell, Sevitsky. *The Causes of Bloat, the Limits of Health* | OOPSLA 2007 | https://doi.org/10.1145/1297027.1297046 | Java heap composition ("health signatures") | Some designs have an asymptotic limit on how healthy their memory can be | Classic framing of memory that is resident but not useful |
| Xu, Mitchell, Arnold, Rountev, Schonberg, Sevitsky. *Finding Low-Utility Data Structures* | PLDI 2010 | https://doi.org/10.1145/1806596.1806617 | Cost/benefit of data structures via abstract dynamic thin slicing | Flags structures whose construction cost far exceeds their use | The closest software-level definition of "built but never used" |
| Xu, Mitchell, Arnold, Rountev, Sevitsky. *Software Bloat Analysis* | FoSER 2010 | https://doi.org/10.1145/1882362.1882448 | Survey / position | Bloat taxonomy | Related-work anchor |
| Drosos, Sotiropoulos, Spinellis, Mitropoulos. *Bloat beneath Python's Scales* | FSE 2024 | https://doi.org/10.1145/3660821 | PyPI dependency bloat (static and dynamic) | Over 50% of dependencies bloated; on average 34% of dependency code bloated; 57% of transitive dependencies bloated | Static proof that a Python process carries code it never runs. The import-time cost of that code is what we measure |
| Ismail, Suh. *Quantitative Overhead Analysis for Python* | IISWC 2018 | https://cpb-us-w2.wpmucdn.com/sites.coecis.cornell.edu/dist/7/89/files/2016/08/iiswc18-revised-1fjavbb.pdf | CPython/PyPy overhead and uarch | C function calls are "a new major source of overhead". JIT performance "depends heavily on the cache hierarchy". "Proper nursery sizing" trades cache performance against GC overhead | Interpreter uarch baseline. Steady state only, not start-up |
| Zhu, Richins, Halpern, Reddi. *Microarchitectural Implications of Event-driven Server-side Web Applications* | MICRO 2015 | https://horizon-lab.org/pubs/micro15.pdf | Node.js front-end | Front-end inefficiency from "limited intra-event code reuse and large inter-event reuse distance". LIP plus a prefetcher cut I-cache MPKI by 88% | Managed-runtime code with low reuse inside an event and long reuse distance across events: the same shape as a harness step |
| Berger, Stern, Altmayer Pizzorno. *Triangulating Python Performance Issues with Scalene* | OSDI 2023 | https://www.usenix.org/conference/osdi23/presentation/berger | Python CPU, memory, copy-volume profiler | Sampling memory profiler; "copy volume" metric | Tool candidate for line-level Python memory attribution |
| Baumann, Appavoo, Krieger, Roscoe. *A fork() in the road* | HotOS 2019 | https://doi.org/10.1145/3317550.3321435 | Position | fork is "a liability" for modern OSes | Agent tools are almost all fork+exec |
| Soares, Stumm. *FlexSC* | OSDI 2010 | https://www.usenix.org/conference/osdi10/flexsc-flexible-system-call-scheduling-exception-less-system-calls | Syscall cost | Synchronous syscalls hurt mainly through "pipeline flushing and pollution of key processor structures (e.g., TLB, data and instruction caches)" | Kernel entries pollute caches; tool start-up is heavy on syscalls |

### 1f. Dead-block baselines (for the definition, not agentic)

| Paper | Venue / year | Link | Key number |
|---|---|---|---|
| Lai, Fide, Falsafi. *Dead-Block Prediction & Dead-Block Correlating Prefetchers* | ISCA 2001 | (ISCA 2001 proceedings; DOI not verified in this survey, so cite from the proceedings) | Introduces trace-based dead-block prediction |
| Khan, Tian, Jiménez. *Sampling Dead Block Prediction for Last-Level Caches* | MICRO 2010 | https://doi.org/10.1109/MICRO.2010.24 | In a 2MB LRU LLC "a cache block is dead 86% of the time" (SPEC) |
| Mazumdar, Mitra, Basu. *Dead Page and Dead Block Predictors: Cleaning TLBs and Caches Together* | HPCA 2021 | https://www.csa.iisc.ac.in/~arkapravab/papers/hpca21_DOA.pdf | Dead LLT pages are "most often dead-on-arrival"; "dead blocks are often concentrated within dead pages"; +8.3% IPC |

---

## 2. Synthesis: what prior work has documented about host-side agentic behaviour, and what it has not

### Documented (with numbers)

1. **Host CPU on the critical path.** Raj et al. (up to 90.6% tool latency; 25-65% for SWE-Agent), AgentCgroup (56-74% OS-level), AgentSysBench (non-LLM dominant in 5 of 10 apps), SPORK (16-37%) and Yuan et al. (2-29%). The spread is large and depends on workload and model speed. All of them measure *time*, not microarchitectural state.
2. **Bursty, low average host utilization with long model-wait gaps.** Agora (6-31% utilization, 11% median, spikes to 100% at stage boundaries) and AgentCgroup (7.6-13.2% of one core). Continuum gives tool gaps of about 1 s mean with a heavy tail. The *model* gap (host idle while the GPU decodes) is implied by the decode-dominated LLM time (Yuan et al.) but nobody has measured it as host idle time per turn.
3. **Constant harness memory baseline plus tool bursts.** AgentCgroup: about 185 MB framework baseline, 98.5% of memory bursts inside tool calls, 15.4x peak-to-average, and up to 502 MB "unreleased".
4. **Sandbox and container start-up.** Rollout-tax (110x substrate spread), AgentCgroup (31-48% initialization), DeltaBox, SpecBox and DSec (5,000 sandboxes/s).
5. **Process churn and concurrency interference.** Agora (SWE-Agent context switches from 71 to 660/s; "degrades microarchitectural locality") and Raj et al. (core over-subscription, coherence).
6. **Context growth and prefix reuse.** Yuan et al. (84.6-99.5% hit ratio; up to 166K tokens), InferCept (37-40% recompute), Continuum, KVFlow and CachedAttention. All on the GPU side. Host DRAM shows up only as a KV spill tier (CachedAttention, KVFlow prefetch).
7. **Idle resident state as a named problem.** On the GPU: InferCept ("memory waste"), TokenCake ("idling in GPU memory") and Continuum (TTL). At system level: AgentSysBench ("idle state holding") and SpecBox (reservation overhead). **Nobody** has named the host-CPU equivalent.
8. **Host energy matters.** 41-45% of system energy is non-GPU (Luo et al.). Framework choice changes energy 9.4x (SWEnergy).

### Undocumented

- **Liveness and reuse of host state.** No agent paper measures whether bytes or cache blocks brought in are ever used again. Agora reports MPKI, AgentCgroup reports RSS, and neither gives reuse.
- **Phase attribution of host misses.** No paper splits host cache misses between harness steady state, harness import/start-up, tool-process start-up, tool real work, and teardown.
- **Tool calls as short-lived-process start-up.** The serverless literature (Shahrad, Lukewarm, Ignite, SOCK) has characterized short-function uarch and Python import cost, but no agent paper has made the connection. Almost every agent tool is a fresh `bash`/`python`/`git` process; per-invocation interpreter start-up has never been measured for agents.
- **What happens to host caches and memory during the model gap.** Does harness state survive the gap? What fraction is already dead before the gap begins?
- **Python GC and import behaviour inside harnesses** (litellm, pydantic, tokenizers) and its effect on cache pollution.
- **Teardown cost** (exit-time finalization, page freeing, `munmap`/TLB shootdowns) for thousands of short tool processes.

---

## 3. Candidate behaviours inherent to agentic execution that could create host dead state

Each entry gives the mechanism, the prior work showing the behaviour exists, how to isolate and trace it, and the conventional counterpart.

### B1. Per-tool-call interpreter start-up (fresh `python`/`bash`/`git`/`pytest` per action)
- **Mechanism.** Each tool call execs a new process that walks `site`, imports modules (unmarshalling `.pyc` code objects, building type and dict objects), and maps shared libraries, then does a few ms of real work and exits. Most bytes and instructions touched during import are touched once. They are dead-on-arrival or die within milliseconds, and they displace the harness's warm lines.
- **Prior evidence.** Agent tools are mostly Bash (AgentCgroup: "98.1% of tool execution time in Bash" for GLM; test execution 43.7-72.9% of bash commands). SOCK puts Python import at about 100 ms. SLIMSTART says libraries are "rarely or never used". Bloat beneath Python's Scales finds 34% of dependency code bloated.
- **Isolate and trace.** Replay a single tool command recorded in a SWE-agent trajectory (e.g. `python reproduce.py` or `pytest -x tests/x.py`) under DynamoRIO memtrace with a fresh process. Mark the import/start-up phase with a `python -X importtime` boundary, or a breakpoint on `PyImport_*` return to `__main__`. Compute per-block last-use relative to process exit. Control: the same command in a zygote/fork server.
- **Conventional counterpart.** Serverless cold starts (Shahrad MICRO'19; SOCK) and `make`-driven compiler invocations (`cc1` per file).

### B2. Harness import footprint that is resident but idle for the whole task
- **Mechanism.** The harness (litellm, pydantic, httpx, tokenizers, framework code) imports tens to hundreds of MB once, then exercises a small slice on each turn. The rest of the heap and code stays resident for the whole task and is never touched after start-up.
- **Prior evidence.** AgentCgroup's "~185 MB framework baseline" is constant across tasks. SLIMSTART reports unused libraries at import time. Yuan et al. show sessions lasting hundreds of turns.
- **Isolate and trace.** Idle-page tracking (`/sys/kernel/mm/page_idle`) on the harness PID across N turns, plus DynamoRIO on one harness step replayed from a trajectory with the LLM call stubbed by a recorded response. Attribute pages to modules through `tracemalloc` or a patched allocator.
- **Conventional counterpart.** Java application-server bloat (Mitchell & Sevitsky 2007; Xu et al. PLDI 2010) and the long-lived warm instances in "Serverless in the Wild".

### B3. Model-wait gaps (harness blocked on an HTTP response for seconds)
- **Mechanism.** After issuing a request the harness sleeps for seconds while other processes (other agents, tool processes, kernel) run. Its cache lines are evicted before they can be reused; if the post-gap working set differs (new context, a different code path), the pre-gap lines were dead when the gap began. In memory, all harness state is resident and idle during the gap.
- **Prior evidence.** Low, bursty host utilization (Agora; AgentCgroup). Decode-dominated LLM time (Yuan et al.). GPU-side idle KV during calls (TokenCake; InferCept). "Idle state holding" (AgentSysBench). Lukewarm shows the microarchitectural effect of long gaps between invocations.
- **Isolate and trace.** Instrument the harness so it emits markers at request send and response receive (or use uprobes on the litellm call). Snapshot cache contents in a simulator (Scarab/gem5 replay of the trace with a fixed gap filled by a co-runner) at gap start and gap end, and count lines whose next reference comes after their eviction. For memory, use idle-page bits at the two markers.
- **Conventional counterpart.** Interactive and OLTP think time; warm serverless instances between invocations (Lukewarm).

### B4. Context re-serialization every turn (growing message list to JSON to HTTP)
- **Mechanism.** Each turn the harness re-walks the full history (tens to hundreds of KB): pydantic validation, `json.dumps`, token counting, and sometimes re-tokenization. It allocates new strings and buffers that are used once and then freed (garbage, not reused), streaming through L1/L2. The GPU reuses the prefix through its KV cache; the host rebuilds it from scratch.
- **Prior evidence.** Context growth to 68.7K-80.1K mean and 166K max tokens (Yuan et al.). Prefix reuse at 84.6-99.5% on the GPU. AgentSysBench reports "context overhead from tool schemas".
- **Isolate and trace.** Replay a harness step at context lengths n=1..K taken from a recorded trajectory. Measure bytes allocated per turn (tracemalloc/Scalene), check that L1D/L2 misses grow linearly in context length, and measure the reuse distance of the serialization buffers under DynamoRIO.
- **Conventional counterpart.** RPC/protobuf serialization tax in datacenters; JSON-heavy web backends.

### B5. Process teardown and the short-lived address space
- **Mechanism.** Tool processes exit after a few ms to s. Their pages (heap, page tables, `.pyc` objects) and cache lines are dead from the last user-mode access to `exit`. Python finalization (module teardown, GC) touches objects one last time only to free them. Kernel teardown (`exit_mmap`, freeing page tables) brings in more lines that are never reused.
- **Prior evidence.** Process churn and context switches rising with concurrency (Agora). Fleet-scale sandbox churn (DSec). The cost of fork (Baumann et al.). Cache pollution from syscalls (FlexSC).
- **Isolate and trace.** DynamoRIO on a tool process with a marker at `Py_FinalizeEx` entry, plus kernel tracing of `exit_mmap` (ftrace/perf). Compare `os._exit()` (skip finalization) against a normal exit.
- **Conventional counterpart.** CGI-style web servers, shell-script pipelines, build systems (`make -j`), serverless functions.

### B6. Interleaving many agents and short processes on shared cores
- **Mechanism.** Concurrent agents, their tool processes and the inference server's CPU threads time-share cores and LLC. Each occupant brings in lines that others evict before reuse, while low-reuse start-up lines (B1) fill capacity. The result is dead-on-arrival blocks plus useful blocks evicted early.
- **Prior evidence.** Agora (SWE-Agent context switches from 71 to 660/s; "degrades microarchitectural locality"). Raj et al. (coherence, over-subscription). Shahrad MICRO'19 ("35% decrease in IPC due to interference"). Lukewarm (31-114% CPI).
- **Isolate and trace.** Multi-trace simulation: interleave per-process DynamoRIO traces at measured context-switch rates and compare dead-block fraction for 1 vs N agents. Natively, use perf counters with `taskset` pinning against co-scheduling.
- **Conventional counterpart.** Multi-tenant FaaS (Shahrad; Lukewarm) and consolidated microservices.

### B7. Discarded and failed actions (retries, failed edits, abandoned branches)
- **Mechanism.** A large share of tool invocations fail or are retried. Everything they bring in (file contents, test-collection state, parsed ASTs) is never used by a later step. In tree-search agents (LATS-style) whole branches are dropped. Their sandbox state and host memory are dead from the moment the branch is pruned.
- **Prior evidence.** Edit failures at 37.2-77.8% and bash failures at 28.4-39.8% (Yuan et al.). Retry groups in 85-97% of tasks, taking 7-21% of time, with "up to 502 MB unreleased" (AgentCgroup). LATS averages 159.7 LLM calls (Autellix). DeltaBox explores many checkpoints.
- **Isolate and trace.** Label trajectory steps as kept or discarded (the next action reverts or retries them). Replay both classes under DynamoRIO and compare bytes touched that are never touched by any later step, using cross-step reuse within the sandbox's page cache (fanotify/ftrace page attribution).
- **Conventional counterpart.** Speculative execution's wrong-path fills, and aborted transactions in databases.

### B8. Repository and test-suite scans with no reuse (grep, find, pytest collection, git status)
- **Mechanism.** Exploration tools stream through the whole repository once: file reads into the page cache, regex scanning, pytest collection importing every test module. Each byte is used once per invocation, and repeated invocations a few turns later may or may not hit, depending on gap length and memory pressure.
- **Prior evidence.** Test execution dominates bash commands, 43.7-72.9% (AgentCgroup). Agents shift from exploration to action over a task (Yuan et al.). Cross-request redundancy of 35.2% in tool calls (AgentSysBench), which points to re-execution of the same reads.
- **Isolate and trace.** Replay the `grep`/`find`/`pytest --collect-only` commands from a trajectory in sequence with the real inter-command gaps. Measure page-cache reuse with a kprobe on `filemap_get_read_batch`/`mark_page_accessed`, and cache-block reuse within one invocation under DynamoRIO.
- **Conventional counterpart.** Streaming scans and analytics (no temporal reuse), and `updatedb`/indexers.

### B9. Prewarmed or reserved sandboxes and caches held in case of reuse
- **Mechanism.** To hide cold starts, systems keep sandboxes, zygotes, KV in host DRAM, or tool-result caches resident. Whatever is never reused is dead by construction; these policies trade dead memory for latency.
- **Prior evidence.** SpecBox (reservation memory overhead; 45.9% peak reduction). CachedAttention (KV in host DRAM). AgentSysBench (idle state for minutes to hours). Serverless keep-alive (Serverless in the Wild).
- **Isolate and trace.** Count reuse of each reserved object per policy over a replayed workload trace, and report dead byte-seconds against latency saved.
- **Conventional counterpart.** Serverless keep-alive windows; connection pools and JIT code caches.

---

## 4. Gaps: what nobody has measured at the microarchitecture level

1. **Dead-block or dead-byte fractions for any agentic workload on the host.** Agora gives MPKI and top-down stalls; nobody gives reuse, last-touch, or dead-on-arrival fractions per cache level.
2. **Attribution of host misses and resident bytes to agent phases** (harness steady state vs harness start-up vs tool start-up vs tool work vs teardown vs model gap). Prior agent work splits *time* by phase, never cache or memory state.
3. **Uarch characterization of agent tool processes as short-lived processes.** Serverless work (Shahrad; Lukewarm; Ignite) did this for FaaS functions. Nobody has done it for agent tools, whose mix (CPython start-up, git, grep, pytest collection) and gap structure (seconds-scale model waits) differ.
4. **Cross-invocation reuse of start-up state between consecutive tool calls in one task.** Lukewarm/Jukebox and Ignite show record-and-replay works when the same function recurs. Nobody has measured whether consecutive `python` tool invocations in an agent share their start-up footprint, which would make the same mechanisms usable for agents.
5. **What the model-wait gap does to host caches and TLBs** (how much of the harness working set survives a multi-second gap under realistic co-running).
6. **Python-runtime contribution** (GC passes, module finalization at exit, allocator arena retention) to dead state in agent harnesses. Ismail & Suh studied nursery size against cache behaviour for steady-state benchmarks only.
7. **Teardown cost** (finalization, `exit_mmap`, TLB shootdowns) per tool call and its pollution of the next occupant's state.
8. **Host-DRAM liveness of the KV spill tiers** (CachedAttention-style) that agent-serving systems add, measured with reuse rather than hit rate.
9. **The host side of GPU-side "idle cache" findings.** InferCept, TokenCake and Continuum show idle KV during tool calls; nobody has measured the symmetric idle *host* state during model calls.

Closest prior works, ranked by overlap with this paper:
(1) Agora / *Architectural Implications of Agentic AI Workflows* (arXiv 2608.04458);
(2) AgentCgroup (arXiv 2602.09345);
(3) Raj et al., CPU-centric agentic AI (arXiv 2511.00739);
(4) Lukewarm Serverless Functions (ISCA'22) together with Shahrad, MICRO'19 (the uarch counterpart);
(5) SLIMSTART (ICDCS'25) together with Bloat beneath Python's Scales (FSE'24) (import-time unused code and memory in Python).
