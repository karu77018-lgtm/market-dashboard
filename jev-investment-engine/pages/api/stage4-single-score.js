import frozen from "../../data/jev-5d-frozen-inputs.json";
import marketData from "../../data/stage4-market-bars.json";
import r0807 from "../../data/jev-5d-single-results/2026-08-07.json";
import r0814 from "../../data/jev-5d-single-results/2026-08-14.json";
import r0821 from "../../data/jev-5d-single-results/2026-08-21.json";
import r0828 from "../../data/jev-5d-single-results/2026-08-28.json";
import r0904 from "../../data/jev-5d-single-results/2026-09-04.json";
import r0914 from "../../data/jev-5d-single-results/2026-09-14.json";
import r0921 from "../../data/jev-5d-single-results/2026-09-21.json";

const singleResults=[r0807,r0814,r0821,r0828,r0904,r0914,r0921];
const RAW="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data";
let runtimePromise;
async function getRuntime(){if(!runtimePromise)runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();return runtimePromise}
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"jev-5d-single-score"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
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
import json,math,statistics
F=json.loads(frozen_json); J=json.loads(single_json); O=json.loads(outcomes_json)
DEV={"2026-08-07","2026-08-14","2026-08-21","2026-08-28"}
HOLD={"2026-09-04","2026-09-14","2026-09-21"}
omap={(r["origin"],r["ticker"]):r for r in O}
fmap={}
for o in F["origins"]:
  for c in o["cases"]: fmap[(o["origin"],c["ticker"])]=c
jmap={}
for o in J:
  for r in o["rows"]:
    if r.get("ok"): jmap[(o["origin"],r["ticker"])]=r
rows=[]
for key,c in fmap.items():
  z=omap.get(key); j=jmap.get(key)
  if not z or not j: continue
  rows.append({"origin":key[0],"ticker":key[1],"group":c["group"],"x":c["features"],"actual":float(z["actual_5d_pct"]),"y":1 if float(z["actual_5d_pct"])>0 else 0,"pjev":float(j["p_up"]),"run_std":float(j.get("run_std",0))})
if len(rows)!=140: raise Exception("ROW_COUNT_"+str(len(rows)))
cols=list(rows[0]["x"].keys()); dev=[r for r in rows if r["origin"] in DEV]; hold=[r for r in rows if r["origin"] in HOLD]
if len(dev)!=80 or len(hold)!=60: raise Exception("SPLIT_COUNT")
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
    for jj in range(len(w)):gw[jj]+=e*x[jj]
  n=len(Y);b-=lr*gb/n
  for jj in range(len(w)):w[jj]-=lr*(gw[jj]/n+lam*w[jj]/n)
def pnum(r): return sigmoid(b+sum(a*z for a,z in zip(w,vec(r))))
for r in rows:
  r["pnum"]=pnum(r); r["pconst"]=base
def br(rs,key): return sum((r[key]-r["y"])**2 for r in rs)/len(rs)
alphas=[0,.25,.5,.75,1]
a=min(alphas,key=lambda x:sum(((.5+x*(r["pjev"]-.5))-r["y"])**2 for r in dev)/len(dev))
for r in rows:r["pjev_cal"]=.5+a*(r["pjev"]-.5)
weights=[0,.25,.5,.75,1]
hw=min(weights,key=lambda z:sum(((z*r["pjev_cal"]+(1-z)*r["pnum"])-r["y"])**2 for r in dev)/len(dev))
for r in rows:r["phybrid"]=hw*r["pjev_cal"]+(1-hw)*r["pnum"]
# Challenger gate chosen ONLY on development Brier.
conf_grid=[0,.05,.1,.15,.2,.25,.3]; std_grid=[.03,.05,.08,.12,.2,1]
cand=[]
for cf in conf_grid:
  for st in std_grid:
    vals=[]
    overrides=0
    for r in dev:
      disagree=(r["pjev_cal"]>=.5)!=(r["pnum"]>=.5)
      use=disagree and abs(r["pjev_cal"]-.5)>=cf and r["run_std"]<=st
      p=r["pjev_cal"] if use else r["pnum"]; vals.append((p-r["y"])**2); overrides+=int(use)
    cand.append((sum(vals)/len(vals),overrides/len(dev),cf,st))
best=min(cand,key=lambda z:(z[0],z[1],z[2],z[3]))
gate_conf,gate_std=best[2],best[3]
for r in rows:
  disagree=(r["pjev_cal"]>=.5)!=(r["pnum"]>=.5)
  use=disagree and abs(r["pjev_cal"]-.5)>=gate_conf and r["run_std"]<=gate_std
  r["override"]=bool(use);r["pchallenger"]=r["pjev_cal"] if use else r["pnum"]
