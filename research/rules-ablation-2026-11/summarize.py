"""Trade-level summary with bootstrap CI, top-3 dependence, yearly losses; optional next-open file.
usage: summarize.py TRADES.pkl [TRADES_NEXTOPEN.pkl] [OUT.csv]"""
import sys, numpy as np, pandas as pd
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.nan
rng = np.random.default_rng(1)
def ci(x, n=2000):
    x = x.to_numpy(); b = [pf(pd.Series(rng.choice(x, len(x)))) for _ in range(n)]
    return np.percentile(b, 5), np.percentile(b, 95)
dc = pd.read_pickle(sys.argv[1])
do = pd.read_pickle(sys.argv[2]) if len(sys.argv) > 2 else None
rows = []
for s, g in dc.groupby('setup', sort=False):
    a, b = g[g.date < '2021'], g[g.date >= '2021']
    yr = g.groupby(g.date.dt.year).pnl_add.apply(pf)
    lo, hi = ci(g.pnl_add)
    r = [s, len(g), pf(g.pnl_add), lo, hi, pf(a.pnl_add), pf(b.pnl_add),
         pf(g.pnl_add.drop(g.nlargest(3, 'pnl_add').index)), int((yr < 1).sum())]
    if do is not None: r.append(pf(do[do.setup == s].pnl_add))
    rows.append(r)
cols = ['rule', 'n', 'PF_add', 'CI5', 'CI95', '2015-20', '2021-26', 'ex_top3', 'years_PF<1'] + (['PF_nextopen'] if do is not None else [])
t = pd.DataFrame(rows, columns=cols).set_index('rule')
pd.set_option('display.width', 250); print(t.round(2).to_string())
if len(sys.argv) > 3: t.round(3).to_csv(sys.argv[3])
