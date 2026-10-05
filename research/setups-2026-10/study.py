"""IPO-base breakout study (research, local only).  Definitions fixed up front."""
import json, sys, os, math
import numpy as np, pandas as pd

MIN_AGE, MAX_AGE = 15, 504          # trading days since first bar (IPO)
MIN_BASE = 15                       # days since the high before breaking it (>= 3 weeks)
DEPTH = (0.10, 0.50)
VOL_X = 1.4
MIN_PX, MIN_DV = 10.0, 20e6
STOP, ADDS = 0.08, (0.10, 0.20)

def load(t):
    f = pd.read_csv(f'bars/{t}.csv', parse_dates=['date'])
    f = f[(f.close > 0) & (f.high >= f.low)].drop_duplicates('date').reset_index(drop=True)
    return f

qqq = load('QQQ'); qqq['ma200'] = qqq.close.rolling(200).mean()
REG = dict(zip(qqq.date, qqq.close > qqq.ma200))

def spac_like(f):
    head = f.close.iloc[:60]
    return len(head) >= 20 and ((head >= 9.4) & (head <= 10.7)).mean() >= 0.8

def trade(f, t, ema, next_open=False):
    o, h, l, c = f.open.values, f.high.values, f.low.values, f.close.values
    if next_open:
        if t + 1 >= len(f): return None
        e_i, entry = t + 1, o[t + 1]
    else:
        e_i, entry = t, c[t]
    stop = entry * (1 - STOP); shares, inv, adds, trig = 1 / entry, 1.0, 0, []
    i = e_i + (0 if next_open else 1)
    if next_open:                      # entry day itself: intraday stop / close checks
        pass
    while i < len(f):
        if i > e_i or next_open is False:
            if o[i] <= stop and i > e_i:
                return dict(exit=o[i], xi=i, why='gap', shares=shares, inv=inv, adds=adds, entry=entry, ei=e_i)
        if l[i] <= stop:
            return dict(exit=stop, xi=i, why='stop', shares=shares, inv=inv, adds=adds, entry=entry, ei=e_i)
        if c[i] < ema[i]:
            return dict(exit=c[i], xi=i, why='ema', shares=shares, inv=inv, adds=adds, entry=entry, ei=e_i)
        for n, lv in enumerate(ADDS):
            if n not in trig and round(c[i] / entry - 1, 9) >= lv:
                trig.append(n); shares += 1 / c[i]; inv += 1; adds += 1
        i += 1
    return dict(exit=c[-1], xi=len(f) - 1, why='open', shares=shares, inv=inv, adds=adds, entry=entry, ei=e_i)

def signals(t, f, ipo=True, next_open=False):
    out = []
    if len(f) < MIN_AGE + 5: return out
    h, l, c, v = f.high.values, f.low.values, f.close.values, f.volume.values.astype(float)
    dv20 = pd.Series(c * v).rolling(20, min_periods=10).mean().values
    vavg = pd.Series(v).shift(1).rolling(50, min_periods=10).mean().values
    ema = pd.Series(l).ewm(span=21, adjust=False).mean().values
    busy_until, base_no = -1, 0
    start = MIN_AGE if ipo else 252
    stop_at = MAX_AGE if ipo else len(f) - 1
    for t in range(start, min(len(f), stop_at + 1)):
        lo_win = 0 if ipo else t - 252
        win = h[lo_win:t]
        H = win.max(); k = lo_win + len(win) - 1 - int(np.argmax(win[::-1]))   # last index of the high
        if c[t] <= H or c[t - 1] > H: continue
        if t - k < MIN_BASE: continue
        depth = 1 - l[k:t].min() / H
        if not (DEPTH[0] <= depth <= DEPTH[1]): continue
        if not (v[t] >= VOL_X * vavg[t]): continue
        if c[t] < MIN_PX or not (dv20[t] >= MIN_DV): continue
        base_no += 1
        if t <= busy_until: continue
        d = f.date.iloc[t]
        r = trade(f, t, ema, next_open)
        if r is None: continue
        busy_until = r['xi']
        out.append(dict(ticker=t_name, date=d, age=t, base_no=base_no, depth=depth, ext=c[t] / H - 1,
                        dayret=c[t] / c[t - 1] - 1, regime=bool(REG.get(d, False)),
                        ret=r['exit'] / r['entry'] - 1, ret_add=r['shares'] * r['exit'] / r['inv'] - 1,
                        days=r['xi'] - r['ei'], why=r['why'], adds=r['adds'],
                        r63=(c[t] / c[t - 63] - 1) if t >= 63 else np.nan, exit_date=f.date.iloc[r['xi']]))
    return out

if __name__ == '__main__':
    mode = sys.argv[1]; nxt = len(sys.argv) > 2 and sys.argv[2] == 'open'
    names = json.load(open('ipo_list.json' if mode == 'ipo' else 'seasoned_list.json'))
    rows, skipped = [], {'missing': 0, 'spac': 0, 'late': 0}
    for t_name in names:
        if not os.path.exists(f'bars/{t_name}.csv'): skipped['missing'] += 1; continue
        f = load(t_name)
        if len(f) == 0: continue
        if mode == 'ipo':
            if f.date.iloc[0] < pd.Timestamp('2014-07-01'): skipped['late'] += 1; continue
            if spac_like(f): skipped['spac'] += 1; continue
        rows += signals(t_name, f, ipo=(mode == 'ipo'), next_open=nxt)
    df = pd.DataFrame(rows)
    df.to_csv(f'trades_{mode}{"_open" if nxt else ""}.csv', index=False)
    print(mode, 'next_open' if nxt else 'close', len(df), skipped)
