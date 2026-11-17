"""Starts of declines and of rallies (Nasdaq-100 1990-2026, S&P 500 as a check).
Down start: first close 5% below the 252-session closing high (re-armed back within 2%); did it reach -10% / -20%
before getting back within 2%?  Up start: during a 10%+ decline, the first close 5% above the lowest close so far
(re-armed by a new low); did the index get back within 2% of its high before closing below that low?"""
import pandas as pd, numpy as np, sys
import ftd
rd=lambda nm,c='adj': pd.read_csv(f'macro/{nm}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date')[c]
IDXN=sys.argv[1] if len(sys.argv)>1 else 'NDX'
n=rd(IDXN,'close'); idx=n.loc['1989-01-01':].index; n=n.reindex(idx)
A={k:rd(k).reindex(idx).ffill() for k in ('SPY','RSP','XLP','XLU','XLF','XLE','XLK','XLY','XLI','XLB','XLV','OIL','GOLD','TLT','HYG','IEF')}
I={k:rd(k,'close').reindex(idx).ffill() for k in ('NDX','GSPC','RUT','SOX','VIX','VIX3M','TNX','IRX','DXY')}
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna().reindex(idx.union(baa.index)).ffill().reindex(idx)
hi=n.rolling(252,min_periods=200).max(); dd=n/hi-1; ma200=n.rolling(200).mean(); ma50=n.rolling(50).mean(); ret=n.pct_change()
SEC=['XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB']; sma={k:A[k].rolling(50).mean() for k in SEC}
# FTDs on QQQ (site rules) for the up side
qf,qev=ftd.events('QQQ'); ftd_days=pd.DatetimeIndex([e['date'] for e in qev])
def feats(i0,t,kind):
    a,b=idx[i0],idx[t]
    r=lambda s:(s.iloc[t]/s.iloc[i0]-1)*100 if pd.notna(s.iloc[i0]) and pd.notna(s.iloc[t]) and s.iloc[i0]>0 else np.nan
    seg=ret.iloc[i0+1:t+1]
    f=dict(days=t-i0, vix=I['VIX'].iloc[t], dvix=I['VIX'].iloc[t]-I['VIX'].iloc[i0],
        term=I['VIX'].iloc[t]/I['VIX3M'].iloc[t] if pd.notna(I['VIX3M'].iloc[t]) else np.nan,
        spx=r(I['GSPC'])-r(n), small=r(I['RUT'])-r(I['GSPC']), sox=r(I['SOX'])-r(I['NDX']),
        eqw=r(A['RSP'])-r(A['SPY']), dfn=(r(A['XLP'])+r(A['XLU']))/2-r(A['SPY']),
        cyc=(r(A['XLY'])+r(A['XLI'])+r(A['XLF']))/3-r(A['SPY']), ene=r(A['XLE'])-r(A['SPY']),
        d10=(I['TNX'].iloc[t]-I['TNX'].iloc[i0])*100, cred=(baa.iloc[t]-baa.iloc[i0])*100,
        hyg=r(A['HYG'])-r(A['IEF']), usd=r(I['DXY']), oil=r(A['OIL']), gold=r(A['GOLD']), tlt=r(A['TLT']),
        v200=(n.iloc[t]/ma200.iloc[t]-1)*100, a50=float(n.iloc[t]>ma50.iloc[t]),
        runup=(n.iloc[i0]/n.iloc[i0-252]-1)*100 if i0>=252 else np.nan,
        maxday=(seg.max() if kind=='up' else seg.min())*100, updays=(seg>0).mean()*100,
        sec50=sum(1 for s in SEC if A[s].iloc[t]>sma[s].iloc[t]) if pd.notna(sma['XLK'].iloc[t]) else np.nan,
        curve=I['TNX'].iloc[t]-I['IRX'].iloc[t])
    if kind=='up':
        f['ftd']=float(((ftd_days>=a)&(ftd_days<=b)).any()) if b>=pd.Timestamp('2000-03-01') else np.nan
        f['depth']=dd.iloc[i0]*100
    return f
def fwd(t):
    g=lambda k:(n.iloc[t+k]/n.iloc[t]-1)*100 if t+k<len(n) else np.nan
    m=lambda k:(n.iloc[t+1:t+k+1].min()/n.iloc[t]-1)*100 if t+k<len(n) else np.nan
    return dict(f20=g(20),f60=g(60),f120=g(120),f250=g(250),mdd60=m(60))
