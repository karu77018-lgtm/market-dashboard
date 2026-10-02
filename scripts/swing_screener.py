#!/usr/bin/env python3
"""Swing screener card for the Positions tab (display-only adapter).

It never changes MC57, V38, NQSAR, Massive, FRED or publication logic. The only
input is the already-acquired adjusted OHLCV frame. Rules come from the
2015-2026 backtest (current listings, Yahoo daily data):

Core (main strategy)
  Selection : trend template, 50-day dollar volume in the top 5% and 189-day
              return in the top 10% of the liquid universe (close >= $10 and
              50-day dollar volume >= $20M).
  Setup     : 10-day / 50-day average daily range <= 0.9 and
              5-day / 50-day average volume <= 0.9.
  No chase  : session change < +3%, previous session <= +3%, close within
              +12% of the 10-day average.
  Trade     : buy at the close, 1% account risk with an -8% stop (about 12.5%
              of equity), add half once at +10%, move the stop to break-even
              after +25%, exit on a close below the 21-day EMA of lows.

Theme slot (earnings-gap style entries)
  Gap up +5% to +20%, close >= +5%, volume 3-15x the 50-day average, close in
  the upper half of the range, above the 50-day average, 20-day average range
  3-7% and correlation-peer RS strength 50-90. 0.5% risk, -8% stop, exit
  after 60 sessions.

Descriptive only; no orders are generated.
"""
from __future__ import annotations

import html
import math

import numpy as np
import pandas as pd

CARD_ID = "mc57-swing-screener"
SECTION = '<section id="t-alloc">'

MIN_PRICE = 10.0
MIN_DV = 20e6
DV_PCT = 95
RS189_PCT = 90
MAX_VC = 0.9
MAX_VDRY = 0.9
MAX_CHG = 0.03
MAX_PREV_CHG = 0.03
MAX_EXT10 = 0.12
STOP = 0.08
CORE_RISK = 0.01
EP_RISK = 0.005
PEER_K = 15
PEER_WINDOW = 120


