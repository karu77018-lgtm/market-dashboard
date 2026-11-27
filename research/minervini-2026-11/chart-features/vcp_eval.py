import pandas as pd, numpy as np
d = pd.read_pickle('vcp_trades.pkl'); d = d[d.date >= '2016-01-01']
d['per'] = np.where(d.date < '2021-01-01', 'A', 'B'); d['m'] = d.date.dt.to_period('M')
def st(x):
    if len(x) < 30: return None
    w = x[x.ret > 0]; lo = x[x.ret <= 0]
    mm = x.groupby('m').ret.mean()
    return dict(N=len(x), win=(x.ret > 0).mean()*100, avgW=w.ret.mean()*100, avgL=lo.ret.mean()*100,
                payoff=-w.ret.mean()/lo.ret.mean() if len(lo) else np.nan, exp=x.ret.mean()*100, med=x.ret.median()*100,
                R=x.R.mean(), stop=(x.R <= -0.99).mean()*100, hold=x.hold.median(), t=mm.mean()/mm.std()*np.sqrt(len(mm)),
                expA=x[x.per=='A'].ret.mean()*100, expB=x[x.per=='B'].ret.mean()*100)
V = lambda q: d[(d.kind=='VCP') & q]
rows = []
for univ, um in (('文面', d.text_tt), ('原典', d.orig_tt)):
    for ex in ('ma50', 'time60'):
        base = (d.exit==ex) & um
        sets = {
          '①毎週金曜に買うだけ(基準)': d[base & (d.kind=='RANDOM')],
          '②20日高値ブレイク(基準)': d[base & (d.kind=='BRK20')],
          '③VCP(収縮2回以上・逓減)': V(base & (d.entry_mode=='stop')),
          '③\'同 終値確認→翌寄り': V(base & (d.entry_mode=='nextopen')),
          '④収縮3回以上': V(base & (d.entry_mode=='stop') & (d.n_vcp>=3)),
          '⑤2回で2回目が70%超縮小': V(base & (d.entry_mode=='stop') & (d.n_vcp==2) & (d.shrink2<=0.3)),
          '⑥毎回ほぼ半分(比≤0.6)': V(base & (d.entry_mode=='stop') & (d.max_ratio<=0.6)),
          '⑦最終収縮≤10%': V(base & (d.entry_mode=='stop') & (d.dlast<=0.10)),
          '⑧出来高枯れ(最終/最初<0.8)': V(base & (d.entry_mode=='stop') & (d.vol_dry<0.8)),
          '⑨ベース4〜8週': V(base & (d.entry_mode=='stop') & d.base_len.between(20,40)),
          '⑩文面フルセット(④or⑤＋⑥＋⑧)': V(base & (d.entry_mode=='stop') & (((d.n_vcp>=3)&(d.max_ratio<=0.6))|((d.n_vcp==2)&(d.shrink2<=0.3))) & (d.vol_dry<0.8)),
          '⑪VCP×UD比≥1.4': V(base & (d.entry_mode=='stop') & (d.ud50>=1.4)),
          '⑫VCP×UD比<1.4': V(base & (d.entry_mode=='stop') & (d.ud50<1.4)),
          '⑬VCP×株価≥30(分割調整後)': V(base & (d.entry_mode=='stop') & (d.price>=30)),
        }
        for k, x in sets.items():
            s = st(x)
            if s: rows.append({'univ': univ, 'exit': ex, 'set': k, **s})
r = pd.DataFrame(rows)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
print(r.round(2).to_string(index=False))
r.to_pickle('vcp_summary.pkl')
