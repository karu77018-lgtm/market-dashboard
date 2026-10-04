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
