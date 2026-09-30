import casesData from "../../data/stage4-direction-expand.json";
import marketData from "../../data/stage4-market-bars.json";

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
export const config={maxDuration:60};

async function fetchJson(url){
  const r=await fetch(url,{headers:{"User-Agent":"jev-research"}});
  if(!r.ok) throw new Error("FETCH_"+r.status);
  return await r.json();
}

const PY = String.raw`
import json, math, statistics
rows=json.loads(stock_rows_json)
qrows=json.loads(qqq_rows_json)
origin=origin_str

def mean(x): return sum(x)/len(x)
def popstd(x):
    m=mean(x); return math.sqrt(sum((v-m)**2 for v in x)/len(x))
def samplestd(x):
    m=mean(x); return math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
def pct(a,b): return (a/b-1)*100 if b else None
def sma(x,n,i):
    if i-n+1<0:return None
    z=x[i-n+1:i+1]
    return mean(z)
def ret(x,n,i):
    if i-n<0:return None
    return pct(x[i],x[i-n])

rows=[r for r in rows if str(r[0])[:10] <= origin]
dates=[str(r[0])[:10] for r in rows]
i=dates.index(origin)
rows=rows[:i+1]
o=[float(r[1]) for r in rows]; h=[float(r[2]) for r in rows]; l=[float(r[3]) for r in rows]; c=[float(r[4]) for r in rows]; v=[float(r[5]) for r in rows]
i=len(c)-1
out={}
for n in [1,5,21,63,126,189]:out["ret"+str(n)]=ret(c,n,i)
for n in [21,50,200]:
    s=sma(c,n,i);out["dist"+str(n)]=pct(c[i],s) if s else None
s0=sma(c,50,i)
for lag in [1,5,10,20]:
    ss=sma(c,50,i-lag)
    out["slope50_change_"+str(lag)]=pct(s0,ss) if s0 and ss else None
# linear regression slope of 50SMA over windows, normalized by current SMA
for win in [5,10,20]:
    vals=[sma(c,50,j) for j in range(i-win+1,i+1)]
    if all(x is not None for x in vals):
        mx=(win-1)/2; my=mean(vals)
        b=sum((x-mx)*(y-my) for x,y in zip(range(win),vals))/sum((x-mx)**2 for x in range(win))
        out["slope50_lr_"+str(win)]=b/s0*100
rets=[(c[j]/c[j-1]-1)*100 for j in range(i-19,i+1)]
logrets=[math.log(c[j]/c[j-1])*100 for j in range(i-19,i+1)]
out["vol20_pop_simple"]=popstd(rets);out["vol20_sample_simple"]=samplestd(rets)
out["vol20_pop_log"]=popstd(logrets);out["vol20_sample_log"]=samplestd(logrets)
adr_hl=[(h[j]/l[j]-1)*100 for j in range(i-19,i+1)]
adr_pc=[(h[j]-l[j])/c[j-1]*100 for j in range(i-19,i+1)]
tr=[]
for j in range(i-19,i+1):
    tr.append(max(h[j]-l[j],abs(h[j]-c[j-1]),abs(l[j]-c[j-1]))/c[j-1]*100)
out["adr20_hl"]=mean(adr_hl);out["adr20_prevclose"]=mean(adr_pc);out["atr20_pct"]=mean(tr)
for n in [3,5,10]:
    x=adr_hl[-n:]
    out["compression_adr"+str(n)+"_over20"]=mean(x)/mean(adr_hl)
    out["compression_range"+str(n)+"_over20"]=mean(x)/mean(adr_hl)
out["compression_vol_over_adr"]=out["vol20_pop_simple"]/mean(adr_hl)
# RSI rolling simple
d=[c[j]-c[j-1] for j in range(1,len(c))]
last=d[-14:]
g=mean([max(x,0) for x in last]);loss=mean([max(-x,0) for x in last])
out["rsi14_simple"]=100 if loss==0 else 100-100/(1+g/loss)
# Wilder RSI: seed first 14 then recurse
if len(d)>=14:
    ag=mean([max(x,0) for x in d[:14]]);al=mean([max(-x,0) for x in d[:14]])
    for x in d[14:]:
        ag=(ag*13+max(x,0))/14
        al=(al*13+max(-x,0))/14
    out["rsi14_wilder"]=100 if al==0 else 100-100/(1+ag/al)
for n in [63,252]:
    out["dist_high"+str(n)]=pct(c[i],max(h[-n:])) if len(h)>=n else None
out["volume_ratio_inc20"]=v[i]/mean(v[-20:])
out["volume_ratio_prev20"]=v[i]/mean(v[-21:-1]) if len(v)>=21 else None
dd=[c[j]*v[j] for j in range(i-19,i+1)]
out["log_ddv_median20"]=math.log1p(statistics.median(dd))
out["log_ddv_mean20"]=math.log1p(mean(dd))
out["gap"]=pct(o[i],c[i-1])
out["close_location"]=(c[i]-l[i])/(h[i]-l[i]) if h[i]!=l[i] else None
out["body_open_pct"]=pct(c[i],o[i])
out["body_prevclose_pct"]=(c[i]-o[i])/c[i-1]*100
# QQQ aligned from fixed Massive market bars
from datetime import datetime, timezone
qm={}
for z in qrows:
    dte=datetime.fromtimestamp(z["t"]/1000,timezone.utc).date().isoformat()
    qm[dte]=float(z["c"])
common=[d for d in dates if d<=origin and d in qm]
if len(common)>=64:
    cr=[]; qr=[]
    mp={str(r[0])[:10]:float(r[4]) for r in rows}
    common=common[-64:]
    for a,b in zip(common[:-1],common[1:]):
        cr.append(mp[b]/mp[a]-1);qr.append(qm[b]/qm[a]-1)
    mc=mean(cr);mq=mean(qr)
    cov=sum((x-mc)*(y-mq) for x,y in zip(cr,qr))
    vx=sum((x-mc)**2 for x in cr);vy=sum((y-mq)**2 for y in qr)
    out["beta63"]=cov/vy if vy else None
    out["corr63"]=cov/math.sqrt(vx*vy) if vx and vy else None
# qqq 21 return
qd=sorted([d for d in qm if d<=origin])
if origin in qd:
    qi=qd.index(origin)
    if qi>=21:
        qret=(qm[origin]/qm[qd[qi-21]]-1)*100
        out["excess21"]=out["ret21"]-qret
json.dumps(out,allow_nan=False)
`;

export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  const ticker=String(req.query.ticker||"BLSH").toUpperCase();
  const origin=String(req.query.origin||"2026-08-07");
  try{
    const idx=await fetchJson("https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/index.json");
    const sh=idx.ticker_to_shard[ticker];
    if(sh===undefined) return res.status(404).json({ok:false,error:"ticker_not_found"});
    const shard=await fetchJson(`https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/shard-${String(sh).padStart(2,"0")}.json`);
    const rows=shard[ticker];
    const expCase=casesData.cases.find(x=>x.ticker===ticker&&x.origin===origin);
    const expected=expCase?Object.fromEntries(casesData.feature_columns.map((k,i)=>[k,expCase.features[i]])):null;
    const py=await getRuntime();
    py.globals.set("stock_rows_json",JSON.stringify(rows));
    py.globals.set("qqq_rows_json",JSON.stringify(marketData.QQQ));
    py.globals.set("origin_str",origin);
    const val=py.runPython(PY);
    const computed=JSON.parse(String(val));
    if(val?.destroy) val.destroy();
    return res.status(200).json({ok:true,ticker,origin,row_count:rows.length,computed,expected});
  }catch(e){
    return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1200)});
  }
}
