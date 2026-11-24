"""Ports of popular public scripts (daily, wide panels or single series).
Squeeze Momentum [LazyBear] PUB;175, CM_Williams_Vix_Fix PUB;239, Up/Dn Volume Ratio (CarusoInsights),
Chandelier Exit V2 (KivancOzbilgic), UT Bot (Yo_adriiiiaan), Supertrend (TradingView built-in)."""
import numpy as np, pandas as pd


def _tr(H, L, C):
    pc = C.shift(1)
    return np.maximum(np.maximum(H - L, (H - pc).abs()), (L - pc).abs()).where(pc.notna(), H - L)


def atr(H, L, C, n):
    return _tr(H, L, C).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def linreg_last(x, n):
    """Pine linreg(src, n, 0): fitted value at the newest bar."""
    t = np.arange(n, dtype=float); tm = t.mean(); den = ((t - tm) ** 2).sum()
    w = (t - tm) / den
    slope = x.rolling(n).apply(lambda v: np.dot(w, v), raw=True)
    mean = x.rolling(n).mean()
    return mean + slope * (n - 1 - tm)


def squeeze(H, L, C, n=20, mult=2.0, multKC=1.5):
    basis = C.rolling(n).mean(); dev = multKC * C.rolling(n).std(ddof=0)   # script uses multKC for the BB (as published)
    ubb, lbb = basis + dev, basis - dev
    rng = _tr(H, L, C).rolling(n).mean()
    ukc, lkc = basis + rng * multKC, basis - rng * multKC
    on = (lbb > lkc) & (ubb < ukc)
    off = (lbb < lkc) & (ubb > ukc)
    mid = ((H.rolling(n).max() + L.rolling(n).min()) / 2 + C.rolling(n).mean()) / 2
    val = linreg_last(C - mid, n)
    return on, off, val


def vixfix(H, L, C, pd_=22, bbl=20, mult=2.0, lb=50, ph=0.85):
    hc = C.rolling(pd_).max()
    wvf = (hc - L) / hc * 100
    upper = wvf.rolling(bbl).mean() + mult * wvf.rolling(bbl).std(ddof=0)
    rh = wvf.rolling(lb).max() * ph
    return wvf, (wvf >= upper) | (wvf >= rh)


def updn(C, V, n=50):
    up = V.where(C > C.shift(1), 0.0); dn = V.where(C < C.shift(1), 0.0)
    return up.rolling(n).mean() / dn.rolling(n).mean()


def chandelier_long(H, L, C, n=22, mult=3.0):
    return H.rolling(n).max() - mult * atr(H, L, C, n)


def utbot(c, a, key=3.0):
    """single series: c close, a ATR(10). returns trailing stop array."""
    n = len(c); ts = np.zeros(n); nloss = key * a
    for i in range(n):
        p = ts[i - 1] if i else 0.0
        cp = c[i - 1] if i else np.nan
        if np.isnan(nloss[i]) or np.isnan(c[i]):
            ts[i] = p if i else 0.0; continue
        if c[i] > p and cp > p: ts[i] = max(p, c[i] - nloss[i])
        elif c[i] < p and cp < p: ts[i] = min(p, c[i] + nloss[i])
        elif c[i] > p: ts[i] = c[i] - nloss[i]
        else: ts[i] = c[i] + nloss[i]
    return ts


def supertrend(h, l, c, a, factor=3.0):
    """single series, TradingView ta.supertrend; returns (line, direction) with direction -1 = up trend."""
    n = len(c); src = (h + l) / 2
    up = np.full(n, np.nan); dn = np.full(n, np.nan); d = np.ones(n); st = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(a[i]):
            continue
        u = src[i] + factor * a[i]; lo = src[i] - factor * a[i]
        pl = dn[i - 1] if i and not np.isnan(dn[i - 1]) else 0.0
        pu = up[i - 1] if i and not np.isnan(up[i - 1]) else 0.0
        lo = lo if (lo > pl or c[i - 1] < pl) else pl
        u = u if (u < pu or c[i - 1] > pu) else pu
        dn[i], up[i] = lo, u
        if i == 0 or np.isnan(a[i - 1]):
            d[i] = 1
        elif st[i - 1] == pu:
            d[i] = -1 if c[i] > u else 1
        else:
            d[i] = 1 if c[i] < lo else -1
        st[i] = lo if d[i] == -1 else u
    return st, d
