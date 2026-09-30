import frozen from "../../data/jev-5d-frozen-inputs.json";
import results from "../../data/jev-5d-results.json";
let runtimePromise;
async function getRuntime(){if(!runtimePromise){runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})()}return runtimePromise}
const PY=String.raw`
import json,math,statistics
F=json.loads(frozen_json);R=json.loads(results_json)
DEV={"2026-08-07","2026-08-14","2026-08-21","2026-08-28"}
HOLD={"2026-09-04","2026-09-14","2026-09-21"}
if R.get("status")!="complete": raise Exception("RESULTS_NOT_COMPLETE")
fmap={}
for o in F["origins"]:
  for c in o["cases"]: fmap[(o["origin"],c["ticker"])] = c
rows=[]
for o in R["origins"]:
  for r in o["cases"]:
    if r.get("status")!="observed": continue
    c=fmap[(o["origin"],r["ticker"])]
    rows.append({"origin":o["origin"],"ticker":r["ticker"],"group":r["group"],"x":c["features"],"pjev":float(r["p_up"]),"y":1 if float(r["actual_5d_pct"])>0 else 0,"actual":float(r["actual_5d_pct"])})
cols=list(rows[0]["x"].keys())
dev=[r for r in rows if r["origin"] in DEV]; hold=[r for r in rows if r["origin"] in HOLD]
usable=[]; med={}; mu={}; sig={}
for k in cols:
  vals=[float(r["x"][k]) for r in dev if r["x"].get(k) is not None and math.isfinite(float(r["x"][k]))]
  if not vals: continue
  vals2=sorted(vals);n=len(vals2);m=vals2[n//2] if n%2 else (vals2[n//2-1]+vals2[n//2])/2
  med[k]=m
  z=[float(r["x"].get(k)) if r["x"].get(k) is not None and math.isfinite(float(r["x"].get(k))) else m for r in dev]
  av=sum(z)/len(z);sd=(sum((v-av)**2 for v in z)/len(z))**0.5
  if sd<1e-9: continue
  usable.append(k);mu[k]=av;sig[k]=sd
def vec(r):
  out=[]
  for k in usable:
    v=r["x"].get(k);v=float(v) if v is not None and math.isfinite(float(v)) else med[k]
    out.append((v-mu[k])/sig[k])
  return out
def sigmoid(z):
  if z>=0:return 1/(1+math.exp(-min(z,60)))
  e=math.exp(max(z,-60));return e/(1+e)
X=[vec(r) for r in dev];Y=[r["y"] for r in dev];d=len(usable)
base=sum(Y)/len(Y);b=math.log(max(base,1e-6)/max(1-base,1e-6));w=[0.0]*d
lr=.05;lam=1.0
for it in range(1200):
  gb=0.0;gw=[0.0]*d
  for x,y in zip(X,Y):
    p=sigmoid(b+sum(a*z for a,z in zip(w,x)));e=p-y;gb+=e
    for j in range(d):gw[j]+=e*x[j]
  n=len(Y);b-=lr*gb/n
  for j in range(d):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
def pnum(r):
  x=vec(r);return sigmoid(b+sum(a*z for a,z in zip(w,x)))
for r in rows:r["pnum"]=pnum(r)
def brier(rs,key):return sum((r[key]-r["y"])**2 for r in rs)/len(rs)
alphas=[0,.25,.5,.75,1]
a=min(alphas,key=lambda x:sum(((.5+x*(r["pjev"]-.5))-r["y"])**2 for r in dev)/len(dev))
for r in rows:r["pjev_cal"]=.5+a*(r["pjev"]-.5)
weights=[0,.25,.5,.75,1]
hw=min(weights,key=lambda z:sum(((z*r["pjev_cal"]+(1-z)*r["pnum"])-r["y"])**2 for r in dev)/len(dev))
for r in rows:r["phybrid"]=hw*r["pjev_cal"]+(1-hw)*r["pnum"]
for r in rows:r["pconst"]=base
def metrics(rs,key):
  if not rs:return {"n":0}
  y=[r["y"] for r in rs];p=[r[key] for r in rs];pred=[x>=.5 for x in p]
  acc=sum(int(a==bool(b)) for a,b in zip(pred,y))/len(rs)
  pos=[i for i,v in enumerate(y) if v==1];neg=[i for i,v in enumerate(y) if v==0]
  tpr=sum(pred[i] for i in pos)/len(pos) if pos else None
  tnr=sum(not pred[i] for i in neg)/len(neg) if neg else None
  bal=(tpr+tnr)/2 if tpr is not None and tnr is not None else None
  br=sum((a-b)**2 for a,b in zip(p,y))/len(rs)
  ll=-sum(b*math.log(max(min(a,1-1e-12),1e-12))+(1-b)*math.log(max(min(1-a,1-1e-12),1e-12)) for a,b in zip(p,y))/len(rs)
  return {"n":len(rs),"accuracy":acc,"balanced_accuracy":bal,"brier":br,"logloss":ll,"mean_p":sum(p)/len(p),"up_frequency":sum(y)/len(y)}
def mcnemar(rs,ka,kb):
  a=b=0
  for r in rs:
    ca=((r[ka]>=.5)==bool(r["y"]));cb=((r[kb]>=.5)==bool(r["y"]))
    if ca and not cb:a+=1
    elif cb and not ca:b+=1
  n=a+b
  if n==0:p=1.0
  else:
    k=min(a,b);tail=sum(math.comb(n,i) for i in range(k+1))/(2**n);p=min(1.0,2*tail)
  return {"a_correct_b_wrong":a,"a_wrong_b_correct":b,"discordant":n,"exact_p":p}
def by_origin(rs,key):
  return {o:metrics([r for r in rs if r["origin"]==o],key) for o in sorted(set(r["origin"] for r in rs))}
keys=["pconst","pnum","pjev","pjev_cal","phybrid"]
out={"version":"jev-5d-strong-stock-v1","development_n":len(dev),"holdout_n":len(hold),"usable_numeric_features":len(usable),"dropped_numeric_features":[k for k in cols if k not in usable],"development_up_frequency":base,"selected_jev_shrinkage":a,"selected_hybrid_jev_weight":hw,
"development":{k:metrics(dev,k) for k in keys},"holdout":{k:metrics(hold,k) for k in keys},
"holdout_by_origin":{k:by_origin(hold,k) for k in keys},
"holdout_by_group":{g:{k:metrics([r for r in hold if r["group"]==g],k) for k in keys} for g in ["leader","hash_control"]},
"mcnemar_holdout":{"jev_vs_numeric":mcnemar(hold,"pjev","pnum"),"hybrid_vs_numeric":mcnemar(hold,"phybrid","pnum"),"hybrid_vs_jev":mcnemar(hold,"phybrid","pjev")},
"holdout_disagreements":[{"origin":r["origin"],"ticker":r["ticker"],"group":r["group"],"actual_5d_pct":r["actual"],"y":r["y"],"pnum":r["pnum"],"pjev":r["pjev"],"pjev_cal":r["pjev_cal"],"phybrid":r["phybrid"]} for r in hold if (r["pnum"]>=.5)!=(r["pjev"]>=.5)],
"note":"Holdout has only three origin blocks; no pseudo-precise bootstrap confidence interval is reported."}
json.dumps(out,allow_nan=False)
`;
export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const py=await getRuntime();py.globals.set("frozen_json",JSON.stringify(frozen));py.globals.set("results_json",JSON.stringify(results));
    const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();return res.status(200).json({ok:true,...out});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1200)})}
}
