"""6-slot portfolio from a signal list (entries at signal close, rule exits), idle money 50% QQQ."""
import sys, pandas as pd, numpy as np
from study import load, STOP, ADDS
sig = pd.read_csv(sys.argv[1], parse_dates=['date', 'exit_date'])
sig = sig[(sig.date >= '2015-01-01') & sig.regime].copy()
QPCT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
qqq = load('QQQ').set_index('date').close
cal = qqq.index[qqq.index >= '2015-01-02']
bars = {t: load(t).set_index('date') for t in sig.ticker.unique()}
by_day = {d: g.sort_values('r63', ascending=False) for d, g in sig.groupby('date')}
cash, qsh, pos, eq = 1.0, 0.0, {}, []
skipped = 0
for d in cal:
    qc = qqq.loc[d]
    # mark + manage open positions at today's bar (entries happen at close, so manage from next day)
    closes = {}
    for t in list(pos):
        b = bars[t]
        if d not in b.index: continue
        p = pos[t]; o, l, c = b.loc[d, ['open', 'low', 'close']]
        if p['ei'] == d: closes[t] = c; continue
        ema = p['ema'] = (2 / 22) * l + (1 - 2 / 22) * p['ema']
        if o <= p['stop']: px = o
        elif l <= p['stop']: px = p['stop']
        elif c < ema: px = c
        else: px = None
        if px is not None:
            cash += p['sh'] * px; del pos[t]; continue
        closes[t] = c
        for n, lv in enumerate(ADDS):
            if n not in p['trig'] and round(c / p['entry'] - 1, 9) >= lv:
                p['trig'].append(n)
                equity = cash + qsh * qc + sum(pp['sh'] * closes.get(tt, pp['last']) for tt, pp in pos.items())
                room = 0.4 * equity - p['sh'] * c
                amt = min(p['unit'], max(0.0, room))
                idle = cash + qsh * qc; amt = min(amt, idle)
                if amt > 0:
                    take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc; p['sh'] += amt / c
        p['last'] = c
    # new entries at today's close
    if d in by_day:
        for _, s in by_day[d].iterrows():
            if s.ticker in pos: continue
            if len(pos) >= 6: skipped += 1; continue
            b = bars[s.ticker]; c = b.loc[d, 'close']
            equity = cash + qsh * qc + sum(pp['sh'] * closes.get(tt, pp['last']) for tt, pp in pos.items())
            unit = equity / 6; idle = cash + qsh * qc; amt = min(unit, idle)
            if amt <= 0: skipped += 1; continue
            take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
            lows = b.loc[:d, 'low']; ema = lows.ewm(span=21, adjust=False).mean().iloc[-1]
            pos[s.ticker] = dict(ei=d, entry=c, stop=c * (1 - STOP), sh=amt / c, unit=unit, trig=[], ema=ema, last=c)
            closes[s.ticker] = c
    # idle money -> QPCT in QQQ
    idle = cash + qsh * qc; qsh = idle * QPCT / qc; cash = idle - qsh * qc
    equity = cash + qsh * qc + sum(pp['sh'] * closes.get(tt, pp['last']) for tt, pp in pos.items())
    eq.append((d, equity, sum(pp['sh'] * closes.get(tt, pp['last']) for tt, pp in pos.items()) / equity))
e = pd.DataFrame(eq, columns=['date', 'equity', 'stock']).set_index('date')
yrs = (e.index[-1] - e.index[0]).days / 365.25
cagr = e.equity.iloc[-1] ** (1 / yrs) - 1
dd = (e.equity / e.equity.cummax() - 1).min()
qn = qqq.loc[e.index] / qqq.loc[e.index[0]]
qcagr = qn.iloc[-1] ** (1 / yrs) - 1; qdd = (qn / qn.cummax() - 1).min()
blend = (1 - QPCT) + QPCT * qn  # cash/QQQ blend with no stocks
print(f'{sys.argv[1]} QPCT={QPCT}: CAGR {cagr:.1%} DD {dd:.1%} | avg stock share {e.stock.mean():.0%} | skipped {skipped}')
print(f'  QQQ: CAGR {qcagr:.1%} DD {qdd:.1%} | idle-only blend CAGR {(blend.iloc[-1]**(1/yrs)-1):.1%}')
yr = e.equity.resample('YE').last(); yr = yr / yr.shift(1).fillna(1.0) - 1
qy = qn.resample('YE').last(); qy = qy / qy.shift(1).fillna(1.0) - 1
print('  yearly:', ' '.join(f'{d.year}:{a:+.0%}/{b:+.0%}' for d, a, b in zip(yr.index, yr, qy)))
