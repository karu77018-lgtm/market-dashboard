import numpy as np, pandas as pd, sys, time
S = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.pkl') else 'setups.pkl')
W = {k: pd.read_pickle(f'w_{k}.pkl').loc['2015-01-01':] for k in ('open', 'high', 'low', 'close')}
full_low = pd.read_pickle('w_low.pkl')
EL = full_low.ewm(span=21, adjust=False).mean().loc['2015-01-01':].to_numpy()
O, H, L, C = (W[k].to_numpy() for k in ('open', 'high', 'low', 'close'))
dates = W['close'].index
try:
    from numba import njit
except Exception:
    njit = lambda f: f

@njit
def run_ticker(sig, o, l, c, el):
    n = len(c); out = []
    busy = -1
    for t in range(n):
        if not sig[t] or t <= busy or np.isnan(c[t]):
            continue
        entry = c[t]; stop = entry * 0.92; sh = 1.0 / entry; inv = 1.0; adds = 0; t1 = False; t2 = False
        x = -1.0; xi = n - 1
        for i in range(t + 1, n):
            if np.isnan(c[i]):
                continue
            if o[i] <= stop:
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
names = list(S)
for name in names:
    M = S[name].to_numpy()
    t0 = time.time(); cnt = 0
    for j in np.where(M.any(axis=0))[0]:
        for (t, xi, ret, pnl, adds) in run_ticker(M[:, j], O[:, j], L[:, j], C[:, j], EL[:, j]):
            rows.append((name, j, dates[t], dates[xi], ret, pnl, adds, xi - t)); cnt += 1
    print(name, cnt, round(time.time() - t0, 1), flush=True)
pd.DataFrame(rows, columns=['setup', 'col', 'date', 'exit', 'ret', 'pnl_add', 'adds', 'days']).to_pickle(('setup_trades_sel.pkl' if len(sys.argv) > 1 else 'setup_trades.pkl'))
