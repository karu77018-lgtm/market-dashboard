"""Option walls for the leveraged ETFs (SOXL, TQQQ) and QQQ — recorded for study.

Reference only, never a trading gate.  The swing candidates' walls come from
options_walls.py; these ETFs are not in the stock universe (no DET row, no OHLCV
in the frame), so the underlying price is fetched alongside the chain (Yahoo
daily bar for the session; Cboe's payload when falling back to Cboe).

QQQ is included because the TQQQ rule judges on QQQ and QQQ's option book is far
deeper than TQQQ's.

Each session stores, per ticker: close/high/low, the walls (cw/pw/gf, same
definitions as options_walls.walls), conf and iv30 (Cboe only; None from Yahoo).
Open interest has no history at either source, so this is validated forward: once 5 and 20 later sessions are
recorded, each day gets the realised outcome (return, whether the high reached
the call wall, whether the low reached the put wall, how far the price ranged).
The weekly study compares those outcomes with a plain volatility baseline.

Ledger: track-record/etf-walls.json
"""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from options_walls import CBOE_URL, fetch_chain_yahoo, quote_age, walls, yahoo_ticker

TICKERS = ("SOXL", "TQQQ", "QQQ")
LEDGER = Path("track-record/etf-walls.json")
SCHEMA = "etf-walls.1"
HORIZONS = (5, 20)


def fetch_payload_cboe(ticker: str, *, timeout: float = 30.0) -> dict[str, Any] | None:
    req = urllib.request.Request(CBOE_URL.format(ticker),
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else None


def fetch_payload_yahoo(ticker: str, session: str, *, tk: Any = None) -> dict[str, Any] | None:
    """The Cboe payload shape built from Yahoo: the session's daily bar + the chain."""
    try:
        tk = tk if tk is not None else yahoo_ticker(ticker)
        start = date.fromisoformat(session)
        bars = tk.history(start=start.isoformat(), end=(start + timedelta(days=1)).isoformat(),
                          auto_adjust=False)
        if bars is None or len(bars) == 0 or str(bars.index[-1].date()) != session:
            return None
        bar = bars.iloc[-1]
        got = fetch_chain_yahoo(ticker, session, tk=tk)
    except Exception:
        return None
    if got is None:
        return None
    return {"timestamp": got[1],
            "data": {"close": float(bar["Close"]), "high": float(bar["High"]), "low": float(bar["Low"]),
                     "iv30": None, "options": got[0]}}


def fetch_payload(ticker: str, session: str | None = None) -> dict[str, Any] | None:
    got = fetch_payload_yahoo(ticker, session) if session else None
    return got if got is not None else fetch_payload_cboe(ticker)


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def snapshot(payload: dict[str, Any], ticker: str, session: str) -> dict[str, Any] | None:
    data = payload["data"]
    close = _num(data.get("close")) or _num(data.get("current_price"))
    options = data.get("options")
    if not close or not isinstance(options, list):
        return None
    w = walls(options, ticker=ticker, spot=close, session=session) or {}
    stamp = payload.get("timestamp")
    return {
        "close": close, "high": _num(data.get("high")), "low": _num(data.get("low")),
        "iv30": _num(data.get("iv30")),
        **{k: w.get(k) for k in ("cw", "cwp", "pw", "pwp", "gf", "gfp", "cwoi", "pwoi", "total_oi", "conf")},
        "asof": str(stamp) if stamp else None, "age": quote_age(str(stamp) if stamp else None, session),
    }


def load_ledger(root: Path) -> dict:
    path = root / LEDGER
    try:
        led = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(led, dict) and isinstance(led.get("days"), dict):
            return led
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "tickers": list(TICKERS), "days": {}}


def save_ledger(led: dict, root: Path) -> None:
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(led, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def forward(led: dict) -> dict:
    """Fill each day's outcome once enough later sessions are recorded (per ticker)."""
    days = sorted(led["days"])
    for t in led.get("tickers", TICKERS):
        seq = [(d, led["days"][d][t]) for d in days if isinstance(led["days"][d].get(t), dict)]
        for i, (d, row) in enumerate(seq):
            out = row.setdefault("fwd", {})
            for n in HORIZONS:
                key = str(n)
                if key in out or i + n >= len(seq):
                    continue
                later = [r for _, r in seq[i + 1:i + 1 + n]]
                hi = max((r.get("high") or r["close"]) for r in later)
                lo = min((r.get("low") or r["close"]) for r in later)
                c0, cn = row["close"], later[-1]["close"]
                gf = row.get("gf")
                out[key] = {
                    "ret": round(cn / c0 - 1, 5),
                    "max_up": round(hi / c0 - 1, 5), "max_dn": round(lo / c0 - 1, 5),
                    "hit_cw": (hi >= row["cw"]) if row.get("cw") else None,
                    "hit_pw": (lo <= row["pw"]) if row.get("pw") else None,
                    "start_above_gf": (c0 > gf) if gf else None,
                    "end": seq[i + n][0],
                }
    return led


def record(led: dict, session: str, snaps: dict[str, dict]) -> dict:
    if snaps:
        led["days"][session] = {**led["days"].get(session, {}), **snaps}
    return led


def run(root: Path, session: str, *, fetch=None) -> dict[str, dict]:
    fetch = fetch or (lambda t: fetch_payload(t, session))
    snaps: dict[str, dict] = {}
    for t in TICKERS:
        payload = fetch(t)
        snap = snapshot(payload, t, session) if payload else None
        if snap:
            snaps[t] = snap
    led = forward(record(load_ledger(root), session, snaps))
    save_ledger(led, root)
    for t, s in snaps.items():
        print(f"etf walls {t}: close {s['close']} cw {s.get('cw')} pw {s.get('pw')} gf {s.get('gf')} "
              f"({s.get('conf')})", flush=True)
    print(f"etf walls: {len(snaps)}/{len(TICKERS)} recorded for {session}", flush=True)
    return snaps
