"""TQQQ rule for the swing rule's idle money (Rules tab section 7 / 9).

Display + ledger only.  It never changes MC57, V38, Massive, FRED or publication
logic; it only reads inputs the refresh already acquired (data/market_inputs.json:
QQQ / TQQQ / ^VIX / GC=F daily rows and FRED BAMLH0A0HYM2).

Rule (validated offline 2000-2026, see Rules tab section 9):

* two halves on QQQ signals, executed in TQQQ
  - 切替型 (switch): hold while QQQ > 200-day line, or QQQ > EMA21 with EMA21 rising
    (5 days); out of trend, buy capitulation rebounds (VIX>=28 in the last 10 days
    and VIX below its 5-day mean and QQQ up, or volume > 1.5x the 20-day mean,
    close in the upper half and QQQ > 8% below its 20-day high) for at most
    15 days / -15% on TQQQ
  - 改良案 (hold): always hold
  - both size by TQQQ 20-day realized vol: min(1, 100% / vol)
  - emergency mode (switch: QQQ <= -15% from its 52-week high or -10% in 10 days;
    hold: -25%): weight = trend-on x min(1, 1 + drawdown / 30%) x min(1, 70% / vol).
    Leaves on golden cross (50 > 200-day), on a return near the high (switch -5%,
    hold -10%), or when the HY spread is below its 40-day mean and 10% below its
    10-day high
* target = 0.625 x switch + 0.375 x hold, in 25% steps (moves only when the raw
  target is >= 0.75 step away), 0% while QQQ is > 35% above its 200-day line until
  it cools below +10% (overheat alarm), at most 25% while the HY spread is above
  1.1 x its 40-day mean
* money not in TQQQ: gold while gold's 126-day return is positive, else T-bills.

State machines (emergency modes, capitulation hold, overheat alarm, 25% step) are
carried day to day in the ledger (track-record/tqqq-rule.json), so a short input
window never resets them.  Each published session is frozen once recorded.
"""
from __future__ import annotations

import html
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LEDGER = Path("track-record/tqqq-rule.json")
SCHEMA = "tqqq-rule.1"
CARD_ID = "tqqq-rule-card"
RULE_NAME = "TQQQルール"
STEP = 0.25
W_SWITCH, W_HOLD = 0.625, 0.375
STATE_KEYS = ("cap_on", "cap_d", "cap_ent", "md_switch", "md_hold", "alarm", "cur")


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).mean().to_numpy()


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _shift(x: np.ndarray, n: int) -> np.ndarray:
    return np.r_[np.full(n, np.nan), x[:-n]] if n < len(x) else np.full(len(x), np.nan)


def indicators(qo, qh, ql, qc, qv, tqc, vix, hy, gold) -> dict[str, np.ndarray]:
    """Stateless daily inputs (arrays aligned on QQQ sessions)."""
    qh, ql, qc, qv = (np.asarray(a, float) for a in (qh, ql, qc, qv))
    tqc, vix, hy, gold = (np.asarray(a, float) for a in (tqc, vix, hy, gold))
    s200, s50, e21 = _sma(qc, 200), _sma(qc, 50), _ema(qc, 21)
    with np.errstate(invalid="ignore", divide="ignore"):
        rfast = (qc > s200) | ((qc > e21) & (e21 > _shift(e21, 5)))
        vol = pd.Series(np.log(tqc)).diff().rolling(20).std().to_numpy() * math.sqrt(252)
        vol = np.nan_to_num(vol, nan=9.9)
        dd52 = np.nan_to_num(qc / pd.Series(qc).rolling(252).max().to_numpy() - 1)  # full 52 weeks only
        ret10 = np.nan_to_num(qc / _shift(qc, 10) - 1)
        spike = pd.Series(vix >= 28).rolling(10).max().fillna(0).to_numpy().astype(bool)
        cap_vix = spike & (vix < _sma(vix, 5)) & (qc > _shift(qc, 1))
        rv20 = qv / _sma(qv, 20)
        clv = np.where(qh > ql, (qc - ql) / (qh - ql), 0.5)
        dd20 = qc / pd.Series(qc).rolling(20).max().to_numpy() - 1
        cap_vol = (rv20 > 1.5) & (clv > 0.5) & (dd20 < -0.08)
        hy_ma = _sma(hy, 40)
        hy_max10 = pd.Series(hy).rolling(10).max().to_numpy()
        hy_calm = (hy < hy_ma) & (hy < hy_max10 * 0.9)
        hy_wide = hy > hy_ma * 1.10
        d200 = qc / s200 - 1
        gold_up = np.nan_to_num(gold / _shift(gold, 126) - 1) > 0
    return {"rfast": rfast, "vol": vol, "dd52": dd52, "ret10": ret10, "cap": cap_vix | cap_vol,
            "golden": s50 > s200, "hy_calm": hy_calm, "hy_wide": hy_wide, "d200": d200,
            "gold_up": gold_up, "tqc": tqc}


