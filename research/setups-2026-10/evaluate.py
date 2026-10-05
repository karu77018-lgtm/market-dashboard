"""Which Setups lists are worth looking at?  Same exits for all (research, local only).
Entry at the signal close, stop -8% (gap -> open), exit at the close below the 21-EMA of lows,
same-amount adds at +10/+20%.  QQQ above its 200-day line only.  2015-2026, current listings."""
import numpy as np, pandas as pd, json, sys
W = {k: pd.read_pickle(f'w_{k}.pkl') for k in ('open', 'high', 'low', 'close', 'volume')}
O, H, L, C, V = (W[k] for k in ('open', 'high', 'low', 'close', 'volume'))
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close
regime = (q > q.rolling(200).mean()).reindex(C.index).fillna(False)
f32 = lambda x: x.astype('float32')
btw = lambda x, a, b: (x >= a) & (x <= b)
sma = lambda x, n: f32(x.rolling(n, min_periods=n).mean())
dv20 = sma(C * V, 20)
elig = (C >= 10) & (dv20 >= 20e6)
ret63, ret189 = f32(C / C.shift(63) - 1), f32(C / C.shift(189) - 1)
rs63 = f32(ret63.where(elig).rank(axis=1, pct=True) * 100)
rs189 = f32(ret189.where(elig).rank(axis=1, pct=True) * 100)
s10, s21, s50, s150, s200 = (sma(C, n) for n in (10, 21, 50, 150, 200))
e21 = f32(C.ewm(span=21, adjust=False).mean())
el21 = f32(L.ewm(span=21, adjust=False).mean())
prevc = C.shift(1)
tr = f32(pd.concat([H - L, (H - prevc).abs(), (L - prevc).abs()]).groupby(level=0).max()) if False else None
tr = f32(np.maximum(H - L, np.maximum((H - prevc).abs(), (L - prevc).abs())))
atr14, atr10, atr50 = sma(tr, 14), sma(tr, 10), sma(tr, 50)
v10, v50 = sma(V, 10), sma(V, 50)
hi252 = f32(H.rolling(252, min_periods=252).max())
piv40 = f32(H.shift(1).rolling(40, min_periods=40).max())
lo40 = f32(L.rolling(40, min_periods=40).min())
idxhi = H.shift(1).rolling(40, min_periods=40).apply(lambda a: 39 - np.argmax(a[::-1]), raw=True) if False else None
# days since the 40-day high (approx via rolling argmax on numpy for speed)
Hn = H.shift(1).to_numpy()
since = np.full(Hn.shape, np.nan, dtype='float32')
for j in range(Hn.shape[1]):
    col = Hn[:, j]
    s = pd.Series(col)
    since[:, j] = s.rolling(40, min_periods=40).apply(lambda a: len(a) - 1 - np.nanargmax(a), raw=True).to_numpy()
since = pd.DataFrame(since, index=C.index, columns=C.columns)
tp = (H + L + C) / 3
vw63 = f32((tp * V).rolling(63, min_periods=63).sum() / V.rolling(63, min_periods=63).sum())
vw252 = f32((tp * V).rolling(252, min_periods=252).sum() / V.rolling(252, min_periods=252).sum())
TT = (C > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(20)) & (C >= 0.75 * hi252)
base = elig & regime.to_numpy()[:, None]
pd.to_pickle(dict(rs63=rs63, rs189=rs189), 'ranks.pkl')

S = {}
lead63 = (rs63 >= 85) & (C > s200)
# 1 発火前 (pre-breakout, generator thresholds)
depth40 = 1 - lo40 / piv40
pdist = C / piv40 - 1
ext50 = (C - s50) / atr14
quiet = (v10 / v50 <= 1) | (atr10 / atr50 <= 1) | ((C.rolling(3).max() / C.rolling(3).min() - 1) <= 0.015)
tight = ((C / s21 - 1).abs() <= 0.03) | ((C / vw63 - 1).abs() <= 0.03) | ((C / vw252 - 1).abs() <= 0.051)
S['発火前'] = base & (rs189 >= 80) & (rs63 >= 80) & TT & btw(depth40, 0.08, 0.35) & (since >= 10) \
    & btw(pdist, -0.08, 0.005) & (ext50 <= 4) & quiet & tight
