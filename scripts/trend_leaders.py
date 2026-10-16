"""トレンド先導株: Minervini's trend template run objectively over the universe.

Display + ledger only.  It never changes MC57, V38, Massive, FRED, the swing
rules or publication logic, and any failure leaves the page as it was.

Trend template (all eight):
  1. close > 150-day and 200-day averages     5. close > 50-day average
  2. 150-day > 200-day                         6. close >= 52-week low x 1.30
  3. 200-day above its value 21 sessions ago   7. close >= 52-week high x 0.75
  4. 50-day > 150-day and 200-day              8. RS in the top 30% of the group
RS = 0.4 x 3m + 0.2 x 6m + 0.2 x 9m + 0.2 x 12m return, ranked inside the group
(S&P 500: inside the S&P 500, as in the usual routine; market: inside the liquid
universe = close >= $10 and 50-day average dollar volume >= $20M, both point-in-time).

Shown:
  * pass counts for the S&P 500 and the liquid market, with a one-year line;
  * pass rate by sector (own 大分類 from the page), so a large sector does not look
    strong just because it has many members, with the change over 20 sessions;
  * the strongest passers split into 新高値型 (close >= 80% of the all-time high) and
    戻り型 (a rebound from a deep fall: the 12-month RS is mostly the low base), with
    a mark when earnings are within 14 days;
  * the breakout health gauge, because passing the template is a watch-list
    condition, not an entry signal.
The S&P 500 membership, next earnings date and all-time high come from one
TradingView scan; without it the card shows the market part only.  The line is
recomputed with today's universe (past members that left are missing), so it is a
guide; the ledger (track-record/trend-template.json) keeps the point-in-time counts.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CARD_ID = "mc57-trend-leaders"
MSEC_ID = "mc57-trend-leaders-msec"
TITLE = "トレンド先導株"
LEDGER = Path("track-record") / "trend-template.json"
TV_URL = "https://scanner.tradingview.com/america/scan"
RS_TOP = 0.70
MIN_PRICE, MIN_DOLLAR_VOL = 10.0, 20e6
MIN_SECTOR = 15
NEW_HIGH_TYPE = 0.80
EARNINGS_DAYS = 14
LEADERS = 10
SPARK_DAYS = 252
NUMS = "①②③④⑤⑥⑦⑧⑨⑩"


# ----------------------------------------------------------------------------- data
def wide(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    f = frame.dropna(subset=["close"]).drop_duplicates(["date", "ticker"], keep="last")
    out = {c: f.pivot(index="date", columns="ticker", values=c).sort_index() for c in ("high", "low", "close", "volume")}
    return out


def template(w: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Conditions 1-7 and the raw RS score for every date x ticker (causal)."""
    c, h, l = w["close"], w["high"], w["low"]
    s50, s150, s200 = (c.rolling(n, min_periods=n).mean() for n in (50, 150, 200))
    hi = h.rolling(252, min_periods=252).max()
    lo = l.rolling(252, min_periods=252).min()
    tt7 = ((c > s150) & (c > s200) & (s150 > s200) & (s200 > s200.shift(21))
           & (s50 > s150) & (s50 > s200) & (c > s50) & (c >= 1.3 * lo) & (c >= 0.75 * hi))
    valid = s200.shift(21).notna() & hi.notna() & c.shift(252).notna()
    raw = (0.4 * (c / c.shift(63)) + 0.2 * (c / c.shift(126)) + 0.2 * (c / c.shift(189))
           + 0.2 * (c / c.shift(252)) - 1)
    dollar = (c * w["volume"]).rolling(50, min_periods=50).mean()
    liquid = (c >= MIN_PRICE) & (dollar >= MIN_DOLLAR_VOL) & valid
    return {"tt7": tt7 & valid, "valid": valid, "raw": raw.where(valid), "liquid": liquid, "hi": hi}


