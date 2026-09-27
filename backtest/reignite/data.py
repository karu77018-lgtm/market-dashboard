"""Massive download + local parquet cache (resumable, never refetches).

Layout under cache/:
  daily/YYYY-MM-DD.parquet      grouped daily, unadjusted (empty file = holiday)
  ref/tickers.parquet           active + delisted common stock / ADR tickers
  ref/splits.parquet            splits in the study window
  minute/TICKER/YYYY-MM-DD.parquet   1-minute bars 04:00-20:00 ET (may be empty)

The key comes from MASSIVE_API_KEY (environment, then repo .env). It is sent
only in the Authorization header and never logged or written.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config import CACHE

BASE = "https://api.massive.com"
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[2]
MINUTE_COLS = ["m", "o", "h", "l", "c", "v", "vw"]
# Free tier: 5 calls/minute. Override with MASSIVE_CALLS_PER_MIN for paid plans.
CALLS_PER_MIN = float(os.environ.get("MASSIVE_CALLS_PER_MIN", "5"))


def _load_key() -> str:
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip().removeprefix("export ").strip() == "MASSIVE_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        sys.exit("MASSIVE_API_KEY not found in environment or .env")
    return key


class Massive:
    def __init__(self) -> None:
        self._headers = {"Authorization": f"Bearer {_load_key()}", "User-Agent": "reignite-bt"}
        self._gap = 60.0 / CALLS_PER_MIN
        self._last = 0.0
        self.calls = 0

    def get(self, path_or_url: str, **params) -> dict:
        url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        last: object = None
        for attempt in range(6):
            wait = self._gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self._headers), timeout=90) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as exc:
                if exc.code == 429 or exc.code >= 500:
                    last = f"HTTP {exc.code}"
                    time.sleep(min(120, 15 * 2 ** attempt))
                    continue
                body = exc.read()[:300].decode(errors="replace")
                raise RuntimeError(f"Massive {exc.code} for {urllib.parse.urlsplit(url).path}: {body}") from None
            except (urllib.error.URLError, TimeoutError) as exc:
                time.sleep(min(120, 15 * 2 ** attempt))
                last = exc
        raise RuntimeError(f"Massive unreachable for {urllib.parse.urlsplit(url).path}: {last!r}")

    def pages(self, path: str, **params):
        payload = self.get(path, **params)
        while True:
            yield from payload.get("results") or []
            nxt = payload.get("next_url")
            if not nxt:
                return
            payload = self.get(nxt)


# ---------------------------------------------------------------- daily ----

def daily_path(day: str) -> Path:
    return CACHE / "daily" / f"{day}.parquet"


def fetch_daily(api: Massive, start: str, end: str) -> None:
    d = dt.date.fromisoformat(start)
    stop = dt.date.fromisoformat(end)
    while d <= stop:
        path = daily_path(str(d))
        if d.weekday() < 5 and not path.exists():
            p = api.get(f"/v2/aggs/grouped/locale/us/market/stocks/{d}", adjusted="false")
            rows = p.get("results") or []
            df = pd.DataFrame(rows).rename(columns={"T": "ticker"})
            if not df.empty:
                df = df[["ticker", "o", "h", "l", "c", "v", "vw"]]
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            print(f"daily {d}: {len(df)} rows", flush=True)
        d += dt.timedelta(days=1)


def load_daily(start: str, end: str) -> pd.DataFrame:
    frames = []
    for path in sorted((CACHE / "daily").glob("*.parquet")):
        day = path.stem
        if start <= day <= end:
            df = pd.read_parquet(path)
            if not df.empty:
                frames.append(df.assign(date=day))
    if not frames:
        raise SystemExit(f"no daily data cached for {start}..{end}; run fetch first")
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------ reference ----

def fetch_reference(api: Massive, start: str, end: str) -> None:
    ref = CACHE / "ref"
    ref.mkdir(parents=True, exist_ok=True)
    tick_path = ref / "tickers.parquet"
    if not tick_path.exists():
        rows = []
        for kind in ("CS", "ADRC"):
            for active in ("true", "false"):
                for r in api.pages("/v3/reference/tickers", market="stocks", type=kind,
                                   active=active, limit=1000):
                    if active == "false" and (r.get("delisted_utc") or "")[:10] < start:
                        continue
                    rows.append({"ticker": r["ticker"], "type": kind, "active": r.get("active"),
                                 "delisted": (r.get("delisted_utc") or "")[:10] or None})
        pd.DataFrame(rows).to_parquet(tick_path, index=False)
        print(f"tickers: {len(rows)}", flush=True)
    split_path = ref / "splits.parquet"
    if not split_path.exists():
        rows = [{"ticker": r["ticker"], "date": r["execution_date"],
                 "split_from": r["split_from"], "split_to": r["split_to"]}
                for r in api.pages("/v3/reference/splits", **{"execution_date.gte": start,
                                                             "execution_date.lte": end, "limit": 1000})]
        pd.DataFrame(rows, columns=["ticker", "date", "split_from", "split_to"]).to_parquet(split_path, index=False)
        print(f"splits: {len(rows)}", flush=True)


def load_reference() -> tuple[set[str], pd.DataFrame]:
    tickers = pd.read_parquet(CACHE / "ref" / "tickers.parquet")
    splits = pd.read_parquet(CACHE / "ref" / "splits.parquet")
    return set(tickers["ticker"]), splits


# --------------------------------------------------------------- minute ----

def minute_path(ticker: str, day: str) -> Path:
    return CACHE / "minute" / ticker.replace("/", "_") / f"{day}.parquet"


def _ranges(days: list[str], calendar: list[str]) -> list[tuple[str, str]]:
    """Merge a ticker's needed days into runs of consecutive trading days."""
    idx = {d: i for i, d in enumerate(calendar)}
    runs: list[list[str]] = []
    for d in sorted(days):
        if runs and idx[d] - idx[runs[-1][-1]] == 1 and len(runs[-1]) < 20:
            runs[-1].append(d)
        else:
            runs.append([d])
    return [(r[0], r[-1]) for r in runs]