# 2 ポケットピボット (leaders: RS189>=85 and above 200MA)
up = C > prevc
vdn = V.where(C < prevc)
dnmax = vdn.shift(1).rolling(10, min_periods=1).max()
S['ポケットピボット'] = base & up & (V > dnmax) & (C > s10) & (C > s50) & (rs189 >= 85) & (C > s200)
# 3 21EMAタッチ (rising 21EMA, touched in last 3 days, holding)
touch = ((L / (e21 * 1.005)).rolling(3).min() <= 1)
S['21EMAタッチ'] = base & touch & (C >= e21 * 0.99) & (e21 > e21.shift(10)) & (rs189 >= 80) & TT
# 4 VCP proxy (contracting range + drying volume near the pivot)
adr = sma(H / L - 1, 20)
S['VCP'] = base & (rs189 >= 80) & TT & (adr >= 0.025) & btw(depth40, 0.08, 0.35) & btw(pdist, -0.10, 0) \
    & (atr10 / atr50 <= 0.75) & (v10 / v50 <= 0.8)
# 5 Multi VWAP (63/252-day VWAP support or reclaim)
def vflags(vw):
    slope = vw / vw.shift(5) - 1
    touched = (L / (vw * 1.0075)).rolling(3).min() <= 1
    dist = C / vw - 1
    sup = touched & (C >= vw) & (dist <= 0.025) & (slope >= -0.005)
    rec = (prevc < vw.shift(1)) & (C >= vw) & (slope >= -0.005)
    return sup | rec
S['Multi VWAP'] = base & (vflags(vw63) | vflags(vw252)) & (rs189 >= 80) & (C > s200)
# 6 底打ち (higher low after a correction, break of the 10-day high, RS63 >= 70)
dd = C / hi252 - 1
hl = (L.rolling(10).min() > L.shift(10).rolling(30).min())
S['底打ち'] = base & btw(dd, -0.50, -0.15) & hl & (C > H.shift(1).rolling(10).max()) & (rs63 >= 70) & (v10 / v50 <= 1.2)
# 7 リーダー状態 (RS63>=85 & 200MA up) by state
pb = C / H.rolling(40).max() - 1; d21 = C / s21 - 1; r5 = C / C.shift(5) - 1; d50 = C / s50 - 1
st5 = (C < s50) | (d21 < -0.06)
st4 = ~st5 & (pb < -0.08)
st3 = ~st5 & ~st4 & btw(pb, -0.08, -0.02) & btw(d21, -0.05, 0.05) & (r5 > -0.03)
st1 = ~st5 & ~st4 & ~st3 & (d21 > 0.10)
st2 = ~st5 & ~st4 & ~st3 & ~st1
for name, mk in (('リーダー②継続', st2), ('リーダー③押し目', st3), ('リーダー①伸び過ぎ', st1), ('リーダー④深押し', st4), ('リーダー⑤割れ', st5)):
    S[name] = base & lead63 & mk
# baselines (sampled every 10th day per ticker to keep counts manageable)
samp = pd.DataFrame((np.arange(len(C))[:, None] + np.arange(C.shape[1])[None, :]) % 10 == 0, index=C.index, columns=C.columns)
S['基準:流動性のある全銘柄'] = base & samp
S['基準:リーダー（RS63≥85・200日線上）'] = base & lead63 & samp
S['基準:TT＋RS189≥80'] = base & TT & (rs189 >= 80) & samp
S['参考:本命の選定（TT・売買代金上位5%・RS189上位10%）'] = base & TT & (rs189 >= 90) & (dv20.where(elig).rank(axis=1, pct=True) >= 0.95) & samp
pd.to_pickle({k: v.loc['2015-01-01':] for k, v in S.items()}, 'setups.pkl')
print({k: int(v.loc['2015-01-01':].to_numpy().sum()) for k, v in S.items()})
