import numpy as np, pandas as pd
exec(open('ema9_study.py').read().split("sig = pd.read_pickle")[0])
sig = pd.read_pickle('honmei.pkl'); sig = sig[sig.date >= '2015-01-01'].sort_values(['ticker', 'date'])
rows = []
for t, g in sig.groupby('ticker'):
    j = col[t]; busy = -1; prev = -10
    for d in g.date:
        i = pos_of[d]
        first = i - prev > 1; prev = i
        if not reg[i] or i <= busy: continue
        r = trade(i, j)
        if not r: continue
        busy = i + r[2]
        rows.append(dict(d=d, t=t, x9=X9[i, j], ret=r[0], radd=r[1], first=first))
T = pd.DataFrame(rows); print('独立トレード', len(T), ' うち連続シグナルの初日', T['first'].sum())
def pf(s): return s[s > 0].sum() / -s[s < 0].sum()
rng = np.random.default_rng(0)
def ci(s, k=4000):
    a = s.to_numpy(); m = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(k)]
    return np.percentile(m, [5, 95])
for bins, lab in (([-1, -.04, -.02, -.01, 0, .01, .02, .03, .05, 9], '細かく'), ([-1, -.01, .02, .03, .05, 9], '粗く')):
    T['b'] = pd.cut(T.x9, bins); T['era'] = np.where(T.d < '2021-01-01', 'A', 'B')
    rows = []
    for b, g in T.groupby('b', observed=True):
        lo, hi = ci(g['radd'])
        rows.append(dict(b=str(b), n=len(g), 平均=g.ret.mean(), 買増込=g['radd'].mean(), 下5=lo, 上95=hi, PF=pf(g.ret),
                         損切率=(g.ret <= -.079).mean(), A=g[g.era == 'A']['radd'].mean(), B=g[g.era == 'B']['radd'].mean(), nA=(g.era == 'A').sum()))
    print('=====', lab); print(pd.DataFrame(rows).round(3).to_string(index=False))
