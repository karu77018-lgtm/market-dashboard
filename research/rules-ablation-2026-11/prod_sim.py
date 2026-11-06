"""Stocks-only portfolio mirroring MC57 track_portfolio.step (v6): 6 names, first buy 1/6 of equity at the
next open, stocks capped at 80%, -8% stop (gap -> open), same-amount adds at close +10/+20% (next open, name
cap 40%), exit next open on close < 21-EMA of lows or close 15% under the highest close.  Idle money = cash."""
import numpy as np, pandas as pd
W = {k: pd.read_pickle(f'w_{k}.pkl') for k in ('open', 'low', 'close')}
O, Lw, Cw = W['open'], W['low'], W['close']
EL = Lw.ewm(span=21, adjust=False).mean()
dates = Cw.loc['2015-01-01':].index
On, Ln, Cn, ELn = (x.to_numpy(float) for x in (O, Lw, Cw, EL))
col = {t: i for i, t in enumerate(Cw.columns)}
row = {d: i for i, d in enumerate(Cw.index)}

def simulate(sig, names=6, w0=1/6, cap_stock=0.80, cap_name=0.40, stop=0.08, trail=0.15, end=None):
    """sig: DataFrame of 本命 (date, ticker, rs189) published after that date's close."""
    by = {d: g.sort_values('rs189', ascending=False).ticker.tolist() for d, g in sig.groupby('date')}
    cash = 1.0; pos = {}; curve = []; trades = []
    ds = dates if end is None else dates[dates <= end]
    prev = None
    for d in ds:
        k = row[d]
        def px_open(j): return On[k, j]
        # 1. open: pending exits, gap stops
        for t in list(pos):
            p = pos[t]; j = p['j']; o = On[k, j]
            if np.isnan(o): continue
            if p['exit'] or o <= p['stop']:
                cash += p['sh'] * o; trades.append((t, p['d0'], d, p['sh'] * o / p['inv'] - 1)); del pos[t]
        held = {t: (On[k, p['j']] if not np.isnan(On[k, p['j']]) else p['last']) for t, p in pos.items()}
        eq_open = cash + sum(p['sh'] * held[t] for t, p in pos.items())
        def room():
            return max(0.0, cap_stock * eq_open - sum(p['sh'] * held.get(t, p['last']) for t, p in pos.items()))
        # 2. adds
        for t, p in pos.items():
            o = held[t]
            for _ in range(p['padd']):
                r = min(cap_name * eq_open - p['sh'] * o, room())
                amt = min(p['unit'], r, cash)
                if amt > 0:
                    p['sh'] += amt / o; p['inv'] += amt; cash -= amt
            p['padd'] = 0
        # 3. entries from prev close's list
        if prev is not None and prev in by:
            for t in by[prev]:
                if t in pos or len(pos) >= names: continue
                j = col[t]; o = On[k, j]
                if np.isnan(o): continue
                unit = eq_open * w0
                amt = min(unit, room(), cash)
                if amt <= 1e-9: continue
                cash -= amt
                pos[t] = dict(j=j, d0=d, entry=o, stop=o * (1 - stop), sh=amt / o, inv=amt,
                              unit=amt if amt < unit else unit, trig=set(), padd=0, exit=False,
                              last=o, hi=o)
                held[t] = o
        # 5. intraday stop, close checks
        for t in list(pos):
            p = pos[t]; j = p['j']; lo, c = Ln[k, j], Cn[k, j]
            if np.isnan(c): continue
            if lo <= p['stop']:
                cash += p['sh'] * p['stop']; trades.append((t, p['d0'], d, p['sh'] * p['stop'] / p['inv'] - 1)); del pos[t]; continue
            p['last'] = c
            if c < ELn[k, j]:
                p['exit'] = True; continue
            p['hi'] = max(p['hi'], c)
            if c < p['hi'] * (1 - trail):
                p['exit'] = True; continue
            for n, lvl in enumerate((0.10, 0.20)):
                if n not in p['trig'] and round(c / p['entry'] - 1, 9) >= lvl:
                    p['trig'].add(n); p['padd'] += 1
        curve.append(cash + sum(p['sh'] * p['last'] for p in pos.values()))
        prev = d
    s = pd.Series(curve, index=ds)
    return s, pd.DataFrame(trades, columns=['ticker', 'entry', 'exit', 'ret'])

def stats(s, tr=None):
    yrs = len(s) / 252
    out = dict(CAGR=(s.iloc[-1] ** (1 / yrs) - 1) * 100, DD=(s / s.cummax() - 1).min() * 100)
    a, b = s[:'2020-12-31'], s['2021-01-01':]
    out['15-20'] = ((a.iloc[-1] / a.iloc[0]) ** (252 / len(a)) - 1) * 100
    out['21-26'] = ((b.iloc[-1] / s[:'2020-12-31'].iloc[-1]) ** (252 / len(b)) - 1) * 100
    y = s.groupby(s.index.year).last() / s.groupby(s.index.year).last().shift(1).fillna(1) - 1
    out['2022'] = y.get(2022, np.nan) * 100
    out['負年'] = int((y < 0).sum())
    if tr is not None:
        r = tr.ret; out['件数'] = len(tr); out['PF'] = r[r > 0].sum() / -r[r < 0].sum()
    return out
