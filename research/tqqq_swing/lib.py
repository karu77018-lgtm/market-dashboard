"""TQQQ EMA21/AVWAP deviation swing research: data loading and indicators.

All indicators are computed on confirmed daily bars. A value at row t only uses
information available at the close of t (pivots are only used after their
right-side confirmation bars have closed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

PIVOT_LR = 5          # left/right bars for swing pivots
AVWAP_MAX_AGE = 20    # AVWAP valid only within this many bars of its anchor
DEVZ_WIN = 252


def load(ticker: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{ticker}_tv_1d.parquet")


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.Close.shift(1)
    tr = pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()  # Wilder RMA, same as ta.atr


def base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EMA21"] = ema(df.Close, 21)
    out["SMA50"] = df.Close.rolling(50).mean()
    out["SMA200"] = df.Close.rolling(200).mean()
    out["ATR14"] = atr(df, 14)
    out["Dev"] = (df.Close - out.EMA21) / out.ATR14
    out["DevPct"] = df.Close / out.EMA21 - 1
    prev = out.Dev.shift(1).rolling(DEVZ_WIN, min_periods=DEVZ_WIN)
    out["DevZ"] = (out.Dev - prev.mean()) / prev.std()
    return out


def _pivots(values: np.ndarray, lr: int, kind: str) -> np.ndarray:
    """Boolean mask: bar i is a pivot low/high with lr bars each side.

    Ties: the left side must be strictly worse, the right side may be equal, so
    a flat double bottom produces one pivot (the first bar).
    """
    n = len(values)
    mask = np.zeros(n, dtype=bool)
    for i in range(lr, n - lr):
        v = values[i]
        left = values[i - lr:i]
        right = values[i + 1:i + 1 + lr]
        if kind == "low":
            mask[i] = (v < left).all() and (v <= right).all()
        else:
            mask[i] = (v > left).all() and (v >= right).all()
    return mask


def add_avwap(df: pd.DataFrame, lr: int = PIVOT_LR, max_age: int = AVWAP_MAX_AGE) -> pd.DataFrame:
    """Anchored VWAP from the most recent *confirmed* swing low / high.

    A pivot at bar p is known only at the close of bar p+lr. From then on the
    AVWAP anchored at p is available, while t - p <= max_age.
    Columns: AVWAP_L / AVWAP_H (NaN when no valid anchor), AgeL / AgeH (bars since anchor).
    """
    out = df.copy()
    tp = ((df.High + df.Low + df.Close) / 3).to_numpy()
    vol = df.Volume.to_numpy().astype(float)
    cpv = np.concatenate([[0.0], np.cumsum(tp * vol)])
    cv = np.concatenate([[0.0], np.cumsum(vol)])
    n = len(df)
    for kind, col, src in (("low", "L", df.Low), ("high", "H", df.High)):
        piv = _pivots(src.to_numpy(), lr, kind)
        anchor = np.full(n, -1)
        last = -1
        for t in range(n):
            p = t - lr
            if p >= 0 and piv[p]:
                last = p
            anchor[t] = last
        av = np.full(n, np.nan)
        age = np.full(n, np.nan)
        for t in range(n):
            p = anchor[t]
            if p < 0 or t - p > max_age:
                continue
            av[t] = (cpv[t + 1] - cpv[p]) / (cv[t + 1] - cv[p])
            age[t] = t - p
        out[f"AVWAP_{col}"] = av
        out[f"Age{col}"] = age
        out[f"Pivot{col}"] = piv  # raw pivot flag at pivot bar (NOT usable at that bar; for plotting only)
    return out


def build() -> pd.DataFrame:
    """TQQQ bars with TQQQ indicators, QQQ indicators (prefixed Q_) and regimes."""
    t = add_avwap(base_indicators(load("TQQQ")))
    q = add_avwap(base_indicators(load("QQQ")))
    q = q.add_prefix("Q_")
    df = t.join(q, how="inner")
    r1 = (df.Q_Close > df.Q_SMA200) & (df.Q_EMA21 > df.Q_SMA50)
    r2 = (df.Q_Close > df.Q_SMA200) & ~r1
    df["Regime"] = np.where(r1, "R1", np.where(r2, "R2", "R3"))
    df.loc[df.Q_SMA200.isna(), "Regime"] = None
    return df


def forward_stats(df: pd.DataFrame, horizons=(5, 10, 20)) -> pd.DataFrame:
    """For signal at close t, entry at Open[t+1]; horizon h exits at Close[t+h].

    MAE/MFE use Low/High over bars t+1..t+h relative to the entry price.
    """
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    n = len(df)
    res = {}
    for H in horizons:
        ret = np.full(n, np.nan)
        mae = np.full(n, np.nan)
        mfe = np.full(n, np.nan)
        for t in range(n - H):
            e = o[t + 1]
            ret[t] = c[t + H] / e - 1
            mae[t] = l[t + 1:t + H + 1].min() / e - 1
            mfe[t] = h[t + 1:t + H + 1].max() / e - 1
        res[f"R{H}"] = ret
        res[f"MAE{H}"] = mae
        res[f"MFE{H}"] = mfe
    return pd.DataFrame(res, index=df.index)
