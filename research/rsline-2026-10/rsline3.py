import numpy as np, pandas as pd
exec(open('rsline2.py').read().split("base = evaluate")[0])
nh = RSL >= RSL.rolling(63, min_periods=63).max()
f63 = nh & ~nh.shift(1, fill_value=False).rolling(20, min_periods=1).max().astype(bool)
sel = TT & (r189 >= 90) & (dvr >= 0.95)
rng = np.random.default_rng(1)
def boot(T, k=3000):
    T = T.copy(); T['m'] = T.d.dt.to_period('M'); groups = [g['radd'].to_numpy() for _, g in T.groupby('m')]
    ms = []
    for _ in range(k):
        pick = rng.integers(0, len(groups), len(groups)); a = np.concatenate([groups[i] for i in pick]); ms.append(a.mean())
    return np.percentile(ms, [5, 50, 95])
for name, m in (('63日 全体', f63 & (off > .03) & (off <= .08) & TT),
                ('63日 本体の外', f63 & (off > .03) & (off <= .08) & TT & ~sel),
                ('63日 本体の外×売買代金上位50%', f63 & (off > .03) & (off <= .08) & TT & ~sel & (dvr >= .5)),
                ('63日 本体の外×RS189上位20%', f63 & (off > .03) & (off <= .08) & TT & ~sel & (r189 >= 80)),
                ('252日 全体', first & (off > .03) & (off <= .08) & TT)):
    T = evaluate(m, name); print('    年別', yearly(T)); print('    月ブロック平均(買増込) 5/50/95%', np.round(boot(T), 4))
B = evaluate(TT & (off > .03) & (off <= .08), '比較 TT×高値-3〜8%'); print('    比較 月ブロック', np.round(boot(B, 300), 4))
