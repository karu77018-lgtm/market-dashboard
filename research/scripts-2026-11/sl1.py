import os, subprocess, pandas as pd, numpy as np, x2
res=pd.read_pickle('tqfund.pkl'); P=res['proxy']; idx=P.index
rd=lambda f: pd.read_csv(f,parse_dates=['date']).set_index('date')
q=rd('x_QQQ_full.csv'); t=rd('x_TQQQ.csv')
qh,ql,qc=(q[k].rename('Q') for k in ('high','low','close'))
wvf,fire=x2.vixfix(qh.to_frame(),ql.to_frame(),qc.to_frame()); fire=fire.iloc[:,0].reindex(idx).fillna(False)
a10=x2.atr(qh.to_frame(),ql.to_frame(),qc.to_frame(),10).iloc[:,0]
st,d=x2.supertrend(qh.to_numpy(),ql.to_numpy(),qc.to_numpy(),a10.to_numpy()); stdown=pd.Series(d==1,index=q.index).reindex(idx)
to,tc=t.open.reindex(idx).to_numpy(),t.close.reindex(idx).to_numpy()
def nav(w):
    nav_o=np.ones(len(idx)); nav_c=np.ones(len(idx)); ut=0.0; cash=1.0
    for i in range(1,len(idx)):
        no=ut*to[i]+cash; wt=w[i-1] if not np.isnan(w[i-1]) else 0.0
        ut=wt*no/to[i]; cash=no*(1-wt); nav_o[i]=no; nav_c[i]=ut*tc[i]+cash
    return nav_o,nav_c
def stats(nc):
    e=pd.Series(nc,index=idx)['2015-01-02':]
    c=lambda s:((s.iloc[-1]/s.iloc[0])**(365.25/(s.index[-1]-s.index[0]).days)-1)*100
    return f"枠単体 {c(e):5.1f}% (15-20 {c(e['2015':'2020']):5.1f}% / 21-26 {c(e['2021':'2026']):5.1f}%) DD {((e/e.cummax()-1).min()*100):5.1f}%"
def variant(name,w):
    o,c=nav(w); df=P.copy(); df['w']=w; df['nav_o']=o; df['nav_c']=c
    pd.to_pickle({'proxy':df},'fund_tmp.pkl')
    out=subprocess.run(['python3','runeng3.py'],env={**os.environ,'FUND':'fund_tmp.pkl','NAME':name},capture_output=True,text=True).stdout.strip()
    print(out,'||',stats(c),flush=True)
w0=P.w.to_numpy().copy()
variant('現行TQQQルール',w0)
print('VixFix発火日数(2015-)',int(fire['2015':].sum()))
for N in (10,20,30):
    w=w0.copy(); f=fire.to_numpy(); left=0
    for i in range(len(w)):
        if f[i]: left=N
        if left>0: w[i]=1.0; left-=1
    variant(f'VixFix発火→{N}日TQQQ100%',w)
w=w0.copy(); w[stdown.to_numpy(bool)]=0; variant('QQQスーパートレンド下向き→0%',w)
w=np.where(stdown.to_numpy(bool),np.minimum(w0,0.5),w0); variant('QQQスーパートレンド下向き→最大50%',w)
