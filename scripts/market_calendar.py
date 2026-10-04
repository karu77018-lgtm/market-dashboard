"""NYSE trading calendar (rule-based, no network).

Full-day holidays: New Year's Day, MLK Day, Presidents' Day, Good Friday,
Memorial Day, Juneteenth (from 2022), Independence Day, Labor Day,
Thanksgiving, Christmas.  Saturday holidays are observed on Friday and Sunday
holidays on Monday, except that New Year's Day on a Saturday is not observed.
Early (13:00 New York) closes: July 3 when July 4 falls Tue-Fri, the day after
Thanksgiving, and Christmas Eve on Mon-Thu.

One-off closures (national days of mourning, weather) are not modelled; callers
treat the calendar as "earliest possible", never as proof that data exists.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = (date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(year, month, (h + l - 7 * m + 114) % 31 + 1)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=None)
def holidays(year: int) -> frozenset[date]:
    days = {
        _nth_weekday(year, 1, 0, 3),               # MLK
        _nth_weekday(year, 2, 0, 3),               # Presidents'
        _easter(year) - timedelta(days=2),         # Good Friday
        _last_weekday(year, 5, 0),                 # Memorial
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),               # Labor
        _nth_weekday(year, 11, 3, 4),              # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:                    # Saturday New Year is not observed
        days.add(_observed(new_year))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))
    return frozenset(days)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def early_close(day: date) -> bool:
    if day.month == 7 and day.day == 3 and day.weekday() < 5 and date(day.year, 7, 4).weekday() in (1, 2, 3, 4):
        return True
    if day == _nth_weekday(day.year, 11, 3, 4) + timedelta(days=1):
        return True
    return day.month == 12 and day.day == 24 and day.weekday() < 4


def session_close_utc(session_date: str | date) -> datetime:
    """The session's NYSE close as an aware UTC datetime (DST and early closes)."""
    day = date.fromisoformat(session_date) if isinstance(session_date, str) else session_date
    close = dtime(13, 0) if early_close(day) else dtime(16, 0)
    return datetime.combine(day, close, tzinfo=NEW_YORK).astimezone(timezone.utc)


def latest_completed_session(now: datetime, settle: timedelta = timedelta(0)) -> date:
    """Most recent trading day whose close (+ ``settle``) is at or before ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = now.astimezone(NEW_YORK).date()
    for _ in range(15):
        if is_trading_day(day) and session_close_utc(day) + settle <= now:
            return day
        day -= timedelta(days=1)
    raise RuntimeError("no trading day in the last 15 days")
