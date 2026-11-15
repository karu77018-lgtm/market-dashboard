import pandas as pd, numpy as np, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import epi
idx=epi.idx; n=epi.n
rd=lambda nm,c='adj': pd.read_csv(f'macro/{nm}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date')[c]
def fred(sid,lag=0):
    s=pd.read_csv(f'macro/F_{sid}.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; s=pd.to_numeric(s,errors='coerce').dropna()
    if lag: s.index=s.index+pd.Timedelta(days=lag)      # publication lag for monthly data
    return s.reindex(idx.union(s.index)).ffill().reindex(idx)
A={k:rd(k).reindex(idx.union(rd(k).index)).ffill().reindex(idx) for k in ('JPY','COPPER','EFA','EEM','N225','DAX','IGV','SMH','BTC','TLT','IWF','IWD','RSP','SPY','XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB','GOLD')}
X={k:rd(k,'close').reindex(idx).ffill() for k in ('SKEW','VIX3M','VVIX','VIX','GSPC')}
qv=rd('QQQV','close').reindex(idx)
dff=fred('DFF'); un=fred('UNRATE',35); cpi=fred('CPIAUCSL',45); nfci=fred('NFCI',7); wti=fred('DCOILWTICO'); d2=fred('DGS2'); d10=fred('DGS10'); d3=fred('DTB3')
rec=pd.read_csv('macro/F_USREC.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]
baa=epi.baa
un3=un.rolling(63).mean(); sahm=un3-un3.rolling(252).min()     # ~3m avg minus 12m low
cpiy=(cpi/cpi.shift(252)-1)*100
ret1=n.pct_change(); rv=ret1.rolling(20).std()*np.sqrt(252)*100
SEC=['XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB']
ma50={k:A[k].rolling(50).mean() for k in SEC}
E0=pd.read_pickle('episodes.pkl').drop_duplicates('peak',keep='first').reset_index(drop=True)
trigs=[pd.Timestamp(t) for t in E0['T']]
rows=[]
for k,r in E0.iterrows():
    pk,T=pd.Timestamp(r.peak),pd.Timestamp(r['T']); p,t=idx.get_loc(pk),idx.get_loc(T)
    rr=lambda s:(s[T]/s[pk]-1)*100 if pd.notna(s[pk]) and pd.notna(s[T]) else np.nan
    seg=n.iloc[p:t+1]; lows=seg.cummin(); bounce=((seg/lows-1).max())*100
    prev=[x for x in trigs if x<T]
    secr=[rr(A[s]) for s in SEC]
    row=dict(peak=r.peak,
      # path / shape
      maxday=ret1.iloc[p+1:t+1].min()*100, bounce=bounce, downshare=(ret1.iloc[p+1:t+1]<0).mean()*100, rv20=rv[T],
      qvol=(qv.iloc[p+1:t+1].mean()/qv.iloc[max(0,p-50):p].mean()) if pd.notna(qv.iloc[p]) else np.nan,
      # vol structure
      skew=X['SKEW'][pk], term=X['VIX'][T]/X['VIX3M'][T] if pd.notna(X['VIX3M'][T]) else np.nan, vvix=X['VVIX'][T],
      # cycle / policy
      fed6m=(dff[pk]-dff.iloc[p-126])*100, fedlvl=dff[pk], curve_pk=d10[pk]-d3[pk], inv18=float(((d10-d3).iloc[max(0,p-378):p+1]<0).any()),
      d2y=(d2[T]-d2[pk])*100, cpi=cpiy[pk], sahm=sahm[pk], nfci=nfci[pk], dnfci=nfci[T]-nfci[pk], baalvl=baa[pk],
      # context
      since=(t-idx.get_loc(prev[-1])) if prev else np.nan, nprev2y=sum(1 for x in prev if idx.get_loc(x)>=t-504), run3y=(n[pk]/n.iloc[p-756]-1)*100 if p>=756 else np.nan,
      pres=(pk.year%4), month=pk.month,
      # cross-asset
      jpy=rr(A['JPY']), copper=rr(A['COPPER']), wti=rr(wti), gold=rr(A['GOLD']), intl=(rr(A['N225'])+rr(A['DAX']))/2-rr(X['GSPC']), efa=rr(A['EFA'])-rr(A['SPY']), tlt=rr(A['TLT']), btc=rr(A['BTC']),
      # leadership / breadth
      gv=rr(A['IWF'])-rr(A['IWD']), eqw=rr(A['RSP'])-rr(A['SPY']), soft=rr(A['IGV'])-r.depth, sec50=sum(1 for s in SEC if A[s][T]>ma50[s][T]) if pd.notna(A['XLK'][T]) and pd.notna(ma50['XLK'][T]) else np.nan,
      secdisp=np.nanstd(secr) if not np.isnan(secr).all() else np.nan, secup=sum(1 for v in secr if v>0) if not np.isnan(secr).all() else np.nan,
      # outcome label
      rec12=float(rec[(rec.index>=T)&(rec.index<=T+pd.Timedelta(days=365))].max()) if T+pd.Timedelta(days=365)<=rec.index[-1]+pd.Timedelta(days=31) else np.nan)
    rows.append(row)
N=pd.DataFrame(rows); F=E0.merge(N,on='peak'); F.to_pickle('episodes_x.pkl')
pd.set_option('display.width',320); pd.set_option('display.max_columns',60)
print(F[['peak','maxday','bounce','rv20','qvol','skew','fed6m','curve_pk','inv18','sahm','cpi','nfci','since','nprev2y','run3y','pres','jpy','intl','gv','eqw','sec50','secdisp','secup','rec12','more']].round(1).to_string())
