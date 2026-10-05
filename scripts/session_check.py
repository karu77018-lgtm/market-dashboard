"""Regular-session check for the daily bars (publication gate).

From 2026-12-06 NYSE and Nasdaq trade about 23 hours a day; trades between
21:00 and midnight ET carry the next day's date.  Every rule on the dashboard
(signal close, next open, -8% stop, 21-EMA of lows, RS189) was studied on
regular-session daily bars (09:30-16:00 ET).  If a data source starts folding
the overnight/extended sessions into its daily bar, the open in particular
silently becomes a 21:00 price.  This check compares today's bars with the
official regular-session open and close (Massive /v1/open-close, which reports
pre-market and after-hours separately) for a small basket.

* any compared ticker off by more than the tolerance -> FAIL (exit 1, nothing is
  published)
* fewer than MIN_COMPARED tickers could be compared (provider outage) ->
  UNVERIFIED, logged, publication continues (an outage must not stop the page)

  python scripts/session_check.py [--root .]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

STOCKS = ("AAPL", "MSFT", "NVDA", "AMZN")   # from work/ohlcv.csv
ETFS = ("SPY", "QQQ")                       # from data/market_inputs.json
TOL_OPEN = 0.002
TOL_CLOSE = 0.001
MIN_COMPARED = 3


def ours(root: Path, session: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    try:
        f = pd.read_csv(root / "work" / "ohlcv.csv", usecols=["ticker", "date", "open", "close"])
        f = f[(f["ticker"].astype(str).str.upper().isin(STOCKS)) & (f["date"].astype(str).str[:10] == session)]
        for r in f.itertuples():
            out[str(r.ticker).upper()] = {"open": float(r.open), "close": float(r.close)}
    except (OSError, ValueError, KeyError):
        pass
    try:
        series = json.loads((root / "data" / "market_inputs.json").read_text(encoding="utf-8"))["series"]
        for t in ETFS:
            row = next((r for r in series.get(t, []) if str(r.get("date"))[:10] == session), None)
            if row and row.get("open") is not None and row.get("close") is not None:
                out[t] = {"open": float(row["open"]), "close": float(row["close"])}
    except (OSError, ValueError, KeyError):
        pass
    return out


def official(tickers: list[str], session: str, api_key: str) -> dict[str, dict[str, float]]:
    import requests
    from provider_inputs import MASSIVE_BASE, _get_json
    client, out = requests.Session(), {}
    for t in tickers:
        try:
            p = _get_json(client, f"{MASSIVE_BASE}/v1/open-close/{t}/{session}",
                          params={"adjusted": "true", "apiKey": api_key}, attempts=3)
        except Exception as exc:  # message carries no key (_safe_url)
            print(f"official open/close unavailable for {t}: {type(exc).__name__}", flush=True)
            continue
        if str(p.get("status")).upper() == "OK" and p.get("open") and p.get("close"):
            out[t] = {"open": float(p["open"]), "close": float(p["close"]),
                      "pre": p.get("preMarket"), "after": p.get("afterHours")}
        time.sleep(0.5)
    return out


def compare(mine: dict, ref: dict) -> dict:
    rows, bad = [], []
    for t in sorted(set(mine) & set(ref)):
        do = mine[t]["open"] / ref[t]["open"] - 1
        dc = mine[t]["close"] / ref[t]["close"] - 1
        ok = abs(do) <= TOL_OPEN and abs(dc) <= TOL_CLOSE
        rows.append({"t": t, "open_diff": round(do, 5), "close_diff": round(dc, 5), "ok": ok})
        if not ok:
            bad.append(t)
    status = "FAIL" if bad else ("PASS" if len(rows) >= MIN_COMPARED else "UNVERIFIED")
    return {"status": status, "compared": len(rows), "mismatch": bad, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    root = Path(ap.parse_args().root)
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    mine = ours(root, session)
    key = os.environ.get("MASSIVE_API_KEY", "")
    ref = official(sorted(mine), session, key) if key and mine else {}
    res = {"session": session, **compare(mine, ref)}
    for r in res["rows"]:
        print(f"{r['t']}: open {r['open_diff']:+.3%} close {r['close_diff']:+.3%} {'OK' if r['ok'] else 'MISMATCH'}",
              flush=True)
    print(f"regular-session check {session}: {res['status']} ({res['compared']} compared)", flush=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "session-check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                                                      encoding="utf-8")
    if res["status"] == "FAIL":
        print("daily bars differ from the official regular-session open/close: "
              "a source may now include overnight/extended trading. Publication stopped.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
