import time, os
from curl_cffi import requests as cr
s=cr.Session(impersonate="chrome")
syms={'QQQ':'QQQ','SPY':'SPY','IWM':'IWM','^SOX':'SOX','^VIX':'VIX','^TNX':'TNX','^IRX':'IRX','DX-Y.NYB':'DXY','CL=F':'OIL','GC=F':'GOLD','XLK':'XLK','XLF':'XLF','XLE':'XLE','XLP':'XLP','XLU':'XLU','XLV':'XLV','XLY':'XLY','XLI':'XLI','IWF':'IWF','IWD':'IWD','RSP':'RSP','HYG':'HYG','IEF':'IEF','^IXIC':'IXIC','^NDX':'NDX','^GSPC':'GSPC','^RUT':'RUT'}
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
            print(fn,len(ts),time.strftime('%Y-%m-%d',time.gmtime(ts[0]-4*3600)),time.strftime('%Y-%m-%d',time.gmtime(ts[-1]-4*3600))); break
        except Exception as e:
            time.sleep(3*(a+1)); err=e
    else: print(fn,'FAILED',err)
