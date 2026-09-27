#!/bin/bash
# One native (untraced) SWE-agent run with per-process instruction accounting.
#
#   IID=<task> RUN_ID=<id> CPUS=<list, e.g. 16-23> OUT=<root> native_run.sh
#
# Same harness configuration as swe-bench-e2e/scripts/trace_e2e.sh (SWE-agent, local
# deployment, qwen3-coder-30b on vLLM, temperature 0, 50-call cap), without DynamoRIO and
# without its drpatch sitecustomize. The harness and every descendant are pinned to CPUS;
# perf samples user instructions on those CPUs only (-C, one sample per 1M instructions,
# CLOCK_MONOTONIC) with task events, so counts can be joined with the harness spans.
# proclog.py records every descendant's command line from outside the pinned set.
set -euo pipefail
PERF=/usr/lib/linux-tools-5.15.0-190/perf
POOL=/localdisk/deepanjm/scaling-out
DATA=/localdisk/deepanjm/agentic-core
SWE_PY=$DATA/swe-agent-venv/bin/python
SWE_SRC=$DATA/SWE-agent
PROCLOG=/localdisk/deepanjm/isca-traces/swe-bench-e2e/scripts/proclog.py
MODEL=qwen3-coder-30b; API_BASE=http://127.0.0.1:8000/v1; API_KEY=local-vllm-key; MAX_CALLS=50
IID=${IID:?}; RUN_ID=${RUN_ID:?}; CPUS=${CPUS:?}; OUT=${OUT:?}
OUTDIR=$OUT/$IID/$RUN_ID; WORK=$OUTDIR/agent
[ -e "$OUTDIR/rc" ] && { echo "$OUTDIR already finished"; exit 0; }
rm -rf "$OUTDIR"; mkdir -p "$WORK/priv/tools" "$WORK/out"
cp -a "$POOL/repos/$IID" "$WORK/repo"
for f in model.patch .swe-agent-env test.patch; do : > "$WORK/priv/$f"; done
echo '{}' > "$WORK/priv/state.json"
mkdir -p "/$IID" /root/tools
for f in state.json model.patch .swe-agent-env test.patch; do [ -e /root/$f ] || touch /root/$f; done
BASE_COMMIT=$(python3 -c "import json;print(json.load(open('$POOL/instances/$IID.json'))['base_commit'])")
python3 -c "import json;open('$WORK/problem_statement.md','w').write(json.load(open('$POOL/instances/$IID.json'))['problem_statement'])"
export OPENAI_API_KEY=$API_KEY PYTHONPATH=$POOL/pysrc HOME=/root USER=root \
       HF_HOME=$DATA/hf-home LITELLM_LOCAL_MODEL_COST_MAP=True NO_PROXY=127.0.0.1,localhost \
       SWETRACE_OUT=$OUTDIR/swetrace.ndjson SWETRACE_RUN_ID=$RUN_ID:$IID SWETRACE_HOST=0 PYTHONUNBUFFERED=1
BINDS="mount --bind $WORK/repo /$IID"
for f in tools state.json model.patch .swe-agent-env test.patch; do BINDS="$BINDS && mount --bind $WORK/priv/$f /root/$f"; done
echo "$CPUS" > "$OUTDIR/cpus.txt"
date +%s.%N > "$OUTDIR/t_launch"
python3 -c "import time;a=time.time();m=time.clock_gettime(time.CLOCK_MONOTONIC);b=time.time();print(f'{(a+b)/2-m:.6f}')" > "$OUTDIR/clock_offset.txt"
( while [ ! -s "$OUTDIR/harness.pid" ]; do sleep 0.01; done
  exec python3 "$PROCLOG" "$(cat "$OUTDIR/harness.pid")" "$OUTDIR/procs.jsonl" "$OUTDIR/rc" ) > "$OUTDIR/proclog.log" 2>&1 &
cd "$SWE_SRC"
set +e
unshare --mount --propagation private -- bash -c 'echo $$ > "$0/harness.pid"; '"$BINDS"' && exec "$@"' "$OUTDIR" \
  "$PERF" record -C "$CPUS" -e 'instructions/period=1000000/u' --sample-cpu -k CLOCK_MONOTONIC -o "$OUTDIR/perf.data" -- \
    taskset -c "$CPUS" "$SWE_PY" -m swetrace.cli run --config "$SWE_SRC/config/default.yaml" \
      "--agent.model.name=openai/$MODEL" "--agent.model.api_base=$API_BASE" "--agent.model.api_key=$API_KEY" \
      --agent.model.per_instance_cost_limit=0 --agent.model.total_cost_limit=0 \
      "--agent.model.per_instance_call_limit=$MAX_CALLS" --agent.model.max_input_tokens=60000 \
      --agent.model.max_output_tokens=4096 --agent.model.temperature=0.0 \
      --agent.tools.execution_timeout=600 --agent.tools.total_execution_timeout=36000 \
      --env.deployment.type=local --env.repo.type=preexisting "--env.repo.repo_name=$IID" \
      "--env.repo.base_commit=$BASE_COMMIT" \
      "--env.post_startup_commands=export PATH=$POOL/envs/$IID/bin:\$PATH" \
      "--problem_statement.path=$WORK/problem_statement.md" "--problem_statement.id=$IID" \
      "--output_dir=$WORK/out" > "$OUTDIR/run.log" 2>&1
RC=$?
date +%s.%N > "$OUTDIR/t_end"
"$PERF" report -i "$OUTDIR/perf.data" --stats 2>/dev/null | grep -E "THROTTLE|SAMPLE events|LOST" > "$OUTDIR/perf_stats.txt" || true
rm -rf "$WORK/repo"
echo $RC > "$OUTDIR/rc"
echo "== $IID $RUN_ID rc=$RC"
