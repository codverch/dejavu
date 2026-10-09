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
