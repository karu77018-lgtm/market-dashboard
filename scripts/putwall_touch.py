"""支えへの接触 (Put Wall Touch), fed by the option walls this pipeline fetches.

The frozen generator reads its option input from a temporary file that does not
exist when the page is built (the walls are fetched afterwards for the swing
candidates and study groups), so the card always said "取得まだか、該当なし".
This rebuilds the card from the walls in the page (window.DET[t].opt) with the
generator's own rule: RS189 >= 80 (or RS21 >= 80 when RS189 is unavailable) and
the close within +/-0.5 ATR(14) of the put wall.  Display only, never a gate.
"""
from __future__ import annotations

import html
import json
import math
import re

import numpy as np
import pandas as pd

TOUCH_ATR = 0.5
MIN_RS = 80
CARD_ID = "putwall-touch"
HEAD_RE = re.compile(r'<div class="card"(?: id="putwall-touch")?><div class="hdr"><h2>支えへの接触 ')


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def atr14(frame: pd.DataFrame) -> dict[str, float]:
    out = {}
    for t, g in frame.sort_values("date").groupby("ticker"):
        g = g.tail(15)
        if len(g) < 15:
            continue
        h, l, c = (g[k].to_numpy(float) for k in ("high", "low", "close"))
        tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        v = float(np.mean(tr))
        if math.isfinite(v) and v > 0:
            out[t] = v
    return out


def rows_from(det: dict, frame: pd.DataFrame, cap: int = 20) -> tuple[list[dict], int]:
    withwall = {t: d for t, d in det.items() if isinstance(d, dict) and isinstance(d.get("opt"), dict)
                and _f(d["opt"].get("pw"))}
    session = frame["date"].max()
    last = frame[frame["date"] == session].set_index("ticker")
    atr = atr14(frame[frame["ticker"].isin(list(withwall))])
    rows = []
    for t, d in withwall.items():
        if t not in last.index or t not in atr:
            continue
        close, pw = _f(last.at[t, "close"]), _f(d["opt"]["pw"])
        rs189, rs21 = _f(d.get("rs189")), _f(d.get("rs21"))
        if not close or close <= 0:
            continue
        if not ((rs189 is not None and rs189 >= MIN_RS) or (rs189 is None and rs21 is not None and rs21 >= MIN_RS)):
            continue
        dist = (close - pw) / atr[t]
        if abs(dist) > TOUCH_ATR:
            continue
        rows.append({"t": t, "close": close, "pw": pw, "pct": pw / close - 1, "atr": dist,
                     "rs189": None if rs189 is None else int(rs189), "rs21": None if rs21 is None else int(rs21),
                     "conf": d["opt"].get("conf"), "above": close >= pw, "dvol": _f(d.get("dvol")) or 0.0})
    rows.sort(key=lambda r: abs(r["atr"]))
    return rows[:cap], len(withwall)


def card_html(rows: list[dict], checked: int, session: str) -> str:
    e = html.escape
    head = (f'<div class="card" id="{CARD_ID}"><div class="hdr"><h2>支えへの接触 '
            '<span class="h2en">Put Wall Touch</span></h2></div>')
    sub = ('<div class="sub">RSが高く、オプションの<b>下値の支え</b>（建玉が最も積み上がった価格）に±0.5ATR以内で接触している銘柄。'
           f'対象はこのページで壁を取得した{checked}銘柄（スイング候補・売買代金上位・RS上位、{e(session)}終値・前日の建玉）。'
           '支えの上なら押し目が拾われやすく、割っていれば下げが速くなりやすい。建玉からの推定であり、売買判定ではない。</div>')
    if not checked:
        return head + sub.replace(f"{checked}銘柄", "0銘柄") + '<div class="empty">オプションの壁を取得できなかったため判定なし</div></div>'
    if not rows:
        return head + sub + '<div class="empty">該当なし</div></div>'
    body = ""
    for d in rows:
        side, cls = ("支えの上", "pos") if d["above"] else ("支えを割っている", "neg")
        rs = f'RS189 {d["rs189"]}' if d["rs189"] is not None else f'RS21 {d["rs21"]}・新規上場'
        body += (f'<div class="prerow" data-liq="{d["dvol"] / 1e6:.1f}" data-tkone="{e(d["t"])}">'
                 f'<div class="premain"><b class="pretk">{e(d["t"])}</b><span class="mut">{rs}</span>'
                 f'<span class="prestage {cls}">{side}</span></div><div class="prenums">'
                 f'<div><i>現値</i>${d["close"]:,.2f}</div><div><i>支え</i>${d["pw"]:,.2f}</div>'
                 f'<div><i>距離</i>{d["pct"] * 100:+.1f}%</div><div><i>ATR</i>{d["atr"]:+.2f}</div></div>'
                 + ('<div class="pretail">建玉薄・信頼度低</div>' if d["conf"] == "LOW" else "") + '</div>')
    return head + sub + f'<div class="prelist">{body}</div></div>'


def _replace_card(text: str, card: str) -> str:
    m = HEAD_RE.search(text)
    if not m:
        return text
    depth, start = 0, m.start()
    for tag in re.finditer(r"<(/?)div\b[^>]*>", text[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return text[:start] + card + text[start + tag.end():]
    return text


def apply(text: str, frame: pd.DataFrame) -> str:
    i = text.find("window.DET=")
    if i < 0 or frame.empty:
        return text
    try:
        det = json.JSONDecoder().raw_decode(text, i + len("window.DET="))[0]
    except ValueError:
        return text
    rows, checked = rows_from(det, frame)
    session = str(pd.Timestamp(frame["date"].max()).date())
    return _replace_card(text, card_html(rows, checked, session))
