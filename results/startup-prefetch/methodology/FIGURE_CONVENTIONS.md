# Figure conventions (labelling after Sriraman, neatness after Athalye)

Written 2026-09-26 for PLAN.md section 2.3. These are rules for matplotlib figures in
`results/startup-prefetch/*/fig_*.png`.

## Sources opened

- **SoftSKU.** Sriraman, Dhanotia, Wenisch. "SoftSKU: Optimizing Server Architectures for
  Microservice Diversity @Scale." ISCA 2019. doi:10.1145/3307650.3322227. **[read]**
  - The paper PDF (14 pages) is from the Meta Research copy linked on the author's page. I
    viewed every figure page (1, 4, 5, 6, 10) as a rendered image.
- **Accelerometer.** Sriraman, Dhanotia. "Accelerometer: Understanding Acceleration
  Opportunities for Data Center Overheads at Hyperscale." ASPLOS 2020. **[read, figures
  only]**
  - The paper PDF (18 pages) is from the Meta Research copy. I viewed pages 4 and 13 as
    images and extracted all captions.
  - The main text was not read in full.
- The PDFs at `users.ece.cmu.edu/~asrirama/publication/{isca/softsku,asplos/accelerometer}.pdf`
  are **talk slides**, not the papers. I did not use them.

## What her figures do (observed)

Each observation names the figure it comes from.

1. **Axis titles are short, and the unit or "%" is always in the title.**
   - Examples: "CPU util. (%)" (SoftSKU Fig. 3), "Pipeline slot breakdown (%)" (Fig. 7),
     "LLC MPKI" (Fig. 9), "Context switch penalty range (%)" (Fig. 4), "% Perf. gain over
     CDP off" (Fig. 16), "% Perf. gain with µSKU" (Fig. 19).
   - Accelerometer: "% Cycles spent in leaf function categories" (Fig. 2), "% Speedup"
     (Fig. 20), "Range of bytes copied" (Fig. 21).
   - Relative quantities name their baseline in the axis title: "over CDP off", "over
     'madvise'", "over no SHP", "over all prefetch off".