def fetch_minutes(api: Massive, needs: dict[str, set[str]], calendar: list[str]) -> None:
    todo = {t: sorted(d for d in days if not minute_path(t, d).exists()) for t, days in needs.items()}
    todo = {t: d for t, d in todo.items() if d}
    total = sum(len(_ranges(d, calendar)) for d in todo.values())
    print(f"minute: {sum(map(len, todo.values()))} ticker-days in ~{total} calls "
          f"(~{total / CALLS_PER_MIN / 60:.1f} h at {CALLS_PER_MIN:g}/min)", flush=True)
    done = 0
    for ticker, days in sorted(todo.items()):
        for lo, hi in _ranges(days, calendar):
            path = f"/v2/aggs/ticker/{urllib.parse.quote(ticker)}/range/1/minute/{lo}/{hi}"
            rows = list(api.pages(path, adjusted="false", sort="asc", limit=50000))
            df = pd.DataFrame(rows)
            if not df.empty:
                ts = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ET)
                df = df.assign(day=ts.dt.strftime("%Y-%m-%d"), m=ts.dt.hour * 60 + ts.dt.minute)
                if "vw" not in df:
                    df["vw"] = df["c"]
            for d in calendar[calendar.index(lo): calendar.index(hi) + 1]:
                part = df[df["day"] == d][MINUTE_COLS] if not df.empty else pd.DataFrame(columns=MINUTE_COLS)
                out = minute_path(ticker, d)
                out.parent.mkdir(parents=True, exist_ok=True)
                part.reset_index(drop=True).to_parquet(out, index=False)
            done += 1
            if done % 25 == 0:
                print(f"  minute calls {done}/{total}", flush=True)


def load_minutes(ticker: str, day: str) -> pd.DataFrame | None:
    path = minute_path(ticker, day)
    if not path.exists():
        return None
    return pd.read_parquet(path)
