from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import legacy_archive as la  # noqa: E402

PAGE = (
    '<html><head></head><body><div class="wrap">'
    '<div class="todayact" id="taCard"><span class="ta-h">NQトレンド信号</span><span id="taEst">推定</span></div>'
    '<nav><a class="tabx" href="#t-market">Daily</a></nav>'
    '<section id="t-market"><div class="msec"><div class="msec-l">① 結論と行動</div></div>'
    '<div class="sar" id="sarPill">NQトレンド信号</div>'
    '<div class="card"><div class="mkt20-deep"><span>リスク</span><b>信用 —・VIX構造 平穏・非常口判定不可</b></div></div>'
    '<div class="card"><div class="lbnote"><b>面取り</b>：個別が確認できるまでは TQQQ/SOXL の投入帯（50MA上0〜3%）で"面"を取る→旧リーダー確認で個別へ（段階論）。</div></div>'
    '</section>'
    '<section id="t-weekly"><div class="card"><h2>今週の結論</h2><div style="font-size:13px"><b>ゲート基準の来週姿勢</b>（NQ運用レジーム）：<b>攻め継続</b>（青）</div>'
    '<div class="sub">①で来週のイベント、②で今週の地合いと騰落、③でブレッドスとレバ環境、④で口座の結果を確認。</div></div>'
    '<div class="msec"><div class="msec-l">② 今週の地合い</div><div class="msec-q">NQレジームの帯で1週間を振り返る（詳細な推移はDaily）</div></div>'
    '<div class="card"><h2>NQレジームの帯 <span class="h2en">Regime History</span></h2></div>'
    '<div class="card"><h2>週次騰落ボード</h2></div>'
    '<div class="msec"><div class="msec-l">③ 環境の質</div><div class="msec-q">広がり・データ品質・レバ環境</div></div>'
    '<div class="card"><h2>レバレッジ・コンディション（SOXL） <span class="h2en">Leverage</span></h2></div>'
    '</section>'
    '<section id="t-rules"><div class="card" id="rules-card"><div class="rreg on">今日の地合い：新規OK</div></div></section>'
    '<section id="t-port"><div class="card" id="archive-intro">old intro</div><div class="msec archive-msec">Core 12</div></section>'
    '</div></body></html>'
)
LEDGER = {"days": {"2026-10-07": {"target": 0.5, "gold": 0.0}}}


def test_moves_nq_and_leverage_cards_into_the_archive_and_rewords():
    out = la.apply(PAGE, LEDGER)
    port = out[out.index('<section id="t-port"'):]
    for marker in ('id="taCard"', 'id="sarPill"', "NQレジームの帯", "レバレッジ・コンディション"):
        assert out.count(marker) == 1 and marker in port, marker
    assert port.index(la.MSEC_ID) < port.index('id="taCard"') < port.index('id="sarPill"') < port.index("NQレジームの帯")
    assert port.index('id="archive-intro"') < port.index(la.MSEC_ID) < port.index('archive-msec">Core 12')
    assert "TQQQルール" in port[:port.index(la.MSEC_ID)]           # intro refreshed
    daily = out[out.index('<section id="t-market"'):out.index('<section id="t-weekly"')]
    weekly = out[out.index('<section id="t-weekly"'):out.index('<section id="t-rules"')]
    assert "非常口" not in daily and "TQQQ/SOXL" not in daily and "TQQQルール枠" in daily
    assert "NQ" not in weekly and "レバ環境" not in weekly and "SOXL" not in weekly
    assert f'id="{la.STANCE_ID}"' in weekly and "新規OK" in weekly and "TQQQ <b>50%</b>" in weekly
    assert la.apply(out, LEDGER) == out


def test_stance_follows_the_rules_card_and_ledger():
    out = la.apply(PAGE.replace("今日の地合い：新規OK", "今日の地合い：新規停止"), None)
    weekly = out[out.index('<section id="t-weekly"'):out.index('<section id="t-rules"')]
    assert "新規停止" in weekly and "TQQQルール：判定不可" in weekly
