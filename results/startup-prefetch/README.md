# Ideal prefetching for Python process creation in coding agents

This directory holds the study described in `PLAN.md`: the code, the configuration, and (on branch
`ideal-prefetching`) every result. Raw traces and simulator output stay on the pod.

## Run it
```
./run.sh all          # or: make all
./run.sh <stage>      # trace-dr trace-native convert summarize analyze build sim-baseline sim-ideal fetch figures
```
- `config.env` names the task, the trace policy, the pod, the two Scarab worktrees and the job count.
- Every stage skips work that is already done.
- Checks stop the run: conversion failures, bit-identity of the two Scarab builds, and a record pass
  matching the baseline.

## Layout
| path | what |
|---|---|
| `lib/` | trace reading and address canonicalisation, symbols and phase boundaries, activity categories, native accounting, simulation runner, ASLR rebasing |
| `scripts/` | one script per stage (see each file's docstring) |
| `w0_benchmark/` … `w5_report/` | results per workstream, each with `README.md` and `STATUS.md` (on `ideal-prefetching`) |
| `w3_baseline/` | on this branch: baseline and bound simulations of every Python creation |
| `scripts/progress.sh` | a one-line progress battery, used in the Claude Code status line |
