import pandas as pd, numpy as np
O,H,L,C,V=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','high','low','close','volume'))
X=pd.read_pickle('s4.pkl'); S,B,F=X['S'],X['B'],X['F']
idx=C.index; n=len(idx)
Cn,On,Ln=C.to_numpy(),O.to_numpy(),L.to_numpy(); En=L.ewm(span=21,adjust=False).mean().to_numpy()
dv50=(C*V).rolling(50,min_periods=40).mean()
liq=((C>=10)&(dv50>=20e6)).to_numpy()
r=lambda k:C/C.shift(k)
rsraw=0.4*r(63)+0.2*r(126)+0.2*r(189)+0.2*r(252)
RS=(rsraw.where(dv50>=5e6).rank(axis=1,pct=True)*100).to_numpy()
hi252c=C.rolling(252,min_periods=200).max()
fresh=(C>=hi252c)&~((C>=hi252c).shift(1).rolling(20,min_periods=1).max().astype(bool))
low_base=C.rolling(252,min_periods=200).min()
depth=(1-C.rolling(252,min_periods=200).min()/C.shift(1).rolling(252,min_periods=200).max())   # rough base depth
# base depth as in bagger card: prior 252-session high to the lowest close since it
def base_depth():
    Hc=C.shift(1).rolling(252,min_periods=200).max().to_numpy(); out=np.full(C.shape,np.nan)
    return Hc
FR=fresh.to_numpy()
# outcome helpers
def outcome(i,j):
    if i+1>=n or np.isnan(On[i+1,j]) or On[i+1,j]<=0: return None
    e=On[i+1,j]; end=min(n,i+253); c=Cn[i+1:end,j]
    if np.isnan(c).all() or end-i<200: return None
    c=pd.Series(c).ffill().to_numpy()
    dbl=np.nanmax(c)/e>=2
    r1=c[-1]/e-1
    # bagger exit: -25% trailing stop on closes from the highest close
    pk=-np.inf; tr=c[-1]/e-1
    for x in c:
        pk=max(pk,x)
        if x<=0.75*pk: tr=x/e-1; break
    # swing rule exit
    st=e*0.92; sw=np.nan
    for k in range(i+1,end):
        if Ln[k,j]<=st: sw=(min(On[k,j],st) if k>i+1 else st)/e-1; break
        if Cn[k,j]<En[k,j]: sw=Cn[k,j]/e-1; break
    return dbl,min(r1,5),min(tr,5),sw
start,stop=idx.get_loc(idx[idx>='2014-06-01'][0]), idx.get_loc(idx[idx<='2025-11-14'][-1])
def collect(mask,name,sample=None,seed=0):
    ii,jj=np.nonzero(mask[start:stop+1]); ii=ii+start
    if sample and len(ii)>sample:
        s=np.random.default_rng(seed).choice(len(ii),sample,replace=False); ii,jj=ii[s],jj[s]
    rows=[]
    for i,j in zip(ii,jj):
        o=outcome(i,j)
        if o: rows.append((idx[i],C.columns[j],*o,RS[i,j]))
    D=pd.DataFrame(rows,columns=['date','t','dbl','r1y','trail','swing','rs']); D['name']=name; return D
liqB=B&liq
Hprev=C.shift(1).rolling(252,min_periods=200).max().to_numpy()
lowsince=C.rolling(252,min_periods=200).min().to_numpy()
deep=(1-lowsince/Hprev)>=0.30
bag=FR&deep&liq&(RS>=90)
parts=[collect(liqB,'TLブレイク'),collect(liqB&(RS>=80),'TLブレイク+RS80'),
       collect((S==1)&liq,'ステージ4の任意の日',sample=20000),
       collect(liq,'全銘柄の任意の日',sample=30000),
       collect(bag,'大化け候補ブレイク(既存)')]
D=pd.concat(parts); D.to_pickle('s4eval.pkl')
D['half']=np.where(D.date<'2020-01-01','2014-19','2020-25')
def pf(x): x=x.dropna(); return x[x>0].sum()/-x[x<=0].sum()
g=D.groupby(['name','half'])
T=pd.DataFrame({'n':g.size(),'2倍到達%':g.dbl.mean()*100,'1年後中央値%':g.r1y.median()*100,'1年後平均%':g.r1y.mean()*100,
  '−25%トレール平均%':g.trail.mean()*100,'トレール勝率%':g.trail.apply(lambda x:(x>0).mean()*100),'スイング出口PF':g.swing.apply(pf)}).round(1)
order=['全銘柄の任意の日','ステージ4の任意の日','TLブレイク','TLブレイク+RS80','大化け候補ブレイク(既存)']
print(T.reindex(order,level=0).to_string())
