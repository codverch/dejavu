# Sampling theory and championship conventions (verified quotes)

Collected 2026-10-09 by literature sub-agents from the primary PDFs/pages (quotes verbatim; NOT FOUND
where a value could not be located). Full downloads were in the session scratchpad.

## SMARTS (Wunderlich et al., ISCA'03) — https://users.ece.cmu.edu/~jhoe/distribution/2003/isca03.pdf
- U = 1000 instructions per sampling unit: "we suggest using U = 1000 in all cases" (§4.2).
- Detailed warming W: "all the 8-way results ... with only 2000 instructions of detailed warming, and 16-way results with 4000" (§4.4); requires functional warming of caches/TLBs/BP between units (§4.1).
- Without functional warming: "even W = 500,000 results in unacceptable bias, as high as 25% for mgrid" (§4.3).
- Sample size n >= (z * V / eps)^2; "n_init = 10,000 is likely to yield 99.7% confidence interval of ±3%" (§5.1).
- Result: CPI within ±3% at 99.7% confidence measuring < 50M instructions per benchmark; average error 0.64%.

## SimPoint
- ASPLOS'02 (Sherwood et al.): BBVs per 100M instructions, k-means k=1..10, BIC; single point avg IPC error 18% (17% in conclusion), multiple points 3%; assumes perfect warm-up.
- PACT'03: 1M-instruction intervals with maxK = 300; "perfect warm-up" assumed.
- SimPoint 3.0 (JILP 2005): "we use an interval size of 10 million instructions"; "10M with MaxK=30 provides very good accuracy"; warm-up "more of an issue" with smaller intervals.

## SimFlex (IEEE Micro 2006) / TurboSMARTS / live-points (ISPASS'06)
- Multiprocessor/server: sampling unit 50,000 cycles, detailed warming 100,000 cycles, target 95% ± 5% (Table 1).
- "We impose a minimum sample size of 30 live-points to ensure that the central limit theorem holds."
- Matched-pair comparison "reduces sample size by a factor of 3.5 to 150": build the CI on the per-point delta.
- Metric for servers: user-mode IPC (U-IPC).

## Championships
- ChampSim current defaults: warmup 0, simulate to end of trace (warmup = 20% of sim if only sim given); README example 200M warm-up / 500M sim. Older ChampSim, CRC-2 kit, IPC1 tag: 1M warm-up / 10M sim defaults.
- DPC-3 (2019): SPEC CPU2017 traces with LLC MPKI >= 1.0, "running for 200 million instructions each, after a warmup of 50 million instructions"; geomean speedup.
- IPC-1 (2020): "50 million warmup instructions, plus another 50 million evaluation instructions"; traces selected where a perfect L1-I gives >= +5% IPC; 83 traces.
- CRC-2 (2017): 2 MB LLC single core; SPEC: "Select 20 benchmarks that put stress on the LLC (LLC MPKI >= 1)", "Use a SimPoint trace with the highest weight value", "200M warmup and 1B detailed execution"; CloudSuite: 6 samples of >= 100M instructions.
- CVP-1: 135 traces x 30M; 2013 traces x 100M (sampled) or 20-600M (whole).
- DPC-2 kit defaults 10M warm-up / 100M sim; evaluation lengths NOT FOUND.

## Implications for the dead-state study (our reading)
- Our 100M windows with 20M warm-up sit between IPC-1 (50M+50M) and DPC-3 (50M+200M); warm-up is shorter
  than the championship 50M. The agent20 audit config and an explicit warm-up sensitivity are needed.
- CRC-2/DPC-3 select LLC-stressing workloads (MPKI >= 1); our agent LLC MPKI is 0.89 — report it as a
  finding, not a selection.
- Use matched-pair CIs for policy deltas (we already pair per unit) and keep >= 30 units per reported cell.
