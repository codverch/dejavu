#!/usr/bin/env bash
# run_replay.sh <out_dir> <port> [delay_s] [wrapper...]: re-run SWE-agent on django-11333 with the
# recorded config, the model replaced by fake_llm.py replaying the recorded responses. Everything
# after the delay is a command prefix for the harness (e.g. perf stat ..., or drrun ... --).
set -uo pipefail
D=/localdisk/deepanjm/agentic-core
TRAJ=$D/dsx_runs/req/run01/trajectory.django__django-11333.json
HERE=/home/deepanjm/dejavu-wt/dead-state/results/dead-state/scripts/replay
out=$(realpath -m $1); port=$2; delay=${3:-0}; shift 3 || shift $#
mkdir -p $out
python3 - "$TRAJ" "$out/config.json" "$port" "$out" <<'PY'
import json, sys
t = json.load(open(sys.argv[1])); rc = t["replay_config"]; rc = json.loads(rc) if isinstance(rc, str) else rc
rc["agent"]["model"]["api_base"] = f"http://127.0.0.1:{sys.argv[3]}/v1"
rc["agent"]["model"]["api_key"] = "local-vllm-key"
rc["agent"]["model"]["retry"] = {"retries": 0, "min_wait": 1.0, "max_wait": 1.0}
rc["agent"]["model"]["completion_kwargs"] = {}
rc["output_dir"] = sys.argv[4] + "/traj"
json.dump(rc, open(sys.argv[2], "w"), indent=1)
PY
python3 $HERE/fake_llm.py $TRAJ $port --delay $delay --log $out/requests.ndjson > $out/fake_llm.log 2>&1 &
FAKE=$!
sleep 1
export OPENAI_API_KEY=local-vllm-key PATH=$D/swe-agent-venv/bin:$PATH PYTHONPATH=$HERE PHASE_LOG=$out/phases.log OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
# private repo clone at the path the trajectory uses, and private /root/tools, in a private mount ns
R=/localdisk/deepanjm/deadblock/replay/repo
[ -d $R/.git ] || git clone -q $D/repos/django__django-11333 $R
git -C $R checkout -q -f 55b68de643b5c2d5f0a8ea7587ab3b2966021ccc && git -C $R clean -qfdx
mkdir -p /root/tools $out/roottools
cd $D/SWE-agent
t0=$(date +%s.%N)
unshare -m --propagation private bash -c "mount --bind $R /django__django-11333 && mount --bind $out/roottools /root/tools && \
  exec $* $D/swe-agent-venv/bin/python3 -c \"import phasewrap; phasewrap.main()\" run --config $out/config.json" > $out/sweagent.log 2>&1
echo "rc=$? wall=$(echo "$(date +%s.%N) - $t0" | bc)" > $out/rc
kill $FAKE
python3 $HERE/check_replay.py $TRAJ $out > $out/fidelity.txt 2>&1
cat $out/rc $out/fidelity.txt
