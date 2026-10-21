from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import provider_inputs as pi  # noqa: E402


def _pts(last: str, n: int = 30, value: float = 3.0):
    import pandas as pd
    days = pd.bdate_range(end=last, periods=n)
    return [{"date": d.strftime("%Y-%m-%d"), "value": value + i * .01} for i, d in enumerate(days)]


def _down(*_a, **_k):
    raise pi.ProviderError("provider request failed: maintenance")


def test_fred_down_uses_treasury_and_last_good(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pi, "_get_json", lambda *a, **k: calls.append(1) or _down())
    tre = {sid: _pts("2026-10-21") for sid in ("DGS3MO", "DGS2", "DGS10", "DFII10", "T10YIE", "T10Y2Y")}
    monkeypatch.setattr(pi, "treasury_substitute_series", lambda *a, **k: tre)
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"series": {"BAMLH0A0HYM2": _pts("2026-10-20", value=3.2)}}))
    out = pi.fetch_fred_inputs("k", target_session="2026-10-21", generated_at="t",
                               cache_path=tmp_path / "cache.json", seed_path=seed)
    assert out["status"] == "READY" and out["required_ready"] == 7
    assert len(calls) == 2  # stops calling FRED after two straight failures
    hy = out["series"]["BAMLH0A0HYM2"]
    assert hy["source"].startswith("last good") and hy["last_date"] == "2026-10-20"
    assert out["series"]["DGS10"]["source"] == "US Treasury daily curve"
    assert {s["series_id"] for s in out["substitutions"]} >= {"DGS10", "BAMLH0A0HYM2"}
    assert out["series"]["NFCI"]["status"] == "ERROR"  # optional, no substitute


def test_stale_substitute_still_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(pi, "_get_json", _down)
    monkeypatch.setattr(pi, "treasury_substitute_series", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"series": {"BAMLH0A0HYM2": _pts("2026-09-01")}}))
    with pytest.raises(pi.ProviderError):
        pi.fetch_fred_inputs("k", target_session="2026-10-21", generated_at="t", seed_path=seed)


def test_good_fred_run_refreshes_cache(monkeypatch, tmp_path):
    def ok(_c, _u, params=None, **_k):
        return {"observations": [{"date": p["date"], "value": str(p["value"])} for p in _pts("2026-10-21")]}
    monkeypatch.setattr(pi, "_get_json", ok)
    cache = tmp_path / "cache.json"
    out = pi.fetch_fred_inputs("k", target_session="2026-10-21", generated_at="t", cache_path=cache)
    assert out["status"] == "READY" and not out["substitutions"]
    saved = json.loads(cache.read_text())["series"]
    assert saved["BAMLH0A0HYM2"][-1]["date"] == "2026-10-21"
