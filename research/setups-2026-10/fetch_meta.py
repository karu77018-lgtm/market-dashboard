import json, time, random, threading, concurrent.futures as cf
from curl_cffi import requests as cr
syms=[s for s,_ in json.load(open('symbols.json'))]
try: meta=json.load(open('meta.json'))
except Exception: meta={}
local=threading.local()
def sess():
    if not hasattr(local,'s'): local.s=cr.Session(impersonate="chrome")
    return local.s
def one(sym):
    for attempt in range(6):
        try:
            r=sess().get(f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}',params={'range':'5d','interval':'1d'},timeout=20)
            if r.status_code==429: time.sleep(10*(attempt+1)); continue
            if r.status_code==404: return sym,{'err':404}
            j=r.json()['chart']
            if j.get('error'): return sym,{'err':str(j['error'])[:80]}
            m=j['result'][0]['meta']
            return sym,{'first':m.get('firstTradeDate'),'type':m.get('instrumentType'),'ex':m.get('exchangeName'),'px':m.get('regularMarketPrice')}
        except Exception as e:
            time.sleep(3*(attempt+1))
    return sym,{'err':'retry'}
todo=[s for s in syms if s not in meta or meta[s].get('err')=='retry']
print('todo',len(todo),flush=True)
t0=time.time()
with cf.ThreadPoolExecutor(3) as ex:
    for i,(s,m) in enumerate(ex.map(one,todo)):
        meta[s]=m
        if i%300==0:
            json.dump(meta,open('meta.json','w')); print(i,round(time.time()-t0),flush=True)
json.dump(meta,open('meta.json','w'))
print('done',len(meta),round(time.time()-t0),flush=True)
