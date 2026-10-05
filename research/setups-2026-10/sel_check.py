import numpy as np, pandas as pd
C = pd.read_pickle('w_close.pkl'); V = pd.read_pickle('w_volume.pkl'); H = pd.read_pickle('w_high.pkl')
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close
regime = (q > q.rolling(200).mean()).reindex(C.index).fillna(False)
sma = lambda x, n: x.rolling(n, min_periods=n).mean()
dv20 = sma(C * V, 20); dv50 = sma(C * V, 50)
elig = (C >= 10) & (dv50 >= 20e6)
s50, s150, s200 = sma(C, 50), sma(C, 150), sma(C, 200)
hi252 = H.rolling(252, min_periods=252).max()
TT = (C > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(20)) & (C >= 0.75 * hi252)
r = pd.read_pickle('ranks.pkl')
dvr = dv50.where(elig).rank(axis=1, pct=True)
SEL = (elig & TT & (r['rs189'] >= 90) & (dvr >= 0.95) & regime.to_numpy()[:, None]).loc['2015-01-01':]
S = pd.read_pickle('setups.pkl')
out = {'選定そのもの（全日）': SEL}
for k in ['発火前', 'ポケットピボット', '21EMAタッチ', 'VCP', 'Multi VWAP', '底打ち', 'リーダー②継続', 'リーダー③押し目', 'リーダー①伸び過ぎ']:
    out['選定内×' + k] = S[k] & SEL
    out['選定外×' + k] = S[k] & ~SEL
pd.to_pickle(out, 'setups_sel.pkl')
print({k: int(v.to_numpy().sum()) for k, v in out.items()})
