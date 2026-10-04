#!/usr/bin/env python3
"""Point-in-time narrative backfill for turnaround-stage events (research only).

For every event in research/jev-backfill-events-v1.json:
  1. fetch Massive news for the ticker published up to the event close
     (one request per event, 120-day window), keeping vendor text in memory only;
  2. derive Jev-free news features (counts, surge, keyword groups, publishers);
  3. ask Jev (question set jev-text-v1, 3 runs, evaluationKind=backfill,
     validationEligible=false) twice: with the company identity masked and as is.
     The masked run limits the model's chance of recognising a company it may
     know the future of; the gap between the two is a look-ahead check.
Only derived numbers are written (to an Actions artifact).  No outcome labels are
sent anywhere: the events file contains inputs only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from run_jev_live_shadow import (DEFAULT_JEV_URL, MASSIVE_NEWS_URL, POSITIVE_QUESTIONS, QUESTION_SET_VERSION,
                                 RISK_QUESTIONS, ShadowRunError, _question_probability, canonical_hash,
                                 parse_timestamp, request_json, utc_iso, validate_jev_url)

LOOKBACK_DAYS = 30
HISTORY_DAYS = 120
MAX_DOCS = 8
MAX_NEWS_PAGES = 10
CUTOFF_RULE = "nyse-close-v2"  # actual NYSE close in New York time (13:00 on early-close days)
NEW_YORK = ZoneInfo("America/New_York")


from market_calendar import early_close, session_close_utc  # noqa: E402,F401  (shared NYSE calendar)


KEYWORDS = {
    "guidance_up": r"(rais|boost|lift|hik|increas)\w* (its |full[- ]year |fy\d* |annual |\d{4} )?(guidance|outlook|forecast)|guidance (raise|hike)|above[- ]consensus guidance",
    "beat": r"\bbeats?\b|tops? (estimates|expectations|forecasts)|better[- ]than[- ]expected|record (revenue|quarter|sales|results)",
    "contract": r"\bcontracts?\b|\bawarded?\b|\bpartnership\b|\bagreement\b|\bdeal\b|\bbacklog\b|\bwins?\b .*\border",
    "theme": r"\bAI\b|artificial intelligence|data ?center|\bGPU|\bnuclear\b|\bquantum\b|\bcrypto|\bbitcoin\b|\bdefen[cs]e\b|\bdrone",
    "upgrade": r"\bupgrades?d?\b|raises? (its )?price target|price target (raised|hike|boost)|initiat\w+ .*\b(buy|outperform|overweight)",
    "approval": r"\bFDA\b|\bapprov(al|ed|es)\b|\bclearance\b",
    "negative": r"\bdowngrade|\bmiss(es|ed)?\b|cuts? (its )?(guidance|outlook|forecast)|lawsuit|investigation|\boffering\b|dilut|plunge|tumble|sinks?\b",
}
SUFFIX = re.compile(r"[,.]?\s+(inc|incorporated|corp|corporation|co|company|holdings?|group|ltd|limited|plc|n\.?v|s\.?a|ag|se|class [a-c]|common stock|ordinary shares|adr|ads)\.?$", re.I)


def name_variants(name: str | None) -> list[str]:
    if not name:
        return []
    out, cur = set(), name.strip()
    out.add(cur)
    for _ in range(3):
        new = SUFFIX.sub("", cur).strip(" ,.")
        if new == cur:
            break
        cur = new
        out.add(cur)
    words = cur.split()
    if len(words) > 1 and len(words[0]) >= 4:
        out.add(words[0])
    return sorted((v for v in out if len(v) >= 3), key=len, reverse=True)


def mask_text(text: str, ticker: str, names: list[str]) -> str:
    t = re.sub(rf"(\$|\b){re.escape(ticker)}\b", "XXXX", text)
    for n in names:
        t = re.sub(rf"\b{re.escape(n)}\b", "the Company", t, flags=re.I)
    return t


def fetch_history(client, *, ticker: str, api_key: str, cutoff: datetime, timeout: int,
                  max_pages: int = MAX_NEWS_PAGES) -> tuple[list[dict[str, Any]], bool]:
    """All news in the window (following next_url), and whether it was truncated."""
    start = cutoff - timedelta(days=HISTORY_DAYS)
    params: dict[str, Any] | None = {
        "ticker": ticker, "published_utc.gte": utc_iso(start), "published_utc.lte": utc_iso(cutoff),
        "sort": "published_utc", "order": "desc", "limit": 1000, "apiKey": api_key}
    url, raw, truncated = MASSIVE_NEWS_URL, [], False
    for page in range(max_pages):
        payload = request_json(client, url, params=params, timeout=timeout)
        raw.extend(payload.get("results") or [])
        next_url = payload.get("next_url")
        if not next_url:
            break
        parsed = urlparse(str(next_url))
        if parsed.scheme != "https" or parsed.netloc != "api.massive.com" or not parsed.path.startswith("/v2/reference/news"):
            raise ShadowRunError("Massive news pagination returned an unexpected URL")
        if page + 1 >= max_pages:
            truncated = True
            break
        url, params = str(next_url), {"apiKey": api_key}
    docs, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            published = parse_timestamp(row.get("published_utc"), field="published_utc")
        except ShadowRunError:
            continue
        if published > cutoff or published < start:
            continue
        title = " ".join(str(row.get("title") or "").split())[:500]
        if not title or title in seen:
            continue
        seen.add(title)
        pub = row.get("publisher") if isinstance(row.get("publisher"), dict) else {}
        docs.append({"published": published, "title": title,
                     "description": " ".join(str(row.get("description") or "").split())[:2000],
                     "publisher": str(pub.get("name") or "")[:200],
                     "n_tickers": len(row.get("tickers") or [])})
    docs.sort(key=lambda d: d["published"], reverse=True)
    return docs, truncated


def news_features(docs: list[dict[str, Any]], cutoff: datetime, truncated: bool = False) -> dict[str, Any]:
    recent = [d for d in docs if d["published"] >= cutoff - timedelta(days=LOOKBACK_DAYS)]
    prior = [d for d in docs if d["published"] < cutoff - timedelta(days=LOOKBACK_DAYS)]
    feats: dict[str, Any] = {"n30": len(recent), "n_prior90": len(prior),
                             # an incomplete older window would inflate the surge: never guess it
                             "surge": None if truncated else round(len(recent) / (len(prior) / 3 + 1), 4),
                             "truncated": truncated,
                             "publishers30": len({d["publisher"] for d in recent}),
                             "solo30": sum(d["n_tickers"] <= 2 for d in recent)}
    for k, pat in KEYWORDS.items():
        rx = re.compile(pat, re.I)
        feats[f"kw_{k}"] = sum(bool(rx.search(d["title"] + " " + d["description"])) for d in recent)
    return feats


def build_state(ev: dict[str, Any], docs: list[dict[str, Any]], cutoff: datetime, masked: bool) -> dict[str, Any]:
    names = name_variants(ev.get("company_name"))
    recent = [d for d in docs if d["published"] >= cutoff - timedelta(days=LOOKBACK_DAYS)][:MAX_DOCS]
    clean = (lambda s: mask_text(s, ev["ticker"], names)) if masked else (lambda s: s)
    documents = [{"source": "massive_news", "published_utc": utc_iso(d["published"]), "title": clean(d["title"]),
                  "description": clean(d["description"]), "publisher": d["publisher"]} for d in recent]
    return {
        "schema_version": "jev-backfill-v1",
        "ticker": "XXXX" if masked else ev["ticker"],
        "company_name": None if masked else ev.get("company_name"),
        "session_date": ev["session_date"],
        "available_at": utc_iso(cutoff),
        "selection": {"candidate_sources": ["転換初動"], "rs21_percentile": ev["rs21"], "rs63_percentile": ev["rs63"],
                      "rs189_percentile": ev["rs189"], "price": None if masked else ev["price"],
                      "return_5d_pct": ev["return_5d_pct"], "distance_from_52w_high_pct": ev["distance_from_52w_high_pct"]},
        "evidence": {"source": "Massive news API", "lookback_days": LOOKBACK_DAYS,
                     "cutoff_inclusive": utc_iso(cutoff), "documents": documents},
        "instructions": ("Treat only the supplied documents as textual evidence. Do not infer that an event is absent "
                         "merely because it is not mentioned. Metrics are context, not textual proof of a catalyst or "
                         "red flag." + (" The company identity is intentionally masked." if masked else "")),
    }


def call_jev(client, url: str, secret: str, ticker: str, state: dict[str, Any], cutoff: datetime,
             timeout: int, attempts: int = 4) -> dict[str, Any]:
    body = {"state": state, "runs": 3, "persist": True, "ticker": ticker, "questionSetVersion": QUESTION_SET_VERSION,
            "asofTimestamp": utc_iso(cutoff), "evaluationKind": "backfill", "validationEligible": False,
            "responseMode": "json"}
    status = None
    for attempt in range(attempts):
        try:
            r = client.post(url, headers={"Authorization": f"Bearer {secret}"}, json=body, timeout=timeout)
            status = r.status_code
            if status == 429 or status >= 500:
                time.sleep(min(2 ** attempt * 3, 30))
                continue
            if status != 200:
                raise ShadowRunError(f"Jev rejected {ticker} (status={status})")
            p = r.json()
            agg = p.get("aggregate") if isinstance(p.get("aggregate"), dict) else None
            out = {"evaluation_id": str(p.get("evaluationId")), "duplicate": p.get("duplicate") is True,
                   "cost": p.get("gatewayCostUsd")}
            if agg:
                for q in list(POSITIVE_QUESTIONS) + list(RISK_QUESTIONS):
                    out[q] = _question_probability(agg, q)
            return out
        except requests.RequestException as exc:
            time.sleep(min(2 ** attempt * 3, 30))
            status = type(exc).__name__
    raise ShadowRunError(f"Jev request for {ticker} failed (status={status})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="research/jev-backfill-events-v1.json")
    ap.add_argument("--output", default=".preservation/jev/backfill-v1.json")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10_000)
    ap.add_argument("--massive-min-interval", type=float, default=13.0)
    ap.add_argument("--variants", default="masked,plain")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    massive_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    secret = os.environ.get("JEV_API_SECRET", "").strip()
    if not massive_key or not secret:
        print("::error title=Jev backfill not configured::MASSIVE_API_KEY or JEV_API_SECRET is missing")
        return 1
    url = validate_jev_url(os.environ.get("JEV_API_URL", DEFAULT_JEV_URL).strip())
    events = json.loads(Path(args.events).read_text(encoding="utf-8"))["events"][args.start:args.start + args.limit]
    variants = [v for v in args.variants.split(",") if v in ("masked", "plain")]
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    news_client, last = requests.Session(), None
    pool = ThreadPoolExecutor(max_workers=args.workers)
    futures = []

    def jev_job(ev_id: str, variant: str, state: dict[str, Any], ticker: str, cutoff: datetime):
        try:
            res = call_jev(requests.Session(), url, secret, ticker, state, cutoff, timeout=180)
            res["state_sha256"] = canonical_hash(state)
            results[ev_id][variant] = res
        except Exception as exc:  # keep going; record a safe error string
            results[ev_id][variant] = {"error": str(exc) if isinstance(exc, ShadowRunError) else type(exc).__name__}

    def flush():
        out_path.write_text(json.dumps({"schema_version": "jev-backfill-results-v2", "cutoff_rule": CUTOFF_RULE,
                                        "question_set_version": QUESTION_SET_VERSION,
                                        "events_file": args.events, "results": results}, ensure_ascii=False, indent=1,
                                       allow_nan=False, default=str), encoding="utf-8")

    for n, ev in enumerate(events):
        # Point-in-time boundary = the session's real NYSE close (the stored asof used a
        # fixed 21:00Z, one hour late in daylight time and wrong on early closes).
        cutoff = min(parse_timestamp(ev["asof"], field="asof"), session_close_utc(ev["session_date"]))
        if last is not None:
            wait = args.massive_min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        last = time.monotonic()
        rec: dict[str, Any] = {"ticker": ev["ticker"], "asof": utc_iso(cutoff), "asof_stored": ev["asof"],
                               "cutoff_rule": CUTOFF_RULE}
        results[ev["event_id"]] = rec
        try:
            docs, truncated = fetch_history(news_client, ticker=ev["ticker"], api_key=massive_key, cutoff=cutoff, timeout=45)
        except Exception as exc:
            rec["news_error"] = str(exc) if isinstance(exc, ShadowRunError) else type(exc).__name__
            continue
        rec.update(news_features(docs, cutoff, truncated))
        if rec["n30"] == 0:
            continue
        for variant in variants:
            state = build_state(ev, docs, cutoff, masked=(variant == "masked"))
            ticker = ev["ticker"]  # the API key column stays the real ticker; the state text is masked
            futures.append(pool.submit(jev_job, ev["event_id"], variant, state, ticker, cutoff))
        if n % 25 == 0:
            flush()
            print(f"backfill progress: {n + 1}/{len(events)} events", flush=True)
    pool.shutdown(wait=True)
    flush()
    ok = sum(1 for r in results.values() for v in variants if isinstance(r.get(v), dict) and "error" not in r[v])
    err = sum(1 for r in results.values() for v in variants if isinstance(r.get(v), dict) and "error" in r[v])
    news_err = sum(1 for r in results.values() if "news_error" in r)
    truncated = sum(1 for r in results.values() if r.get("truncated"))
    missing = sum(1 for r in results.values() if r.get("n30") and any(v not in r for v in variants))
    print(f"Jev backfill complete: events={len(results)} jev_ok={ok} jev_errors={err} "
          f"news_errors={news_err} truncated_windows={truncated} unfinished={missing} cutoff_rule={CUTOFF_RULE}")
    # Any failure or unfinished evaluation makes the run unsuccessful (never a green "complete").
    return 1 if (err or news_err or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
