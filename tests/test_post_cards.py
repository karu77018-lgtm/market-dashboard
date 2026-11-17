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


def _q(vals):
    return pd.Series(vals, index=pd.bdate_range("2020-01-01", periods=len(vals)), dtype=float)


def test_timeline_marks_phases_and_outcomes():
    base = [100.0] * 260
    down = [100 - i for i in range(1, 16)]            # -15%: a decline
    up = [85 * 1.06] * 3                               # +6% from the low: first bounce
    fail = [80.0] * 3                                  # new low: that bounce failed
    back = [80 * 1.06] * 3 + [99.0] * 3                # bounce, then back near the high: real bottom
    tl = pq.timeline(_q(base + down + up + fail + back))
    assert [e["ok"] for e in tl["events"]] == [0, 1]
    assert tl["phase"][259] == "h" and tl["phase"][270] == "d" and tl["phase"][275] == "u5"
    assert tl["phase"][-1] == "h"


def test_counts_combine_seed_and_live_record(tmp_path):
    (tmp_path / "seed").mkdir()
    (tmp_path / "track-record").mkdir()
    (tmp_path / pq.COUNTS).write_text(json.dumps({"counts": {"2026-10-01": 3, "2026-10-02": 4}}))
    (tmp_path / "track-record" / "signals.json").write_text(json.dumps(
        {"sessions": {"2026-10-02": {"best": ["A"]}, "2026-10-05": {"best": []}, "2026-12-01": {"best": ["B"]}}}))
    assert pq.load_counts(tmp_path, "2026-11-16") == {"2026-10-01": 3, "2026-10-02": 1, "2026-10-05": 0}


def test_card_has_the_tiles_and_no_ticker_names():
    st = json.loads((ROOT / pq.SEED).read_text(encoding="utf-8"))
    doc, text = pq.card_doc(st, PAGE, ROOT)
    for word in ("QQQと局面", "いまの局面", "本命候補の数", "下げの初動", "先導株の警戒灯", "今回の下げの中身", "FTD・セクター",
                 "予測の答え合わせ", "売買の推奨ではありません", "1680"):
        assert word in doc
    assert "best" not in json.dumps(st) and set(st) == {"session", "q_dates", "q", "phase", "events", "c_dates", "c"}
    assert text.startswith("【米国株 相場の局面") and "参考値" in text


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
