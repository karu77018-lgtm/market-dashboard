import pandas as pd, json, time, concurrent.futures as cf
from curl_cffi import requests as cr
tick=list(pd.read_pickle('close.pkl').columns)
s=cr.Session(impersonate='chrome'); crumb=s.get('https://query2.finance.yahoo.com/v1/test/getcrumb',timeout=20).text
out={}
def one(t):
    for k in range(3):
        try:
            r=s.get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{t}',params={'modules':'assetProfile','crumb':crumb},timeout=20)
            if r.status_code==200:
                a=(r.json()['quoteSummary']['result'] or [{}])[0].get('assetProfile',{})
                return t,(a.get('sector'),a.get('industry'))
            if r.status_code==404: return t,(None,None)
        except Exception: pass
        time.sleep(1+k)
    return t,(None,None)
with cf.ThreadPoolExecutor(6) as ex:
    for i,(t,v) in enumerate(ex.map(one,tick)):
        out[t]=v
        if i%500==0: print(i,flush=True)
json.dump(out,open('industry.json','w')); print('done',sum(1 for v in out.values() if v[1]))
