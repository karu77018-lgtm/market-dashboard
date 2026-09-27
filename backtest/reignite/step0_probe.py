"""Step 0: probe what the configured Massive plan can actually return.

Run locally from the repository root:

    python backtest/reignite/step0_probe.py

The key is read from MASSIVE_API_KEY (environment first, then ./.env). It is
sent only in the Authorization header, never placed in a URL, and never
printed or written to disk. The script only reads; it changes nothing on the
account. Output: a summary on stdout and backtest/reignite/cache/step0_report.json.
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

BASE = "https://api.massive.com"
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "cache" / "step0_report.json"
# Years back to test for history depth.
DEPTHS = [0, 1, 2, 3, 5, 7, 10, 15, 20]


def load_key() -> str:
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


class Client:
    def __init__(self, key: str):
        self._headers = {"Authorization": f"Bearer {key}", "User-Agent": "reignite-step0"}
        self.calls = 0
        self.throttled = 0
        self.first_429_at_call: int | None = None
        self.rate_headers: dict[str, str] = {}

    def get(self, path: str, **params) -> tuple[int, dict]:
        url = f"{BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            self.calls += 1
            req = urllib.request.Request(url, headers=self._headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self._note_headers(resp.headers)
                    return resp.status, json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as exc:
                self._note_headers(exc.headers)
                body = exc.read()
                if exc.code == 429:
                    self.throttled += 1
                    if self.first_429_at_call is None:
                        self.first_429_at_call = self.calls
                    time.sleep(65 if attempt else 15)
                    continue
                try:
                    return exc.code, json.loads(body or b"{}")
                except json.JSONDecodeError:
                    return exc.code, {"error": body[:200].decode(errors="replace")}
            except urllib.error.URLError as exc:
                return 0, {"error": f"network: {exc.reason}"}
        return 429, {"error": "rate limited after retries"}

    def _note_headers(self, headers) -> None:
        for name, value in (headers or {}).items():
            if "ratelimit" in name.lower() or name.lower() == "retry-after":
                self.rate_headers[name] = value


def weekday_near(years_back: int, today: dt.date) -> dt.date:
    """A Wednesday roughly `years_back` years before `today` (avoids most holidays)."""
    d = today.replace(year=today.year - years_back) if years_back else today - dt.timedelta(days=7)
    while d.weekday() != 2:
        d -= dt.timedelta(days=1)
    return d


def ok(status: int, payload: dict) -> bool:
    return status == 200 and payload.get("status") not in {"NOT_AUTHORIZED", "ERROR"}


def reason(status: int, payload: dict) -> str:
    return f"{status} {payload.get('status', '')} {payload.get('message') or payload.get('error') or ''}".strip()


def probe_grouped(c: Client, day: dt.date) -> dict:
    s, p = c.get(f"/v2/aggs/grouped/locale/us/market/stocks/{day}", adjusted="false")
    n = p.get("resultsCount") or len(p.get("results") or [])
    return {"date": str(day), "ok": ok(s, p) and n > 0, "rows": n, "detail": reason(s, p)}


def probe_minute(c: Client, ticker: str, day: dt.date) -> dict:
    s, p = c.get(f"/v2/aggs/ticker/{ticker}/range/1/minute/{day}/{day}",
                 adjusted="false", sort="asc", limit=50000)
    bars = p.get("results") or []
    out = {"ticker": ticker, "date": str(day), "ok": ok(s, p) and bool(bars),
           "bars": len(bars), "detail": reason(s, p)}
    if bars:
        first = dt.datetime.fromtimestamp(bars[0]["t"] / 1000, ET)
        last = dt.datetime.fromtimestamp(bars[-1]["t"] / 1000, ET)
        out |= {"first_bar_et": first.strftime("%H:%M"), "last_bar_et": last.strftime("%H:%M"),
                "premarket": first.time() < dt.time(9, 30), "afterhours": last.time() >= dt.time(16, 0)}
    return out


def probe_ticks(c: Client, kind: str, ticker: str, day: dt.date) -> dict:
    s, p = c.get(f"/v3/{kind}/{ticker}", timestamp=str(day), limit=5)
    rows = p.get("results") or []
    return {"kind": kind, "ticker": ticker, "date": str(day), "ok": ok(s, p) and bool(rows),
            "rows": len(rows), "sample_fields": sorted(rows[0])[:12] if rows else [],
            "detail": reason(s, p)}


def probe_reference(c: Client, today: dt.date) -> dict:
    out: dict = {}
    s, p = c.get("/v3/reference/tickers", market="stocks", active="false", limit=1000)
    rows = p.get("results") or []
    out["delisted_list"] = {"ok": ok(s, p) and bool(rows), "first_page_rows": len(rows),
                            "has_next_page": bool(p.get("next_url")),
                            "sample": [{k: r.get(k) for k in ("ticker", "type", "delisted_utc")}
                                       for r in rows[:3]], "detail": reason(s, p)}
    past = weekday_near(3, today)
    s, p = c.get("/v3/reference/tickers", market="stocks", date=str(past), limit=5)
    out["point_in_time_list"] = {"date": str(past), "ok": ok(s, p) and bool(p.get("results")),
                                 "detail": reason(s, p)}
    shares = []
    targets = [("AAPL", weekday_near(3, today)), ("AAPL", weekday_near(8, today))]
    delisted = next((r for r in rows if r.get("type") == "CS" and r.get("delisted_utc")), None)
    if delisted:
        when = dt.date.fromisoformat(delisted["delisted_utc"][:10]) - dt.timedelta(days=30)
        targets.append((delisted["ticker"], when))
    for ticker, day in targets:
        s, p = c.get(f"/v3/reference/tickers/{urllib.parse.quote(ticker)}", date=str(day))
        r = p.get("results") or {}
        shares.append({"ticker": ticker, "date": str(day), "ok": ok(s, p) and bool(r),
                       "share_class_shares_outstanding": r.get("share_class_shares_outstanding"),
                       "weighted_shares_outstanding": r.get("weighted_shares_outstanding"),
                       "detail": reason(s, p)})
    out["shares_outstanding_point_in_time"] = shares
    s, p = c.get("/v3/reference/splits", limit=1)
    out["splits"] = {"ok": ok(s, p), "detail": reason(s, p)}
    # Float endpoint (may not exist or may need a higher tier).
    s, p = c.get("/stocks/vX/float", ticker="AAPL", limit=1)
    out["float_endpoint"] = {"ok": ok(s, p) and bool(p.get("results")), "detail": reason(s, p)}
    return out


def depth(results: list[dict]) -> str | None:
    good = [r["date"] for r in results if r["ok"]]
    return min(good) if good else None


def main() -> None:
    c = Client(load_key())
    today = dt.datetime.now(ET).date()
    report: dict = {"run_at_et": dt.datetime.now(ET).isoformat(timespec="seconds")}
    days = [weekday_near(y, today) for y in DEPTHS]

    print("grouped daily ...", flush=True)
    report["grouped_daily"] = [probe_grouped(c, d) for d in days]
    print("1-minute bars ...", flush=True)
    report["minute_bars"] = [probe_minute(c, "SPY", d) for d in days]
    print("trades / quotes ...", flush=True)
    report["ticks"] = [probe_ticks(c, k, "SPY", d) for k in ("trades", "quotes")
                       for d in (days[0], days[DEPTHS.index(3)], days[DEPTHS.index(10)])]
    print("reference ...", flush=True)
    report["reference"] = probe_reference(c, today)
    report["rate_limit"] = {"calls": c.calls, "http_429": c.throttled,
                            "first_429_at_call": c.first_429_at_call,
                            "headers_seen": c.rate_headers}

    g, m = depth(report["grouped_daily"]), depth(report["minute_bars"])
    report["summary"] = {"grouped_daily_earliest_ok": g, "minute_earliest_ok": m,
                         "minute_has_extended_hours": any(r.get("premarket") and r.get("afterhours")
                                                          for r in report["minute_bars"]),
                         "trades_ok": any(r["ok"] for r in report["ticks"] if r["kind"] == "trades"),
                         "quotes_ok": any(r["ok"] for r in report["ticks"] if r["kind"] == "quotes")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    def line(r: dict, extra: str = "") -> str:
        return f"  {r['date']}  {'OK ' if r['ok'] else 'NG '} {extra or r['detail']}"

    print("\n== grouped daily (all tickers, 1 call/day) ==")
    for r in report["grouped_daily"]:
        print(line(r, f"rows={r['rows']}" if r["ok"] else ""))
    print("== 1-minute bars SPY ==")
    for r in report["minute_bars"]:
        print(line(r, f"bars={r['bars']} {r.get('first_bar_et')}-{r.get('last_bar_et')}" if r["ok"] else ""))
    print("== trades / quotes SPY ==")
    for r in report["ticks"]:
        print(f"  {r['kind']:<7}" + line(r).lstrip())
    ref = report["reference"]
    print("== reference ==")
    print(f"  delisted list: {'OK' if ref['delisted_list']['ok'] else 'NG'} "
          f"(first page {ref['delisted_list']['first_page_rows']}, more={ref['delisted_list']['has_next_page']})")
    print(f"  point-in-time list: {'OK' if ref['point_in_time_list']['ok'] else 'NG'}")
    for r in ref["shares_outstanding_point_in_time"]:
        print(f"  shares {r['ticker']} @ {r['date']}: {r['share_class_shares_outstanding']}"
              f" / weighted {r['weighted_shares_outstanding']}  ({'OK' if r['ok'] else r['detail']})")
    print(f"  float endpoint: {'OK' if ref['float_endpoint']['ok'] else ref['float_endpoint']['detail']}")
    print(f"== rate limit == calls={c.calls} 429s={c.throttled} first_429_at={c.first_429_at_call}")
    print(f"\nreport written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
