import pandas as pd, numpy as np
d = pd.read_pickle('setup_trades.pkl')
ipo = pd.read_csv('trades_ipo.csv', parse_dates=['date']); ipo = ipo[(ipo.date >= '2015') & ipo.regime]
ipo = pd.DataFrame(dict(setup='IPOベース', date=ipo.date, ret=ipo.ret, pnl_add=ipo.ret_add * (1 + ipo.adds), adds=ipo.adds, days=ipo.days))
d = pd.concat([d, ipo])
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.nan
rows = []
for s, g in d.groupby('setup', sort=False):
    y = g.groupby(g.date.dt.year).pnl_add.apply(pf)
    a, b = g[g.date < '2021'], g[g.date >= '2021']
    rows.append(dict(setup=s, n=len(g), per_yr=round(len(g) / 11.75), win=round((g.ret > 0).mean() * 100),
                     avg=round(g.ret.mean() * 100, 2), PF=round(pf(g.ret), 2), PF_add=round(pf(g.pnl_add), 2),
                     PF_15_20=round(pf(a.pnl_add), 2), PF_21_26=round(pf(b.pnl_add), 2),
                     bad_yrs=int((y < 1).sum()), days=round(g.days.mean())))
t = pd.DataFrame(rows).set_index('setup')
pd.set_option('display.width', 220)
print(t.to_string())
