"""Option walls for the swing candidates (reference only, never a trading gate).

Also fetched for study groups (dollar-volume top 5%, RS189 x trend template top 40,
RS63 top 30, RS21 top 30) for the weekly study of whether walls relate to later
returns.  Those go only into the ticker detail (DET, tagged with "grp"), not onto
the swing card.

Source: Cboe delayed quotes (one JSON per underlying with open interest, IV and
greeks for every listed option).  Open interest is published by OCC once a day,
so the walls describe positioning as of the previous session.

Per underlying, over expiries after the session date and within 45 days:
  cw  上値の壁   strike >= spot with the largest call open interest
  pw  下値の支え strike <= spot with the largest put open interest
  gf  性質の境目 price where net dealer gamma (calls +, puts -) changes sign,
                 re-evaluated with Black-Scholes on a +/-30% price grid
  *p  distance from the close (fraction); walls weight OI by gamma at the close
The output matches the existing ticker-detail fields (DET[ticker].opt).
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from datetime import date
from typing import Any, Iterable

import numpy as np

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
HORIZON_DAYS = 45
RATE = 0.04
LOW_TOTAL_OI = 5000
LOW_WALL_OI = 500
OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def fetch_chain(ticker: str, *, timeout: float = 20.0) -> list[dict[str, Any]] | None:
    got = fetch_chain_with_time(ticker, timeout=timeout)
    return got[0] if got else None


def fetch_chain_with_time(ticker: str, *, timeout: float = 20.0) -> tuple[list[dict[str, Any]], str | None] | None:
    """(options, Cboe quote timestamp) — the timestamp is kept so freshness is real."""
    req = urllib.request.Request(CBOE_URL.format(ticker.replace(".", "")),
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    options = (payload.get("data") or {}).get("options") if isinstance(payload, dict) else None
    if not isinstance(options, list):
        return None
    stamp = payload.get("timestamp") if isinstance(payload, dict) else None
    return options, (str(stamp) if stamp else None)


def quote_age(stamp: str | None, session: str) -> int | None:
    """Calendar days from the session to the quote time (None when unknown)."""
    if not stamp:
        return None
    try:
        return (date.fromisoformat(stamp[:10]) - date.fromisoformat(session)).days
    except ValueError:
        return None


def _parse(options: Iterable[dict[str, Any]], ticker: str, session: str) -> list[tuple]:
    """(is_call, strike, years, oi, iv) for the root ticker inside the horizon."""
    start = date.fromisoformat(session)
    root = ticker.replace(".", "")
    rows = []
    for item in options:
        m = OCC.match(str(item.get("option") or ""))
        if not m or m.group(1) != root:
            continue  # adjusted/non-standard roots carry different deliverables
        y, mo, d = m.group(2)[:2], m.group(2)[2:4], m.group(2)[4:]
        days = (date(2000 + int(y), int(mo), int(d)) - start).days
        oi = float(item.get("open_interest") or 0)
        if not (0 < days <= HORIZON_DAYS) or oi <= 0:
            continue
        rows.append((m.group(3) == "C", int(m.group(4)) / 1000.0, max(days, 1) / 365.0, oi,
                     float(item.get("iv") or 0.0)))
    return rows


def _gamma(spot: np.ndarray, strike: np.ndarray, years: np.ndarray, iv: np.ndarray) -> np.ndarray:
    s = spot[:, None]
    vol_t = iv * np.sqrt(years)
    d1 = (np.log(s / strike) + (RATE + 0.5 * iv ** 2) * years) / vol_t
    return np.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi) / (s * vol_t)


def gamma_flip(rows: list[tuple], spot: float) -> float | None:
    usable = [r for r in rows if 0.05 <= r[4] <= 5.0]
    if len(usable) < 10:
        return None
    is_call = np.array([r[0] for r in usable])
    strike, years, oi, iv = (np.array([r[i] for r in usable], dtype=float) for i in (1, 2, 3, 4))
    grid = np.linspace(spot * 0.7, spot * 1.3, 241)
    sign = np.where(is_call, 1.0, -1.0)
    gex = (_gamma(grid, strike, years, iv) * (sign * oi)[None, :]).sum(axis=1) * grid ** 2
    cross = np.where(np.sign(gex[:-1]) != np.sign(gex[1:]))[0]
    if not len(cross):
        return None
    flips = [grid[i] - gex[i] * (grid[i + 1] - grid[i]) / (gex[i + 1] - gex[i]) for i in cross]
    return float(min(flips, key=lambda x: abs(x - spot)))


def walls(options: list[dict[str, Any]], *, ticker: str, spot: float, session: str) -> dict[str, Any] | None:
    rows = _parse(options, ticker, session)
    if not rows or not spot or spot <= 0:
        return None
    # Walls are the strikes with the largest gamma exposure (OI x gamma at the
    # close), so far out-of-the-money open interest does not dominate.
    calls: dict[float, float] = {}
    puts: dict[float, float] = {}
    call_oi: dict[float, float] = {}
    put_oi: dict[float, float] = {}
    for is_call, strike, years, oi, iv in rows:
        g = (float(_gamma(np.array([spot]), np.array([strike]), np.array([years]), np.array([iv]))[0, 0])
             if 0.05 <= iv <= 5.0 else 0.0)
        book, raw = (calls, call_oi) if is_call else (puts, put_oi)
        book[strike] = book.get(strike, 0.0) + oi * g
        raw[strike] = raw.get(strike, 0.0) + oi
    above = {k: v for k, v in calls.items() if k >= spot and v > 0}
    below = {k: v for k, v in puts.items() if k <= spot and v > 0}
    cw = max(above, key=above.get) if above else None
    pw = max(below, key=below.get) if below else None
    gf = gamma_flip(rows, spot)
    total = sum(r[3] for r in rows)
    wall_oi = min(call_oi.get(cw, 0) if cw else 0, put_oi.get(pw, 0) if pw else 0)
    out = {
        "cw": cw, "cwp": (cw / spot - 1) if cw else None,
        "pw": pw, "pwp": (pw / spot - 1) if pw else None,
        "gf": round(gf, 2) if gf else None, "gfp": (gf / spot - 1) if gf else None,
        "cwoi": int(call_oi[cw]) if cw else None, "pwoi": int(put_oi[pw]) if pw else None,
        "total_oi": int(total), "age": None, "source": "Cboe delayed quotes (OI as of prior session)",
        "conf": "LOW" if total < LOW_TOTAL_OI or wall_oi < LOW_WALL_OI else "OK",
    }
    return out if cw or pw or gf else None


def fetch_walls(targets: dict[str, float], session: str,
                *, pause: float = 0.25, max_failures: int = 6) -> dict[str, dict[str, Any]]:
    """targets: ticker -> session close."""
    out: dict[str, dict[str, Any]] = {}
    failures = 0
    retry: list[str] = []
    for ticker, spot in list(targets.items()) + [(None, None)]:
        if ticker is None:  # one more try for transient misses (Cboe drops some requests)
            if not retry or failures >= max_failures:
                break
            time.sleep(1.0)
            items, retry = [(t, targets[t]) for t in retry], []
            for t, s in items:
                got = fetch_chain_with_time(t)
                if got is not None:
                    _store(out, t, s, session, got)
                time.sleep(pause)
            break
        if failures >= max_failures:
            break
        got = fetch_chain_with_time(ticker)
        if got is None:
            failures += 1
            retry.append(ticker)
            continue
        failures = 0
        _store(out, ticker, spot, session, got)
        time.sleep(pause)
    print(f"option walls: {len(out)}/{len(targets)} tickers", flush=True)
    return out


def _store(out: dict, ticker: str, spot: float, session: str, got: tuple) -> None:
    chain, stamp = got
    result = walls(chain, ticker=ticker, spot=spot, session=session)
    if result:
        result["asof"] = stamp
        result["age"] = quote_age(stamp, session)
        out[ticker] = result


def update_det(text: str, found: dict[str, dict[str, Any]]) -> str:
    """Fill the existing ticker-detail rows (上値の壁・下値の支え・性質の境目)."""
    marker = "window.DET="
    start = text.find(marker)
    if start < 0 or not found:
        return text
    begin = start + len(marker)
    try:
        obj, end = json.JSONDecoder().raw_decode(text, begin)
    except ValueError:
        return text
    changed = False
    for ticker, opt in found.items():
        if isinstance(obj.get(ticker), dict):
            obj[ticker]["opt"] = opt
            changed = True
    if not changed:
        return text
    blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    return text[:begin] + blob + text[end:]
