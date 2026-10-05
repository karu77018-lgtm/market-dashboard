from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import design_system as ds  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = ("<html><head><style>.badge{background:#14331f;color:#21ac53;border:1px solid #1d7840}"
        ".warn{background:#3a290b;color:#bb9d24}.mark{background:#1b1a18;width:3px}"
        ".tiny{font-size:8.5px}svg text{font-size:7px}.liqsub{font-size:8px}"
        ".num{font-family:ui-monospace,Menlo,monospace}.glow{box-shadow:0 4px 12px rgba(0,0,0,.35)}</style>"
        "<style id='jev-ranking-style'>.jev{}</style></head><body><div class='card'><h2>見出し"
        "<span class='h2en'>Title</span></h2><b class='badge'>IN</b></div></body></html>")


def css_of(text: str) -> str:
    return re.search(r'<style id="ds-style">(.*?)</style>', text, re.S).group(1)


def test_one_stylesheet_last_in_head_and_idempotent():
    out = ds.apply(PAGE)
    assert out.count('id="ds-style"') == 1 and ds.apply(out) == out
    head = out[:out.index("</head>")]
    assert head.rindex("<style") == head.index('<style id="ds-style">')
    assert ds.STYLE_RE.sub("", out) == PAGE                     # nothing but the stylesheet changes


def test_dark_badges_become_light_tints_of_their_hue():
    css = css_of(ds.apply(PAGE))
    g = ds.FAMILIES["green"]
    assert f".badge{{background:{g[0]};color:{g[1]};border-color:{g[2]};box-shadow:none}}" in css
    assert f".warn{{background:{ds.FAMILIES['amber'][0]}" in css
    assert ".mark{" not in css                                  # a dark marker without text stays


def test_text_floor_unified_numbers_and_soft_shadows():
    css = css_of(ds.apply(PAGE))
    assert ".tiny{font-size:10px}" in css
    assert "svg text{font-size:10px}" not in css and ".liqsub{font-size:10px}" not in css
    assert ".num{font-family:inherit;font-variant-numeric:tabular-nums}" in css
    assert ".glow{box-shadow:0 4px 12px rgba(28,27,25,.12)}" in css
    assert ".h2en,.msec-en" in css and "--ds-up:" in css


def test_family_classification():
    assert ds.family("#7fe6a4") == "green" and ds.family("#e67f7f") == "red"
    assert ds.family("#82a7e3") == "blue" and ds.family("#bb9d24") == "amber"
    assert ds.family("#9c7fe6") == "purple" and ds.family("#66e2ce") == "teal"
    assert ds.family("#e7e6e0") == "neutral"


def test_styling_never_changes_the_jev_page_hash():
    assert rj.source_hash(ds.apply(PAGE)) == rj.source_hash(PAGE)


def test_published_page_has_no_dark_badges_left():
    text = ds.apply((ROOT / "source-mc57.html").read_text(encoding="utf-8"))
    css = ds.page_css(text) + css_of(text)
    leftovers = [sel for sel, body in ds.RULE_RE.findall(ds.page_css(text))
                 if (bg := ds.BG_RE.search(body)) and (fg := ds.FG_RE.search(body))
                 and ds.luminance(bg.group(1)) < .25 < ds.luminance(fg.group(1))
                 and "::" not in sel and ":before" not in sel and ":after" not in sel
                 and f"{' '.join(sel.split())}{{background:" not in css]
    assert leftovers == []
