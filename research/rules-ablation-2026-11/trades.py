"""Exits identical to MC57 research/setups-2026-10/trades_all.py:
entry at signal close, stop -8% (gap -> open), exit at close below 21-EMA of lows, adds at +10/+20%."""
import numpy as np, pandas as pd, sys
from numba import njit
SIG = pd.read_pickle(sys.argv[1])  # dict name -> bool DataFrame (dates x tickers), from 2015
out_path = sys.argv[2]
NXT = len(sys.argv) > 3 and sys.argv[3] == 'nextopen'
W = {k: pd.read_pickle(f'w_{k}.pkl').loc['2015-01-01':] for k in ('open', 'low', 'close')}
EL = pd.read_pickle('w_low.pkl').ewm(span=21, adjust=False).mean().loc['2015-01-01':]
dates = W['close'].index; cols = W['close'].columns

@njit
def run_ticker(sig, o, l, c, el, nxt):
    n = len(c); out = []
    busy = -1
    for t in range(n):
        if not sig[t] or t <= busy or np.isnan(c[t]):
            continue
        t0 = t
        if nxt:
            if t + 1 >= n or np.isnan(o[t + 1]):
                continue
            entry = o[t + 1]; t0 = t + 1
        else:
            entry = c[t]
        stop = entry * 0.92; sh = 1.0 / entry; inv = 1.0; adds = 0; t1 = False; t2 = False
        x = -1.0; xi = n - 1
        for i in range(t0 if nxt else t + 1, n):
            if np.isnan(c[i]):
                continue
            if i > t0 and o[i] <= stop:
                x = o[i]; xi = i; break
            if l[i] <= stop:
                x = stop; xi = i; break
            if c[i] < el[i]:
                x = c[i]; xi = i; break
            r = c[i] / entry - 1
            if not t1 and r >= 0.1 - 1e-9:
                t1 = True; sh += 1.0 / c[i]; inv += 1.0; adds += 1
            if not t2 and r >= 0.2 - 1e-9:
                t2 = True; sh += 1.0 / c[i]; inv += 1.0; adds += 1
        if x < 0:
            last = c[t]
            for i in range(n - 1, t, -1):
                if not np.isnan(c[i]):
                    last = c[i]; break
            x = last
        busy = xi
        out.append((t, xi, x / entry - 1, sh * x - inv, adds))
    return out

rows = []
for name, S in SIG.items():
    S = S.reindex(index=dates, columns=cols, fill_value=False).fillna(False)
    M = S.to_numpy(dtype=bool)
    for j in np.where(M.any(axis=0))[0]:
        o = W['open'].iloc[:, j].to_numpy(np.float64); l = W['low'].iloc[:, j].to_numpy(np.float64)
        c = W['close'].iloc[:, j].to_numpy(np.float64); el = EL.iloc[:, j].to_numpy(np.float64)
        for (t, xi, ret, pnl, adds) in run_ticker(M[:, j], o, l, c, el, NXT):
            rows.append((name, cols[j], dates[t], dates[xi], ret, pnl, adds, xi - t))
d = pd.DataFrame(rows, columns=['setup', 'ticker', 'date', 'exit', 'ret', 'pnl_add', 'adds', 'days'])
d.to_pickle(out_path)
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.nan
for s, g in d.groupby('setup', sort=False):
    a, b = g[g.date < '2021'], g[g.date >= '2021']
    print(f"{s}: n={len(g)} win={(g.ret>0).mean()*100:.0f}% avg={g.ret.mean()*100:.2f}% PF={pf(g.ret):.2f} "
          f"PF_add={pf(g.pnl_add):.2f} 15-20={pf(a.pnl_add):.2f} 21-26={pf(b.pnl_add):.2f}")
