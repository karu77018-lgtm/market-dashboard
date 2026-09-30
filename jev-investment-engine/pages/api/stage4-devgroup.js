import frozen from "../../data/jev-5d-frozen-inputs.json";
import marketData from "../../data/stage4-market-bars.json";
import r1 from "../../data/jev-5d-single-results/2026-08-07.json";
import r2 from "../../data/jev-5d-single-results/2026-08-14.json";
import r3 from "../../data/jev-5d-single-results/2026-08-21.json";
import r4 from "../../data/jev-5d-single-results/2026-08-28.json";
const ORIGINS=new Set(["2026-08-07","2026-08-14","2026-08-21","2026-08-28"]);
const RESULTS=[r1,r2,r3,r4];
const RAW="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data";
async function getj(u){const r=await fetch(u,{cache:"no-store"});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
function metrics(a){const n=a.length;if(!n)return {n:0};let ok=0,br=0,mp=0,ups=0,ms=0;for(const x of a){const y=x.actual>0?1:0;ok+=((x.p>=0.5)?1:0)===y;br+=(x.p-y)**2;mp+=x.p;ups+=y;ms+=x.s;}return {n,accuracy:ok/n,brier:br/n,mean_p:mp/n,up_frequency:ups/n,mean_run_std:ms/n}}
export const config={maxDuration:60};
export default async function handler(req,res){
 res.setHeader("Cache-Control","no-store");
 if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
 try{
  const idx=await getj(RAW+"/index.json");
  const qdates=marketData.QQQ.map(z=>new Date(z.t).toISOString().slice(0,10));
  const pmap=new Map();for(const o of RESULTS)for(const r of o.rows)pmap.set(o.origin+"|"+r.ticker,r);
  const need=new Map();
  for(const o of frozen.origins){if(!ORIGINS.has(o.origin))continue;const oi=qdates.indexOf(o.origin);const future=qdates.slice(oi+1,oi+6);for(const c of o.cases){const sh=idx.ticker_to_shard[c.ticker];if(!need.has(sh))need.set(sh,[]);need.get(sh).push({origin:o.origin,ticker:c.ticker,group:c.group,future});}}
  const rows=[];
  for(const [sh,items] of need){const obj=await getj(RAW+"/shard-"+String(sh).padStart(2,"0")+".json");for(const it of items){const mp=new Map((obj[it.ticker]||[]).map(r=>[String(r[0]).slice(0,10),r]));const a=it.future.map(d=>mp.get(d));if(a.some(x=>!x))continue;const entry=Number(a[0][1]),end=Number(a[4][4]),p=pmap.get(it.origin+"|"+it.ticker);if(!(entry>0)||!(end>0)||!p?.ok)continue;rows.push({origin:it.origin,ticker:it.ticker,group:it.group,actual:(end/entry-1)*100,p:Number(p.p_up),s:Number(p.run_std||0)});}}
  const bo={};for(const o of [...ORIGINS].sort())bo[o]=metrics(rows.filter(x=>x.origin===o));
  return res.status(200).json({ok:true,overall:metrics(rows),leader:metrics(rows.filter(x=>x.group==="leader")),hash_control:metrics(rows.filter(x=>x.group==="hash_control")),by_origin:bo});
 }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e)})}
}