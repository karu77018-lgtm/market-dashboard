#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

import requests

root = Path(__file__).resolve().parents[1]
qset = json.loads((root / "research/expectation_gap/question-set-en-v2.json").read_text())
url = os.getenv("JEV_API_URL", "https://jev-investment-engine.vercel.app/api/jev")
secret = os.getenv("JEV_API_SECRET")
if not secret:
    raise SystemExit("JEV_API_SECRET is required")

state = {
    "ticker": "TEST",
    "as_of": "2026-10-01T00:00:00Z",
    "pre_event_context": {
        "return_20d_pct": 18.0,
        "excess_vs_qqq_20d_pct": 15.0
    },
    "company_specific_evidence": [
        "Revenue growth accelerated and operating margin improved year over year.",
        "Management raised full-year revenue guidance."
    ],
    "instructions": "Use only supplied evidence. Do not predict stock price."
}

response = requests.post(
    url,
    headers={"Authorization": f"Bearer {secret}"},
    json={
        "state": state,
        "questions": qset["questions"],
        "runs": 1,
        "persist": False,
        "responseMode": "json"
    },
    timeout=90
)

if response.status_code != 200:
    print(response.text[:1000], file=sys.stderr)
    raise SystemExit(f"Jev smoke failed: HTTP {response.status_code}")

payload = response.json()
aggregate = payload.get("aggregate")
expected = set(qset["questions"])
actual = set(aggregate or {})
if expected != actual:
    raise SystemExit(f"Jev smoke incomplete: expected={len(expected)} actual={len(actual)}")

print(json.dumps({
    "ok": True,
    "question_set": qset["version"],
    "question_count": len(actual),
    "duration_ms": payload.get("durationMs"),
    "gateway_cost_usd": payload.get("gatewayCostUsd")
}, indent=2))
