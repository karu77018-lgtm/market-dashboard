import numpy as np, pandas as pd
C = pd.read_pickle('w_close.pkl'); O = pd.read_pickle('w_open.pkl'); L = pd.read_pickle('w_low.pkl')
Cn, On, Ln = C.to_numpy(float), O.to_numpy(float), L.to_numpy(float)
En = L.ewm(span=21, adjust=False).mean().to_numpy(float)
X9 = (C / C.ewm(span=9, adjust=False).mean() - 1).to_numpy(float)
X21 = (C / C.ewm(span=21, adjust=False).mean() - 1).to_numpy(float)
dates = C.index; pos_of = {d: i for i, d in enumerate(dates)}; col = {t: j for j, t in enumerate(C.columns)}
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(dates)
reg = (q > q.rolling(200).mean()).to_numpy()
n = len(dates)
def trade(i, j):
    e = Cn[i, j]; stop = e * .92; units = 1.0; cost = e; trig = 0
    for k in range(i + 1, n):
        o, l, c = On[k, j], Ln[k, j], Cn[k, j]
        if np.isnan(c): continue
        px = o if o <= stop else stop if l <= stop else c if c < En[k, j] else None
        if px is not None:
            return px / e - 1, (units * px - cost) / e, k - i
        for lv in (1.10, 1.20)[trig:]:
            if c >= e * lv: units += e / c; cost += e; trig += 1
    return None
sig = pd.read_pickle('honmei.pkl'); sig = sig[sig.date >= '2015-01-01']
rows = []
for d, t in zip(sig.date, sig.ticker):
    i, j = pos_of[d], col[t]
    if not reg[i]: continue
    r = trade(i, j)
    if r: rows.append(dict(d=d, x9=X9[i, j], x21=X21[i, j], ret=r[0], radd=r[1], days=r[2]))
H = pd.DataFrame(rows)
S = pd.read_pickle('setup_trades_sel.pkl'); S = S[S.setup == '選定そのもの（全日）'].copy()
S['x9'] = [X9[pos_of[d], c] for d, c in zip(S.date, S.col)]
S['radd'] = S.pnl_add; S['d'] = S.date
def pf(s): return s[s > 0].sum() / -s[s < 0].sum() if (s < 0).any() else np.nan
bins = [-1, -.04, -.03, -.02, -.01, 0, .01, .02, .03, .04, .05, .07, 9]
for name, T in (('本命シグナル（全日）', H), ('選定銘柄（形を問わず）', S)):
    T = T.copy(); T['b'] = pd.cut(T.x9, bins); T['era'] = np.where(T.d < '2021-01-01', 'A', 'B')
    g = T.groupby('b', observed=True)
    out = pd.DataFrame({'n': g.size(), '平均': g.ret.mean(), '買増込': g.radd.mean(), 'PF': g.ret.apply(pf),
        '勝率': g.ret.apply(lambda s: (s > 0).mean()), '損切率': g.ret.apply(lambda s: (s <= -.079).mean()),
        '15-20': T[T.era == 'A'].groupby('b', observed=True).radd.mean(), '21-26': T[T.era == 'B'].groupby('b', observed=True).radd.mean()})
    print('=====', name, len(T)); print((out).round(3).to_string())
