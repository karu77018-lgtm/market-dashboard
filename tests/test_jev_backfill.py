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
