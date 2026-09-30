#!/usr/bin/env python3
"""Build a point-in-time earnings Jev semantic overlay from SEC exhibits.

This script ONLY extracts semantic features. It does not calculate performance,
fit thresholds, rank outcomes, or run any backtest.

For each frozen earnings event:
1) fetch the public SEC full-submission text from the event's filing_url;
2) extract the earnings release exhibit (prefer EX-99.1 / EX-99);
3) send pre-event market context + event text to Jev v2;
4) persist derived probabilities/classes and hashes only.

Backtests are intentionally local-only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_jev_live_shadow import ShadowRunError, safe_number

DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"
SEC_UA = "market-dashboard-research/1.0 karu77018-lgtm@users.noreply.github.com"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def strip_markup(text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def extract_document_blocks(submission: str) -> list[dict[str, str]]:
    blocks = []
    for m in re.finditer(r"(?is)<DOCUMENT>(.*?)</DOCUMENT>", submission):
        block = m.group(1)
        def tag(name: str) -> str:
            mm = re.search(rf"(?im)^<{name}>\s*(.+)$", block)
            return mm.group(1).strip() if mm else ""
        text_match = re.search(r"(?is)<TEXT>(.*)</TEXT>", block)
        body = text_match.group(1) if text_match else block
        blocks.append(
            {
                "type": tag("TYPE"),
                "sequence": tag("SEQUENCE"),
                "filename": tag("FILENAME"),
                "description": tag("DESCRIPTION"),
                "text": strip_markup(body),
            }
        )
    return blocks


def choose_earnings_text(submission: str) -> tuple[str, str]:
    blocks = extract_document_blocks(submission)
    preferred = []
    for block in blocks:
        typ = block["type"].upper()
        desc = block["description"].lower()
        fn = block["filename"].lower()
        score = 0
        if typ in {"EX-99.1", "EX-99", "EX-99.01"}:
            score += 100
        elif typ.startswith("EX-99"):
            score += 80
        if "earn" in desc or "result" in desc or "press release" in desc:
            score += 30
        if "99" in fn:
            score += 5
        if score:
            preferred.append((score, block))
    if preferred:
        preferred.sort(key=lambda x: (-x[0], x[1]["sequence"]))
        b = preferred[0][1]
        return b["text"][:14000], f"{b['type']}:{b['filename'] or b['description']}"
    for block in blocks:
        if block["type"].upper().startswith("8-K"):
            return block["text"][:14000], "8-K-fallback"
    return strip_markup(submission)[:14000], "submission-fallback"


def fetch_sec_submission(
    session: requests.Session,
    url: str,
    *,
    min_interval: float,
    timeout: int = 30,
) -> tuple[str, str]:
    last_at = getattr(fetch_sec_submission, "_last_at", 0.0)
    wait = min_interval - (time.monotonic() - last_at)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            response = session.get(
                url,
                headers={
                    "User-Agent": SEC_UA,
                    "Accept-Encoding": "gzip, deflate",
                    "Host": "www.sec.gov",
                },
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt < 3:
                time.sleep(1 + attempt)
                continue
            raise ShadowRunError(f"SEC fetch failed: {type(exc).__name__}") from None
        setattr(fetch_sec_submission, "_last_at", time.monotonic())
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
            time.sleep(2 ** attempt)
            continue
        if response.status_code != 200:
            raise ShadowRunError(f"SEC HTTP {response.status_code}")
        return choose_earnings_text(response.text)
    raise ShadowRunError("SEC fetch failed after retries")


def evaluate_jev(
    session: requests.Session,
    url: str,
    secret: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    response = session.post(
        url,
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "state": state,
            "questions": questions,
            "runs": 1,
            "persist": False,
            "responseMode": "json",
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise ShadowRunError(f"Jev HTTP {response.status_code}: {response.text[:300]}")
    payload = response.json()
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ShadowRunError("Jev aggregate missing")
    return {
        "aggregate": aggregate,
        "duration_ms": safe_number(payload.get("durationMs")),
        "gateway_cost_usd": _finite(payload.get("gatewayCostUsd")),
    }


def prob(aggregate: dict[str, Any], qid: str) -> float | None:
    row = aggregate.get(qid)
    return _finite(row.get("probabilityMean")) if isinstance(row, dict) else None


def choice(aggregate: dict[str, Any], qid: str) -> str | None:
    row = aggregate.get(qid)
    value = row.get("majorityChoice") if isinstance(row, dict) else None
    return str(value) if value is not None else None


def choice_probability(
    aggregate: dict[str, Any], qid: str, option: str
) -> float | None:
    row = aggregate.get(qid)
    dist = row.get("choiceDistribution") if isinstance(row, dict) else None
    return _finite(dist.get(option)) if isinstance(dist, dict) else None


def derived(aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_business_change": prob(aggregate, "JEV01_material_business_change"),
        "persistent_change": prob(aggregate, "JEV02_persistent_change"),
        "information_novelty": prob(aggregate, "JEV03_information_novelty"),
        "surprise_class": choice(aggregate, "JEV04_surprise_vs_prior_expectations"),
        "positive_surprise_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "positive_surprise"
        ),
        "negative_surprise_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "negative_surprise"
        ),
        "broadly_expected_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "broadly_expected"
        ),
        "evidence_quality": choice(aggregate, "JEV05_evidence_quality"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument(
        "--events",
        default="research/event_risk/earnings-expectation-load-core-v1.json",
    )
    ap.add_argument(
        "--questions",
        default="research/expectation_gap/question-set-en-v2.json",
    )
    ap.add_argument(
        "--output",
        default="research/event_risk/earnings-jev-overlay-v1.json",
    )
    ap.add_argument("--start-date", default="2026-09-01")
    ap.add_argument("--end-date", default="2026-09-30")
    ap.add_argument("--sec-min-interval", type=float, default=0.15)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    jev_secret = os.getenv("JEV_API_SECRET")
    jev_url = os.getenv("JEV_API_URL") or DEFAULT_JEV_URL
    if not jev_secret:
        raise SystemExit("JEV_API_SECRET is required")

    event_payload = json.loads((root / args.events).read_text(encoding="utf-8"))
    rows = [
        r for r in event_payload.get("rows", [])
        if isinstance(r, dict)
        and r.get("ticker")
        and r.get("filing_date")
        and r.get("accession_number")
        and args.start_date <= str(r.get("filing_date")) <= args.end_date
        and str(r.get("filing_url") or "").startswith("https://www.sec.gov/")
    ]
    if not rows:
        raise SystemExit("No earnings event rows with SEC filing URLs")

    qset = json.loads((root / args.questions).read_text(encoding="utf-8"))
    questions = qset.get("questions")
    if not isinstance(questions, dict) or len(questions) != 5:
        raise SystemExit("Expected five Jev v2 questions")

    sec = requests.Session()
    jev = requests.Session()
    outputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    cost = 0.0

    for i, row in enumerate(rows, 1):
        ticker = str(row["ticker"]).upper()
        filing_date = str(row["filing_date"])
        accession = str(row["accession_number"])
        try:
            event_text, source = fetch_sec_submission(
                sec,
                str(row["filing_url"]),
                min_interval=args.sec_min_interval,
            )
            state = {
                "schema_version": "earnings-jev-overlay-state-v1",
                "ticker": ticker,
                "event_date": filing_date,
                "pre_event_market_context": {
                    "pre20_return_pct": row.get("pre20_return_pct"),
                    "pre20_excess_qqq_pct": row.get("pre20_excess_qqq_pct"),
                    "rs63_change_20d": row.get("rs63_change_20d"),
                    "distance_to_63d_high_pct": row.get("dist_high63_pct"),
                },
                "company_specific_evidence": {
                    "sec_source": source,
                    "earnings_release_text": event_text,
                },
                "instructions": [
                    "Use only the supplied evidence.",
                    "The market metrics are prior-expectation context, not proof of business quality.",
                    "Do not predict the stock price or use any post-event return.",
                    "If the filing does not contain actual operating information, mark evidence quality weak or insufficient.",
                ],
            }
            result = evaluate_jev(
                jev, jev_url, jev_secret, state, questions, args.timeout
            )
            cost += result.get("gateway_cost_usd") or 0.0
            outputs.append(
                {
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "state_sha256": canonical_hash(state),
                    "sec_evidence_source": source,
                    "sec_evidence_chars": len(event_text),
                    "jev": derived(result["aggregate"]),
                    "duration_ms": result.get("duration_ms"),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        if i % 25 == 0:
            print(
                json.dumps(
                    {
                        "processed": i,
                        "success": len(outputs),
                        "errors": len(errors),
                    }
                ),
                flush=True,
            )

    payload = {
        "version": "earnings-jev-overlay-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_set_version": qset.get("version"),
        "runs_per_event": 1,
        "event_count": len(rows),
        "jev_success_count": len(outputs),
        "jev_error_count": len(errors),
        "gateway_cost_usd": round(cost, 8),
        "evidence_source": "SEC full-submission text; prefer EX-99.1 / EX-99 earnings release exhibit",
        "privacy": {
            "sec_text_persisted": False,
            "raw_jev_runs_persisted": False,
        },
        "rows": outputs,
        "errors": errors,
    }
    path = root / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "event_count": len(rows),
                "jev_success_count": len(outputs),
                "jev_error_count": len(errors),
                "gateway_cost_usd": payload["gateway_cost_usd"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
