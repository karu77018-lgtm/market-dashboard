from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_display as ad  # noqa: E402
import market_internals_ui as mi  # noqa: E402
import putwall_touch as pw  # noqa: E402


def test_real_estate_is_split_from_financials():
    hier = {"金融": [{"sub": "地方銀行", "n": 100, "rs": 60, "br": 10},
                     {"sub": "REIT", "n": 50, "rs": 40, "br": 4},
                     {"sub": "不動産開発", "n": 10, "rs": 20, "br": 0}]}
    split = mi.split_real_estate(hier)
    assert split["金融"] == {"rs": 60, "br": 10, "n": 100}
    assert split["不動産"]["n"] == 60 and split["不動産"]["rs"] == round((40 * 50 + 20 * 10) / 60)
    assert mi.split_real_estate({"金融": [{"sub": "地方銀行", "n": 3, "rs": 1, "br": 0}]})["不動産"] is None


def test_hooks_split_rows_and_shift_calendar():
    calls = []
    mod = types.SimpleNamespace(
        build_index_vs_breadth=lambda mkt: [{"ja": "金融", "tk": "XLF", "x": 93.0, "q": "停滞", "rs": 46, "br": 12, "n": 1041},
                                            {"ja": "不動産", "tk": "XLRE", "x": 92.0, "q": "停滞", "rs": 46, "br": 12, "n": 1041}],
        _index_vs_breadth_card=lambda rows: "",
        build_econ_calendar=lambda asof=None: calls.append(asof) or '<div class="sub">定例スケジュールからの推定（目安）。</div>')
    mi.install_audit_hooks(mod)
    rows = mod.build_index_vs_breadth({"etf_hier": {"金融": [{"sub": "銀行", "n": 9, "rs": 70, "br": 30}]}})
    assert rows[0]["n"] == 9 and rows[1]["n"] == 0
    card = mod._index_vs_breadth_card(rows)
    assert "未提供" in card and "加重平均" in card
    out = mod.build_econ_calendar("2026-10-02")
    assert calls[-1] == pd.Timestamp("2026-10-03") and "10/3〜10/10" in out


def test_history_headline_matches_series(tmp_path: Path):
    (tmp_path / "market-history").mkdir()
    vals = [0.0] * 60 + [1.0] * 20
    dates = [f"d{i:03d}" for i in range(80)]
    (tmp_path / "market-history" / "defensive-2y.json").write_text(json.dumps(
        {"session_date": dates[-1], "dates": dates, "series": {"defensive": vals}}))
    value, label, _ = mi.history_headline(tmp_path, {"files": {"defensive": {"2y": "defensive-2y.json"}}}, "defensive")
    assert value == 1.0 and label == "攻め優勢"


def test_weekly_publish_and_notes():
    page = ('<div class="mut" style="font-size:10.5px;margin:8px 0 4px;font-weight:800">保有12の週次 <button>x</button></div>'
            '<div style="display:flex;flex-wrap:wrap;gap:6px"><span class="chip">A</span></div>'
            '<div>50日線上 <b>32%</b>　・　非常口 <b>未発動</b></div>'
            '<div class="msec-q">カーブ×21EMA（残高・非常口・資産曲線はPositions）</div>'
            '&lt;span&gt;2026-10-02 09:00 JST&lt;/span&gt; RS189 nan'
            '<div class="note">注記：データ未取得のため除外し残り指標で100点満点に再正規化 → credit</div>'
            '<div class="sub">GICS11セクター＋スタイル5本をSPYとの相対力で配置（横=相対力）。<span>x</span></div>'
            '<div class="msec-g rrg-desc" style="display:none">横=RS189百分位中央値（50が市場中央）</div>')
    out = ad.fix_notes(ad.fix_publish_time(ad.fix_weekly(page), "2026-10-02"))
    assert "保有12" not in out and "非常口 <b>" not in out and "アーカイブ" in out
    assert "米国 2026-10-02 終値" in out and "09:00 JST" not in out and "RS189 未取得" in out
    assert "再正規化" not in out and ad.ETF_RRG_DESC in out and "RS189百分位" not in out


def test_changelog_from_ledger():
    ledger = {"sessions": {"2026-10-05": {"best": [{"t": "AAA"}, {"t": "BBB"}], "regime": "on"},
                           "2026-10-06": {"best": [{"t": "BBB"}, {"t": "CCC"}], "regime": "off"}}}
    mc57 = {"history": [{"date": "2026-10-05", "mc57": 40}, {"date": "2026-10-06", "mc57": 30}]}
    card = ad.changelog_html(ledger, mc57, "2026-10-06")
    assert "本命 IN: <b>CCC</b>" in card and "外れた: AAA" in card and "新規OK→新規停止" in card and "40→30" in card
    assert "まだありません" in ad.changelog_html(None, None, "2026-10-06")
    page = ('<div class="card ch-card"><h2>前回からの変化<span class="h2en">Change Log</span></h2>'
            '<div class="sub">初回記録。</div></div><div class="msec">next</div>')
    once = page.replace(page[:page.index('<div class="msec">')], card)
    assert ad.fix_changelog(once, Path("/nonexistent"), "2026-10-06").count("前回からの変化") == 1


def test_put_wall_touch_uses_page_walls():
    d = pd.bdate_range("2026-09-01", periods=20)
    rows = [("AAA", x, 100, 101, 99, 100, 1) for x in d] + [("BBB", x, 50, 51, 49, 50, 1) for x in d]
    frame = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    det = {"AAA": {"rs189": 90, "opt": {"pw": 99.5, "conf": "OK"}},           # 0.25 ATR above the wall
           "BBB": {"rs189": 50, "opt": {"pw": 50.0}}}                           # weak: excluded
    page = ('<script>window.DET=' + json.dumps(det) + ';</script>'
            '<div class="card"><div class="hdr"><h2>支えへの接触 <span class="h2en">Put Wall Touch</span></h2></div>'
            '<div class="sub">取得まだか、該当なし。</div><div class="empty">該当なし</div></div><p>after</p>')
    out = pw.apply(page, frame)
    assert 'data-tkone="AAA"' in out and "BBB</b>" not in out and "<p>after</p>" in out
    assert "壁を取得した2銘柄" in out and pw.apply(out, frame) == out
