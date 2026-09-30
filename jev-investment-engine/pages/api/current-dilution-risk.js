import eventsData from "../../../research/event_risk/event-metadata-current-20260930.json";
import readyData from "../../../research/event_risk/financing-readiness-current-20260930.json";
import hazard from "../../../research/event_risk/dilution-hazard-v2-shelf.json";
import decomp from "../../../research/event_risk/event-risk-decomposition-v1.json";

export const config={maxDuration:120};
const PRICE_SHA="d6b2aaf113a8c97034de3ef20bd06dfc23f1eba9";
const RAW=`https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/${PRICE_SHA}/chart-data`;
async function j(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"current-dilution-risk"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
function mean(a){return a.reduce((s,x)=>s+x,0)/a.length}
function sd(a){if(a.length<2)return null;const m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1))}
function median(a){const b=[...a].sort((x,y)=>x-y),n=b.length;return n%2?b[(n-1)/2]:(b[n/2-1]+b[n/2])/2}
function daysBetween(a,b){return Math.floor((a-b)/86400000)}
function hb(n){return n===0?"0":n===1?"1":"2plus"}
function vb(v){return v<=hazard.vol_tertiles.low_max?"low":v<=hazard.vol_tertiles.mid_max?"mid":"high"}
export default async function handler(req,res){
 res.setHeader("Cache-Control","no-store");
 if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
 try{
  const idx=await j(RAW+"/index.json");
  const shardNums=[...new Set(Object.values(idx.ticker_to_shard||{}).filter(Number.isInteger))].sort((a,b)=>a-b);
  const shards=await Promise.all(shardNums.map(async sh=>[sh,await j(RAW+`/shard-${String(sh).padStart(2,"0")}.json`)]));
  const universe={};for(const [,obj] of shards)Object.assign(universe,obj);
  let asOf="0000-00-00";
  for(const rows of Object.values(universe)){if(rows?.length){const d=String(rows[rows.length-1][0]).slice(0,10);if(d>asOf)asOf=d}}
  const asDate=new Date(asOf+"T00:00:00Z"), d90=new Date(asDate.getTime()-90*86400000), d365=new Date(asDate.getTime()-365*86400000);
  const DIL=new Set(["public_offering","private_placement","pipe_transaction","warrant_or_conversion"]);
  const devents=new Map();
  for(const e of eventsData.events||[]){if(!DIL.has(e.category)||!e.ticker)continue;const d=new Date(e.filing_date+"T00:00:00Z");if(d<=asDate){if(!devents.has(e.ticker))devents.set(e.ticker,[]);devents.get(e.ticker).push(d)}}
  const forms=new Map();
  for(const f of readyData.rows||[]){if(!f.ticker)continue;const d=new Date(f.filing_date+"T00:00:00Z");if(d>asDate)continue;if(!forms.has(f.ticker))forms.set(f.ticker,[]);forms.get(f.ticker).push({d,form:f.form_type})}
  const tHS=hazard.tables.history_shelf, tHSV=hazard.tables.history_shelf_vol, base=hazard.train_event_rate;
  const imp=decomp.dilution.impact_5d;
  const scaleRoot=Math.sqrt(5), out=[];
  for(const [tk,rows] of Object.entries(universe)){
    if(!rows||rows.length<100)continue;
    const rr=rows.map(r=>[String(r[0]).slice(0,10),...r.slice(1).map(Number)]).filter(r=>r[0]<=asOf);
    if(rr.length<100)continue;
    const i=rr.length-1,close=rr[i][4];if(!(close>=5))continue;
    const ddv=median(rr.slice(-20).map(r=>r[4]*r[5]).filter(Number.isFinite));if(!(ddv>=1e7))continue;
    const rets=[];for(let k=Math.max(1,rr.length-20);k<rr.length;k++)rets.push((rr[k][4]/rr[k-1][4]-1)*100);
    const vol=sd(rets);if(!(vol>0))continue;
    const ev=(devents.get(tk)||[]), prior90=ev.filter(d=>d>=d90&&d<=asDate).length;
    const ff=(forms.get(tk)||[]);
    const shelf=ff.some(x=>(x.form==="S-3"||x.form==="S-3ASR")&&x.d>=d365);
    const b424=ff.some(x=>x.form==="424B5"&&x.d>=d90);
    const khs=`${hb(prior90)}|${shelf?"shelf":"noshelf"}`;
    const khsv=`${hb(prior90)}|${shelf?"shelf":"noshelf"}|${vb(vol)}`;
    const pCal=tHS[khs]?.shrunk_rate ?? hazard.tables.history[hb(prior90)]?.shrunk_rate ?? base;
    const pRank=tHSV[khsv]?.shrunk_rate ?? pCal;
    const scale=vol*scaleRoot;
    out.push({ticker:tk,as_of:asOf,price:close,ddv20:ddv,vol20_pct:vol,prior_dilution_90d:prior90,shelf_365d:shelf,b424b5_90d:b424,
      p60_calibrated:pCal,p60_rank:pRank,
      conditional_median_5d_pct:imp.median_z*scale,
      conditional_p10_5d_pct:imp.p10_z*scale,
      downside_ev_5d_pct:pCal*imp.mean_negative_part_z*scale,
      upside_offset_ev_5d_pct:pCal*imp.mean_positive_part_z*scale,
      net_dilution_ev_5d_pct:pCal*imp.mean_z*scale});
  }
  out.sort((a,b)=>b.p60_rank-a.p60_rank||a.downside_ev_5d_pct-b.downside_ev_5d_pct);
  const top=out.slice(0,100);
  return res.status(200).json({ok:true,version:"current-dilution-risk-v1",price_sha:PRICE_SHA,as_of:asOf,eligible_n:out.length,
   model_note:"p60_calibrated uses history+shelf (best holdout Brier); p60_rank uses history+shelf+vol (best holdout ROC/top-decile lift).",
   impact_note:"5D conditional impact scaled by current vol using event-risk-decomposition-v1. Negative and positive components remain separate.",
   top});
 }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1500)})}
}