# Simulation methodology of the reference papers (verified)

Collected 2026-10-09 by literature sub-agents from primary PDFs/repos; quotes verbatim; "not stated" = searched
the full text for warm/simpoint/million/billion/geomean/confidence and found nothing.

## Cross-cutting
- Replacement/dead-block papers: **no confidence intervals or error bars in any of them**; one deterministic run
  per (policy, workload); geomean speedup over LRU; weighted speedup for multi-core; single SimPoint is the norm.
- Warm-up/measure drifted from 100M/100M (CRC1) to 200M/1B (CRC2: Glider, Mockingjay).
- Litz group: one 100M steady-state Intel-PT window per app (2020-22); since 2024 (Scarab 2.0 / scarab-infra)
  10M SimPoints + 10M warm-up for DynamoRIO memtraces, 50M warm-up for PT traces.
- **No paper models short-lived processes or cold start**, except Ignite (MICRO'23), which flushes
  microarchitectural state between serverless invocations. scarab-infra keeps only the main thread of one process.

## Dead-time quantification in prior work
| paper | definition | number |
|---|---|---|
| Lai ISCA'01 | CDF of last-touch -> miss distance | "80% of the deadtimes ... 500 cycles or more" |
| Cache Bursts MICRO'08 | efficiency E = sum U_i/(N*A*S) (time-averaged live fraction) | geomean efficiency L1D 0.08, L2 0.17 (64KB 2-way L1D, 1MB 16-way L2; SPEC2000 etc.) => ~92% / 83% dead |
| SDBP MICRO'10 | live = placement..last reference; dead = last reference..eviction | "a cache block in a 2MB LRU-managed LLC is dead 86% of the time" (memory-intensive SPEC2006) |

## Per paper
| paper | simulator | workloads | warm-up | measured | sampling | stats |
|---|---|---|---|---|---|---|
| Lai ISCA'01 | SimpleScalar 3.0 | Olden + SPEC95/2K | skip 1B cycles | 3B cycles (6B equake) | none | averages |
| Cache Bursts MICRO'08 | sim-alpha; MP-sauce | SPEC2000+, commercial | not stated | up to 2B (SimPoint) | SimPoint | geomean |
| SDBP MICRO'10 | CMP$im (CRC1) | SPEC2006 | not stated | 1B | single SimPoint | geomean |
| SHiP MICRO'11 | CMP$im | 24 mm/server/SPEC | not stated | 250M | PinPoints | averages |
| Hawkeye ISCA'16 | CMP$im (CRC1) | SPEC2006 (28) | 50M | 200M | single SimPoint 250M | geomean |
| Glider MICRO'19 | ChampSim (CRC2) | 33 SPEC06/17/GAP, LLC MPKI>1 | 200M | 1B | single SimPoint | average |
| Mockingjay HPCA'22 | ChampSim | 33 SPEC/GAP + 25 CVP1 | 200M | 1B | single SimPoint | geomean |
| Leeway PACT'17 | CMP$im | SPEC + CloudSuite | 500M | 1B | up to 6 SimPoints (weighted) | geomean |
| CRC1 2010 | CMP$im | 65 workloads | 100M | 100M | SimPoint-like | geomean |
| CRC2 2017 | ChampSim | 20 SPEC06 (LLC MPKI>=1) + CloudSuite | 200M | 1B | highest-weight SimPoint | geomean |
| I-SPY MICRO'20 | ZSim | 9 datacenter | not stated | up to 100M steady state | one window | average |
| Ripple ISCA'21 | ZSim | 9 datacenter | not stated | 100M PT (user+kernel) | one window | average |
| Twig MICRO'21 | Scarab (PT) | 9 datacenter | not stated | 100M | one window | avg ± std across inputs |
| Thermometer ISCA'22 | ChampSim (PT) | 13 datacenter + CBP5/IPC1 | artifact 50M | artifact 50M | one window | average |
| Whisper MICRO'22 | Scarab (PT) | 12 datacenter | sensitivity 0-90% | 100M (sens. to 1B) | one window | average |
| CRISP ASPLOS'22 | Scarab+Ramulator | SPEC17, Tailbench | not stated | 200M | "representative" | average |
| PDede MICRO'21 | Intel in-house | 100+ apps | 100M+ | 10M+ | SimPoints | **validated to silicon within 5%** |
| UDP ISCA'24 (Scarab 2.0) | Scarab | 10 datacenter | 10M (PT 50M) | 10 x 10M SimPoints | SimPoint, weighted | geomean |
| ATR MICRO'25 | Scarab | SPEC2017 | 10M | 10M SimPoints (8 to >100) | SimPoint | not stated |
| Ignite MICRO'23 | gem5 FS | 20 serverless fns | 20,000 invocations | per invocation | flush between invocations | PMU validation |

## What this means for the dead-state study
1. Our 100M windows (20M warm-up, 80M measured) exceed the Scarab-group convention (10M+10M) and match the
   window length of Litz's PT studies; warm-up is below CRC2 (200M). Report agent20 (10M+10M) to match the
   baselines exactly, and a warm-up sensitivity (cold vs 20M) for L2/LLC.
2. Prior dead-time numbers (LLC 86% dead; L1D 92%, L2 83%) are on LLC-stressing SPEC; the agent's must be
   compared to same-instrument baselines, never to these numbers directly.
3. Our CIs (Horvitz-Thompson over 160 PPS units, paired per unit) exceed the field's norm; keep them.
4. Our all-process, cold-start methodology goes beyond scarab-infra (main thread of one process) and the
   steady-state-only convention; state this as a contribution and justify cold start as the agent's reality
   (Ignite is the only precedent).
5. Simulator validation: the field rarely validates against hardware (PDede only); we have a native Zen 2
   L1-D refill check (within 2%) from the semsim study, and should add Scarab-vs-native for a few units.
| 15 | SDBP: Sampling Dead Block Prediction for Last-Level Caches (Khan, Tian, Jimenez) | MICRO 2010 | CMP$im (JILP CRC-1 version), "accurate to within 4% of a detailed cycle-accurate simulator"; L1D 32KB/8w, L2 256KB/8w, "L3: 2MB/core", 16-way | SPEC CPU2006 (first ref input), memory-intensive subset (>=1% LLC-miss reduction under optimal); 10 quad-core mixes, 8MB shared LLC | Pin-based CMP$im, fast-forward to SimPoint | not stated (no "warm" in the text; Table III lists instructions fast-forwarded to reach the simpoint) | 1B | SimPoint, "a single one billion instruction characteristic interval" | 1 per benchmark | geomean speedup ("geometric mean speedup of 5.9%"); predictor accuracy/coverage; dead-time fraction; no CIs | Abstract: "On average, a cache block in a 2MB LRU-managed LLC is dead 86% of the time, i.e., it will not be referenced again before it is evicted." Sec. 6: "We use SimPoint [18] to identify a single one billion instruction characteristic interval (i.e. simpoint) of each benchmark." "For single-core experiments, the infrastructure simulates one billion instructions." (people.engr.tamu.edu/djimenez/taco/pdfs/micro2010_sampler_dist.pdf) |
| 16 | SHiP: Signature-based Hit Predictor (Wu, Jaleel, Hasenplaugh, Martonosi, Steely, Emer) | MICRO 2011 | "Pin-based CMP$im simulation framework"; LLC "1MB per-core, 16-way" | 24 memory-sensitive apps from multimedia/PC games, enterprise server, SPEC CPU2006; 161 4-core mixes | SPEC: PinPoints (ref input); others: "collected on a hardware tracing platform" | not stated (only "warm up" mention concerns predictor table, Sec. 7) | 250M | PinPoints (SimPoint) for SPEC; not stated for server traces | 1 per app | per-app and average speedup over LRU; miss reduction; multi-core weighted speedup; no CIs | Sec. 4.2: "The SPEC CPU2006 workloads were collected using PinPoints [25] for the reference input set while the other workloads were collected on a hardware tracing platform. These workloads were run for 250 million instructions." |
| 17 | Cache Bursts (Liu, Ferdman, Huh, Burger) | MICRO 2008 | sim-alpha (Alpha 21264, execution-driven) for single-thread; MP-sauce (full-system, SimOS-PPC derived) for multi-threaded | 11 SPEC2000 + Versabench corner_turn, vpenta + sphinx + stream; SPECweb99, TPC-W, SPECjbb + 5 SPLASH-2 | execution-driven simulation at SimPoint regions | not stated (no "warm" in the text; author PDF compas.cs.stonybrook.edu) | "up to 2 billion instructions" | SimPoint | not stated | geomean "cache efficiency" (live fraction of capacity-time): baseline "0.08 and 0.17" for a 64KB 2-way DL1 and 1MB 16-way L2; predictor coverage/accuracy tables; no CIs | Sec. 2: "The geometric mean of the baseline cache efficiency for the L1 data cache and L2 cache ... is only 0.08 and 0.17 respectively". Sec. 4.4.1: "For each benchmark, we simulate up to 2 billion instructions identified by SimPoint [24]." |
| 18 | Dead-Block Prediction & Dead-Block Correlating Prefetchers (Lai, Fide, Falsafi) | ISCA 2001 | SimpleScalar 3.0, out-of-order, bus contention added | SPEC2K gcc, mcf, ammp, art, equake; SPEC95 compress, perl, mgrid, swim; plus bh, em3d, health, mst, treeadd (Table 2; the "suite [2]" name is cut off in the extracted text, likely Olden — not verified) | execution-driven | skip ("skipping an initialization period of one billion cycles"); no separate warm-up stated | "three billions cycles (six billion cycles for equake)" — measured in cycles, not instructions | none (single contiguous region after skip); compress run on train input over the whole input | 1 per benchmark | coverage/accuracy, speedup; no CIs | Sec. 4: "In the interest of reduced simulation time, we simulated the benchmarks for three billions cycles (six billion cycles for equake) after skipping an initialization period of one billion cycles." (archived author PDF www.ece.cmu.edu/~babak/papers/isca01.pdf) |
| 19 | Clearing the Clouds: Emerging Scale-out Workloads on Modern Hardware (Ferdman et al.) | ASPLOS 2012 | none: real hardware (32nm Intel Xeon X5670), performance counters via Intel VTune | CloudSuite scale-out (Data Serving, MapReduce, Media Streaming, SAT Solver, Web Frontend, Web Search) vs SPECint, PARSEC, SPECweb09, TPC-C, TPC-E, Web Backend | hardware counters | "after the workload completes the ramp-up period and reaches a steady state"; SAT Solver: "first 30 minutes as warmup" | 180 s window per workload; SAT Solver last 15 min; full run for PARSEC/SPEC CINT2006 | none (contiguous steady-state window); traditional server workloads included "to validate our evaluation framework" | 1 window per workload | counter-derived breakdowns (cycles, IPC, MPKI, LLC sensitivity via polluter threads); no CIs stated | Sec. 3.1: "For all scale-out and traditional server workloads except SAT Solver, we perform a 180-second measurement after the workload completes the ramp-up period and reaches a steady state." |
| 20 | AsmDB: Understanding and Mitigating Front-End Stalls in WSCs (Ayers, Nagendra, August, Cho, Kanev, Kozyrakis, Krishnamurthy, Litz, Moseley, Ranganathan) | ISCA 2019 | (i) fleet: LBR-based always-on tracing with "fleet-wide temporal and spatial sampling"; (ii) prototype: modified ZSim, trace-driven, Haswell-like single core, L1I 32KiB, L2 256KiB, 10MiB L3 allowance | Google WSC binaries (web search and others) | DynamoRIO memtrace client (instruction + data) for simulation; LBR + PEBS in production | not stated (no "warm" in the text) | "We limit traces to 2 billion instructions during steady-state execution" | fleet profile: random sample of production machines; simulation: one steady-state trace per app | not stated per app | fleet distributions (jump distances, cold-code fractions); simulated MPKI/speedup vs ideal I-cache; no CIs | Sec. 5.5: "We use DynamoRIO's [4] memtrace client to capture instruction and data memory traces for our target applications. We limit traces to 2 billion instructions during steady-state execution which is more than sufficient for instruction cache studies." (people.ucsc.edu/~hlitz/papers/asmdb.pdf) |
| 21 | Jukebox / Lukewarm Serverless Functions (Schall, Margaritov, Ustiugov, Sandberg, Grot) | ISCA 2022 | gem5 full-system, Skylake-like (L1I 32KB/8w, L1D 32KB/8w, L2 1MB/8w, LLC 8MB/16w non-inclusive); Broadwell-like variant | 20 short serverless functions in Python/NodeJS/Go (DeathStarBench Hotel Reservation, Online Boutique, AWS auth, FunctionBench AES, Fibonacci) in containers behind gRPC | gem5 checkpoint after functional (KVM) boot + "20000 invocations of each function"; plus real-HW Top-Down counters with stress-ng stressor | software state warmed by 20000 invocations (JIT stabilised); microarchitectural state deliberately NOT warm: "The baseline (1) is modeled by flushing all microarchitectural state in-between function invocations" | "simulate 20 invocations" per function in timing mode (footprint study: 25 executions) | none; whole invocations | 20 invocations per function | geomean speedup ("18.7%"; "12% geomean speedup on the Broadwell configuration"); L2/LLC instruction MPKI reduction; error bars = range across invocations (Fig. 6a) | Sec. 4.2: "we boot the system in functional mode (KVM core) and execute 20000 invocations of each function, at which point we create a checkpoint of the system state ... For the experiments, we switch to cycle-accurate timing mode and simulate 20 invocations." Sec. 5.2: "The baseline (1) is modeled by flushing all microarchitectural state in-between function invocations." (ease-lab.github.io/ease_website/pubs/JUKEBOX_ISCA22.pdf) |
| 22 | Profiling a Warehouse-Scale Computer (Kanev, Darago, Hazelwood, Ranganathan, Moseley, Wei, Brooks) | ISCA 2015 | none: production hardware; Google-Wide Profiling (GWP) via perf + PMU counters | live Google fleet jobs, "measured on more than 20,000 Google machines over a three year period" | sampled perf profiles and PMU counters | n/a (live, long-running services) | n/a ("a brief period of time" per machine-under-test) | two-level random sampling: "randomly select a small fraction of Google's server fleet to profile each day"; random time within machine | "more than 20,000 Google machines"; longitudinal studies "with durations of 12-36 months" | cycle-share distributions (datacenter tax, Top-Down breakdowns); no CIs | Sec. 2: "GWP is based on the premise of low-overhead random sampling, both of machines within the datacenter, and of execution time within a machine." (research.google pubs/archive/44271.pdf) |

## Prefetching papers (verified)
| paper | simulator | warm-up | measured | traces | stats |
|---|---|---|---|---|---|
| Bingo HPCA'19 | ChampSim | SPEC: 20M (server: SimFlex checkpoints, 40K of 200K) | SPEC: 80M | 5 checkpoints/server app, 5 SPEC mixes | "95% confidence and less than 4% error" (SimFlex) |
| Pythia MICRO'21 | ChampSim | 100M (multi-core 50M) | 500M (150M) | 150 traces, LLC MPKI >= 3 | geomean, no CIs |
| Berti MICRO'22 | ChampSim | 50M | 200M | SPEC17/GAP LLC MPKI >= 1 | geomean, no CIs |
| Hermes MICRO'22 | ChampSim | 100M (50M) | 500M (100M) | 110 traces, MPKI >= 3 | geomean, no CIs |
| SPP MICRO'16 | full text not obtained | | | | |

Our 100M windows with 20M warm-up + 80M measured are exactly Bingo's SPEC methodology.
| 23 | Pythia: Customizable Hardware Prefetching via Online RL (Bera, Kanellopoulos, Nori, Shahroodi, Subramoney, Mutlu) | MICRO 2021 | ChampSim, trace-driven; Skylake-like 1-12 cores; L1/L2 32KB/256KB 8w; "LLC 2MB/core, 64B line, 16 way, SHiP" | 150 traces from 50 workloads (SPEC CPU2006/2017 via DPC-2/DPC-3 traces, PARSEC 2.1, Ligra via Pin, CloudSuite) with LLC MPKI >= 3 | DPC traces + Intel Pin | 1C: 100M; nC: 50M per workload | 1C: 500M; nC: 150M per workload (rewind if finished early) | traces = DPC SimPoint-style slices (multiple per workload) | 150 traces / 50 workloads (~3 per workload) | geomean speedup; per-suite breakdown; tuning on 10 random traces | Sec. 5: "For single-core simulations (1C), we warm up the core using 100 M instructions from each workload and simulate the next 500 M instructions. For multi-core multi-programmed simulations (nC), we use 50 M and 150 M instructions from each workload respectively to warmup and simulate." (arXiv 2109.12021) |
