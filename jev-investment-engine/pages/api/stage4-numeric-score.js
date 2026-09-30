import frozen from "../../data/jev-5d-frozen-inputs.json";
import marketData from "../../data/stage4-market-bars.json";

const RAW="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data";
let runtimePromise;
async function getRuntime(){if(!runtimePromise)runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();return runtimePromise}
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"jev-5d-numeric-score"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
async function outcomes(){
  const idx=await fetchJson(RAW+"/index.json");
  const qdates=marketData.QQQ.map(z=>new Date(z.t).toISOString().slice(0,10));
  const need=new Map();
  for(const o of frozen.origins){
    const oi=qdates.indexOf(o.origin);if(oi<0||oi+5>=qdates.length)throw new Error("calendar_missing_"+o.origin);
    const future=qdates.slice(oi+1,oi+6);
    for(const c of o.cases){
      const sh=idx.ticker_to_shard[c.ticker];if(!Number.isInteger(sh))continue;
      if(!need.has(sh))need.set(sh,[]);
      need.get(sh).push({origin:o.origin,ticker:c.ticker,group:c.group,future});
    }
  }
  const out=[];
  for(const [sh,items] of need){
    const obj=await fetchJson(RAW+`/shard-${String(sh).padStart(2,"0")}.json`);
    for(const it of items){
      const mp=new Map((obj[it.ticker]||[]).map(r=>[String(r[0]).slice(0,10),r]));
      const a=it.future.map(d=>mp.get(d));if(a.some(x=>!x))continue;
      const entry=Number(a[0][1]),end=Number(a[4][4]);if(!(entry>0)||!(end>0))continue;
      out.push({origin:it.origin,ticker:it.ticker,group:it.group,actual_5d_pct:(end/entry-1)*100});
    }
  }
  return out;
}
const PY=String.raw`
import json, math
F=json.loads(frozen_json); O=json.loads(outcomes_json)
DEV={"2026-08-07","2026-08-14","2026-08-21","2026-08-28"}
HOLD={"2026-09-04","2026-09-14","2026-09-21"}
omap={(r["origin"],r["ticker"]):r for r in O}
rows=[]
for o in F["origins"]:
  for c in o["cases"]:
    z=omap.get((o["origin"],c["ticker"]))
    if not z: continue
    rows.append({"origin":o["origin"],"ticker":c["ticker"],"group":c["group"],"x":c["features"],"actual":float(z["actual_5d_pct"]),"y":1 if float(z["actual_5d_pct"])>0 else 0})
cols=list(rows[0]["x"].keys());dev=[r for r in rows if r["origin"] in DEV];hold=[r for r in rows if r["origin"] in HOLD]
med={};mu={};sig={};usable=[]
for k in cols:
  vals=[float(r["x"][k]) for r in dev if r["x"].get(k) is not None and math.isfinite(float(r["x"][k]))]
  if not vals: continue
  vals.sort();n=len(vals);m=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
  z=[float(r["x"][k]) if r["x"].get(k) is not None and math.isfinite(float(r["x"][k])) else m for r in dev]
  av=sum(z)/len(z);sd=(sum((v-av)**2 for v in z)/len(z))**0.5
  if sd<1e-9: continue
  med[k]=m;mu[k]=av;sig[k]=sd;usable.append(k)
def vec(r):
  z=[]
  for k in usable:
    v=r["x"].get(k);v=float(v) if v is not None and math.isfinite(float(v)) else med[k]
    z.append((v-mu[k])/sig[k])
  return z
def sigmoid(z):
  if z>=0:return 1/(1+math.exp(-min(z,60)))
  e=math.exp(max(z,-60));return e/(1+e)
Y=[r["y"] for r in dev];X=[vec(r) for r in dev];base=sum(Y)/len(Y);b=math.log(max(base,1e-6)/max(1-base,1e-6));w=[0.0]*len(usable)
lr=.05;lam=1.0
for _ in range(1200):
  gb=0.0;gw=[0.0]*len(w)
  for x,y in zip(X,Y):
    p=sigmoid(b+sum(a*z for a,z in zip(w,x)));e=p-y;gb+=e
    for j in range(len(w)):gw[j]+=e*x[j]
  n=len(Y);b-=lr*gb/n
  for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
def pnum(r):return sigmoid(b+sum(a*z for a,z in zip(w,vec(r))))
for r in rows:r["pnum"]=pnum(r);r["pconst"]=base;r["pallup"]=1.0
def metrics(rs,key):
  p=[r[key] for r in rs];y=[r["y"] for r in rs];pred=[v>=.5 for v in p]
  acc=sum(int(a==bool(b)) for a,b in zip(pred,y))/len(rs)
  pos=[i for i,v in enumerate(y) if v==1];neg=[i for i,v in enumerate(y) if v==0]
  tpr=sum(pred[i] for i in pos)/len(pos) if pos else None;tnr=sum(not pred[i] for i in neg)/len(neg) if neg else None
  bal=(tpr+tnr)/2 if tpr is not None and tnr is not None else None
  br=sum((a-b)**2 for a,b in zip(p,y))/len(rs)
  ll=-sum(yy*math.log(max(min(pp,1-1e-12),1e-12))+(1-yy)*math.log(max(min(1-pp,1-1e-12),1e-12)) for pp,yy in zip(p,y))/len(rs)
  return {"n":len(rs),"accuracy":acc,"balanced_accuracy":bal,"brier":br,"logloss":ll,"mean_p":sum(p)/len(p),"up_frequency":sum(y)/len(y)}
def byorigin(rs,key):return {o:metrics([r for r in rs if r["origin"]==o],key) for o in sorted(set(r["origin"] for r in rs))}
def avgret(rs,side):
  z=[r["actual"] for r in rs if (r["pnum"]>=.5)==side]
  return {"n":len(z),"mean_actual_pct":sum(z)/len(z) if z else None,"median_actual_pct":sorted(z)[len(z)//2] if z else None}
out={"version":"jev-5d-strong-stock-v1","development_n":len(dev),"holdout_n":len(hold),"usable_numeric_features":len(usable),"development_up_frequency":base,
"development":{"constant":metrics(dev,"pconst"),"numeric":metrics(dev,"pnum"),"all_up":metrics(dev,"pallup")},
"holdout":{"constant":metrics(hold,"pconst"),"numeric":metrics(hold,"pnum"),"all_up":metrics(hold,"pallup")},
"holdout_by_origin":{"numeric":byorigin(hold,"pnum"),"all_up":byorigin(hold,"pallup")},
"holdout_by_group":{g:{"numeric":metrics([r for r in hold if r["group"]==g],"pnum"),"all_up":metrics([r for r in hold if r["group"]==g],"pallup")} for g in ["leader","hash_control"]},
"holdout_numeric_return_split":{"predicted_up":avgret(hold,True),"predicted_down":avgret(hold,False)},
"holdout_rows":[{"origin":r["origin"],"ticker":r["ticker"],"group":r["group"],"actual_5d_pct":r["actual"],"pnum":r["pnum"]} for r in hold]}
json.dumps(out,allow_nan=False)
`;
export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{const o=await outcomes(),py=await getRuntime();py.globals.set("frozen_json",JSON.stringify(frozen));py.globals.set("outcomes_json",JSON.stringify(o));const v=await py.runPythonAsync(PY);const x=JSON.parse(String(v));if(v?.destroy)v.destroy();return res.status(200).json({ok:true,...x});}
  catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1200)})}
}
