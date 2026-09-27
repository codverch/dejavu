# W2: which tool calls create a Python process, and how well that can be predicted

## Setup

- **Data:** 30 native SWE-agent runs, 6 each of five SWE-bench tasks (`../w0_benchmark/native/`).
- **Tool call:** a model-invoked action (`tool.exec`), or SWE-agent's state probe (`tool.get_state`,
  which runs `python3 _state_anthropic` after every action). Setup commands are excluded.
- **Creates Python:** a process forked inside the call exec'd a Python interpreter (perf exec
  events).
- **Type:** the command's first word (after a leading `cd <dir> &&` and any `VAR=value`), or the
  editor's subcommand (`lib/native.py:tool_type`).

## Results

**How often (`fig_tool_types.png`, `type_summary.csv`, `fig_python_per_step.png`).**
- Of 2,208 tool calls, 1,961 created at least one Python process:
  - all 1,119 state probes;
  - 842 of 1,089 actions.
- Each type either always creates Python or never does:
  - **always:** every editor subcommand, `python <script>`, `python -c`, `python -m …` (pytest,
    unittest, django, py_compile) and `submit`;
  - **never:** `grep`, `find`, `rm`, `git`, `sed`, `ls`.
- An agent step creates a median of 2 Python processes (mean 1.78).

**Most invoked tools (`fig_most_invoked_tools.png`, `fig_most_invoked_tools_by_name.png`).** These
are drawn like Fig. 21 of *Agentic Coding in the Wild* (Liu et al., arXiv 2608.00101), over the
1,089 model-invoked actions:

| tool | share of actions |
|---|---|
| `str_replace_editor view` | 24.2% |
| `python <script>` | 17.1% |
| `grep` | 13.5% |
| `str_replace_editor create` | 13.3% |
| `str_replace_editor str_replace` | 8.2% |
| `python -c` | 5.8% |
| `submit` | 4.8% |
| `find` | 4.5% |

The `_by_name` version uses SWE-agent's three registered tool names, the paper's granularity.

**Prediction.** The prediction point is the end of `response.parse`: the action is known, and
nothing has run yet. The predictors were fixed before the results were seen, and the rule (P1) was
trained leave-one-task-out. Pooled over all calls:

| predictor | accuracy | precision | recall | median per-run accuracy (min) |
|---|---|---|---|---|
| P0 always yes | 0.888 | 0.888 | 1.000 | 0.894 (0.803) |
| **P1 rule on call type** | **0.997** | **1.000** | **0.997** | **1.000 (0.968)** |
| P2 previous call of the same kind | 0.834 | 0.919 | 0.891 | 0.842 (0.770) |
| P3 P1 or P2 | 0.930 | 0.927 | 1.000 | 0.935 (0.902) |

- On actions only, P1 scores 0.995 / 1.000 / 0.993.
- P1's 6 misses are types seen in only one task (e.g. `python -m django`), so the held-out rule
  has never seen them.
- Figures: `fig_accuracy_cdf.png` and the `precision`/`recall` variants, plus `_actions` versions
  of each.
- Predicting *which* script from the type is also exact where the script is known
  (`which_script.csv`): editor → `str_replace_editor`, state → `_state_anthropic`, `submit` →
  `submit`.

**Lead time (`fig_leadtime_cdf.png`, `lead.csv`).** Time from the prediction point to the Python
exec:
- **Actions:** median 56.4 ms (10th percentile 55.2 ms, 90th 68.4 ms). The tree ran a median of 12M
  instructions in that time.
- **State probes:** median 206.5 ms, because they wait for the action to finish.

The action lead time is narrow. It is plausibly dominated by SWE-ReX's fixed pexpect send delays;
an earlier study measured about 2 × 50 ms per command. That was not measured here.

## Limits
- Command lines were mostly not captured natively (see W0). Which script ran comes from exec
  chains, so plain `python <script>` calls are "(script not captured)".
- Five tasks, one agent (SWE-agent), one model. The deterministic type→Python mapping is a property
  of SWE-agent's tools. Another agent's tools would need their own table.
