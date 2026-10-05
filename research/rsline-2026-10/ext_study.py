import numpy as np, pandas as pd
import fullrule_sim as F
C = F.C
E21 = C.ewm(span=21, adjust=False).mean().to_numpy(float)
E9 = C.ewm(span=9, adjust=False).mean().to_numpy(float)
Cn, On, Ln, En, dates, col, q, reg, by_day, health = F.Cn, F.On, F.Ln, F.En, F.dates, F.col, F.q, F.reg, F.by_day, F.health
def run(max21=None, max9=None, band=None, start='2015-01-02', end='2026-08-31', cap=0.40, qmode='switch'):
    cash, qsh, pos, eq, trades = 1.0, 0.0, {}, [], []
    idx = [i for i, d in enumerate(dates) if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    for i in idx:
        d = dates[i]; qc = q.iloc[i]
        def val():
            return cash + qsh * qc + sum(p['sh'] * (Cn[i, j] if not np.isnan(Cn[i, j]) else p['last']) for j, p in pos.items())
        for j in list(pos):
            p = pos[j]; o, l, c, e = On[i, j], Ln[i, j], Cn[i, j], En[i, j]
            if np.isnan(c): continue
            px = o if o <= p['stop'] else p['stop'] if l <= p['stop'] else c if c < e else None
            if px is not None:
                trades.append(dict(d=p['d'], x21=p['x21'], x9=p['x9'], ret=px / p['entry'] - 1,
                                   pnl=(p['sh'] * px - p['inv']) / p['eq0'], adds=len(p['trig'])))
                cash += p['sh'] * px; del pos[j]; continue
            p['last'] = c
            for k, lv in enumerate((0.10, 0.20)):
                if k not in p['trig'] and round(c / p['entry'] - 1, 9) >= lv:
                    p['trig'].append(k)
                    equity = val(); room = cap * equity - p['sh'] * c
                    amt = min(p['unit'], max(0.0, room), cash + qsh * qc)
                    if amt > 0:
                        take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
                        p['sh'] += amt / c; p['inv'] += amt
        if reg.iloc[i] and d in by_day:
            for t in by_day[d]:
                j = col[t]
                if j in pos: continue
                if len(pos) >= 6: break
                c = Cn[i, j]; x21 = c / E21[i, j] - 1; x9 = c / E9[i, j] - 1
                if max21 is not None and x21 > max21: continue
                if max9 is not None and x9 > max9: continue
                if band is not None and band[0] < x9 <= band[1]: continue
                equity = val(); unit = equity / 6; amt = min(unit, cash + qsh * qc)
                if amt <= 0: break
                take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
                pos[j] = dict(d=d, entry=c, stop=c * 0.92, sh=amt / c, inv=amt, unit=unit, trig=[], last=c, eq0=equity, x21=x21, x9=x9)
        h = health(i); qp = 0.0 if qmode == 'none' else (0.5 if (h is None or h >= 0 or not reg.iloc[i]) else 1.0)
        idle = cash + qsh * qc; qsh = idle * qp / qc; cash = idle - qsh * qc
        eq.append(val())
    e = pd.Series(eq, index=dates[idx]); yrs = (e.index[-1] - e.index[0]).days / 365.25
    return e.iloc[-1] ** (1 / yrs) - 1, (e / e.cummax() - 1).min(), pd.DataFrame(trades), e
if __name__ == '__main__':
    cg, dd, T, e = run()
    print(f'base CAGR {cg:.1%} DD {dd:.1%} n={len(T)}')
    print(T[['x21','x9']].describe(percentiles=[.1,.25,.5,.75,.9]).round(3))
    def pf(s): return s[s>0].sum() / -s[s<0].sum()
    for name, b in (('x21', [-1, .03, .06, .09, .12, .15, .20, 9]), ('x9', [-1, .01, .03, .05, .07, .10, 9])):
        T['b'] = pd.cut(T[name], b)
        g = T.groupby('b', observed=True)
        print(pd.DataFrame({'n': g.size(), 'win': g.ret.apply(lambda s: (s>0).mean()), 'avg_ret': g.ret.mean(),
              'med': g.ret.median(), 'PF': g.ret.apply(pf), 'pnl_sum': g.pnl.sum(), 'stop8': g.ret.apply(lambda s: (s<=-0.079).mean())}).round(3))
        T['era'] = np.where(T.d < '2021-01-01', '15-20', '21-26')
        print(T.groupby(['era','b'], observed=True).ret.agg(['size','mean', pf]).round(3))
    for m21 in (None, .20, .15, .12, .10, .08):
        r = run(max21=m21); print(f'max21={m21}: CAGR {r[0]:.1%} DD {r[1]:.1%} n={len(r[2])}', flush=True)
    for m9 in (.10, .07, .05, .03):
        r = run(max9=m9); print(f'max9={m9}: CAGR {r[0]:.1%} DD {r[1]:.1%} n={len(r[2])}', flush=True)
