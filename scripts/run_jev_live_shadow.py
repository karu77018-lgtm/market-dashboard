#!/usr/bin/env python3
"""Run bounded, point-in-time Jev shadow evaluations for current MC57 names.

The script deliberately keeps vendor text out of Git and Actions artifacts.  It
fetches news up to the dashboard's generated_at cutoff, submits a compact state
to the private Jev API, and writes only an audit summary (IDs, counts, hashes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


MASSIVE_NEWS_URL = "https://api.massive.com/v2/reference/news"
DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"
QUESTION_SET_VERSION = "jev-text-v1"
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
EVALUATION_PATTERN = re.compile(r"^Evaluation:\s*#([^\s]+)\s*$", re.MULTILINE)
COST_PATTERN = re.compile(r"^Cost:\s*\$([0-9.]+)\s*$", re.MULTILINE)


class ShadowRunError(RuntimeError):
    """A safe-to-log shadow runner failure."""


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ShadowRunError(f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowRunError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ShadowRunError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def embedded_json(html: str, variable: str) -> Any:
    marker = f"window.{variable}="
    offset = html.find(marker)
    if offset < 0:
        raise ShadowRunError(f"{marker} was not found in the dashboard")
    try:
        value, _ = json.JSONDecoder().raw_decode(html[offset + len(marker):])
    except json.JSONDecodeError as exc:
        raise ShadowRunError(f"{marker} is not valid JSON") from exc
    return value


def load_dashboard(path: Path, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    html = path.read_text(encoding="utf-8")
    calc = embedded_json(html, "CALC")
    details = embedded_json(html, "DET")
    if not isinstance(calc, dict) or not isinstance(calc.get("names"), list):
        raise ShadowRunError("window.CALC.names is missing")
    if not isinstance(details, dict):
        details = {}

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered = sorted(
        (row for row in calc["names"] if isinstance(row, dict)),
        key=lambda row: (int(row.get("rk") or 10_000), str(row.get("t") or "")),
    )
    for row in ordered:
        ticker = str(row.get("t") or "").strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker) or ticker in seen:
            continue
        seen.add(ticker)
        candidates.append({"ticker": ticker, "selection": row, "detail": details.get(ticker) or {}})
        if len(candidates) >= limit:
            break
    if not candidates:
        raise ShadowRunError("dashboard contains no valid MC57 candidates")
    return candidates, calc


def load_company_names(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        if TICKER_PATTERN.fullmatch(ticker) and name:
            result[ticker] = name[:300]
    return result


def safe_number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def request_json(
    client: requests.Session,
    url: str,
    *,
    params: dict[str, Any],
    timeout: int,
    attempts: int = 3,
) -> dict[str, Any]:
    last_status: int | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params, timeout=timeout)
            last_status = response.status_code
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                    time.sleep(min(max(delay, 1.0), 30.0))
                    continue
            if 400 <= response.status_code < 500:
                raise ShadowRunError(
                    f"Massive news request was rejected (status={response.status_code})"
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ShadowRunError("Massive news response is not an object")
            return payload
        except (requests.RequestException, ValueError) as exc:
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            kind = type(exc).__name__
            raise ShadowRunError(f"Massive news request failed ({kind}, status={last_status})") from None
    raise ShadowRunError(f"Massive news request failed (status={last_status})")


def normalize_news(
    rows: Any,
    *,
    ticker: str,
    start: datetime,
    cutoff: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    documents: list[tuple[datetime, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            published = parse_timestamp(row.get("published_utc"), field="published_utc")
        except ShadowRunError:
            continue
        if published < start or published > cutoff:
            continue
        mentioned = {str(item).upper() for item in (row.get("tickers") or []) if isinstance(item, str)}
        if mentioned and ticker not in mentioned:
            continue
        title = " ".join(str(row.get("title") or "").split())[:500]
        if not title:
            continue
        description = " ".join(str(row.get("description") or "").split())[:2000]
        url = str(row.get("article_url") or "").strip()[:1000]
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        publisher = row.get("publisher") if isinstance(row.get("publisher"), dict) else {}
        document = {
            "source": "massive_news",
            "published_utc": utc_iso(published),
            "title": title,
            "description": description,
            "publisher": str(publisher.get("name") or "")[:200],
            "article_url": url,
        }
        documents.append((published, document))
    documents.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in documents[:limit]]


def fetch_news(
    client: requests.Session,
    *,
    ticker: str,
    api_key: str,
    start: datetime,
    cutoff: datetime,
    limit: int,
    timeout: int,
) -> list[dict[str, Any]]:
    payload = request_json(
        client,
        MASSIVE_NEWS_URL,
        params={
            "ticker": ticker,
            "published_utc.gte": utc_iso(start),
            "published_utc.lte": utc_iso(cutoff),
            "sort": "published_utc",
            "order": "desc",
            "limit": limit,
            "apiKey": api_key,
        },
        timeout=timeout,
    )
    return normalize_news(
        payload.get("results"), ticker=ticker, start=start, cutoff=cutoff, limit=limit
    )


def candidate_state(
    candidate: dict[str, Any],
    *,
    company_name: str | None,
    documents: list[dict[str, Any]],
    manifest: dict[str, Any],
    calc: dict[str, Any],
    cutoff: datetime,
    lookback_days: int,
) -> dict[str, Any]:
    selection = candidate["selection"]
    detail = candidate["detail"] if isinstance(candidate["detail"], dict) else {}
    return {
        "schema_version": "jev-live-shadow-v1",
        "ticker": candidate["ticker"],
        "company_name": company_name,
        "session_date": manifest.get("session_date"),
        "available_at": utc_iso(cutoff),
        "selection": {
            "mc57_rank": safe_number(selection.get("rk")),
            "rs189_percentile": safe_number(selection.get("rs")),
            "price": safe_number(selection.get("px")),
            "return_5d_pct": safe_number(selection.get("r5")),
            "distance_from_52w_high_pct": safe_number(selection.get("d52")),
        },
        "dashboard_context": {
            "mc57": safe_number(manifest.get("mc57")),
            "mc57_status": manifest.get("mc57_status"),
            "nqsar_status": manifest.get("nqsar_status"),
            "market_color": calc.get("color"),
            "sector": detail.get("sec"),
            "subtheme": detail.get("sth"),
            "market_cap_band": detail.get("cap"),
        },
        "evidence": {
            "source": "Massive news API",
            "lookback_days": lookback_days,
            "cutoff_inclusive": utc_iso(cutoff),
            "documents": documents,
        },
        "instructions": (
            "Treat only the supplied documents as textual evidence. Do not infer that an event is "
            "absent merely because it is not mentioned. Dashboard metrics are context, not textual "
            "proof of a catalyst or red flag."
        ),
    }


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_jev_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        return value
    raise ShadowRunError("JEV_API_URL must be HTTPS (or localhost for tests)")


def evaluate_jev(
    client: requests.Session,
    *,
    url: str,
    secret: str,
    ticker: str,
    state: dict[str, Any],
    cutoff: datetime,
    timeout: int,
    attempts: int = 3,
) -> dict[str, Any]:
    body = {
        "state": state,
        "runs": 3,
        "persist": True,
        "ticker": ticker,
        "questionSetVersion": QUESTION_SET_VERSION,
        "asofTimestamp": utc_iso(cutoff),
        "evaluationKind": "live",
        "validationEligible": False,
        "responseMode": "summary",
    }
    last_status: int | None = None
    for attempt in range(attempts):
        try:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {secret}"},
                json=body,
                timeout=timeout,
            )
            last_status = response.status_code
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 10))
                    continue
            if response.status_code != 200:
                raise ShadowRunError(f"Jev rejected {ticker} (status={response.status_code})")
            evaluation = EVALUATION_PATTERN.search(response.text)
            if not evaluation:
                raise ShadowRunError(f"Jev response for {ticker} omitted the evaluation id")
            cost = COST_PATTERN.search(response.text)
            return {
                "evaluation_id": evaluation.group(1),
                "duplicate": response.text.startswith("Jev DUPLICATE"),
                "gateway_cost_usd": float(cost.group(1)) if cost else None,
            }
        except ShadowRunError:
            raise
        except requests.RequestException as exc:
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            raise ShadowRunError(
                f"Jev request for {ticker} failed ({type(exc).__name__}, status={last_status})"
            ) from None
    raise ShadowRunError(f"Jev request for {ticker} failed (status={last_status})")


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def append_actions_summary(payload: dict[str, Any]) -> None:
    path_value = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path_value:
        return
    status = payload.get("status", "unknown")
    lines = [
        "## Jev live shadow",
        "",
        f"- Status: `{status}`",
        f"- Session: `{payload.get('session_date') or '-'}`",
        f"- Evidence cutoff: `{payload.get('available_at') or '-'}`",
        f"- Selected: {payload.get('selected_count', 0)}",
        f"- Evaluated: {payload.get('evaluated_count', 0)}",
        f"- Skipped without recent news: {payload.get('skipped_no_news_count', 0)}",
        f"- Errors: {payload.get('error_count', 0)}",
        "- Mode: Shadow only; not validation-eligible and never a trade order.",
        "",
    ]
    with Path(path_value).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily Jev shadow evaluations")
    parser.add_argument("--root", default=".")
    parser.add_argument("--dashboard", default="source-mc57.html")
    parser.add_argument("--manifest", default="latest-manifest.json")
    parser.add_argument("--reference", default="work/massive-reference.json")
    parser.add_argument("--output", default=".preservation/jev/live-shadow-summary.json")
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--max-news", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--provider-timeout", type=int, default=45)
    parser.add_argument("--jev-timeout", type=int, default=180)
    args = parser.parse_args()

    if not 1 <= args.max_candidates <= 25:
        parser.error("--max-candidates must be between 1 and 25")
    if not 1 <= args.max_news <= 50:
        parser.error("--max-news must be between 1 and 50")
    if not 1 <= args.lookback_days <= 90:
        parser.error("--lookback-days must be between 1 and 90")

    root = Path(args.root).resolve()
    output_path = root / args.output
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ShadowRunError("manifest must be a JSON object")
    cutoff = parse_timestamp(manifest.get("generated_at"), field="manifest.generated_at")
    candidates, calc = load_dashboard(root / args.dashboard, args.max_candidates)
    company_names = load_company_names(root / args.reference)

    summary: dict[str, Any] = {
        "schema_version": "jev-live-shadow-summary-v1",
        "status": "started",
        "session_date": manifest.get("session_date"),
        "available_at": utc_iso(cutoff),
        "question_set_version": QUESTION_SET_VERSION,
        "evaluation_kind": "live",
        "validation_eligible": False,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "code_sha": os.environ.get("GITHUB_SHA"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "selected_count": len(candidates),
        "evaluated_count": 0,
        "skipped_no_news_count": 0,
        "error_count": 0,
        "results": [],
    }

    massive_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    jev_secret = os.environ.get("JEV_API_SECRET", "").strip()
    if not massive_key or not jev_secret:
        missing = [
            name for name, value in (("MASSIVE_API_KEY", massive_key), ("JEV_API_SECRET", jev_secret))
            if not value
        ]
        summary["status"] = "configuration_missing"
        summary["missing"] = missing
        write_summary(output_path, summary)
        append_actions_summary(summary)
        print(f"::warning title=Jev live shadow not configured::Missing {', '.join(missing)}")
        return 1

    jev_url = validate_jev_url(os.environ.get("JEV_API_URL", DEFAULT_JEV_URL).strip())
    start = cutoff - timedelta(days=args.lookback_days)
    summary["news_window_start"] = utc_iso(start)
    news_client = requests.Session()
    jev_client = requests.Session()

    for candidate in candidates:
        ticker = candidate["ticker"]
        rank = candidate["selection"].get("rk")
        try:
            documents = fetch_news(
                news_client,
                ticker=ticker,
                api_key=massive_key,
                start=start,
                cutoff=cutoff,
                limit=args.max_news,
                timeout=args.provider_timeout,
            )
            if not documents:
                summary["skipped_no_news_count"] += 1
                summary["results"].append(
                    {"ticker": ticker, "mc57_rank": rank, "status": "skipped_no_news"}
                )
                print(f"Jev shadow {ticker}: skipped (no news before cutoff)")
                continue
            state = candidate_state(
                candidate,
                company_name=company_names.get(ticker),
                documents=documents,
                manifest=manifest,
                calc=calc,
                cutoff=cutoff,
                lookback_days=args.lookback_days,
            )
            state_hash = canonical_hash(state)
            result = evaluate_jev(
                jev_client,
                url=jev_url,
                secret=jev_secret,
                ticker=ticker,
                state=state,
                cutoff=cutoff,
                timeout=args.jev_timeout,
            )
            summary["evaluated_count"] += 1
            summary["results"].append(
                {
                    "ticker": ticker,
                    "mc57_rank": rank,
                    "status": "duplicate" if result["duplicate"] else "evaluated",
                    "news_count": len(documents),
                    "state_sha256": state_hash,
                    "evaluation_id": result["evaluation_id"],
                    "gateway_cost_usd": result["gateway_cost_usd"],
                }
            )
            suffix = "duplicate" if result["duplicate"] else "saved"
            print(f"Jev shadow {ticker}: {suffix} evaluation #{result['evaluation_id']}")
        except Exception as exc:
            safe_error = exc if isinstance(exc, ShadowRunError) else ShadowRunError(type(exc).__name__)
            summary["error_count"] += 1
            summary["results"].append(
                {"ticker": ticker, "mc57_rank": rank, "status": "error", "error": str(safe_error)}
            )
            print(f"::warning title=Jev shadow {ticker} failed::{safe_error}")

    summary["status"] = "partial" if summary["error_count"] else "success"
    write_summary(output_path, summary)
    append_actions_summary(summary)
    print(
        "Jev live shadow complete: "
        f"evaluated={summary['evaluated_count']} "
        f"skipped={summary['skipped_no_news_count']} errors={summary['error_count']}"
    )
    return 1 if summary["error_count"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShadowRunError as exc:
        print(f"::error title=Jev live shadow failed::{exc}")
        raise SystemExit(2)
