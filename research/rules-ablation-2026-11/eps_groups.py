"""Signal sets: the rule selection split by point-in-time EPS state (inside), and TT+RS189>=80 outside it."""
import json, numpy as np, pandas as pd
SEL = pd.read_pickle('sel.pkl'); L = pd.read_pickle('eps_labels.pkl').fillna('NO_DATA')
A = ['ACCEL_CONFIRMED', 'ACCEL_PERSISTENT']
LOWB = ['ACCEL_CONFIRMED_LOWBASE', 'ACCEL_PERSISTENT_LOWBASE']
ONE = ['ACCEL_ONE_Q', 'IMPROVING_3Q']
DEC = ['DECEL_ONE_Q', 'DECEL_CONFIRMED', 'CONTRACTION']
BAD = ['LOSS', 'TURNAROUND', 'NON_COMPARABLE']
isin = lambda F, xs: F.isin(xs).to_numpy()
G = {
    '全体（基準）': SEL,
    'A 加速確定（V38主候補）': SEL & isin(L, A),
    'A2 加速確定＋低ベース': SEL & isin(L, A + LOWB),
    'B 加速系すべて（単発含む）': SEL & isin(L, A + LOWB + ONE),
    'C 横ばい': SEL & isin(L, ['FLAT']),
    'D 減速・減益': SEL & isin(L, DEC),
    'E 赤字・黒字転換・比較不能': SEL & isin(L, BAD),
    'F データ不足': SEL & isin(L, ['INSUFFICIENT', 'NO_DATA']),
    'notA 加速確定以外': SEL & ~isin(L, A),
    'notD 減速・減益を除外': SEL & ~isin(L, DEC),
}
pd.to_pickle(G, 'sig_eps.pkl')

# outside the selection: TT & RS189>=80 & liquid & QQQ>200MA, not selected
C = pd.read_pickle('w_close.pkl'); H = pd.read_pickle('w_high.pkl'); V = pd.read_pickle('w_volume.pkl')
sma = lambda x, n: x.rolling(n, min_periods=n).mean()
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close
reg = (q > q.rolling(200).mean()).reindex(C.index).fillna(False)
e20 = (C >= 10) & (sma(C * V, 20) >= 20e6)
rs189 = (C / C.shift(189) - 1).where(e20).rank(axis=1, pct=True) * 100
s50, s150, s200 = sma(C, 50), sma(C, 150), sma(C, 200); hi = H.rolling(252, min_periods=252).max()
TT = (C > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(20)) & (C >= 0.75 * hi)
U = (e20 & TT & (rs189 >= 80) & reg.to_numpy()[:, None]).loc['2015-01-01':] & ~SEL
pd.to_pickle(U, 'out_universe.pkl')
json.dump(U.columns[U.any(axis=0)].tolist(), open('out_tickers.json', 'w'))
print('outside tickers', int(U.any(axis=0).sum()))
