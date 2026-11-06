"""Panels + MC57 rule selection, reproducing research/setups-2026-10 (panel.py, evaluate.py ranks, sel_check.py)."""
import json, os, glob, numpy as np, pandas as pd
tick = []
for p in sorted(glob.glob('meta/*.json')):
    s = os.path.basename(p)[:-5]
    m = json.load(open(p))
    if s != 'QQQ' and m.get('first') and m.get('type') == 'EQUITY' and os.path.exists(f'bars/{s}.csv'):
        tick.append(s)
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date')
cal = q.index
fields = {k: {} for k in ('open', 'high', 'low', 'close', 'volume')}
for t in tick:
    f = pd.read_csv(f'bars/{t}.csv', parse_dates=['date']).drop_duplicates('date').set_index('date')
    f = f[(f.close > 0) & (f.high >= f.low)]
    for k in fields:
        fields[k][t] = f[k].astype('float32')
W = {k: pd.DataFrame(d).reindex(cal).astype('float32') for k, d in fields.items()}
for k, w in W.items():
    w.to_pickle(f'w_{k}.pkl')
print('panel', W['close'].shape, flush=True)

C, H, V = W['close'], W['high'], W['volume']
regime = (q.close > q.close.rolling(200).mean()).reindex(C.index).fillna(False)
f32 = lambda x: x.astype('float32')
sma = lambda x, n: x.rolling(n, min_periods=n).mean()
# ranks exactly as evaluate.py (elig with dv20)
dv20 = sma(C * V, 20)
elig20 = (C >= 10) & (dv20 >= 20e6)
rs189 = f32((C / C.shift(189) - 1).where(elig20).rank(axis=1, pct=True) * 100)
# selection exactly as sel_check.py (elig with dv50)
dv50 = sma(C * V, 50)
elig = (C >= 10) & (dv50 >= 20e6)
s50, s150, s200 = sma(C, 50), sma(C, 150), sma(C, 200)
hi252 = H.rolling(252, min_periods=252).max()
TT = (C > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(20)) & (C >= 0.75 * hi252)
dvr = dv50.where(elig).rank(axis=1, pct=True)
SEL = (elig & TT & (rs189 >= 90) & (dvr >= 0.95) & regime.to_numpy()[:, None]).loc['2015-01-01':]
pd.to_pickle(SEL, 'sel.pkl')
ever = SEL.columns[SEL.any(axis=0)].tolist()
json.dump(ever, open('sel_tickers.json', 'w'))
print('selection days', int(SEL.to_numpy().sum()), 'tickers ever selected', len(ever), flush=True)
