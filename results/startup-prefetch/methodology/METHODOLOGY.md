# Modelling methodology for the ideal creation-time prefetcher

Written 2026-09-26 for W3/W4 of `results/startup-prefetch/PLAN.md`. It extends
`/h/deepanjm/mise/characterization/methodology/literature_review.md` (the "prior review"),
which already covers the cold/warm question (Lukewarm, Ignite, SMARTS, LiveSim, Full Speed
Ahead, Kanev, Top-Down). This file adds what the prior review did not cover: how
prefetchers, and record/replay prefetchers in particular, are evaluated.

## Markers and sources

- **[read]** means I downloaded the full paper and read its design, methodology and
  evaluation sections (PDF text extraction with `pypdf`, figures rendered with PyMuPDF where
  needed). It does not mean I read every related-work paragraph.
- **[abstract only]** means I confirmed only the citation and abstract.
- Every number attributed to a paper below was read in that paper's text. No number in this
  file is a result of our study.
- PDFs were fetched on 2026-09-26 from the URLs in the last section.

## Terms used in this file

- **Creation region.** The instructions of one Python process creation, from `exec` to the
  first instruction of the tool's own code (PLAN.md section 1).
- **spf.** Our startup prefetcher (PLAN.md W4). *Record* is pass 1, which lists the lines a
  creation region touches. *Replay* is pass 2, which prefetches them.
- **Coverage.** The share of the baseline's demand misses at a level that the prefetcher
  turns into hits. The denominator is baseline misses.
- **Overprediction.** Prefetched lines that are never used before eviction. The papers below
  normalise it to *baseline misses*.
- **Accuracy.** Useful prefetches divided by prefetches issued. The denominator is
  *prefetches*. Overprediction and accuracy are different quantities, and Bingo says so in a
  footnote.
- **Late prefetch.** A prefetch that is still in flight when the demand access arrives.
- **Pollution.** Demand misses that would not have occurred without the prefetcher.

---------------------------------------------------------------------------------------------
## 1. Sampling and warm-up
---------------------------------------------------------------------------------------------

### 1.1 Wunderlich, Wenisch, Falsafi, Hoe. "SMARTS: Accelerating Microarchitecture Simulation via Rigorous Statistical Sampling." ISCA 2003. [read]

What the paper does:
- It simulates systematically sampled units of U instructions and fast-forwards the rest.
  The abstract states that CPI and EPI can be estimated "to within ±3% with 99.7%
  confidence by measuring fewer than 50 million instructions".
- **Stale-state bias.** Between units, functional simulation leaves microarchitectural state
  unchanged: "We have observed stale-state induced bias as high as 50% for sampling units of
  10,000 instructions."
- **Two remedies.**
  - *Detailed warming:* W instructions of detailed simulation before each unit. The paper
    says the right W is hard to derive analytically.
  - *Functional warming:* caches and branch predictors are updated during fast-forward.
- **Two kinds of error.**
  - *Random error* widens the confidence interval. It is controlled by sample size, which is
    set from the coefficient of variation (standard deviation divided by mean).
  - *Systematic error*, for example "incorrect cache hierarchy state prior to the start of a
    sampling unit", is a *bias*. A known bias can be subtracted. A bias that can only be
    bounded "introduces a proportional amount of uncertainty in the estimate beyond the
    confidence interval".

Practices we adopt:
1. **The creation region is the measurement unit. It is simulated whole, from its first
   instruction, with no warm-up.**
   - Cold state is exactly what we study, so any fixed warm-up removes the effect.
   - The prior review (section 8.3) already records that Scarab's functional `WARMUP` asserts
     when an MLC is present, which golden_cove has.
2. **Confidence over invocations, not over instructions.**
   - The population is "creations of one tool class". Report the median with the 10th-90th
     percentile band (PLAN.md), plus a 95% CI on the mean speedup.
   - If the CI half-width exceeds ±5% of the mean, add creations. The coefficient of
     variation from the first sample sets how many.
3. **Keep bias separate from noise.**
   - The golden_cove `LOG2(num_sets)` set-count bug is a systematic error. More creations do
     not shrink it.
   - We bound it by reporting every headline number under both `PARAMS.golden_cove` and
     `PARAMS.golden_cove_pow2`, and stating the gap as an uncertainty.
4. **Label stale-state windows as biased.**
   - The DynamoRIO harness windows (200M instructions every 2B) begin with empty simulated
     state, but on the native machine they ran warm.
   - Their absolute IPC therefore carries SMARTS-style cold bias. Report them as "cold-start
     window", never as the harness's steady-state IPC.

### 1.2 Sherwood, Perelman, Hamerly, Calder. "Automatically Characterizing Large Scale Program Behavior." ASPLOS 2002 (SimPoint). [read]

What the paper does:
- It collects basic block vectors (BBVs) per 100M-instruction interval and clusters them with
  k-means after random projection to 15 dimensions.
- It chooses one representative interval per cluster, weighted by cluster size.
- Its single-point IPC experiment is run so that "all the architecture structures are
  completely warmed up when starting simulation (no cold-start effect)".
- **The start of a program is the least representative place to simulate.**
  - Simulating the first 100M instructions ("none") gave "an average error of 210%".
  - Blindly fast-forwarding 1B instructions gave 80%, and a single SimPoint gave 18%.
  - Table 2 reports the end of the initialisation phase separately. The gzip clustering puts
    initialisation into its own cluster (cluster 4).
- **Rates must be combined carefully:** "Care must be taken to combine statistics correctly
  (simply averaging will give incorrect results for statistics such as rates)."

Practices we adopt:
1. **Do not use SimPoint (or any phase-based selection) to choose creation windows.**
   - SimPoint's goal is to avoid initialisation and cold start. Ours is to measure it.
   - A creation region *is* an initialisation phase. PLAN.md traces every Python tool process
     under 200M instructions whole, which is the right choice.
2. **Aggregate rates from sums.**
   - Report the IPC of a class of creations as Σinstructions / Σcycles, or show the
     per-creation distribution. Do not average per-creation IPCs.
   - The same applies to MPKI and to "share of perfect bound recovered". Compute that share
     from summed cycles, and also give its per-creation distribution.
