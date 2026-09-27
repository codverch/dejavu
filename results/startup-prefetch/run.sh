#!/bin/bash
# The start-up prefetching study, end to end.
#
#   ./run.sh all            every stage, in order
#   ./run.sh <stage> ...    trace-dr trace-native convert summarize analyze build sim-baseline sim-ideal sim-more fetch figures
#
# Runs on phoebe-login. Traces and simulations run on the pod (config.env), which cannot see /h,
# so code is copied there first and results are copied back at the end. Every stage is
# idempotent: finished work is skipped. A failed check stops the script.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$HERE/config.env"
LOG="$HERE/logs"; mkdir -p "$LOG"
pod() { $KX bash -c "$*"; }
sha() { git -C "$1" rev-parse --short HEAD; }
BR_PKG() { echo "$POD_ROOT/scarab/$(git -C "$1" rev-parse --abbrev-ref HEAD)-$(sha "$1")"; }
DR_DIR=$POD_ROOT/w0/dr/$TASK/$DR_RUN

sync() {
  tar -C "$HERE" --exclude=__pycache__ -cf - lib scripts | pod "mkdir -p $POD_ROOT && tar -C $POD_ROOT -xf -"
}

stage() {
  case "$1" in
  trace-dr)
    pod "[ -e $DR_DIR/rc ] || (cd $E2E_SCRIPTS && IID=$TASK RUN_ID=$DR_RUN WINDOW_INSTRS=$DR_WINDOW PERIOD_INSTRS=$DR_PERIOD \
         E2E_ROOT=$POD_ROOT/w0/dr bash trace_e2e.sh)"
    pod "test \$(cat $DR_DIR/rc) = 0" ;;
  trace-native)
    runs=""; for t in $NATIVE_TASKS; do for i in $(seq 1 "$NATIVE_RUNS"); do runs="$runs,$t:run$i"; done; done
    pod "cd $POD_ROOT && python3 scripts/native_batch.py --out $POD_ROOT/native --runs ${runs#,} \
         --parallel $NATIVE_PARALLEL --cores $NATIVE_CORES" ;;
  convert)
    pod "[ -f $DR_DIR/attribution/windows.csv ] || (cd $E2E_SCRIPTS && taskset -c $SIM_CPUS $POD_PY_LZ4 e2e_post.py $DR_DIR --jobs 56)"
    pod "python3 -c \"import json,sys; s=json.load(open('$DR_DIR/convert_status.json')); bad=[k for k,v in s.items() if v!='ok']; print(len(s),'units',len(bad),'failed'); sys.exit(1 if bad else 0)\"" ;;
  summarize)
    pod "cd $POD_ROOT && ls -d native/*/run* | taskset -c $SIM_CPUS xargs -P 30 -I{} sh -c '[ -f {}/calls.csv ] || $POD_PY scripts/native_summary.py {}'" ;;
  analyze)
    pod "cd $POD_ROOT && [ -f w1/creation.csv ] || taskset -c $SIM_CPUS $POD_PY scripts/w1_creation.py $DR_DIR w1 --jobs 32" ;;
  build)
    bash "$HERE/scripts/build_scarab.sh" "$BASELINE_WT"
    bash "$HERE/scripts/build_scarab.sh" "$IDEAL_WT"
    # the added code, switched off, must change nothing
    T=$(pod "cd $POD_ROOT && python3 -c \"import csv; r=[x for x in csv.DictReader(open('$DR_DIR/attribution/windows.csv')) if x['window']=='0' and x['tid']==x['pid'] and x['phase']=='tool execution']; print(' '.join(sorted({x['comm']:x['trace_zip'] for x in r}.values())[:4]))\"")
    pod "cd $POD_ROOT && $POD_PY scripts/check_identical.py $(BR_PKG "$BASELINE_WT") $(BR_PKG "$IDEAL_WT") checks/identical $T > checks/identical.txt"
    pod "cat $POD_ROOT/checks/identical.txt" ;;
  sim-baseline)
    pod "cd $POD_ROOT && $POD_PY scripts/w3_baseline.py $DR_DIR w1 w3 --pkg $(BR_PKG "$BASELINE_WT") --jobs $JOBS" ;;
  sim-ideal)
    pod "cd $POD_ROOT && $POD_PY scripts/w4_ideal_prefetch.py $DR_DIR w1 w3 w4 --pkg $(BR_PKG "$IDEAL_WT") --jobs $JOBS"
    pod "python3 -c \"import csv,sys; c=list(csv.DictReader(open('$POD_ROOT/w4/checks.csv'))); bad=[x for x in c if x['ok']!='1']; print(len(c),'checks',len(bad),'failed'); sys.exit(1 if bad else 0)\"" ;;
  sim-more)
    # W6: two units per phase from four other SWE-bench tasks. Two units hit an instruction Scarab
    # cannot decode (OP_INV) at 52.3M and 5.89M instructions; they are simulated up to before it.
    pod "cd $POD_ROOT && $POD_PY scripts/w6_more_traces.py $MORE_TRACES w6 --pkg $(BR_PKG "$IDEAL_WT") --jobs 48 \
         --limit sphinx-doc-678=52000000 --limit pydata-1524=5800000"
    # W7: each whole task's instructions per phase, for the task-level speedup
    pod "cd $POD_ROOT && python3 scripts/phase_mix.py w6/phase_mix.csv $TASK=$DR_DIR \
         $(for t in psf__requests-1142 pydata__xarray-2905 sphinx-doc__sphinx-8459 sympy__sympy-11618; do echo "$t=$MORE_TRACES/$t/trace1"; done)" ;;
  fetch)
    mkdir -p "$RESULTS"/{w0_benchmark/native,w0_benchmark/dr,w1_creation,w3_baseline,w4_ideal_prefetch,w6_more_traces,checks}
    pod "cat $POD_ROOT/checks/identical.txt" > "$RESULTS/checks/identical.txt"
    pod "cd $POD_ROOT/w6 && tar -cf - selection.csv limits.csv results.csv checks.csv" | tar -C "$RESULTS/w6_more_traces" -xf -
    mkdir -p "$RESULTS/w7_task_speedup"; pod "cat $POD_ROOT/w6/phase_mix.csv" > "$RESULTS/w7_task_speedup/phase_mix.csv"
    pod "cd $POD_ROOT/native && tar -cf - */run*/{calls.csv,procs.csv,gaps.csv,harness_spans.csv,throttle.json,perf_stats.txt,cpu_idle.json,rc,cpus.txt,swetrace.ndjson}" | tar -C "$RESULTS/w0_benchmark/native" -xf -
    pod "cd $DR_DIR && tar -cf - swetrace.ndjson sampling_policy.json procs.jsonl attribution/windows.csv attribution/summary.json convert_status.json rc" | tar -C "$RESULTS/w0_benchmark/dr" -xf -
    pod "cd $POD_ROOT/w1 && tar -cf - creation.csv pairs.csv shells.csv" | tar -C "$RESULTS/w1_creation" -xf -
    pod "cd $POD_ROOT/w3 && tar -cf - results.csv runs/*__self_warm/series.npz" | tar -C "$RESULTS/w3_baseline" -xf -
    pod "cd $POD_ROOT/w4 && tar -cf - results.csv rebase.csv pollution.csv checks.csv" | tar -C "$RESULTS/w4_ideal_prefetch" -xf - ;;
  figures)
    python3 "$HERE/scripts/w2_prediction.py" "$RESULTS/w2_prediction" $(ls -d "$RESULTS"/w0_benchmark/native/*/run*)
    python3 "$HERE/scripts/figs_w1.py" "$RESULTS"
    python3 "$HERE/scripts/figs_w3_w4.py" "$RESULTS"
    python3 "$HERE/scripts/figs_w6.py" "$RESULTS"
    python3 "$HERE/scripts/w7_task_speedup.py" "$RESULTS" ;;
  *) echo "unknown stage $1" >&2; exit 2 ;;
  esac
}

sync
stages=("$@"); [ "${1:-}" = all ] && stages=(trace-dr trace-native convert summarize analyze build sim-baseline sim-ideal sim-more fetch figures)
for s in "${stages[@]}"; do
  echo "== $s  $(date -u +%FT%TZ)"
  stage "$s" 2>&1 | tee "$LOG/$s.log"
done
