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


def test_counts_combine_seed_and_live_record(tmp_path):
    (tmp_path / "seed").mkdir()
    (tmp_path / "track-record").mkdir()
    (tmp_path / pq.COUNTS).write_text(json.dumps({"counts": {"2026-10-01": 3, "2026-10-02": 4}}))
    (tmp_path / "track-record" / "signals.json").write_text(json.dumps(
        {"sessions": {"2026-10-02": {"best": ["A"]}, "2026-10-05": {"best": []}, "2026-12-01": {"best": ["B"]}}}))
    assert pq.load_counts(tmp_path, "2026-11-16") == {"2026-10-01": 3, "2026-10-02": 1, "2026-10-05": 0}


def test_state_keeps_two_years_of_qqq_only():
    q = pd.Series(range(1, 700), index=pd.bdate_range("2024-01-01", periods=699), dtype=float)
    st = pq.build_state(q, ROOT, str(q.index[-10].date()))
    assert set(st) == {"session", "q_dates", "q"} and len(st["q"]) == pq.DAYS and st["q_dates"][-1] == st["session"]


def test_card_shows_market_and_counts_but_no_names_or_decline_analysis():
    st = json.loads((ROOT / pq.SEED).read_text(encoding="utf-8"))
    doc, text = pq.card_doc(st, PAGE, ROOT)
    for word in ("地合いと本命の推移", "いまの地合い", "本命が出た日の割合", "直近60日", "広がり", "資金の向き先",
                 "銘柄とルールは非公開", "売買の推奨ではありません", "1680"):
        assert word in doc
    for word in ("下げの中身", "警戒灯", "FTD", "本物の底になる率"):
        assert word not in doc
    signals = json.loads((ROOT / "track-record" / "signals.json").read_text(encoding="utf-8"))["sessions"]
    names = {n if isinstance(n, str) else n.get("ticker", "") for s in signals.values() for n in (s.get("best") or [])}
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
