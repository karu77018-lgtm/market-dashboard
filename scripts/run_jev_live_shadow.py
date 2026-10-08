#!/usr/bin/env python3
"""Run bounded, point-in-time Jev shadow evaluations for the Positions and Setups tabs.

Targets are every ticker listed in the Positions tab (swing 本命 / まだ入れる /
次の候補 first, then the other lists) and the Setups tab. News is limited to
articles mainly about the ticker, price recaps are dropped, and company-issued
releases are preferred over commentary.

The script deliberately keeps vendor text out of Git and Actions artifacts. It
fetches Massive news in paginated time-window batches, fans matching articles
out to the selected tickers in memory, submits compact states to the private
Jev API, writes an audit summary, and publishes only derived probabilities and
scores for the dashboard ranking.
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
POSITIVE_QUESTIONS = {
    "CAT01_guidance_raise": "上方修正",
    "CAT02_demand_acceleration": "需要加速",
    "CAT03_major_contract": "大型契約",
    "CAT04_new_product": "新製品",
    "CAT05_regulatory_approval": "承認・許認可",
    "CAT06_company_specific": "企業固有材料",
    "TXT01_management_tone_improved": "経営トーン改善",
}
RISK_QUESTIONS = {
    "RF01_dilution": "希薄化",
    "RF02_going_concern": "継続企業",
    "RF03_accounting": "会計",
    "RF04_management_change": "経営陣交代",
    "RF05_legal_regulatory": "法務・規制",
    "RF06_guidance_cut": "下方修正",
    "TXT02_margin_pressure": "利益率圧力",
}


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


SWING_CARD_ID = "mc57-swing-screener"
# New-rule candidates, in priority order.  Only these three sections of the
# Positions "スイング候補" card are evaluated as primary Jev targets; the
# archived Core 12 table and its bench are no longer used.
SWING_SECTIONS = ("本命", "まだ入れる", "次の候補")
_SWING_SECTION = re.compile(
    r'<div class="sw-sec[^"]*"><span>([^<]+)<small>.*?</span>'
    r'(?:<button class="cp" data-tk="([^"]*)")?', re.S)


def swing_candidates(html: str) -> list[tuple[str, str]]:
    """(ticker, section) from the swing card, in section and display order."""
    start = html.find(f'id="{SWING_CARD_ID}"')
    if start < 0:
        return []
    end = html.find("</section>", start)
    card = html[start:end if end > 0 else len(html)]
    found: list[tuple[str, str]] = []
    for match in _SWING_SECTION.finditer(card):
        title = match.group(1).strip()
        if title not in SWING_SECTIONS or not match.group(2):
            continue
        for ticker in match.group(2).split(","):
            found.append((ticker.strip().upper(), title))
    order = {name: i for i, name in enumerate(SWING_SECTIONS)}
    return sorted(found, key=lambda item: order[item[1]])


# Jev targets are limited to the names the user actually trades from: the
# Positions tab (t-alloc) first, then the Setups tab (t-today).  Every copy
# list (data-tk) inside those two tabs is a target; anything outside them
# (RS leaders, pick-ups, option-wall names elsewhere) is not evaluated.
TARGET_TABS = ("t-alloc", "t-today")
_TAB_START = re.compile(r'<section id="(t-[a-z0-9_-]+)"')
_COPY_LIST = re.compile(r'data-tk="([^"]*)"')
_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)
_H2_EN = re.compile(r'<span class="h2en">.*?</span>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _tab_segments(html: str) -> dict[str, str]:
    starts = [(m.start(), m.group(1)) for m in _TAB_START.finditer(html)]
    segments: dict[str, str] = {}
    for index, (offset, tab) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(html)
        segments.setdefault(tab, html[offset:end])
    return segments


def tab_candidates(html: str) -> list[tuple[str, str]]:
    """(ticker, label) for every copy list in the Positions and Setups tabs.

    The swing card's 本命 / まだ入れる / 次の候補 come first in that order; the
    other lists follow in display order, labelled by their card heading.
    """
    found: list[tuple[str, str]] = list(swing_candidates(html))
    segments = _tab_segments(html)
    for tab in TARGET_TABS:
        segment = segments.get(tab, "")
        card_start = segment.find(f'id="{SWING_CARD_ID}"')
        card_end = segment.find('<div class="card"', card_start + 1) if card_start >= 0 else -1
        if card_start >= 0 and card_end < 0:
            card_end = len(segment)
        for match in _COPY_LIST.finditer(segment):
            before = segment[:match.start()]
            if card_start <= match.start() < card_end:
                sections = list(_SWING_SECTION.finditer(segment, card_start, match.start()))
                label = sections[-1].group(1).strip() if sections else "スイング候補"
                if label in SWING_SECTIONS:
                    continue  # already added above, in priority order
            else:
                heading = list(_H2.finditer(before))
                label = _TAG.sub("", _H2_EN.sub("", heading[-1].group(1))).strip() if heading else ""
            label = label or ("Positions" if tab == "t-alloc" else "Setups")
            for ticker in match.group(1).split(","):
                ticker = ticker.strip().upper()
                if ticker:
                    found.append((ticker, label[:40]))
    return found


WALL_NEAR_SLOTS = 20
_GROUP_ORDER = {"cand": 0, "rs21": 1, "rs63": 2, "rs189": 3, "dv": 4}


def wall_near(details: dict[str, Any]) -> list[str]:
    """Tickers whose upper option wall is 0-5% above the close, study priority first."""
    near = []
    for ticker, detail in details.items():
        opt = detail.get("opt") if isinstance(detail, dict) else None
        if not isinstance(opt, dict) or not opt.get("cw"):
            continue
        cwp = opt.get("cwp")
        if isinstance(cwp, (int, float)) and 0 <= cwp <= 0.05:
            rs = detail.get("rs189") if isinstance(detail.get("rs189"), (int, float)) else 0
            near.append((_GROUP_ORDER.get(str(opt.get("grp")), 5), -float(rs), ticker))
    return [t for _, _, t in sorted(near)]


def load_dashboard(path: Path, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    html = path.read_text(encoding="utf-8")
    try:
        calc = embedded_json(html, "CALC")
    except ShadowRunError:
        calc = {}
    details = embedded_json(html, "DET")
    if not isinstance(calc, dict):
        calc = {}
    if not isinstance(details, dict):
        details = {}

    candidates: list[dict[str, Any]] = []
    by_ticker: dict[str, dict[str, Any]] = {}

    def add(ticker: str, source: str) -> None:
        ticker = ticker.strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker):
            return
        if ticker in by_ticker:
            sources = by_ticker[ticker]["sources"]
            if source not in sources:
                sources.append(source)
            return
        if len(candidates) >= limit:
            return
        detail = details.get(ticker) if isinstance(details.get(ticker), dict) else {}
        row = {
            "t": ticker,
            "rk": None,
            "rs": detail.get("rs189"),
            "px": detail.get("px"),
            "d52": detail.get("d52"),
        }
        candidate = {"ticker": ticker, "selection": row, "detail": detail, "sources": [source]}
        candidates.append(candidate)
        by_ticker[ticker] = candidate

    # Targets: only the Positions and Setups tabs (swing 本命 / まだ入れる /
    # 次の候補 first).  RS leaders, pick-ups and option-wall names elsewhere on
    # the dashboard are intentionally not evaluated.
    for ticker, source in tab_candidates(html):
        add(ticker, source)
    if not candidates:
        raise ShadowRunError("dashboard contains no valid Jev candidates")
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
    attempts: int = 5,
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


# Company-issued releases carry the events Jev is asked about (guidance,
# contracts, offerings, officer changes); they are kept first.
PRIMARY_PUBLISHERS = (
    "globenewswire", "business wire", "businesswire", "pr newswire", "prnewswire",
    "accesswire", "access newswire", "newsfile", "eqs", "cision",
)
# Price recaps and listicles contain no company event, only restated prices.
LOW_SIGNAL_TITLES = re.compile(
    r"|".join((
        r"\b(?:outpaces|outperforms|underperforms|lags|trails|dips more than|dipped more than|"
        r"rises? (?:higher )?than|falls? more (?:steeply )?than|gains? but lags)\b"
        r".*\b(?:market|s&p|nasdaq|dow)\b",
        r"\bwhat you (?:should|need to) know\b",
        r"\bhere'?s what an? \$[\d,]+ investment\b",
        r"\bshould you (?:buy|sell|hold)\b",
        r"\b(?:buy|sell),? or hold\b",
        r"\bhold or sell\b",
        r"\bstock market (?:today|midday)\b",
        r"\btop stock reports\b",
        r"\bstocks? to (?:buy|watch) (?:now|today|this)\b",
    )),
    re.I,
)
_NAME_SUFFIX = re.compile(
    r"[,.]?\s+(?:inc|corp|corporation|co|company|ltd|plc|holdings?|group|n\.v|s\.a|ag|se|class [a-z])\.?$",
    re.I,
)


def short_company_name(name: str | None) -> str:
    """'Advanced Micro Devices, Inc.' -> 'advanced micro devices' (lowercase)."""
    text = " ".join(str(name or "").split())
    for _ in range(3):
        text = _NAME_SUFFIX.sub("", text).strip()
    return text.lower() if len(text) >= 3 else ""


def is_low_signal(title: str) -> bool:
    return bool(LOW_SIGNAL_TITLES.search(title))


def is_about(row: dict[str, Any], ticker: str, company_name: str | None = None) -> bool:
    """True when the article is mainly about the ticker, not a passing mention.

    Kept when the ticker is the first tagged ticker, the article tags at most
    two tickers, or the title names the ticker or the company.
    """
    tagged = [str(item).upper() for item in (row.get("tickers") or []) if isinstance(item, str)]
    if not tagged:
        return True
    if ticker not in tagged:
        return False
    if tagged[0] == ticker or len(tagged) <= 2:
        return True
    title = str(row.get("title") or "")
    if re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", title):
        return True
    short = short_company_name(company_name)
    return bool(short) and short in title.lower()


def publisher_rank(publisher: str) -> int:
    name = publisher.lower()
    return 0 if any(key in name for key in PRIMARY_PUBLISHERS) else 1


def normalize_news(
    rows: Any,
    *,
    ticker: str,
    start: datetime,
    cutoff: datetime,
    limit: int,
    company_name: str | None = None,
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
        if not is_about(row, ticker, company_name):
            continue
        title = " ".join(str(row.get("title") or "").split())[:500]
        if not title or is_low_signal(title):
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
    documents.sort(key=lambda item: (publisher_rank(item[1]["publisher"]), -item[0].timestamp()))
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


def fetch_news_bulk(
    client: requests.Session,
    *,
    tickers: list[str],
    api_key: str,
    start: datetime,
    cutoff: datetime,
    limit: int,
    timeout: int,
    min_interval: float,
    page_size: int = 1000,
    max_pages: int = 50,
    company_names: dict[str, str] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Fetch one market-wide news window and fan articles out to candidates.

    Massive's free-plan request budget is spent per page instead of per ticker.
    Vendor text stays in process memory and is never written to Git or an
    Actions artifact.
    """
    allowed = {ticker for ticker in tickers if TICKER_PATTERN.fullmatch(ticker)}
    by_ticker: dict[str, list[tuple[datetime, dict[str, Any]]]] = {
        ticker: [] for ticker in sorted(allowed)
    }
    seen: dict[str, set[tuple[str, str]]] = {ticker: set() for ticker in allowed}
    if not allowed:
        return {}, {
            "mode": "bulk_window_pagination",
            "pages": 0,
            "articles_scanned": 0,
            "tickers_with_news": 0,
            "tickers_without_news": 0,
        }

    url = MASSIVE_NEWS_URL
    params: dict[str, Any] | None = {
        "published_utc.gte": utc_iso(start),
        "published_utc.lte": utc_iso(cutoff),
        "sort": "published_utc",
        "order": "desc",
        "limit": page_size,
        "apiKey": api_key,
    }
    names = company_names or {}
    keep = limit * 3  # gather a few extra so company releases can be preferred
    pages = 0
    scanned = 0
    dropped_mention = 0
    dropped_low_signal = 0
    last_request_at: float | None = None

    while url:
        if last_request_at is not None and min_interval > 0:
            remaining = min_interval - (time.monotonic() - last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        last_request_at = time.monotonic()
        payload = request_json(
            client,
            url,
            params=params or {"apiKey": api_key},
            timeout=timeout,
        )
        pages += 1
        rows = payload.get("results")
        if not isinstance(rows, list):
            rows = []
        scanned += len(rows)

        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                published = parse_timestamp(row.get("published_utc"), field="published_utc")
            except ShadowRunError:
                continue
            if published < start or published > cutoff:
                continue
            mentioned = {
                str(item).upper()
                for item in (row.get("tickers") or [])
                if isinstance(item, str)
            }
            tagged = allowed.intersection(mentioned)
            if not tagged:
                continue
            matches = {ticker for ticker in tagged if is_about(row, ticker, names.get(ticker))}
            dropped_mention += len(tagged) - len(matches)
            if not matches:
                continue
            title = " ".join(str(row.get("title") or "").split())[:500]
            if not title:
                continue
            if is_low_signal(title):
                dropped_low_signal += 1
                continue
            description = " ".join(str(row.get("description") or "").split())[:2000]
            article_url = str(row.get("article_url") or "").strip()[:1000]
            publisher = row.get("publisher") if isinstance(row.get("publisher"), dict) else {}
            document = {
                "source": "massive_news",
                "published_utc": utc_iso(published),
                "title": title,
                "description": description,
                "publisher": str(publisher.get("name") or "")[:200],
                "article_url": article_url,
            }
            key = (title, article_url)
            for ticker in matches:
                if len(by_ticker[ticker]) >= keep or key in seen[ticker]:
                    continue
                seen[ticker].add(key)
                by_ticker[ticker].append((published, document))

        if all(len(items) >= limit for items in by_ticker.values()):
            break
        next_url = payload.get("next_url")
        if not next_url:
            break
        parsed = urlparse(str(next_url))
        if parsed.scheme != "https" or parsed.netloc != "api.massive.com":
            raise ShadowRunError("Massive news pagination returned an unexpected host")
        if pages >= max_pages:
            raise ShadowRunError(
                f"Massive news pagination exceeded {max_pages} pages"
            )
        url = str(next_url)
        params = {"apiKey": api_key}

    documents = {
        ticker: [
            document
            for _, document in sorted(
                items,
                key=lambda item: (publisher_rank(item[1]["publisher"]), -item[0].timestamp()),
            )[:limit]
        ]
        for ticker, items in by_ticker.items()
    }
    with_news = sum(bool(items) for items in documents.values())
    return documents, {
        "mode": "bulk_window_pagination",
        "pages": pages,
        "api_calls": pages,
        "page_size": page_size,
        "articles_scanned": scanned,
        "candidate_tickers": len(allowed),
        "tickers_with_news": with_news,
        "tickers_without_news": len(allowed) - with_news,
        "dropped_passing_mentions": dropped_mention,
        "dropped_low_signal": dropped_low_signal,
        "company_releases": sum(
            publisher_rank(doc["publisher"]) == 0 for items in documents.values() for doc in items
        ),
    }


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
            "candidate_sources": candidate.get("sources") or [],
            "rs21_percentile": safe_number(detail.get("rs21")),
            "rs63_percentile": safe_number(detail.get("rs")),
            "rs189_percentile": safe_number(detail.get("rs189") or selection.get("rs")),
            "price": safe_number(detail.get("px") or selection.get("px")),
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


def _question_probability(aggregate: dict[str, Any], question_id: str) -> float | None:
    feature = aggregate.get(question_id)
    if not isinstance(feature, dict):
        return None
    value = feature.get("probabilityMean")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return min(1.0, max(0.0, float(value)))


def ranking_row(
    *,
    ticker: str,
    mc57_rank: Any,
    state_sha256: str,
    evaluation_id: str,
    news_count: int,
    aggregate: dict[str, Any],
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    positive = {
        question_id: value
        for question_id in POSITIVE_QUESTIONS
        if (value := _question_probability(aggregate, question_id)) is not None
    }
    risks = {
        question_id: value
        for question_id in RISK_QUESTIONS
        if (value := _question_probability(aggregate, question_id)) is not None
    }
    if len(positive) != len(POSITIVE_QUESTIONS) or len(risks) != len(RISK_QUESTIONS):
        raise ShadowRunError(f"Jev aggregate for {ticker} is incomplete")
    catalyst_mean = sum(positive.values()) / len(positive)
    risk_mean = sum(risks.values()) / len(risks)
    top_positive = max(positive, key=positive.get)
    top_risk = max(risks, key=risks.get)
    candidate = candidate or {}
    detail = candidate.get("detail") if isinstance(candidate.get("detail"), dict) else {}
    return {
        "ticker": ticker,
        "mc57_rank": mc57_rank,
        "candidate_sources": candidate.get("sources") or [],
        "rs21": safe_number(detail.get("rs21")),
        "rs63": safe_number(detail.get("rs")),
        "rs189": safe_number(detail.get("rs189")),
        "expected_value_score": round(100 * (catalyst_mean - risk_mean), 4),
        "catalyst_probability": round(catalyst_mean, 6),
        "risk_probability": round(risk_mean, 6),
        "top_catalyst": top_positive,
        "top_catalyst_label": POSITIVE_QUESTIONS[top_positive],
        "top_catalyst_probability": round(positive[top_positive], 6),
        "top_risk": top_risk,
        "top_risk_label": RISK_QUESTIONS[top_risk],
        "top_risk_probability": round(risks[top_risk], 6),
        "evaluation_id": evaluation_id,
        "news_count": news_count,
        "state_sha256": state_sha256,
    }


def load_prior_ranking(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("state_sha256")): row
        for row in rows
        if isinstance(row, dict) and row.get("state_sha256")
    }


def prior_ranking_session(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload.get("session_date") if isinstance(payload, dict) else None


def write_public_ranking(
    path: Path,
    *,
    session_date: Any,
    available_at: str,
    rows: list[dict[str, Any]],
    error_count: int = 0,
) -> None:
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row.get("expected_value_score") or 0),
            int(row.get("mc57_rank") or 10_000),
            str(row.get("ticker") or ""),
        ),
    )
    payload = {
        "schema_version": "jev-public-ranking-v1",
        "status": "partial" if error_count else ("ready" if ordered else "no_evaluable_news"),
        "session_date": session_date,
        "available_at": available_at,
        "question_set_version": QUESTION_SET_VERSION,
        "runs_per_ticker": 3,
        "formula": "100 * (mean(7 positive probabilities) - mean(7 risk probabilities))",
        "rows": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


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
        "responseMode": "json",
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
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                raise ShadowRunError(f"Jev response for {ticker} was not JSON") from None
            evaluation_id = payload.get("evaluationId") if isinstance(payload, dict) else None
            if not evaluation_id:
                raise ShadowRunError(f"Jev response for {ticker} omitted the evaluation id")
            aggregate = (
                payload.get("aggregate")
                if isinstance(payload, dict) and isinstance(payload.get("aggregate"), dict)
                else None
            )
            return {
                "evaluation_id": str(evaluation_id),
                "duplicate": payload.get("duplicate") is True,
                "gateway_cost_usd": safe_number(payload.get("gatewayCostUsd")),
                "aggregate": aggregate,
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
    parser.add_argument("--ranking-output", default="data/jev-ranking.json")
    parser.add_argument("--max-candidates", type=int, default=70)
    parser.add_argument("--max-news", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--provider-timeout", type=int, default=45)
    parser.add_argument("--jev-timeout", type=int, default=180)
    parser.add_argument("--massive-min-interval", type=float, default=13.0)
    parser.add_argument("--massive-page-size", type=int, default=1000)
    parser.add_argument("--massive-max-pages", type=int, default=50)
    args = parser.parse_args()

    if not 1 <= args.max_candidates <= 100:
        parser.error("--max-candidates must be between 1 and 100")
    if not 1 <= args.max_news <= 50:
        parser.error("--max-news must be between 1 and 50")
    if not 1 <= args.lookback_days <= 90:
        parser.error("--lookback-days must be between 1 and 90")
    if not 0 <= args.massive_min_interval <= 120:
        parser.error("--massive-min-interval must be between 0 and 120 seconds")
    if not 100 <= args.massive_page_size <= 1000:
        parser.error("--massive-page-size must be between 100 and 1000")
    if not 1 <= args.massive_max_pages <= 100:
        parser.error("--massive-max-pages must be between 1 and 100")

    root = Path(args.root).resolve()
    output_path = root / args.output
    ranking_path = root / args.ranking_output
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ShadowRunError("manifest must be a JSON object")
    cutoff = parse_timestamp(manifest.get("generated_at"), field="manifest.generated_at")
    candidates, calc = load_dashboard(root / args.dashboard, args.max_candidates)
    company_names = load_company_names(root / args.reference)
    candidate_sources = sorted({source for row in candidates for source in row.get("sources", [])})

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
        "candidate_source_counts": {
            source: sum(source in row.get("sources", []) for row in candidates)
            for source in candidate_sources
        },
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
    prior_ranking = load_prior_ranking(ranking_path)
    ranking_rows: list[dict[str, Any]] = []

    try:
        news_by_ticker, news_stats = fetch_news_bulk(
            news_client,
            tickers=[candidate["ticker"] for candidate in candidates],
            api_key=massive_key,
            start=start,
            cutoff=cutoff,
            limit=args.max_news,
            timeout=args.provider_timeout,
            min_interval=args.massive_min_interval,
            page_size=args.massive_page_size,
            max_pages=args.massive_max_pages,
            company_names=company_names,
        )
    except Exception as exc:
        safe_error = exc if isinstance(exc, ShadowRunError) else ShadowRunError(type(exc).__name__)
        summary["status"] = "news_fetch_failed"
        summary["error_count"] = 1
        summary["news_error"] = str(safe_error)
        write_summary(output_path, summary)
        append_actions_summary(summary)
        print(f"::warning title=Jev Massive news batch failed::{safe_error}")
        return 1
    summary["massive_news"] = news_stats

    for candidate in candidates:
        ticker = candidate["ticker"]
        rank = candidate["selection"].get("rk")
        try:
            documents = news_by_ticker.get(ticker, [])
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
            derived = None
            if result["aggregate"] is not None:
                derived = ranking_row(
                    ticker=ticker,
                    mc57_rank=rank,
                    state_sha256=state_hash,
                    evaluation_id=result["evaluation_id"],
                    news_count=len(documents),
                    aggregate=result["aggregate"],
                    candidate=candidate,
                )
            elif result["duplicate"] and state_hash in prior_ranking:
                derived = prior_ranking[state_hash]
            if derived is None:
                # Saved earlier but neither the API nor the last public ranking can
                # give the scores back: this is not a successful evaluation.
                raise ShadowRunError(
                    f"Jev evaluation #{result['evaluation_id']} for {ticker} has no recoverable aggregate"
                )
            if derived is not None:
                ranking_rows.append(derived)
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
                    "expected_value_score": (
                        derived.get("expected_value_score") if derived is not None else None
                    ),
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
    prior_session = prior_ranking_session(ranking_path)
    keep_prior = bool(summary["error_count"]) and prior_session == summary["session_date"]
    if keep_prior:
        # A partial rerun must not replace a complete ranking of the same session.
        summary["ranking_kept"] = "previous ranking of the same session retained (errors in this run)"
        print("::warning title=Jev ranking kept::errors in this run; previous ranking of the same session retained")
    elif ranking_rows or not summary["error_count"]:
        write_public_ranking(
            ranking_path,
            session_date=summary["session_date"],
            available_at=summary["available_at"],
            rows=ranking_rows,
            error_count=summary["error_count"],
        )
        from render_jev_ranking import bind_ranking
        bind_ranking(root / args.dashboard, ranking_path)
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
