#!/usr/bin/env python3
"""Local-only ablation test for deterministic earnings expectation load + Jev.

No provider calls. No GitHub Actions. This script consumes frozen JSON inputs
and evaluates only post-announcement, potentially tradable outcomes.

Primary outcomes:
- first post-event OPEN -> fifth post-event CLOSE
- first post-event CLOSE -> fifth post-event CLOSE

The historical pre-event-close -> 5D return is retained only as a descriptive
diagnostic because a decision made after the earnings release cannot capture
the already-realized gap.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


CAL_END = "2026-08-31"
HOLDOUT_START = "2026-09-01"


def finite(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x=float(v)
    except (TypeError,ValueError):
        return None
    return x if math.isfinite(x) else None


def pct_rank_against(value: float, calibration: list[float]) -> float:
    if not calibration:
        raise ValueError("empty calibration")
    less=sum(x < value for x in calibration)
    equal=sum(x == value for x in calibration)
    return 100.0*(less+0.5*equal)/len(calibration)


def post_open_to_5d(row: dict[str,Any]) -> float | None:
    gap=finite(row.get("gap_pct"))
    r5=finite(row.get("ret5_pct"))
    if gap is None or r5 is None or 1+gap/100 <= 0:
        return None
    return 100*((1+r5/100)/(1+gap/100)-1)


def post_close1_to_5d(row: dict[str,Any]) -> float | None:
    r1=finite(row.get("ret1_pct"))
    r5=finite(row.get("ret5_pct"))
    if r1 is None or r5 is None or 1+r1/100 <= 0:
        return None
    return 100*((1+r5/100)/(1+r1/100)-1)


def q(values:list[float], p:float)->float|None:
    if not values:
        return None
    s=sorted(values)
    x=(len(s)-1)*p
    lo=math.floor(x); hi=math.ceil(x)
    return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)


def stats(rows:list[dict[str,Any]], field:str)->dict[str,Any]:
    vals=[finite(r.get(field)) for r in rows]
    vals=[v for v in vals if v is not None]
    return {
        "n":len(vals),
        "mean":statistics.fmean(vals) if vals else None,
        "median":statistics.median(vals) if vals else None,
        "p10":q(vals,.10),
        "p_negative":statistics.fmean(v<0 for v in vals) if vals else None,
    }


def bootstrap_mean_diff(
    a:list[float], b:list[float], *, seed:int=20261001, draws:int=20000
)->dict[str,float]|None:
    if len(a)<5 or len(b)<5:
        return None
    rng=random.Random(seed)
    diffs=[]
    for _ in range(draws):
        aa=[a[rng.randrange(len(a))] for _ in a]
        bb=[b[rng.randrange(len(b))] for _ in b]
        diffs.append(statistics.fmean(aa)-statistics.fmean(bb))
    diffs.sort()
    return {
        "observed":statistics.fmean(a)-statistics.fmean(b),
        "ci95_low":diffs[int(.025*draws)],
        "ci95_high":diffs[int(.975*draws)-1],
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",required=True)
    ap.add_argument("--jev",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--threshold",type=float,default=60.0)
    ap.add_argument("--positive-surprise-cutoff",type=float,default=.60)
    args=ap.parse_args()

    events=json.loads(Path(args.events).read_text())
    overlay=json.loads(Path(args.jev).read_text())
    base=[r for r in events.get("rows",[]) if isinstance(r,dict)]
    jev_rows={
        (str(r.get("ticker")),str(r.get("accession_number"))):r
        for r in overlay.get("rows",[]) if isinstance(r,dict)
    }

    cal=[
        finite(r.get("pre20_excess_qqq_pct"))
        for r in base if str(r.get("filing_date","")) <= CAL_END
    ]
    cal=[x for x in cal if x is not None]

    joined=[]
    for r in base:
        date=str(r.get("filing_date",""))
        if date < HOLDOUT_START:
            continue
        excess=finite(r.get("pre20_excess_qqq_pct"))
        if excess is None:
            continue
        j=jev_rows.get((str(r.get("ticker")),str(r.get("accession_number"))))
        out=dict(r)
        out["deterministic_excess_load_pctile"]=pct_rank_against(excess,cal)
        out["post_open_to_5d_pct"]=post_open_to_5d(r)
        out["post_close1_to_5d_pct"]=post_close1_to_5d(r)
        out["jev"]=j.get("jev") if j else None
        joined.append(out)

    high=[r for r in joined if r["deterministic_excess_load_pctile"]>=args.threshold]

    evidence_usable=[
        r for r in high
        if isinstance(r.get("jev"),dict)
        and r["jev"].get("evidence_quality") in {"strong","usable"}
    ]
    positive_surprise=[
        r for r in evidence_usable
        if finite(r["jev"].get("positive_surprise_probability")) is not None
        and finite(r["jev"].get("positive_surprise_probability"))>=args.positive_surprise_cutoff
        and r["jev"].get("surprise_class")=="positive_surprise"
    ]
    jev_risk=[
        r for r in evidence_usable
        if r not in positive_surprise
    ]

    result={
        "version":"earnings-jev-local-ablation-v1",
        "calibration_end":CAL_END,
        "holdout_start":HOLDOUT_START,
        "deterministic_feature":"pre20_excess_qqq_pct percentile calibrated on Jul-Aug only",
        "deterministic_threshold":args.threshold,
        "jev_positive_surprise_cutoff":args.positive_surprise_cutoff,
        "counts":{
            "holdout":len(joined),
            "deterministic_high_load":len(high),
            "high_load_with_usable_jev":len(evidence_usable),
            "jev_positive_surprise":len(positive_surprise),
            "jev_refined_risk":len(jev_risk),
        },
        "post_open_to_5d":{
            "all_high_load":stats(high,"post_open_to_5d_pct"),
            "jev_positive_surprise":stats(positive_surprise,"post_open_to_5d_pct"),
            "jev_refined_risk":stats(jev_risk,"post_open_to_5d_pct"),
        },
        "post_close1_to_5d":{
            "all_high_load":stats(high,"post_close1_to_5d_pct"),
            "jev_positive_surprise":stats(positive_surprise,"post_close1_to_5d_pct"),
            "jev_refined_risk":stats(jev_risk,"post_close1_to_5d_pct"),
        },
        "descriptive_preclose_to_5d":{
            "all_high_load":stats(high,"ret5_pct"),
            "jev_positive_surprise":stats(positive_surprise,"ret5_pct"),
            "jev_refined_risk":stats(jev_risk,"ret5_pct"),
        },
    }

    a=[finite(r.get("post_open_to_5d_pct")) for r in jev_risk]
    b=[finite(r.get("post_open_to_5d_pct")) for r in positive_surprise]
    a=[x for x in a if x is not None]; b=[x for x in b if x is not None]
    result["bootstrap_post_open_mean_diff_risk_minus_positive"]=bootstrap_mean_diff(a,b)

    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
