import eventsData from "../../../research/event_risk/event-metadata-20260930.json";
import shelfData from "../../../research/event_risk/shelf-readiness-v1.json";
let runtimePromise;
async function getRuntime(){if(!runtimePromise)runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();return runtimePromise}
export const config={maxDuration:120};
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"dilution-hazard-study"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
const PY=String.raw`
import json,math,statistics,datetime
E=json.loads(events_json);U=json.loads(universe_json);S=json.loads(shelf_json)
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
    sr=S.get("snapshots",{}).get(snap,{}).get(tk,{})
    shelf_recent=1 if (sr.get("s3_365",0)+sr.get("s3asr_365",0))>0 else 0
    b424_90=int(sr.get("b424_90",0) or 0)
    b424_30=int(sr.get("b424_30",0) or 0)
    days_shelf=min(999,int(sr.get("days_since_shelf",9999) or 9999))
    x=[len(past30),len(past90),len(puw90),days_since,math.log1p(ddv),math.log(price),vol20,ret21 or 0,ret63 or 0,dist_high63]
    rows.append({"snap":snap,"ticker":tk,"x":x,"y":y,"prior90":len(past90),"future_n":len(future),
                 "shelf":shelf_recent,"b424_90":b424_90,"b424_30":b424_30,"days_shelf":days_shelf})
DEV=set(SNAPS[:4]);CAL={SNAPS[4]};HOLD={SNAPS[5]}
dev=[r for r in rows if r["snap"] in DEV];cal=[r for r in rows if r["snap"] in CAL];hold=[r for r in rows if r["snap"] in HOLD]
train=dev+cal
base=mean([r["y"] for r in train])
# volatility tertiles learned on development only
v=sorted(r["x"][6] for r in dev)
v1=v[len(v)//3];v2=v[(2*len(v))//3]
def hb(r):
    return "0" if r["prior90"]==0 else "1" if r["prior90"]==1 else "2plus"
def vb(r):
    z=r["x"][6]
    return "low" if z<=v1 else "mid" if z<=v2 else "high"
def brier(rr,p):
    return mean([(a-r["y"])**2 for a,r in zip(p,rr)])
def ap(y,p):
    order=sorted(range(len(y)),key=lambda i:p[i],reverse=True);tot=sum(y)
    if tot==0:return None
    tp=0;s=0
    for rank,i in enumerate(order,1):
        if y[i]:tp+=1;s+=tp/rank
    return s/tot
def auc(y,p):
    pos=[p[i] for i,z in enumerate(y) if z];neg=[p[i] for i,z in enumerate(y) if not z]
    if not pos or not neg:return None
    s=0
    for a in pos:
      for b in neg:s+=1 if a>b else .5 if a==b else 0
    return s/(len(pos)*len(neg))
def metrics(rr,p):
    y=[r["y"] for r in rr];k=max(1,len(rr)//10);order=sorted(range(len(rr)),key=lambda i:p[i],reverse=True)
    top=order[:k];rate=mean(y)
    return {"n":len(rr),"event_rate":rate,"brier":brier(rr,p),"roc_auc":auc(y,p),"average_precision":ap(y,p),
            "mean_p":mean(p),"top_decile_event_rate":mean([y[i] for i in top]),"top_decile_lift":mean([y[i] for i in top])/rate if rate else None}
def rates(rr,keyfn):
    d={}
    for r in rr:
        k=keyfn(r);d.setdefault(k,[]).append(r["y"])
    return {k:{"n":len(z),"rate":mean(z)} for k,z in d.items()}
def sb(r): return "shelf" if r["shelf"] else "noshelf"
def cb(r): return "424" if r["b424_90"]>0 else "no424"
hist_raw=rates(dev,lambda r:hb(r))
hv_raw=rates(dev,lambda r:hb(r)+"|"+vb(r))
hs_raw=rates(dev,lambda r:hb(r)+"|"+sb(r))
hsc_raw=rates(dev,lambda r:hb(r)+"|"+sb(r)+"|"+cb(r))
hsv_raw=rates(dev,lambda r:hb(r)+"|"+sb(r)+"|"+vb(r))
# empirical Bayes shrinkage chosen on calibration
strengths=[0,25,50,100,200,500]
def build_rates(raw,strength):
    return {k:(z["rate"]*z["n"]+base*strength)/(z["n"]+strength) for k,z in raw.items()}
def pred_from(rr,rates_,keyfn):
    return [rates_.get(keyfn(r),base) for r in rr]
specs=[
 ("history",hist_raw,lambda r:hb(r)),
 ("history_vol",hv_raw,lambda r:hb(r)+"|"+vb(r)),
 ("history_shelf",hs_raw,lambda r:hb(r)+"|"+sb(r)),
 ("history_shelf_424",hsc_raw,lambda r:hb(r)+"|"+sb(r)+"|"+cb(r)),
 ("history_shelf_vol",hsv_raw,lambda r:hb(r)+"|"+sb(r)+"|"+vb(r))
]
best_strength={}
for name,raw,keyfn in specs:
    best_strength[name]=min(strengths,key=lambda s:brier(cal,pred_from(cal,build_rates(raw,s),keyfn)))
# refit rates on dev+cal with frozen strengths
train_specs=[
 ("history",rates(train,lambda r:hb(r)),lambda r:hb(r)),
 ("history_vol",rates(train,lambda r:hb(r)+"|"+vb(r)),lambda r:hb(r)+"|"+vb(r)),
 ("history_shelf",rates(train,lambda r:hb(r)+"|"+sb(r)),lambda r:hb(r)+"|"+sb(r)),
 ("history_shelf_424",rates(train,lambda r:hb(r)+"|"+sb(r)+"|"+cb(r)),lambda r:hb(r)+"|"+sb(r)+"|"+cb(r)),
 ("history_shelf_vol",rates(train,lambda r:hb(r)+"|"+sb(r)+"|"+vb(r)),lambda r:hb(r)+"|"+sb(r)+"|"+vb(r))
]
preds={"constant":[base]*len(hold)}
tables={}
for name,raw,keyfn in train_specs:
    rrates=build_rates(raw,best_strength[name])
    preds[name]=pred_from(hold,rrates,keyfn)
    tables[name]={k:{"n":z["n"],"raw_rate":z["rate"],"shrunk_rate":rrates[k]} for k,z in raw.items()}
shelf_only=rates(train,lambda r:sb(r))
b424_only=rates(train,lambda r:cb(r))
out={"version":"dilution-hazard-v2-shelf","snapshots":SNAPS,"rows":len(rows),"development_n":len(dev),"calibration_n":len(cal),"holdout_n":len(hold),
"universe_filters":[">=100 prior sessions","price >= $5","DDV20 >= $10M"],
"target":"any public offering/private placement/PIPE/warrant-conversion filing in next 60 calendar days",
"train_event_rate":base,"vol_tertiles":{"low_max":v1,"mid_max":v2},
"selected_shrink_strength":best_strength,
"tables":tables,"shelf_only_train":shelf_only,"b424_90_only_train":b424_only,
"holdout":{name:metrics(hold,p) for name,p in preds.items()},
"holdout_counts":{"positives":sum(r["y"] for r in hold),"total":len(hold)},
"note":"PIT shelf-readiness v2. S-3/S-3ASR are shelf readiness. 424B5 is generic capital-markets activity and can include debt."}
json.dumps(out,allow_nan=False)
`;
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
    const shards=await Promise.all(Array.from({length:32},(_,i)=>fetchJson(base+`shard-${String(i).padStart(2,"0")}.json`)));
    const universe=Object.assign({},...shards);
    const py=await getRuntime();py.globals.set("events_json",JSON.stringify(eventsData));py.globals.set("universe_json",JSON.stringify(universe));py.globals.set("shelf_json",JSON.stringify(shelfData));
    const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();return res.status(200).json({ok:true,...out});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)})}
}