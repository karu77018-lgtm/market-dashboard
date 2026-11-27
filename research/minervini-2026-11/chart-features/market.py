import pandas as pd, numpy as np, json, warnings
warnings.filterwarnings('ignore')
df = pd.read_parquet('feat.parquet', columns=['date', 'tk', 'struct', 'tt', 'ud50', 'overhead', 'bos_dn', 'brk20'])
px = pd.read_pickle('px.pkl')
q = px['QQQ'][['Open', 'High', 'Low', 'Close']]
st = df[~df.tk.isin(['SPY', 'QQQ'])]
br = st.groupby('date').agg(up_struct=('struct', lambda s: (s == 1).mean()), dn_struct=('struct', lambda s: (s == -1).mean()),
                            tt=('tt', 'mean'), ud=('ud50', lambda s: (s > 1).mean()),
                            lowoh=('overhead', lambda s: (s < 0.1).mean()), brk=('brk20', 'mean'), brkdn=('bos_dn', 'mean'))
br['struct_net'] = br.up_struct - br.dn_struct
br['brk_net10'] = (br.brk - br.brkdn).rolling(10).mean()
qf = df[df.tk == 'QQQ'].set_index('date')[['struct']]
from features import features
qq = features(px['QQQ'])
m = br.join(qq[['dist25', 'struct', 'overhead', 'ud50']].add_prefix('q_'))
# net liquidity
W = pd.read_csv('WALCL.csv', index_col=0, parse_dates=True).iloc[:, 0]
T = pd.read_csv('WTREGEN.csv', index_col=0, parse_dates=True).iloc[:, 0]
R = pd.to_numeric(pd.read_csv('RRPONTSYD.csv', index_col=0, parse_dates=True).iloc[:, 0], errors='coerce')
nl = (W - T).reindex(m.index, method='ffill') - R.reindex(m.index, method='ffill').fillna(0) * 1000
# 週次データは公表が翌週のため1週間遅らせる
nl = nl.shift(5)
m['nl_chg13'] = nl / nl.shift(63) - 1
c = q.Close; o1 = q.Open.shift(-1)
for h in (20, 60):
    m[f'q{h}'] = (c.shift(-h) / o1 - 1).reindex(m.index)
lw = q.Low.shift(-1)[::-1].rolling(60, min_periods=60).min()[::-1]
m['qdd60'] = (lw / o1 - 1).reindex(m.index)
m = m[m.index >= '2016-01-01']
out = {}
for col in ['struct_net', 'tt', 'ud', 'lowoh', 'brk_net10', 'q_dist25', 'q_struct', 'nl_chg13']:
    s = m[[col, 'q20', 'q60', 'qdd60']].dropna()
    if col in ('q_struct',):
        g = s.groupby(col)
    elif col == 'q_dist25':
        g = s.groupby(pd.cut(s[col], [-1, 2, 4, 6, 99], labels=['0-2', '3-4', '5-6', '7+']))
    else:
        g = s.groupby(pd.qcut(s[col], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5']))
    t = g.agg(n=('q20', 'size'), q20=('q20', 'mean'), q60=('q60', 'mean'), win60=('q60', lambda x: (x > 0).mean()), dd60=('qdd60', 'median'))
    t[['q20', 'q60', 'win60', 'dd60']] *= 100
    out[col] = t.round(2).reset_index().astype({t.index.name or col: str}).to_dict('records')
    print('\n==', col); print(t.round(2))
    # 期間別の頑健性
    for p, ss in (('16-20', s[s.index < '2021']), ('21-26', s[s.index >= '2021'])):
        print(p, 'corr60=', round(ss[col].corr(ss.q60, method='spearman'), 3), 'corrDD=', round(ss[col].corr(ss.qdd60, method='spearman'), 3))
m.to_pickle('market_series.pkl')
json.dump(out, open('market_results.json', 'w'), ensure_ascii=False, default=float)
print(m[['struct_net', 'tt', 'ud', 'lowoh', 'q_dist25', 'q_struct', 'nl_chg13']].tail(5))
