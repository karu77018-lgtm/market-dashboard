from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jev_backfill as jb  # noqa: E402


def test_masking_hides_ticker_and_company_names():
    names = jb.name_variants("Vertiv Holdings Co.")
    text = "Vertiv Holdings (NYSE: VRT) raises guidance; $VRT and Vertiv shine"
    out = jb.mask_text(text, "VRT", names)
    assert "VRT" not in out and "Vertiv" not in out and "XXXX" in out


def test_features_and_state_are_point_in_time():
    cut = datetime(2024, 3, 1, 21, tzinfo=timezone.utc)
    docs = [{"published": datetime(2024, 2, 20, tzinfo=timezone.utc), "title": "Acme raises full-year guidance",
             "description": "record revenue; new AI data center contract", "publisher": "P1", "n_tickers": 1},
            {"published": datetime(2023, 12, 1, tzinfo=timezone.utc), "title": "Acme analyst upgrade",
             "description": "", "publisher": "P2", "n_tickers": 3}]
    f = jb.news_features(docs, cut)
    assert f["n30"] == 1 and f["n_prior90"] == 1 and f["kw_guidance_up"] == 1 and f["kw_theme"] == 1
    ev = {"ticker": "ACME", "company_name": "Acme Corp", "session_date": "2024-03-01", "rs21": 90, "rs63": 70,
          "rs189": 50, "price": 10.0, "return_5d_pct": 3.0, "distance_from_52w_high_pct": -20.0}
    masked = jb.build_state(ev, docs, cut, masked=True)
    assert masked["ticker"] == "XXXX" and masked["company_name"] is None
    assert len(masked["evidence"]["documents"]) == 1 and "Acme" not in masked["evidence"]["documents"][0]["title"]
    plain = jb.build_state(ev, docs, cut, masked=False)
    assert plain["ticker"] == "ACME" and "Acme" in plain["evidence"]["documents"][0]["title"]


def test_cutoff_is_the_real_nyse_close():
    iso = lambda d: jb.session_close_utc(d).isoformat()
    assert iso("2023-01-04") == "2023-01-04T21:00:00+00:00"      # winter: 16:00 ET
    assert iso("2023-03-14") == "2023-03-14T20:00:00+00:00"      # daylight time: 16:00 ET = 20:00Z
    assert iso("2023-11-24") == "2023-11-24T18:00:00+00:00"      # day after Thanksgiving 13:00 ET
    assert iso("2023-07-03") == "2023-07-03T17:00:00+00:00"      # July 3 early close
    assert iso("2024-12-24") == "2024-12-24T18:00:00+00:00"      # Christmas Eve early close
    assert iso("2020-07-03") == "2020-07-03T20:00:00+00:00"      # July 4 on Saturday: no early close rule


class _Resp:
    def __init__(self, payload):
        self.status_code, self._p, self.headers = 200, payload, {}

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _Resp(self.pages.pop(0))


def _row(day: int, title: str):
    return {"published_utc": f"2024-02-{day:02d}T12:00:00Z", "title": title, "tickers": ["A"], "publisher": {"name": "P"}}


def test_news_history_follows_pagination_and_flags_truncation():
    import pytest
    cut = datetime(2024, 3, 1, 21, tzinfo=timezone.utc)
    nxt = "https://api.massive.com/v2/reference/news?cursor=abc"
    client = _Client([{"results": [_row(20, "a")], "next_url": nxt}, {"results": [_row(10, "b")]}])
    docs, truncated = jb.fetch_history(client, ticker="A", api_key="K", cutoff=cut, timeout=1)
    assert [d["title"] for d in docs] == ["a", "b"] and not truncated
    assert client.calls[1] == (nxt, {"apiKey": "K"})
    client = _Client([{"results": [_row(20, "a")], "next_url": nxt}] * 3)
    docs, truncated = jb.fetch_history(client, ticker="A", api_key="K", cutoff=cut, timeout=1, max_pages=2)
    assert truncated and jb.news_features(docs, cut, truncated)["surge"] is None
    client = _Client([{"results": [], "next_url": "https://evil.example/v2/reference/news?c=1"}])
    with pytest.raises(jb.ShadowRunError):
        jb.fetch_history(client, ticker="A", api_key="K", cutoff=cut, timeout=1)
