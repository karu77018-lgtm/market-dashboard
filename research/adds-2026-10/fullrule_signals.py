"""本命 signals 2014-2026 with the dashboard's own rule code (swing_screener / breakout_health)."""
import sys, math, numpy as np, pandas as pd
sys.path.insert(0, '/home/claude/market-dashboard/scripts')
from swing_screener import structure_pivot, MIN_PRICE, MIN_DV, DV_PCT, RS189_PCT, MAX_VC, MAX_VDRY, MAX_CHG, MAX_PREV_CHG
from breakout_health import _sar_up_at
O, H, L, C, V = (pd.read_pickle(f'w_{k}.pkl') for k in ('open', 'high', 'low', 'close', 'volume'))
ma50, ma150, ma200 = (C.rolling(n).mean() for n in (50, 150, 200))
hi252 = H.rolling(252, min_periods=200).max()
dv50 = (C * V).rolling(50, min_periods=40).mean()
dr = H / L - 1
vc = dr.rolling(10).mean() / dr.rolling(50).mean()
vdry = V.rolling(5).mean() / V.rolling(50).mean()
chg = (C / C.shift(1) - 1).round(9)
liquid = (C >= MIN_PRICE) & (dv50 >= MIN_DV)
tt = (C > ma50) & (ma50 > ma150) & (ma150 > ma200) & (ma200 > ma200.shift(20)) & (C >= 0.75 * hi252)
dvp = dv50.where(liquid).rank(axis=1, pct=True) * 100
r189 = C / C.shift(189) - 1
rsp = r189.where(liquid).rank(axis=1, pct=True) * 100
timing = (vc <= MAX_VC) & (vdry <= MAX_VDRY) & (chg < MAX_CHG) & (chg.shift(1) <= MAX_PREV_CHG)
sig = (liquid & tt & (dvp >= DV_PCT) & (rsp >= RS189_PCT) & timing).loc['2014-06-01':]
print('selected&timing', int(sig.to_numpy().sum()), flush=True)
cache = {}
Hn, Ln, Cn = H.to_numpy(float), L.to_numpy(float), C.to_numpy(float)
pos_of = {d: i for i, d in enumerate(C.index)}
rows = []
for d, row in sig.iterrows():
    i = pos_of[d]
    for t in row.index[row.to_numpy()]:
        j = C.columns.get_loc(t)
        if not _sar_up_at(cache, t, H, L, C, d):
            continue
        px = Cn[i, j]
        line, hl = structure_pivot(Hn[max(0, i - 259):i + 1, j], Ln[max(0, i - 259):i + 1, j])
        inside = not math.isnan(line) and px <= line
        if inside and line > hl and (px - hl) / (line - hl) < 0.5:
            continue
        rows.append((d, t, float(rsp.iat[i, j])))
out = pd.DataFrame(rows, columns=['date', 'ticker', 'rs189'])
out.to_pickle('honmei.pkl')
print('本命 signals', len(out), out.date.dt.year.value_counts().sort_index().to_dict())
