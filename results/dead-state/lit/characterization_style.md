# Characterization style: Seshadri, Basu, and the Mutlu group

Notes for writing the characterization section of the dead-state paper. These cover how the papers
below build a characterization, and how Vivek Seshadri writes one.

**Rule zero.** Every claim about a paper comes from its PDF, which I read in full text on 2026-10-09
(sources at the end). Text in quotation marks is copied verbatim. The only edits are restored
ligatures: PDF extraction drops "fi", "ff" and "ffi", so "Vlter" became "filter" and "eUective" became
"effective". Section and figure numbers are the paper's own. When I paraphrase, I say so. When I did
not check something, I say that too.

**Attribution corrections.**
- *Redundant Memory Mappings* (ISCA'15) is by Karakostas, Gandhi, Ayar, Cristal, Hill, McKinley,
  Nemirovsky, Swift and Ünsal. **Basu is not an author.** It is the follow-on to Direct Segments from
  the Wisconsin group, so it is included below, marked as non-Basu.
- *Observations and Opportunities in Architecting Shared Virtual Memory* (ISPASS'16) is Vesely, Basu,
  Oskin, Loh and Bhattacharjee, written at AMD Research and Rutgers, not IISc.
- I found no Basu paper titled "Trans-FW" or "Characterizing ... GPU unified memory" on his IISc
  publication page. The characterization-heavy IISc papers used instead are: Dead Page/Dead Block
  Predictors (HPCA'21), Neighborhood-aware translation (MICRO'18), Trident (MICRO'21), MGvm (MICRO'22)
  and ObservUVM (ISCA'26).
- For "Understanding and Improving the Latency of DRAM" I used the characterization paper from that
  line of work: Lee et al., *Understanding and Exploiting Design-Induced Latency Variation in Modern
  DRAM Chips* (SIGMETRICS'17; Seshadri is a co-author). I did not read any Mowry prefetching paper.

---

## 1. Per-paper analysis

### 1.1 Vivek Seshadri

Seshadri's papers are mechanism papers. The characterization is short, but it carries the paper:
usually one figure or table, one property, and one sentence of intuition. The depth comes from three
things:
- he names the inefficiency precisely;
- he states the *ideal* explicitly;
- he picks a metric that measures exactly the waste he wants to remove.

#### The Evicted-Address Filter (PACT'12) — Seshadri, Mutlu, Kozuch, Mowry

- **Fundamental property.** Reuse behaviour is visible right after eviction. In the paper's words:
  "Observation: If a cache block with high reuse is prematurely evicted from the cache, then it will
  likely be accessed soon after eviction. On the other hand, a cache block with little or no reuse
  will likely not be accessed for a long time after eviction." (§2.1, set off as a highlighted box)
- **Framing.**
  - §1 opens from the ideal: "Ideally, to ensure high performance, the cache should be filled only
    with blocks that have high temporal reuse".
  - It then names two departures from that ideal and defines each once: "This problem is referred to
    as cache pollution" and "This problem is referred to as cache thrashing."
  - Prior work is classified by the *granularity* at which it predicts reuse. PC-based or
    region-based predictors "do not distinguish between the reuse behavior of blocks within a group".
  - The paper then argues that this granularity is the reason prior work cannot handle both problems
    at once ("The Problem:", §1).
- **Characterization steps.** This is a reasoning-first paper, not a measurement-first one. §2.2,
  "The Problem with Large Working Sets", works through two cases analytically:
  - Case 1: the working set is larger than cache + EAF.
  - Case 2: the working set is larger than the cache but smaller than cache + EAF.
  - It derives what goes wrong in each case before any data is shown.
- **Ideal / opportunity.**
  - The EAF is sized so the boundary between high and low reuse matches the cache: "we set the size
    of the EAF to be the same as the number of blocks in the cache" (§2.1).
  - Sensitivity to that choice is deferred to §7.4 ("Section 7.4 analyzes the effect of varying the
    size of the EAF").
- **Sensitivity.** The paper compares against five mechanisms and two replacement policies, and
  concludes the benefit is "orthogonal to the benefits of using an improved cache replacement policy".
- **Takeaway for us.** Turn a lifetime property into a one-line observation. Box it. Then explain why
  it holds.

#### Mitigating Prefetcher-Caused Pollution, "ICP" (TACO'15) — Seshadri et al.

This is the Seshadri paper closest to dead blocks. Its Figure 1 is a dead-block characterization.

- **Fundamental property.** "We first observe that a significant majority of accurate prefetches are
  used only once by the application." (§1)
- **Scope condition, stated up front.** "This observation is valid only for secondary caches (L2, L3,
  etc.) and not for the primary L1 caches, in which multiple demand requests may access different
  words within a prefetched block." (§1)
- **Root cause, one sentence.** "The main intuition behind why the majority of the accurate
  prefetched blocks are used only once is that prefetching typically works well for large data
  structures that do not fit into the cache. Blocks of such data structures have a large reuse
  distance, and thus are unlikely to get used more than once while in the cache." (§1)
- **Measurement.**
  - One study: a 1 MB L3 with a stream prefetcher.
  - Fig. 1, "Usage distribution of prefetched blocks", is a per-benchmark stacked bar with three
    states: unused, used once, used more than once.
  - Result: "over 95% of the accurate prefetches are used only once."
- **Guarding the claim.** Footnote 1: "The aim of this study is not to show that prefetched blocks
  are less likely to be reused than demand-fetched blocks. Rather, it is to show that prefetched
  blocks are less likely to be used more than once."
- **Ideal-policy figure.** Fig. 2 is a schematic of cache occupancy over time for each insertion or
  promotion policy. "There are three points to note regarding the figure."
- **Metric that measures the waste directly (§6.1).** The prefetch lifetime:
  - Definition: "The prefetch lifetime metric is a measure of the time a prefetched block stays in
    the cache unnecessarily. There are two phases when a prefetched block stays in the cache
    unnecessarily: (1) before its first use, and (2) after its last use."
  - Time is measured "in terms of the number of misses to the corresponding cache set" (a logical
    clock, not cycles).
  - It has an analytic ideal: "the ideal average prefetch lifetime is 1", and with all accurate
    prefetches used immediately it equals the associativity (16).
  - Result reported against that ideal: "from 13.81 to 2.16 (ideal = 1)" (§6.2).
- **Metric is not cost, said explicitly.** "Not all applications are sensitive to cache space.
  Therefore, even if the prefetches of an application cause high pollution, it may not affect the
  application's performance" (§6). Benchmarks in Figs. 4–5 are "sorted based on the increasing order
  of fraction of inaccurate prefetches". Cache-insensitive applications are excluded (footnote 7).
- **Sensitivity.** "varying cache sizes, memory latency, core counts, and cache replacement policies"
  (§1 contributions); 157 two-core workloads.
- **Takeaway for us.** Our dead time before first use and dead time after last use correspond to ICP's
  two phases. Give the metric an analytic ideal. State that dead capacity is not the same as lost
  performance.

#### RowClone (MICRO'13) — Seshadri et al.

- **Fundamental inefficiency.** "Clearly, all these problems result from the fact that existing
  systems must necessarily transfer a large quantity of data over the memory channel although neither
  copy nor initialization of bulk data requires any computation." (§1). The data movement is
  unnecessary *by construction*.
- **Quantification.**
  - Three numbered reasons, each with a number: "a typical system today (using DDR3-1066) takes
    roughly a microsecond (1046ns) to copy 4KB of data over the memory channel"; the channel transfer
    is "40% for DDR3-1066" of the energy (§1).
  - Workload prevalence: Fig. 10 shows the "Fraction of memory traffic due to read, write, copy and
    initialization operations" for six system-level workloads (bootup, compile, forkbench, mcached,
    mysql, shell). "between 10% and 80% of the memory traffic is generated by copy and initialization
    operations" (§7.3).
- **Why prior work does not fix it.** "none of these techniques eliminate the need to transfer data
  over the memory channel, and hence, all of them suffer from the three problems mentioned above."
- **Drilling when the data disagrees.** RowClone-based zeroing slightly hurt three applications. The
  paper explains this with a phase-level account: "although the operating system zeroes out any newly
  allocated page, the application typically accesses almost all cache lines of a page immediately
  after the page is zeroed out. There are two phases" (§7.3).
- **Workload choice.** SPEC is named as unrepresentative ("Applications from standard benchmark
  suites like SPEC CPU2006 do not trigger many bulk copy or initialization operations"). The
  workloads that exercise the property are chosen deliberately (§1).
- **Sensitivity.** Fig. 7 and Fig. 13 vary the forkbench parameters and the copy/initialization
  intensity.

#### Page Overlays (ISCA'15) — Seshadri et al.

- **Fundamental inefficiency.** The mismatch between tracking granularity and use granularity: "even
  if only a single cache line is modified within the virtual page, the system needs to create a full
  copy of the entire physical page, leading to inefficient use of memory capacity." (§2.2)
- **Prior work classified by cost type.** "Prior works to address this problem either rely on
  software techniques [23] (high performance overhead), propose hardware support specific to a
  particular application [35, 45, 60] (low value for cost), or significantly modify the structure of
  existing virtual memory [11, 59] (high cost for adoption)." (§1)
- **Characterization by workload type.** For the fork study (§5.1, Figs. 8–9):
  - Benchmarks are grouped by write-working-set shape: Type 1 low write working set; Type 2 "almost
    all cache lines within each modified page are updated"; Type 3 "only a few cache line within each
    modified page are updated". Five benchmarks of each type.
  - Then: "We draw three conclusions."
  - The explanation for Type 2 goes one level deeper, to time: "the performance trends can be
    explained by the distance in time when cache lines of each page are updated by the application."
- **Takeaway for us.** Group workloads by the *mechanism-relevant property* (here, the spatial shape
  of writes within a page), not by suite. Explain residual differences with a second variable
  (temporal spread).

#### Gather-Scatter DRAM (MICRO'15) — Seshadri et al.

- **Fundamental inefficiency.** Spatial underutilization: "the cache line size (typically 64 bytes)
  is usually much larger than the size of the individual data item involved in a strided access
  (typically 4 or 8 bytes)." (§1)
- **One worked example in place of a survey.**
  - Figure 1 (a 4-field tuple table) shows both costs: "First, each cache line contains only one
    useful piece of data (shaded boxes in the figure). As a result, the processor must fetch four
    times more cache lines than necessary".
  - The second cost: "each cache line access also brings along the remaining fields of the table into
    the cache".
- **Why it is unavoidable today.** HTAP runs both access patterns on the same table, so "existing
  systems cannot avoid strided accesses." (§1)
- **Ideal.** The claim is "near-ideal memory bandwidth and cache utilization" (abstract). The thesis
  version (§2.2) adds the ideal explicitly (see 1.1.6).

#### Ambit (MICRO'17) and the PhD thesis (CMU-CS-16-106)

- **Ambit.** Real-system measurement establishes the bound before the mechanism: "our experiments on
  a multi-core Intel Skylake [7] and an NVIDIA GeForce GTX 745 [4] show that the available memory
  bandwidth of these systems limits the throughput of bulk bitwise operations." (§1)
- **Thesis, Ch. 1–2. The best single model of "fundamental inefficiency" framing.**
  - Names the phenomenon: "In this thesis, we observe that this curse of multiple granularities
    results in significant inefficiency in the memory subsystem." (Abstract)
  - Draws the whole system stack with the granularity at each layer: Fig. 1.1, word / cache line /
    page / row.
  - Ch. 2 dissects one example per class into enumerated "Sources of Inefficiency" (§2.1.2: First
    redundancy, Second latency and CPU use, Third bandwidth and pollution, Finally energy). Each ends
    with an "Ideally" paragraph: "Ideally, instead of copying an entire page of data, the system
    should eliminate all the redundancy by remapping only the data that is actually modified."
  - The goal includes a do-no-harm clause: "without significantly modifying existing abstractions and
    without degrading the performance/efficiency of applications that do not use our proposed
    techniques." (§1.3)
  - The approach is framed as latent capability: "our approach is to exploit the untapped potential
    in various hardware structures" (§2.3).

#### Dirty-Block Index (ISCA'14) — Seshadri et al.

- **Property.** This is an *organizational* inefficiency, not a workload one: "We find that this
  approach is inefficient and inhibits several cache optimizations." (Abstract)
- **Motivation.** Two "key principles" drawn from two prior optimizations (§2).
- **Depth.** DBI is shown to enable three optimizations at once. *Generality* serves as evidence that
  the problem is fundamental.

### 1.2 Arkaprava Basu

Basu's characterizations are measurement-first and organized around a *question about the workload*.
Each finding ends in a boxed or numbered statement that names an opportunity. Three moves recur:
1. state a hypothesis, then measure it on real hardware with a stock tool;
2. separate static prevalence from dynamic frequency;
3. use a controlled intervention (page size, input sorting, microbenchmark) to isolate one cause.

#### Efficient Virtual Memory for Big Memory Servers / Direct Segments (ISCA'13) — Basu, Gandhi, Chang, Hill, Swift

- **Fundamental property.** A workload *usage* property, set against a mechanism's generality:
  "These workloads typically allocate most of the memory at startup in large chunks with uniform
  access permission." (§1)
- **Structure (§2).** "Our study includes the following three aspects":
  - (1) Use of virtual memory: which features are actually used.
  - (2) Cost of virtual memory: TLB-miss overhead.
  - (3) Execution environment.
- **Steps.**
  - *Hypothesis, then measurement.* "We hypothesize that big-memory workloads do little or no
    swapping ... We examine this hypothesis by measuring the amount of swapping in these workloads
    with the vmstat Linux utility. As expected, we observe no swapping activity" (§2.1).
  - *Time series.* Fig. 1, "Memory allocated over time by workloads", samples pmap every 5 s for
    25 minutes. Result: "most memory is allocated early in the execution and very little variation in
    allocation thereafter."
  - *Fraction table.* Table 3 gives the % of allocated memory with read-write permission (99.38–99.98%).
  - *Cost on real hardware.* Hardware counters for page-walker cycles; Table 4 gives the % of cycles
    on D-TLB and I-TLB misses at 4 KB, 2 MB and 1 GB pages. The paper flags its estimate as
    conservative: "Our estimate for TLB-miss latency is conservative as we do not account for L1 TLB
    misses that hit in L2 TLB".
  - *Anomaly explained.* NPB:CG gets *worse* with 1 GB pages. The paper traces this to a "3X increase
    in TLB miss rate likely due to the smaller number of TLB entries available for 1GB pages (4
    entries)".
- **Observation boxes.** Each one is a single claim:
  - Observation 1: "For the majority of their address space, big-memory workloads do not require,
    swapping, fragmentation mitigation, or fine-grained protection ... They allocate memory early and
    have stable memory usage."
  - Observation 2: "Big-memory workloads pay a cost of page-based virtual memory".
  - Observation 3: lists the a/b/c execution properties.
- **Out-of-scope costs, named.** "there are several other costs that are beyond the scope of this
  analysis: the dynamic energy cost of L1 TLB hit, the energy cost of page table walk on TLB miss,
  and the memory and cache space for page tables."
- **Opportunity.** §3 opens with "Inspired by the observations in Section 2". The mechanism maps
  exactly the region that Observation 1 shows does not need paging.
- **Takeaway for us.** This is our template for start-up-allocated, never-used memory. Measure use
  (what fraction is ever touched), cost (what it costs us), and environment (process lifetime,
  repetition). Box each observation.

#### Opportunistic Virtual Caching (ISCA'12) — Basu, Hill, Swift

- **Property.** The hard case is rare in practice: "We find, though, that many of these problems
  occur rarely in practice." (§1)
- **Static vs dynamic, side by side.** Table 4 reports three numbers per workload:
  - % of pages with synonyms (static);
  - % of synonym pages that are read-only (whether it can be harmful);
  - % of dynamic accesses to synonym pages (how often it matters).
- **Tools.** Kernel page-table analysis for static counts, PIN for dynamic references (§3).
- **Root cause in one clause.** "This occurs because these pages were often from immutable shared
  library code (95-100% of the synonym pages)."
- **Comparing against a physical time scale.** "even the smallest inter-arrival time between
  invalidations (2.325ms for memcached) is an order of magnitudes longer than the typical time to
  flush and refill a L1 cache (~ 5µs)." (§3.2)
- **"Finding N" boxes.**
  - "Finding 1: While synonyms are present in most applications, conflicting use of them is rare."
  - "Finding 2: TLB invalidations that occur due to page mapping or protection changes are infrequent
    and are thus unlikely to create much overhead."
- **From "rare" to a design.** "Unfortunately, correctness and backward compatibility must be
  absolute and not 'almost always'." (§4). Characterization shows where the fast path is safe. The
  mechanism keeps a fallback.

#### Observations and Opportunities in Shared Virtual Memory (ISPASS'16) — Vesely, Basu, Oskin, Loh, Bhattacharjee

- **Format.** A pure characterization paper. Each section ends with "Observations and
  opportunities:" as a numbered list. §VIII is "Summary: Observations and Opportunities".
- **Microbenchmarks to expose hidden hardware parameters.** Sweeping the number of workitems from 1
  to 64: "there is a significant jump in the page walk latency beyond 16 workitems ... This suggests
  that in our test hardware, the IOMMU allows up to 16 concurrent page table walks" (§IV-A).
- **Scaling sweep.** Each application is run with increasing memory footprint (e.g., BPT from 2 to
  21 GB), with misses reported per kilo wavefront instructions at 4 KB vs 2 MB pages (Fig. 3).
- **Sensitivity sorts workloads.** Graph500 loses almost all TLB misses with 2 MB pages "but there
  is no observable change in execution time". The root cause found: it "loads data from the memory
  to the GPU's scratchpad ... in contiguous chunks, and thus amortizes TLB misses well" (§IV-B).
- **Causal intervention to separate one level of the hierarchy from the rest (§IV-C).**
  - Unsorted versions of XSBench and BPT are run against the original sorted-key versions.
  - 1 GB pages then remove translation cost, leaving the residual slowdown attributable to caches and
    DRAM.
  - "This strongly indicates that poor locality affects the GPU's address translation far more than
    the rest of the memory hierarchy."
- **Opportunity as the gap between two curves.** Fig. 8 plots physical memory over time with and
  without GPU page faults. "The difference between these two lines signifies opportunity to save
  physical memory." The paper also explains when the gap closes: XSBench eventually touches the whole
  energy grid.

#### Dead Page and Dead Block Predictors (HPCA'21) — Mazumdar, Mitra, Basu (IISc)

This is the closest prior characterization to our dead cache blocks.

- **Definition.** "A dead block is an entry in a cache that will not experience further hits until
  its eviction. The entry is dead because it serves no purpose while occupying space in the cache."
  (§I)
- **Two complementary views (§IV-A).**
  - *Snapshot view:* Fig. 1, "Fraction of LLT entries dead or DOA at any time", is "estimate[d] ...
    by sampling entries over time". Result: 81.66% dead.
  - *At-eviction classification:* Fig. 2. "We classify entries at the time of their eviction from
    LLT, unlike the sampling of entries in Figure 1."
  - Three classes: "dead-on-arrival (DOA), mostly dead (dead time > live time) but experienced at
    least one TLB hit, and active/mostly live (dead time < live time)."
- **Two observations that steer the design.** "(1) There are many dead entries in the LLT that can be
  leveraged to improve TLB performance. (2) DOAs dominates among the dead entries, and thus, any
  technique to leverage dead pages in LLT should focus on DOA pages."
- **Cross-structure correlation as opportunity (§IV-B).** "To quantify the opportunity for such an
  optimization, we measure the likelihood of a DOA block in LLC being part of a DOA page in the LLT."
  Table III: 72.7% of DOA blocks fall on DOA pages.
- **Root cause (§IV-C, "Discussion").**
  - "the LLTs/LLCs observe the access streams filtered by the upper levels ... If the reuse distance
    of an entry, after its immediate reuse, is large enough, then LLTs/LLCs will fail to register any
    hit".
  - The LLT/LLC difference is then explained by residency: an LLT entry's "average stay ... is 4×-5×
    shorter than an LLC entry."
- **Anticipating the reader.** "A curious reader could ask if the dead block predictors designed for
  LLC could work well for LLT too?"
- **Takeaway for us.** Report dead state both as a snapshot (capacity-time) and at eviction (per-entry
  class). Split dead into DOA vs mostly-dead. Explain the level-to-level differences with access-stream
  filtering and residency time. Look for correlation across granularities (block vs page,
  page vs file, object vs import).

#### Neighborhood-aware Address Translation (MICRO'18) — Shin, LeBeane, Solihin, Basu

- **Ideal bound first.** Fig. 3, "Speed up possible with ideal address translation". "A system with
  an ideal address translation mechanism is an unrealistic system where all translation happens in a
  single cycle. Thus, the height of each bar in the figure shows performance lost due to address
  translation overheads." (§II-C)
- **Spatial-underutilization property from a hardware fact.** Eight 8-byte PTEs share a 64-byte line
  and the walker fetches the whole line, "However, only the desired PTE is typically used ... and the
  rest of the cache line is discarded." (§III)
- **Opportunity measured.** Figs. 5–6 give the fraction of concurrent walks that fall in the same
  neighborhood (≈0.4 at the leaf level, 0.7 at the upper levels). The outlier is explained: MVT "has
  a nearly random memory access pattern".
- **Software root cause.** "CUs concurrently execute independent work-groups, but they often run
  similar regions of code during the same period of execution."
- **Numbered "Summary:"** closes §III with four items. Sensitivity (§V-C): number of walkers, IOMMU
  buffer size.

#### Trident (MICRO'21) — Ram, Panwar, Basu (IISc)

- **Framing from wasted hardware.** "One pays for the underutilized hardware through both – the
  runtime cost (e.g., power dissipation), and the design and verification cost." (§1)
- **Metric vs performance.** "Reduction in page walk cycles does not always lead to proportional
  performance gain on out-of-order cores. Rather, the speed up depends upon what portions of walk
  cycles are on the critical path of execution." (§4.1). Fig. 1a shows walk cycles and Fig. 1b shows
  performance for the same configurations.
- **Mappability over time.** Fig. 3 uses a kernel module that periodically scans the address space.
  Fig. 4 gives TLB-miss frequency per region class.

#### ObservUVM (ISCA'26) and MGvm (MICRO'22) — Basu's group (IISc)

- **ObservUVM §III, "Current Shortcomings and Key Insights".**
  - A toy matrix-multiply diagram (Fig. 2) shows why LRM evicts live regions.
  - The waste of a conservative policy is quantified by occupancy *at eviction*: "on average, a 2MB
    region is over 90% occupied at eviction".
  - The hidden hardware limit is reverse-engineered with a microbenchmark: notifications rise linearly
    and then saturate at 256 (Fig. 3).
  - The section closes with a "Summary of Key Insights" box (four items).
- **MGvm §III.**
  - Fig. 4 decomposes total L1-TLB-miss cycles into four named components (local hit, remote hit,
    local walk, remote walk). This is a cost breakdown that points straight at the remote components.
  - "Sensitivity studies and generality" (§VI-C).

#### Redundant Memory Mappings (ISCA'15) — Karakostas et al. (not Basu; Wisconsin follow-on)

- **Coverage/concentration statistic.** Table 2 reports the number of ranges needed "to map 99% of
  the application's memory" and the "percentage of application memory mapped by the single largest
  range". "The workloads require between 16 to 112 ranges to map their entire virtual address space.
  However, the number of ranges to cover 99% ... falls to fewer than 50." (§3)
- **Takeaway for us.** "How many files/modules/objects cover 90%/99% of dead bytes" is the same
  statistic, and it directly sizes any mechanism.

### 1.3 Mutlu group exemplars

#### Google Workloads for Consumer Devices (ASPLOS'18) — Boroumand et al.

- **Property.** "data movement between the main memory system and computation units ... is a major
  contributor to the total system energy." (§1)
- **Root-cause drilling, in the order the paper does it (§4):**
  1. *User interaction.* Page scrolling and tab switching, chosen because they govern perceived
     speed.
  2. *Function share.* Fig. 1 is the energy breakdown for scrolling across six pages. Two functions
     (texture tiling, color blitting) take 41.9%, and everything else is "Other" (each < 1%).
  3. *Hardware component split.* Fig. 2 splits energy into CPU, L1, LLC, interconnect, memory
     controller and DRAM. "77% of the total energy consumption is due to data movement."
  4. *Cross-check with a second counter.* "We confirm this by measuring the MPKI issued by the
     last-level cache (LLC)" (21.4 on average).
  5. *Data-structure root cause.* Texture tiling's data movement comes from "(1) the poor data
     locality during texture tiling; and (2) the large rasterized bitmap size (e.g., 1024x1024 pixels,
     which is 4 MB), which typically exceeds the LLC capacity."
  6. *Primitive composition.* "texture tiling requires only simple primitives: memcopy, bitwise
     operations, and simple arithmetic operations".
  7. *Close each step.* "We conclude that texture tiling and color blitting are responsible for a
     significant portion of the data movement that takes place during web page scrolling."
- **Explicit selection criteria (§3.2).** A function is a target only if it meets all four:
  1. it is the top energy consumer;
  2. data movement is a significant share of total energy;
  3. MPKI > 10;
  4. data movement is the largest component of its own energy.
- **Alternatives dismissed with data.** GPU rasterization raises page load time "by up to 24.9%" on
  text-heavy pages.
- **Methodology honesty.** Wi-Fi off and lowest brightness "to ensure that the majority of the total
  energy is spent on the SoC and the memory system"; conservative PIM energy assumptions.

#### Design-Induced Latency Variation in DRAM (SIGMETRICS'17) — Lee, Khan, Subramanian, Ghose, Ausavarungnirun, Pekhimenko, Seshadri, Mutlu

- **Hypothesis from the physical design before any data (§3).** The variation is predicted from RC
  distance to the peripheral logic. Its four distinguishing properties ("Predetermined at design
  time", "Static distribution", "Constant", "Similarity in DRAMs with the same design") separate it
  from process and temperature variation.
- **Three research questions organize the section:** organization, interface, operating conditions.
- **A test pattern designed to reveal the structure.** Errors are aggregated by row address modulo
  512 "because each bitline is connected to 512 cells. Hence, our expectation is that the
  design-induced variation pattern will repeat every 512 cells." The rows are then sorted and
  reordered to make the periodicity visible (Figs. 6–7).
- **Choosing the operating point that exposes the effect.** Variation is visible only at
  tRP = 7.5 ns. At 10 ns errors are random; at 5 ns everything fails.
- **Scale and honest negatives (§5.6).** 96 DIMMs / 768 chips. "we did not observe design-induced
  variation in 24 DIMMs. However, we believe that this is in part due to a limitation of our
  infrastructure" (2.5 ns step size).
- **Independent validation.** SPICE circuit simulation in Appendix B "validate[s] our hypotheses".
- **"We make two/three observations"** appears in nearly every subsection, each closed by "We
  conclude that".

---

## 2. A recipe for a deep characterization section (12 rules)

1. **Open from the ideal, not the baseline.** State what a perfect system would hold or move, then
   measure the distance from it.
   - EAF §1: "Ideally, ... the cache should be filled only with blocks that have high temporal reuse".
   - Thesis §2.1.2 ends each inefficiency with an "Ideally" paragraph.
   - *For us:* "Ideally, a cache (memory) holds only state that will be referenced again before it
     is evicted (freed)."

2. **Name the phenomenon once and define it operationally.**
   - "This problem is referred to as cache pollution" (EAF).
   - "A dead block is an entry in a cache that will not experience further hits until its eviction"
     (Basu HPCA'21).
   - "curse of multiple granularities" (thesis).
   - *For us:* define dead state, dead time, DOA, and mostly-dead once, with the clock (cycles,
     accesses, or set misses as in ICP §6.1).

3. **Ask a question about the workload, not the hardware, and split it into named aspects.**
   - Direct Segments §2 has three aspects (use, cost, environment).
   - Lee §3 has three research questions (organization, interface, operating conditions).
   - Boroumand §4 goes interaction → function → component.

4. **Hypothesize, then measure with the simplest tool that can falsify it.**
   - Direct Segments: "We hypothesize ... We examine this hypothesis by measuring ... with the vmstat
     Linux utility."
   - Lee: predict the 512-row period from the bitline design, then test for it.

5. **Report every quantity in two views: snapshot (prevalence) and per-object at end of life
   (classification).**
   - Basu HPCA'21: Fig. 1 (sampled at any time) vs Fig. 2 (classified at eviction into DOA, mostly
     dead, live).
   - OVC Table 4: % of pages (static) vs % of dynamic accesses.

6. **Measure the waste with a metric whose ideal is known analytically.**
   - ICP prefetch lifetime: two phases, before first use and after last use; ideal = 1; reported
     "13.81 to 2.16 (ideal = 1)".
   - Neighborhood: ideal translation is one cycle, so bar height is the lost performance.

7. **Drill every headline number down at least three levels:** behaviour/phase → software
   (function, module, data structure) → hardware structure → cost.
   - Boroumand: scrolling → texture tiling → bitmap (4 MB) > LLC → DRAM/interconnect energy → 77%
     data-movement energy.
   - Basu HPCA'21: LLC/LLT DOA → filtered access stream + residency 4–5× shorter.

8. **Explain every outlier and every anomaly. A leftover anomaly is a hole in the story.**
   - Direct Segments: NPB:CG worse at 1 GB pages, explained by 4 vs 32 entries.
   - ISPASS'16: graph500 insensitive because of its LDS chunking.
   - RowClone: zeroing hurts because pages are touched right after zeroing.
   - Neighborhood: MVT's random access.

9. **Use controlled interventions to isolate causes.**
   - ISPASS'16: sorted vs unsorted keys, then 1 GB pages to remove translation, leaving the residual
     for caches and DRAM.
   - ObservUVM: microbenchmark that reveals 256 counters.
   - *For us:* the same agent with imports pre-warmed vs cold, a forked zygote vs fresh exec, or the
     LLM stubbed with replayed responses.

10. **Separate the metric from the cost, and say so in a sentence.**
    - ICP: "even if the prefetches of an application cause high pollution, it may not affect the
      application's performance".
    - Trident: walk-cycle reduction "does not always lead to proportional performance gain".
    - *For us:* dead capacity-time is not equal to lost IPC. Show both, and show sensitivity (e.g.,
      the cache-size sweep).

11. **Quantify concentration and correlation, because they size the opportunity.**
    - RMM: "number of ranges to cover 99%".
    - Basu HPCA'21: 72.7% of DOA blocks lie on DOA pages.
    - Boroumand: two functions = 41.9%, everything else < 1% each.
    - *For us:* how many modules or files cover 90% of dead bytes; how much dead-block mass falls on
      dead pages or dead files.

12. **End each subsection with a boxed one-sentence observation, and the section with a numbered
    summary that maps each observation to an opportunity.**
    - Direct Segments "Observation 1–3".
    - OVC "Finding 1–2".
    - ISPASS'16 "Observations and opportunities:".
    - ObservUVM "Summary of Key Insights".
    - Neighborhood "Summary: (1)…(4)".

Corollaries used throughout these papers:
- Pick workloads that exercise the property and say why the standard suite does not (RowClone on
  SPEC).
- Group workloads by the mechanism-relevant property (Page Overlays Types 1/2/3).
- Name what you did not measure (Direct Segments' out-of-scope costs).
- Report negative results and tool limits (Lee: 24 DIMMs showed nothing, 2.5 ns steps).
- Validate with a second, independent method (Boroumand: LLC MPKI; Lee: SPICE).

---

## 3. Seshadri writing style: 15 habits

All quotations are verbatim (ligatures restored).

1. **One goal sentence that starts "Our goal is".** It lists what must be reduced and the
   constraints.
   - "Our goal is to design a mechanism that reduces the latency, bandwidth, and energy consumed by
     bulk data operations." (RowClone §1)
   - "Our goal is to design a mechanism that 1) improves the performance (cache hit rate and memory
     bandwidth consumption) of strided accesses, and 2) works with commodity DRAM modules and
     traditional non-sectored caches with very few changes." (GS-DRAM §1)

2. **"Ideally," states the target before the problem.**
   - "Ideally, to ensure high performance, the cache should be filled only with blocks that have high
     temporal reuse – blocks that are likely to be accessed multiple times within a short time
     interval." (EAF §1)
   - "Ideally, instead of copying an entire page of data, the system should eliminate all the
     redundancy by remapping only the data that is actually modified." (Thesis §2.1.2)

3. **Define a term in the sentence right after describing it, with the passive "is referred to as".**
   - "First, cache blocks with little or no reuse can evict blocks with high reuse from the cache.
     This problem is referred to as cache pollution." (EAF §1)

4. **Count, then enumerate: "due to three reasons. First, … Second, … Third, …".**
   - "Bulk data operations degrade both system performance and energy efficiency due to three
     reasons. First, existing systems perform such operations one byte/word/cache line at a time."
     (RowClone §1)

5. **Put a concrete number on the problem in the introduction.**
   - "For example, a typical system today (using DDR3-1066) takes roughly a microsecond (1046ns) to
     copy 4KB of data over the memory channel." (RowClone §1)

6. **A "Clearly," sentence that reduces all symptoms to one root cause.**
   - "Clearly, all these problems result from the fact that existing systems must necessarily
     transfer a large quantity of data over the memory channel although neither copy nor
     initialization of bulk data requires any computation." (RowClone §1)

7. **"Unfortunately," as the pivot from the reasonable approach to its flaw.**
   - "Unfortunately, the cache line size (typically 64 bytes) is usually much larger than the size of
     the individual data item involved in a strided access (typically 4 or 8 bytes)." (GS-DRAM §1)
   - "Unfortunately, keeping track of the behavior of all blocks in the system would incur large
     storage overhead and lookup latency." (EAF §1)

8. **Bold-run-in paragraph labels that make the argument skimmable.** "The Problem:", "Our
   Approach:", "Summary of Operation:" (EAF §1).

9. **The key observation is stated as a self-contained, boxed sentence pair: positive case, then
   negative case.**
   - "Observation: If a cache block with high reuse is prematurely evicted from the cache, then it
     will likely be accessed soon after eviction. On the other hand, a cache block with little or no
     reuse will likely not be accessed for a long time after eviction." (EAF §2.1)

10. **"Our key observation is that …" / "The key observation behind our approach is that …"**
    - "Our key observation is that DRAM can internally and efficiently transfer a large quantity of
      data (multiple KBs) between a row of DRAM cells and the associated row buffer." (RowClone
      abstract)
    - "The key idea behind ICP-AP is to detect cases when an accurate prefetch is misclassified as
      inaccurate" (ICP §2.2)

11. **Follow a measured observation immediately with its intuition.**
    - "The main intuition behind why the majority of the accurate prefetched blocks are used only
      once is that prefetching typically works well for large data structures that do not fit into
      the cache." (ICP §1)

12. **"We draw N conclusions." Then "First, …" with the figure in parentheses.**
    - "We draw three conclusions. First, benchmarks with low write working set (Type 1) consume very
      little additional memory after forking (Figure 8)." (Page Overlays §5.1)
    - "We draw three conclusions from Figures 4 and 5." (ICP §6.2)

13. **Close each result with "We conclude that …"** — a one-line verdict.
    - "We conclude that the benefits of EAF-cache are orthogonal to the benefits of using an improved
      cache replacement policy." (EAF §7.3)
    - "We conclude that GS-DRAM provides the best of both the row store and the column store layouts."
      (GS-DRAM §5.1)

14. **Frame the design space as a question, then answer "In response".**
    - "We ask the question, can we architect a generalized framework that can enable a wide variety
      of fine-grain management techniques, without significantly altering the existing virtual memory
      framework? In response, we present a new virtual memory (VM) framework" (Page Overlays §1)

15. **Fence the claim: say what the study does *not* show.**
    - "The aim of this study is not to show that prefetched blocks are less likely to be reused than
      demand-fetched blocks. Rather, it is to show that prefetched blocks are less likely to be used
      more than once." (ICP §1, footnote 1)
    - "This observation is valid only for secondary caches (L2, L3, etc.) and not for the primary L1
      caches" (ICP §1)

Sentence-level texture, from reading all seven papers (paraphrase, not quotation):
- Sentences are short, 15–25 words, with one claim each.
- Adjectives are rare; the numbers carry the emphasis.
- "We find" and "We observe" come before every empirical claim.
- Prior work is described by what it *cannot* do, never dismissed with an adjective.
- Every section opens with one sentence that says what the section does.
- Each paragraph's first sentence is its claim, and the rest is support.

---

## 4. Good problem vs incremental: a checklist distilled from Seshadri's framing

A problem is a good one (in the sense these papers argue for) if most of these hold. Each item
points to the framing it is distilled from.

- [ ] **The waste is unnecessary by construction**, not just large. The work done is not needed:
  RowClone, "neither copy nor initialization of bulk data requires any computation".
  *Dead state:* bytes and blocks held but never referenced again.
- [ ] **The root cause is structural**: an abstraction or granularity mismatch, not a tuning
  parameter. Thesis: "curse of multiple granularities"; DBI: a metadata *organization* that
  "inhibits several cache optimizations".
- [ ] **Existing solutions treat symptoms and leave the root cause in place.** RowClone: "none of
  these techniques eliminate the need to transfer data over the memory channel".
- [ ] **Prior work can be sorted by the *kind* of cost it pays.** Page Overlays: "high performance
  overhead" / "low value for cost" / "high cost for adoption". If prior work only differs in degree,
  the problem may be incremental.
- [ ] **The ideal can be stated in one sentence and its distance measured.** Thesis "Ideally…";
  ICP "ideal = 1".
- [ ] **One property explains two or more symptoms that were previously treated separately.**
  EAF unifies pollution and thrashing; DBI enables three optimizations with one structure.
- [ ] **There is untapped capability or information already in the system.** Thesis §2.3: "exploit
  the untapped potential in various hardware structures". RowClone: the row buffer; GS-DRAM: the
  multiple chips. *For us:* the agent's own phase knowledge, or the repetition of start-up.
- [ ] **The fix can preserve existing abstractions and do no harm to everyone else.** Thesis §1.3:
  "without significantly modifying existing abstractions and without degrading the
  performance/efficiency of applications that do not use our proposed techniques."
- [ ] **Generality: many uses fall out of one insight.** Page Overlays Table 1 lists seven
  techniques.
- [ ] **The property is predicted to persist or grow.** Direct Segments: "we expect even higher
  address translation overheads in future". ISPASS'16: the second-generation APU's translation share
  "doubled".

Red flags for an incremental problem (the opposite of the above, paraphrased):
- the gain only comes from a better predictor for a known quantity;
- there is no stated ideal;
- the inefficiency disappears with a larger structure (Direct Segments contrasts large pages, which
  "must grow with memory sizes", with a fixed-cost solution);
- the benefit is confined to one workload with no structural reason.

---

## 5. Suggested outline: "Dead State in Agentic Execution"

The story runs behaviour → software → microarchitecture → cost → opportunity. Every number is a
placeholder `[...]`. Fill each from our measured data, with the figure source named in a comment.

**§N. Dead State in Agentic Execution**

Opening paragraph (habits 1, 2, 3; rule 1):
- "Ideally, a cache holds only blocks that will be referenced again before eviction, and memory holds
  only pages that will be referenced again before they are freed."
- Define *dead state*, *dead time* (before first use / after last use, following ICP §6.1), *DOA*,
  and the clock.
- One sentence on the three questions: (1) how much state is dead, (2) where it comes from, (3) what
  it costs.

**N.1 Methodology (short; details in §Methodology)**
- Workloads: [N] agent harnesses × [M] tasks, chosen because [property] (RowClone-style
  justification of why the standard suites do not exercise this).
- Instruments: Scarab cache_lib dead-block patch (L1I/L1D/L2/LLC); idle-page tracking + perf for
  memory; py-spy / semantic phase labels for attribution.
- Clocks and windows: [sampling policy]. State what is not measured (Direct Segments-style
  out-of-scope list).

**N.2 How much state is dead? (prevalence: behaviour level)**
- Fig. A, snapshot view: dead fraction of capacity-time per structure (L1I, L1D, L2, LLC, resident
  memory), per agent. Show datacenter baselines measured the same way.
- Fig. B, end-of-life view: per-block/page class at eviction or free, DOA / mostly-dead / mostly-live
  (Basu HPCA'21 Figs. 1–2).
- Box, **Observation 1:** "[X–Y]% of [structure] capacity-time holds dead state; [Z]% of dead entries
  are DOA."
- Explain the level-to-level differences with access-stream filtering and residency (Basu HPCA'21
  §IV-C).

**N.3 When does state die? (phase level)**
- Fig. C, time series over one agent episode: live vs dead bytes, with agent phases annotated
  (start-up / think / act / tool-exec / idle). This is the Direct Segments Fig. 1 analogue.
- Dead-time split: before first use vs after last use (ICP's two phases).
- Box, **Observation 2:** "[Most] dead state is created in [phase] and stays dead for [the rest of
  the episode / until process exit]."
- Explain the anomaly: any phase or agent that breaks the pattern (rule 8).

**N.4 What software creates it? (code and data-structure level)**
- Fig. D, attribution of dead bytes/blocks to software origin (interpreter start-up, imports by
  module, harness, tool processes, LLM client). Concentration statistic: "[k] modules cover 90% of
  dead bytes" (RMM / Boroumand style).
- Table E: cross-granularity correlation. The fraction of dead blocks on dead pages, and of dead pages
  in dead files or modules (Basu HPCA'21 Table III).
- Root cause in one sentence per top contributor ("This occurs because …", OVC style).
- Box, **Observation 3:** "Dead state is concentrated: [k] [origins] account for [X]%; the cause is
  [eager import / start-up allocation / …]."

**N.5 Is it inherent? (controlled interventions)**
- Intervention 1: [warm vs cold start / zygote vs exec] → change in dead fraction.
- Intervention 2: [LLM replay or stubbed latency] → removes the think-time effect.
- Intervention 3: [cache size or associativity sweep] → does dead capacity shrink or persist? (EAF
  §7.4 / Lee operating-point style.)
- State which part of the residual each intervention removes (ISPASS'16 sorted/unsorted + 1 GB pages
  logic).
- Box, **Observation 4:** "[X]% of dead state persists across [interventions]; it is structural, not
  an artefact of [tool / size]."

**N.6 What does it cost? (microarchitecture → performance)**
- Ideal bound: performance with an oracle that never holds dead state (oracle replacement / perfect
  bypass), alongside a perfect cache. Bar height is lost performance (Neighborhood Fig. 3).
- Metric ≠ cost sentence (ICP §6 / Trident §4.1): "[Dead capacity] does not translate one-for-one
  into [IPC / energy]; only [structures / phases on the critical path] matter."
- Breakdown of the cost into named components (MGvm Fig. 4 style): [misses due to displaced live
  state], [writeback / fill traffic], [memory footprint × time].
- Box, **Observation 5:** "Eliminating dead state would yield at most [X]% [metric]; [structure]
  accounts for most of it."
- Report negatives honestly: e.g., where the oracle gain is ~0, say so and explain why (Lee §5.6
  style).

**N.7 Summary: observations and opportunities**
- Numbered list mapping each observation to an opportunity (ISPASS'16 §VIII / ObservUVM box). Each
  item has one sentence of fact and one of implication. No mechanism design.
- Closing "We conclude that …" sentence for the section.

Figure inventory implied by the outline:
- stacked-bar prevalence (A, B);
- annotated time series (C);
- ranked attribution with a cumulative-coverage line (D);
- correlation table (E);
- intervention deltas (paired bars);
- ideal-bound bars with a component breakdown.

Per memory/figure-style: direct labels, serif, legend inside, black outlines.

---

## Sources (local text extracts in the session scratchpad; PDFs fetched 2026-10-09)

| Paper | URL |
|---|---|
| EAF (PACT'12) | https://users.ece.cmu.edu/~omutlu/pub/eaf-cache_pact12.pdf |
| DBI (ISCA'14) | https://users.ece.cmu.edu/~omutlu/pub/dirty-block-index_isca14.pdf |
| RowClone (MICRO'13) | https://users.ece.cmu.edu/~omutlu/pub/rowclone_micro13.pdf |
| Page Overlays (ISCA'15) | https://users.ece.cmu.edu/~omutlu/pub/page-overlays-for-fine-grained-memory-management_isca15.pdf |
| GS-DRAM (MICRO'15) | https://people.inf.ethz.ch/omutlu/pub/GSDRAM-gather-scatter-dram_micro15.pdf |
| Ambit (MICRO'17) | https://people.inf.ethz.ch/omutlu/pub/ambit-bulk-bitwise-dram_micro17.pdf |
| ICP (TACO'15) | https://people.inf.ethz.ch/omutlu/pub/informed-caching-for-prefetching_taco15.pdf |
| Thesis CMU-CS-16-106 | https://arxiv.org/abs/1605.06483 |
| Direct Segments (ISCA'13) | https://research.cs.wisc.edu/multifacet/papers/isca13_direct_segment.pdf |
| OVC (ISCA'12) | https://www.csa.iisc.ac.in/~arkapravab/papers/isca12_OVC.pdf |
| ISPASS'16 | https://www.csa.iisc.ac.in/~arkapravab/papers/ispass16.pdf |
| Dead Page/Block (HPCA'21) | https://www.csa.iisc.ac.in/~arkapravab/papers/hpca21_DOA.pdf |
| Neighborhood (MICRO'18) | https://www.csa.iisc.ac.in/~arkapravab/papers/micro2018_neighborhood.pdf |
| Trident (MICRO'21) | https://www.csa.iisc.ac.in/~arkapravab/papers/MICRO21_Trident.pdf |
| MGvm (MICRO'22) | https://www.csa.iisc.ac.in/~arkapravab/papers/MICRO22_MGvm.pdf |
| ObservUVM (ISCA'26) | https://www.csa.iisc.ac.in/~arkapravab/papers/ISCA26_ObservUVM.pdf |
| RMM (ISCA'15) | https://pages.cs.wisc.edu/~swift/papers/isca15-rmm.pdf |
| Google consumer workloads (ASPLOS'18) | https://people.inf.ethz.ch/omutlu/pub/Google-consumer-workloads-data-movement-and-PIM_asplos18.pdf |
| Design-induced latency variation (SIGMETRICS'17) | https://arxiv.org/abs/1610.09604 |