def passes(t: dict[str, pd.DataFrame], members: pd.Index | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(pass, eligible, rs percentile) inside a group: the liquid market or a member list."""
    if members is None:
        elig = t["liquid"]
    else:
        cols = t["valid"].columns.intersection(members)
        elig = t["valid"][cols]
    raw = t["raw"][elig.columns].where(elig)
    rs = raw.rank(axis=1, pct=True)
    ok = t["tt7"][elig.columns] & elig & (rs >= RS_TOP)
    return ok, elig, rs


def _sector(det: dict, ticker: str) -> str:
    sec = str((det.get(ticker) or {}).get("sec") or "").strip()
    return re.sub(r"^\d+\.\s*", "", sec) or "その他"


def fetch_tv(timeout: float = 25.0) -> dict | None:
    """S&P 500 members + next earnings + all-time high, in one display-only call each."""
    def scan(payload: dict) -> list:
        req = urllib.request.Request(TV_URL, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              "User-Agent": "Mozilla/5.0 (v38-market-dashboard)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("data") or []
    try:
        sp = scan({"columns": ["name"], "symbols": {"symbolset": ["SYML:SP;SPX"]},
                   "range": [0, 1000], "options": {"lang": "en"}})
        allrows = scan({"columns": ["name", "earnings_release_next_date", "High.All"],
                        "filter": [{"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]}],
                        "symbols": {"query": {"types": []}, "tickers": []}, "range": [0, 10000],
                        "options": {"lang": "en"}, "preset": "all_stocks"})
    except Exception as exc:  # display-only
        print(f"trend leaders: TradingView lookup skipped: {exc!r}", flush=True)
        return None
    members = {str(r["d"][0]).upper() for r in sp if r.get("d")}
    info = {}
    for r in allrows:
        d = r.get("d") or []
        if len(d) >= 3 and d[0]:
            info[str(d[0]).upper()] = {"earn": d[1], "ath": d[2]}
    return {"sp500": members, "info": info} if len(members) >= 400 else None


# ----------------------------------------------------------------------------- compute
def compute(frame: pd.DataFrame, det: dict, session: str, tv: dict | None = None) -> dict | None:
    w = wide(frame)
    if len(w["close"]) < 253:
        return None
    t = template(w)
    last = w["close"].index[-1]
    out: dict[str, Any] = {"session": str(last.date())}
    groups = {"mkt": None}
    if tv and tv.get("sp500"):
        groups["sp"] = pd.Index(sorted(tv["sp500"]))
    series, today = {}, {}
    for key, members in groups.items():
        ok, elig, rs = passes(t, members)
        cnt, n = ok.sum(axis=1), elig.sum(axis=1)
        frac = (cnt / n.where(n > 0)).dropna()
        series[key] = frac.iloc[-SPARK_DAYS:]
        today[key] = {"pass": int(cnt.iloc[-1]), "n": int(n.iloc[-1]),
                      "ago20": float(frac.iloc[-21]) if len(frac) > 21 else None,
                      "ok": ok.iloc[-1], "rs": rs.iloc[-1], "ok20": ok.iloc[-21] if len(ok) > 21 else None,
                      "elig": elig.iloc[-1], "elig20": elig.iloc[-21] if len(elig) > 21 else None}
    out["series"], out["today"] = series, today

    # sector pass rates inside the liquid market
    m = today["mkt"]
    rows = []
    secs = pd.Series({tk: _sector(det, tk) for tk in m["elig"][m["elig"]].index})
    overall = m["pass"] / m["n"] if m["n"] else 0
    for sec, tks in secs.groupby(secs).groups.items():
        tks = list(tks)
        if len(tks) < MIN_SECTOR or sec == "その他":
            continue
        p = int(m["ok"][tks].sum())
        rate = p / len(tks)
        prev = None
        if m["ok20"] is not None:
            e20 = [x for x in tks if bool(m["elig20"].get(x, False))]
            prev = (int(m["ok20"][e20].sum()) / len(e20)) if e20 else None
        rows.append({"sector": sec, "pass": p, "n": len(tks), "rate": rate,
                     "lift": rate / overall if overall else None, "chg": None if prev is None else rate - prev})
    out["sectors"] = sorted(rows, key=lambda r: (-r["rate"], -r["n"]))
    out["overall"] = overall

    # leaders
    info = (tv or {}).get("info") or {}
    hi_all = w["high"].max()
    sday = date.fromisoformat(session)

    def leader(tk: str, rs: float) -> dict:
        c = float(w["close"][tk].iloc[-1])
        meta = info.get(tk) or {}
        ath = meta.get("ath") or float(hi_all.get(tk, np.nan))
        ath = max(float(ath), float(hi_all.get(tk, 0) or 0)) if ath == ath else None
        earn = meta.get("earn")
        days = None
        if isinstance(earn, (int, float)) and earn > 0:
            days = (datetime.fromtimestamp(earn, timezone.utc).date() - sday).days
        return {"t": tk, "rs": int(round(rs * 99)), "sec": _sector(det, tk),
                "from_hi52": c / float(t["hi"][tk].iloc[-1]) - 1,
                "from_ath": (c / ath - 1) if ath else None,
                "kind": "新高値型" if ath and c >= NEW_HIGH_TYPE * ath else "戻り型",
                "earn_days": days if days is not None and 0 <= days <= 60 else None,
                "ath_source": "all" if meta.get("ath") else "3y"}

    out["leaders"] = {}
    sp_set = set(groups["sp"]) if "sp" in groups else set()
    for key in today:
        d = today[key]
        cand = d["rs"][d["ok"][d["ok"]].index].sort_values(ascending=False)
        if key == "mkt" and sp_set:
            cand = cand[[x not in sp_set for x in cand.index]]
        out["leaders"][key] = [leader(tk, float(r)) for tk, r in cand.head(LEADERS).items()]
    return out


# ----------------------------------------------------------------------------- render
def _pct(v: float | None, sign: bool = False) -> str:
    if v is None or v != v:
        return "—"
    return f"{v * 100:+.0f}%" if sign else f"{v * 100:.0f}%"


def _spark(series: dict[str, pd.Series]) -> str:
    keys = [k for k in ("mkt", "sp") if k in series and len(series[k]) > 5]
    if not keys:
        return ""
    W, H, P = 320, 70, 4
    top = max(0.05, max(float(series[k].max()) for k in keys)) * 1.1
    colors = {"mkt": "#3774d3", "sp": "#8a7b3c"}
    lines = []
    for k in keys:
        s = series[k]
        n = len(s)
        pts = " ".join(f"{P + (W - 2 * P) * i / (n - 1):.1f},{H - P - (H - 2 * P) * float(v) / top:.1f}"
                       for i, v in enumerate(s.to_numpy()))
        lines.append(f'<polyline fill="none" stroke="{colors[k]}" stroke-width="1.6" points="{pts}"/>')
    first = series[keys[0]].index[0]
    return (f'<svg class="tt-spark" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" '
            f'aria-label="通過率の推移">{"".join(lines)}</svg>'
            f'<div class="tt-axis"><span>{first:%Y/%m}</span><span>縦軸 0〜{top * 100:.0f}%</span><span>今日</span></div>')


def _short(sector: str) -> str:
    return re.sub(r"（[^）]*）", "", sector).strip() or sector


def _leader_rows(rows: list[dict], shown: int = 6) -> str:
    e = html.escape
    out = []
    for r in rows:
        kind_cls = "tt-new" if r["kind"] == "新高値型" else "tt-reb"
        earn = (f'<span class="tt-earn">決算{r["earn_days"]}日</span>'
                if r["earn_days"] is not None and r["earn_days"] <= EARNINGS_DAYS else "")
        ath_label = "最高値" if r["ath_source"] == "all" else "3年高値"
        out.append(
            f'<div class="tt-ld" data-tkone="{e(r["t"])}"><b>{e(r["t"])}</b>'
            f'<span class="tt-rs">RS{r["rs"]}</span><span class="tt-kind {kind_cls}">{r["kind"]}</span>{earn}'
            f'<span class="tt-m">{e(r["sec"])}・52週高値{_pct(r["from_hi52"], True)}・{ath_label}{_pct(r["from_ath"], True)}</span></div>')
    if not out:
        return '<div class="tt-empty">該当なし</div>'
    rest = out[shown:]
    return "".join(out[:shown]) + (f'<details class="tt-more"><summary>残り{len(rest)}銘柄</summary>{"".join(rest)}</details>'
                                   if rest else "")


def card_html(res: dict, health: dict | None = None) -> str:
    e = html.escape
    td = res["today"]

    def tile(key: str, label: str) -> str:
        if key not in td:
            return f'<div class="tt-tile"><span>{label}</span><b>—</b><i>構成銘柄を取得できず</i></div>'
        d = td[key]
        frac = d["pass"] / d["n"] if d["n"] else 0
        chg = "" if d["ago20"] is None else f'（20日前 {d["ago20"] * 100:.0f}%）'
        return (f'<div class="tt-tile"><span>{label}</span><b>{d["pass"]}<small>/{d["n"]}</small></b>'
                f'<i>通過率 {frac * 100:.0f}%{chg}</i></div>')

    sec_rows = []
    best = max((r["rate"] for r in res["sectors"]), default=0) or 1
    for i, r in enumerate(res["sectors"]):
        lift = r["lift"] or 0
        cls = "tt-hot" if lift >= 1.5 else ("tt-cold" if lift <= 0.5 else "")
        chg = "" if r["chg"] is None else f'{r["chg"] * 100:+.0f}pt'
        sec_rows.append(
            f'<div class="tt-sec {cls}"><span class="tt-sn" title="{e(r["sector"])}">{e(_short(r["sector"]))}</span>'
            f'<span class="tt-bar"><i style="width:{100 * r["rate"] / best:.0f}%"></i></span>'
            f'<span class="tt-sv">{r["rate"] * 100:.0f}%</span><span class="tt-sc">{r["pass"]}/{r["n"]}</span>'
            f'<span class="tt-sd">{chg}</span></div>')
    head_secs, rest_secs = sec_rows[:8], sec_rows[8:]
    sectors = "".join(head_secs) + (f'<details class="tt-more"><summary>残り{len(rest_secs)}業種</summary>'
                                    f'{"".join(rest_secs)}</details>' if rest_secs else "")

    gauge = ""
    if health and health.get("on") is not None:
        try:
            from breakout_health import _fmt, _state_word
            word, color = _state_word(health)
            note = ("通過銘柄のブレイクは報われている" if health["on"] else
                    "今は通過銘柄でもブレイク直後の買いが報われにくい。候補リストとして使い、買いはスイングルールの合図を待つ")
            gauge = (f'<div class="tt-gauge"><span>ブレイク成功度（Daily）</span><b style="color:{color}">{e(word)} '
                     f'{e(_fmt(health.get("value")))}</b><div>{e(note)}</div></div>')
        except Exception:
            gauge = ""

    sp_block = (f'<div class="tt-h3">S&amp;P500のRS上位（S&amp;P500内の順位）</div>{_leader_rows(res["leaders"]["sp"])}'
                if "sp" in res["leaders"] else "")
    mkt_title = "S&amp;P500外のRS上位（流動性のある全市場の順位）" if "sp" in res["leaders"] else "RS上位（流動性のある全市場の順位）"
    hd = td["sp"] if "sp" in td else td["mkt"]
    hd_label = "S&amp;P500通過" if "sp" in td else "全市場通過"
    return (
        f'<div class="card" id="{CARD_ID}" data-source-improvement="trend-template">'
        f'<div class="chd"><h2>{TITLE}（トレンドテンプレート8条件）</h2>'
        f'<div class="chd-now" style="color:#3774d3"><b>{hd["pass"]}</b><span>{hd_label}</span></div></div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        '思い込みを入れずに、全銘柄へ同じ8条件を当てる。①株価が150日線・200日線より上 ②150日線＞200日線 '
        '③200日線が1か月前より上 ④50日線が150日線・200日線より上 ⑤株価が50日線より上 ⑥52週安値から+30%以上 '
        '⑦52週高値から−25%以内 ⑧RS（3・6・9・12か月の加重騰落率）がグループ内の上位30%。'
        '全市場は株価10ドル以上・50日平均売買代金2,000万ドル以上。'
        '<b>業種は数ではなく通過率で比べる</b>（銘柄の多い業種は数だけ多く見える）。右端は20営業日前からの変化。'
        '<b>新高値型</b>＝最高値の80%以上にいる本物の先導株。<b>戻り型</b>＝大きく下げた後の戻りでRSが高く出ている銘柄で、'
        '12か月の騰落率が低い出発点に引っ張られている。オニール流の先導株は新高値型。'
        '8条件は監視リストに入れる条件で、買いの合図ではない。決算14日以内は印付き。'
        '推移の線は今のユニバースで過去を計算し直した参考値（その後に消えた銘柄は入らない）。'
        '日々の値は track-record/trend-template.json に記録。売買指示ではない。'
        '</div></details>'
        f'<div class="tt-tiles">{tile("sp", "S&amp;P500")}{tile("mkt", "全市場（流動性あり）")}</div>'
        f'<div class="tt-h3">通過率の推移（1年）<span class="tt-key"><i class="k1"></i>全市場'
        f'{"<i class=k2></i>S&amp;P500" if "sp" in res["series"] else ""}</span></div>{_spark(res["series"])}'
        f'<div class="tt-h3">業種別の通過率（全市場平均 {res["overall"] * 100:.0f}%）</div>'
        f'<div class="tt-secs">{sectors}</div>'
        f'{gauge}{sp_block}<div class="tt-h3">{mkt_title}</div>{_leader_rows(res["leaders"]["mkt"])}'
        '</div>')


STYLE = """
<style id="mc57-trend-leaders-style">
#mc57-trend-leaders .tt-tiles{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0}
#mc57-trend-leaders .tt-tile{background:#f6f5f1;border-radius:8px;padding:6px 8px;font-size:11.5px;color:#6b6858}
#mc57-trend-leaders .tt-tile b{display:block;font-size:18px;color:#1c1b19;font-variant-numeric:tabular-nums}
#mc57-trend-leaders .tt-tile b small{font-size:12px;color:#6b6858;font-weight:400}
#mc57-trend-leaders .tt-tile i{font-style:normal}
#mc57-trend-leaders .tt-h3{font-size:12.5px;font-weight:700;margin:10px 0 4px;display:flex;justify-content:space-between;gap:6px;flex-wrap:wrap}
#mc57-trend-leaders .tt-key{font-weight:400;color:#6b6858;font-size:11px}
#mc57-trend-leaders .tt-key i{display:inline-block;width:10px;height:2px;margin:0 3px 3px 8px;vertical-align:middle}
#mc57-trend-leaders .tt-key .k1{background:#3774d3}#mc57-trend-leaders .tt-key .k2{background:#8a7b3c}
#mc57-trend-leaders .tt-spark{width:100%;height:70px;display:block;background:#faf9f6;border-radius:6px}
#mc57-trend-leaders .tt-axis{display:flex;justify-content:space-between;font-size:10.5px;color:#8a8778}
#mc57-trend-leaders .tt-sec{display:grid;grid-template-columns:minmax(0,9.5em) 1fr 2.6em 3.8em 3em;gap:6px;align-items:center;font-size:12px;padding:3px 0;font-variant-numeric:tabular-nums}
#mc57-trend-leaders .tt-sn{font-size:11.5px;line-height:1.25;overflow-wrap:anywhere}
#mc57-trend-leaders .tt-bar{background:#efeee9;border-radius:3px;height:8px;overflow:hidden}
#mc57-trend-leaders .tt-bar i{display:block;height:100%;background:#9fb7dc}
#mc57-trend-leaders .tt-hot .tt-bar i{background:#23824d}#mc57-trend-leaders .tt-hot .tt-sv{color:#23824d;font-weight:700}
#mc57-trend-leaders .tt-cold .tt-bar i{background:#c9c6ba}#mc57-trend-leaders .tt-cold{color:#8a8778}
#mc57-trend-leaders .tt-sv,#mc57-trend-leaders .tt-sc,#mc57-trend-leaders .tt-sd{text-align:right}
#mc57-trend-leaders .tt-sc,#mc57-trend-leaders .tt-sd{color:#6b6858;font-size:11px}
#mc57-trend-leaders .tt-more summary{font-size:11.5px;color:#3774d3;cursor:pointer;margin:2px 0}
#mc57-trend-leaders .tt-ld{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;border-top:1px solid #e1dfd6;padding:5px 2px;font-size:12px;cursor:pointer}
#mc57-trend-leaders .tt-ld b{font-size:13px}
#mc57-trend-leaders .tt-rs{font-variant-numeric:tabular-nums;color:#3f3d35}
#mc57-trend-leaders .tt-kind,#mc57-trend-leaders .tt-earn{font-size:10.5px;border-radius:5px;padding:1px 6px;color:#fff;white-space:nowrap}
#mc57-trend-leaders .tt-new{background:#23824d}#mc57-trend-leaders .tt-reb{background:#8a7b3c}
#mc57-trend-leaders .tt-earn{background:#b5523f}
#mc57-trend-leaders .tt-m{flex-basis:100%;color:#6b6858;font-size:11px;overflow-wrap:anywhere}
#mc57-trend-leaders .tt-gauge{background:#f6f5f1;border-radius:8px;padding:6px 8px;margin:10px 0 2px;font-size:11.5px;color:#4d4a40}
#mc57-trend-leaders .tt-gauge b{margin-left:6px}
#mc57-trend-leaders .tt-empty{font-size:12px;color:#6b6858;padding:4px 2px}
</style>"""


# ----------------------------------------------------------------------------- page
def _div_end(text: str, start: int) -> int:
    """Index just past the </div> closing the <div ...> that opens at ``start``."""
    depth, i = 0, start
    tag = re.compile(r"<(/?)div\b[^>]*>", re.I)
    for m in tag.finditer(text, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return m.end()
    return -1


def _find_div(text: str, div_id: str) -> int:
    """Start of the <div> carrying ``id`` (attribute order varies after BeautifulSoup)."""
    m = re.search(r'<div\b[^>]*\bid="' + re.escape(div_id) + r'"[^>]*>', text)
    return m.start() if m else -1


def _renumber_themes(text: str) -> str:
    a = text.find('<section id="t-themes"')
    if a < 0:
        return text
    b = text.find("</section>", a)
    count = iter(NUMS)
    head = re.compile(r'(<div class="msec[^"]*"[^>]*><div class="msec-l">)\s*[①-⑩]?\s*')
    seg = head.sub(lambda m: m.group(1) + next(count, "") + " ", text[a:b])
    return text[:a] + seg + text[b:]


def apply(text: str, res: dict | None, health: dict | None = None) -> str:
    """Replace the card in place, or insert it next to the theme gate card."""
    if res is None:
        return text
    card = card_html(res, health)
    if "mc57-trend-leaders-style" not in text:
        text = text.replace("</head>", STYLE + "</head>", 1)
    old = _find_div(text, CARD_ID)
    if old >= 0:
        end = _div_end(text, old)
        return text[:old] + card + text[end:] if end > 0 else text
    gate = _find_div(text, "mc57-theme-gate")
    if 'id="t-themes"' in text and gate >= 0:
        # page already split into Rotation/Themes: add the section header too
        end = _div_end(text, gate)
        block = (f'<div class="msec" id="{MSEC_ID}"><div class="msec-l">② 客観スクリーン'
                 '<span class="msec-en">Trend Template</span></div>'
                 '<div class="msec-q">8条件の通過数・業種別の通過率・RS上位を思い込みなしで</div></div>' + card)
        return _renumber_themes(text[:end] + block + text[end:])
    if gate >= 0:            # before the split: rotation_split moves it under its header
        return text[:gate] + card + text[gate:]
    rot = text.find('<section id="t-rotation"')
    if rot >= 0:
        close = text.find("</section>", rot)
        return text[:close] + card + text[close:]
    return text


# ----------------------------------------------------------------------------- ledger
def load_ledger(root: Path) -> dict:
    p = root / LEDGER
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"schema": "trend-template.1", "days": {}}


def record(ledger: dict, res: dict) -> dict:
    day = {k: [v["pass"], v["n"]] for k, v in res["today"].items()}
    day["sec"] = {r["sector"]: [r["pass"], r["n"]] for r in res["sectors"]}
    day["top"] = {k: [r["t"] for r in v[:LEADERS]] for k, v in res["leaders"].items()}
    ledger.setdefault("days", {})[res["session"]] = day
    ledger["last_day"] = res["session"]
    return ledger


def save_ledger(ledger: dict, root: Path) -> None:
    p = root / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def run(text: str, frame: pd.DataFrame, session: str, root: Path, health: dict | None) -> str:
    """Daily refresh: compute, record today's counts, render."""
    from rule_refresh import page_det
    res = compute(frame, page_det(text), session, fetch_tv())
    if res is None:
        return text
    save_ledger(record(load_ledger(root), res), root)
    print(f"trend leaders: market {res['today']['mkt']['pass']}/{res['today']['mkt']['n']}"
          + (f", S&P500 {res['today']['sp']['pass']}/{res['today']['sp']['n']}" if "sp" in res["today"] else ""),
          flush=True)
    return apply(text, res, health)


def main() -> int:
    """Display workflows: re-render from the saved inputs; never records."""
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rule_refresh import load_frame, page_det
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    frame = load_frame(root / "work" / "ohlcv.csv", session)
    if frame is None:
        print(f"saved OHLCV for {session} unavailable; trend leaders left as published", flush=True)
        return 0
    text = page.read_text(encoding="utf-8")
    try:
        import breakout_health
        health = breakout_health.compute(frame)
    except Exception as exc:
        print(f"breakout health skipped: {exc!r}", flush=True)
        health = None
    res = compute(frame, page_det(text), session, fetch_tv())
    page.write_text(apply(text, res, health), encoding="utf-8")
    print("trend leaders: rendered" if res else "trend leaders: not enough history", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
