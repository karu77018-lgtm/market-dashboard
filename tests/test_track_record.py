from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import track_record as tr  # noqa: E402


def page(best: str) -> str:
    tk = f'<button class="cp" data-tk="{best}" onclick="copyTk(event,this)">コピー</button>' if best else ""
    return ("<html><head></head><body><nav><a class=\"tabx\" href=\"#t-market\">Daily</a>"
            "<a class=\"tabx\" href=\"#t-alloc\" onclick=\"tab('t-alloc',this);return false;\">Positions</a>"
            "<a class=\"tabx\" href=\"#t-today\">Setups</a></nav>"
            '<section id="t-market"></section><section id="t-alloc"><div class="card" id="mc57-swing-screener">'
            f'<div class="sw-sec"><span>本命<small>n</small></span>{tk}</div>'
            '<div class="sw-sec"><span>次の候補<small>n</small></span><button class="cp" data-tk="ZZZ">x</button></div>'
            '</div></section><section id="t-today"></section></body></html>')


def bars(rows: list[tuple]) -> pd.DataFrame:
    """rows: (date, open, high, low, close) for ticker AAA."""
    return pd.DataFrame([("AAA", pd.Timestamp(d), o, h, l, c, 1e6) for d, o, h, l, c in rows],
                        columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def test_record_freezes_first_publication(tmp_path: Path):
    path = tmp_path / "signals.json"
    tr.record(page("AAA,BBB"), path, "2026-10-05", {"AAA": 10.0}, now="t1")
    tr.record(page("AAA,BBB"), path, "2026-10-05", {}, now="t2")
    led = tr.record(page("CCC"), path, "2026-10-05", {}, now="t3")
    day = led["sessions"]["2026-10-05"]
    assert [r["t"] for r in day["best"]] == ["AAA", "BBB"] and day["recorded_at"] == "t1"
    assert day["revisions"] == 1 and [r["t"] for r in day["latest"]] == ["CCC"]
    assert json.loads(path.read_text())["start"] == "2026-10-05"
    assert tr.published_best(page("")) == []


def test_trade_uses_next_open_and_rule_exits():
    d = pd.bdate_range("2026-01-01", periods=60)
    rising = [(d[k].date().isoformat(), 100 + k, 101 + k, 99.5 + k, 100.5 + k) for k in range(40)]
    frame = bars(rising + [(d[40].date().isoformat(), 125, 125, 90, 95)])
    t = tr._trade(frame.set_index("date")[["open", "high", "low", "close"]], d[30].date().isoformat())
    assert t["entry"] == 131 and t["entry_day"] == d[31].date().isoformat()
    assert t["status"] == "損切り −8%" and abs(t["last"] - 131 * 0.92) < 1e-9 and t["closed"]
    gap = bars(rising + [(d[40].date().isoformat(), 118, 119, 110, 112)])
    g = tr._trade(gap.set_index("date")[["open", "high", "low", "close"]], d[30].date().isoformat())
    assert g["status"] == "損切り（窓）" and g["last"] == 118
    pending = tr._trade(frame.set_index("date")[["open", "high", "low", "close"]], d[40].date().isoformat())
    assert pending == {"status": "約定待ち"}


def test_adds_and_open_position():
    d = pd.bdate_range("2026-01-01", periods=50)
    up = [(d[k].date().isoformat(), 100 * 1.01 ** k, 100 * 1.01 ** k * 1.005, 100 * 1.01 ** k * 0.995,
           100 * 1.01 ** k) for k in range(50)]
    t = tr._trade(bars(up).set_index("date")[["open", "high", "low", "close"]], d[10].date().isoformat())
    assert t["status"] == "保有中" and not t["closed"] and t["adds"] == 2
    assert t["ret"] > 0 and t["ret_add"] < t["ret"]  # later adds at higher prices dilute the % return


def test_tab_inserted_after_positions_and_idempotent(tmp_path: Path):
    led = tr.record(page("AAA"), tmp_path / "s.json", "2026-10-05", {"AAA": 1.0}, now="t")
    out = tr.apply(page("AAA"), led, [{"ticker": "AAA", "session": "2026-10-05", "status": "約定待ち"}])
    assert out.index('id="t-record"') > out.index('id="t-alloc"') and out.index('id="t-record"') < out.index('id="t-today"')
    nav = out[out.index("<nav>"):out.index("</nav>")]
    assert nav.index('href="#t-record"') > nav.index('href="#t-alloc"') > 0
    assert "約定待ち" in out and "記録開始 2026-10-05" in out
    again = tr.apply(out, led, [])
    assert again.count('id="t-record"') == 1 and again.count('<a class="tabx" href="#t-record"') == 1
    assert "まだ記録がありません" in again