2. **Breakdowns are 100%-stacked horizontal bars, one row per workload.**
   - Examples: SoftSKU Figs. 5 and 7; Accelerometer Figs. 2 and 3.
   - The x-axis runs from 0 to 100 and is titled "... (%)".
   - Rows are grouped by suite: the group name is written vertically to the left of a
     bracket or separator line ("Our microservices", "SPEC2006", "Google [Kanev'15]
     (Haswell)", "FB microservices").
   - The group label names the source and the platform whenever the data comes from prior
     work.
3. **Every segment of a breakdown carries its value** as an integer percentage inside the
   segment.
   - Examples: "37", "31", "20" in Accelerometer Fig. 2; "32 | 36 | 12 | 20" in SoftSKU
     Fig. 7.
   - Very thin segments are left unlabelled or get a cramped label.
4. **Totals and caveats are written at the end of a bar.**
   - Accelerometer Fig. 3 prints "Net = 37%", "8%", "20%" after each row.
   - It prints "13%*" where only part of the data exists, and the text explains the
     asterisk.
5. **Legends sit on top of the plot, in one or two horizontal rows.**
   - The entries are in the same order as the stacked segments.
   - Where the stack is a share, the legend entries carry the unit: "Branch (%)",
     "Floating point (%)" (SoftSKU Fig. 5).
6. **Categories are defined in a table beside the breakdown.** Accelerometer Table 2
   ("Categorization of leaf functions") lists each category with examples ("Memory — Memory
   copy, allocation, free, compare"; "Kernel — Task scheduling, interrupt handling, ...").
7. **Values that do not fit are printed, not hidden.**
   - SoftSKU Fig. 9 clips tall bars and writes "D=80, C=0.1" above them.
   - Fig. 11 writes "L=65" and "S=..." above clipped bars, and marks a cluster "Very low
     values" with a bracket.
8. **Missing configurations are marked "NA" on the chart,** not silently dropped
   (Accelerometer Fig. 20).
9. **Bounds are drawn next to the mechanism in the same chart.** Accelerometer Fig. 20
   places an "Ideal" bar first, beside the on-chip and off-chip options, in "% Speedup".
10. **The chosen configuration is highlighted with a red outline** (SoftSKU Figs. 17 and
    18b, where "488" is also printed). Bar labels that encode configurations, such as
    "{LLC ways data, code}" in Fig. 16, are explained in the text next to the figure.
11. **Error bars appear on measured performance gains** (SoftSKU Figs. 17-19). The text
    states "We report 95% confidence intervals on mean results."
12. **CDFs mark the threshold that matters with a dotted vertical line and a short
    in-plot note** (Accelerometer Figs. 21-22: "Ads1: On-chip 'g' to break even").
13. **Captions follow "Figure N: <what is plotted>: <one-line takeaway>."**
    - SoftSKU Fig. 9: "LLC code & data MPKI: LLC data MPKI is high across microservices and
      Web incurs a high code LLC MPKI."
    - Fig. 3: "Max. achievable CPU utilization in user- and kernel-mode across µservices:
      utilization can be low to avoid QoS violations."
    - Accelerometer uses the same pattern with a period instead of a colon.
14. **Comparison baselines from prior work appear in the same chart,** labelled with the
    citation (SoftSKU Figs. 6-9: "Google [Kanev'15] (Haswell)", "Google [Ayers18]
    (Haswell)", "SPEC2006").

## Rules we follow (matplotlib)

Rules 1-11 are Sriraman-style labelling. Rules 12-14 are the Athalye-style neatness that
PLAN.md asks for.

1. **Every axis has a title with a unit.**
   - Write it as `ax.set_ylabel("Cycles saved vs cold (%)")`, or with the unit in brackets:
     `"Instructions (millions)"`, `"Lead time (µs)"`.
   - For a relative metric, name the baseline in the title: "Speedup over cold (%)",
     "Traffic over cold baseline (%)".
2. **Annotate every bar or segment of interest with its value.**
   - Use `ax.bar_label(bars, fmt="%.1f", padding=2)` for single bars.
   - For stacked segments, `ax.text` at the segment centre, and only if the segment is
     wider than about 4% of the axis. Otherwise leave it unlabelled and give the value in
     the caption file.
3. **Use 100%-stacked horizontal bars for breakdowns** (share of cycles, instructions or
   misses by operation).
   - One row per creation class or configuration, x from 0 to 100, titled "... (%)".
   - Group rows with a vertical group label on the left, for example "_state_anthropic
     (py3.8)" vs "str_replace_editor (py3.8)".
4. **Print totals at the end of rows** (`"n = 57"`, `"total 82.4M instr"`) when the stack is
   normalised. The reader then keeps the absolute scale.
5. **Name every category, either on the plot or in an explicit legend.**
   - Put the legend on top (`loc="lower left", bbox_to_anchor=(0, 1.02), ncol=k,
     frameon=False`) in segment order.
   - Prefer direct labels (Athalye) when there are four or fewer series.
6. **Publish a category-definition table** (Markdown or CSV next to the figure) for any
   breakdown whose categories we define, for example the creation-region operations. Give
   each category its symbols or boundary rule, as in Accelerometer Table 2.
7. **Never hide an out-of-range value.** Clip the axis if needed, but print the value above
   the clipped bar. Mark missing or not-run configurations "not run" or "NA" at their
   position, per rule zero.
8. **Draw bounds next to the mechanism.** Cold, self-warm, perfect-* and `instant+self` go
   on the same axis and in the same units as the realistic spf bars.
   - Show ideal configurations with hatching or a lighter fill.
   - Include the word "ideal" in their label.
9. **Show variation.** Draw the median as the bar with a 10th-90th percentile whisker
   (PLAN.md), or use box plots (25-75 box, 10-90 whiskers).
   - The caption file says which, and gives n.
   - Sriraman's figures use 95% confidence-interval error bars; we use the percentile band
     because PLAN.md requires it. Give the CI in the README.
10. **Mark thresholds on CDFs** with a dotted vertical line and a short in-plot note. For
    example, on `fig_leadtime_cdf.png`: "time to issue creation-region prefetches".
11. **Captions.** Each `fig_*.txt` holds two to four sentences in this order:
    - `<What is plotted>: <takeaway>.`
    - the data source: the task (`django__django-13809`), the Python version, the Scarab
      configuration (`golden_cove` or `golden_cove_pow2`), and the input CSV path;
    - the definition of anything non-obvious (baseline, normalisation, ideal assumptions).
12. **Spines.** Left and bottom only (`ax.spines[["top", "right"]].set_visible(False)`).
    - No boxed legends, no background colour, and no 3-D.
    - Use a light dotted y-grid only where values are read off the axis.
13. **Font and colour.**
    - Serif type, as in `anish_style.py`. Sriraman's figures are sans-serif; PLAN.md chooses
      serif, so serif wins.
    - Colour with thin black outlines (memory note "Figure style").
    - One colour per category, used the same way in every figure of the study.
14. **Output.** One graph per file, PNG at 400 dpi, with a sibling `.txt` caption file.

## Items not verified

- The Accelerometer body text was not read. Its figure observations come from the rendered
  pages 4 and 13 and the extracted captions only.
- muSuite (IISWC 2018) was not opened.
- The red-outline and "NA" conventions were observed in one or two figures each. I did not
  check whether they appear consistently across her other papers.