def default_state() -> dict[str, Any]:
    return {"cap_on": False, "cap_d": 0, "cap_ent": 0.0, "md_switch": False, "md_hold": False,
            "alarm": False, "cur": 0.0}


def run(ind: dict[str, np.ndarray], start: int = 0, state: dict | None = None) -> tuple[dict, dict]:
    """Advance the state machines over rows start..end. Returns (per-row outputs, final state)."""
    st = dict(default_state() if state is None else state)
    n = len(ind["vol"])
    out = {k: np.full(n, np.nan) for k in ("switch", "hold", "raw", "step", "target", "gold")}
    flags = {k: np.zeros(n, bool) for k in ("md_switch", "md_hold", "alarm", "cap_hold", "hy_wide", "trend")}
    states: list[dict | None] = [None] * n
    for i in range(start, n):
        vol, dd, rf = ind["vol"][i], ind["dd52"][i], bool(ind["rfast"][i])
        vt = min(1.0, 1.0 / vol) if vol > 0 else 0.0
        emerg = (min(1.0, max(0.0, 1 + dd / 0.30)) * min(1.0, 0.7 / vol)) if rf and vol > 0 else 0.0
        # capitulation hold (switch half only, outside trend)
        if rf:
            st["cap_on"], cap_hold = False, False
        else:
            ended = False
            if st["cap_on"]:
                st["cap_d"] += 1
                if st["cap_d"] > 15 or ind["tqc"][i] < st["cap_ent"] * (1 - 0.15):
                    st["cap_on"], ended = False, True
            # no new entry on the bar a hold expired or was stopped (keeps the 15-day / -15% limits)
            if not st["cap_on"] and not ended and bool(ind["cap"][i]):
                st["cap_on"], st["cap_d"], st["cap_ent"] = True, 0, float(ind["tqc"][i])
            cap_hold = st["cap_on"]
        calm = bool(ind["hy_calm"][i])
        golden = bool(ind["golden"][i])
        # emergency modes
        trig_s = dd <= -0.15 or ind["ret10"][i] <= -0.10
        exit_s = golden or dd > -0.05 or calm
        if not st["md_switch"] and trig_s:
            st["md_switch"] = True
        elif st["md_switch"] and exit_s:
            st["md_switch"] = False
        exit_h = golden or dd > -0.10 or calm
        if not st["md_hold"] and dd <= -0.25:
            st["md_hold"] = True
        elif st["md_hold"] and exit_h:
            st["md_hold"] = False
        normal_s = 1.0 if cap_hold else (vt if rf else 0.0)
        w_s = emerg if st["md_switch"] else normal_s
        w_h = emerg if st["md_hold"] else vt
        raw = W_SWITCH * w_s + W_HOLD * w_h
        # 25% steps with a 0.75-step dead band (stateful)
        lv = min((0.0, 0.25, 0.5, 0.75, 1.0), key=lambda l: abs(l - raw))
        if lv != st["cur"] and abs(raw - st["cur"]) >= 0.75 * STEP:
            st["cur"] = lv
        # overheat alarm (hysteresis)
        d2 = ind["d200"][i]
        if not math.isnan(d2):
            if not st["alarm"] and d2 > 0.35:
                st["alarm"] = True
            elif st["alarm"] and d2 < 0.10:
                st["alarm"] = False
        tgt = 0.0 if st["alarm"] else st["cur"]
        wide = bool(ind["hy_wide"][i])
        if wide:
            tgt = min(tgt, 0.25)
        out["switch"][i], out["hold"][i], out["raw"][i], out["step"][i], out["target"][i] = w_s, w_h, raw, st["cur"], tgt
        out["gold"][i] = (1 - tgt) if bool(ind["gold_up"][i]) else 0.0
        flags["md_switch"][i], flags["md_hold"][i], flags["alarm"][i] = st["md_switch"], st["md_hold"], st["alarm"]
        flags["cap_hold"][i], flags["hy_wide"][i], flags["trend"][i] = cap_hold, wide, rf
        states[i] = dict(st)
    return {**out, **flags, "states": states}, st


