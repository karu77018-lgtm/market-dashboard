from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import options_walls as ow  # noqa: E402


def _opt(kind: str, strike: float, oi: float, expiry: str = "261016", iv: float = 0.5, root: str = "AAA") -> dict:
    return {"option": f"{root}{expiry}{kind}{int(strike * 1000):08d}", "open_interest": oi, "iv": iv}


def _chain() -> list[dict]:
    rows = []
    for k in range(80, 121, 5):
        rows.append(_opt("C", k, 1000 + (4000 if k == 105 else 0)))
        rows.append(_opt("P", k, 1000 + (4000 if k == 95 else 0)))
    rows.append(_opt("C", 200, 90000))            # far OTM: must not become the wall
    rows.append(_opt("C", 105, 99999, "270115"))  # beyond 45 days: ignored
    rows.append(_opt("C", 105, 99999, root="AAA1"))  # adjusted root: ignored
    return rows


def test_walls_use_gamma_weighted_oi_inside_horizon():
    w = ow.walls(_chain(), ticker="AAA", spot=100.0, session="2026-10-01")
    assert w["cw"] == 105.0 and abs(w["cwp"] - 0.05) < 1e-9
    assert w["pw"] == 95.0 and abs(w["pwp"] + 0.05) < 1e-9
    assert w["cwoi"] == 5000 and w["conf"] == "OK"
    assert w["gf"] is not None and 80 < w["gf"] < 120


def test_no_chain_gives_no_walls():
    assert ow.walls([], ticker="AAA", spot=100.0, session="2026-10-01") is None


def test_update_det_fills_existing_detail_rows():
    page = 'x<script>window.DET={"AAA":{"opt":null,"px":1},"BBB":{"opt":null}};var y=1;</script>'
    out = ow.update_det(page, {"AAA": {"cw": 105.0}, "ZZZ": {"cw": 1.0}})
    body = out[out.index("window.DET=") + len("window.DET="):out.index(";var y")]
    det = json.loads(body)
    assert det["AAA"]["opt"] == {"cw": 105.0} and det["BBB"]["opt"] is None
    assert out.endswith(";var y=1;</script>")


def test_quote_age_uses_the_real_timestamp():
    assert ow.quote_age("2026-10-05 09:31:00", "2026-10-02") == 3
    assert ow.quote_age(None, "2026-10-02") is None
    assert ow.quote_age("garbage", "2026-10-02") is None


def test_exact_three_percent_previous_day_is_allowed():
    import pandas as pd
    c = pd.Series([100.0, 103.0])
    assert ((c / c.shift(1) - 1).round(9)).iloc[-1] <= 0.03


class _Chain:
    def __init__(self, calls, puts):
        self.calls, self.puts = calls, puts


class _FakeYahoo:
    """yfinance.Ticker stand-in: expiries + option_chain(expiry) -> calls/puts frames."""

    def __init__(self, chains):
        self.chains = chains
        self.asked = []

    @property
    def options(self):
        return tuple(self.chains)

    def option_chain(self, expiry):
        self.asked.append(expiry)
        return self.chains[expiry]


def _frame(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["contractSymbol", "strike", "openInterest", "impliedVolatility"])


def _yahoo_chain():
    calls, puts = [], []
    for k in range(80, 121, 5):
        calls.append((f"AAA261016C{k * 1000:08d}", k, 1000 + (4000 if k == 105 else 0), 0.5))
        puts.append((f"AAA261016P{k * 1000:08d}", k, 1000 + (4000 if k == 95 else 0), 0.5))
    calls.append(("AAA261016C00125000", 125, float("nan"), float("nan")))  # Yahoo leaves gaps as NaN
    far = _Chain(_frame([("AAA270115C00105000", 105, 99999, 0.5)]), _frame([]))
    return {"2026-10-16": _Chain(_frame(calls), _frame(puts)), "2027-01-15": far}


def test_yahoo_chain_matches_the_cboe_shape_and_skips_far_expiries():
    tk = _FakeYahoo(_yahoo_chain())
    options, stamp = ow.fetch_chain_yahoo("AAA", "2026-10-01", tk=tk)
    assert tk.asked == ["2026-10-16"]  # 2027-01-15 is beyond 45 days: never requested
    assert stamp and all(set(o) == {"option", "open_interest", "iv"} for o in options)
    w = ow.walls(options, ticker="AAA", spot=100.0, session="2026-10-01")
    assert w["cw"] == 105.0 and w["pw"] == 95.0 and w["conf"] == "OK"


def test_yahoo_without_listed_options_is_an_answer_not_an_error():
    assert ow.fetch_chain_yahoo("AAA", "2026-10-01", tk=_FakeYahoo({}))[0] == []

    class Broken:
        @property
        def options(self):
            raise RuntimeError("429")
    assert ow.fetch_chain_yahoo("AAA", "2026-10-01", tk=Broken()) is None


def test_yahoo_first_cboe_only_when_yahoo_errors(monkeypatch):
    monkeypatch.setattr(ow, "fetch_chain_yahoo", lambda t, s: None if t == "BAD" else ([], "s"))
    monkeypatch.setattr(ow, "fetch_chain_cboe", lambda t, timeout=20.0: ([], "c"))
    assert ow.fetch_chain_with_time("OK", session="2026-10-01")[2] == ow.YAHOO_SOURCE
    assert ow.fetch_chain_with_time("BAD", session="2026-10-01")[2] == ow.CBOE_SOURCE


def test_a_run_of_errors_pauses_instead_of_dropping_the_rest(monkeypatch):
    # 6 errors in a row in the middle used to end the fetch; later tickers (the
    # RS63/RS21 study groups) were never asked.
    bad = {f"E{i}" for i in range(6)}
    targets = {"A": 1.0, **{t: 1.0 for t in sorted(bad)}, "Z1": 1.0, "Z2": 1.0}
    calls = []

    def fake(t, session=None, timeout=20.0):
        calls.append(t)
        return None if t in bad else ([], "2026-10-02 20:00:00", "test")

    monkeypatch.setattr(ow, "fetch_chain_with_time", fake)
    monkeypatch.setattr(ow, "walls", lambda chain, **k: {"cw": 1.0})
    monkeypatch.setattr(ow.time, "sleep", lambda s: None)
    got = ow.fetch_walls(targets, "2026-10-02")
    assert {"A", "Z1", "Z2"} <= set(got)


def test_a_dead_source_stops_early(monkeypatch):
    calls = []
    monkeypatch.setattr(ow, "fetch_chain_with_time", lambda t, session=None, timeout=20.0: calls.append(t))
    monkeypatch.setattr(ow.time, "sleep", lambda s: None)
    assert ow.fetch_walls({f"T{i}": 1.0 for i in range(50)}, "2026-10-02") == {}
    assert len(calls) == 6
