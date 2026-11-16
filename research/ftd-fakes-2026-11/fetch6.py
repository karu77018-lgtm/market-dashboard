import time
from curl_cffi import requests as cr
s=cr.Session(impersonate="chrome")
for sym,fn in (('QQQ','QQQ'),('SPY','SPY'),('IWM','IWM'),('RSP','RSP'),('^VIX','VIX'),('^VIX3M','VIX3M'),('^GSPC','GSPC'),('^IXIC','IXIC')):
    r=s.get(f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}',params={'period1':0,'period2':int(time.time()),'interval':'1d'},timeout=40); res=r.json()['chart']['result'][0]; q=res['indicators']['quote'][0]
    with open(f'ftd_{fn}.csv','w') as f:
        f.write('date,open,high,low,close,volume\n')
        for i,t in enumerate(res['timestamp']):
            v=[q[k][i] for k in ('open','high','low','close','volume')]
            if v[3] is None or v[2] is None: continue
            f.write(time.strftime('%Y-%m-%d',time.gmtime(t-4*3600))+','+','.join('' if x is None else f'{x:.6g}' for x in v)+'\n')
    print(fn,len(res['timestamp']),time.strftime('%Y-%m-%d',time.gmtime(res['timestamp'][0])),end=' | ')