# ---------------------------------------------------------------- inputs

def _rows(market: dict, symbol: str) -> pd.DataFrame:
    rows = (market.get("series") or {}).get(symbol) or []
    f = pd.DataFrame(rows)
    if f.empty:
        return f
    f["date"] = pd.to_datetime(f["date"].astype(str).str[:10])
    for c in ("open", "high", "low", "close", "volume"):
        if c in f:
            f[c] = pd.to_numeric(f[c], errors="coerce")
    return f.dropna(subset=["close"]).drop_duplicates("date", keep="last").set_index("date").sort_index()


def _fred(market: dict, series_id: str) -> pd.Series:
    hist = (((market.get("fred") or {}).get("series") or {}).get(series_id) or {}).get("history") or []
    s = pd.Series({pd.Timestamp(p["date"]): float(p["value"]) for p in hist if p.get("value") is not None}, dtype=float)
    return s.sort_index()


def known_before(series: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """For each session, the last observation dated strictly before it (FRED one-day lag)."""
    s = series.dropna().sort_index()
    return pd.Series(s.asof(idx - pd.Timedelta(days=1)).to_numpy(dtype=float) if len(s) else np.nan, index=idx)


def frame_from_market(market: dict) -> pd.DataFrame | None:
    """Aligned daily inputs on QQQ sessions, or None when a required input is missing.

    Required on the latest session: QQQ, TQQQ, VIX, HY OAS (FRED may lag a few days and
    is carried forward) and gold (a gold bar within 4 days and 127 observations for the
    126-day test).  A missing input keeps the last frozen recommendation instead of
    publishing a different allocation.
    """
    q = _rows(market, "QQQ")
    t = _rows(market, "TQQQ")
    v = _rows(market, "^VIX")
    g = _rows(market, "GC=F")
    hy = _fred(market, "BAMLH0A0HYM2")
    rf = _fred(market, "DGS3MO")
    if q.empty or t.empty or v.empty or hy.empty or g.empty:
        return None
    idx = q.index
    f = pd.DataFrame({"qo": q["open"], "qh": q["high"], "ql": q["low"], "qc": q["close"], "qv": q["volume"]}, index=idx)
    f["to"] = t["open"].reindex(idx)
    f["tc"] = t["close"].reindex(idx)
    f["vix"] = v["close"].reindex(idx).ffill()
    # FRED values are published the next morning: a session uses the last value dated
    # before it (never the same day's value, which was not known at the close).
    f["hy"] = known_before(hy, idx)
    f["gold"] = g["close"].reindex(idx.union(g.index)).ffill().reindex(idx)
    f["gopen"] = g["open"].reindex(idx) if "open" in g else np.nan
    f["rf"] = (known_before(rf, idx) / 100.0) if not rf.empty else 0.0
    # FRED history is shorter than the 2-year price window: keep the price rows (200-day
    # line / 52-week high) and only require HY on the latest session.
    f = f[f["tc"].notna() & f["qc"].notna()]
    if len(f) < 260 or pd.isna(f["hy"].iloc[-1]) or pd.isna(f["vix"].iloc[-1]):
        return None
    last = f.index[-1]
    if (last - g.index[g.index <= last].max()).days > 4 or g["close"].loc[:last].notna().sum() < 127:
        return None
    return f


def compute_frame(f: pd.DataFrame, start: int = 0, state: dict | None = None) -> tuple[dict, dict]:
    ind = indicators(f["qo"].to_numpy(), f["qh"].to_numpy(), f["ql"].to_numpy(), f["qc"].to_numpy(),
                     f["qv"].to_numpy(), f["tc"].to_numpy(), f["vix"].to_numpy(), f["hy"].to_numpy(),
                     f["gold"].to_numpy() if "gold" in f else np.full(len(f), np.nan))
    return run(ind, start, state)


# ---------------------------------------------------------------- ledger

def new_ledger() -> dict[str, Any]:
    return {"schema": SCHEMA, "days": {}, "last_day": None, "state": None}


def load(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and obj.get("schema") == SCHEMA:
            return obj
    except Exception:
        pass
    return new_ledger()


def save(ledger: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(ledger, h, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        h.write("\n")
    os.replace(tmp, path)


def _r(x: Any, nd: int = 4) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def day_record(f: pd.DataFrame, out: dict, i: int, st: dict) -> dict[str, Any]:
    row = f.iloc[i]
    return {
        "target": _r(out["target"][i], 3), "gold": _r(out["gold"][i], 3), "raw": _r(out["raw"][i]),
        "switch": _r(out["switch"][i]), "hold": _r(out["hold"][i]),
        "md_switch": bool(out["md_switch"][i]), "md_hold": bool(out["md_hold"][i]),
        "alarm": bool(out["alarm"][i]), "cap_hold": bool(out["cap_hold"][i]), "hy_wide": bool(out["hy_wide"][i]),
        "trend": bool(out["trend"][i]),
        "qqq": _r(row["qc"], 4), "tqqq_open": _r(row["to"], 4), "tqqq": _r(row["tc"], 4),
        "gold_open": _r(row.get("gopen"), 4), "gold_px": _r(row.get("gold"), 4), "rf": _r(row.get("rf"), 5),
        "hy": _r(row["hy"], 3), "vix": _r(row["vix"], 2),
        "state": {k: (bool(st[k]) if isinstance(st[k], bool) else _r(st[k], 6)) for k in STATE_KEYS},
    }


FIRST_RECORD = 251  # every lookback (200-day line, 52-week high) is complete from here on


def update(ledger: dict, f: pd.DataFrame, session: str) -> dict:
    """Record every session after ledger['last_day'] up to ``session`` (frozen once written).

    A ledger with history continues only from its own last day and state.  When the
    input window no longer contains that day (a gap in the download) the ledger is left
    unchanged rather than restarted, so frozen days and the state machines never reset.
    """
    dates = [d.strftime("%Y-%m-%d") for d in f.index]
    if session not in dates:
        return ledger
    last = ledger.get("last_day")
    if ledger.get("days"):
        if not last or last >= session:
            return ledger
        if last not in dates or not ledger.get("state"):
            print(f"TQQQ rule: ledger last day {last} not in the input window; not updated", flush=True)
            return ledger
        start, state = dates.index(last) + 1, ledger["state"]
    else:  # cold start: run the whole window from the default state
        start, state = 0, None
    end = dates.index(session)
    if start > end:
        return ledger
    out, st = compute_frame(f.iloc[:end + 1], start, state)
    for i in range(max(start, FIRST_RECORD), end + 1):
        ledger["days"][dates[i]] = day_record(f, out, i, out["states"][i])
    if not ledger["days"]:
        return ledger
    ledger["state"] = st
    ledger["last_day"] = session
    return ledger


# ---------------------------------------------------------------- idle-money fund (for the forward record)

def fund_bars(ledger: dict) -> dict[str, dict[str, float]]:
    """Open/close NAV of the TQQQ-rule sleeve on recorded days.

    Held as units: the weights decided at a close are bought at the next open (TQQQ
    open, gold open) and the whole sleeve is marked together, so the day return is the
    weighted sum of TQQQ, gold and T-bill returns; the overnight gap belongs to the
    holdings bought the previous morning.  Without a recorded gold open the gold trade
    uses the previous close.
    """
    days = sorted(ledger.get("days", {}))
    bars: dict[str, dict[str, float]] = {}
    prev = None
    ut = ug = cash = 0.0
    nav = 1.0
    for d in days:
        r = ledger["days"][d]
        if prev is None:
            bars[d] = {"open": nav, "close": nav}
            prev, cash = r, 1.0
            continue
        to, t1 = _r(r.get("tqqq_open"), 8) or _r(prev.get("tqqq"), 8), _r(r.get("tqqq"), 8)
        g1 = _r(r.get("gold_px"), 8) or _r(prev.get("gold_px"), 8)
        go = _r(r.get("gold_open"), 8) or _r(prev.get("gold_px"), 8) or g1
        nav_open = ut * (to or 0.0) + ug * (go or 0.0) + cash
        wt, wg = float(prev.get("target") or 0), float(prev.get("gold") or 0)
        if not to or (wg > 0 and not go):
            wt, wg = 0.0, 0.0
        ut = wt * nav_open / to if to else 0.0
        ug = wg * nav_open / go if go else 0.0
        cash = nav_open * (1 - wt - wg)
        rf = float(prev.get("rf") or 0) / 252
        cash *= 1 + rf
        nav = ut * (t1 or to or 0.0) + ug * (g1 or go or 0.0) + cash
        bars[d] = {"open": nav_open, "close": nav}
        prev = r
    return bars


# ---------------------------------------------------------------- display

def latest(ledger: dict | None) -> tuple[str | None, dict | None]:
    if not ledger or not ledger.get("days"):
        return None, None
    d = max(ledger["days"])
    return d, ledger["days"][d]


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _pp(x: float) -> str:
    """Share of total assets: whole numbers, one decimal only when needed (16.5%)."""
    v = round(x * 100 + 1e-9, 1)
    return f"{v:.0f}%" if abs(v - round(v)) < 1e-9 else f"{v:.1f}%"


def summary_words(rec: dict) -> tuple[str, str]:
    """(mode label, css class)."""
    if rec.get("alarm"):
        return "過熱警報（0%）", "off"
    if rec.get("hy_wide"):
        return "信用スプレッド拡大（上限25%）", "warn"
    if rec.get("md_switch") or rec.get("md_hold"):
        return "緊急モード", "warn"
    return "平時", "on"


def sleeve_split(rec: dict, sleeve_pct: int) -> tuple[float, float, float]:
    """Shares of the swing rule's idle money: (TQQQ, gold, T-bills/cash)."""
    s = sleeve_pct / 100.0
    t = s * float(rec.get("target") or 0)
    g = s * float(rec.get("gold") or 0)
    return t, g, max(0.0, 1 - t - g)


def total_split(rec: dict, sleeve_pct: int, stock: float) -> tuple[float, float, float, float]:
    """Shares of total assets: (stocks, TQQQ, gold, cash/T-bills) for a stock share."""
    t, g, _ = sleeve_split(rec, sleeve_pct)
    idle = max(0.0, 1 - stock)
    return stock, idle * t, idle * g, max(0.0, idle * (1 - t - g))


COLORS = {"stock": "#467ed6", "tqqq": "#18813d", "gold": "#c99a2e", "cash": "#b9b5aa"}
EXAMPLES = (0.0, 0.25, 0.5, 0.75)


def card_html(day: str | None, rec: dict | None, sleeve_pct: int | None = None, top: bool = False,
              stock: float | None = None, session: str | None = None,
              holdings: dict | None = None) -> str:
    from swing_allocation import MAX_NAMES, INITIAL_WEIGHT
    cid = CARD_ID if top else CARD_ID + "-mini"
    e = html.escape
    if not rec:
        return (f'<div class="tqr-card" id="{cid}"><div class="tqr-top"><span class="tqr-h">{RULE_NAME}</span>'
                '<span class="tqr-m">判定不可</span></div><div class="tqr-sub">入力（QQQ・TQQQ・VIX・HY OAS・金）が'
                'そろわないため今日の目標を出していません。前日の比率のまま。</div></div>')
    word, cls = summary_words(rec)
    pct = sleeve_pct if sleeve_pct in (50, 100) else 50
    tgt, gold = float(rec.get("target") or 0), float(rec.get("gold") or 0)
    stale = (f'<div class="tqr-stale">{e(session)}の入力が欠けたため、{e(day or "")}の判定のままです。</div>'
             if session and day and day < session else "")
    # 1) total assets: stocks / TQQQ / gold / cash
    s_pct = round(stock * 100) / 100 if stock is not None else None
    t_in, g_in, c_in = sleeve_split(rec, pct)          # shares of the money not in stocks
    fill = (f'枠の <b>{_pct(tgt)}</b> をTQQQ' + (f'・<b>{_pct(gold)}</b> を金' if gold > 0 else '')
            + ('・残りを短期国債' if tgt + gold < 0.999 else ''))
    if s_pct is not None:
        st_, tq, gd, ca = total_split(rec, pct, s_pct)
        parts = [("stock", "個別株", st_), ("tqqq", "TQQQ", tq), ("gold", "金", gd), ("cash", "現金・短期国債", ca)]
        head = '<div class="tqr-big">現在の個別株比率を使った資産全体の目標配分</div>'
        if holdings:
            head += holdings_html(holdings)
        how = (f'<div class="tqr-how">個別株以外の <b>{_pp(1 - st_)}</b> のうち <b>{pct}%</b> が枠（ブレイク成功度で50%か100%）→ '
               f'{fill} ＝ 全体の TQQQ <b>{_pp(tq)}</b>。枠の外は現金。'
               f'個別株{_pp(st_)}はサイトの保有記録の評価比率。TQQQ・金・現金は余剰資金の目標配分で、保存済みの保有そのものではありません。実口座とは別です。自分の比率が違うときは下の表で。</div>')
    else:
        parts = [("tqqq", "TQQQ", t_in), ("gold", "金", g_in), ("cash", "現金・短期国債", c_in)]
        head = ('<div class="tqr-big">個別株以外のお金の配分（今日の目標）</div>'
                f'<div class="tqr-sub" data-stock-allocation="pending">通常スイング最大{MAX_NAMES}銘柄・初回{INITIAL_WEIGHT:.0%}。'
                '新ルールの保有比率は記録開始待ちのため、資産全体の目標は未表示です。旧ルールの保有比率は使いません。</div>')
        how = (f'<div class="tqr-how">個別株以外のお金の <b>{pct}%</b> が枠（ブレイク成功度で50%か100%）→ {fill}。'
               '枠の外は現金。資産全体での比率は下の表で。</div>')
    bar = '<div class="tqr-bar">' + "".join(
        f'<i style="width:{v * 100:.2f}%;background:{COLORS[k]}"></i>' for k, _, v in parts if v > 0.0005) + '</div>'
    legend = '<div class="tqr-leg">' + "".join(
        f'<span><i style="background:{COLORS[k]}"></i>{n} <b>{_pp(v)}</b></span>' for k, n, v in parts
        if v > 0.0005 or k in ("stock", "tqqq")) + '</div>'
    # 3) your own stock share
    cols = list(EXAMPLES)
    rows = [("TQQQ", lambda s: total_split(rec, pct, s)[1])]
    if gold > 0:
        rows.append(("金", lambda s: total_split(rec, pct, s)[2]))
    rows.append(("現金・国債", lambda s: total_split(rec, pct, s)[3]))
    table = ('<table class="tqr-tab"><tr><th>自分の個別株</th>' + "".join(f'<th>{_pp(c)}</th>' for c in cols) + '</tr>'
             + "".join(f'<tr><td>{n}</td>' + "".join(f'<td>{_pp(fn(c))}</td>' for c in cols) + '</tr>' for n, fn in rows)
             + '</table>')
    checks = [
        ("トレンド", "上" if rec.get("trend") else "下"),
        ("緊急", "切替型" if rec.get("md_switch") and not rec.get("md_hold") else
         "両方" if rec.get("md_switch") and rec.get("md_hold") else "改良案" if rec.get("md_hold") else "なし"),
        ("HY OAS", f'{rec.get("hy"):.2f}%' + ("（拡大）" if rec.get("hy_wide") else "") if rec.get("hy") is not None else "—"),
        ("過熱", "警報" if rec.get("alarm") else "なし"),
    ]
    chk = "".join(f'<span class="tqr-chip"><i>{e(k)}</i>{e(v)}</span>' for k, v in checks)
    return (f'<div class="tqr-card tqr-{cls}" id="{cid}" data-day="{e(day or "")}">'
            f'<div class="tqr-top"><span class="tqr-h">{RULE_NAME}</span><span class="tqr-m">{e(word)}</span>'
            f'<span class="tqr-d">{e((day or "")[5:].replace("-", "/"))} 終値で判定→翌営業日に執行</span></div>'
            + stale + head + bar + legend + how
            + f'<details class="tqr-more"{" open" if s_pct is None else ""}><summary>自分の個別株比率で読み替え（資産全体の%）</summary>' + table
            + f'<div class="tqr-sub tqr-mut">計算：TQQQ＝（100%−個別株）×枠{pct}%×目標{_pct(tgt)}。ルールはRulesタブ9。</div></details>'
            f'<div class="tqr-chips">{chk}</div></div>')


STYLE = ('<style id="tqqq-rule-style">.tqr-card{border-radius:12px;padding:10px 14px;margin:8px 0;border:1px solid #d7d3c7;'
         'background:#f7f6f1}.tqr-card.tqr-on{background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.45)}'
         '.tqr-card.tqr-warn{background:#f3ecd6;border-color:#e0cf98}.tqr-card.tqr-off{background:rgba(239,68,68,.08);'
         'border-color:rgba(239,68,68,.4)}.tqr-top{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}'
         '.tqr-h{font-weight:800;font-size:14px;color:#1b1a18}.tqr-d{font-size:11px;color:#8a877c;margin-left:auto}'
         '.tqr-m{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:#fff;border:1px solid #d7d3c7;color:#565243}'
         '.tqr-big{font-size:12px;font-weight:700;color:#565243;margin:8px 0 5px}'
         '.tqr-bar{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#e9e7e0}.tqr-bar i{display:block;height:100%}'
         '.tqr-leg{display:flex;flex-wrap:wrap;gap:2px 14px;margin:6px 0 2px;font-size:13px;color:#565243}'
         '.tqr-leg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}'
         '.tqr-leg b{color:#1b1a18;font-size:16px}.tqr-how{font-size:11.5px;color:#565243;line-height:1.6;margin-top:6px}'
         '.tqr-stale{font-size:12px;font-weight:700;color:#8a5a00;background:#f3ecd6;border:1px solid #e0cf98;'
         'border-radius:8px;padding:5px 8px;margin-top:6px}'
         '.tqr-more{margin-top:6px}.tqr-more summary{font-size:11.5px;color:#467ed6;cursor:pointer}'
         '.tqr-tab{width:100%;border-collapse:collapse;font-size:11.5px;margin:4px 0;table-layout:fixed}'
         '.tqr-tab th,.tqr-tab td{border-bottom:1px solid #e0ddd5;padding:3px 4px;text-align:right;'
         'font-variant-numeric:tabular-nums;white-space:nowrap}.tqr-tab th:first-child,.tqr-tab td:first-child'
         '{text-align:left;width:30%}.tqr-tab th{color:#706e64;font-weight:700;font-size:10.5px}'
         '.tqr-sub{font-size:11.5px;color:#565243;line-height:1.55;margin-top:4px}.tqr-mut{color:#8a877c}'
         '.tqr-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}.tqr-chip{font-size:10.5px;background:#fff;'
         'border:1px solid #e0ddd5;border-radius:6px;padding:1px 6px;color:#1b1a18}.tqr-chip i{font-style:normal;'
         'color:#8a877c;margin-right:4px}</style>')


def holding_state(root: Path) -> dict | None:
    """Latest marked saved model inventory, including inherited positions.

    Never substitute 5x20%, today's candidates, or a fresh simulation's empty
    start for quantities that are actually present in the saved holding record.
    """
    try:
        import track_record
        import track_portfolio as tp
        ledger = track_record.load(root / track_record.LEDGER)
        pf = tp.current_portfolio(ledger)
        if not pf:
            return None
        eq = [e for e in pf.get("equity", []) if e[1] is not None]
        if len(eq) < 2 or eq[-1][1] <= 0:
            return None
        total = float(eq[-1][1])
        positions = [{"ticker": t, "share": p["shares"] * p["last"] / total,
                      "stale": bool(p.get("stale"))} for t, p in pf.get("positions", {}).items()]
        stock = sum(p["share"] for p in positions)
        cash = pf["cash"] / total
        sleeve = 1 - stock - cash
        return {"as_of": eq[-1][0], "stock": stock, "cash": cash, "sleeve_share": sleeve,
                "sleeve": "QQQ" if pf.get("sleeve") == "legacy-qqq" else "TQQQルール枠（NAV）",
                "positions": positions, "inherited": pf.get("inventory_origin", {}).get("rule") != track_record.RULE_ID}
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def holdings_html(state: dict) -> str:
    """Separate dated actual model inventory from the prospective sleeve target."""
    from swing_allocation import MAX_NAMES, INITIAL_WEIGHT
    e = html.escape
    holdings = "・".join(f'{e(p["ticker"])} {p["share"]:.1%}' + ("（最終価格）" if p["stale"] else "")
                         for p in state["positions"])
    return (f'<div class="tqr-sub" data-stock-allocation="recorded" data-stock-asof="{e(state["as_of"])}">'
            f'<b>現在の保有記録：{e(state["as_of"])}終値時点</b>。個別株 <b>{state["stock"]:.1%}</b>'
            f'（{len(state["positions"])}銘柄）。通常スイングは最大{MAX_NAMES}銘柄・新規の初回{INITIAL_WEIGHT:.0%}。'
            + ('既存の保有数量を旧配分から引き継ぎ、20%ずつに買い直していません。' if state["inherited"] else '')
            + '<details class="tqr-more"><summary>保有内訳（モデル記録・実口座ではありません）</summary>'
            f'<div class="tqr-sub">{holdings or "個別株なし"}<br/>'
            f'{e(state["sleeve"])} {state["sleeve_share"]:.1%}・現金 {state["cash"]:.1%}。'
            '下のTQQQ・現金比率は余剰資金を配分する次営業日の目標です。</div></details></div>')


def stock_share(root: Path) -> float | None:
    state = holding_state(root)
    return state["stock"] if state else None


def page_session(root: Path) -> str | None:
    try:
        return json.loads((root / "latest-manifest.json").read_text(encoding="utf-8")).get("session_date")
    except Exception:
        return None


def apply_top(text: str, ledger: dict | None, sleeve_pct: int | None, stock: float | None = None,
              session: str | None = None, holdings: dict | None = None) -> str:
    """Put today's TQQQ-rule card at the top of the page (where the NQ card used to be)."""
    import re
    day, rec = latest(ledger)
    card = card_html(day, rec, sleeve_pct, top=True, stock=stock, session=session, holdings=holdings)
    m = re.search(rf'<div[^>]*\bid="{CARD_ID}"', text)
    if m:
        # replace the existing card (balanced divs)
        depth, pos = 0, m.start()
        for tag in re.finditer(r"<(/?)div\b[^>]*>", text[pos:]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                text = text[:pos] + card + text[pos + tag.end():]
                break
    else:
        i = text.find("<nav")
        if i < 0:
            return text
        text = text[:i] + card + text[i:]
    text = re.sub(r'<style id="tqqq-rule-style">.*?</style>', "", text, count=1, flags=re.S)
    return text.replace("</head>", STYLE + "</head>", 1)


def update_ledger(root: Path, session: str) -> dict:
    """Refresh path: advance the ledger from data/market_inputs.json (before the forward record)."""
    path = root / LEDGER
    ledger = load(path)
    try:
        market = json.loads((root / "data" / "market_inputs.json").read_text(encoding="utf-8"))
        f = frame_from_market(market)
        if f is not None:
            ledger = update(ledger, f, session)
            save(ledger, path)
        else:
            print("TQQQ rule: inputs incomplete; keeping the last recorded day", flush=True)
    except Exception as exc:  # display + ledger only
        print(f"TQQQ rule update skipped: {exc!r}", flush=True)
    return ledger


def render_only(text: str, root: Path, sleeve_pct: int | None, session: str | None = None) -> str:
    """Render the committed ledger; the stock share comes from the forward record."""
    state = holding_state(root)
    return apply_top(text, load(root / LEDGER), sleeve_pct, state["stock"] if state else None,
                     session or page_session(root), holdings=state)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import track_portfolio as tp

    ap = argparse.ArgumentParser(description="Render the committed TQQQ-rule ledger (display workflows).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    text = page.read_text(encoding="utf-8")
    page.write_text(render_only(text, root, tp.published_qqq_pct(text)), encoding="utf-8")
