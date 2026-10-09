"""Forward record of the swing rule run as the actual 5-slot portfolio.

The Rules tab's money management, applied day by day to the 本命 lists exactly as
they were first published (track-record/signals.json):

* capital starts at 1.0 on the first recorded session; at most 5 names;
* a 本命 published after session S's close is bought at the next session's open
  (the list is published after the close, so that is the first price a reader can
  get; the Rules tab's backtest buys at S's close).  Only when that session's
  regime was "on".  Slots short: higher 189-day return first.  A name already
  held is not bought twice;
* first purchase = 20% of equity at that open; stop = entry x 0.92 (a gap below
  exits at the open, otherwise at the stop);
* a close at entry x 1.10 / 1.20 buys the SAME amount again at the next open,
  never taking the name above 40% of equity;
* a close below the 21-EMA of lows sells at the next open;
* idle money (cash + the TQQQ-rule sleeve) is rebalanced at each open to the
  published sleeve share (Rules tab section 7: 50%, or 100% when breakout success
  is weak and QQQ is above its 200-day line); the rest is cash at 0%.  The sleeve
  is the TQQQ rule (section 9) marked by tqqq_rule.fund_bars (TQQQ / gold /
  T-bills at the published weights).  Until October 2026 the sleeve was QQQ;
  old ledgers are retained separately, never rebuilt as current-rule results;
* equity is marked at each close.  No fees, slippage, taxes or theme slots.

State is persisted and advanced only through sessions after ``last_day``; it is
never recomputed from the chart window, so results cannot drift.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

import pandas as pd

from swing_allocation import RULE_ID, MAX_NAMES, INITIAL_WEIGHT, EFFECTIVE_DATE
STOP = 0.08
ADDS = (0.10, 0.20)
CAP = 0.40
ALPHA = 2 / 22
DEFAULT_QQQ_PCT = 50
SLEEVE = "tqqq-rule"
QQQ_PCT_RE = re.compile(r"余剰資金の(?:QQQ|TQQQルール枠)\s*(\d+)%")


def published_qqq_pct(text: str) -> int | None:
    """The idle-cash QQQ share the Rules tab published for this session."""
    start = text.find('id="rules-card"')
    if start < 0:
        return None
    m = QQQ_PCT_RE.search(text, start, start + 20000)
    return int(m.group(1)) if m and int(m.group(1)) in (0, 50, 100) else None


def new_portfolio(start: str, *, legacy_tqqq: bool = False) -> dict[str, Any]:
    return {"start": start, "last_day": start, "cash": 1.0, "qqq_sh": 0.0, "qqq_pct": DEFAULT_QQQ_PCT,
            "sleeve": SLEEVE, "rule": "swing-v3.1-tqqq-sleeve" if legacy_tqqq else RULE_ID, "max_names": 6 if legacy_tqqq else MAX_NAMES, "initial_weight": 1 / 6 if legacy_tqqq else INITIAL_WEIGHT, "positions": {}, "closed": [], "skipped": [], "equity": [[start, 1.0, None]]}


def current_portfolio(ledger: dict) -> dict | None:
    """Carry saved inventory forward independently of the pure-v4 performance series.

    Reading is non-mutating. Historical quantities, cash, marks and add units are
    preserved; only future entry limits/sizing adopt the current rule.
    """
    if ledger.get("current_portfolio"):
        return copy.deepcopy(ledger["current_portfolio"])
    histories = ledger.get("portfolio_history", [])
    source = histories[-1]["portfolio"] if histories else ledger.get("portfolio")
    if not source:
        return None
    pf = copy.deepcopy(source)
    origin = pf.get("rule", histories[-1].get("rule", "legacy") if histories else ledger.get("rule", "legacy"))
    pf.update(rule=RULE_ID, max_names=MAX_NAMES, initial_weight=INITIAL_WEIGHT)
    if pf.get("sleeve") != SLEEVE:
        pf["sleeve"] = "legacy-qqq"
    pf["allocation_effective_date"] = EFFECTIVE_DATE
    pf["inventory_origin"] = {"rule": origin, "as_of": source["last_day"],
                               "max_names": source.get("max_names", 6),
                               "initial_weight": source.get("initial_weight", 1 / 6),
                               "method": "carry-saved-quantities-no-reweight"}
    return pf


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _bar(bars: dict[str, pd.DataFrame], t: str, day: str) -> tuple[float, float, float] | None:
    g = bars.get(t)
    if g is None:
        return None
    ts = pd.Timestamp(day)
    if ts not in g.index:
        return None
    row = g.loc[ts]
    o, lo, c = _f(row["open"]), _f(row["low"]), _f(row["close"])
    return (o, lo, c) if None not in (o, lo, c) and o > 0 else None


def _ema_until(bars: dict[str, pd.DataFrame], t: str, day: str) -> float | None:
    g = bars.get(t)
    if g is None:
        return None
    lows = g.loc[g.index <= pd.Timestamp(day), "low"].astype(float).dropna()
    return float(lows.ewm(span=21, adjust=False).mean().iloc[-1]) if len(lows) else None


def _sell(pf: dict, t: str, day: str, price: float, reason: str) -> None:
    p = pf["positions"].pop(t)
    proceeds = p["shares"] * price
    pf["cash"] += proceeds
    pf["closed"].append({"t": t, "signal": p["signal"], "entry_day": p["entry_day"], "entry": p["entry"],
                         "exit_day": day, "exit": price, "reason": reason, "adds": p["adds"],
                         "invested": p["invested"], "pnl": proceeds - p["invested"],
                         "ret": proceeds / p["invested"] - 1, "days": p["days"]})


def _fund(pf: dict, amount: float, q_open: float) -> float:
    """Take up to ``amount`` from cash, then from the QQQ sleeve.  Returns what was funded."""
    idle = pf["cash"] + pf["qqq_sh"] * q_open
    amount = max(0.0, min(amount, idle))
    from_cash = min(pf["cash"], amount)
    pf["cash"] -= from_cash
    rest = amount - from_cash
    if rest > 0:
        pf["qqq_sh"] -= rest / q_open
    return amount


def _value(pf: dict, px: dict[str, float], q: float) -> float:
    return pf["cash"] + pf["qqq_sh"] * q + sum(p["shares"] * px.get(t, p["last"]) for t, p in pf["positions"].items())


def step(pf: dict, day: str, prev: str, q: dict, signal: dict | None, bars: dict[str, pd.DataFrame],
         sleeve: dict | None = None) -> None:
    """Advance the portfolio through one session ``day`` (``prev`` = previous session).

    ``q`` is QQQ (benchmark).  ``sleeve`` is the idle-money instrument's open/close
    (the TQQQ-rule NAV); without it the sleeve is QQQ itself (the pre-October-2026 rule).
    """
    bench_close = _f(q.get("close"))
    s = sleeve if sleeve is not None else q
    q_open, q_close = _f(s.get("open")), _f(s.get("close"))
    today = {t: _bar(bars, t, day) for t in pf["positions"]}
    # 1. at the open: confirmed 21-EMA breaks, then gap stops
    for t, b in list(today.items()):
        p = pf["positions"][t]
        if b is None:
            continue
        if p.get("pending_exit"):
            _sell(pf, t, day, b[0], "安値21EMA割れ（翌始値）")
        elif b[0] <= p["stop"]:
            _sell(pf, t, day, b[0], "損切り（窓）")
    held_open = {t: today[t][0] for t in pf["positions"] if today.get(t)}
    equity_open = _value(pf, held_open, q_open)
    # 2. same-amount adds, capped at 40% of equity
    for t, p in pf["positions"].items():
        b = today.get(t)
        for _ in range(int(p.get("pending_add", 0))):
            if b is None:
                break
            room = CAP * equity_open - p["shares"] * b[0]
            amt = _fund(pf, min(p["unit"], room), q_open) if room > 0 else 0.0
            if amt > 0:
                p["shares"] += amt / b[0]
                p["invested"] += amt
                p["adds"] += 1
        p["pending_add"] = 0
    # 3. new entries from the list published after prev's close
    # A lagging inherited record catches up with its original sizing until the
    # announced cutover date. Current rules never retroactively size past trades.
    origin = pf.get("inventory_origin", {})
    before_cutover = day < pf.get("allocation_effective_date", "")
    max_names = origin.get("max_names", pf["max_names"]) if before_cutover else pf["max_names"]
    initial_weight = origin.get("initial_weight", pf["initial_weight"]) if before_cutover else pf["initial_weight"]
    if signal and signal.get("regime") == "on":
        names = [r for r in signal.get("best", []) if r["t"] not in pf["positions"]]
        names.sort(key=lambda r: (r.get("r189") is None, -(r.get("r189") or 0.0)))  # stable: card order on ties
        for r in names:
            t = r["t"]
            if len(pf["positions"]) >= max_names:
                pf["skipped"].append({"t": t, "signal": prev, "day": day, "why": f"{max_names}銘柄で満杯"})
                continue
            b = _bar(bars, t, day)
            ema = _ema_until(bars, t, prev)
            if b is None or ema is None:
                pf["skipped"].append({"t": t, "signal": prev, "day": day, "why": "株価データなし"})
                continue
            unit = equity_open * initial_weight
            amt = _fund(pf, unit, q_open)
            if amt <= 1e-9:
                pf["skipped"].append({"t": t, "signal": prev, "day": day, "why": "資金不足"})
                continue
            pf["positions"][t] = {"signal": prev, "entry_day": day, "entry": b[0], "stop": b[0] * (1 - STOP),
                                  "shares": amt / b[0], "unit": unit, "invested": amt, "adds": 0,
                                  "triggered": [], "pending_add": 0, "pending_exit": False,
                                  "ema": ema, "last": b[0], "days": 0}
            today[t] = b
    pf["skipped"] = pf["skipped"][-300:]
    # 4. idle money to the published QQQ share
    if signal and signal.get("qqq_pct") in (0, 50, 100):
        pf["qqq_pct"] = signal["qqq_pct"]
    idle = pf["cash"] + pf["qqq_sh"] * q_open
    pf["qqq_sh"] = idle * pf["qqq_pct"] / 100 / q_open
    pf["cash"] = idle - pf["qqq_sh"] * q_open
    # 5. intraday stops, then the close
    closes: dict[str, float] = {}
    for t in list(pf["positions"]):
        p, b = pf["positions"][t], today.get(t)
        if b is None:
            p["stale"] = True
            continue
        p.pop("stale", None)
        p["days"] += 1
        if b[1] <= p["stop"]:
            _sell(pf, t, day, p["stop"], "損切り −8%")
            continue
        p["ema"] = ALPHA * b[1] + (1 - ALPHA) * p["ema"]
        p["last"] = closes[t] = b[2]
        if b[2] < p["ema"]:
            p["pending_exit"] = True
            continue
        for n, lvl in enumerate(ADDS):
            if n not in p["triggered"] and round(b[2] / p["entry"] - 1, 9) >= lvl:
                p["triggered"].append(n)
                p["pending_add"] = int(p.get("pending_add", 0)) + 1
    pf["equity"].append([day, _value(pf, closes, q_close), bench_close])
    pf["last_day"] = day


def advance(pf: dict, sessions: dict[str, dict], frame: pd.DataFrame, qqq: dict[str, dict], until: str,
            fund: dict[str, dict] | None = None) -> dict:
    """Run every session after pf['last_day'] up to ``until`` that has a QQQ open and close
    (and, for the TQQQ-rule sleeve, a recorded sleeve NAV)."""
    if pf.get("rule") not in (RULE_ID, "swing-v3.1-tqqq-sleeve") or pf.get("sleeve") not in (SLEEVE, "legacy-qqq"):
        raise ValueError("Legacy portfolio must be archived, not advanced under the current allocation")
    days = sorted(d for d in qqq if pf["last_day"] < d <= until)
    if not days:
        return pf
    if pf["equity"][0][2] is None:
        pf["equity"][0][2] = _f((qqq.get(pf["start"]) or {}).get("close"))
    bars = {t: g.set_index("date")[["open", "low", "close"]].sort_index() for t, g in frame.groupby("ticker")}
    prev = pf["last_day"]
    for day in days:
        q = qqq.get(day) or {}
        sv = None
        if pf.get("sleeve") == SLEEVE or (pf.get("sleeve") == "legacy-qqq" and day >= pf.get("allocation_effective_date", EFFECTIVE_DATE)):
            sv = (fund or {}).get(day) or {}
            if _f(sv.get("open")) is None or _f(sv.get("close")) is None:
                pf["waiting"] = day
                break
        if _f(q.get("open")) is None or _f(q.get("close")) is None:
            pf["waiting"] = day      # resume here next run rather than skip a session
            break
        pf.pop("waiting", None)
        if pf.get("sleeve") == "legacy-qqq" and sv is not None:
            # Exchange the saved QQQ units for synthetic sleeve NAV at the SAME
            # next-session open. Preserve dollars; never rewrite a past mark.
            value = pf["qqq_sh"] * float(q["open"])
            prior_units = pf["qqq_sh"]
            pf["qqq_sh"] = value / float(sv["open"])
            pf["sleeve"] = SLEEVE
            pf["sleeve_conversion"] = {"day": day, "from": "QQQ", "to": SLEEVE,
                                       "old_units": prior_units, "value_at_open": value}
        step(pf, day, prev, q, sessions.get(prev), bars, sv)
        prev = day
    return pf


def stats(pf: dict) -> dict[str, Any]:
    eq = [e for e in pf.get("equity", []) if e[1] is not None]
    out: dict[str, Any] = {"days": len(eq) - 1, "names": len(pf.get("positions", {})),
                           "closed": len(pf.get("closed", [])), "skipped": len(pf.get("skipped", []))}
    if not eq:
        return out
    out["ret"] = eq[-1][1] - 1
    q0 = eq[0][2]
    if q0 and eq[-1][2]:
        out["qqq"] = eq[-1][2] / q0 - 1
    peak, dd = 0.0, 0.0
    for _, v, _ in eq:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    out["dd"] = dd
    done = pf.get("closed", [])
    if done:
        out["win"] = sum(c["pnl"] > 0 for c in done) / len(done)
    total = eq[-1][1]
    held = sum(p["shares"] * p["last"] for p in pf.get("positions", {}).values())
    out["stock_share"] = held / total if total else None
    return out
