import numpy as np, pandas as pd
C = pd.read_pickle('w_close.pkl'); O = pd.read_pickle('w_open.pkl'); L = pd.read_pickle('w_low.pkl'); V = pd.read_pickle('w_volume.pkl')
dates = C.index
spy = pd.read_csv('bars/SPY.csv', parse_dates=['date']).set_index('date').close.reindex(dates)
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(dates)
reg = (q > q.rolling(200).mean()).to_numpy()
sma = lambda x, n: x.rolling(n, min_periods=n).mean()
dv50 = sma(C * V, 50)
elig = (C >= 10) & (dv50 >= 20e6)
m50, m150, m200 = sma(C, 50), sma(C, 150), sma(C, 200)
hi252 = C.rolling(252, min_periods=252).max()
TT = (C > m50) & (m50 > m150) & (m150 > m200) & (m200 > m200.shift(20)) & (C >= 0.75 * hi252)
r189 = (C / C.shift(189) - 1).where(elig).rank(axis=1, pct=True) * 100
dvr = dv50.where(elig).rank(axis=1, pct=True)
RSL = C.div(spy, axis=0)
rsl_new = RSL >= RSL.rolling(252, min_periods=252).max()          # RS line at a 52-week high today
first = rsl_new & ~rsl_new.shift(1, fill_value=False).rolling(20, min_periods=1).max().astype(bool)  # first in 20 days
off = 1 - C / hi252                                                  # price below its 52-week closing high
Cn, On, Ln = C.to_numpy(float), O.to_numpy(float), L.to_numpy(float)
En = L.ewm(span=21, adjust=False).mean().to_numpy(float)
n = len(dates); start = dates.get_loc(dates[dates >= '2015-01-01'][0])
def trade(i, j):
    e = Cn[i, j]; stop = e * .92; units = 1.0; cost = e; trig = 0
    for k in range(i + 1, n):
        o, l, c = On[k, j], Ln[k, j], Cn[k, j]
        if np.isnan(c): continue
        px = o if o <= stop else stop if l <= stop else c if c < En[k, j] else None
        if px is not None: return px / e - 1, (units * px - cost) / e, k - i
        for lv in (1.10, 1.20)[trig:]:
            if c >= e * lv: units += e / c; cost += e; trig += 1
    return None
def evaluate(mask, name, every_day=False):
    M = (mask & elig).to_numpy() & reg[:, None]
    out = []
    for j in range(M.shape[1]):
        idx = np.flatnonzero(M[start:, j]) + start; busy = -1
        for i in idx:
            if i <= busy: continue
            r = trade(i, j)
            if r is None: continue
            busy = i + r[2]; out.append((dates[i], r[0], r[1], r[2]))
    T = pd.DataFrame(out, columns=['d', 'ret', 'radd', 'days'])
    if T.empty: print(name, 'none'); return T
    pf = lambda s: s[s > 0].sum() / -s[s < 0].sum()
    a, b = T[T.d < '2021-01-01'], T[T.d >= '2021-01-01']
    print(f"{name:34s} n={len(T):5d}/yr {len(T)/11.7:5.0f}  avg {T.ret.mean():+.3f} add {T['radd'].mean():+.3f}  PF {pf(T.ret):.2f} PFadd {pf(T['radd']):.2f}  win {(T.ret>0).mean():.2f}  "
          f"15-20 PF {pf(a['radd']):.2f}  21-26 PF {pf(b['radd']):.2f}", flush=True)
    return T
lead = first
lead_nohigh = first & (off > 0.03)
sel = TT & (r189 >= 90) & (dvr >= 0.95)
lead_r = TT & (r189 >= 80)
print('--- baselines (enter whenever condition true & flat)')
evaluate(elig, '全銘柄（流動性あり）')
evaluate(TT, 'トレンドテンプレート')
evaluate(lead_r, 'TT×RS189上位20%')
print('--- RS line new high (first in 20 days)')
evaluate(lead, 'RSライン新高値（全部）')
for lo, hi in ((0, .03), (.03, .08), (.08, .15), (.15, .25), (.25, .5)):
    evaluate(first & (off > lo) & (off <= hi), f'RSL新高値×株価は高値-{lo:.0%}〜{hi:.0%}')
print('--- with leader filters')
evaluate(lead_nohigh & TT, 'RSL先行（株価-3%超）×TT')
for lo, hi in ((.03, .08), (.08, .15), (.15, .25)):
    evaluate(first & (off > lo) & (off <= hi) & TT, f'RSL先行×TT×高値-{lo:.0%}〜{hi:.0%}')
evaluate(lead_nohigh & lead_r, 'RSL先行×TT×RS189上位20%')
evaluate(lead_nohigh & TT & (dvr >= .5), 'RSL先行×TT×売買代金上位50%')
evaluate(lead_nohigh & TT & (dvr < .95), 'RSL先行×TT×本体の外(DV<95%)')
evaluate(first & (off <= .03) & TT, 'RSLと株価が同時に新高値×TT')
pd.to_pickle(dict(first=first, off=off, TT=TT, r189=r189, dvr=dvr), 'rsl_masks.pkl')
