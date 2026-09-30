from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request
import json, math, statistics, os

COMMIT="d84a70dd46df011df502217f2737ed08a1e90fa2"
BASE=f"https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/{COMMIT}/chart-data/"
DATA=os.path.join(os.path.dirname(__file__),"..","..","data","stage4-direction-expand.json")

def get_json(url):
    req=Request(url,headers={"User-Agent":"jev-research"})
    with urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def mean(xs): return sum(xs)/len(xs)
def std(xs):
    if len(xs)<2:return None
    m=mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))
def pct(a,b): return (a/b-1)*100 if b else None
def sma(vals,n,i):
    if i-n+1<0:return None
    x=vals[i-n+1:i+1]
    return mean(x) if all(v is not None for v in x) else None
def ret(vals,n,i):
    if i-n<0 or vals[i] is None or vals[i-n] is None:return None
    return pct(vals[i],vals[i-n])
def rsi14(vals,i):
    if i<14:return None
    gains=[]; losses=[]
    for j in range(i-13,i+1):
        if vals[j] is None or vals[j-1] is None:return None
        d=vals[j]-vals[j-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag=mean(gains); al=mean(losses)
    if al==0:return 100.0
    rs=ag/al
    return 100-100/(1+rs)
def corr_beta(xs,ys):
    if len(xs)!=len(ys) or len(xs)<2:return (None,None)
    mx,my=mean(xs),mean(ys)
    vx=sum((x-mx)**2 for x in xs)
    vy=sum((y-my)**2 for y in ys)
    cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    corr=cov/math.sqrt(vx*vy) if vx>0 and vy>0 else None
    beta=cov/vy if vy>0 else None
    return beta,corr

def load_ticker(tk,index):
    sh=index["ticker_to_shard"][tk]
    obj=get_json(BASE+f"shard-{sh:02d}.json")
    rows=obj[tk]
    return rows

def calc(ticker,origin):
    idx=get_json(BASE+"index.json")
    rows=load_ticker(ticker,idx)
    qrows=load_ticker("QQQ",idx)
    def norm(rows):
        out=[]
        for r in rows:
            d=str(r[0])[:10]
            out.append((d,*[float(x) if x is not None else None for x in r[1:6]]))
        return out
    rows=norm(rows); qrows=norm(qrows)
    mp={r[0]:r for r in rows}; qm={r[0]:r for r in qrows}
    dates=[r[0] for r in rows]
    if origin not in mp: raise ValueError("origin_missing")
    i=dates.index(origin)
    sub=rows[:i+1]
    c=[r[4] for r in sub]; o=[r[1] for r in sub]; h=[r[2] for r in sub]; l=[r[3] for r in sub]; v=[r[5] for r in sub]
    last=c[-1]
    out={}
    out["ret1"]=ret(c,1,len(c)-1)
    for n in [5,21,63,126,189]: out[f"ret{n}"]=ret(c,n,len(c)-1)
    for n in [21,50,200]:
        s=sma(c,n,len(c)-1); out[f"dist{n}"]=pct(last,s) if s else None
    # slope candidates
    s_now=sma(c,50,len(c)-1)
    for lag in [5,10,20]:
        s_old=sma(c,50,len(c)-1-lag)
        out[f"slope50_lag{lag}"]=pct(s_now,s_old) if s_now and s_old else None
    rets=[]
    for j in range(max(1,len(c)-20),len(c)):
        if c[j] is None or c[j-1] is None: continue
        rets.append((c[j]/c[j-1]-1)*100)
    out["vol20_simple"]=std(rets)
    adr=[]
    for j in range(max(0,len(c)-20),len(c)):
        if h[j] and l[j]: adr.append((h[j]/l[j]-1)*100)
    out["adr20"]=mean(adr) if adr else None
    for n in [5,10]:
        x=[]
        for j in range(max(0,len(c)-n),len(c)):
            if h[j] and l[j]: x.append((h[j]/l[j]-1)*100)
        out[f"compression_adr{n}_over20"]=(mean(x)/out["adr20"]) if x and out["adr20"] else None
    out["rsi14_simple"]=rsi14(c,len(c)-1)
    for n in [63,252]:
        if len(c)>=n:
            mx=max(x for x in h[-n:] if x is not None); out[f"dist_high{n}"]=pct(last,mx)
        else: out[f"dist_high{n}"]=None
    vv=[x for x in v[-20:] if x is not None]
    out["volume_ratio"]=v[-1]/mean(vv) if vv else None
    dd=[c[j]*v[j] for j in range(max(0,len(c)-20),len(c)) if c[j] is not None and v[j] is not None]
    med=statistics.median(dd) if dd else None
    out["log_ddv"]=math.log1p(med) if med else None
    out["gap"]=pct(o[-1],c[-2]) if len(c)>1 else None
    out["close_location"]=(c[-1]-l[-1])/(h[-1]-l[-1]) if h[-1] is not None and l[-1] is not None and h[-1]!=l[-1] else None
    out["body_open"]=pct(c[-1],o[-1]) if o[-1] else None
    out["body_prevclose"]=(c[-1]-o[-1])/c[-2]*100 if len(c)>1 and c[-2] else None
    # aligned 63 daily simple returns vs QQQ
    common=[d for d in dates[-65:] if d in qm]
    sr=[]; qr=[]
    for a,b in zip(common[-64:-1],common[-63:]):
        pass
    # build return pairs ending origin
    common=[d for d in dates if d<=origin and d in qm]
    if len(common)>=64:
        common=common[-64:]
        for j in range(1,len(common)):
            a,b=common[j-1],common[j]
            sr.append(mp[b][4]/mp[a][4]-1)
            qr.append(qm[b][4]/qm[a][4]-1)
    beta,corr=corr_beta(sr,qr)
    out["beta63"]=beta; out["corr63"]=corr
    qdates=[r[0] for r in qrows if r[0]<=origin]
    qi=qdates.index(origin) if origin in qdates else -1
    qc=[qm[d][4] for d in qdates]
    qret21=ret(qc,21,qi) if qi>=0 else None
    out["excess21"]=out["ret21"]-qret21 if out["ret21"] is not None and qret21 is not None else None
    return out

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q=parse_qs(urlparse(self.path).query)
            ticker=q.get("ticker",["BLSH"])[0].upper()
            origin=q.get("origin",["2026-08-07"])[0]
            got=calc(ticker,origin)
            expected=None
            with open(DATA,"r",encoding="utf-8") as f:
                data=json.load(f)
            for c in data["cases"]:
                if c["ticker"]==ticker and c["origin"]==origin:
                    expected=dict(zip(data["feature_columns"],c["features"]));break
            payload={"ok":True,"ticker":ticker,"origin":origin,"computed":got,"expected":expected}
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(json.dumps(payload,separators=(",",":")).encode())
        except Exception as e:
            self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(json.dumps({"ok":False,"error":str(e)}).encode())