rows=[]
# down starts
armed=False
for t in range(260,len(n)):
    if not armed and dd.iloc[t]>=-0.02: armed=True
    elif armed and dd.iloc[t]<=-0.05:
        armed=False; w=n.iloc[t-252:t+1]; i0=idx.get_loc(w.idxmax())
        j=t; low=dd.iloc[t]
        while j<len(n)-1 and dd.iloc[j]>-0.02: j+=1;  low=min(low,dd.iloc[j]) if dd.iloc[j]<=-0.02 else low; 
        # recompute properly: lowest dd until back within 2%
        j=t; low=dd.iloc[t]
        while j<len(n)-1:
            j+=1
            if dd.iloc[j]>=-0.02: break
            low=min(low,dd.iloc[j])
        done=dd.iloc[j]>=-0.02 or j==len(n)-1
        rows.append(dict(kind='down',date=idx[t],ref=idx[i0],hit10=float(low<=-0.10),hit20=float(low<=-0.20),low=low*100,open_=not (dd.iloc[j]>=-0.02),**feats(i0,t,'down'),**fwd(t)))
# up starts
indec=False
for t in range(260,len(n)):
    c=n.iloc[t]
    if not indec:
        if dd.iloc[t]<=-0.10: indec=True; trough=c; ti=t; armed=True
        continue
    if dd.iloc[t]>=-0.02: indec=False; continue
    if c<trough: trough=c; ti=t; armed=True
    elif armed and c>=trough*1.05:
        armed=False; j=t; res=np.nan
        while j<len(n)-1:
            j+=1
            if n.iloc[j]<trough: res=0.0; break
            if dd.iloc[j]>=-0.02: res=1.0; break
        rows.append(dict(kind='up',date=idx[t],ref=idx[ti],ok=res,**feats(ti,t,'up'),**fwd(t)))
R=pd.DataFrame(rows); R['half']=np.where(R.date<'2008-01-01','1990-2007','2008-2026'); R.to_pickle(f'ud_{IDXN}.pkl')
D=R[R.kind=='down']; U=R[R.kind=='up']
print(IDXN,'down starts',len(D),'-> -10%:',round(D.hit10.mean()*100),'% -> -20%:',round(D.hit20.mean()*100),'%  by half',D.groupby('half').hit10.agg(['size','mean']).round(2).to_dict())
print(IDXN,'up starts',len(U),'-> real bottom (back near the high first):',round(U.ok.mean()*100),'%  by half',U.groupby('half').ok.agg(['size','mean']).round(2).to_dict())
def screen(S,y,keys):
    out=[]
    for k in keys:
        x=S.dropna(subset=[k,y])
        if len(x)<20: continue
        med=x[k].median() if x[k].nunique()>2 else 0.5
        res=[]
        for h in ('1990-2007','2008-2026'):
            z=x[x.half==h]; hi_=z[z[k]>med][y]; lo_=z[z[k]<=med][y]
            res.append((hi_.mean()*100 if len(hi_) else np.nan, lo_.mean()*100 if len(lo_) else np.nan, len(hi_), len(lo_)))
        d1=res[0][0]-res[0][1]; d2=res[1][0]-res[1][1]
        out.append(dict(k=k,cut=round(med,2),n=len(x),hi1=np.round(res[0][0]),lo1=np.round(res[0][1]),hi2=np.round(res[1][0]),lo2=np.round(res[1][1]),same=np.sign(d1)==np.sign(d2) and min(abs(d1),abs(d2))>=10))
    return pd.DataFrame(out)
K=['days','vix','dvix','term','spx','small','sox','eqw','dfn','cyc','ene','d10','cred','hyg','usd','oil','gold','tlt','v200','a50','runup','maxday','updays','sec50','curve']
pd.set_option('display.width',250)
print('\n== down start -> reaches -10% (rate % above / below the cut, by half)'); s=screen(D,'hit10',K); print(s.to_string(index=False))
print('\n== up start -> real bottom'); s2=screen(U,'ok',K+['ftd','depth']); print(s2.to_string(index=False))
