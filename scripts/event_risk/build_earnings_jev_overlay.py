#!/usr/bin/env python3
"""Build a September holdout earnings Jev overlay from Massive 10-Q text.

This script extracts semantic features only. It does not calculate returns,
fit thresholds, optimize weights, or run a backtest.

Evidence policy:
- match the earnings event to a Form 10-Q filed on the SAME date only;
- fetch the 10-Q main document through Massive (not SEC directly);
- extract visible MD&A / Results of Operations text;
- send pre-event deterministic context + event text to Jev v2;
- persist derived Jev features and audit hashes only.

Backtests remain local-only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
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
from scripts.run_expectation_gap_shadow import MassivePacer

DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"


def canonical_hash(value: Any) -> str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value,bool) or value is None:
        return None
    try:
        x=float(value)
    except (TypeError,ValueError):
        return None
    return x if math.isfinite(x) else None


def _entities(raw: Any) -> list[dict[str,Any]]:
    if isinstance(raw,list):
        return [x for x in raw if isinstance(x,dict)]
    if isinstance(raw,str):
        try:
            val=json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [x for x in val if isinstance(x,dict)] if isinstance(val,list) else []
    return []


def _filing_tickers(row: dict[str,Any]) -> set[str]:
    out=set()
    for ent in _entities(row.get("entities")):
        data=ent.get("company_data") if isinstance(ent.get("company_data"),dict) else {}
        t=data.get("ticker")
        if isinstance(t,str) and t:
            out.add(t.upper())
        for item in data.get("tickers") or []:
            if isinstance(item,str) and item:
                out.add(item.upper())
    return out


def _compact_to_iso(value: Any) -> str:
    s=str(value or "")
    if re.fullmatch(r"\d{8}",s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10]


def strip_10q_html(raw: str) -> str:
    raw=re.sub(r"(?is)<ix:header.*?</ix:header>"," ",raw)
    raw=re.sub(r"(?is)<script.*?</script>|<style.*?</style>"," ",raw)
    raw=re.sub(r"(?is)<!--.*?-->"," ",raw)
    text=re.sub(r"(?s)<[^>]+>"," ",raw)
    text=html.unescape(text)
    return " ".join(text.split())


def extract_mda(raw: str) -> tuple[str,str]:
    text=strip_10q_html(raw)
    patterns=[
        r"item\s*2\.?\s*management[’'s\s]+discussion\s+and\s+analysis",
        r"management[’'s\s]+discussion\s+and\s+analysis",
        r"results\s+of\s+operations",
    ]
    start=None
    label="10-Q-visible-fallback"
    for pat in patterns:
        m=re.search(pat,text,re.I)
        if m:
            start=m.start()
            label=pat
            break
    if start is None:
        return text[:14000],label
    segment=text[start:start+22000]
    end=re.search(r"\bitem\s*3\.?\s+quantitative\b|\bitem\s*4\.?\s+controls\b",segment,re.I)
    if end and end.start()>3000:
        segment=segment[:end.start()]
    return segment[:14000],label


def fetch_10q_index(
    client: MassivePacer,start_date:str,end_date:str
)->dict[tuple[str,str],dict[str,Any]]:
    start=start_date.replace("-","")
    end=end_date.replace("-","")
    rows=client.paged(
        "/v1/reference/sec/filings",
        {
            "type":"10-Q",
            "filing_date.gte":start,
            "filing_date.lte":end,
            "limit":1000,
            "sort":"filing_date",
            "order":"asc",
        },
        max_pages=10,
    )
    out={}
    for row in rows:
        date=_compact_to_iso(row.get("filing_date"))
        for ticker in _filing_tickers(row):
            out[(ticker,date)]=row
    return out


def evaluate_jev(
    session:requests.Session,url:str,secret:str,state:dict[str,Any],
    questions:dict[str,Any],timeout:int
)->dict[str,Any]:
    response=session.post(
        url,
        headers={"Authorization":f"Bearer {secret}"},
        json={
            "state":state,
            "questions":questions,
            "runs":1,
            "persist":False,
            "responseMode":"json",
        },
        timeout=timeout,
    )
    if response.status_code!=200:
        raise ShadowRunError(f"Jev HTTP {response.status_code}: {response.text[:300]}")
    payload=response.json()
    aggregate=payload.get("aggregate")
    if not isinstance(aggregate,dict):
        raise ShadowRunError("Jev aggregate missing")
    return {
        "aggregate":aggregate,
        "duration_ms":safe_number(payload.get("durationMs")),
        "gateway_cost_usd":_finite(payload.get("gatewayCostUsd")),
    }


def prob(agg:dict[str,Any],qid:str)->float|None:
    row=agg.get(qid)
    return _finite(row.get("probabilityMean")) if isinstance(row,dict) else None


def choice(agg:dict[str,Any],qid:str)->str|None:
    row=agg.get(qid)
    v=row.get("majorityChoice") if isinstance(row,dict) else None
    return str(v) if v is not None else None


def choice_probability(agg:dict[str,Any],qid:str,option:str)->float|None:
    row=agg.get(qid)
    dist=row.get("choiceDistribution") if isinstance(row,dict) else None
    return _finite(dist.get(option)) if isinstance(dist,dict) else None


def derived(agg:dict[str,Any])->dict[str,Any]:
    return {
        "material_business_change":prob(agg,"JEV01_material_business_change"),
        "persistent_change":prob(agg,"JEV02_persistent_change"),
        "information_novelty":prob(agg,"JEV03_information_novelty"),
        "surprise_class":choice(agg,"JEV04_surprise_vs_prior_expectations"),
        "positive_surprise_probability":choice_probability(
            agg,"JEV04_surprise_vs_prior_expectations","positive_surprise"
        ),
        "negative_surprise_probability":choice_probability(
            agg,"JEV04_surprise_vs_prior_expectations","negative_surprise"
        ),
        "broadly_expected_probability":choice_probability(
            agg,"JEV04_surprise_vs_prior_expectations","broadly_expected"
        ),
        "evidence_quality":choice(agg,"JEV05_evidence_quality"),
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=".")
    ap.add_argument("--events",default="research/event_risk/earnings-expectation-load-core-v1.json")
    ap.add_argument("--questions",default="research/expectation_gap/question-set-en-v2.json")
    ap.add_argument("--output",default="research/event_risk/earnings-jev-overlay-v1.json")
    ap.add_argument("--start-date",default="2026-09-01")
    ap.add_argument("--end-date",default="2026-09-30")
    ap.add_argument("--massive-min-interval",type=float,default=13.0)
    ap.add_argument("--timeout",type=int,default=120)
    args=ap.parse_args()

    root=Path(args.root).resolve()
    api_key=os.getenv("MASSIVE_API_KEY") or os.getenv("MASSIVE_KEY") or os.getenv("POLYGON_API_KEY")
    secret=os.getenv("JEV_API_SECRET")
    jev_url=os.getenv("JEV_API_URL") or DEFAULT_JEV_URL
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required")
    if not secret:
        raise SystemExit("JEV_API_SECRET is required")

    event_payload=json.loads((root/args.events).read_text())
    rows=[
        r for r in event_payload.get("rows",[])
        if isinstance(r,dict)
        and r.get("ticker") and r.get("filing_date") and r.get("accession_number")
        and args.start_date<=str(r.get("filing_date"))<=args.end_date
    ]
    qset=json.loads((root/args.questions).read_text())
    questions=qset.get("questions")
    if not isinstance(questions,dict) or len(questions)!=5:
        raise SystemExit("Expected five Jev v2 questions")

    massive=MassivePacer(api_key,args.massive_min_interval)
    index=fetch_10q_index(massive,args.start_date,args.end_date)
    jev=requests.Session()

    outputs=[]
    errors=[]
    unmatched=[]
    cost=0.0

    for i,row in enumerate(rows,1):
        ticker=str(row["ticker"]).upper()
        date=str(row["filing_date"])
        filing=index.get((ticker,date))
        if not filing:
            unmatched.append({"ticker":ticker,"filing_date":date,"reason":"NO_SAME_DAY_10Q"})
            continue
        main_url=str(filing.get("main_file_url") or "")
        if not main_url.startswith("https://api.massive.com/"):
            unmatched.append({"ticker":ticker,"filing_date":date,"reason":"NO_MASSIVE_MAIN_FILE"})
            continue
        try:
            payload=massive.get(main_url)
            # Filing-file endpoints may return raw text/HTML through the client wrapper.
            if isinstance(payload,dict):
                raw=payload.get("content") or payload.get("text") or payload.get("html")
                if raw is None:
                    raw=json.dumps(payload,ensure_ascii=False)
            else:
                raw=str(payload)
            evidence,section=extract_mda(str(raw))
            state={
                "schema_version":"earnings-jev-overlay-state-v1",
                "ticker":ticker,
                "event_date":date,
                "pre_event_market_context":{
                    "pre20_return_pct":row.get("pre20_return_pct"),
                    "pre20_excess_qqq_pct":row.get("pre20_excess_qqq_pct"),
                    "rs63_change_20d":row.get("rs63_change_20d"),
                    "distance_to_63d_high_pct":row.get("dist_high63_pct"),
                },
                "company_specific_evidence":{
                    "source":"same-day 10-Q via Massive",
                    "section":section,
                    "text":evidence,
                },
                "instructions":[
                    "Use only supplied evidence.",
                    "Market metrics are prior-expectation context, not proof of business quality.",
                    "Do not predict stock price and do not use post-event returns.",
                    "If the 10-Q text is not sufficient to compare actual business change with prior expectations, mark evidence quality weak or insufficient.",
                ],
            }
            result=evaluate_jev(jev,jev_url,secret,state,questions,args.timeout)
            cost+=result.get("gateway_cost_usd") or 0.0
            outputs.append({
                "ticker":ticker,
                "filing_date":date,
                "accession_number":str(row["accession_number"]),
                "state_sha256":canonical_hash(state),
                "evidence_chars":len(evidence),
                "jev":derived(result["aggregate"]),
                "duration_ms":result.get("duration_ms"),
            })
        except Exception as exc:
            errors.append({
                "ticker":ticker,"filing_date":date,
                "error":type(exc).__name__,"message":str(exc)[:300]
            })
        if i%10==0:
            print(json.dumps({
                "processed":i,"success":len(outputs),
                "unmatched":len(unmatched),"errors":len(errors)
            }),flush=True)

    out={
        "version":"earnings-jev-overlay-v1",
        "created_at":datetime.now(timezone.utc).isoformat(),
        "question_set_version":qset.get("version"),
        "start_date":args.start_date,
        "end_date":args.end_date,
        "event_count":len(rows),
        "jev_success_count":len(outputs),
        "unmatched_count":len(unmatched),
        "jev_error_count":len(errors),
        "gateway_cost_usd":round(cost,8),
        "evidence_source":"same-day Form 10-Q main document fetched through Massive",
        "privacy":{"filing_text_persisted":False,"raw_jev_runs_persisted":False},
        "rows":outputs,
        "unmatched":unmatched,
        "errors":errors,
    }
    path=root/args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({
        "ok":True,"event_count":len(rows),"jev_success_count":len(outputs),
        "unmatched_count":len(unmatched),"jev_error_count":len(errors),
        "gateway_cost_usd":out["gateway_cost_usd"]
    },indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
