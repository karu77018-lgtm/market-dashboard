import eventsData from "../../../research/event_risk/event-metadata-20260930.json";
let runtimePromise;
async function getRuntime(){if(!runtimePromise)runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();return runtimePromise}
export const config={maxDuration:120};
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"dilution-hazard-study"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
const PY=String.raw`
import json,math,statistics,datetime
E=json.loads(events_json);U=json.loads(universe_json)
DIL={"public_offering","private_placement","pipe_transaction","warrant_or_conversion"}
UW={"underwriting_agreement"}
def mean(x):return sum(x)/len(x) if x else None
def sd(x):
    if len(x)<2:return None
    m=mean(x);return math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
def sigmoid(z):
    if z>=0:return 1/(1+math.exp(-min(z,60)))
    e=math.exp(max(z,-60));return e/(1+e)
def auc(y,p):
    pos=[p[i] for i,v in enumerate(y) if v];neg=[p[i] for i,v in enumerate(y) if not v]
    if not pos or not neg:return None
    s=0
    for a in pos:
      for b in neg:s+=1 if a>b else .5 if a==b else 0
    return s/(len(pos)*len(neg))
def ap(y,p):
    order=sorted(range(len(y)),key=lambda i:p[i],reverse=True)
    tp=0;tot=sum(y);s=0
    if tot==0:return None
    for rank,i in enumerate(order,1):
      if y[i]:tp+=1;s+=tp/rank
    return s/tot
def q(v,p):
    s=sorted(v);x=(len(s)-1)*p;lo=int(x);hi=min(len(s)-1,lo+1);return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def norm(rows):
    out=[]
    for r in rows:
      try:out.append((str(r[0])[:10],float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5])))
      except:pass
    return out
SER={k:norm(v) for k,v in U.items()}
all_dates=sorted(set(r[0] for rows in SER.values() for r in rows))
SNAP_TARGETS=["2026-04-03","2026-04-24","2026-05-15","2026-06-05","2026-06-26","2026-07-17"]
def nearest_on_or_before(d):
    z=[x for x in all_dates if x<=d];return z[-1] if z else None
SNAPS=[nearest_on_or_before(d) for d in SNAP_TARGETS]
dil_events={}
uw_events={}
for e in E["events"]:
    tk=e["ticker"];d=datetime.date.fromisoformat(e["filing_date"])
    if e["category"] in DIL:dil_events.setdefault(tk,[]).append(d)
    if e["category"] in UW:uw_events.setdefault(tk,[]).append(d)
for d in dil_events.values():d.sort()
for d in uw_events.values():d.sort()
def days_between(a,b):return (a-b).days
rows=[]
for snap in SNAPS:
  sdte=datetime.date.fromisoformat(snap);end60=sdte+datetime.timedelta(days=60)
  for tk,rr in SER.items():
    dates=[r[0] for r in rr];inds=[i for i,d in enumerate(dates) if d<=snap]
    if not inds:continue
    i=inds[-1]
    if i<99:continue
    price=rr[i][4]
    if price<5:continue
    ddv=statistics.median([rr[j][4]*rr[j][5] for j in range(i-19,i+1)])
    if ddv<1e7:continue
    daily=[(rr[j][4]/rr[j-1][4]-1)*100 for j in range(i-19,i+1)]
    vol20=sd(daily)
    if not vol20 or vol20<=0:continue
    ret21=(rr[i][4]/rr[i-21][4]-1)*100 if i>=21 else None
    ret63=(rr[i][4]/rr[i-63][4]-1)*100 if i>=63 else None
    high63=max(rr[j][2] for j in range(i-62,i+1)) if i>=62 else rr[i][2]
    dist_high63=(rr[i][4]/high63-1)*100
    de=dil_events.get(tk,[]);ue=uw_events.get(tk,[])
    past90=[d for d in de if sdte-datetime.timedelta(days=90)<=d<=sdte]
    past30=[d for d in de if sdte-datetime.timedelta(days=30)<=d<=sdte]
    puw90=[d for d in ue if sdte-datetime.timedelta(days=90)<=d<=sdte]
    last=max([d for d in de if d<=sdte],default=None)
    days_since=min(365,days_between(sdte,last)) if last else 365
    future=[d for d in de if sdte<d<=end60]
    y=1 if future else 0
    x=[len(past30),len(past90),len(puw90),days_since,math.log1p(ddv),math.log(price),vol20,ret21 or 0,ret63 or 0,dist_high63]
    rows.append({"snap":snap,"ticker":tk,"x":x,"y":y,"prior90":len(past90),"future_n":len(future)})
DEV=set(SNAPS[:4]);CAL={SNAPS[4]};HOLD={SNAPS[5]}
dev=[r for r in rows if r["snap"] in DEV];cal=[r for r in rows if r["snap"] in CAL];hold=[r for r in rows if r["snap"] in HOLD]
def prep(train):
    d=len(train[0]["x"]);med=[];mu=[];sig=[]
    for j in range(d):
      v=sorted(r["x"][j] for r in train);m=statistics.median(v);med.append(m);av=mean(v);mu.append(av);s=(sum((z-av)**2 for z in v)/len(v))**0.5;sig.append(s if s>1e-9 else 1)
    return med,mu,sig
def vec(r,state):
    med,mu,sig=state;return [(r["x"][j]-mu[j])/sig[j] for j in range(len(mu))]
def fit(train,lam,iters=500):
    st=prep(train);X=[vec(r,st) for r in train];Y=[r["y"] for r in train];base=mean(Y);b=math.log(max(base,1e-6)/max(1-base,1e-6));w=[0.0]*len(X[0]);lr=.05
    for _ in range(iters):
      gb=0;gw=[0.0]*len(w)
      for x,y in zip(X,Y):
        p=sigmoid(b+sum(a*z for a,z in zip(w,x)));e=p-y;gb+=e
        for j in range(len(w)):gw[j]+=e*x[j]
      n=len(Y);b-=lr*gb/n
      for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
    return st,b,w,base
def pred(m,rr):
    st,b,w,base=m;return [sigmoid(b+sum(a*z for a,z in zip(w,vec(r,st)))) for r in rr]
def metrics(rr,p):
    y=[r["y"] for r in rr];base=mean(y);br=mean([(a-b)**2 for a,b in zip(p,y)])
    k=max(1,len(rr)//10);order=sorted(range(len(rr)),key=lambda i:p[i],reverse=True);top=order[:k]
    return {"n":len(rr),"event_rate":base,"brier":br,"roc_auc":auc(y,p),"average_precision":ap(y,p),
            "mean_p":mean(p),"top_decile_event_rate":mean([y[i] for i in top]),"top_decile_lift":mean([y[i] for i in top])/base if base else None}
lams=[1,5,10,20,50]
cv=[]
for lam in lams:
    fold=[]
    for j in range(2,4):
      tr=[r for r in rows if r["snap"] in set(SNAPS[:j])]
      va=[r for r in rows if r["snap"]==SNAPS[j]]
      m=fit(tr,lam);p=pred(m,va);fold.append(metrics(va,p)["brier"])
    cv.append((mean(fold),lam,fold))
best=min(cv)[1]
mdev=fit(dev,best);pcal=pred(mdev,cal);base=mdev[3]
alphas=[0,.25,.5,.75,1]
alpha=min(alphas,key=lambda a:mean([(base+a*(p-base)-r["y"])**2 for p,r in zip(pcal,cal)]))
mfinal=fit(dev+cal,best);basef=mfinal[3]
ph=[basef+alpha*(p-basef) for p in pred(mfinal,hold)]
# simple empirical prior-event strata using only dev+cal
train=dev+cal
strata={}
for label,fn in [("prior90_0",lambda r:r["prior90"]==0),("prior90_1",lambda r:r["prior90"]==1),("prior90_2plus",lambda r:r["prior90"]>=2)]:
    z=[r["y"] for r in train if fn(r)]
    strata[label]={"n":len(z),"rate":mean(z) if z else None}
# empirical predictor on holdout
pemp=[]
for r in hold:
    k="prior90_0" if r["prior90"]==0 else "prior90_1" if r["prior90"]==1 else "prior90_2plus"
    pemp.append(strata[k]["rate"] if strata[k]["rate"] is not None else basef)
# constant
pconst=[basef]*len(hold)
out={"version":"dilution-hazard-v1","snapshots":SNAPS,"rows":len(rows),"development_n":len(dev),"calibration_n":len(cal),"holdout_n":len(hold),
"features":["prior_dilution30","prior_dilution90","prior_underwriting90","days_since_last_dilution","log_ddv20","log_price","vol20","ret21","ret63","dist_high63"],
"cv":[{"lambda":l,"brier":b,"folds":f} for b,l,f in cv],"selected_lambda":best,"shrink_alpha":alpha,
"train_event_rate":mean([r["y"] for r in dev+cal]),"strata":strata,
"holdout":{"constant":metrics(hold,pconst),"empirical_history":metrics(hold,pemp),"logistic":metrics(hold,ph)},
"holdout_counts":{"positives":sum(r["y"] for r in hold),"total":len(hold)},
"note":"Pilot 60-calendar-day dilution hazard. Snapshot universe requires >=100 prior sessions. No financial-statement cash runway yet."}
json.dumps(out,allow_nan=False)
`;
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
    const shards=await Promise.all(Array.from({length:32},(_,i)=>fetchJson(base+`shard-${String(i).padStart(2,"0")}.json`)));
    const universe=Object.assign({},...shards);
    const py=await getRuntime();py.globals.set("events_json",JSON.stringify(eventsData));py.globals.set("universe_json",JSON.stringify(universe));
    const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();return res.status(200).json({ok:true,...out});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)})}
}