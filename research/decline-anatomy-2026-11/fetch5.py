import re, time, subprocess, io
from curl_cffi import requests as cr
s=cr.Session(impersonate="chrome")
def get(u,fn,**k):
    try:
        r=s.get(u,timeout=40,**k); open('ext/'+fn,'wb').write(r.content); print(fn,r.status_code,len(r.content)); return r
    except Exception as e: print(fn,'ERR',str(e)[:80])
for nm,u in (('pe','s-p-500-pe-ratio'),('cape','shiller-pe'),('eps','s-p-500-earnings'),('epsg','s-p-500-earnings-growth'),('ey','s-p-500-earnings-yield'),('ps','s-p-500-price-to-sales'),('pb','s-p-500-price-to-book')):
    get(f'https://www.multpl.com/{u}/table/by-month',f'multpl_{nm}.html'); time.sleep(0.5)
get('https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv','cboe_total.csv')
get('https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv','cboe_equity.csv')
get('https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpcarchive.csv','cboe_total_arch.csv')
get('https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypcarchive.csv','cboe_equity_arch.csv')
r=get('https://www.aaii.com/files/surveys/sentiment.xls','aaii.xls')
r=get('https://naaim.org/programs/naaim-exposure-index/','naaim.html')
if r is not None:
    links=re.findall(r'href="([^"]+\.xlsx?)"',r.text); print('naaim links',links[:3])
    if links: get(links[0],'naaim.xlsx')
r=get('https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics','finra.html')
if r is not None:
    links=re.findall(r'href="([^"]+margin-statistics[^"]*\.xlsx?)"',r.text); print('finra links',links[:3])
    if links: get(('https://www.finra.org'+links[0]) if links[0].startswith('/') else links[0],'finra.xlsx')
for sid in ('UMCSENT','WRMFNS','MMMFFAQ027S','RMFSL','BOGZ1FA563064105Q','BOGZ1LM153064105Q'):
    out=subprocess.run(['curl','-s','-m','60','-o',f'ext/F_{sid}.csv','-w','%{http_code}',f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'],capture_output=True,text=True).stdout
    try: l=open(f'ext/F_{sid}.csv').read().splitlines(); print(sid,out,len(l),l[1][:24],l[-1][:24])
    except Exception as e: print(sid,out,'ERR')
