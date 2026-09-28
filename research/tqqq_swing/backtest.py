"""Step 3: strategy backtests for the TQQQ deviation swing candidates.

Execution model (all strategies):
  * signals on confirmed closes, fills at the next open, 0.05% slippage per side
  * one position at a time, cash earns nothing
  * intraday stop: if Low <= stop, fill at min(Open, stop)
  * trades TQQQ; "Q" variants take entry/exit signals from QQQ bars
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

import lib

SLIP = 0.0005
FULL = ("2011-02-10", None)
IS = ("2011-02-10", "2018-12-31")
OOS = ("2019-01-01", None)
WINDOWS = {"FULL": FULL, "IS": IS, "OOS": OOS}

K1 = (0.5, 1.0, 1.5)
K2 = (None, 1.5, 2.0, 2.5, 3.0)
K3 = (None, 3.0, 4.0)
STOPS = ("1.5ATR", "2.0ATR", "SigLow")
NS = (10, 20)


@dataclass(frozen=True)
class Exit:
    k2: float | None   # sell half when Dev >= k2 (close) -> next open
    k3: float | None   # sell all when Dev >= k3
    stop: str          # "1.5ATR" | "2.0ATR" | "SigLow"
    n: int             # at N bars after entry, exit if close < entry price

    def label(self) -> str:
        f = lambda v: "-" if v is None else f"{v:g}"
        return f"k2={f(self.k2)} k3={f(self.k3)} stop={self.stop} N={self.n}"


def exit_grid() -> list[Exit]:
    out = []
    for k2, k3, st, n in itertools.product(K2, K3, STOPS, NS):
        if k2 is not None and k3 is not None and k3 <= k2:
            continue
        out.append(Exit(k2, k3, st, n))
    return out


# ---------------------------------------------------------------- signals
def _recent(mask: pd.Series, lo: int, hi: int) -> pd.Series:
    """True if mask held on any bar in [t-hi, t-lo]."""
    return mask.shift(lo).rolling(hi - lo + 1, min_periods=1).max().fillna(0).astype(bool)


def entry_signals(df: pd.DataFrame) -> dict[tuple, pd.Series]:
    """Keys: (family, src, k1). src 'T' = TQQQ bars, 'Q' = QQQ bars."""
    sig = {}
    r1 = df.Regime == "R1"
    r12 = df.Regime.isin(["R1", "R2"])
    anyr = df.Regime.notna()
    for src, p in (("T", ""), ("Q", "Q_")):
        c, h, lo = df[p + "Close"], df[p + "High"], df[p + "Low"]
        dev, devz, av, atr = df[p + "Dev"], df[p + "DevZ"], df[p + "AVWAP_L"], df[p + "ATR14"]
        reclaim = c > h.shift(1)
        for k1 in K1:
            sig[("A", src, k1)] = reclaim & _recent(dev <= -k1, 1, 5) & r1
        touch = av.notna() & (lo <= av + atr) & (c >= av - atr)
        sig[("B", src, None)] = reclaim & _recent(touch, 0, 2) & r12
        sig[("C", src, None)] = reclaim & _recent(devz <= -2.5, 1, 5) & anyr
    return {k: v.fillna(False).to_numpy() for k, v in sig.items()}


def sig_label(key: tuple) -> str:
    fam, src, k1 = key
    s = {"A": "A押し目", "B": "B AVWAP", "C": "C投げ売り"}[fam]
    s += "[QQQ]" if src == "Q" else ""
    return s + (f" k1={k1:g}" if k1 is not None else "")


# ---------------------------------------------------------------- engine
class Data:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.idx = df.index
        self.o, self.h, self.l, self.c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
        self.atr = df.ATR14.to_numpy()
        self.regime = df.Regime.to_numpy()
        self.src = {
            "T": (df.Close.to_numpy(), df.EMA21.to_numpy(), df.Dev.to_numpy()),
            "Q": (df.Q_Close.to_numpy(), df.Q_EMA21.to_numpy(), df.Q_Dev.to_numpy()),
        }

    def span(self, win):
        s, e = win
        i0 = self.idx.searchsorted(pd.Timestamp(s))
        i1 = len(self.idx) if e is None else self.idx.searchsorted(pd.Timestamp(e), side="right")
        return i0, i1


def run(d: Data, entry: np.ndarray, src: str, ex: Exit, sizing: str, win) -> tuple[np.ndarray, list[dict], np.ndarray]:
    i0, i1 = d.span(win)
    o, h, l, c, atr = d.o, d.h, d.l, d.c, d.atr
    cx, emax, devx = d.src[src]
    m = {"1.5ATR": 1.5, "2.0ATR": 2.0}.get(ex.stop)
    cash, sh = 1.0, 0.0
    eq = np.empty(i1 - i0)
    held = np.zeros(i1 - i0, dtype=bool)
    trades = []
    pend_entry = None       # (signal index)
    pend_exit = None        # "all" | "half"
    tr = None
    for i in range(i0, i1):
        # --- open: pending orders
        if pend_exit and sh > 0:
            q = sh if pend_exit == "all" else sh / 2
            px = o[i] * (1 - SLIP)
            cash += q * px
            sh -= q
            tr["pnl"] += q * (px - tr["px"])
            if sh <= 1e-12:
                sh = 0.0
                tr.update(exit=i, why=tr.get("why_pending", pend_exit))
                trades.append(tr)
                tr = None
        pend_exit = None
        if pend_entry is not None and sh == 0:
            s = pend_entry
            px = o[i] * (1 + SLIP)
            stop = l[s] if m is None else px - m * atr[s]
            rps = px - stop
            if rps > 0:
                equity = cash
                q = equity / px if sizing == "full" else min(0.01 * equity / rps, equity / px)
                cash -= q * px
                sh = q
                tr = dict(sig=s, entry=i, px=px, stop=stop, q0=q, risk=q * rps, pnl=0.0,
                          alloc=q * px / equity, regime=d.regime[s], armed=False, partial=False)
        pend_entry = None
        # --- intraday stop
        if sh > 0 and l[i] <= tr["stop"]:
            px = min(o[i], tr["stop"]) * (1 - SLIP)
            cash += sh * px
            tr["pnl"] += sh * (px - tr["px"])
            tr.update(exit=i, why="stop")
            trades.append(tr)
            tr, sh = None, 0.0
        # --- close
        eq[i - i0] = cash + sh * c[i]
        held[i - i0] = sh > 0
        if sh > 0:
            if not tr["armed"] and cx[i] >= emax[i]:
                tr["armed"] = True
            why = None
            if tr["armed"] and cx[i] < emax[i]:
                why = "ema21"
            elif ex.k3 is not None and devx[i] >= ex.k3:
                why = "k3"
            elif i - tr["entry"] == ex.n and c[i] < tr["px"]:
                why = "time"
            if why:
                pend_exit, tr["why_pending"] = "all", why
            elif ex.k2 is not None and not tr["partial"] and devx[i] >= ex.k2:
                pend_exit, tr["partial"] = "half", True
        elif entry[i] and i + 1 < i1:
            pend_entry = i
    if tr is not None:  # mark open trade at last close
        tr["pnl"] += sh * (c[i1 - 1] - tr["px"])
        tr.update(exit=i1 - 1, why="open")
        trades.append(tr)
    return eq, trades, held


def run_target(d: Data, target: np.ndarray, win) -> tuple[np.ndarray, list[dict], np.ndarray]:
    """Full-in benchmark: hold TQQQ when target[t] (decided at close t, traded next open)."""
    i0, i1 = d.span(win)
    o, c = d.o, d.c
    cash, sh = 1.0, 0.0
    eq = np.empty(i1 - i0)
    held = np.zeros(i1 - i0, dtype=bool)
    trades, tr = [], None
    want = False
    for i in range(i0, i1):
        if want and sh == 0:
            px = o[i] * (1 + SLIP)
            sh, cash = cash / px, 0.0
            tr = dict(sig=i - 1, entry=i, px=px, q0=sh, risk=np.nan, pnl=0.0, alloc=1.0, regime=d.regime[max(i - 1, 0)])
        elif not want and sh > 0:
            px = o[i] * (1 - SLIP)
            cash += sh * px
            tr["pnl"] = sh * (px - tr["px"])
            tr.update(exit=i, why="signal")
            trades.append(tr)
            tr, sh = None, 0.0
        eq[i - i0] = cash + sh * c[i]
        held[i - i0] = sh > 0
        want = bool(target[i])
    if tr is not None:
        tr["pnl"] = sh * (c[i1 - 1] - tr["px"])
        tr.update(exit=i1 - 1, why="open")
        trades.append(tr)
    return eq, trades, held


def benchmarks(d: Data) -> dict[str, np.ndarray]:
    df = d.df
    n = len(df)
    return {
        "TQQQ B&H": np.ones(n, dtype=bool),
        "TQQQ when QQQ>SMA200": (df.Q_Close > df.Q_SMA200).to_numpy(),
        "対照: R1中保有": (df.Regime == "R1").to_numpy(),
        "対照: R1中 & 終値>EMA21": ((df.Regime == "R1") & (df.Close > df.EMA21)).to_numpy(),
    }


def qqq_bh(d: Data, win) -> np.ndarray:
    i0, i1 = d.span(win)
    qo, qc = d.df.Q_Open.to_numpy(), d.df.Q_Close.to_numpy()
    return qc[i0:i1] / (qo[i0] * (1 + SLIP))


# ---------------------------------------------------------------- metrics
def metrics(eq: np.ndarray, trades: list[dict], held: np.ndarray, idx: pd.DatetimeIndex) -> dict:
    years = (idx[-1] - idx[0]).days / 365.25
    cagr = eq[-1] ** (1 / years) - 1 if eq[-1] > 0 else -1.0
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    mdd = (eq / peak - 1).min()
    pnl = np.array([t["pnl"] for t in trades]) if trades else np.array([])
    gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    r = np.array([t["pnl"] / t["risk"] for t in trades if t.get("risk") and t["risk"] > 0])
    hold = np.array([t["exit"] - t["entry"] + 1 for t in trades]) if trades else np.array([])
    return dict(
        CAGR=cagr, MaxDD=mdd, MAR=cagr / abs(mdd) if mdd < 0 else np.nan,
        Trades=len(trades), Win=(pnl > 0).mean() if len(pnl) else np.nan,
        PF=gp / gl if gl > 0 else np.nan, AvgHold=hold.mean() if len(hold) else np.nan,
        Exposure=held.mean(), ExpR=r.mean() if len(r) else np.nan,
        AvgAlloc=np.mean([t["alloc"] for t in trades]) if trades else np.nan,
        Final=eq[-1],
    )
