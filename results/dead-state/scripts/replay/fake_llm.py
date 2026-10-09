#!/usr/bin/env python3
"""A fake OpenAI chat-completions endpoint that replays a recorded SWE-agent trajectory.

The harness runs unmodified (its litellm + httpx path, history processors, parser, trajectory
saving, and real tools in the real repository); only the GPU model is replaced. Request i is answered
with the i-th assistant message of the recorded history (content + tool_calls), so a deterministic
environment reproduces the recorded run step for step.

  fake_llm.py <trajectory.json> <port> [--delay S] [--log requests.ndjson]
--delay sleeps S seconds before answering (the model's think time; 0 = back-to-back steps).
The log records, per request: index, number of messages, request bytes, and whether the request's
last message matches the recorded history at that point (the fidelity check).
"""
import argparse, json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("traj"); ap.add_argument("port", type=int)
ap.add_argument("--delay", type=float, default=0.0); ap.add_argument("--log")
A = ap.parse_args()
T = json.load(open(A.traj))
H = T["history"]
ANS = [i for i, m in enumerate(H) if m["role"] == "assistant"]
lock = threading.Lock()
state = {"n": 0}
log = open(A.log, "a") if A.log else None


def content_of(m):
    c = m.get("content")
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c or ""


class H_(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        req = json.loads(body or b"{}")
        with lock:
            i = state["n"]; state["n"] += 1
        if i >= len(ANS):
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"replay exhausted"}'); return
        rec = H[ANS[i]]
        # fidelity: the request should carry exactly the recorded messages that precede this answer
        msgs = req.get("messages", [])
        match = len(msgs) == ANS[i] and content_of(msgs[-1]).strip() == content_of(H[ANS[i] - 1]).strip() if msgs else False
        if A.delay:
            time.sleep(A.delay)
        msg = {"role": "assistant", "content": rec.get("content") or ""}
        if rec.get("tool_calls"):
            msg["tool_calls"] = [{"id": c["id"], "type": "function", "function": c["function"]} for c in rec["tool_calls"]]
        out = {"id": f"replay-{i}", "object": "chat.completion", "created": int(time.time()), "model": req.get("model", "replay"),
               "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if rec.get("tool_calls") else "stop"}],
               "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        if log:
            log.write(json.dumps({"i": i, "n_msgs": len(msgs), "expected_msgs": ANS[i], "req_bytes": len(body),
                                  "match": match, "t": time.time()}) + "\n"); log.flush()

    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"data":[{"id":"replay"}]}')


print(f"replaying {len(ANS)} responses on :{A.port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", A.port), H_).serve_forever()
