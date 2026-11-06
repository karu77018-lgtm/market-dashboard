"""本命 candidates per day rebuilt with MC57's own rule code (scripts/swing_screener.py):
selected (TT, DV top 5%, RS189 top 10%) & 形 timing, QQQ > 200MA, plus weekly SAR / HL-structure
fields for buyable() and tier().  Point in time: only data up to the signal day."""
import sys, math, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import swing_screener as ss

W = {k: pd.read_pickle(f'w_{k}.pkl') for k in ('open', 'high', 'low', 'close', 'volume')}
H, L, C, V = W['high'], W['low'], W['close'], W['volume']
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(C.index)
reg = (q > q.rolling(200).mean())
state = ss._states(C, H, L, V)
hi252 = H.rolling(252, min_periods=200).max()
ma50 = C.rolling(50).mean()
start = C.index.get_loc(C.loc['2015-01-01':].index[0])
rows = []
Hn, Ln = H.to_numpy(float), L.to_numpy(float)
for k in range(start, len(C)):
    if not reg.iloc[k]:
        continue
    s = state(k)
    cand = s['selected'] & s['timing']
    for t in cand[cand].index:
        j = C.columns.get_loc(t)
        hh = Hn[:k + 1, j][-260:]; ll = Ln[:k + 1, j][-260:]
        d = ss.structure_detail(hh, ll)
        px = float(s['last'][t])
        line, hl = (float('nan'), float('nan')) if d is None else (d['line'], d['hl'])
        inside = bool(not math.isnan(line) and px <= line)
        pos = (px - hl) / (line - hl) if inside and line > hl else None
        try:
            up, age = ss.weekly_sar_state(H[t].iloc[:k + 1], L[t].iloc[:k + 1], C[t].iloc[:k + 1])
        except Exception:
            up, age = None, None
        r = dict(date=C.index[k], ticker=t, close=px, rs189=float(s['rs189_pct'][t]), rs63=float(s['rs63_pct'][t]),
                 dv=float(s['dv_pct'][t]), pivot_line=line, hl=hl, inside=inside, pos=pos, sar_up=up, sar_age=age,
                 hi_dist=px / float(hi252.iloc[k, j]) - 1, ext50=px / float(ma50.iloc[k, j]) - 1,
                 vc=float(s['vc'][t]), vdry=float(s['vdry'][t]), chg=float(s['chg'][t]))
        r['buyable'] = ss.buyable(r)
        r['tier'] = ss.tier(r)
        rows.append(r)
    if k % 250 == 0:
        print(C.index[k].date(), len(rows), flush=True)
df = pd.DataFrame(rows)
df.to_pickle('prod_cands.pkl')
print('candidates', len(df), 'buyable', int(df.buyable.sum()))
