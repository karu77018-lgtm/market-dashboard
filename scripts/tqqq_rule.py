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
        dd52 = np.nan_to_num(qc / pd.Series(qc).rolling(252, min_periods=1).max().to_numpy() - 1)
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
            if st["cap_on"]:
                st["cap_d"] += 1
                if st["cap_d"] > 15 or ind["tqc"][i] < st["cap_ent"] * (1 - 0.15):
                    st["cap_on"] = False
            if not st["cap_on"] and bool(ind["cap"][i]):
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


def frame_from_market(market: dict) -> pd.DataFrame | None:
    """Aligned daily inputs on QQQ sessions, or None when a required input is missing."""
    q = _rows(market, "QQQ")
    t = _rows(market, "TQQQ")
    v = _rows(market, "^VIX")
    g = _rows(market, "GC=F")
    hy = _fred(market, "BAMLH0A0HYM2")
    rf = _fred(market, "DGS3MO")
    if q.empty or t.empty or v.empty or hy.empty:
        return None
    idx = q.index
    f = pd.DataFrame({"qo": q["open"], "qh": q["high"], "ql": q["low"], "qc": q["close"], "qv": q["volume"]}, index=idx)
    f["to"] = t["open"].reindex(idx)
    f["tc"] = t["close"].reindex(idx)
    f["vix"] = v["close"].reindex(idx).ffill()
    f["hy"] = hy.reindex(idx.union(hy.index)).ffill().reindex(idx)
    f["gold"] = (g["close"].reindex(idx).ffill() if not g.empty else np.nan)
    f["rf"] = (rf.reindex(idx.union(rf.index)).ffill().reindex(idx) / 100.0) if not rf.empty else 0.0
    # FRED history is shorter than the 2-year price window: keep the price rows (200-day
    # line / 52-week high) and only require HY on the latest session.
    f = f[f["tc"].notna() & f["qc"].notna()]
    return f if len(f) >= 210 and pd.notna(f["hy"].iloc[-1]) else None


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
        "gold_px": _r(row.get("gold"), 4), "rf": _r(row.get("rf"), 5), "hy": _r(row["hy"], 3), "vix": _r(row["vix"], 2),
        "state": {k: (bool(st[k]) if isinstance(st[k], bool) else _r(st[k], 6)) for k in STATE_KEYS},
    }


def update(ledger: dict, f: pd.DataFrame, session: str) -> dict:
    """Record every session after ledger['last_day'] up to ``session`` (frozen once written)."""
    dates = [d.strftime("%Y-%m-%d") for d in f.index]
    if session not in dates:
        return ledger
    last = ledger.get("last_day")
    if last and last in dates and ledger.get("state"):
        start, state = dates.index(last) + 1, ledger["state"]
    elif last and last >= session:
        return ledger
    else:  # cold start: run the whole window from the default state
        start, state = 0, None
    end = dates.index(session)
    if start > end:
        return ledger
    out, st = compute_frame(f.iloc[:end + 1], start, state)
    for i in range(max(start, 199), end + 1):  # indicators need the 200-day line
        ledger["days"][dates[i]] = day_record(f, out, i, out["states"][i])
    ledger["state"] = st
    ledger["last_day"] = session
    return ledger


# ---------------------------------------------------------------- idle-money fund (for the forward record)

def fund_bars(ledger: dict) -> dict[str, dict[str, float]]:
    """Open/close NAV of the TQQQ-rule sleeve on recorded days.

    Weights decided at a close trade at the next open (TQQQ open); gold is marked
    close to close with yesterday's weight; the rest earns the 3-month T-bill rate.
    """
    days = sorted(ledger.get("days", {}))
    bars: dict[str, dict[str, float]] = {}
    nav, prev, prev2 = 1.0, None, None
    for d in days:
        r = ledger["days"][d]
        if prev is None:
            bars[d] = {"open": nav, "close": nav}
            prev, prev2 = r, r
            continue
        wt_over = float(prev2.get("target") or 0) if prev2 is not prev else float(prev.get("target") or 0)
        wt_new = float(prev.get("target") or 0)
        wg = float(prev.get("gold") or 0)
        t0, to, t1 = prev.get("tqqq"), r.get("tqqq_open"), r.get("tqqq")
        g0, g1 = prev.get("gold_px"), r.get("gold_px")
        rf = float(prev.get("rf") or 0) / 252
        gap = (to / t0 - 1) if t0 and to else 0.0
        intra = (t1 / to - 1) if to and t1 else 0.0
        gret = (g1 / g0 - 1) if g0 and g1 else 0.0
        cash = max(0.0, 1 - wt_new - wg)
        nav_open = nav * (1 + wt_over * gap)
        nav = nav_open * (1 + wt_new * intra) * (1 + wg * gret + cash * rf)
        bars[d] = {"open": nav_open, "close": nav}
        prev2, prev = prev, r
    return bars


# ---------------------------------------------------------------- display

