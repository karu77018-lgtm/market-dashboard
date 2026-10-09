from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import track_record as tr  # noqa: E402


def page(best: str | None, regime: str = "on") -> str:
    tk = f'<button class="cp" data-tk="{best}" onclick="copyTk(event,this)">コピー</button>' if best else ""
    card = ("" if best is None else
            f'<div class="card" id="mc57-swing-screener" data-regime="{regime}">'
            f'<div class="sw-sec"><span>本命<small>n</small></span>{tk}</div>'
            '<div class="sw-sec"><span>次の候補<small>n</small></span><button class="cp" data-tk="ZZZ">x</button></div></div>')
    return ("<html><head></head><body><nav><a class=\"tabx\" href=\"#t-market\">Daily</a>"
            "<a class=\"tabx\" href=\"#t-alloc\" onclick=\"tab('t-alloc',this);return false;\">Positions</a>"
            "<a class=\"tabx\" href=\"#t-today\">Setups</a></nav>"
            f'<section id="t-market"></section><section id="t-alloc">{card}</section>'
            '<section id="t-today"></section></body></html>')


def bars(rows: list[tuple]) -> pd.DataFrame:
    """rows: (date, open, high, low, close) -> one ticker, date-indexed."""
    f = pd.DataFrame([(pd.Timestamp(d), o, h, lo, c) for d, o, h, lo, c in rows],
                     columns=["date", "open", "high", "low", "close"])
    return f.set_index("date")


D = [d.date().isoformat() for d in pd.bdate_range("2026-01-01", periods=80)]
FLAT = [(D[k], 100.0, 100.5, 99.5, 100.0) for k in range(30)]  # history; EMA of lows ~= 99.5


def run(rows, qqq=None, session=D[29]):
    state = {"ticker": "AAA", "session": session, "status": "約定待ち"}
    return tr.advance(state, bars(rows), qqq or {})


def test_record_freezes_first_good_publication(tmp_path: Path):
    led = tr.new_ledger()
    tr.record(led, page(None), "2026-10-05", {}, now="t0")                   # card missing: not frozen as 0
    assert "2026-10-05" not in led["sessions"] and led["failures"][0]["reason"] == "no_card"
    tr.record(led, page("AAA,BBB"), "2026-10-05", {"AAA": 10.0}, now="t1")
    tr.record(led, page("AAA,BBB"), "2026-10-05", {}, now="t2")
    tr.record(led, page("CCC"), "2026-10-05", {}, now="t3")
    day = led["sessions"]["2026-10-05"]
    assert [r["t"] for r in day["best"]] == ["AAA", "BBB"] and day["recorded_at"] == "t1"
    assert day["revisions"] == 1 and [r["t"] for r in day["latest"]] == ["CCC"]
    assert day["regime"] == "on" and day["rule"] == "pre-v4-unversioned" and led["start"] == "2026-10-05"
    assert tr.published_best(page("")) == ("ok", [])                       # real zero is still recorded
    tr.record(led, page("", regime="off"), "2026-10-06", {}, now="t4")
    assert led["sessions"]["2026-10-06"]["best"] == [] and led["sessions"]["2026-10-06"]["regime"] == "off"


def test_corrupt_ledger_is_never_overwritten(tmp_path: Path):
    path = tmp_path / tr.LEDGER
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    with pytest.raises(tr.LedgerError):
        tr.load(path)
    out = tr.run(page("AAA"), pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"]),
                 "2026-10-05", tmp_path)
    assert path.read_text() == "{broken" and "記録ファイルを読めなかった" in out


def test_same_amount_adds_at_next_open():
    rows = FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 111, 111, 110.5, 111), (D[32], 111, 121, 111, 121),
                   (D[33], 121, 130, 121, 130)]
    s = run(rows)
    m = tr.metrics(s)
    assert m["entry"] == 100 and s["adds"] == 2 and s["invested"] == 2.0 + 1.0
    expected = (1 / 100 + 1 / 111 + 1 / 121) * 130 / 3 - 1               # same dollars at 100, 111, 121
    assert abs(m["ret_add"] - expected) < 1e-12 and abs(m["ret_add"] - 0.181850) < 1e-5


