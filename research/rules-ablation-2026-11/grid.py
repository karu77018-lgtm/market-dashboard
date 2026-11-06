"""Rule ablation / variation grid around the MC57 selection. Exits fixed (trades.py)."""
import numpy as np, pandas as pd
W = {k: pd.read_pickle(f'w_{k}.pkl') for k in ('open', 'high', 'low', 'close', 'volume')}
O, H, L, C, V = (W[k] for k in ('open', 'high', 'low', 'close', 'volume'))
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(C.index)
sma = lambda x, n: x.rolling(n, min_periods=n).mean()
col = lambda s: s.fillna(False).to_numpy()[:, None]
REG = {
    'QQQ>200MA': col(q > sma(q, 200)),
    'なし': np.ones((len(C), 1), bool),
    'QQQ>50MA': col(q > sma(q, 50)),
    'QQQ>200MA&50MA': col((q > sma(q, 200)) & (q > sma(q, 50))),
    'QQQ>200MA&200MA上向き': col((q > sma(q, 200)) & (sma(q, 200) > sma(q, 200).shift(20))),
}
dv20, dv50 = sma(C * V, 20), sma(C * V, 50)
elig20 = (C >= 10) & (dv20 >= 20e6)
rank = lambda r: (r.where(elig20).rank(axis=1, pct=True) * 100)
RS = {n: rank(C / C.shift(n) - 1) for n in (63, 126, 189)}
RS['加重'] = rank(0.4 * (C / C.shift(63) - 1) + 0.2 * (C / C.shift(126) - 1) + 0.2 * (C / C.shift(189) - 1) + 0.2 * (C / C.shift(252) - 1))
elig = (C >= 10) & (dv50 >= 20e6)
dvr = dv50.where(elig).rank(axis=1, pct=True)
s10, s21, s50, s150, s200 = (sma(C, n) for n in (10, 21, 50, 150, 200))
e21 = C.ewm(span=21, adjust=False).mean()
hi252 = H.rolling(252, min_periods=252).max()
TTp = dict(a=C > s50, b=s50 > s150, c=s150 > s200, d=s200 > s200.shift(20), e=C >= 0.75 * hi252)
TT = TTp['a'] & TTp['b'] & TTp['c'] & TTp['d'] & TTp['e']
TT_noe = TTp['a'] & TTp['b'] & TTp['c'] & TTp['d']
TT_nod = TTp['a'] & TTp['b'] & TTp['c'] & TTp['e']
prevc = C.shift(1)
tr = np.maximum(H - L, np.maximum((H - prevc).abs(), (L - prevc).abs()))
atr14 = sma(tr, 14)
EPS = pd.read_pickle('eps_labels.pkl').reindex(columns=C.columns).reindex(C.loc['2015-01-01':].index)

def sel(tt=TT, rs='189', rsmin=90, dvmin=0.95, reg='QQQ>200MA', extra=None):
    m = elig & reg_mask(reg)
    if tt is not None: m &= tt
    if rs is not None: m &= RS[int(rs) if rs.isdigit() else rs] >= rsmin
    if dvmin is not None: m &= dvr >= dvmin
    if extra is not None: m &= extra
    return m.loc['2015-01-01':]
def reg_mask(name):
    return pd.DataFrame(np.repeat(REG[name], C.shape[1], 1), index=C.index, columns=C.columns)

G = {}
G['00 基準（MC57ルール）'] = sel()
# --- 外す
G['10 −TT'] = sel(tt=None)
G['11 −RS189'] = sel(rs=None)
G['12 −売買代金上位5%'] = sel(dvmin=None)
G['13 −地合い(QQQ>200MA)'] = sel(reg='なし')
G['14 −TTの52週高値-25%以内'] = sel(tt=TT_noe)
G['15 −TTの200MA上向き'] = sel(tt=TT_nod)
G['16 TTのみ（RS・売買代金なし）'] = sel(rs=None, dvmin=None)
# --- 閾値を変える
for v in (80, 85, 95): G[f'20 RS189≥{v}'] = sel(rsmin=v)
for v in (0.90, 0.80, 0.98): G[f'21 売買代金上位{round((1-v)*100)}%'] = sel(dvmin=v)
for n in ('63', '126', '加重'): G[f'22 RS{n}≥90（189の代わり）'] = sel(rs=n)
for r in ('QQQ>50MA', 'QQQ>200MA&50MA', 'QQQ>200MA&200MA上向き'): G[f'23 地合い {r}'] = sel(reg=r)
# --- 足す
G['30 +RS63≥80'] = sel(extra=RS[63] >= 80)
G['31 +52週高値-10%以内'] = sel(extra=C >= 0.90 * hi252)
G['32 +52週高値-5%以内'] = sel(extra=C >= 0.95 * hi252)
G['33 +21EMA上'] = sel(extra=C > e21)
G['34 +50MAから3ATR以内（伸び切り除外）'] = sel(extra=(C - s50) / atr14 <= 3)
G['35 +50MA乖離+25%以内'] = sel(extra=C / s50 - 1 <= 0.25)
G['36 +売買代金増加（20日>50日）'] = sel(extra=dv20 > dv50)
G['37 +10MA上'] = sel(extra=C > s10)
G['38 +5日で+15%超を除外'] = sel(extra=(C / C.shift(5) - 1) <= 0.15)
base = sel()
G['40 +EPS 減速・減益を除外'] = base & ~EPS.isin(['DECEL_ONE_Q', 'DECEL_CONFIRMED', 'CONTRACTION']).to_numpy()
G['41 +EPS 加速確定を除外'] = base & ~EPS.isin(['ACCEL_CONFIRMED', 'ACCEL_PERSISTENT']).to_numpy()
pd.to_pickle(G, 'sig_grid.pkl')
print({k: int(v.to_numpy().sum()) for k, v in G.items()})
