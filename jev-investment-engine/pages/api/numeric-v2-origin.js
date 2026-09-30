import marketData from "../../data/stage4-market-bars.json";
import expectedData from "../../data/stage4-direction-expand.json";

let runtimePromise;
async function getRuntime(){
  if(!runtimePromise){
    runtimePromise=(async()=>{
      const { loadPyodide } = await import("pyodide");
      return await loadPyodide();
    })();
  }
  return runtimePromise;
}
export const config={maxDuration:120};

async function fetchJson(url){
  const r=await fetch(url,{headers:{"User-Agent":"jev-research"}});
  if(!r.ok) throw new Error("FETCH_"+r.status+"_"+url);
  return await r.json();
}
async function fetchText(url){
  const r=await fetch(url,{headers:{"User-Agent":"jev-research"}});
  if(!r.ok) throw new Error("FETCH_"+r.status+"_"+url);
  return await r.text();
}

const PY = String.raw`
import json, math, statistics, hashlib, csv, io
from datetime import datetime, timezone

U=json.loads(universe_json)
M=json.loads(market_json)
E=json.loads(expected_json)
fred_text=fred_csv_text
ORIGINS=[requested_origin]
FEATURES=E["feature_columns"]

def mean(x): return sum(x)/len(x)
def samplestd(x):
    if len(x)<2:return None
    m=mean(x);return math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
def pct(a,b): return (a/b-1)*100 if b not in (None,0) else None
def sma(x,n,i):
    if i-n+1<0:return None
    z=x[i-n+1:i+1]
    return mean(z) if len(z)==n else None
def ret(x,n,i):
    if i-n<0:return None
    return pct(x[i],x[i-n])
def wilder_rsi(c,i,n=14):
    if i<n:return None
    d=[c[j]-c[j-1] for j in range(1,i+1)]
    if len(d)<n:return None
    ag=mean([max(x,0) for x in d[:n]]);al=mean([max(-x,0) for x in d[:n]])
    for x in d[n:]:
        ag=(ag*(n-1)+max(x,0))/n
        al=(al*(n-1)+max(-x,0))/n
    return 100.0 if al==0 else 100-100/(1+ag/al)
def avg_rank_pct(vals):
    items=sorted((v,k) for k,v in vals.items() if v is not None and math.isfinite(v))
    n=len(items); out={}; p=0
    while p<n:
        q=p+1
        while q<n and items[q][0]==items[p][0]: q+=1
        avg_rank=((p+1)+q)/2.0
        rank=100.0*avg_rank/n
        for j in range(p,q):out[items[j][1]]=rank
        p=q
    return out

def normalize_rows(rows):
    out=[]
    for r in rows:
        try:
            d=str(r[0])[:10]
            out.append((d,float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5])))
        except: pass
    return out

SER={k:normalize_rows(v) for k,v in U.items()}
# Massive market data
MARKET={}
for k,arr in M.items():
    rr=[]
    for z in arr:
        d=datetime.fromtimestamp(float(z["t"])/1000,timezone.utc).date().isoformat()
        rr.append((d,float(z["o"]),float(z["h"]),float(z["l"]),float(z["c"]),float(z["v"])))
    MARKET[k]=rr

# FRED VIXCLS,DGS10
FRED={"VIXCLS":{},"DGS10":{}}
reader=csv.DictReader([line for line in fred_text.replace(chr(13),"").split(chr(10)) if line.strip()])
for row in reader:
    d=row.get("DATE") or row.get("observation_date")
    if not d: continue
    for key in ["VIXCLS","DGS10"]:
        v=row.get(key)
        try:FRED[key][d]=float(v)
        except:pass

def context(rows,origin):
    dates=[r[0] for r in rows]
    if origin not in dates:return None
    i=dates.index(origin)
    sub=rows[:i+1]
    if len(sub)<21:return None
    o=[r[1] for r in sub];h=[r[2] for r in sub];l=[r[3] for r in sub];c=[r[4] for r in sub];v=[r[5] for r in sub]
    return dates,i,o,h,l,c,v

def basic_at(rows,origin):
    z=context(rows,origin)
    if not z:return None
    dates,i,o,h,l,c,v=z;i=len(c)-1
    s50=sma(c,50,i);s200=sma(c,200,i)
    ddv=None
    if len(c)>=20:
        ddv=statistics.median([c[j]*v[j] for j in range(i-19,i+1)])
    return {
      "close":c[i],"sma50":s50,"sma200":s200,"ddv20":ddv,
      "ret63":ret(c,63,i),"ret189":ret(c,189,i),
      "above50":(c[i]>s50) if s50 else None,
      "above200":(c[i]>s200) if s200 else None
    }

def market_feature(rows,origin,prefix):
    z=context(rows,origin)
    if not z:return {}
    dates,_,o,h,l,c,v=z;i=len(c)-1
    out={}
    for n in [5,21,63]:out[prefix+"_ret"+str(n)]=ret(c,n,i)
    s50=sma(c,50,i);out[prefix+"_dist50"]=pct(c[i],s50) if s50 else None
    if i>=20:
        rr=[(c[j]/c[j-1]-1)*100 for j in range(i-19,i+1)]
        out[prefix+"_vol20"]=samplestd(rr)
    else:out[prefix+"_vol20"]=None
    return out

def fred_pair(key,origin):
    dates=sorted(d for d in FRED[key] if d<=origin)
    if not dates:return (None,None)
    last=dates[-1]; val=FRED[key][last]
    ch=val-FRED[key][dates[-21]] if len(dates)>=21 else None
    return val,ch

def stock_features(tk,origin,rank63,rank189,b50,b200,b50chg,nhnl):
    rows=SER[tk];z=context(rows,origin)
    if not z:return None
    dates,_,o,h,l,c,v=z;i=len(c)-1
    if i<20:return None
    x={}
    for n in [1,5,21,63,126,189]:x["ret"+str(n)]=ret(c,n,i)
    for n in [21,50,200]:
        s=sma(c,n,i);x["dist"+str(n)]=pct(c[i],s) if s else None
    s0=sma(c,50,i);s10=sma(c,50,i-10)
    x["slope50"]=pct(s0,s10) if s0 and s10 else None
    rr=[(c[j]/c[j-1]-1)*100 for j in range(i-19,i+1)]
    x["vol20"]=samplestd(rr)
    adr=[(h[j]/l[j]-1)*100 for j in range(i-19,i+1)]
    x["adr20"]=mean(adr)
    x["compression"]=mean(adr[-5:])/mean(adr) if mean(adr) else None
    x["rsi14"]=wilder_rsi(c,i)
    x["dist_high63"]=pct(c[i],max(h[-63:])) if len(h)>=63 else None
    x["dist_high252"]=pct(c[i],max(h[-252:])) if len(h)>=252 else None
    x["volume_ratio"]=v[i]/mean(v[-20:]) if mean(v[-20:]) else None
    x["log_ddv"]=math.log1p(statistics.median([c[j]*v[j] for j in range(i-19,i+1)]))
    x["gap"]=pct(o[i],c[i-1])
    x["close_location"]=(c[i]-l[i])/(h[i]-l[i]) if h[i]!=l[i] else None
    x["body"]=pct(c[i],o[i])
    x["rs63"]=rank63.get(tk);x["rs189"]=rank189.get(tk)
    for key in ["QQQ","SPY","IWM","HYG","IEF"]:
        x.update(market_feature(MARKET[key],origin,key))
    vix,vixchg=fred_pair("VIXCLS",origin);tnx,tnxchg=fred_pair("DGS10",origin)
    x["^VIX_level"]=vix;x["^VIX_change20"]=vixchg
    x["^TNX_level"]=tnx;x["^TNX_change20"]=tnxchg
    x["breadth50"]=b50;x["breadth200"]=b200;x["breadth50_change20"]=b50chg;x["nhnl252"]=nhnl
    # beta/corr 63 aligned to QQQ
    qmap={r[0]:r[4] for r in MARKET["QQQ"]}
    smap={r[0]:r[4] for r in rows if r[0]<=origin}
    common=sorted(set(smap).intersection(qmap))
    common=[d for d in common if d<=origin]
    if len(common)>=64:
        common=common[-64:];sr=[];qr=[]
        for a,b in zip(common[:-1],common[1:]):
            sr.append(smap[b]/smap[a]-1);qr.append(qmap[b]/qmap[a]-1)
        ms,mq=mean(sr),mean(qr)
        cov=sum((a-ms)*(b-mq) for a,b in zip(sr,qr));vs=sum((a-ms)**2 for a in sr);vq=sum((b-mq)**2 for b in qr)
        x["beta63"]=cov/vq if vq else None;x["corr63"]=cov/math.sqrt(vs*vq) if vs and vq else None
    else:x["beta63"]=None;x["corr63"]=None
    qdates=sorted(d for d in qmap if d<=origin)
    if origin in qdates and qdates.index(origin)>=21:
        qi=qdates.index(origin);qret=(qmap[origin]/qmap[qdates[qi-21]]-1)*100
        x["excess21"]=x["ret21"]-qret if x["ret21"] is not None else None
    else:x["excess21"]=None
    return x

def breadth(origin):
    vals=[]
    for tk,rows in SER.items():
        b=basic_at(rows,origin)
        if b: vals.append(b)
    d50=sum(1 for b in vals if b["above50"] is not None);d200=sum(1 for b in vals if b["above200"] is not None)
    b50=100*sum(1 for b in vals if b["above50"] is True)/d50 if d50 else None
    b200=100*sum(1 for b in vals if b["above200"] is True)/d200 if d200 else None
    return b50,b200,len(vals)

# previous breadth date 20 QQQ sessions ago
qdates=[r[0] for r in MARKET["QQQ"]]
results=[]; summaries=[]
for origin in ORIGINS:
    basics={tk:basic_at(rows,origin) for tk,rows in SER.items()}
    basics={tk:b for tk,b in basics.items() if b}
    r63=avg_rank_pct({tk:b["ret63"] for tk,b in basics.items() if b["ret63"] is not None})
    r189=avg_rank_pct({tk:b["ret189"] for tk,b in basics.items() if b["ret189"] is not None})
    d50=sum(1 for b in basics.values() if b["above50"] is not None);d200=sum(1 for b in basics.values() if b["above200"] is not None)
    b50=100*sum(1 for b in basics.values() if b["above50"] is True)/d50 if d50 else None
    b200=100*sum(1 for b in basics.values() if b["above200"] is True)/d200 if d200 else None
    b50chg=None
    if origin in qdates:
        qi=qdates.index(origin)
        if qi>=20:
            old=qdates[qi-20];ob50,_,_=breadth(old);b50chg=(b50-ob50) if b50 is not None and ob50 is not None else None
    # 252-day new-high minus new-low percentage, only where full history exists
    hi=lo=den=0
    for tk,rows in SER.items():
        z=context(rows,origin)
        if not z:continue
        dates,_,o,h,l,c,v=z;i=len(c)-1
        if len(c)>=252:
            den+=1
            if c[i]>=max(c[-252:]):hi+=1
            if c[i]<=min(c[-252:]):lo+=1
    nhnl=100*(hi-lo)/den if den else None
    eligible=[]
    for tk,b in basics.items():
        if b["close"]<5 or b["ddv20"] is None or b["ddv20"]<10000000:continue
        if b["sma50"] is None or b["sma200"] is None or not (b["sma50"]>b["sma200"] and b["close"]>b["sma200"]):continue
        if r63.get(tk,0)<85 or r189.get(tk,0)<85:continue
        eligible.append(tk)
    leaders=sorted(eligible,key=lambda t:(-r189.get(t,0),-r63.get(t,0),t))[:15]
    leadset=set(leaders)
    remaining=[t for t in eligible if t not in leadset]
    controls=sorted(remaining,key=lambda t:hashlib.sha256((origin+"|"+t+"|numeric-v2").encode()).hexdigest())[:15]
    chosen=[(t,"leader") for t in leaders]+[(t,"hash_control") for t in controls]
    for tk,group in chosen:
        feat=stock_features(tk,origin,r63,r189,b50,b200,b50chg,nhnl)
        rows=SER[tk];dates=[r[0] for r in rows]
        oi=dates.index(origin);future=rows[oi+1:oi+6]
        if len(future)<5:continue
        actual=(future[-1][4]/future[0][1]-1)*100
        results.append({"origin":origin,"ticker":tk,"group":group,"features":{k:feat.get(k) for k in FEATURES},"actual_5d_pct":actual})
    summaries.append({"origin":origin,"universe":len(basics),"eligible":len(eligible),"selected":len(chosen),"leaders":len(leaders),"controls":len(controls),"breadth50":b50,"breadth200":b200,"breadth50_change20":b50chg,"nhnl252":nhnl})

json.dumps({"version":"numeric-v2-origin-v1","feature_columns":FEATURES,"origin":requested_origin,"summary":summaries[0] if summaries else None,"cases":results},allow_nan=False)
`;

export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
    const shards=await Promise.all(Array.from({length:32},(_,i)=>fetchJson(base+`shard-${String(i).padStart(2,"0")}.json`)));
    const universe=Object.assign({},...shards);
    const fred=await fetchText("https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS,DGS10");
    const py=await getRuntime();
    const requested=String(req.query.origin||"");
    const allowed=new Set(["2026-07-10","2026-07-17","2026-07-24","2026-07-31","2026-08-07","2026-08-14","2026-08-21","2026-08-28","2026-09-04","2026-09-14","2026-09-21"]);
    if(!allowed.has(requested)) return res.status(400).json({ok:false,error:"invalid_origin"});
    py.globals.set("requested_origin",requested);
    py.globals.set("universe_json",JSON.stringify(universe));
    py.globals.set("market_json",JSON.stringify(marketData));
    py.globals.set("expected_json",JSON.stringify(expectedData));
    py.globals.set("fred_csv_text",fred);
    const val=await py.runPythonAsync(PY);
    const obj=JSON.parse(String(val));
    if(val?.destroy) val.destroy();
    return res.status(200).json({ok:true,...obj});
  }catch(e){
    return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)});
  }
}