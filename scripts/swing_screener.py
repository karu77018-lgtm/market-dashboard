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
        r63 = ret(63)
        comp = 2 * r63 + ret(126) + r189 + ret(252)
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
                "rs21_pct": _pct_rank(ret(21), liquid), "rs63_pct": _pct_rank(r63, liquid),
                "comp_pct": _pct_rank(comp, liquid), "vc": vc.iloc[k], "vdry": vdry.iloc[k],
                "chg": chg.iloc[k], "ext10": ext10, "el21": el21.iloc[k], "checks": checks,
                "timing": timing, "selected": selected, "signal": selected & timing,
                "adr20": adr20.iloc[k], "ma50": ma50.iloc[k], "v50_prev": v50.iloc[k - 1],
                "prev_chg": chg.iloc[k - 1]}

    at.el21 = el21
    return at


STALE_DAYS = 60
PIVOT_LENGTHS = range(2, 11)


def structure_pivot(high: np.ndarray, low: np.ndarray) -> tuple[float, float]:
    """LL->HL structure on the last bar: (pivot line, HL) of the tightest valid setup.

    For each pivot length n in 2..10 a pivot low at bar p is the lowest low of p-n..p+n and is
    only known at bar p+n. When a confirmed pivot low is higher than the previous one (LL->HL),
    the highest high between them is the pivot line. The setup is invalidated once a later low
    breaks the HL. Among the valid setups on the last bar the lowest pivot line is chosen.
    Returns (nan, nan) when no valid setup exists.
    """
    n_bars = len(low)
    best_line, best_hl = np.inf, np.nan
    for n in PIVOT_LENGTHS:
        roll = pd.Series(low).rolling(2 * n + 1, center=True).min().to_numpy()
        pivots = np.where((low == roll) & ~np.isnan(low))[0]
        confirm = {p + n: p for p in pivots if p + n < n_bars}
        prev, setup = None, None
        for t in range(n_bars):
            if setup is not None and low[t] < setup[1]:
                setup = None
            if t in confirm:
                p = confirm[t]
                if prev is not None and low[p] > low[prev]:
                    setup = (p, low[p], float(np.nanmax(high[prev:p + 1])))
                prev = p
        if setup is not None and setup[2] < best_line:
            best_line, best_hl = setup[2], float(setup[1])
    return (float("nan"), float("nan")) if np.isinf(best_line) else (float(best_line), best_hl)


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

    # Consecutive sessions meeting the selection rules (capped just above the stale threshold).
    today_sel = list(selected[selected].index)
    streak = {t: 0 for t in today_sel}
    alive = set(today_sel)
    for back in range(1, STALE_DAYS + 2):
        if not alive:
            break
        sel_k = state(-back)["selected"] if back > 1 else selected
        for t in list(alive):
            if bool(sel_k.get(t, False)):
                streak[t] += 1
            else:
                alive.discard(t)
    struct_cache: dict[str, tuple[float, float]] = {}

    def struct(t: str) -> tuple[float, float]:
        if t not in struct_cache:
            hh, ll = h[t].to_numpy(dtype=float)[-260:], l[t].to_numpy(dtype=float)[-260:]
            struct_cache[t] = structure_pivot(hh, ll)
        return struct_cache[t]

    def pct_int(v) -> int | None:
        return None if pd.isna(v) else int(round(float(v)))

    def row(t: str, st: dict) -> dict:
        px = float(st["last"][t])
        line, hl = struct(t)
        inside = bool(not math.isnan(line) and px <= line)
        return {"ticker": t, "close": px, "rs189": int(round(st["rs189_pct"][t])),
                "rs21": pct_int(st["rs21_pct"].get(t)), "rs63": pct_int(st["rs63_pct"].get(t)),
                "pivot_line": line, "hl": hl, "inside": inside, "streak": streak.get(t),
                "dv": int(round(st["dv_pct"][t])), "vc": float(st["vc"][t]), "vdry": float(st["vdry"][t]),
                "chg": float(st["chg"][t]), "prev_chg": float(st["prev_chg"][t]),
                "ext10": float(st["ext10"][t]), "el21": float(st["el21"][t]),
                "stop": px * (1 - STOP), "add": px * 1.10, "be": px * 1.25}

    core = [row(t, s) for t in selected[selected & timing].index]
    core.sort(key=lambda r: (not r["inside"], -r["rs189"]))

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
    late.sort(key=lambda r: (r["lag"], not r["inside"], -r["rs189"]))

    watch = []
    for t in selected[selected & ~timing].index:
        if t in seen:
            continue
        r = row(t, s)
        r["missing"] = [k for k, m in checks.items() if not bool(m.get(t, False))]
        watch.append(r)
    watch.sort(key=lambda r: (len(r["missing"]), not r["inside"], -r["rs189"]))

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
#mc57-swing-screener .sw-sum{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 8px}
#mc57-swing-screener .sw-sum span{font-size:11px;border-radius:999px;padding:2px 9px;background:#e6e4dd;color:#4d4a40;font-weight:700}
#mc57-swing-screener .sw-sum b{font-size:13px;margin-left:3px;color:#1c1b19}
#mc57-swing-screener .sw-sec{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:14px 0 6px;font-weight:800;font-size:13px}
#mc57-swing-screener .sw-sec small{font-weight:600;color:#6f6c62;font-size:11px;margin-left:6px}
#mc57-swing-screener .sw-t{background:#fbfaf7;border:1px solid #e3e1db;border-left:4px solid #23824d;border-radius:10px;padding:9px 10px 8px;margin:7px 0;cursor:pointer}
#mc57-swing-screener .sw-t:active{background:#ecebe6}
#mc57-swing-screener .sw-t.late{border-left-color:#7aa37d}
#mc57-swing-screener .sw-t.ep{border-left-color:#3774d3}
#mc57-swing-screener .sw-top{display:flex;align-items:baseline;gap:8px}
#mc57-swing-screener .sw-tk{font-size:17px;font-weight:800;letter-spacing:.2px}
#mc57-swing-screener .sw-px{font-size:13px;font-variant-numeric:tabular-nums;color:#33312a}
#mc57-swing-screener .sw-ch{font-size:12px;font-weight:700;font-variant-numeric:tabular-nums}
#mc57-swing-screener .up{color:#18813e}#mc57-swing-screener .dn{color:#b42222}
#mc57-swing-screener .sw-rs{margin-left:auto;text-align:right;line-height:1}
#mc57-swing-screener .sw-rs b{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}
#mc57-swing-screener .sw-rs span{display:block;font-size:9px;color:#6f6c62;margin-top:2px}
#mc57-swing-screener .sw-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
#mc57-swing-screener .sw-c{font-size:10.5px;font-weight:700;border-radius:5px;padding:1px 6px;white-space:nowrap;background:#ecebe6;color:#55524a}
#mc57-swing-screener .sw-c.hl{background:#e3f1e7;color:#1f6b3f;border:1px solid #9fcdb0}
#mc57-swing-screener .sw-c.old{background:#f6e3dc;color:#9a3f2b}
#mc57-swing-screener .sw-c.miss{background:#f3ecd6;color:#6b5a1e}
#mc57-swing-screener .sw-c.ep{background:#e2ebfa;color:#2a5aa8}
#mc57-swing-screener .sw-lv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin-top:8px}
#mc57-swing-screener .sw-lv div{background:#f0efeb;border-radius:6px;padding:4px 5px;min-width:0}
#mc57-swing-screener .sw-lv i{display:block;font-style:normal;font-size:9.5px;color:#6f6c62;white-space:nowrap}
#mc57-swing-screener .sw-lv b{display:block;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#mc57-swing-screener .sw-lv .stop b{color:#b42222}
#mc57-swing-screener .sw-bar{position:relative;height:6px;border-radius:3px;background:#e6e4dd;margin:12px 4px 3px}
#mc57-swing-screener .sw-bar .in{position:absolute;top:0;bottom:0;background:#bfdcc8;border-radius:3px}
#mc57-swing-screener .sw-bar .mk{position:absolute;top:-4px;width:3px;height:14px;margin-left:-1px;background:#1c1b19;border-radius:2px}
#mc57-swing-screener .sw-bl{display:flex;justify-content:space-between;font-size:10px;color:#55524a;font-variant-numeric:tabular-nums}
#mc57-swing-screener .sw-opt{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;margin-top:4px}
#mc57-swing-screener .sw-opt div{background:#eeebf7;border-radius:6px;padding:4px 5px;min-width:0}
#mc57-swing-screener .sw-opt i{display:block;font-style:normal;font-size:9.5px;color:#5d5591;white-space:nowrap}
#mc57-swing-screener .sw-opt b{display:block;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#mc57-swing-screener .sw-opt em{font-style:normal;font-weight:600;font-size:10.5px;color:#55524a}
#mc57-swing-screener .sw-olow{font-size:10px;color:#9a3f2b;margin-top:2px}
#mc57-swing-screener .sw-ft{font-size:10.5px;color:#6f6c62;margin-top:5px;font-variant-numeric:tabular-nums}
#mc57-swing-screener .sw-w{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;border-top:1px solid #e3e1db;padding:7px 2px;cursor:pointer}
#mc57-swing-screener .sw-w:active{background:#ecebe6}
#mc57-swing-screener .sw-w .sw-tk{font-size:14px}
#mc57-swing-screener .sw-w .sw-chips{flex-basis:100%;margin-top:0}
#mc57-swing-screener .sw-empty{font-size:12px;color:#6f6c62;padding:2px 2px 4px}
#mc57-swing-screener .sw-hint{font-size:10.5px;color:#6f6c62;margin:-2px 0 4px}
</style>"""


def _p(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _d(v: float) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"${v:,.2f}"


def _ratio(v: float) -> str:
    text = f"{v:.3f}"
    return f"{v:.4f}" if text == "0.900" else text


def _miss_label(name: str, r: dict) -> str:
    """Current value -> value needed, for one unmet timing condition."""
    if name == "収縮":
        return f"値幅 {_ratio(r['vc'])} → 0.90以下"
    if name == "出来高減":
        return f"出来高 {_ratio(r['vdry'])} → 0.90以下"
    if name == "当日+3%未満":
        return f"当日 {r['chg'] * 100:+.2f}% → +3%未満"
    if name == "前日+3%以下":
        return f"前日 {r['prev_chg'] * 100:+.2f}% → +3%以下"
    if name == "10日線+12%以内":
        return f"10日線 {r['ext10'] * 100:+.2f}% → +12%以内"
    return name


def _rs3(r: dict) -> str:
    f = lambda v: "—" if v is None else str(v)
    return f"RS 21・63・189 {f(r.get('rs21'))}・{f(r.get('rs63'))}・{r['rs189']}"


def _ch(v: float) -> str:
    return f'<span class="sw-ch {"up" if v >= 0 else "dn"}">{_p(v)}</span>'


def _chips(r: dict, extra: str = "") -> str:
    out = []
    if r.get("inside"):
        out.append('<span class="sw-c hl">HL構造・ライン下</span>')
    st = r.get("streak")
    if st is not None and st > STALE_DAYS:
        out.append(f'<span class="sw-c old">選定{STALE_DAYS}日超</span>')
    elif st:
        out.append(f'<span class="sw-c">選定{st}日目</span>')
    f = lambda v: "—" if v is None else str(v)
    out.append(f'<span class="sw-c">RS21 {f(r.get("rs21"))}・63 {f(r.get("rs63"))}</span>')
    return f'<div class="sw-chips">{"".join(out)}{extra}</div>'




def _top(r: dict, right: str) -> str:
    e = html.escape
    return (f'<div class="sw-top"><span class="sw-tk">{e(r["ticker"])}</span>'
            f'<span class="sw-px">{_d(r["close"])}</span>{_ch(r["chg"])}{right}</div>')


def _rs_box(r: dict) -> str:
    return f'<div class="sw-rs"><b>{r["rs189"]}</b><span>RS189</span></div>'


def _levels(r: dict) -> str:
    cell = lambda cls, label, v: f'<div class="{cls}"><i>{label}</i><b>{_d(v)}</b></div>'
    return ('<div class="sw-lv">' + cell("stop", "損切り −8%", r["stop"]) + cell("", "安値21EMA", r["el21"])
            + cell("", "買い増し +10%", r["add"]) + cell("", "建値へ +25%", r["be"]) + '</div>')


def _struct_line(r: dict) -> str:
    """Price position between the HL (structure break) and the pivot line."""
    line, hl = r.get("pivot_line"), r.get("hl")
    if line is None or (isinstance(line, float) and math.isnan(line)) or not hl or hl >= line:
        return '<div class="sw-ft">HL構造なし（安値の切り上げ未確認）</div>'
    px = r["close"]
    lo, hi = min(hl, px), max(line, px)
    pos = lambda x: (x - lo) / (hi - lo) * 100 if hi > lo else 50
    return (f'<div class="sw-bar"><div class="in" style="left:{pos(hl):.1f}%;width:{pos(line) - pos(hl):.1f}%"></div>'
            f'<div class="mk" style="left:{pos(px):.1f}%"></div></div>'
            f'<div class="sw-bl"><span>HL {_d(hl)} {_p(hl / px - 1)}</span>'
            f'<span>ライン {_d(line)} {_p(line / px - 1)}</span></div>')


def _strike(v: float) -> str:
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"


def _opt_line(r: dict) -> str:
    o = r.get("opt")
    if not o:
        return ""
    cells = []
    for key, label in (("cw", "OP 上値の壁"), ("pw", "OP 下値の支え"), ("gf", "OP 境目")):
        v = o.get(key)
        if v and key == "gf" and v >= 100:
            v = round(v)  # an estimated level, not a listed strike
        value = f'{_strike(v)} <em>{_p(o[key + "p"])}</em>' if v else "—"
        cells.append(f'<div><i>{label}</i><b>{value}</b></div>')
    if all(not o.get(k) for k in ("cw", "pw", "gf")):
        return ""
    low = '<div class="sw-olow">建玉が薄いので参考度低め</div>' if o.get("conf") == "LOW" else ""
    return f'<div class="sw-opt">{"".join(cells)}</div>{low}'


def _foot(r: dict) -> str:
    return (f'<div class="sw-ft">値幅 {r["vc"]:.2f}・出来高 {r["vdry"]:.2f}・10日線 {_p(r["ext10"])}'
            f'・売買代金 {r["dv"]}</div>')


def card_html(result: dict) -> str:
    e = html.escape
    core, watch, ep = result["core"], result["watch"], result["ep"]
    late = result.get("late", [])
    tile = lambda cls, r, inner: f'<div class="sw-t{cls}" data-tkone="{e(r["ticker"])}">{inner}</div>'
    core_body = "".join(
        tile("", r, _top(r, _rs_box(r)) + _chips(r) + _struct_line(r) + _levels(r) + _opt_line(r) + _foot(r)) for r in core[:12]
    ) or '<div class="sw-empty">本日の買い候補なし（待つのもルール）。</div>'
    late_body = "".join(
        tile(" late", r, _top(r, _rs_box(r))
             + _chips(r, f'<span class="sw-c">{r["lag"]}日前 {e(r["signal_date"][5:].replace("-", "/"))} '
                         f'{_d(r["signal_close"])}から{_p(r["from_signal"])}</span>')
             + _struct_line(r) + _levels(r) + _opt_line(r)) for r in late[:10]
    ) or '<div class="sw-empty">該当なし。</div>'
    watch_body = "".join(
        f'<div class="sw-w" data-tkone="{e(r["ticker"])}"><span class="sw-tk">{e(r["ticker"])}</span>'
        f'<span class="sw-px">{_d(r["close"])}</span>{_ch(r["chg"])}'
        f'<span class="sw-c">RS189 {r["rs189"]}</span>'
        + ('<span class="sw-c hl">HL構造・ライン下</span>' if r.get("inside") else "")
        + '<div class="sw-chips">'
        + "".join(f'<span class="sw-c miss">{e(_miss_label(m, r))}</span>' for m in r["missing"])
        + '</div></div>' for r in watch[:15]
    ) or '<div class="sw-empty">選定条件を満たす銘柄なし。</div>'
    ep_body = "".join(
        tile(" ep", r, _top(r, f'<div class="sw-rs"><b>{r["peer"]}</b><span>テーマ強度</span></div>')
             + '<div class="sw-chips">'
             + f'<span class="sw-c ep">窓 {_p(r["gap"])}</span><span class="sw-c ep">出来高 {r["volx"]:.1f}倍</span>'
             + f'<span class="sw-c">値幅 {r["adr"] * 100:.1f}%</span>'
             + ("" if r["tt"] else '<span class="sw-c miss">トレンドテンプレ外</span>') + '</div>'
             + f'<div class="sw-lv" style="grid-template-columns:repeat(2,minmax(0,1fr))">'
             + f'<div class="stop"><i>損切り −8%</i><b>{_d(r["stop"])}</b></div>'
             + '<div><i>手仕舞い</i><b>60営業日・リスク0.5%</b></div></div>' + _opt_line(r)) for r in ep[:8]
    ) or '<div class="sw-empty">本日のテーマ枠候補なし。</div>'

    def copy_btn(items: list[dict]) -> str:
        tks = ",".join(r["ticker"] for r in items)
        if not tks:
            return ""
        return (f'<button class="cp" data-tk="{e(tks)}" onclick="copyTk(event,this)">コピー '
                f'<span class="n">{len(items)}</span></button>')

    def sec(title: str, note: str, items: list[dict]) -> str:
        return f'<div class="sw-sec"><span>{title}<small>{note}</small></span>{copy_btn(items)}</div>'

    summary = "".join(f'<span>{k}<b>{n}</b></span>' for k, n in
                      (("買い", len(core)), ("まだ入れる", len(late)), ("テーマ", len(ep)), ("監視", len(watch))))
    return (
        f'<div class="card" id="{CARD_ID}" data-source-improvement="swing-screener">'
        '<div class="chd"><h2>スイング候補（新ルール）<span class="h2en">Swing Screener</span></h2>'
        f'<div class="chd-now" style="color:#23824d"><b>{len(core)}</b><span>買い候補</span></div></div>'
        f'<div class="sub">{e(result["session"])} 終値基準・流動性あり{result["universe"]}銘柄から選定'
        f'{result.get("selected", 0)}銘柄。タップで銘柄詳細。</div>'
        f'<div class="sw-sum">{summary}</div>'
        + sec("買い候補", "本日の終値で成立", core) + core_body
        + sec("まだ入れる", "1〜2日前に成立", late) + late_body
        + sec("テーマ枠", "本日の窓開け", ep) + ep_body
        + sec("監視", "選定OK・形待ち", watch[:15])
        + '<div class="sw-hint">黄色は「今の値 → 成立に必要な値」</div>' + watch_body
        + '<details class="cxpl" style="margin-top:10px"><summary>ルールと見方</summary><div class="cxpl-b">'
        '<b>選定</b>：トレンドテンプレート・50日平均売買代金が上位5%・189日リターンが上位10%'
        '（株価$10以上・売買代金$20M以上の銘柄内）。<b>形</b>：10日/50日の平均値幅0.9以下・5日/50日の出来高0.9以下。'
        '<b>追わない</b>：当日+3%未満・前日+3%以下・10日線+12%以内。<br/>'
        '<b>売買</b>：終値で買う。資金の1%リスク・−8%損切り（1銘柄は資金の約12.5%）。'
        '終値+10%で持ち株の半分を1回だけ買い増し、高値+25%で損切りを建値へ、安値21EMAを割って引けたら手仕舞い。'
        '余剰資金の50%はQQQ。<br/>'
        '<b>バー</b>：緑の始まりがHL（切り上げた安値・割れたら構造崩れ）、緑の終わりがピボットライン'
        '（直近のLL→HL間の最高値・期間2〜10本で一番狭い構造）、黒い線が今の株価。<br/>'
        '<b>並び順</b>：HL構造・ライン下（安値が切り上がり、ラインの下で静かにしている）を優先し、その中はRS189順。'
        'バックテストでは、HL構造・ライン下のPFは2015〜20年2.22・2021〜24年1.89・2025〜26年2.34（今のルール全体は2.58・0.97・1.99）。'
        '<b>選定◯日目</b>は選定条件を連続で満たしている日数で、60日超の古いリーダーは成績が悪い（PF 1.40・0.17・0.87）。'
        'RS21・63は参考表示（並び順には使わない。RS21上位5%は追いかけになりやすい）。<br/>'
        '<b>下段の数字</b>：値幅＝10日÷50日の平均値幅、出来高＝5日÷50日の平均出来高（静かな日が続くと下がる）、'
        '10日線＝10日線からの乖離、売買代金＝流動性の順位（100が最大）。<br/>'
        '<b>OP（オプション・参考）</b>：Cboeの遅延データ。45日以内に満期のオプションで、建玉×ガンマが最大の行使価格を'
        '上値の壁（コール・今の株価より上）と下値の支え（プット・下）として表示。境目＝ディーラーのガンマが正負に入れ替わる価格'
        '（上では値動きが落ち着きやすく、下では荒れやすいとされる）。建玉は前営業日時点。ルールの判定には使わない。<br/>'
        '<b>まだ入れる</b>：1〜2日前に条件が成立し、成立時の終値+3%以内・その後に損切り/安値21EMA割れなし・'
        '選定条件を維持・当日+3%未満・10日線+12%以内。成立日に入るより成績は落ち、地合いが悪い時期は特に悪い'
        '（PF 1日遅れ1.78・2日遅れ1.6前後）。株数は通常どおり、損切りは今の価格から−8%。<br/>'
        '<b>テーマ枠</b>：窓+5〜20%・終値+5%以上・出来高3〜15倍・上半分引け・50日線上・値幅3〜7%・'
        '相関の高い15銘柄のRS平均（テーマ強度）50〜90。リスク0.5%・同時3銘柄・60営業日で手仕舞い。<br/>'
        '2015〜2026年のバックテスト（現存銘柄・税金なし）で年率+24.5%・最大DD−28%。上場廃止銘柄は未検証。売買指示ではない。'
        '</div></details>'
        '</div>'
    )


def apply(text: str, frame: pd.DataFrame, walls_fn=None) -> str:
    """Insert the card; ``walls_fn(targets, session)`` optionally adds option walls."""
    if CARD_ID in text or SECTION not in text:
        return text
    try:
        result = evaluate(frame)
    except Exception as exc:  # display-only: never break publication
        print(f"swing screener skipped: {exc!r}", flush=True)
        return text
    found: dict = {}
    if walls_fn is not None:
        rows = result["core"] + result.get("late", []) + result["ep"] + result["watch"][:15]
        try:
            found = walls_fn({r["ticker"]: r["close"] for r in rows}, result["session"]) or {}
        except Exception as exc:
            print(f"option walls skipped: {exc!r}", flush=True)
        for r in rows:
            r["opt"] = found.get(r["ticker"])
    try:
        card = card_html(result)
    except Exception as exc:
        print(f"swing screener skipped: {exc!r}", flush=True)
        return text
    text = text.replace(SECTION, SECTION + card, 1)
    text = text.replace("</head>", STYLE + "</head>", 1)
    if found:
        from options_walls import update_det
        text = update_det(text, found)
    return text
