import pandas as pd, numpy as np, json, warnings
warnings.filterwarnings('ignore')
df = pd.read_parquet('feat.parquet')
df = df[(df.date >= '2016-01-01')]
mkt = df[df.tk.isin(['SPY', 'QQQ'])].copy()
df = df[~df.tk.isin(['SPY', 'QQQ'])]
df = df[df.f20.notna()].copy()
for h in ('f20', 'f60'):
    lo, hi = df[h].quantile([.01, .99])
    df[h] = df[h].clip(lo, hi)
    df['x' + h[1:]] = df[h] - df.groupby('date')[h].transform('median')
df['period'] = np.where(df.date < '2021-01-01', 'A_16-20', 'B_21-26')
df['month'] = df.date.dt.to_period('M')
dates = np.sort(df.date.unique())
samp5 = set(dates[::5]); samp20 = set(dates[::20])

CONT = {
 'struct': '市場構造(+1=HH/HL,-1=LH/LL)', 'dist_res': '直上ピボットまでの距離(ATR)', 'res_near': '上方1ATR内の壁の数',
 'overhead': '上値のしこり(252日出来高のうち現値より上)', 'thin_up': '現値〜+2ATRの出来高比率', 'pos_poc': 'POCからの位置(ATR)',
 'd_avwap_hi': '52週高値起点AVWAPとの乖離', 'd_avwap_lo': '52週安値起点AVWAPとの乖離',
 'ud50': 'UD比(50日)', 'dist25': 'ディストリビューション日数(25日)', 'acc25': '大商い上昇日数(25日)', 'clv20': '引け位置(出来高加重20日)',
 'range_ratio': '値幅収縮(10日幅/60日幅)', 'vol_dry': '出来高枯れ(10日/50日)', 'atr_ratio': 'ATR10/ATR50',
 'ldv50': '売買代金(log)', 'amihud': '非流動性(Amihud)'}

def cont_eval(d, col):
    s = d[d.date.isin(samp5)][['date', col, 'x20', 'mae20', 'period']].dropna()
    s = s[s.groupby('date')[col].transform('count') >= 30]
    s['r'] = s.groupby('date')[col].rank(pct=True)
    s['rx'] = s.groupby('date')['x20'].rank(pct=True)
    ic = s.groupby('date').apply(lambda g: np.corrcoef(g.r, g.rx)[0, 1])
    ic20 = ic[ic.index.isin(samp20)]
    s['q'] = np.minimum((s.r * 5).astype(int), 4) + 1
    q = s.groupby('q').agg(x20=('x20', 'mean'), mae=('mae20', 'median'))
    icp = s.groupby('period').apply(lambda g: g.groupby('date').apply(lambda x: np.corrcoef(x.r, x.rx)[0, 1]).mean())
    return dict(ic=ic.mean(), t=ic20.mean() / ic20.std() * np.sqrt(len(ic20)),
                icA=icp.get('A_16-20', np.nan), icB=icp.get('B_21-26', np.nan),
                q=[round(x * 100, 2) for x in q.x20], spread=(q.x20.iloc[-1] - q.x20.iloc[0]) * 100,
                maeQ1=q.mae.iloc[0] * 100, maeQ5=q.mae.iloc[-1] * 100)

res = {'cont': {}, 'event': {}}
subsets = {'ALL': df, 'TT': df[df.tt]}
for sn, d in subsets.items():
    for col in CONT:
        r = cont_eval(d, col); r['name'] = CONT[col]; res['cont'][f'{sn}|{col}'] = r
        print(sn, col, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != 'name'}, flush=True)

# ---------- イベント ----------
def dedupe(d, mask, gap=10):
    m = d[mask][['tk', 'date']].copy()
    m['i'] = d[mask].index
    pos = d.groupby('tk').cumcount()
    m['p'] = pos[mask].values
    m['prev'] = m.groupby('tk').p.shift()
    keep = m[(m.prev.isna()) | (m.p - m.prev > gap)].i
    return d.loc[keep]

EV = {
 'brk20': ('20日高値ブレイク(基準)', lambda d: d.brk20),
 'bos_up': ('構造ブレイク(直近ピボット高値を終値で上抜け)', lambda d: d.bos_up),
 'choch_up': ('下降構造からの転換(CHoCH)', lambda d: d.choch_up),
 'bos_dn': ('直近ピボット安値割れ', lambda d: d.bos_dn),
 'sr3': ('3回以上試されたレジスタンス突破', lambda d: d.sr_touch_bo >= 3),
 'sr1': ('1回だけのレジスタンス突破', lambda d: d.sr_touch_bo == 1),
 'pocket': ('ポケットピボット', lambda d: d.pocket),
 'tight_bo': ('収縮→出来高放れ(VCP型)', lambda d: d.tight_bo),
 'loose_bo': ('収縮なしのブレイク', lambda d: d.loose_bo),
 'avwap_reclaim': ('52週高値起点AVWAP奪回', lambda d: d.avwap_reclaim),
 'brk_lowOH': ('ブレイク×上値しこり少(<10%)', lambda d: d.brk20 & (d.overhead < 0.10)),
 'brk_highOH': ('ブレイク×上値しこり多(>30%)', lambda d: d.brk20 & (d.overhead > 0.30)),
 'brk_ud_hi': ('ブレイク×UD比≥1.4', lambda d: d.brk20 & (d.ud50 >= 1.4)),
 'brk_ud_lo': ('ブレイク×UD比<1.0', lambda d: d.brk20 & (d.ud50 < 1.0)),
 'brk_clv_hi': ('ブレイク×引け強い(CLV20上位)', lambda d: d.brk20 & (d.clv20 > 0.15)),
 'brk_dist_hi': ('ブレイク×売り抜け日多(≥6)', lambda d: d.brk20 & (d.dist25 >= 6)),
}
def ev_stats(e, base):
    m = e.groupby('month').x20.mean()
    return dict(n=len(e), x20=e.x20.mean() * 100, med20=e.x20.median() * 100, win=(e.x20 > 0).mean() * 100,
                x60=e.x60.mean() * 100, mae=e.mae20.median() * 100, t=m.mean() / m.std() * np.sqrt(len(m)),
                base_x20=base.x20.mean() * 100, base_win=(base.x20 > 0).mean() * 100, base_mae=base.mae20.median() * 100,
                xA=e[e.period == 'A_16-20'].x20.mean() * 100, xB=e[e.period == 'B_21-26'].x20.mean() * 100)
for sn, d in subsets.items():
    d = d.sort_values(['tk', 'date']).reset_index(drop=True)
    for k, (nm, f) in EV.items():
        e = dedupe(d, f(d).fillna(False).astype(bool))
        r = ev_stats(e, d); r['name'] = nm; res['event'][f'{sn}|{k}'] = r
        print(sn, k, {a: round(b, 2) for a, b in r.items() if a != 'name'}, flush=True)

json.dump(res, open('results.json', 'w'), ensure_ascii=False, default=float)