3. **Optional cross-check of identity.** A BBV Manhattan distance between consecutive
   creations of one class is an independent measure of "same work", alongside W1's
   32-instruction-sequence identity. Not required.

---------------------------------------------------------------------------------------------
## 2. Record/replay prefetching of short invocations (closest prior work)
---------------------------------------------------------------------------------------------

### 2.1 Schall, Margaritov, Ustiugov, Sandberg, Grot. "Lukewarm Serverless Functions: Characterization and Optimization." ISCA 2022. doi:10.1145/3470496.3527390. (Jukebox) [read]

Jukebox is the closest prior work to spf. Here is exactly what it does.

**What is recorded.**
- Only **L2 instruction misses**. The record logic sits at the L1-I: "On an L2 hit, the
  Jukebox record mechanism takes no action, effectively filtering all L2 hits." A miss is
  recorded "when the miss finally returns to the L1-I".
- **Virtual** addresses are recorded, so the scheme survives page migration and compaction.
- **Encoding.**
  - A 16-entry, fully associative FIFO, the Code Region Reference Buffer (CRRB), coalesces
    misses by 1 KB code region.
  - Each entry is a 38-bit region pointer plus a 16-bit access vector, 54 bits in total.
  - An evicted entry is written to memory and never modified again. The same region can
    therefore appear more than once in the record.
- **Order.** The FIFO order encodes first-touch order at region granularity. Within a region,
  replay reorders the lines.
- **Size.** Metadata is capped at 16 KB for record plus 16 KB for replay (Table 1). The
  metadata-size sweep (Fig. 9) found "little gain with increasing metadata storage beyond
  16KB". With 1 KB regions, the record needs 9.6 to 29.5 KB (Fig. 8).

**When recording and replay happen.**
- Recording starts "as soon as the container running the function has been launched".
- Replay is "triggered by the OS upon receiving a new function invocation", through a pair of
  base/limit registers. The scheduler may start it when it assigns the instance thread to a
  core.
- Each invocation replays the metadata written by the *previous* invocation of the same
  instance, and records afresh.

**What replay does and where lines go.**
- The engine reads metadata sequentially and translates each region's base address through
  the I-TLB. This also pre-populates the TLB.
- It then enqueues every line in the access vector in the **L2 prefetch queue**. Lines land
  in the **L2**, not the L1-I.
- The authors give two reasons for the L2: footprints of 300-800 KB fit a 1 MB L2 but not a
  32-64 KB L1-I, and bulk-filling a large L2 avoids timing prefetches into a small L1.
- Replay issues everything "without synchronizing with the core" (section 5.5). This bulk
  issue is how they explain beating PIF, which re-indexes on divergence.

**Baselines and bounds.**
- *Baseline:* "flushing all microarchitectural state in-between function invocations".
- *Upper bound:* "Perfect I-cache", an infinite L1-I that holds the instruction footprint
  accumulated over all simulated invocations.
- *Competitor:* PIF with its published sizes, and "PIF-ideal" with unlimited index and
  metadata that persist across invocations.
- *Setup:* gem5 full system, so both kernel and user code are simulated. They boot in KVM,
  run 20,000 invocations, take a checkpoint, then simulate 20 invocations in timing mode.

**How results are reported.**
- **Speedup [%]** per function, normalised to the baseline, with the geomean (Fig. 10).
  Perfect I-cache gives 31% on average and Jukebox 18.7%.
- **Coverage (Fig. 11):** "fractions of L2 instruction misses in the baseline that are (1)
  covered, (2) not covered, and (3) overpredicted (i.e., prefetched but not referenced)",
  all normalised to the number of baseline L2 instruction misses. They report an average
  overprediction of 10%, with a maximum of 15.8%.
- **Memory bandwidth increase [%] over the baseline (Fig. 12).**
  - The denominator is all memory requests: instruction and data, demand and prefetch.
  - The overhead is split into overpredicted lines, record metadata and replay metadata:
    14% on average, 23% worst case.
  - "Jukebox does not change the amount of bandwidth consumed for correct timely prefetches."
- **MPKI reduction per level (Table 3).** For L2 and LLC instruction misses, on two cache
  configurations.
- **Sensitivity to the target L2 size.** On a 256 KB L2 (Broadwell-like), L2 instruction
  misses fall only 15%, against 74% on the 1 MB Skylake-like L2, because "many of Jukebox's
  prefetches [are] evicted from the L2 before they are consumed".

**Mapping onto our experiment.**

| Jukebox | spf (PLAN.md W4) | Consequence |
|---|---|---|
| Records L2 instruction misses only | Records every distinct line the region touches, I and D, in first-touch order, with the serving level | spf's `instant` bound is at least as large as Jukebox's. Also report a Jukebox-like *filtered* variant: record only lines that missed the L2 in the cold run, instructions only. This separates "record everything" from "record misses". |
| 1 KB regions, 16 KB metadata cap | Plain list of line addresses, no cap | Report the replay-list size in bytes per creation class, so metadata cost is visible. Say plainly that uncapped metadata is part of the ideal. |
| Replays the previous invocation's record | `--spf_source prev` (previous creation of the same class, ASLR-rebased) | `prev` is the Jukebox analogue. `self` is stronger than anything Jukebox evaluates; call it the oracle. |
| Trigger: OS schedules an invocation | Trigger: W2's predicted creation point (end of `response.parse`) | Jukebox has no false positives because invocations are known. We must report the oracle trigger and the W2 trigger separately (PLAN.md already requires this). |
| Bulk issue through the L2 prefetch queue, no pacing | `instant` (no queue, no bandwidth) and `stream:<d>` (paced) | Jukebox is neither. We recommend a third timing, `bulk`: issue every recorded line at the trigger through the normal prefetch queue as fast as it drains. That is the Jukebox policy and the natural realistic reference. **Not in PLAN.md; proposed to W4, not adopted unilaterally.** |
| Destination L2 | `--spf_dest l1d/l2/llc` (+ l1i) | Sweep every destination (PLAN.md). Because of the set-count bug, the golden_cove L2 behaves as 1 MB. Jukebox's own 256 KB vs 1 MB result shows the answer depends on L2 capacity, so the pow2 config is required, not optional. |
| Baseline flushes all state between invocations | Cold = pass 1 of `--memtrace_repeat` | Same definition. |
| Upper bound: infinite L1-I holding the footprint | `--perfect_{icache,dcache,mlc,l1}` | Scarab's perfect flags turn every access into a hit, including first touches of fresh heap addresses that no replay can predict. Our perfect bound is therefore *looser* than Jukebox's. "Share of perfect bound recovered" understates spf relative to a footprint bound. Report `instant+self` as a second, footprint-style bound. |
| Coverage normalised to baseline L2 instruction misses, split covered/uncovered/overpredicted | PLAN.md: coverage, accuracy | Add the three-way split, with the Jukebox denominator, per level and split I/D. |
| Bandwidth % over all baseline memory requests, split overpredicted / record metadata / replay metadata | PLAN.md: "extra bytes from memory" | Use the same denominator and split. Replay-list reads are a real cost of `prev`; under `instant` they are zero by construction, which must be said. |
| Full system (kernel included) | User-level DynamoRIO traces | Kernel exec, page faults and syscalls are missing. Jukebox's footprints include kernel lines; ours cannot. State this next to every comparison with Jukebox numbers. |

