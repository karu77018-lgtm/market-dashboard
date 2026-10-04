from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import market_calendar as mc  # noqa: E402
import probe_massive_confirmation as probe  # noqa: E402


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_known_nyse_holidays_and_early_closes():
    for d in ("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
              "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25", "2027-03-26", "2027-12-24",
              "2025-01-01", "2025-04-18", "2025-06-19", "2025-07-04", "2025-11-27"):
        assert not mc.is_trading_day(date.fromisoformat(d)), d
    assert mc.is_trading_day(date(2021, 12, 31))          # Saturday New Year 2022 is not observed on Fri
    assert mc.is_trading_day(date(2026, 10, 5)) and not mc.is_trading_day(date(2026, 10, 3))
    assert mc.early_close(date(2026, 11, 27)) and mc.early_close(date(2026, 12, 24))
    assert mc.session_close_utc("2026-11-27") == utc(2026, 11, 27, 18, 0)
    assert mc.session_close_utc("2026-10-05") == utc(2026, 10, 5, 20, 0)


def test_latest_completed_session():
    settle = probe.SETTLE
    assert mc.latest_completed_session(utc(2026, 10, 5, 21, 44), settle) == date(2026, 10, 2)
    assert mc.latest_completed_session(utc(2026, 10, 5, 21, 45), settle) == date(2026, 10, 5)
    assert mc.latest_completed_session(utc(2026, 10, 4, 12, 0)) == date(2026, 10, 2)        # Sunday
    assert mc.latest_completed_session(utc(2026, 11, 27, 20, 0), settle) == date(2026, 11, 27)  # early close
    assert mc.latest_completed_session(utc(2026, 11, 27, 12, 0), settle) == date(2026, 11, 25)  # skips Thanksgiving


def test_probe_reruns_when_published_session_is_behind():
    never = lambda s, k: (_ for _ in ()).throw(AssertionError("no network when stale"))
    run, why = probe.decide({"session_date": "2026-10-02", "provider_status": {"massive": "READY"}},
                            utc(2026, 10, 6, 5, 30), "", never)
    assert run and "behind" in why
    run, _ = probe.decide({"session_date": "2026-10-05", "provider_status": {"massive": "READY"}},
                          utc(2026, 10, 6, 5, 30), "k", never)
    assert not run
    run, _ = probe.decide({"session_date": "2026-10-05", "provider_status": {"massive": "PROVISIONAL"}},
                          utc(2026, 10, 6, 5, 30), "k", lambda s, k: s == "2026-10-05")
    assert run
    run, _ = probe.decide({"session_date": "2026-10-05", "provider_status": {}}, utc(2026, 10, 6, 5, 30), "",
                          never)
    assert not run                                         # no key: never calls Massive