def test_exact_ten_percent_triggers_add():
    rows = FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 100, 110, 100, 100 * 1.1), (D[32], 110, 110, 109, 110)]
    s = run(rows)
    assert s["triggered"] == [0] and s["adds"] == 1


def test_ema_break_sells_next_open_not_same_close():
    rows = FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 99.9, 100, 99.4, 99.5)]
    s = run(rows)
    assert not s.get("closed") and s["status"] == "売り待ち（21EMA割れ）"
    s = tr.advance(s, bars(rows + [(D[32], 80, 80, 79, 79)]), {})
    assert s["closed"] and s["exit"] == 80 and s["exit_day"] == D[32]
    assert abs(tr.metrics(s)["ret"] - (-0.20)) < 1e-12


def test_stops_and_gap():
    rows = FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 99, 99, 91, 95)]
    s = run(rows)
    assert s["closed"] and s["status"] == "損切り −8%" and abs(s["exit"] - 92) < 1e-9
    gap = run(FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 90, 91, 89, 90)])
    assert gap["status"] == "損切り（窓）" and gap["exit"] == 90
    assert run(FLAT)["status"] == "約定待ち"


def test_qqq_uses_same_execution_times():
    qqq = {D[29]: {"open": 99, "close": 100}, D[30]: {"open": 120, "close": 120}, D[31]: {"open": 120, "close": 120}}
    s = run(FLAT + [(D[30], 100, 100.4, 99.9, 100), (D[31], 100, 100.4, 99.9, 100)], qqq)
    m = tr.metrics(s)
    assert m["ret"] == 0 and m["qqq"] == 0                               # both flat over the held period


def test_closed_trades_survive_shorter_history_and_dropped_ticker(tmp_path: Path):
    led = tr.new_ledger()
    tr.record(led, page("AAA"), D[29], {}, now="t")
    rows = FLAT + [(D[30], 100, 100, 99.9, 100), (D[31], 99, 99, 91, 95)]
    frame = bars(rows).reset_index().assign(ticker="AAA", volume=1)
    tr.advance_all(led, frame, {})
    before = tr.trades_for_display(led)
    assert before[0]["closed"] and tr.summary(before)["closed"] == 1
    tr.advance_all(led, frame.tail(5), {})                                # 260-day window moved on
    tr.advance_all(led, frame[frame["ticker"] == "ZZZ"], {})              # ticker left the universe
    after = tr.trades_for_display(led)
    assert after == before


def test_median_is_the_true_median():
    trades = [{"closed": True, "ret": -0.08, "ret_add": 0, "days": 1, "ticker": "A", "session": "s"},
              {"closed": True, "ret": 0.20, "ret_add": 0, "days": 1, "ticker": "B", "session": "s"}]
    assert abs(tr.summary(trades)["median"] - 0.06) < 1e-12


def test_run_persists_and_tab_is_idempotent(tmp_path: Path):
    frame = bars(FLAT).reset_index().assign(ticker="AAA", volume=1)
    out = tr.run(page("AAA"), frame, D[29], tmp_path)
    saved = json.loads((tmp_path / tr.LEDGER).read_text())
    assert saved["schema"] == tr.SCHEMA and f"{D[29]}:AAA" in saved["trades"]
    assert out.index('id="t-record"') > out.index('id="t-alloc"') and out.index('id="t-record"') < out.index('id="t-today"')
    nav = out[out.index("<nav>"):out.index("</nav>")]
    assert nav.index('href="#t-record"') > nav.index('href="#t-alloc"') > 0
    assert "約定待ち" in out and f'data-rule="{tr.RULE_ID}"' in out
    again = tr.render_only(out, tmp_path)
    assert again.count('id="t-record"') == 1 and again.count('<a class="tabx" href="#t-record"') == 1
    assert tr.render_only(again, tmp_path) == again