### 2.2 Schall, Sandberg, Grot. "Warming Up a Cold Front-End with Ignite." MICRO 2023. doi:10.1145/3613424.3614258. [read]

What the paper adds beyond Jukebox:
- **Record.** It records **BTB insertions** (taken branches only), delta-encoded (7-bit and
  21-bit fields), into a per-container memory region. The metadata limit is 120 KiB.
- **Replay.** Each record does three things:
  - it prefetches the branch's instruction block **into the L2**;
  - it inserts the entry into the BTB;
  - for a conditional branch, it sets the bimodal (BIM) entry to weakly taken.
- **Throttling.** Replay is throttled when more than 1K restored BTB entries have not yet
  been accessed.
- **Replay starts with the function.** "by starting replay together with the function,
  Ignite loses the opportunity to cover misses at the very start of a function's execution".
- **Baseline and bound.**
  - The baseline is a next-line instruction prefetcher plus a stride data prefetcher, used in
    all configurations. Speedup is normalised to it.
  - The "Ideal" front end is a perfect L1-I, a perfect BTB and a pre-trained CBP.
  - Cold is modelled by flushing all structures between invocations and overwriting the
    bimodal predictor with random state.
- **Jukebox leaves the rest of the front end cold.**
  - Jukebox gives a 16% speedup, Boomerang+Jukebox 20%, and the Ideal front end 61%
    (section 3.1).
  - With a cold BPU, fetch-directed prefetching runs down the wrong path. Next-line
    instruction traffic is 25% useless (wrong path), and Boomerang+JB increases useless
    fetches further.
- **Restore accuracy (Fig. 9c).** For each restored structure (L2, BTB, CBP), misses are
  split into covered, uncovered and overpredicted. For L2 and BTB, overpredicted means
  "installed by Ignite but never used".
- **Bandwidth (Fig. 10).** Absolute bytes per invocation, split into useful instructions,
  useless instructions (including wrong-path), record metadata and replay metadata. This is
  the worst case, with record and replay simultaneous.
- **Initial vs subsequent mispredictions.** Mispredictions are split into *initial* (first
  dynamic execution of a branch) and *subsequent* (prior review, section 1.4).

Mapping:
1. **spf prefetches cache lines only.** The BTB, the branch predictors and the uop cache stay
   cold.
   - golden_cove runs FDIP (`fdip_enable` defaults to 1 in
     `src/prefetcher/pref.param.def:161`; PARAMS.golden_cove does not override it). By
     Ignite's argument, FDIP on a cold BTB/BP fetches down wrong paths.
   - So, in every spf configuration, report BTB and conditional-predictor MPKI, and the
     cycles with `--perfect_bp`/`--perfect_btb` added on top of spf. This shows how much of
     the gap to "all perfect" is front-end state that a cache-only prefetcher cannot restore.
2. **Our trigger fires before the process exists.** Ignite loses the very start of each
   function. spf triggers at the end of `response.parse`, before `exec`. W2's lead-time CDF
   measures exactly the advantage Ignite lacks.
   - Under `stream:<d>` and the proposed `bulk`, report the coverage of the first N (for
     example 1M) instructions separately, because that is where Ignite says replay-at-start
     loses coverage.
3. **Report traffic in absolute bytes per creation as well as percent.** Ignite's Fig. 10
   format (useful vs useless vs metadata) is readable at a glance.

---------------------------------------------------------------------------------------------
## 3. Temporal instruction streaming: record/replay of miss streams
---------------------------------------------------------------------------------------------

### 3.1 Ferdman, Wenisch, Ailamaki, Falsafi, Moshovos. "Temporal Instruction Fetch Streaming." MICRO 2008. [read]

What the paper does:
- **Opportunity study.**
  - They trace L1-I misses (user and OS, collected with Flexus) and find repeated
    subsequences with SEQUITUR.
  - Each miss is classified as **Non-repetitive**, **New** (first occurrence of a repeating
    stream), **Head** (first miss of a later occurrence) or **Opportunity** (the remaining
    misses of a later occurrence).
  - Head and New are separated out "because our hardware mechanisms are not be able to
    eliminate these misses due to training and prediction-trigger mechanisms". They find 94%
    of misses on average are part of a recurring stream.
- **Stream-lookup heuristics** (First, Digram, Recent, Longest) are compared against the
  SEQUITUR bound, which "represents perfect stream lookup".
- **Sensitivity study.** Each L1-I miss that is on chip is turned into an instant hit with
  probability p, and performance is plotted against p. p = 100% "approximates a perfect and
  timely instruction prefetcher". Because results come from sampled simulation, they fit
  regression lines.
- **Credit only beyond the baseline prefetcher.** "We account TIFS hits only in excess of
  those provided by the next-line instruction prefetcher."
- **Traffic.**
  - *Discards* are prefetched blocks replaced before use.
  - Coverage and discards are normalised to L1 fetch misses.
  - Total L2 traffic overhead is a fraction of base L2 traffic (reads, fetches and
    writebacks): 13% on average.
