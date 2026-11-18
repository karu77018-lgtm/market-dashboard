import json
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import post_cards as pq  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = (ROOT / "source-mc57.html").read_text(encoding="utf-8")
STATES = "".join(re.findall(r'<script id="(?:phase-check|decline-anatomy|reg-history|ftd-check|sector-heat)-state" '
                            r'type="application/json">.*?</script>', PAGE, re.S))
MINI = ('<html><head></head><body><section id="t-post1"><div class="msec">old</div>'
        '<div class="postwrap"><button class="pfsbtn">x</button><iframe class="postframe" srcdoc="a"></iframe><button class="pfsclose" onclick="pfs(this,0)">✕</button></div>'
        '<p id="after">after</p></section>' + STATES + '</body></html>')


def test_bands_follow_the_sites_pulse_labels():
    assert [pq.band_of(v) for v in (None, 10, 39.9, 40, 54.9, 55, 90)] == [None, "weak", "weak", "mixed", "mixed", "good", "good"]


def test_state_keeps_two_years_with_the_gate_and_breakout_line():
    q = pd.Series(range(1, 900), index=pd.bdate_range("2023-01-02", periods=899), dtype=float)
    q.iloc[-30:] = 100.0                                   # a drop under the 200-day average closes the gate
    health = {"chart": [(str(d.date()), 0.01, 5) for d in q.index[-10:]]}
    st = pq.build_state(q, ROOT, str(q.index[-1].date()), health)
    assert set(st) == {"session", "q_dates", "q", "gate", "bh"} and len(st["q"]) == len(st["gate"]) == pq.DAYS
    assert st["gate"][-40] is True and st["gate"][-1] is False and st["bh"][-1] == [st["session"], 0.01]


def test_counts_are_gated_before_the_live_record(tmp_path):
    (tmp_path / "seed").mkdir()
    (tmp_path / "track-record").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / pq.COUNTS).write_text(json.dumps({"counts": {"2026-10-01": 3, "2026-10-02": 4},
                                                  "sectors": {"2026-10-01": {"Technology": 3}, "2026-10-02": {"Energy": 4}}}))
    (tmp_path / "track-record" / "signals.json").write_text(json.dumps(
        {"sessions": {"2026-10-05": {"best": [{"t": "AAA"}], "regime": "on"}}}))
    (tmp_path / pq.SECTOR_MAP).write_text(json.dumps({"sectors": {"AAA": "Healthcare"}}))
    st = {"session": "2026-10-05", "q_dates": ["2026-10-01", "2026-10-02", "2026-10-05"], "q": [1, 2, 3],
          "gate": [True, False, True], "bh": []}
    s = pq.series(st, tmp_path)
    assert s["c"] == [3, 0, 1] and s["sec"] == [{"Technology": 3}, {}, {"Healthcare": 1}]


def test_screener_counts_read_from_the_page():
    sc = pq.screener_today(PAGE)
    assert "liquid" in sc and "本命" in sc.get("lists", {})


def test_card_shows_market_and_counts_but_no_names_or_rules():
    st = json.loads((ROOT / pq.SEED).read_text(encoding="utf-8"))
    doc, text = pq.card_doc(st, PAGE, ROOT)
    for word in ("新規の可否", "候補の流れ", "ブレイク成功度", "地合いと本命の推移", "本命の出方", "月別の本命",
                 "本命のセクター構成", "地合いの中身", "銘柄・条件は非公開", "売買の推奨ではありません", "1680"):
        assert word in doc
    for word in ("QQQが200日線", "週足SAR", "トレンドテンプレート", "売買代金", "値幅", "下げの中身", "FTD"):
        assert word not in doc and word not in text
    signals = json.loads((ROOT / "track-record" / "signals.json").read_text(encoding="utf-8"))["sessions"]
    names = {n if isinstance(n, str) else n.get("t", "") for s in signals.values() for n in (s.get("best") or [])}
    assert not any(f">{n}<" in doc for n in names if n)
    assert text.startswith("【米国株 地合いと本命")


def test_block_after_original_cards_stable_and_out_of_jev_hash():
    out = pq.apply(MINI, ROOT)
    assert out.index('class="postwrap"') < out.index('id="post-cards"') < out.index('id="after"')
    assert pq.apply(out, ROOT) == out and out.count(pq.STYLE_ID) == 1
    again = pq.apply(str(BeautifulSoup(out, "html.parser")), ROOT)
    assert again.count('id="post-cards"') == 1 and again.count('<span class="pq-end">') == 1
    assert rj.source_hash(out) == rj.source_hash(MINI)
    assert "全画面表示" in out and "投稿文をコピー" in out and pq.embedded_state(out)["session"]


def test_no_publish_tab_keeps_page():
    page = "<html><head></head><body><p>x</p></body></html>"
    assert pq.apply(page, ROOT) == page


def test_share_cards_carry_no_site_names():
    import html as _h
    out = pq.apply(PAGE, ROOT)
    s = out.index('id="t-post1"')
    region = _h.unescape(out[s:out.index("</section>", s)])
    for word in ("MC57", "57銘柄", "マーケットパルス", "Dashboard"):
        assert word not in region
    assert pq.scrub("補助リスク（MC57外） MC57 11。") == "補助リスク（スコア外） 地合いスコア 11。"
