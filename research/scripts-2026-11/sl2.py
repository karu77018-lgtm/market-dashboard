import os, subprocess, pandas as pd, numpy as np, x2
res=pd.read_pickle('tqfund.pkl'); P=res['proxy']; idx=P.index
rd=lambda f: pd.read_csv(f,parse_dates=['date']).set_index('date')
q=rd('x_QQQ_full.csv').reindex(idx); t=rd('x_TQQQ.csv').reindex(idx)
qc=q.close; to,tc=t.open.to_numpy(),t.close.to_numpy()
full=P.full.fillna(False).to_numpy(bool); w0=P.w.fillna(0).to_numpy()
def nav(w):
    nav_o=np.ones(len(idx)); nav_c=np.ones(len(idx)); ut=0.0; cash=1.0
    for i in range(1,len(idx)):
        no=ut*to[i]+cash; wt=w[i-1]
        ut=wt*no/to[i]; cash=no*(1-wt); nav_o[i]=no; nav_c[i]=ut*tc[i]+cash
    return nav_o,nav_c
def ratchet(bad,exempt_full=True):
    w=w0.copy()
    for i in range(1,len(w)):
        if bad[i] and not (exempt_full and full[i]) and w[i]>w[i-1]: w[i]=w[i-1]
    return w
def sstats(nc):
    e=pd.Series(nc,index=idx)['2015-01-02':]
    c=lambda s:((s.iloc[-1]/s.iloc[0])**(365.25/(s.index[-1]-s.index[0]).days)-1)*100
    return f"枠単体 {c(e):5.1f}% ({c(e['2015':'2020']):5.1f}/{c(e['2021':'2026']):5.1f}) DD {((e/e.cummax()-1).min()*100):5.1f}%"
def go(name,w,reg=None):
    o,c=nav(w); df=P.copy(); df['w']=w; df['nav_o']=o; df['nav_c']=c
    pd.to_pickle({'proxy':df},'fund_tmp.pkl'); env={**os.environ,'FUND':'fund_tmp.pkl','NAME':name}
    if reg is not None: pd.to_pickle(reg,'reg_tmp.pkl'); env['REG']='reg_tmp.pkl'
    out=subprocess.run(['python3','runall.py'],env=env,capture_output=True,text=True)
    print((out.stdout.strip() or out.stderr[-300:]),'||',sstats(c),flush=True)
# bad-market definitions
ma50=qc.rolling(50).mean(); e21=qc.ewm(span=21,adjust=False).mean(); hi=qc.rolling(252,min_periods=200).max()
sp=(rd('x_SPHB.csv').close/rd('x_SPLV.csv').close).reindex(idx); vt=(rd('x_VIX.csv').close/rd('x_VIX3M.csv').close).reindex(idx)
B={'50日線の下':qc<ma50,'21EMAの下':qc<e21,'21EMAの下かつ21EMA下向き':(qc<e21)&(e21<e21.shift(5)),
   '50日線下向き':ma50<ma50.shift(5),'50日線の下かつ下向き':(qc<ma50)&(ma50<ma50.shift(5)),
   '高値から−8%以上':qc/hi-1<=-0.08,'高値から−10%以上':qc/hi-1<=-0.10,
   'SPHB/SPLV 20日−4%':sp/sp.shift(20)-1<=-0.04,'VIX/VIX3M≥1':vt>=1.0}
if __name__=='__main__':
    go('現行',w0)
    for k,b in B.items():
        go('増やさない: '+k, ratchet(b.fillna(False).to_numpy(bool)))