- **Comparison.** Against FDIP tuned in FDIP's favour (unlimited tag bandwidth, deeper
  lookahead), and against "Perfect", a perfect instruction-streaming upper bound.

Mapping:
1. **Opportunity accounting for spf.** Classify each creation-region miss in the cold
   baseline as:
   - (a) the line is in the replay list, so coverable;
   - (b) the line is not in the list because it is new in this creation (the `prev` source,
     for example a fresh heap address);
   - (c) the line is in the list but was evicted before use.

   Class (b) is the TIFS "New"/"Non-repetitive" analogue. It bounds `prev` below `self`
   without any simulation. W1's identity CDF gives the instruction side; the data side needs
   this line-level count.
2. **Credit spf only beyond golden_cove's own prefetchers.** The baseline keeps its L1-D
   stream prefetcher and FDIP on. Coverage is measured against the misses that remain in
   that baseline, not against a no-prefetch machine. This is the TIFS rule.
3. **Traffic denominator.** Use the baseline's total traffic at the destination level
   (reads, fills and writebacks), as TIFS does, and the baseline's memory requests, as
   Jukebox does. State which one each figure uses.

### 3.2 Ferdman, Kaynak, Falsafi. "Proactive Instruction Fetch." MICRO 2011. [read]

What the paper does:
- **Record the retire-order stream.** It records the correct-path, retire-order instruction
  stream, compacted into spatial regions with bit vectors, rather than the L1-I miss or
  access stream. Cache filtering and wrong-path noise make the miss/access streams less
  repetitive.
- **Coverage definition** (footnote 1): "the fraction of the correct-path instruction cache
  misses predicted through temporal correlation". Correct-path accesses that were already
  fetched by wrong-path misses count as hits and are excluded.
- **Perfect-latency cache bound** (footnote 3): it "always returns the requested instruction
  block with the latency of a cache hit, with all other externally-observed behaviors of the
  cache matching the Next-Line configuration".
  - PIF reaches 27% against 29% for the perfect cache.
  - On two benchmarks PIF slightly exceeds the "perfect" design, because the perfect cache
    puts more pressure on the interconnect.
- **Measurement.**
  - SimFlex sampling launched from checkpoints with warmed caches, prefetcher tables and
    branch predictors.
  - 100,000 cycles warm queues and the interconnect; the next 50,000 cycles are measured.
  - Speedup uses user IPC (UIPC) "at a 95% confidence level with less than ±5% error".

Mapping:
1. **spf's record is already a retire-order stream.** DynamoRIO traces contain committed,
   correct-path instructions only, so pass 1 lists what the program *needs*, not what a
   cold machine happened to miss. This is the PIF argument for recording before the cache
   filter. Say so when explaining why `self` is an oracle.
2. **A "perfect" bound need not be a strict upper bound.**
   - PIF beat its perfect cache through second-order effects. In Scarab, perfect caches can
     change FDIP run-ahead and queue occupancy the same way.
   - The PLAN.md regression check ("all four perfect ≤ any one perfect ≤ baseline") stays.
   - If spf ever beats the matching perfect configuration, report it and explain it. Do not
     clip "share of bound recovered" at 100%.
3. **Use the PIF coverage definition for instruction lines:** covered correct-path demand
   misses divided by the baseline's correct-path demand misses. Scarab models some wrong-path
   fetch. State whether its wrong-path accesses are counted, which is not yet verified (see
   "Items not verified").

---------------------------------------------------------------------------------------------
## 4. Data prefetcher evaluation: definitions and oracle bounds
---------------------------------------------------------------------------------------------

### 4.1 Somogyi, Wenisch, Ailamaki, Falsafi, Moshovos. "Spatial Memory Streaming." ISCA 2006. [read]

Definitions and methods:
- **Coverage** "represents the fraction of L1 read misses that are eliminated by SMS".
- **Overpredictions** "represent blocks that are fetched but not used prior to eviction or
  invalidation, and thus waste bandwidth".
- **Pollution** is folded into the uncovered category: "Overpredictions can also cause cache
  pollution; this effect is implicitly taken into account because the additional misses are
  categorized as uncovered."
- **Oracle opportunity:** "an oracle predictor that incurs only one miss per spatial region
  generation". It is compared against simply enlarging the cache block, and reported as
  misses per instruction normalised to 64 B blocks with no predictor.
- **Coverage is studied with an infinite pattern history table** "to assess the true
  opportunity without regard to storage limitations", before storage is limited.
- **Sampling.** SMARTS-style sampling with "95% confidence intervals that target ±5% error on
  change in performance, using paired-measurement sampling".
- **Time breakdown (Fig. 13).** Base and SMS bars are "normalized to represent the same
  amount of completed work", so relative bar height is speedup and the segments are stall
  categories. They also explain where coverage did *not* turn into speedup: overlapped
  misses in OLTP, and store-buffer stalls in Qry1.

Mapping:
1. **Paired measurement.**
   - Each creation is simulated under cold, self-warm, perfect and every spf configuration.
     The per-creation *difference* is the unit of analysis.
   - Report the CI of the paired difference, not two independent CIs. Paired CIs are
     narrower and correct here.
2. **Count pollution inside the coverage split.** Demand misses that spf *adds* (lines it
   evicted) are counted as uncovered or new misses, not silently netted out. Report the count
   of spf-induced misses separately as well.
