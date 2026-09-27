# "Agentic coding in the wild": what the paper categorises and how it plots it

Written 2026-09-26 for PLAN.md W1 item 5 (`fig_operation_breakdown.png`). Rule zero applies.
Everything below was read in the paper's PDF (arXiv 2608.00101v1, 20 pages; text extracted
with `pypdf`, figure pages rendered and viewed). No category is invented here.

## 1. Candidates found

I searched for "Agentic coding in the wild" (arXiv, Microsoft Research, and a broader search
for "in the wild" coding-agent studies). One paper matches the title. Four others share the
phrase "in the wild" or study coding agents in production.

| # | Exact title (arXiv abstract page) | Authors | Link | Date | Match? | Read |
|---|---|---|---|---|---|---|
| 1 | **Agentic Coding in the Wild: Characterizing GitHub Copilot Traces at Production Scale** (the PDF title omits "Traces": "Agentic Coding in the Wild: Characterizing GitHub Copilot at Production Scale") | Banruo Liu (UIUC), Haoran Qiu, Íñigo Goiri, Rodrigo Fonseca, Ricardo Bianchini, Esha Choukse (Microsoft Azure Research / Microsoft Azure) | https://arxiv.org/abs/2608.00101 | v1, 30 Jul 2026 | **Yes. This is the paper.** | [read] |
| 2 | SWE-chat: Coding Agent Interactions From Real Users in the Wild | Joachim Baumann, Vishakh Padmakumar, Xiang Li, John Yang, Diyi Yang, Sanmi Koyejo | https://arxiv.org/abs/2604.20779 | 22 Apr 2026 | No (different title) | [abstract only] |
| 3 | Investigating Autonomous Agent Contributions in the Wild: Activity Patterns and Code Change over Time | Razvan Mihai Popescu, David Gros, Andrei Botocan, Rahul Pandita, Prem Devanbu, Maliheh Izadi | https://arxiv.org/abs/2604.00917 | 1 Apr 2026 | No (studies pull requests) | [abstract only] |
| 4 | Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild | Obada Kraishan | https://arxiv.org/abs/2609.17598 | 12 Sep 2026 | No (studies pull requests) | [abstract only] |
| 5 | From Agent Behaviour to Agent-Friendly Documentation: An Empirical Study of How Coding Agents Discover, Read, and Write Technical Documentation | Zhijun Gao, Jing Chen | https://arxiv.org/abs/2608.20195 | 20 Aug 2026 | No | [abstract only] |

- A Microsoft Research page for paper 1 exists:
  https://www.microsoft.com/en-us/research/publication/agentic-coding-in-the-wild-characterizing-github-copilot-at-production-scale/.
  I did not open it.
- The rest of this file is about paper 1.

## 2. What the paper measures

- **Data.** Anonymised client-side telemetry from GitHub Copilot's coding agent in Visual
  Studio and VS Code, first week of June 2026 (section 3.1, Table 3).
- **Size.** 13.5M sessions, 95.1M turns, 3.2M users, 27+ models, 45+ tools, 760.5M LLM calls
  and 774.7M tool calls.
- **What is recorded.** For every LLM call and tool invocation, the telemetry records
  "timestamps, durations, input/output token counts ..., model names, tool names, and success
  or failure status".
- **What is not recorded.** "We do not collect the prompt text or file content, model
  outputs, source code, tool arguments". So the paper never sees a command line. It sees only
  a tool's *name*.

## 3. How it categorises agent operations

The paper has **no single formal taxonomy of tool calls with written definitions**. It
categorises at four levels. Each is quoted or tabulated here exactly as the paper gives it.

### 3.1 Execution hierarchy (section 3.2), defined in the text

- **Session:** "a coding agent session lifetime."
- **User-Turn (or simply Turn):** "one agentic coding conversation triggered by the user
  prompt and followed by the agent's full autonomous response chain."
- **Step:** "a single LLM invocation or tool call within a turn; the last step in a turn is
  always an LLM invocation."
- **Canonical pattern:** `User prompt → LLM → [LLM | tools → LLM]* → final response`.
- **Tool batch** (used in sections 4.4 and 7.2 and in Figs. 12, 26 and 28; no formal
  definition sentence) is a group of tool invocations dispatched together. "93% contain a
  single tool invocation, while only 7% dispatch multiple tools concurrently."

