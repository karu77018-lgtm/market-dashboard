import numpy as np, pandas as pd, json
EQ=np.load('fresh_eq.npy'); ST=np.load('fresh_st.npy'); QQ=np.load('fresh_qq.npy'); S=pd.DatetimeIndex(pd.to_datetime(pd.read_pickle('fresh_starts.pkl')))
live=json.load(open('/home/claude/md/track-record/signals.json'))['modeled_portfolio']; le=[x[1] for x in live['equity']]; n=len(le)-1
print('live n sessions',n,'ret',round(le[-1]-1,4))
j=int(np.argmin(np.abs((S-pd.Timestamp('2026-10-05')).days))); print('replica fresh start',S[j].date(),np.round(EQ[j,[5,9,14,20,n-1]]-1,3),'stops10/20/30',ST[j])
print('live at same marks:',np.round(np.array(le)[[5,9,14,20,n]]-1,3))
qs=[0.5,1,2.5,5,10,25,50,75,90,95]
tab={}
for h in (10,15,20,25,29,30,40,50,60,80,100,125,150,200,250):
    x=EQ[:,h]-1; x=x[~np.isnan(x)]; tab[h]=np.percentile(x,qs)
T=pd.DataFrame(tab,index=[f'p{q}' for q in qs]).T*100
print(T.round(1).to_string())
x=EQ[:,n]-1; m=~np.isnan(x); x=x[m]; Sm=S[m]
print(f'\nhorizon {n}: N={len(x)} min {x.min():.3f} ; share <= live({le[-1]-1:.3f}): {(x<=le[-1]-1).mean()*100:.2f}% ; worst 8 starts:',[(str(Sm[i].date()),round(x[i],3)) for i in np.argsort(x)[:8]])
for a,b in (('2015','2021'),('2022','2026')):
    mm=(Sm>=a)&(Sm<=b+'-12-31'); print(f'  {a}-{b}: N={mm.sum()} p1 {np.percentile(x[mm],1)*100:.1f} p5 {np.percentile(x[mm],5)*100:.1f} p50 {np.percentile(x[mm],50)*100:.1f} min {x[mm].min()*100:.1f}  share<=live {(x[mm]<=le[-1]-1).mean()*100:.2f}%')
lq=live['equity'][-1][2]/live['equity'][0][2]
ex=(EQ[:,n]-QQ[:,n])[m]; print('excess vs QQQ at horizon: p1 %.1f p5 %.1f p50 %.1f ; live excess %.1f ; share<=live %.2f%%'%(np.percentile(ex,1)*100,np.percentile(ex,5)*100,np.percentile(ex,50)*100,(le[-1]-lq)*100,(ex<=le[-1]-lq).mean()*100))
dd=np.array([(EQ[i,:n+1]/np.maximum.accumulate(EQ[i,:n+1])-1).min() for i in range(len(EQ))])[m]
ldd=(np.array(le)/np.maximum.accumulate(le)-1).min(); print('max DD within horizon: p1 %.1f p5 %.1f p50 %.1f ; live %.1f ; share<=live %.2f%%'%(np.percentile(dd,1)*100,np.percentile(dd,5)*100,np.percentile(dd,50)*100,ldd*100,(dd<=ldd).mean()*100))
print('stops within 10 sessions of start:',{int(a):int(b) for a,b in zip(*np.unique(ST[:,0],return_counts=True))})
print('stops within 20:',{int(a):int(b) for a,b in zip(*np.unique(ST[:,1],return_counts=True))})
bad=np.where((EQ[:,n]-1<=-0.10))[0]; print('starts with <=-10%% at %d: %d (%.1f%%)'%(n,len(bad),len(bad)/m.sum()*100))
for h in (60,125,250):
    y=EQ[bad,h]; y=y[~np.isnan(y)]; print(f'   after {h} sessions from start: n={len(y)} median {np.median(y)-1:+.1%} p25 {np.percentile(y,25)-1:+.1%} worst {y.min()-1:+.1%} share back above start {(y>=1).mean():.0%}')
# clusters: distinct bad episodes
bs=S[bad]; ep=(pd.Series(bs).diff().dt.days.fillna(99)>20).cumsum(); print('bad-start episodes:',[(str(g.iloc[0].date()),str(g.iloc[-1].date()),len(g)) for _,g in pd.Series(bs).groupby(ep.values)])
