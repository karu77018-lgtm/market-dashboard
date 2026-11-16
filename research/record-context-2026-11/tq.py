"""TQQQ-rule sleeve 2014-2026 with the dashboard's own code (scripts/tqqq_rule.py)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0,'/home/claude/md/scripts')
import tqqq_rule as tr
rd=lambda f: pd.read_csv(f,parse_dates=['date']).set_index('date')
q=rd('x_QQQ_full.csv'); t=rd('x_TQQQ.csv'); v=rd('x_VIX.csv'); g=rd('x_GOLD.csv')
hy=pd.read_csv('hy.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; hy=pd.to_numeric(hy,errors='coerce').dropna()
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna()
idx=q.index[q.index>=t.index[0]]
def frame(hy_series):
    f=pd.DataFrame({'qo':q.open,'qh':q.high,'ql':q.low,'qc':q.close,'qv':q.volume}).reindex(idx)
    f['to']=t.open.reindex(idx); f['tc']=t.close.reindex(idx)
    f['vix']=v.close.reindex(idx).ffill(); f['vixh']=v.high.reindex(v.index.union(idx)).ffill().reindex(idx)
    f['hy']=tr.known_before(hy_series,idx); f['gold']=g.close.reindex(idx.union(g.index)).ffill().reindex(idx)
    return f
# full VIX history for sigma levels: big_flags gets vixh on idx only -> pass full-history via monkeypatch
import bottom_alert
_orig=bottom_alert.big_flags
bottom_alert.big_flags=lambda vh,ix: _orig(v.high, ix)
proxy=pd.concat([baa[:hy.index[0]-pd.Timedelta(days=1)]*(hy.iloc[0]/baa.asof(hy.index[0])), hy])
res={}
for nm,h in (('proxy',proxy),('nocap',pd.Series(1.0,index=baa.index))):
    f=frame(h); out,_=tr.compute_frame(f)
    w=pd.Series(out['target'],index=idx); full=pd.Series(out['full'],index=idx)
    # fund NAV: weight decided at close i-1 bought at open i
    to,tc=f.to.to_numpy(),f.tc.to_numpy(); nav_o=np.ones(len(idx)); nav_c=np.ones(len(idx)); ut=0.0; cash=1.0
    for i in range(1,len(idx)):
        no=ut*to[i]+cash; wt=w.iloc[i-1] if not np.isnan(w.iloc[i-1]) else 0.0
        ut=wt*no/to[i]; cash=no*(1-wt); nav_o[i]=no; nav_c[i]=ut*tc[i]+cash
    res[nm]=pd.DataFrame({'w':w,'full':full,'nav_o':nav_o,'nav_c':nav_c,'wide':out['hy_wide']},index=idx)
    e=res[nm].nav_c['2015-01-02':]; yrs=(e.index[-1]-e.index[0]).days/365.25
    print(nm,'fund 2015-: CAGR',round((e.iloc[-1]/e.iloc[0])**(1/yrs)-1,3),'maxDD',round((e/e.cummax()-1).min(),3),'avg weight',round(w['2015':].mean(),2),'wide days%',round(res[nm].wide['2015':].mean()*100,1),'full days',int(full['2015':].sum()))
    for a,b in (('2015','2021'),('2022','2026')):
        e=res[nm].nav_c[a:b]; yrs=(e.index[-1]-e.index[0]).days/365.25; print('   ',a,b,'CAGR',round((e.iloc[-1]/e.iloc[0])**(1/yrs)-1,3),'maxDD',round((e/e.cummax()-1).min(),3))
# overlap check of wide flag: real HY vs BAA-only proxy since 2023-11
fb=frame(baa); ob,_=tr.compute_frame(fb); wb=pd.Series(ob['hy_wide'],index=idx)['2024-02':]; wr=res['proxy'].wide['2024-02':]
print('overlap 2024-02+: wide real',round(wr.mean()*100,1),'% baa-proxy',round(wb.mean()*100,1),'% agree',round((wr==wb).mean()*100,1),'%')
pd.to_pickle(res,'tqfund.pkl')
print('big(大底フル) start dates:',[str(d.date()) for d in res['proxy'].index[(res['proxy'].full==1)&(res['proxy'].full.shift(1)!=1)] if d>=pd.Timestamp('2015-01-01')])
print('latest',res['proxy'].iloc[-1].to_dict())