def metrics(rs,key):
  if not rs:return {"n":0}
  y=[r["y"] for r in rs];p=[r[key] for r in rs];pred=[x>=.5 for x in p]
  acc=sum(int(a==bool(b)) for a,b in zip(pred,y))/len(rs)
  pos=[i for i,v in enumerate(y) if v==1];neg=[i for i,v in enumerate(y) if v==0]
  tpr=sum(pred[i] for i in pos)/len(pos) if pos else None;tnr=sum(not pred[i] for i in neg)/len(neg) if neg else None
  bal=(tpr+tnr)/2 if tpr is not None and tnr is not None else None
  brier=sum((aa-bb)**2 for aa,bb in zip(p,y))/len(rs)
  ll=-sum(bb*math.log(max(min(aa,1-1e-12),1e-12))+(1-bb)*math.log(max(min(1-aa,1-1e-12),1e-12)) for aa,bb in zip(p,y))/len(rs)
  return {"n":len(rs),"accuracy":acc,"balanced_accuracy":bal,"brier":brier,"logloss":ll,"mean_p":sum(p)/len(p),"up_frequency":sum(y)/len(y)}
def byorigin(rs,key):return {o:metrics([r for r in rs if r["origin"]==o],key) for o in sorted(set(r["origin"] for r in rs))}
def mcnemar(rs,ka,kb):
  aa=bb=0
  for r in rs:
    ca=((r[ka]>=.5)==bool(r["y"]));cb=((r[kb]>=.5)==bool(r["y"]))
    if ca and not cb:aa+=1
    elif cb and not ca:bb+=1
  n=aa+bb
  if n==0:p=1.0
  else:
    k=min(aa,bb);tail=sum(math.comb(n,i) for i in range(k+1))/(2**n);p=min(1.0,2*tail)
  return {"a_correct_b_wrong":aa,"a_wrong_b_correct":bb,"discordant":n,"exact_p":p}
keys=["pconst","pnum","pjev","pjev_cal","phybrid","pchallenger"]
def std_bucket(rs):
  med=statistics.median([r["run_std"] for r in rs])
  return {"median_run_std":med,"low_std_jev":metrics([r for r in rs if r["run_std"]<=med],"pjev"),"high_std_jev":metrics([r for r in rs if r["run_std"]>med],"pjev"),"gt_0_10_n":sum(r["run_std"]>.10 for r in rs)}
out={
 "version":"jev-5d-strong-stock-v1-single-case-score",
 "development_n":len(dev),"holdout_n":len(hold),"usable_numeric_features":len(usable),"development_up_frequency":base,
 "selected_jev_shrinkage":a,"selected_hybrid_jev_weight":hw,
 "selected_challenger_gate":{"confidence_from_half":gate_conf,"max_run_std":gate_std,"development_brier":best[0],"development_override_rate":best[1]},
 "development":{k:metrics(dev,k) for k in keys},
 "holdout":{k:metrics(hold,k) for k in keys},
 "holdout_by_origin":{k:byorigin(hold,k) for k in keys},
 "holdout_by_group":{g:{k:metrics([r for r in hold if r["group"]==g],k) for k in keys} for g in ["leader","hash_control"]},
 "holdout_run_stability":std_bucket(hold),
 "holdout_override_count":sum(r["override"] for r in hold),
 "mcnemar_holdout":{"jev_vs_numeric":mcnemar(hold,"pjev","pnum"),"challenger_vs_numeric":mcnemar(hold,"pchallenger","pnum"),"hybrid_vs_numeric":mcnemar(hold,"phybrid","pnum")},
 "holdout_disagreements":[{"origin":r["origin"],"ticker":r["ticker"],"group":r["group"],"actual_5d_pct":r["actual"],"y":r["y"],"pnum":r["pnum"],"pjev":r["pjev"],"run_std":r["run_std"],"pjev_cal":r["pjev_cal"],"phybrid":r["phybrid"],"pchallenger":r["pchallenger"],"override":r["override"]} for r in hold if (r["pnum"]>=.5)!=(r["pjev"]>=.5)],
 "holdout_rows":[{"origin":r["origin"],"ticker":r["ticker"],"group":r["group"],"actual_5d_pct":r["actual"],"pnum":r["pnum"],"pjev":r["pjev"],"run_std":r["run_std"],"pjev_cal":r["pjev_cal"],"phybrid":r["phybrid"],"pchallenger":r["pchallenger"],"override":r["override"]} for r in hold],
 "note":"All Jev predictions are independent single-case 3-run evaluations. Hyperparameters and gates selected on development only."
}
json.dumps(out,allow_nan=False)
`;

export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const o=await outcomes(),py=await getRuntime();
    py.globals.set("frozen_json",JSON.stringify(frozen));
    py.globals.set("single_json",JSON.stringify(singleResults));
    py.globals.set("outcomes_json",JSON.stringify(o));
    const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();
    return res.status(200).json({ok:true,...out});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1600)})}
}
