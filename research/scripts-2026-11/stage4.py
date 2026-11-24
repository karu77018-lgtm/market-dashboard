"""Stage 4 Trendline (Vishwajeeth_JK, v2.0) ported bar by bar. Lookback-high mode (252), decline 40%, retest 5%, high/low.
Returns per-bar state (0 none, 1 stage 4, 2 broken) and the break bars."""
import numpy as np


def fit(o, c, h, p0, P, i):
    """tightest line from the peak (p0, P) over bars p0+1..i that no body rises above."""
    idx = np.arange(p0 + 1, i + 1)
    if len(idx) == 0:
        return np.nan, np.nan
    dist = idx - p0
    sbody = np.max((np.maximum(o[idx], c[idx]) - P) / dist)
    hs = (h[idx] - P) / dist
    ok = hs >= sbody
    return (hs[ok].min() if ok.any() else np.nan), sbody


def run(o, h, l, c, drop=40.0, lookback=252, retest=5.0):
    n = len(c)
    state = 0; peak = peakbar = s4low = s4lowbar = wavelow = rally = refstart = np.nan
    slope = body = np.nan
    st = np.zeros(n, np.int8); brk = np.zeros(n, bool); fail = np.zeros(n, bool); peaks = np.full(n, np.nan); lows = np.full(n, np.nan); tla = np.full(n, np.nan)
    valid = ~np.isnan(c)
    for i in range(n):
        if not valid[i]:
            st[i] = state; continue
        lenraw = i + 1 if np.isnan(refstart) else i - int(refstart)
        win = max(1, min(lookback, lenraw))
        a = max(0, i - win + 1)
        seg = h[a:i + 1]
        k = int(np.nanargmax(seg)); ph = seg[k]; cand = a + k
        dd = (ph - l[i]) / ph * 100
        fresh = np.isnan(s4lowbar) or cand > s4lowbar
        trig = dd >= drop and fresh
        handled = False
        if state == 2:
            rally = max(rally, h[i])
            isre = l[i] <= wavelow * (1 + retest / 100)
            isnew = (rally - l[i]) / rally * 100 >= drop
            if h[i] > peak:
                state = 0
            elif isre or isnew:
                handled = True; state = 1; fail[i] = True
                wavelow = min(wavelow, l[i]) if isre else l[i]
                if l[i] < s4low:
                    s4low, s4lowbar, refstart = l[i], i, i
                slope, body = fit(o, c, h, int(peakbar), peak, i)
        if state == 0 and trig:
            state = 1; peak, peakbar = ph, cand; s4low = s4lowbar = np.nan
            s4low, s4lowbar, wavelow, refstart = l[i], i, l[i], i
            slope, body = fit(o, c, h, int(peakbar), peak, i)
        elif state == 1 and not handled:
            dist = i - peakbar
            tl = peak + slope * dist if not np.isnan(slope) else np.nan
            if not np.isnan(tl) and c[i] > tl:
                brk[i] = True; state = 2; rally = h[i]
            else:
                if l[i] < wavelow: wavelow = l[i]
                if l[i] < s4low: s4low, s4lowbar, refstart = l[i], i, i
                bs = (max(o[i], c[i]) - peak) / dist; hs = (h[i] - peak) / dist
                if np.isnan(slope):
                    slope, body = hs, bs
                elif bs > slope:
                    slope, body = fit(o, c, h, int(peakbar), peak, i)
                else:
                    body = max(body, bs)
                    if hs >= body and hs < slope: slope = hs
        tla[i] = (peak + slope * (i - peakbar)) if state == 1 and not np.isnan(slope) else np.nan
        st[i] = state; peaks[i] = peak if state else np.nan; lows[i] = s4low if state else np.nan
    run.tl = tla
    return st, brk, fail, peaks, lows
