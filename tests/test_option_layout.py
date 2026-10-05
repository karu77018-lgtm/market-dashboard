from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import option_layout as ol  # noqa: E402


def opt(cwp=0.12, pwp=-0.04, gfp=-0.10, conf="OK", spot=100.0):
    lvl = lambda p: None if p is None else round(spot * (1 + p), 2)
    return {"cw": lvl(cwp), "cwp": cwp, "pw": lvl(pwp), "pwp": pwp, "gf": lvl(gfp), "gfp": gfp, "conf": conf}


def test_judge_conditions():
    assert ol.judge(opt()) == (True, [])
    ok, why = ol.judge(opt(cwp=0.025))
    assert not ok and why == ["上値の壁が近い（+2.5%）"]
    assert ol.judge(opt(pwp=-0.107))[1] == ["支えが遠い（−10.7%）"]
    assert ol.judge(opt(gfp=0.03))[1] == ["境目より下（+3.0%）"]
    assert ol.judge(opt(conf="LOW"))[1] == ["建玉が薄い"]
    assert ol.judge(opt(cwp=None))[0] is True  # no call wall above: nothing in the way
    assert ol.judge(opt(pwp=None))[1] == ["下値の支えなし"]
    assert ol.judge(None) == (False, ["オプションなし"])


def test_collect_roles_in_positions_order_each_ticker_once():
    bull = {"sar_up": True}
    swing = {"regime": {"on": True},
             "core": [{"ticker": "AAA", "close": 10, **bull}, {"ticker": "NOPE", "close": 10, "sar_up": False}],
             "late": [{"ticker": "BBB", "close": 20, **bull}],
             "watch": [{"ticker": "CCC", "close": 30}, {"ticker": "AAA", "close": 10}],
             "glead": [{"ticker": "DDD", "close": 40}], "glead_near": [],
             "study": [("GGG", 70.0, "rs189"), ("AAA", 10.0, "rs189"), ("HHH", 80.0, "rs21")]}
    pickup = {"rows": [{"ticker": "EEE", "close": 50, "missing": []},
                       {"ticker": "FFF", "close": 60, "missing": ["a", "b"]}]}
    got = [(c["t"], c["role"]) for c in ol.collect(swing, pickup)]
    assert got == [("AAA", "本命"), ("BBB", "まだ入れる"), ("CCC", "次の候補"), ("DDD", "好位置"), ("EEE", "拾う枠"),
                   ("GGG", "RS上位")]
    stopped = dict(swing, regime={"on": False})
    assert [c["role"] for c in ol.collect(stopped, None)] == ["次の候補", "次の候補", "好位置", "RS上位"]


def test_forward_and_independent_summary():
    days = pd.bdate_range("2026-01-02", periods=41)
    rows = []
    for i, d in enumerate(days):
        rows.append(("UP", d, 100 + i))
        rows.append(("DN", d, 100 - i * 0.5))
    frame = pd.DataFrame(rows, columns=["ticker", "date", "close"])
    led = {"schema": ol.SCHEMA, "days": {}}
    for i in range(25):  # judged daily; UP passes, DN does not
        s = days[i].strftime("%Y-%m-%d")
        ol.record(led, s, [{"t": "UP", "role": "本命", "close": 100 + i, "ok": True, "why": []},
                           {"t": "DN", "role": "次の候補", "close": 100 - i * 0.5, "ok": False, "why": ["x"]}])
    ol.forward(led, frame)
    first = led["days"][days[0].strftime("%Y-%m-%d")]["rows"]
    assert first[0]["r20"] == 0.2 and first[1]["r20"] == -0.1
    assert "r20" not in led["days"][days[24].strftime("%Y-%m-%d")]["rows"][0]  # only 20 sessions later
    summ = ol.summary(led)
    assert summ["ok"]["n"] == 2 and summ["ng"]["n"] == 2  # days 0 and 20, not 25 overlapping ones
    assert summ["ok"]["avg"] > 0 > summ["ng"]["avg"] and summ["since"] == days[0].strftime("%Y-%m-%d")


PAGE = ('<html><head></head><body><section id="t-today">'
        '<div class="msec"><div class="msec-l">① IPOベース</div></div><div class="card">ipo</div>'
        '<div class="msec ds-merged-head"><div class="msec-l">② 支えへの接触（オプション・検証中）</div></div>'
        '<div class="card ds-merged"><div class="hdr"><h2>支えへの接触</h2></div><div class="empty">該当なし</div></div>'
        '</section><section id="t-port"></section></body></html>')


def rows():
    return ol.evaluate([{"t": "MRVL", "role": "本命", "close": 272.29}, {"t": "AMD", "role": "本命", "close": 633.91}],
                       {"MRVL": opt(0.102, -0.045, -0.138, spot=272.29), "AMD": opt(0.025, -0.053, -0.062, spot=633.91)})


def test_apply_replaces_the_old_section_in_place_and_is_idempotent():
    out = ol.apply(PAGE, rows(), {"days": 1, "since": "2026-10-02", "ok": {"n": 0}, "ng": {"n": 0}}, "2026-10-02")
    assert "支えへの接触" not in out and "オプション配置（検証中）" in out
    assert out.index("IPOベース") < out.index("オプション配置") < out.index('<section id="t-port"')
    assert 'data-tkone="MRVL"' in out and "上値の壁 $300（+10.2%）" in out
    assert "外れた候補（1）" in out and "AMD</b> 本命：上値の壁が近い（+2.5%）" in out
    assert "記録 1日分" in out
    again = ol.apply(out, rows(), None, "2026-10-02")
    assert again.count(f'id="{ol.CARD_ID}"') == 1 and again.count(f'id="{ol.MSEC_ID}"') == 1
    assert again.count('id="option-layout-style"') == 1
    assert "次の更新" in ol.apply(PAGE, None, None, None)


def test_display_run_rerenders_latest_recorded_day(tmp_path, monkeypatch):
    (tmp_path / "source-mc57.html").write_text(PAGE, encoding="utf-8")
    led = ol.record({"schema": ol.SCHEMA, "days": {}}, "2026-10-02", rows())
    ol.save_ledger(led, tmp_path)
    monkeypatch.setattr(sys, "argv", ["option_layout.py", "--root", str(tmp_path)])
    assert ol.main() == 0
    out = (tmp_path / "source-mc57.html").read_text(encoding="utf-8")
    assert "MRVL" in out and "② オプション配置（検証中）" in out
    assert json.loads((tmp_path / ol.LEDGER).read_text())["days"]["2026-10-02"]["rows"][0]["t"] == "MRVL"


def test_fetch_walls_retries_transient_misses(monkeypatch):
    import options_walls as ow
    calls = []

    def fake(t, timeout=20.0):
        calls.append(t)
        return None if calls.count(t) == 1 and t == "B" else ([], "2026-10-02 20:00:00")

    monkeypatch.setattr(ow, "fetch_chain_with_time", fake)
    monkeypatch.setattr(ow, "walls", lambda chain, **k: {"cw": 1.0})
    monkeypatch.setattr(ow.time, "sleep", lambda s: None)
    got = ow.fetch_walls({"A": 10.0, "B": 20.0, "C": 30.0}, "2026-10-02")
    assert sorted(got) == ["A", "B", "C"] and calls == ["A", "B", "C", "B"]


def test_positions_tile_shows_the_option_badge_only_when_it_passes():
    import swing_screener as sw
    assert "オプション配置◎" in sw._opt_line({"opt": opt(0.12, -0.04, -0.10)})
    assert "オプション配置◎" not in sw._opt_line({"opt": opt(0.025, -0.04, -0.10)})