3. **Explain gaps between coverage and speedup.**
   - When coverage is high but speedup is low, say why: for example, misses that the
     out-of-order core already overlapped (Scarab's MLP), or front-end state that is still
     cold (section 2.2).
   - Use a same-work stall breakdown (SMS Fig. 13 style) for cold vs spf vs perfect on one
     creation class.

### 4.2 Michaud. "Best-Offset Hardware Prefetching." HPCA 2016. [read]

Note: the file at `irisa.fr/.../BOP_HPCA_2016.pdf` is the talk slides. The paper text was
read from the IEEE copy hosted at safari.ethz.ch (URL below).

Definitions and methods:
- **Timeliness is the design goal.** An offset d is good for line X only if X−d was accessed
  "recently, but not too recently". "Ideally, the time between the accesses to lines X − d
  and X should be greater than the latency for completing a prefetch request."
- **A late prefetch is still useful.** "Late prefetches may accelerate the execution, but not
  as much as timely prefetches."
- **How late prefetches are modelled.** The simulator has fill queues instead of L2/L3
  MSHRs. "When a demand miss hits in a fill queue and the block in the fill queue was
  prefetched, the miss request is dropped and the block ... is promoted from prefetch to
  demand miss."
- **Prefetchers are evaluated inside the full memory system.** "a hardware prefetcher cannot
  be evaluated as a stand-alone mechanism, as it interacts with other parts of the
  microarchitecture in a very complex way."
  - The baseline has an L1 stride prefetcher and an L2 next-line prefetcher. The paper shows
    the effect of disabling each (Figs. 4 and 5).
  - Speedups are "relative to the baselines with L2 next-line" enabled.
- **Stated simulator limits:** trace-driven, Pin-based, "operating system activity is not
  simulated", and no wrong-path instructions.

Mapping:
1. **Evaluate spf on top of golden_cove's prefetchers, not instead of them.** Also run one
   sensitivity with the L1-D stream prefetcher off, to show how much of the cold-miss
   population that prefetcher already covers.
2. **Timeliness is three-way.**
   - For `stream:<d>` and `bulk`, report timely hits, late prefetches, and prefetched lines
     that are never used.
   - For late prefetches, also report the latency that remains exposed. Scarab has
     `L1_LATE_PREF_CYCLES` and `L1_LATE_PREF_CYCLES_DIST_*` in
     `src/prefetcher/pref.stat.def`. Whether spf-injected requests reach those counters must
     be checked.
3. **State the same limits BOP states:** no OS, and trace-driven with limited wrong-path
   fidelity.

### 4.3 Bakhshalipour, Shakerinava, Lotfi-Kamran, Sarbazi-Azad. "Bingo Spatial Data Prefetcher." HPCA 2019. [read]

Definitions and methods:
- **Miss coverage** is "the fraction of cache misses eliminated by the prefetcher".
- **Accuracy** "is the percentage of all prefetched cache blocks that have been used by the
  processor before eviction".
- **Overpredictions** "are incorrect prefetches, which are normalized to the number of data
  misses in the baseline system without a prefetcher". A footnote says overprediction is
  "Not to be confused with accuracy".
- **Figure 7** is a stacked bar per workload: Coverage, Uncovered and Overprediction, all
  over baseline misses.
- **Storage sizing rule.** Each competitor starts at its published configuration. Its tables
  are grown until average coverage stops changing by more than 5%.
- **Sampling.** SimFlex checkpoints; 200K instructions per checkpoint, of which the first 40K
  warm queues; "95% confidence and less than 4% error". SPEC runs use 20M instructions of
  warm-up followed by 80M measured.

Mapping:
1. **Report both overprediction and accuracy, and label them distinctly.**
   - Overprediction = unused spf prefetches / baseline misses.
   - Accuracy = used spf prefetches / spf prefetches.
   - A creation region with few baseline misses and a long replay list can have low
     overprediction yet low accuracy. Both matter.
2. **Size-sensitivity rule for `prev` replay lists.** If W4 caps the list (Jukebox-style),
   grow the cap until mean coverage changes by less than 5%, and report the knee.

### 4.4 Srinath, Mutlu, Kim, Patt. "Feedback Directed Prefetching: Improving the Performance and Bandwidth-Efficiency of Hardware Prefetchers." HPCA 2007. [read]

Exact definitions (section 2.2):
- **Prefetch accuracy** = useful prefetches / prefetches sent to memory. A useful prefetch
  is a "prefetched cache block[] that [is] used by demand requests while [it is] resident in
  the L2 cache".
- **Prefetch lateness** = late prefetches / useful prefetches. A prefetch is late "if the
  prefetched data has not yet returned from main memory by the time a load or store
  instruction requests the prefetched data". In hardware, this is a demand request that hits
  an MSHR entry whose pref-bit is set.
- **Prefetcher-generated cache pollution** = demand misses caused by the prefetcher / demand
  misses. "A demand miss is defined to be caused by the prefetcher if it would not have
  occurred had the prefetcher not been present." In hardware this is approximated with a
  4096-entry Bloom-style filter.
- **Bandwidth metric: BPKI.** Memory bus accesses per thousand retired instructions. They use
  "Bus Accesses (rather than the number of prefetches sent) ... because this metric includes
  the effect of L2 misses caused due to demand accesses as well as prefetches."
- **Method.** Fast-forward past initialisation, then simulate 250M instructions of each
  benchmark that sends at least 200K prefetches.

Mapping:
1. **Scarab contains this paper's mechanism, and golden_cove turns it on.**
   - `PARAMS.golden_cove` sets `--pref_throttlefb_on=1`, `--pref_acc_thresh_{1,2,3}`,
     `--pref_timely_thresh=0.01`, `--pref_polpf_thresh=0.005` and
     `--pref_update_interval=8192`.
   - `pref_common.c` has a "Feedback directed prefetching" block, and `pref_stream.c`
     checks `PREF_THROTTLEFB_ON`. Checked in `/h/deepanjm/dejavu/src` on 2026-09-26.
   - **Consequence for W4:** spf's injected prefetches must not feed the stream
     prefetcher's accuracy, lateness or pollution counters. If they do, spf changes the
     baseline prefetcher's aggressiveness and the comparison is confounded.
   - W4 must either keep spf requests out of the FDP counters, or report that they are
     included and show the stream prefetcher's degree with and without spf.
2. **Use FDP's definitions verbatim** for accuracy, lateness and pollution, but measure
   pollution *exactly* rather than with a filter.
   - Paired runs give the counterfactual directly: demand misses in the spf run at lines that
     hit in the no-spf run.
   - This is how `fig_pollution.png` (the harness window after a false positive) should be
     computed.
3. **Traffic is bus/DRAM accesses per kilo-instruction, including demand misses caused by
   pollution.** It is not a count of spf prefetches. Report BPKI alongside bytes.

### 4.5 How the papers use ideal and oracle prefetchers as bounds

| Paper | Bound | What it assumes |
|---|---|---|
| TIFS | Probabilistic "prefetch coverage p" and "Perfect" streaming | On-chip misses become instant hits with probability p |
| TIFS | SEQUITUR "Opportunity" | Perfect stream lookup; Head and New misses not coverable |
| PIF | Perfect-latency L1-I | Every fetch at hit latency, other behaviour unchanged |
| SMS | Oracle: one miss per spatial region generation | Perfect spatial prediction; infinite PHT for coverage |
| Jukebox | Perfect I-cache = infinite L1-I holding the footprint of all invocations | Footprint-limited, not "every access hits" |
| Ignite | Ideal front end = perfect L1-I + perfect BTB + pre-trained CBP | Front end only |
| Jukebox | PIF-ideal: unlimited, persistent metadata | A competitor given unbounded storage |

What we take from the table:
1. **Every paper names the bound's assumptions.** Ours are:
   - `--perfect_*`: every access at that level hits, including lines no replay could know;
   - `instant+self`: every recorded line present at process start, with zero bandwidth and
     zero metadata.

   Label both "ideal" in every figure (PLAN.md already requires "ideal ... labelled as
   such").
2. **Bounds are drawn in the same figure and the same units as the mechanism:** Jukebox
   Figs. 10 and 13, Ignite Fig. 8, PIF Fig. 10. PLAN.md's `fig_speedup_by_config.png` with
   perfect and self-warm marked follows this.

---------------------------------------------------------------------------------------------
## 5. Simulator trust and representativeness
---------------------------------------------------------------------------------------------

### 5.1 Nowatzki, Menon, Ho, Sankaralingam. "Architectural Simulators Considered Harmful." IEEE Micro, Nov/Dec 2015 (volume 35, pp. 4-12 per the IEEE/ACM listing). doi:10.1109/MM.2015.74. [read]

Points relevant to us:
- **Pitfall 1a, over-simplified abstractions.** Documentation implies that what is not
  modelled does not matter. Their advice: "simulator writers document the reasons for
  abstraction decisions and explicitly describe inappropriate use cases."
- **Pitfall 2a, inaccessible simulator errors.** Their gem5 examples include a pipeline flush
  when MSHRs run out, and mislabelled micro-ops. Advice: "validate and sanity check the
  simulator with their own workloads and microbenchmarks."
- **Pitfall 2b, the "trends myth".** Relative comparisons are only trustworthy if "the new
  technique being evaluated ... [is] insulated from or statistically uncorrelated with the
  source of simulation errors."
- **Pitfall 2c, false confidence from validation.** Validation at one design point does not
  carry over when parameters change.
- **Pitfall 3c, first-order analysis.** "a first-order analysis of a technique's effects
  should be required ... Unless the authors can demonstrate with a simple first-order
  analysis why something works, demonstrating improvements on certain metrics of interest is
  not useful."
- **Terminology.** They avoid the term "cycle-accurate", which "implies accuracy to an
  existing system at cycle granularity, which is rarely the case".

Mapping:
1. **The set-count bug is correlated with our effect.** The trends myth applies directly.
   - golden_cove's `LOG2(num_sets)` masking makes the L2 behave as 1 MB and the LLC as 2 MB
     (PLAN.md trap 9).
   - Whether a creation footprint fits in the L2 is the very thing that decides spf-into-L2
     gains (compare Jukebox's 256 KB vs 1 MB result).
   - The bug is therefore *not* uncorrelated with the technique. Every headline number is
     reported under both configurations, and neither is called "the" result.
2. **First-order model before simulation claims.** For each creation class, predict the spf
   gain from:
   (covered baseline misses at level L) × (latency difference between L and the next level)
   ÷ (observed memory-level parallelism).

   Show it next to the simulated gain. If they disagree by more than about 2×, explain the
   difference before reporting the simulated number.
3. **Write "cycle-level simulation (Scarab)", not "cycle-accurate".**
4. **List blind spots with every result**, as the paper's pitfall 1a asks simulator writers
   to do:
   - no kernel;
   - no TLB model (prior review, section 6);
   - the set-count bug;
   - trace-driven wrong-path fidelity;
   - a single core with no co-runners.
5. **Sanity-check microbenchmarks.** A synthetic trace that touches N distinct lines once,
   replayed with `instant+self`, must show exactly N cold misses and 0 misses after replay
   (minus evictions). That is a Nowatzki-style own-workload check of the spf plumbing. It
   complements the correctness checks in PLAN.md W4.

### 5.2 Kanev, Darago, Hazelwood, Ranganathan, Moseley, Wei, Brooks. "Profiling a Warehouse-Scale Computer." ISCA 2015. [read, partial — sections 1-4]

Points relevant to us, beyond those in the prior review (section 2.1):
- **Cycles, not MPKI.** Top-Down counts stall costs "in cycles, as opposed to ... miss rates,
  misses per kilo-instruction". The paper warns that "a high value for MPKI in the L1
  instruction cache can raise a false alarm ... misses in the L1 alone cause very little
  end-performance impact."
- **Counter hygiene.**
  - They validate counters with microbenchmarks, because "errata in more exotic performance
    counters can be common".
  - They use only "counter expressions that can fit ... a core's performance monitoring unit
    (PMU) in a single measurement (time-multiplexing the PMU often results in erroneous
    counter expressions)".
- **Distributions, not means.** Boxes span the 25th to 75th percentiles around the median;
  whiskers span the 10th to 90th.
- **Representativeness.** The fleet differs "from common wisdom for optimizing SPEC-like or
  open-source scale-out workloads".

Mapping:
1. **Rank structures and configurations by cycles saved.** MPKI changes appear only as
   supporting evidence (PLAN.md).
2. **Native cross-checks follow Kanev's counter hygiene.** Any perf counter used to
   cross-check the direction of an effect must be:
   - collected in one PMU group without multiplexing (check `perf stat` for the
     "(xx.xx%)" multiplex marker);
   - validated with a microbenchmark;
   - collected under the throttle rules in PLAN.md trap 2.
3. **Show variation over creations as box plots** with a 25-75 box and 10-90 whiskers,
   matching PLAN.md's 10th-90th band.
4. **Representativeness.** We study one SWE-bench task (django__django-13809, python3.8). Say
   so in every figure caption. Do not generalise to other interpreters or harnesses without
   data (PLAN.md open question 4).

---------------------------------------------------------------------------------------------
## 6. Practices this study follows
---------------------------------------------------------------------------------------------

Each item gives the practice, its source, how we implement it, and how an agent verifies it.

1. **Simulate each creation region whole from its first instruction, with no warm-up.**
   - Source: SMARTS [read]; SimPoint [read]; prior review section 8.3.
   - Implement: cold = pass 1 of `--memtrace_repeat`; no `--warmup`; no SimPoint selection.
   - Verify: `grep -i warmup` in every sim command in `logs/sim-*.log` returns nothing, and
     Scarab's instruction count equals the trace's to within 0.1% (PLAN.md W3 check).
2. **Report bounds next to the mechanism in the same units.** Cold, self-warm, each perfect
   level, all-perfect, `instant+self`, and the realistic spf configurations.
   - Source: Jukebox Fig. 10 [read]; Ignite Fig. 8 [read]; PIF Fig. 10 [read].
   - Implement: `fig_speedup_by_config.png` shows all of them on one axis (speedup over cold,
     %).
   - Verify: every configuration name in `results.csv` appears in the figure's legend or
     labels.
3. **Label ideal configurations as ideal and state their assumptions.** `instant` has zero
   bandwidth, zero metadata and no queue. `--perfect_*` makes every access hit.
   - Source: section 4.5 table (TIFS, PIF, SMS, Jukebox, Ignite).
   - Implement: the word "ideal" appears in those legend entries, and captions state the
     assumptions.
   - Verify: `grep -l ideal fig_*.txt` covers every figure that contains `instant` or
     perfect bars.
4. **Coverage split into covered / uncovered / overpredicted, normalised to baseline misses,
   per level, split I/D.**
   - Source: Jukebox Fig. 11 [read]; Ignite Fig. 9c [read]; Bingo Fig. 7 [read]; SMS
     section 4 [read].
   - Implement: columns `cov_covered`, `cov_uncovered`, `cov_overpred` per level and side in
     `results.csv`.
   - Verify: for each row, covered + uncovered = baseline misses (±spf-induced misses, which
     get their own column).
5. **Accuracy, reported separately from overprediction.**
   - Source: Bingo footnote 9 [read]; FDP section 2.2.1 [read].
   - Implement: accuracy = used spf prefetches / issued spf prefetches.
   - Verify: both columns exist and differ in their denominators; the README states both
     formulas.
6. **Lateness, using the FDP definition.** Late = the demand arrives while the spf prefetch
   is in flight (MSHR hit on a prefetch). Lateness = late / useful. Also report the exposed
   latency.
   - Source: FDP [read]; BOP section 5.4 [read].
   - Implement: from Scarab `L1_PREF_LATE`/`MLC_PREF_LATE`/`L1_LATE_PREF_CYCLES*`, or from
     spf's own counters if those stats do not see spf requests.
   - Verify: under `instant`, lateness = 0 by construction. A test that asserts this must
     pass.
7. **Pollution, measured exactly by the paired counterfactual.**
   - Source: FDP definition [read]; SMS "implicitly ... uncovered" [read].
   - Implement: demand misses in the spf run to lines that hit in the paired no-spf run,
     including in the harness window after a false-positive trigger.
   - Verify: pollution = 0 when `spf_mode=off` (bit-identical check in PLAN.md W4).
8. **Traffic, with a stated denominator, split into useful / overpredicted / metadata, plus
   BPKI.**
   - Source: Jukebox Fig. 12 [read]; Ignite Fig. 10 [read]; TIFS section 6.4 [read]; FDP
     BPKI [read].
   - Implement: `fig_traffic.png` shows absolute bytes per creation, stacked; the CSV also
     has % over baseline memory requests and BPKI.
   - Verify: the stacked components sum to the total within rounding; the caption names the
     denominator.
9. **Credit spf only beyond golden_cove's own prefetchers.**
   - Source: TIFS section 6.1 [read]; BOP section 5 [read].
   - Implement: the baseline keeps the L1-D stream prefetcher and FDIP on. One sensitivity
     run turns the stream prefetcher off.
   - Verify: the sim commands for baseline and spf differ only in `--spf_*` flags (diff the
     logged command lines).
10. **Keep spf out of the baseline's feedback throttling (FDP counters).**
    - Source: FDP [read]; `PARAMS.golden_cove` (`pref_throttlefb_on=1`), checked in the
      source.
    - Implement: W4 tags spf requests so the stream prefetcher's accuracy, lateness and
      pollution counters ignore them, or documents that they do not.
    - Verify: the stream prefetcher's issued-prefetch count in the spf run equals the no-spf
      run's, or the difference is reported and explained.
11. **Bracket the cache-only bound with front-end state.**
    - Source: Ignite sections 3 and 6 [read].
    - Implement: report BTB/BP MPKI in spf runs, plus spf + `--perfect_bp --perfect_btb`.
    - Verify: rows for those configurations exist in `results.csv`.
12. **Opportunity accounting before simulation.** Split baseline misses into coverable /
    new-this-creation / evicted-before-use.
    - Source: TIFS section 4 [read]; SMS oracle [read].
    - Implement: `w4_ideal_prefetch/opportunity.csv`, computed offline from the record
      lists and the cold-run miss addresses.
    - Verify: the three classes sum to the baseline miss count for each creation.
13. **Paired statistics over creations: median, 10-90 band, 95% CI of the paired
    difference.**
    - Source: SMARTS [read]; SMS paired-measurement sampling [read]; Kanev box plots [read].
    - Implement: every speedup figure shows per-creation distributions. The README gives the
      CI and n.
    - Verify: n ≥ 10 per class, or the README states why not. If the CI half-width exceeds
      5%, that is stated.
14. **Aggregate rates from sums, not means of ratios.**
    - Source: SimPoint section 5.2 [read].
    - Implement: class IPC = Σinstr / Σcycles; share of bound recovered is computed from
      summed cycles.
    - Verify: a unit test recomputes one class aggregate from `results.csv` both ways and
      shows the sum-based value is the one reported.
15. **Rank by cycles, not MPKI.**
    - Source: Kanev [read]; prior review.
    - Implement: headline tables sort by cycles saved. MPKI is secondary.
    - Verify: in REPORT.md, no claim of importance rests on MPKI alone.
16. **Report every headline under golden_cove and golden_cove_pow2, and treat the gap as
    bias.**
    - Source: Nowatzki "trends myth" [read]; SMARTS bias vs random error [read]; Jukebox L2
      sensitivity [read].
    - Implement: two rows per configuration.
    - Verify: `results.csv` has both config values for every headline row.
17. **First-order prediction next to each simulated gain.**
    - Source: Nowatzki pitfall 3c [read].
    - Implement: `w4_ideal_prefetch/first_order.csv` with the predicted and simulated
      columns.
    - Verify: rows whose ratio is outside [0.5, 2] carry an explanation in the README.
18. **State blind spots in every README:** no kernel, no TLB model, the set-count bug,
    limited wrong-path fidelity, one core.
    - Source: Nowatzki pitfall 1a [read]; BOP section 5 [read]; prior review section 8.
    - Implement: a "Blind spots" section in the w3/w4 READMEs.
    - Verify: `grep -c "Blind spots"` returns 1 in each README.
19. **Native cross-check of direction only, with Kanev's counter hygiene.**
    - Source: Kanev [read]; Nowatzki pitfall 2a [read].
    - Implement: one `perf stat` group without multiplexing, validated on a microbenchmark,
      comparing back-to-back vs thrashed `python -c pass` for L2 misses.
    - Verify: the perf output shows no multiplexing percentage; the README gives the command.
20. **Hold out by task for anything learned** (predictor rules, `stream:<d>` choice, list
    caps).
    - Source: PLAN.md. No paper above does this for invocation-level prefetch; it is our own
      rule.
    - Implement: leave-one-task-out in W2; the d sweep is reported in full rather than
      tuned.
    - Verify: code review of W2's split; the README lists which tasks trained each
      parameter.
21. **Name the benchmark and configuration in every caption.**
    - Source: Kanev representativeness [read]; `FIGURE_CONVENTIONS.md`.
    - Implement: every `fig_*.txt` names the task, the Python version and the Scarab config.
    - Verify: `grep -L django fig_*.txt` returns nothing.

---------------------------------------------------------------------------------------------
## 7. Items not verified
---------------------------------------------------------------------------------------------

- **Scarab counters and spf.** Whether Scarab's `L1_PREF_LATE`, `MLC_PREF_LATE`,
  `PREF_UNUSED_EVICT` and `L1_LATE_PREF_CYCLES*` count requests injected by a new prefetcher
  (spf) or only the built-in ones. I read only the stat names in
  `src/prefetcher/pref.stat.def`, not their update sites.
- **FDP throttling and spf.** Whether `pref_throttlefb_on` would see spf requests. It depends
  on how W4 injects them.
- **Wrong-path accesses in coverage.** Whether Scarab's trace frontend fetches wrong-path
  instructions that touch the caches, which affects PIF-style correct-path coverage
  accounting.
- **SMARTS.** The ±3%/99.7% figure is from the abstract. I did not re-derive the paper's W
  bound for our core.
- **Kanev.** Read partially (sections 1-4 and methodology). The leaf-function "tax" section
  is summarised from the prior review, where it was read.
- **Page ranges and volumes** for PIF (pp. 152-162), SMS (pp. 252-263), Bingo (pp. 399-411) and Nowatzki (vol. 35, pp. 4-12) come from search-engine/dblp/ACM listings, not from the PDFs.
- **Nowatzki.** The Wisconsin-hosted PDF was read. I assumed it is the published IEEE Micro
  version (same pages 4-12 and figures). I did not compare it against IEEE Xplore.
- **Bingo.** The "Accurately and Maximally Prefetching Spatial Data Access Patterns with
  Bingo" journal/extended version appeared in search results. I did not open it; only the
  HPCA 2019 paper was read.
- **The `bulk` timing mode** in section 2.1 is a recommendation. It is not in PLAN.md, and
  nobody has decided to adopt it.
- **The first-order model (item 17)** is my proposal, derived from Nowatzki's general advice.
  No paper above gives this exact formula.

## Source URLs (fetched 2026-09-26)

- SMARTS: https://infoscience.epfl.ch/server/api/core/bitstreams/88f7afe8-38b8-41c6-b60b-6415544b0c22/content
- SimPoint: https://cseweb.ucsd.edu/~calder/papers/ASPLOS-02-SimPoint.pdf (doi:10.1145/605397.605403)
- Jukebox: https://ease-lab.github.io/ease_website/pubs/JUKEBOX_ISCA22.pdf
- Ignite: https://ease-lab.github.io/ease_website/pubs/IGNITE_MICRO23.pdf
- TIFS: https://compas.cs.stonybrook.edu/~mferdman/downloads.php/MICRO08_Temporal_Instruction_Fetch_Streaming.pdf
- PIF: https://infoscience.epfl.ch/server/api/core/bitstreams/39bb1aa6-41f3-4773-9954-bad24882d9cf/content (MICRO-44, 2011, pp. 152-162)
- SMS: https://users.ece.cmu.edu/~ssomogyi/publ/isca2006.pdf (ISCA 2006, pp. 252-263)
- BOP paper: https://safari.ethz.ch/architecture/fall2020/lib/exe/fetch.php?media=07446087.pdf (slides: https://www.irisa.fr/alf/downloads/michaud/BOP_HPCA_2016.pdf)
- Bingo: https://cs.ipm.ac.ir/~plotfi/papers/bingo_hpca19.pdf (HPCA 2019, pp. 399-411, doi:10.1109/HPCA.2019.00053)
- FDP: http://hps.ece.utexas.edu/pub/srinath_hpca07.pdf (doi:10.1109/HPCA.2007.346185)
- Nowatzki: https://pages.cs.wisc.edu/~karu/courses/cs752/fall2016/pdfs/sim-harmful.pdf
- Kanev: https://gwern.net/doc/cs/hardware/2015-kanev.pdf
