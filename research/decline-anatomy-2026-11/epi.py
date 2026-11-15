import pandas as pd, numpy as np
rd=lambda n,c='adj': pd.read_csv(f'macro/{n}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date')[c]
ndx=rd('NDX','close'); idx=ndx.loc['1989-01-01':].index
S={k:rd(k).reindex(idx).ffill() for k in ('SPY','XLP','XLU','XLF','XLE','XLK','IWF','IWD','OIL','GOLD')}
I={k:rd(k,'close').reindex(idx).ffill() for k in ('NDX','GSPC','RUT','SOX','VIX','TNX','IRX','DXY')}
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna().reindex(idx.union(baa.index)).ffill().reindex(idx)
n=I['NDX']; hi=n.rolling(252,min_periods=200).max(); dd=n/hi-1; ma200=n.rolling(200).mean()
def episodes(trig=-0.10, rearm=-0.04):
    ev=[]; armed=True
    for t in range(260,len(n)):
        if armed and dd.iloc[t]<=trig:
            w=n.iloc[t-252:t+1]; pk=w.idxmax(); ev.append((pk,idx[t])); armed=False
        elif not armed and dd.iloc[t]>=rearm: armed=True
    return ev
def feats(pk,T):
    r=lambda s: (s[T]/s[pk]-1)*100 if pd.notna(s.get(pk,np.nan)) and pd.notna(s.get(T,np.nan)) else np.nan
    p=idx.get_loc(pk); t=idx.get_loc(T)
    return dict(peak=pk.date(),T=T.date(),depth=round(r(n),1),days=t-p,vix=I['VIX'][T],dvix=I['VIX'][T]-I['VIX'][pk],
      runup=(n[pk]/n.iloc[p-252]-1)*100 if p>=252 else np.nan, v200=(n[T]/ma200[T]-1)*100,
      sox=r(I['SOX'])-r(n), small=r(I['RUT'])-r(I['GSPC']), spx=r(I['GSPC'])-r(n),
      dfn=(r(S['XLP'])+r(S['XLU']))/2-r(S['SPY']), fin=r(S['XLF'])-r(S['SPY']), ene=r(S['XLE'])-r(S['SPY']),
      d10=(I['TNX'][T]-I['TNX'][pk])*100, d3m=(I['IRX'][T]-I['IRX'][pk])*100, curve=I['TNX'][T]-I['IRX'][T],
      cred=(baa[T]-baa[pk])*100, usd=r(I['DXY']), oil=r(S['OIL']), gold=r(S['GOLD']))
def outcomes(pk,T):
    t=idx.get_loc(T); f=lambda k: (n.iloc[t+k]/n.iloc[t]-1)*100 if t+k<len(n) else np.nan
    seg=n.iloc[t:t+251]; lowi=seg.idxmin()
    # episode bottom: min until dd recovers to >= -4%
    j=t
    while j<len(n)-1 and dd.iloc[j]<-0.04: j+=1
    ep=n.iloc[idx.get_loc(pk):j+1]; bot=ep.idxmin()
    return dict(more=round((seg.min()/n.iloc[t]-1)*100,1), final=round((ep.min()/n[pk]-1)*100,1), bot=bot.date(), d2bot=idx.get_loc(bot)-t, f20=f(20),f60=f(60),f120=f(120),f250=f(250), done=bool(j<len(n)-1))
ev=episodes(); rows=[{**feats(a,b),**outcomes(a,b)} for a,b in ev if b>=pd.Timestamp('1990-06-01')]
E=pd.DataFrame(rows); E.to_pickle('episodes.pkl')
pd.set_option('display.width',300); pd.set_option('display.max_columns',40)
print(E.round(1).to_string())
print('now',idx[-1].date(),'NDX dd',round(dd.iloc[-1]*100,1),'VIX',I['VIX'].iloc[-1])
