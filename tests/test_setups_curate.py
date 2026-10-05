from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import breadth_refresh as br  # noqa: E402
import enhance_source_mc57 as en  # noqa: E402
import setups_curate as sc  # noqa: E402


def msec(title):
    return f'<div class="msec"><div class="msec-l">{title}<span class="msec-en">X</span></div><div class="msec-q">q</div></div>'


def card(title):
    return f'<div class="card"><div class="hdr"><h2>{title}</h2></div><div class="sub">s</div></div>'


PAGE = ('<html><head></head><body><section id="t-today">' + card("銘柄検索")
        + msec("① 発火前（構造）") + card("発火前") + msec("② 支えへの接触（オプション）") + card("支えへの接触")
        + msec("③ コンフルエンス") + card("エントリー候補ボード") + msec("④ 発火トリガー") + card("PP") + card("本日のピックアップ")
        + msec("⑥ 底打ち") + card("底打ち") + msec("⑦ リーダー母集団") + card("リーダー監視")
        + '</section><section id="t-port"><div class="card" id="archive-intro">a</div></section>'
          "<footer class='disc'>d</footer></body></html>")


def titles(soup, sec):
    s = soup.find("section", id=sec)
    return [n.select_one(".msec-l").get_text(" ", strip=True) if "msec" in n.get("class") else n.find("h2").get_text(strip=True)
            if n.find("h2") else n.get("id") for n in s.find_all(recursive=False)]


def test_setups_keep_three_sections_and_archive_the_rest():
    out = sc.apply(PAGE)
    soup = BeautifulSoup(out, "html.parser")
    assert titles(soup, "t-today") == ["銘柄検索", "setups-intro", "① 発火前（構造） X", "発火前",
                                       "② 支えへの接触（オプション） X", "支えへの接触",
                                       "③ リーダー監視（RS≥85・200MA上） X", "リーダー監視"]
    port = titles(soup, "t-port")
    assert port[:2] == ["archive-intro", "旧セットアップ（参考） Former setups"]
    assert port[2:] == ["コンフルエンス X", "エントリー候補ボード", "発火トリガー X", "PP", "本日のピックアップ", "底打ち X", "底打ち"]
    assert sc.apply(out) == out
    assert out.count('class="card ds-merged"') == 3 and out.count("<footer class='disc'>") == 1


def test_nothing_to_curate_is_a_no_op():
    page = '<html><body><section id="t-today">' + msec("① 発火前") + card("発火前") + '</section><section id="t-port"></section></body></html>'
    assert sc.apply(page) == page


def test_breadth_chart_ticks_and_card_replacement():
    assert en.nice_ticks(17, 63) == [20.0, 40.0, 60.0] and en.nice_ticks(-250, 330) == [-200.0, 0.0, 200.0]
    svg = en.svg_line([30, 40, 55, 20, 32], "#1f4b8f", unit="%")
    assert ">40%</text>" in svg and 'stroke="#1f4b8f"' in svg
    zero = en.svg_line([-50, 20, -10], "#1f4b8f", zero=True)
    assert 'stroke-dasharray="4 3"' in zero and ">0</text>" in zero
    page = ('<div class="x"><div class="card" data-source-improvement="50ma-participation"><div>old</div></div>'
            '<div class="card" data-source-improvement="52week-high-low"><div>old</div></div></div><p>after</p>')
    out = br.replace_cards(page, "<NEW/>")
    assert out == '<div class="x"><NEW/></div><p>after</p>'
    assert br.replace_cards("<p>none</p>", "<NEW/>") == "<p>none</p>"
