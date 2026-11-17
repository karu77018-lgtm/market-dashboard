"""本命 signals by industry-group strength and by distance to earnings (local panel, 2014-2026)."""
import pandas as pd, numpy as np, json
sig=pd.read_pickle('honmei.pkl')
C=pd.read_pickle('close.pkl').astype(float); O=pd.read_pickle('open.pkl').astype(float); L=pd.read_pickle('low.pkl').astype(float)
EL=L.ewm(span=21,adjust=False).mean(); idx=C.index; pos={d:i for i,d in enumerate(idx)}
Cn,On,Ln,En=C.to_numpy(),O.to_numpy(),L.to_numpy(),EL.to_numpy(); col={t:j for j,t in enumerate(C.columns)}
def trade(d,t):
    i,j=pos[d],col[t]
    if i+1>=len(idx) or np.isnan(On[i+1,j]): return np.nan
    e=On[i+1,j]; st=e*0.92
    for k in range(i+1,min(len(idx),i+250)):
        if Ln[k,j]<=st: return (min(On[k,j],st) if k>i+1 else st)/e-1
        if Cn[k,j]<En[k,j]: return Cn[k,j]/e-1
    return np.nan
ind=json.load(open('industry.json')); earn={t:pd.to_datetime(v) for t,v in json.load(open('earnings.json')).items()}
lab=pd.Series({t:v[1] for t,v in ind.items() if v[1]}); sec=pd.Series({t:v[0] for t,v in ind.items() if v[0]})
r63=C.pct_change(63,fill_method=None); r126=C.pct_change(126,fill_method=None)
def grp_rank(r,labels,d,minn=5):
    x=r.loc[d].dropna(); x=x[x.index.isin(labels.index)]; g=x.groupby(labels.reindex(x.index)).agg(['median','size']); g=g[g['size']>=minn]
    return g['median'].rank(pct=True)
rows=[]
for d,t in zip(sig.date,sig.ticker):
    if d not in pos or t not in col: continue
    ret=trade(d,t)
    if np.isnan(ret): continue
    gi=lab.get(t); gs=sec.get(t)
    ri=grp_rank(r63,lab,d).get(gi,np.nan) if gi else np.nan
    ri6=grp_rank(r126,lab,d).get(gi,np.nan) if gi else np.nan
    rs=grp_rank(r63,sec,d,20).get(gs,np.nan) if gs else np.nan
    e=earn.get(t,pd.DatetimeIndex([]))
    nxt=e[e>d]; prv=e[e<=d]
    dn=np.busday_count(d.date(),nxt.min().date()) if len(nxt) else np.nan
    dp=np.busday_count(prv.max().date(),d.date()) if len(prv) else np.nan
    rows.append(dict(date=d,t=t,ret=min(ret,3),ind=ri,ind6=ri6,sec=rs,dnext=dn,dprev=dp))
R=pd.DataFrame(rows); R['half']=np.where(R.date<'2020-01-01','2014-19','2020-26'); R.to_pickle('fi.pkl')
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
def show(name,m):
    o=[]
    for h in ('2014-19','2020-26'):
        z=R[R.half==h]; a=z[m[z.index]]; b=z[~m[z.index]]
        o.append(f'{h}: PF {pf(a.ret):.2f} 平均{a.ret.mean()*100:+.1f}% 勝率{(a.ret>0).mean()*100:.0f}% (n{len(a)}) vs PF {pf(b.ret):.2f} {b.ret.mean()*100:+.1f}% {(b.ret>0).mean()*100:.0f}% (n{len(b)})')
    print(f'{name:30s}',' | '.join(o))
print('signals',len(R), R.groupby('half').size().to_dict(), 'industry known',R.ind.notna().mean().round(2),'earnings known',R.dnext.notna().mean().round(2))
for q in (0.8,0.67,0.5): show(f'業種63日 上位{int((1-q)*100)}%',R.ind>=q)
show('業種63日 下位33%',R.ind<0.33)
for q in (0.8,0.5): show(f'業種126日 上位{int((1-q)*100)}%',R.ind6>=q)
show('セクター63日 上位半分',R.sec>=0.5)
for k in (5,10,15): show(f'決算まで{k}営業日以内',R.dnext<=k)
for k in (5,10,20): show(f'決算後{k}営業日以内',R.dprev<=k)
