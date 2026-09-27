# W1: what happens every time a tool call creates a Python process

## Setup

- **Data:** the DynamoRIO trace of `django__django-13809` (`../w0_benchmark/`, 200M-instruction
  windows). Every Python process a tool call created is analysed from its first instruction.
- **Canonical PCs.** PCs are canonicalised to (file, link-time address), so ASLR does not hide
  identical code.
- **Phases.** The stream is cut at exact symbol boundaries (`lib/symbols.py`, using the libc6-dbg
  symbols for ld.so and libc):
  - **loader:** exec to the executable's ELF entry point `_start`;
  - **process init:** to `Py_BytesMain`;
  - **interpreter init:** to the first `PyRun_*`;
  - **tool code:** to `Py_FinalizeEx`;
  - **teardown:** to the end.
- **Creation region:** loader + process init + interpreter init.
- **Categories.** Each instruction also gets an activity category (`lib/categories.py`).
- **Script:** `scripts/w1_creation.py`. Figures: `scripts/figs_w1.py`.

## Results

**Scale.** The run created 46 Python processes in tool calls:
- 26 `_state_anthropic`, the state probe after every action;
- 13 `str_replace_editor`;
- 7 others: 2 `python -c`, 2 `submit`, 2 test scripts, 1 `python -m django`.

45 have their whole creation region inside the traced window. The 45 regions total 3.28 B
instructions.

**Creation is most of the work.**

| script | creation region (median) | whole process | creation share |
|---|---|---|---|
| `_state_anthropic` | 73.0M instructions | 87.1M | 84% |
| `str_replace_editor` | 73.2M | 149.2M | 49% |

`_state_anthropic` (median phases): loader 1.52M, process init 3.2K, interpreter init 71.47M,
tool code 6.2M, teardown 7.8M.

**Correction (2026-09-27).** A first version ended the loader at the first instruction outside
ld.so. That boundary fires early, because ld.so calls libc's ifunc resolvers while it relocates, so
most of the relocation was counted as "process init" (loader 0.26M, process init 1.26M). The
boundary is now the ELF entry point. The creation-region end, and therefore every creation-region
number and pair, is unchanged. The old table is kept on the pod as
`w1/creation_v1_ldso_boundary.csv`.

**The sequence of operations (`fig_flowchart.png`, source in `fig_flowchart.dot`).** Every step:
1. The harness writes a command.
2. `sh -c 'env bash -n'` and `bash -n` start.
3. `python3` is exec'd.
4. Its loader, process init and interpreter init run.

Per-phase cold cycles and L2/LLC misses come from W3 (Scarab golden_cove, pass 1 of the self-warm
runs, 100K-instruction intervals assigned to the phase that holds their midpoint), `_state`, median
over 26 creations:
- **loader:** 1.52M instructions, 1.29M cycles, 103K L2 misses, 19K LLC misses. It is 2% of the
  region's instructions but 37% of its L2 misses (68 per 1K instructions).
- **interpreter init:** 71.47M instructions, 38.65M cycles, 176K L2 misses, 32K LLC misses
  (2.5 L2 misses per 1K instructions).
- **process init:** 3.2K instructions, below the resolution of the interval data.

**How often it is the same (`fig_identical_cdf.png`).** Share of the creation region whose
32-instruction sequences also ran in the previous creation of the same script:

| script | pairs | median | minimum |
|---|---|---|---|
| `_state_anthropic` | 25 | 99.986% | 99.976% |
| `str_replace_editor` | 12 | 99.909% | 99.876% |

The minimum over all 39 pairs is 99.876%.

**Where the pair first differs (`fig_prefix_cdf.png`).**
- The exact common prefix is a median 77.7K instructions (`_state`).
- The first difference is in ld.so's `strchr` in 28 of 39 pairs, and in libc string routines or a
  dict lookup in the rest.
- The divergence is local. After it, the streams realign.

**Per operation (`fig_identical_by_operation.png`, `_state`, 26 creations).**
- **Identical instruction count in every creation:** process init (1.26M), ld.so relocation (0.89M),
  codec/locale (3.41M) and `.pyc` unmarshal (5.28M).
- **Nearly identical:** the rest, with a coefficient of variation of at most 0.66%. The largest
  variation is dict/hash/string (17.4M), which is consistent with per-process hash randomisation;
  that was not isolated.

**Operation breakdown (`fig_operation_breakdown.png`).** This is drawn in the form of Fig. 21 of
*Agentic Coding in the Wild*. That paper records only tool names and defines no taxonomy of the
work inside a tool call (`agentic_in_the_wild.md`), so the categories are ours. Over all 45 regions:

| operation | share |
|---|---|
| dict / hash / str | 23.9% |
| bytecode eval | 20.5% |
| other interpreter | 17.1% |
| type setup | 8.8% |
| `.pyc` unmarshal | 7.3% |
| GC | 6.2% |
| allocation | 5.9% |
| codec / locale | 4.7% |
| ld.so relocation | 1.2% |
| ld.so symbol lookup | 1.1% |

**Timeline (`fig_timeline.png`).** Every creation is placed on the traced run's timeline and
coloured by its identity with the previous one. Times are from the traced run and inflated by
DynamoRIO; the native timelines give real durations.

## Limits
- One task and one Python build (python3.8 with a shared libpython).
- The traced run carries DynamoRIO-only artefacts:
  - the `drpatch` sitecustomize import;
  - `GLIBC_TUNABLES` parsing, about 41K instructions per native process.
- Category attribution is by function name. Stripped code would fall into "other".
