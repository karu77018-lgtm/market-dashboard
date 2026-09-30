import eventsData from "../../research/event_risk/event-metadata-20260930.json";

let runtimePromise;
async function getRuntime(){
  if(!runtimePromise) runtimePromise=(async()=>{const {loadPyodide}=await import("pyodide");return loadPyodide()})();
  return runtimePromise;
}
export const config={maxDuration:120};
async function fetchJson(url){
  const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"event-risk-study"}});
  if(!r.ok) throw new Error("HTTP_"+r.status+"_"+url);
  return r.json();
}
const PY=String.raw`
import json,math,statistics,datetime
E=json.loads(events_json);U=json.loads(universe_json);IDX=json.loads(index_json)
def mean(x): return sum(x)/len(x) if x else None
def q(v,p):
    if not v:return None
    s=sorted(v); x=(len(s)-1)*p; lo=int(math.floor(x)); hi=int(math.ceil(x))
    if lo==hi:return s[lo]
    return s[lo]*(hi-x)+s[hi]*(x-lo)
def sd(v):
    if len(v)<2:return None
    m=mean(v);return math.sqrt(sum((x-m)**2 for x in v)/(len(v)-1))
def norm(rows):
    out=[]
    for r in rows:
        try: out.append((str(r[0])[:10],float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5])))
        except: pass
    return out
SER={k:norm(v) for k,v in U.items()}
rows=[];skip={}
last_seen={}
for e in E["events"]:
    tk=e["ticker"];cat=e["category"];d=e["filing_date"]
    if tk not in SER:
        skip["no_price"] = skip.get("no_price",0)+1; continue
    rr=SER[tk]; dates=[x[0] for x in rr]
    # seasoned common-equity proxy: >=200 prior sessions
    prior=[i for i,x in enumerate(dates) if x<d]
    future=[i for i,x in enumerate(dates) if x>d]
    if not prior or len(future)<5:
        skip["calendar"] = skip.get("calendar",0)+1; continue
    pi=prior[-1]; fi=future[0]
    if pi<199:
        skip["history_lt200"] = skip.get("history_lt200",0)+1; continue
    close0=rr[pi][4]
    if close0<5:
        skip["price_lt5"] = skip.get("price_lt5",0)+1; continue
    ddv=statistics.median([rr[j][4]*rr[j][5] for j in range(pi-19,pi+1)])
    if ddv<1e7:
        skip["ddv_lt10m"] = skip.get("ddv_lt10m",0)+1; continue
    # same ticker/category cooldown 30 calendar days
    key=(tk,cat)
    dd=datetime.date.fromisoformat(d)
    if key in last_seen and (dd-last_seen[key]).days<30:
        skip["cooldown30"] = skip.get("cooldown30",0)+1; continue
    last_seen[key]=dd
    r1=[(rr[j][4]/rr[j-1][4]-1)*100 for j in range(pi-19,pi+1)]
    vol20=sd(r1)
    if not vol20 or vol20<=0:
        skip["vol_missing"] = skip.get("vol_missing",0)+1; continue
    gap=(rr[fi][1]/close0-1)*100
    # strict next-session: next session after filing date is session 1
    c5=rr[future[4]][4]
    ret5=(c5/close0-1)*100
    post5=(c5/rr[fi][1]-1)*100
    ret20=None;post20=None
    if len(future)>=20:
        c20=rr[future[19]][4]
        ret20=(c20/close0-1)*100
        post20=(c20/rr[fi][1]-1)*100
    z5=ret5/(vol20*math.sqrt(5))
    z20=ret20/(vol20*math.sqrt(20)) if ret20 is not None else None
    rows.append({"ticker":tk,"date":d,"category":cat,"family":e.get("family"),"gap":gap,"ret5":ret5,"post5":post5,
                 "ret20":ret20,"post20":post20,"z5":z5,"z20":z20,"vol20":vol20,"ddv20":ddv})
def metrics(rs):
    r5=[x["ret5"] for x in rs];gap=[x["gap"] for x in rs];z5=[x["z5"] for x in rs]
    r20=[x["ret20"] for x in rs if x["ret20"] is not None];z20=[x["z20"] for x in rs if x["z20"] is not None]
    return {
      "n5":len(r5),"n20":len(r20),
      "gap":{"p10":q(gap,.1),"p25":q(gap,.25),"median":q(gap,.5),"p75":q(gap,.75),"p90":q(gap,.9)},
      "ret5":{"mean":mean(r5),"p10":q(r5,.1),"p25":q(r5,.25),"median":q(r5,.5),"p75":q(r5,.75),"p90":q(r5,.9),
              "p_negative":mean([v<0 for v in r5]),"p_le_m10":mean([v<=-10 for v in r5]),"p_ge_10":mean([v>=10 for v in r5])},
      "ret20":{"mean":mean(r20),"p10":q(r20,.1),"p25":q(r20,.25),"median":q(r20,.5),"p75":q(r20,.75),"p90":q(r20,.9),
               "p_negative":mean([v<0 for v in r20]) if r20 else None,"p_le_m20":mean([v<=-20 for v in r20]) if r20 else None,"p_ge_20":mean([v>=20 for v in r20]) if r20 else None},
      "z5":{"p10":q(z5,.1),"p25":q(z5,.25),"median":q(z5,.5),"p75":q(z5,.75),"p90":q(z5,.9)},
      "z20":{"p10":q(z20,.1),"p25":q(z20,.25),"median":q(z20,.5),"p75":q(z20,.75),"p90":q(z20,.9)}
    }
cats=sorted(set(x["category"] for x in rows))
families=sorted(set(x["family"] for x in rows if x.get("family")))
bycat={c:metrics([x for x in rows if x["category"]==c]) for c in cats}
byfam={f:metrics([x for x in rows if x["family"]==f]) for f in families}
# dilution composite excludes underwriting because it mixes debt and equity underwriting
pure_dil=[x for x in rows if x["category"] in ["public_offering","private_placement","pipe_transaction","warrant_or_conversion"]]
out={"version":"event-risk-reaction-v1","method":{
 "baseline":"last close strictly before 8-K filing date",
 "horizon":"strict next regular sessions after filing date",
 "filters":["ticker in price cache",">=200 prior sessions","prior close >= $5","DDV20 >= $10M","30-calendar-day same ticker/category cooldown"],
 "normalization":"return / (pre-event 20D daily volatility * sqrt(horizon))"
},"input_events":E["event_count"],"matched_events":len(rows),"skip":skip,
"by_category":bycat,"by_family":byfam,"dilution_composite":metrics(pure_dil),
"rows":rows}
json.dumps(out,allow_nan=False)
`;
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
    const idx=await fetchJson(base+"index.json");
    const needed=new Set();
    for(const e of eventsData.events){const sh=idx.ticker_to_shard?.[e.ticker];if(Number.isInteger(sh))needed.add(sh);}
    const arr=await Promise.all([...needed].sort((a,b)=>a-b).map(async sh=>[sh,await fetchJson(base+`shard-${String(sh).padStart(2,"0")}.json`)]));
    const universe={};for(const [,obj] of arr)Object.assign(universe,obj);
    const py=await getRuntime();
    py.globals.set("events_json",JSON.stringify(eventsData));
    py.globals.set("universe_json",JSON.stringify(universe));
    py.globals.set("index_json",JSON.stringify(idx));
    const v=await py.runPythonAsync(PY);const out=JSON.parse(String(v));if(v?.destroy)v.destroy();
    return res.status(200).json({ok:true,...out});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)})}
}
