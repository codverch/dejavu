#!/usr/bin/env python3
"""Fidelity of a replay: does every step reproduce the recorded action and observation?
  check_replay.py <recorded trajectory.json> <replay out dir>"""
import glob, json, sys
rec = json.load(open(sys.argv[1]))["trajectory"]
f = glob.glob(f"{sys.argv[2]}/traj/**/*.traj", recursive=True)
if not f:
    sys.exit("no replay .traj found")
rep = json.load(open(f[0]))["trajectory"]
req = [json.loads(l) for l in open(f"{sys.argv[2]}/requests.ndjson")]
print(f"steps recorded {len(rec)} replayed {len(rep)}; requests {len(req)}, request-history match {sum(r['match'] for r in req)}/{len(req)}")
same_a = sum(a["action"] == b["action"] for a, b in zip(rec, rep))
same_o = sum(a["observation"].strip() == b["observation"].strip() for a, b in zip(rec, rep))
print(f"identical actions {same_a}/{min(len(rec), len(rep))}, identical observations {same_o}/{min(len(rec), len(rep))}")
for k, (a, b) in enumerate(zip(rec, rep)):
    if a["observation"].strip() != b["observation"].strip():
        print(f"  step {k}: {a['action'][:70]!r}\n    rec {a['observation'][:120]!r}\n    rep {b['observation'][:120]!r}")