def _pivot(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    f = frame[["ticker", "date", "open", "high", "low", "close", "volume"]].copy()
    f["ticker"] = f["ticker"].astype(str).str.upper()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    f = f[f["date"].notna()].drop_duplicates(["ticker", "date"], keep="last")
    return {c: f.pivot(index="date", columns="ticker", values=c).sort_index()
            for c in ("open", "high", "low", "close", "volume")}


def _pct_rank(values: pd.Series, mask: pd.Series) -> pd.Series:
    v = values.where(mask)
    return v.rank(pct=True) * 100


LATE_LAGS = (1, 2)
LATE_MAX_UP = 0.03


def _states(c: pd.DataFrame, h: pd.DataFrame, l: pd.DataFrame, v: pd.DataFrame) -> callable:
    """Return a function giving the core-rule state for a (negative) row position."""
    ma10 = c.rolling(10).mean()
    ma50 = c.rolling(50).mean()
    ma150 = c.rolling(150).mean()
    ma200 = c.rolling(200).mean()
    hi252 = h.rolling(252, min_periods=200).max()
    lo252 = l.rolling(252, min_periods=200).min()
    dv50 = (c * v).rolling(50, min_periods=40).mean()
    dr = h / l - 1
    adr20 = dr.rolling(20).mean()
    vc = dr.rolling(10).mean() / dr.rolling(50).mean()
    v50 = v.rolling(50).mean()
    vdry = v.rolling(5).mean() / v50
    chg = c / c.shift(1) - 1
    el21 = l.ewm(span=21, adjust=False).mean()

    def at(k: int) -> dict:
        last = c.iloc[k]
        liquid = (last >= MIN_PRICE) & (dv50.iloc[k] >= MIN_DV)
        tt = (last > ma50.iloc[k]) & (ma50.iloc[k] > ma150.iloc[k]) & (ma150.iloc[k] > ma200.iloc[k]) \
            & (ma200.iloc[k] > ma200.iloc[k - 20]) & (last >= 0.75 * hi252.iloc[k]) & (last >= 1.3 * lo252.iloc[k])

        def ret(n: int) -> pd.Series:
            return last / c.iloc[k - n] - 1 if len(c) + k >= n else pd.Series(np.nan, index=c.columns)

        r189 = ret(189)
        comp = 2 * ret(63) + ret(126) + r189 + ret(252)
        dv_pct = _pct_rank(dv50.iloc[k], liquid)
        rs189_pct = _pct_rank(r189, liquid)
        ext10 = last / ma10.iloc[k] - 1
        checks = {
            "収縮": vc.iloc[k] <= MAX_VC,
            "出来高減": vdry.iloc[k] <= MAX_VDRY,
            "当日+3%未満": chg.iloc[k] < MAX_CHG,
            "前日+3%以下": chg.iloc[k - 1] <= MAX_PREV_CHG,
            "10日線+12%以内": ext10 <= MAX_EXT10,
        }
        timing = pd.Series(True, index=c.columns)
        for m in checks.values():
            timing &= m.fillna(False)
        selected = liquid & tt & (dv_pct >= DV_PCT) & (rs189_pct >= RS189_PCT)
        return {"last": last, "liquid": liquid, "tt": tt, "dv_pct": dv_pct, "rs189_pct": rs189_pct,
                "comp_pct": _pct_rank(comp, liquid), "vc": vc.iloc[k], "vdry": vdry.iloc[k],
                "chg": chg.iloc[k], "ext10": ext10, "el21": el21.iloc[k], "checks": checks,
                "timing": timing, "selected": selected, "signal": selected & timing,
                "adr20": adr20.iloc[k], "ma50": ma50.iloc[k], "v50_prev": v50.iloc[k - 1]}

    at.el21 = el21
    return at


def evaluate(frame: pd.DataFrame) -> dict:
    p = _pivot(frame)
    o, h, l, c, v = p["open"], p["high"], p["low"], p["close"], p["volume"]
    if len(c) < 260:
        return {"session": str(c.index[-1].date()) if len(c) else "", "core": [], "late": [], "watch": [],
                "ep": [], "universe": 0, "reason": "history_short"}
    state = _states(c, h, l, v)
    s = state(-1)
    last, liquid, tt, chg = s["last"], s["liquid"], s["tt"], s["chg"]
    selected, timing, checks = s["selected"], s["timing"], s["checks"]

    def row(t: str, st: dict) -> dict:
        px = float(st["last"][t])
        return {"ticker": t, "close": px, "rs189": int(round(st["rs189_pct"][t])),
                "dv": int(round(st["dv_pct"][t])), "vc": float(st["vc"][t]), "vdry": float(st["vdry"][t]),
                "chg": float(st["chg"][t]), "ext10": float(st["ext10"][t]), "el21": float(st["el21"][t]),
                "stop": px * (1 - STOP), "add": px * 1.10, "be": px * 1.25}

    core = [row(t, s) for t in selected[selected & timing].index]
    core.sort(key=lambda r: -r["rs189"])

    # Late entries: signal 1-2 sessions ago, not re-signalled today, still near the signal close,
    # no stop or 21EMA-low exit since, still selected, and today's no-chase checks pass.
    late, seen = [], {r["ticker"] for r in core}
    nochase = (chg < MAX_CHG) & (s["ext10"] <= MAX_EXT10)
    for lag in LATE_LAGS:
        past = state(-1 - lag)
        for t in past["signal"][past["signal"]].index:
            if t in seen or not bool(selected.get(t, False)) or not bool(nochase.get(t, False)):
                continue
            base = float(past["last"][t])
            after = slice(len(c) - lag, len(c))
            lows = l[t].iloc[after]
            closes = c[t].iloc[after]
            if (lows <= base * (1 - STOP)).any() or (closes < state.el21[t].iloc[after]).any():
                continue
            if float(last[t]) > base * (1 + LATE_MAX_UP):
                continue
            r = row(t, s)
            r.update({"signal_date": str(c.index[-1 - lag].date()), "signal_close": base,
                      "from_signal": float(last[t]) / base - 1, "lag": lag})
            late.append(r)
            seen.add(t)
    late.sort(key=lambda r: (r["lag"], -r["rs189"]))

    watch = []
    for t in selected[selected & ~timing].index:
        if t in seen:
            continue
        r = row(t, s)
        r["missing"] = [k for k, m in checks.items() if not bool(m.get(t, False))]
        watch.append(r)
    watch.sort(key=lambda r: (len(r["missing"]), -r["rs189"]))

    # Theme slot: earnings-gap style entries with correlation-peer strength 50-90.
    adr20, ma50 = s["adr20"], s["ma50"]
    gap = o.iloc[-1] / c.iloc[-2] - 1
    volx = v.iloc[-1] / s["v50_prev"]
    rng = (h.iloc[-1] - l.iloc[-1]).replace(0, np.nan)
    clv = (last - l.iloc[-1]) / rng
    ep_mask = liquid & (gap >= 0.05) & (gap <= 0.20) & (chg >= 0.05) & (volx >= 3) & (volx <= 15) \
        & (clv >= 0.5) & (last > ma50) & (adr20 >= 0.03) & (adr20 < 0.07)
    ep = []
    if ep_mask.any():
        peer = _peer_scores(c, liquid, s["comp_pct"], list(ep_mask[ep_mask].index))
        for t in ep_mask[ep_mask].index:
            ps = peer.get(t)
            if ps is None or not (50 <= ps < 90):
                continue
            ep.append({"ticker": t, "close": float(last[t]), "gap": float(gap[t]), "chg": float(chg[t]),
                       "volx": float(volx[t]), "peer": int(round(ps)), "adr": float(adr20[t]),
                       "stop": float(last[t] * (1 - STOP)), "tt": bool(tt[t])})
        ep.sort(key=lambda r: -r["peer"])
    return {"session": str(c.index[-1].date()), "core": core, "late": late, "watch": watch, "ep": ep,
            "universe": int(liquid.sum()), "selected": int(selected.sum())}


def _peer_scores(c: pd.DataFrame, liquid: pd.Series, comp_pct: pd.Series, targets: list[str]) -> dict:
    """Mean composite-RS percentile of the 15 most correlated liquid stocks (last 120 sessions)."""
    rets = np.log(c / c.shift(1)).iloc[-PEER_WINDOW:]
    cols = [t for t in rets.columns if bool(liquid.get(t, False)) and rets[t].isna().sum() <= 10]
    if len(cols) < PEER_K + 1:
        return {}
    R = rets[cols].fillna(0.0).to_numpy()
    R = (R - R.mean(0)) / (R.std(0) + 1e-9)
    idx = {t: i for i, t in enumerate(cols)}
    cp = comp_pct.reindex(cols).to_numpy()
    out = {}
    for t in targets:
        if t not in idx:
            continue
        corr = (R.T @ R[:, idx[t]]) / R.shape[0]
        corr[idx[t]] = -np.inf
        top = np.argsort(-corr)[:PEER_K]
        vals = cp[top]
        vals = vals[~np.isnan(vals)]
        if len(vals):
            out[t] = float(vals.mean())
    return out


STYLE = """
<style id="mc57-swing-screener-style">
#mc57-swing-screener .sw-sec{font-weight:700;font-size:13px;margin:10px 2px 4px;display:flex;flex-wrap:wrap;align-items:center;gap:6px}
#mc57-swing-screener .sw-row{border-top:1px solid #e1dfd6;padding:7px 2px}
#mc57-swing-screener .sw-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;font-weight:700}
#mc57-swing-screener .sw-tk{font-size:15px}
#mc57-swing-screener .sw-px{font-size:12px;color:#4d4a40;font-variant-numeric:tabular-nums}
#mc57-swing-screener .sw-m{font-size:12px;color:#4d4a40;margin-top:2px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#mc57-swing-screener .sw-lv{font-size:12px;margin-top:2px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#mc57-swing-screener .sw-lv b{font-weight:700}
#mc57-swing-screener .sw-miss{font-size:11px;border-radius:5px;padding:1px 6px;background:#efe9d6;color:#6b5a1e;white-space:nowrap}
#mc57-swing-screener .sw-tag{font-size:11px;border-radius:5px;padding:1px 6px;color:#fff;white-space:nowrap}
#mc57-swing-screener .sw-go{background:#23824d}#mc57-swing-screener .sw-late{background:#5b8a5f}#mc57-swing-screener .sw-wait{background:#8a7b3c}#mc57-swing-screener .sw-ep{background:#3774d3}
#mc57-swing-screener .sw-empty{font-size:13px;color:#4d4a40;padding:6px 2px}
#mc57-swing-screener .sw-chips{font-size:12px;overflow-wrap:anywhere;line-height:1.7}
</style>"""


def _p(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _d(v: float) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"${v:,.2f}"


def card_html(result: dict) -> str:
    e = html.escape
    core, watch, ep = result["core"], result["watch"], result["ep"]
    late = result.get("late", [])
    rows = []
    for r in core[:12]:
        rows.append(
            f'<div class="sw-row"><div class="sw-h"><span class="sw-tag sw-go">買い候補</span>'
            f'<span class="sw-tk">{e(r["ticker"])}</span><span class="sw-px">{_d(r["close"])}（{_p(r["chg"])}）</span></div>'
            f'<div class="sw-m">RS189 {r["rs189"]}・売買代金 {r["dv"]}・値幅 {r["vc"]:.2f}・出来高 {r["vdry"]:.2f}'
            f'・10日線 {_p(r["ext10"])}</div>'
            f'<div class="sw-lv">損切り <b>{_d(r["stop"])}</b>（−8%）・買い増し {_d(r["add"])}（+10%）'
            f'・建値へ {_d(r["be"])}（+25%）・安値21EMA {_d(r["el21"])}</div></div>'
        )
    core_body = "".join(rows) or '<div class="sw-empty">本日の買い候補なし（待つのもルール）。</div>'
    lrows = []
    for r in late[:10]:
        lrows.append(
            f'<div class="sw-row"><div class="sw-h"><span class="sw-tag sw-late">{r["lag"]}日前に成立</span>'
            f'<span class="sw-tk">{e(r["ticker"])}</span><span class="sw-px">{_d(r["close"])}（{_p(r["chg"])}）</span></div>'
            f'<div class="sw-m">成立 {e(r["signal_date"][5:].replace("-", "/"))} {_d(r["signal_close"])} から {_p(r["from_signal"])}'
            f'・RS189 {r["rs189"]}・売買代金 {r["dv"]}</div>'
            f'<div class="sw-lv">今入るなら 損切り <b>{_d(r["stop"])}</b>（−8%）・買い増し {_d(r["add"])}'
            f'・建値へ {_d(r["be"])}・安値21EMA {_d(r["el21"])}</div></div>'
        )
    late_body = "".join(lrows) or '<div class="sw-empty">該当なし。</div>'
    wrows = []
    for r in watch[:15]:
        miss = "".join(f'<span class="sw-miss">{e(m)}</span>' for m in r["missing"])
        wrows.append(
            f'<div class="sw-row"><div class="sw-h"><span class="sw-tk">{e(r["ticker"])}</span>'
            f'<span class="sw-px">{_d(r["close"])}（{_p(r["chg"])}）・RS189 {r["rs189"]}</span>{miss}</div></div>'
        )
    watch_body = "".join(wrows) or '<div class="sw-empty">選定条件を満たす銘柄なし。</div>'
    erows = []
    for r in ep[:8]:
        tt = "" if r["tt"] else '<span class="sw-miss">トレンドテンプレ外</span>'
        erows.append(
            f'<div class="sw-row"><div class="sw-h"><span class="sw-tag sw-ep">テーマ枠</span>'
            f'<span class="sw-tk">{e(r["ticker"])}</span><span class="sw-px">{_d(r["close"])}（{_p(r["chg"])}）</span>{tt}</div>'
            f'<div class="sw-m">窓 {_p(r["gap"])}・出来高 {r["volx"]:.1f}倍・テーマ強度 {r["peer"]}・値幅 {r["adr"] * 100:.1f}%</div>'
            f'<div class="sw-lv">損切り <b>{_d(r["stop"])}</b>（−8%）・60営業日で手仕舞い・リスク0.5%</div></div>'
        )
    ep_body = "".join(erows) or '<div class="sw-empty">本日のテーマ枠候補なし。</div>'

    def copy_btn(items: list[dict]) -> str:
        tks = ",".join(r["ticker"] for r in items)
        if not tks:
            return ""
        return (f'<button class="cp" data-tk="{e(tks)}" onclick="copyTk(event,this)">コピー '
                f'<span class="n">{len(items)}</span></button>')

    return (
        f'<div class="card" id="{CARD_ID}" data-source-improvement="swing-screener">'
        '<div class="chd"><h2>スイング候補（新ルール）<span class="h2en">Swing Screener</span></h2>'
        f'<div class="chd-now" style="color:#23824d"><b>{len(core)}</b><span>買い候補</span></div></div>'
        f'<div class="sub">{e(result["session"])} 終値基準・流動性あり {result["universe"]} 銘柄中、選定条件を満たすのは '
        f'{result.get("selected", 0)} 銘柄。</div>'
        '<details class="cxpl"><summary>ルール</summary><div class="cxpl-b">'
        '<b>選定</b>：トレンドテンプレート・50日平均売買代金が上位5%・189日リターンが上位10%'
        '（株価$10以上・売買代金$20M以上の銘柄内）。<b>形</b>：10日/50日の平均値幅0.9以下・5日/50日の出来高0.9以下。'
        '<b>追わない</b>：当日+3%未満・前日+3%以下・10日線+12%以内。<br/>'
        '<b>売買</b>：終値で買う。資金の1%リスク・−8%損切り（1銘柄は資金の約12.5%）。'
        '終値+10%で持ち株の半分を1回だけ買い増し、高値+25%で損切りを建値へ、安値21EMAを割って引けたら手仕舞い。'
        '余剰資金の50%はQQQ。<br/>'
        '<b>まだ入れる</b>：1〜2日前に条件が成立し、成立時の終値+3%以内・その後に損切り/安値21EMA割れなし・'
        '選定条件を維持・当日+3%未満・10日線+12%以内。成立日に入るより成績は落ち、地合いが悪い時期は特に悪い'
        '（PF 1日遅れ1.78・2日遅れ1.6前後）。株数は通常どおり、損切りは今の価格から−8%。<br/>'
        '<b>テーマ枠</b>：窓+5〜20%・終値+5%以上・出来高3〜15倍・上半分引け・50日線上・値幅3〜7%・'
        '相関の高い15銘柄のRS平均50〜90。リスク0.5%・同時3銘柄・60営業日で手仕舞い。<br/>'
        '2015〜2026年のバックテスト（現存銘柄・税金なし）で年率+24.5%・最大DD−28%。上場廃止銘柄は未検証。売買指示ではない。'
        '</div></details>'
        f'<div class="sw-sec">買い候補（本日の終値で条件成立）{copy_btn(core)}</div>{core_body}'
        f'<div class="sw-sec">まだ入れる（1〜2日前に成立）{copy_btn(late)}</div>{late_body}'
        f'<div class="sw-sec">テーマ枠（本日の窓開け）{copy_btn(ep)}</div>{ep_body}'
        f'<div class="sw-sec">監視（選定OK・形待ち）{copy_btn(watch[:15])}</div>{watch_body}'
        '</div>'
    )


def apply(text: str, frame: pd.DataFrame) -> str:
    if CARD_ID in text or SECTION not in text:
        return text
    try:
        card = card_html(evaluate(frame))
    except Exception as exc:  # display-only: never break publication
        print(f"swing screener skipped: {exc!r}", flush=True)
        return text
    text = text.replace(SECTION, SECTION + card, 1)
    return text.replace("</head>", STYLE + "</head>", 1)
