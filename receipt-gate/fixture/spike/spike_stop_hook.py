#!/usr/bin/env python3
"""Step-0 spike: empirically pin Stop-hook blocking semantics on the
installed Claude Code (2.1.236). Logs every invocation's stdin payload;
exits 2 with a distinctive stderr instruction on the FIRST invocation,
0 afterwards. ASCII-only output."""
import json
import os
import sys

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spike_log.jsonl")

raw = sys.stdin.read()
try:
    payload = json.loads(raw)
except Exception:
    payload = {"unparseable_raw": raw[:2000]}

prior = 0
if os.path.exists(LOG):
    with open(LOG, "r", encoding="utf-8") as f:
        prior = sum(1 for _ in f)

with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"invocation": prior + 1, "payload": payload}) + "\n")

if prior == 0:
    sys.stderr.write(
        "SPIKE-BLOCK: this stop was blocked by a Stop hook. Include the exact "
        "token RESUMED-AFTER-BLOCK in your reply, then stop again."
    )
    sys.exit(2)
sys.exit(0)
