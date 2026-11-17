"""本命 signals in the 10 sessions after a QQQ follow-through day, split by what was known that day."""
import pandas as pd, numpy as np, ftd
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
df,ev=ftd.events('QQQ'); q=df.close.to_numpy(float); ql=df.low.to_numpy(float); qv=df.volume.to_numpy(float); qi={d:i for i,d in enumerate(df.index)}
state={}
for e in ev:
    i=e['i']; fl=e['low']
    for k in range(0,11):
        if i+k>=len(q): break
        d=df.index[i+k]
        if k>0 and q[i+k]<fl: break                      # already failed: no longer "after an FTD"
        neg1= (q[i+1]<q[i]) if k>=1 else None
        dist=any((q[i+t]<q[i+t-1]*0.998) and qv[i+t]>qv[i+t-1] for t in range(1,k+1)) if k>=1 else False
        risky=(e['day']<=7) or (e['day']>=16)
        warn=(1 if neg1 else 0)+(1 if dist else 0)
        state[d]=('当日' if k==0 else ('警告なし' if warn==0 else '警告あり'),risky,k)
rows=[]
for d,t in zip(sig.date,sig.ticker):
    s=state.get(d)
    rows.append(dict(date=d,t=t,grp=('FTD後10日以内・'+s[0]) if s else 'それ以外',risky=(s[1] if s else None),ret=trade(d,t)))
R=pd.DataFrame(rows).dropna(subset=['ret']); R['ret']=R.ret.clip(upper=3)
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
for nm,sub in (('全期間',R),('2015-2020',R[R.date<'2021']),('2021-2026',R[R.date>='2021'])):
    g=sub.groupby('grp'); print(nm); print(pd.DataFrame({'件数':g.size(),'平均%':g.ret.mean()*100,'勝率%':g.ret.apply(lambda x:(x>0).mean()*100),'PF':g.ret.apply(pf)}).round(2).to_string())
a=R[R.grp!='それ以外']; g=a.groupby('risky'); print('FTD後10日以内の本命：日数リスク高(True)/低(False)'); print(pd.DataFrame({'件数':g.size(),'平均%':g.ret.mean()*100,'PF':g.ret.apply(pf)}).round(2).to_string())
