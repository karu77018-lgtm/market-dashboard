import time, subprocess
from curl_cffi import requests as cr
s=cr.Session(impersonate="chrome")
syms={'^SKEW':'SKEW','^VIX3M':'VIX3M','^VVIX':'VVIX','JPY=X':'JPY','HG=F':'COPPER','EFA':'EFA','EEM':'EEM','^N225':'N225','^GDAXI':'DAX','QQEW':'QQEW','IGV':'IGV','SMH':'SMH','BTC-USD':'BTC','TLT':'TLT','XLB':'XLB','XLRE':'XLRE','XLC':'XLC'}
for sym,fn in syms.items():
    for a in range(4):
        try:
            r=s.get(f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}',params={'period1':0,'period2':int(time.time()),'interval':'1d'},timeout=30)
            res=r.json()['chart']['result'][0]; ts=res['timestamp']; q=res['indicators']['quote'][0]; adj=res['indicators'].get('adjclose',[{}])[0].get('adjclose')
            with open(f'macro/{fn}.csv','w') as f:
                f.write('date,close,adj\n')
                for i,t in enumerate(ts):
                    if q['close'][i] is None: continue
                    f.write(time.strftime('%Y-%m-%d',time.gmtime(t-4*3600))+f",{q['close'][i]:.6g},{(adj[i] if adj and adj[i] is not None else q['close'][i]):.6g}\n")
            print(fn,time.strftime('%Y-%m-%d',time.gmtime(ts[0])),end='; '); break
        except Exception as e: time.sleep(3*(a+1))
    else: print(fn,'FAILED',end='; ')
# QQQ with volume, full history
r=s.get('https://query2.finance.yahoo.com/v8/finance/chart/QQQ',params={'period1':0,'period2':int(time.time()),'interval':'1d'},timeout=30); res=r.json()['chart']['result'][0]; q=res['indicators']['quote'][0]
with open('macro/QQQV.csv','w') as f:
    f.write('date,close,adj\n')
    for i,t in enumerate(res['timestamp']):
        if q['volume'][i]: f.write(time.strftime('%Y-%m-%d',time.gmtime(t-4*3600))+f",{q['volume'][i]},{q['volume'][i]}\n")
print()
for sid in ('DFF','UNRATE','CPIAUCSL','NFCI','DCOILWTICO','DGS2','USREC','DGS10','DTB3'):
    out=subprocess.run(['curl','-s','-m','40','-o',f'macro/F_{sid}.csv','-w','%{http_code}',f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'],capture_output=True,text=True).stdout
    l=open(f'macro/F_{sid}.csv').read().splitlines(); print(sid,out,len(l),l[1][:22],l[-1][:22],end=' | ')
