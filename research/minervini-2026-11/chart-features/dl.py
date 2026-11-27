import json,yfinance as yf,pandas as pd,os
u=json.load(open('work/universe.json'))+['SPY','QQQ']
u=[t.replace('.','-') for t in u]
out={}
for i in range(0,len(u),200):
    ch=u[i:i+200]
    d=yf.download(ch,start='2015-01-01',progress=False,auto_adjust=True,group_by='ticker',threads=True)
    for t in ch:
        try:
            x=d[t].dropna()
            if len(x)>300: out[t]=x
        except Exception: pass
    print(i,len(out),flush=True)
pd.to_pickle(out,'work/px.pkl')
