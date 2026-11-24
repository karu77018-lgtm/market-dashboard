"""GreenStar HUD (GS2) metrics ported from the Pine source (FlyMe2, v1.0), daily bars, wide panels (date x ticker)."""
import numpy as np, pandas as pd


def rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def metrics(O, H, L, C, V, spy):
    pc = C.shift(1)
    tr = pd.concat([(H - L), (H - pc).abs(), (L - pc).abs()]).groupby(level=0).max().reindex(C.index)
    atr = rma(tr, 14)
    atr_pct = atr / C * 100
    sma50, sma150, sma200 = (C.rolling(n).mean() for n in (50, 150, 200))
    ext = ((C - sma50) / sma50 * 100) / atr_pct                      # xFromMA (ATR multiples from the 50-day SMA)
    mx = ext.rolling(120, min_periods=120).max()
    pmax = (ext / mx * 100).where(mx > 0)                             # %MaxATRx
    # VCPT
    adr = ((H - L) / L * 100).rolling(20).mean().replace(0, 1e-4)
    hc, lc = C.rolling(5).max(), C.rolling(5).min()
    hp, lp = H.rolling(5).max(), L.rolling(5).min()
    comb = (((hc - lc) / lc * 100) / adr + ((hp - lp) / lp * 100) / adr) / 2
    hi, lo = comb.rolling(50).max(), comb.rolling(50).min()
    rng = hi - lo
    vcpt = ((comb - lo) / rng * 100).where(rng != 0, 0.0)
    # STS: share of the last 25 bars whose stock/SPY ratio is below today's
    ratio = C.div(spy, axis=0)
    cnt = sum((ratio > ratio.shift(i)).astype(float) for i in range(1, 26))
    sts = (cnt / 25 * 100).where(ratio.shift(25).notna())
    # MM (Minervini 8 conditions as written in the script)
    hi260, lo260 = H.rolling(260).max(), L.rolling(260).min()
    rs = (0.4 * C / C.shift(63) + 0.2 * C / (C.shift(126) * 2) + 0.2 * C / (C.shift(189) * 3) + 0.2 * C / (C.shift(252) * 4)) * 100
    conds = [(C > sma150) & (C > sma200), sma150 > sma200, sma200 > sma200.shift(22), (sma50 > sma150) & (sma50 > sma200),
             C > sma50, (C / lo260 - 1) * 100 >= 25, (1 - C / hi260) * 100 <= 25, rs > 70]
    mm = sum(c.astype(int) for c in conds).where(C.shift(260).notna())
    buzz = 100 * (V / V.rolling(50).mean() - 1)
    return dict(atr_pct=atr_pct, ext=ext, pmax=pmax, vcpt=vcpt, sts=sts, mm=mm, buzz=buzz)
