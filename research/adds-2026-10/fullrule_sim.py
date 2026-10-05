import numpy as np, pandas as pd, sys
C = pd.read_pickle('w_close.pkl'); O = pd.read_pickle('w_open.pkl'); Lw = pd.read_pickle('w_low.pkl')
EL = Lw.ewm(span=21, adjust=False).mean()
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(C.index)
reg = (q > q.rolling(200).mean())
sig = pd.read_pickle('honmei.pkl')
dates = C.index; pos_of = {d: i for i, d in enumerate(dates)}; col = {t: j for j, t in enumerate(C.columns)}
Cn, On, Ln, En = C.to_numpy(float), O.to_numpy(float), Lw.to_numpy(float), EL.to_numpy(float)
# breakout health: mean 10-day forward return of signals dated in the 63 sessions ending 10 sessions ago
n = len(dates); sums = np.zeros(n); cnts = np.zeros(n)
for d, t in zip(sig.date, sig.ticker):
    i, j = pos_of[d], col[t]
    if i + 10 < n and Cn[i, j] > 0 and not np.isnan(Cn[i + 10, j]):
        sums[i] += Cn[i + 10, j] / Cn[i, j] - 1; cnts[i] += 1
cs, ck = np.cumsum(sums), np.cumsum(cnts)
def health(i):
    a, b = i - 10, i - 73
    if b < 0: return None
    k = ck[a] - ck[b]
    return None if k < 5 else (cs[a] - cs[b]) / k
by_day = {d: g.sort_values('rs189', ascending=False).ticker.tolist() for d, g in sig.groupby('date')}
def run(start='2015-01-02', end='2026-08-31', add_size=1.0, cap=0.40, be_after=None, qmode='switch'):
    cash, qsh, pos, eq, worst, ntr = 1.0, 0.0, {}, [], 0.0, 0
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
                worst = min(worst, (p['sh'] * px - p['inv']) / p['eq0'])
                cash += p['sh'] * px; del pos[j]; continue
            p['last'] = c
            for k, lv in enumerate((0.10, 0.20)):
                if k not in p['trig'] and round(c / p['entry'] - 1, 9) >= lv:
                    p['trig'].append(k)
                    if add_size > 0:
                        equity = val(); room = cap * equity - p['sh'] * c
                        amt = min(p['unit'] * add_size, max(0.0, room), cash + qsh * qc)
                        if amt > 0:
                            take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
                            p['sh'] += amt / c; p['inv'] += amt
                    if be_after is not None and k == be_after:
                        p['stop'] = max(p['stop'], p['inv'] / p['sh'])
        if reg.iloc[i] and d in by_day:
            for t in by_day[d]:
                j = col[t]
                if j in pos: continue
                if len(pos) >= 6: break
                c = Cn[i, j]; equity = val(); unit = equity / 6; amt = min(unit, cash + qsh * qc)
                if amt <= 0: break
                take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
                pos[j] = dict(entry=c, stop=c * 0.92, sh=amt / c, inv=amt, unit=unit, trig=[], last=c, eq0=equity); ntr += 1
        if qmode == 'none': qp = 0.0
        else:
            h = health(i); qp = 0.5 if (h is None or h >= 0 or not reg.iloc[i]) else 1.0
            if qmode == 'fixed50': qp = 0.5
        idle = cash + qsh * qc; qsh = idle * qp / qc; cash = idle - qsh * qc
        eq.append(val())
    e = pd.Series(eq, index=dates[idx]); yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = e.iloc[-1] ** (1 / yrs) - 1; dd = (e / e.cummax() - 1).min()
    run.last = e
    return cagr, dd, worst, ntr / yrs
if __name__ == '__main__':
    for qm in ('none', 'switch'):
        r = run(qmode=qm); print(f'今のルール qmode={qm}: 年率 {r[0]:.1%} DD {r[1]:.1%} 最大損失/銘柄 {r[2]:.1%} 年{r[3]:.0f}件', flush=True)
    e = run.last; y = e.resample('YE').last(); print({k.year: round(v, 3) for k, v in (y / y.shift(1).fillna(1) - 1).items()})
