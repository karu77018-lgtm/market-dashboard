import eventsData from "../../../research/event_risk/event-metadata-20260930.json";
let runtimePromise;
async function getRuntime(){if(!runtimePromise)runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();return runtimePromise}
export const config={maxDuration:120};
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"event-family-hazard"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
const PY=String.raw`
import json,math,statistics,datetime
E=json.loads(events_json);U=json.loads(universe_json)
FAMILIES={
 "buyback":{"share_repurchase_program"},
 "severe_downside":{"going_concern","covenant_violation","debt_acceleration","payment_default","listing_deficiency_notice","regulatory_investigation","guidance_withdrawal"},
 "commercial_upside":{"share_repurchase_program","significant_contract_award","partnership_or_collaboration"},
 "regulatory_event":{"regulatory_decision"},
 "guidance_event":{"guidance_issuance_or_update","guidance_withdrawal"}
}
def mean(x):return sum(x)/len(x) if x else None
def sd(x):
    if len(x)<2:return None
    m=mean(x);return math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
def auc(y,p):
    pos=[p[i] for i,z in enumerate(y) if z];neg=[p[i] for i,z in enumerate(y) if not z]
    if not pos or not neg:return None
    s=0
    for a in pos:
      for b in neg:s+=1 if a>b else .5 if a==b else 0
    return s/(len(pos)*len(neg))
def ap(y,p):
    order=sorted(range(len(y)),key=lambda i:p[i],reverse=True);tot=sum(y)
    if tot==0:return None
    tp=0;s=0
    for rank,i in enumerate(order,1):
      if y[i]:tp+=1;s+=tp/rank
    return s/tot
def norm(rows):
    out=[]
    for r in rows:
      try:out.append((str(r[0])[:10],float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5])))
      except:pass
    return out
SER={k:norm(v) for k,v in U.items()}
all_dates=sorted(set(r[0] for rows in SER.values() for r in rows))
SNAP_TARGETS=["2026-04-03","2026-04-24","2026-05-15","2026-06-05","2026-06-26","2026-07-17"]
def nearest(d):
    z=[x for x in all_dates if x<=d];return z[-1] if z else None
SNAPS=[nearest(d) for d in SNAP_TARGETS]
emap={name:{} for name in FAMILIES}
for e in E["events"]:
    d=datetime.date.fromisoformat(e["filing_date"]);tk=e["ticker"];cat=e["category"]
    for name,cats in FAMILIES.items():
      if cat in cats:emap[name].setdefault(tk,[]).append(d)
for fam in emap.values():
  for a in fam.values():a.sort()
# base eligible snapshots shared across families
snaprows=[]
for snap in SNAPS:
  sdte=datetime.date.fromisoformat(snap)
  for tk,rr in SER.items():
    dates=[r[0] for r in rr];inds=[i for i,d in enumerate(dates) if d<=snap]
    if not inds:continue
    i=inds[-1]
    if i<99 or rr[i][4]<5:continue
    ddv=statistics.median([rr[j][4]*rr[j][5] for j in range(i-19,i+1)])
    if ddv<1e7:continue
    daily=[(rr[j][4]/rr[j-1][4]-1)*100 for j in range(i-19,i+1)]
    vol=sd(daily)
    if not vol or vol<=0:continue
    snaprows.append({"snap":snap,"ticker":tk,"vol":vol})
DEV=set(SNAPS[:4]);CAL={SNAPS[4]};HOLD={SNAPS[5]}
strengths=[0,25,50,100,200,500]
def hb(n):return "0" if n==0 else "1" if n==1 else "2plus"
def vb(v,a,b):return "low" if v<=a else "mid" if v<=b else "high"
def rates(rr,key):
    d={}
    for r in rr:d.setdefault(key(r),[]).append(r["y"])
    return {k:{"n":len(z),"rate":mean(z)} for k,z in d.items()}
def build(raw,s,base):return {k:(z["rate"]*z["n"]+base*s)/(z["n"]+s) for k,z in raw.items()}
def pred(rr,rt,key,base):return [rt.get(key(r),base) for r in rr]
def brier(rr,p):return mean([(a-r["y"])**2 for a,r in zip(p,rr)])
def metrics(rr,p):
    y=[r["y"] for r in rr];rate=mean(y);k=max(1,len(rr)//10);order=sorted(range(len(rr)),key=lambda i:p[i],reverse=True);top=order[:k]
    return {"n":len(rr),"event_rate":rate,"brier":brier(rr,p),"roc_auc":auc(y,p),"average_precision":ap(y,p),"mean_p":mean(p),
            "top_decile_event_rate":mean([y[i] for i in top]),"top_decile_lift":mean([y[i] for i in top])/rate if rate else None}
out={}
for name in FAMILIES:
  rr=[]
  for s in snaprows:
    sdte=datetime.date.fromisoformat(s["snap"]);events=emap[name].get(s["ticker"],[])
    prior=[d for d in events if sdte-datetime.timedelta(days=90)<=d<=sdte]
    future=[d for d in events if sdte<d<=sdte+datetime.timedelta(days=60)]
    rr.append({**s,"prior":len(prior),"y":1 if future else 0})
  dev=[r for r in rr if r["snap"] in DEV];cal=[r for r in rr if r["snap"] in CAL];hold=[r for r in rr if r["snap"] in HOLD];train=dev+cal
  base=mean([r["y"] for r in train])
  vv=sorted(r["vol"] for r in dev);v1=vv[len(vv)//3];v2=vv[2*len(vv)//3]
  k1=lambda r:hb(r["prior"]);k2=lambda r:hb(r["prior"])+"|"+vb(r["vol"],v1,v2)
  raw1=rates(dev,k1);raw2=rates(dev,k2)
  best1=min(strengths,key=lambda s:brier(cal,pred(cal,build(raw1,s,base),k1,base)))
  best2=min(strengths,key=lambda s:brier(cal,pred(cal,build(raw2,s,base),k2,base)))
  tr1=rates(train,k1);tr2=rates(train,k2);rt1=build(tr1,best1,base);rt2=build(tr2,best2,base)
  p0=[base]*len(hold);p1=pred(hold,rt1,k1,base);p2=pred(hold,rt2,k2,base)
  out[name]={"categories":sorted(FAMILIES[name]),"train_event_rate":base,"selected_shrink":{"history":best1,"history_vol":best2},
             "history_table":{k:{"n":z["n"],"raw_rate":z["rate"],"shrunk_rate":rt1[k]} for k,z in tr1.items()},
             "holdout":{"constant":metrics(hold,p0),"history":metrics(hold,p1),"history_vol":metrics(hold,p2)}}
json.dumps({"version":"event-family-hazard-v1","snapshots":SNAPS,"holdout_snapshot":SNAPS[-1],"families":out,
"note":"Occurrence only. Commercial/regulatory/guidance event polarity must be resolved separately."},allow_nan=False)
`;
export default async function handler(req,res){
 res.setHeader("Cache-Control","no-store");if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
 try{
  const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
  const shards=await Promise.all(Array.from({length:32},(_,i)=>fetchJson(base+`shard-${String(i).padStart(2,"0")}.json`)));
  const universe=Object.assign({},...shards),py=await getRuntime();py.globals.set("events_json",JSON.stringify(eventsData));py.globals.set("universe_json",JSON.stringify(universe));
  const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();return res.status(200).json({ok:true,...out});
 }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)})}
}