### 3.2 Wall-clock categories (section 5.1, Fig. 12)

The paper "breaks down an agentic session wall-clock time into three categories: (1) LLM
execution, (2) tool execution, and (3) user idle time between turns." The figure legend
calls them "LLM time", "Tool batch time" and "User idle".

### 3.3 Tool categories (section 7.1 text and Fig. 27 legend)

**Individual tools.** The paper's unit is the tool name. Fig. 21 lists the 15 most-invoked
tools and "Others". Its axis labels abbreviate the names, and the text and Fig. 23 give the
full names:
`get_file`, `run_command_in_terminal`, `replace_string_in_file`, `code_search`, `run_build`,
`file_search`, `apply_patch`, `create_file`, `update_plan_progress`,
`multi_replace_string_in_file`, `get_errors`, `edit_file`, `get_files_in_project`,
`get_symbols_by_name`, `get_projects_in_solution`. `run_tests` appears in Fig. 25.

**Informal three-way grouping in the text (section 7.1).** It is used to describe latency.
It has no definition sentence, and no table assigns every tool to a group.

| Group (paper's words) | Tools the paper names as members |
|---|---|
| "Read-oriented operations" | `update_plan_progress`, `get_symbols_by_name`, `get_file`, `file_search` (also "Read and search tools, such as `get_file` and `code_search`") |
| "Mutating tools" | `replace_string_in_file`, `apply_patch`, `create_file` |
| "execution-oriented tools" | `run_command_in_terminal`, `run_build` |

**Two-way grouping in Fig. 27 (legend: "Read" / "Write").** The bar colour assigns each of
the 15 tools to one group. I read the colours from the rendered page 14.

| Read | Write |
|---|---|
| get_files_in_project, get_symbols_by_name, get_file, get_projects_in_solution, file_search, code_search, get_errors | create_file, edit_file, run_command_in_terminal, replace_string_in_file, update_plan_progress, run_build, apply_patch, multi_replace_string_in_file |

- The two groupings disagree on `update_plan_progress`. It is "read-oriented" in the 7.1
  text but coloured "Write" in Fig. 27.
- Fig. 27 folds execution into "Write". Its caption says "Read/lookup tools are frequently
  batched; write/run-command tools are almost always serial."

### 3.4 Turn-level workflow archetypes (section 4.4, Table 5)

These come from clustering turns "using their tool composition, LLM-call depth, token
consumption, and execution characteristics". Table 5, verbatim:

| Archetype | LLM calls (median) | Description | Share of turns |
|---|---|---|---|
| Deep-loop read | 9 | 7 tool batches; read-heavy | 30.5% |
| LLM-only | 1 | No tools; pure reasoning | 20.2% |
| Multi-cycle edit | 5 | Read + edit + build | 19.0% |
| Multi-cycle other | 4 | Read-dominant | 13.2% |
| Deep-loop w/failures | 36 | 34 batches; retry loops | 9.1% |
| Deep-loop run | 7 | Terminal-heavy | 8.1% |

### 3.5 User types (section 8.1, Table 7)

These are included for completeness and are not an operation taxonomy: Readers ("Mostly
reads/searches"), Coders ("Balanced read+edit+exec"), Terminal users ("Mostly terminal
calls"), Deep-loop users ("Long agentic loops") and Chat-only users ("100% Q&A turns; no
tools").

## 4. How the paper plots the breakdowns

| Figure | What | Chart type | Axes | Normalisation | Annotation |
|---|---|---|---|---|---|
| Fig. 21 "Most invoked tools and their frequency." | Tool-call mix | Vertical bar chart, one bar per tool, sorted by frequency descending, then an "Others" bar (grey) | y: "Invocation %" (0-35); x: abbreviated tool names, rotated about 45° | Share of all tool invocations (%) | Value printed above every bar (35.0, 17.0, 9.8, ...) |
| Fig. 12 (a) single-turn, (b) multi-turn sessions | Wall-time split into LLM / tool batch / user idle | CDF over sessions, one line per category | x: "% of Total Session Time" (0-100); y: "CDF of Sessions" (0-1) | Per-session share of wall-clock time | Median of each category in the legend, e.g. "LLM time (med 13.7%)", "Tool batch time (med 2.0%)", "User idle (med 80.1%)" |
| Fig. 23 | Tool latency by tool | CDF per tool (top 10), log-x | x: "Duration (log scale)", ticks 1ms-1d; y: "CDF of Tool Calls" | none | Legend with full tool names |
| Fig. 22 | Tool vs LLM call duration | Two CDFs, log-x | x: "Duration (log scale)"; y: "CDF of Calls" | none | Dashed vertical median lines labelled "166ms" and "5.3s" |
| Fig. 24 | Duration by success/failure | Per-tool distributions, log-y (ms), with success rate on a second y-axis | y1: "Duration (ms)" 10^1-10^6; y2: "Success Rate (%)" | none | Legend: "Success dur.", "Failure dur.", "Success rate" |
| Fig. 27 | Parallelism per tool, grouped Read/Write | Horizontal bar chart, colour = group | x: "Parallelism Rate (%)"; y: tool names | Fraction of a tool's invocations issued in a parallel batch | Average batch size printed at the end of each bar ("1.9×") |
| Fig. 28 | Tool time inside vs outside LLM windows | 100%-stacked vertical bars per duration bucket | y: "Share of Tool Time (%)"; x: duration bucket with the bucket's share of batches in parentheses ("< 50ms (21%)") | Per bucket, to 100% | Segment percentages printed inside the segments |
| Fig. 11 | Prompt-token source breakdown | One 100%-stacked horizontal bar ("Avg per Call") | x: "Token Share (%)" | Average share per call | Legend: System, History, FuncCalls, Context, RepoInstr |

Style notes, from the rendered pages:
- Sans-serif fonts.
- Dashed light grid.
- Legends inside the plot area.
- Axis titles on every axis, with the unit or the "%" in the title.

## 5. What this means for `fig_operation_breakdown.png`

These are facts about applicability, not decisions. The decision belongs to W1 and the user.

1. **The paper gives no category definitions for operations *inside* a tool call.** It
   cannot see inside one: no arguments, no processes.
   - It has nothing for exec, ld.so, libc init or interpreter init.
   - Applying "its taxonomy" to creation-region operations is therefore not possible without
     inventing categories. PLAN.md says to stop and report in that case. **For
     creation-region operations: stop; the paper does not define a usable taxonomy.**
2. **For tool calls, the paper's usable, explicitly labelled categorisation is Fig. 27's
   two-way Read / Write split.** It is assigned by tool name, and its legend is explicit.
   - The three-way Read-oriented / Mutating / execution-oriented grouping of section 7.1 is
     prose. It names only some tools, and it disagrees with Fig. 27 on
     `update_plan_progress`.
   - Mapping SWE-agent tools (`str_replace_editor view/create/str_replace`, `bash` commands,
     `submit`, `_state_anthropic`) onto either grouping requires a judgement the paper does
     not make for these tools. Any such mapping must be labelled "our mapping, following the
     paper's Read/Write grouping", with the full mapping table published next to the figure.
3. **To follow the paper's plotting convention for a tool-mix breakdown, use Fig. 21's
   form:**
   - vertical bars sorted by descending share;
   - y-axis "Invocation %";
   - the value printed above each bar;
   - the long tail grouped as "Others" in a neutral colour.

   For a time split, use Fig. 12's form: a CDF over units (sessions, or steps for us) of
   "% of total time", with the median in the legend. For a time split per bucket, use
   Fig. 28's form: 100%-stacked bars with the percentages inside.
4. **The paper's wall-time categories line up with PLAN.md's phases.** Its LLM execution,
   tool execution and user idle map onto our model inference, tool execution and harness
   phases, except that the paper has no "harness" category and our runs have no user idle.
   Say so if the categories are borrowed.

## 6. Items not verified

- The Read/Write assignment in section 3.3 was read from bar colours in a 110-dpi rendering
  of page 14. I did not check it against the figure's source data.
- I did not open the Microsoft Research page or any later arXiv version. Only v1 exists as of
  2026-09-26 per the arXiv submission history.
- For papers 2-5, I read only the abstract pages. None of them was checked for a tool
  taxonomy. SWE-chat reports "355,000 agent tool calls" in its abstract and may categorise
  them; not verified.