def latest(ledger: dict | None) -> tuple[str | None, dict | None]:
    if not ledger or not ledger.get("days"):
        return None, None
    d = max(ledger["days"])
    return d, ledger["days"][d]


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


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


def card_html(day: str | None, rec: dict | None, sleeve_pct: int | None = None, top: bool = False) -> str:
    cid = CARD_ID if top else CARD_ID + "-mini"
    if not rec:
        return (f'<div class="tqr-card" id="{cid}"><div class="tqr-top"><span class="tqr-h">{RULE_NAME}</span>'
                '<span class="tqr-v">判定不可</span></div><div class="tqr-sub">入力（QQQ・TQQQ・VIX・HY OAS）が'
                'そろわないため今日の目標を出していません。前日の比率のまま。</div></div>')
    word, cls = summary_words(rec)
    tgt = float(rec.get("target") or 0)
    gold = float(rec.get("gold") or 0)
    parts = [f"TQQQ <b>{_pct(tgt)}</b>"]
    if gold > 0:
        parts.append(f"金 {_pct(gold)}")
    rest = max(0.0, 1 - tgt - gold)
    if rest > 0.001:
        parts.append(f"短期国債 {_pct(rest)}")
    split = ""
    if sleeve_pct in (50, 100):
        t, g, c = sleeve_split(rec, sleeve_pct)
        split = (f'<div class="tqr-sub">余剰資金のうち<b>{sleeve_pct}%</b>をこの枠に（ブレイク成功度）'
                 f'→ 余剰資金の TQQQ <b>{_pct(t)}</b>' + (f'・金 {_pct(g)}' if g > 0 else '')
                 + f'・現金/短期国債 {_pct(c)}</div>')
    checks = [
        ("トレンド", "上" if rec.get("trend") else "下"),
        ("緊急", "切替型" if rec.get("md_switch") and not rec.get("md_hold") else
         "両方" if rec.get("md_switch") and rec.get("md_hold") else "改良案" if rec.get("md_hold") else "なし"),
        ("HY OAS", f'{rec.get("hy"):.2f}%' + ("（拡大）" if rec.get("hy_wide") else "") if rec.get("hy") is not None else "—"),
        ("過熱", "警報" if rec.get("alarm") else "なし"),
    ]
    chk = "".join(f'<span class="tqr-chip"><i>{html.escape(k)}</i>{html.escape(v)}</span>' for k, v in checks)
    return (f'<div class="tqr-card tqr-{cls}" id="{cid}" data-day="{html.escape(day or "")}">'
            f'<div class="tqr-top"><span class="tqr-h">{RULE_NAME}</span><span class="tqr-v">{" ・ ".join(parts)}</span>'
            f'<span class="tqr-m">{html.escape(word)}</span></div>'
            f'{split}<div class="tqr-chips">{chk}</div>'
            f'<div class="tqr-sub tqr-mut">{html.escape(day or "")} 終値で判定 → 翌営業日に執行。ルールはRulesタブ9。</div></div>')


STYLE = ('<style id="tqqq-rule-style">.tqr-card{border-radius:12px;padding:10px 14px;margin:8px 0;border:1px solid #d7d3c7;'
         'background:#f7f6f1}.tqr-card.tqr-on{background:rgba(34,197,94,.10);border-color:rgba(34,197,94,.45)}'
         '.tqr-card.tqr-warn{background:#f3ecd6;border-color:#e0cf98}.tqr-card.tqr-off{background:rgba(239,68,68,.08);'
         'border-color:rgba(239,68,68,.4)}.tqr-top{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 10px}'
         '.tqr-h{font-weight:800;font-size:14px;color:#1b1a18}.tqr-v{font-size:14px;color:#1b1a18}'
         '.tqr-m{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:#fff;border:1px solid #d7d3c7;color:#565243}'
         '.tqr-sub{font-size:11.5px;color:#565243;line-height:1.55;margin-top:4px}.tqr-mut{color:#8a877c}'
         '.tqr-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}.tqr-chip{font-size:10.5px;background:#fff;'
         'border:1px solid #e0ddd5;border-radius:6px;padding:1px 6px;color:#1b1a18}.tqr-chip i{font-style:normal;'
         'color:#8a877c;margin-right:4px}</style>')


def apply_top(text: str, ledger: dict | None, sleeve_pct: int | None) -> str:
    """Put today's TQQQ-rule card at the top of the page (where the NQ card used to be)."""
    import re
    day, rec = latest(ledger)
    card = card_html(day, rec, sleeve_pct, top=True)
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
    if 'id="tqqq-rule-style"' not in text:
        text = text.replace("</head>", STYLE + "</head>", 1)
    return text


def run_refresh(text: str, root: Path, session: str, sleeve_pct: int | None) -> str:
    """Refresh path: advance the ledger from data/market_inputs.json, then render."""
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
    return apply_top(text, ledger, sleeve_pct)


def render_only(text: str, root: Path, sleeve_pct: int | None) -> str:
    return apply_top(text, load(root / LEDGER), sleeve_pct)


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
