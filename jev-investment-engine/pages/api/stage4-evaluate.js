import crypto from "crypto";
import { getVercelOidcToken } from "@vercel/oidc";
import frozen from "../../data/jev-5d-frozen-inputs.json";
import marketData from "../../data/stage4-market-bars.json";

const GATEWAY="https://ai-gateway.vercel.sh/v1/evaluate";
const MODEL="typesafe-ai/jev";
const RAW="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data";
function sha(x){return crypto.createHash("sha256").update(x).digest("hex")}
function mean(a){return a.reduce((x,y)=>x+y,0)/a.length}
function sd(a){if(a.length<2)return 0;const m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/a.length)}
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"jev-5d-eval"}});if(!r.ok)throw new Error("HTTP_"+r.status);return r.json()}
function costOf(x){const g=x?.providerMetadata?.gateway||x?.provider_metadata?.gateway||{};for(const k of ["cost","gatewayCost","inferenceCost"]){const n=Number(g[k]);if(Number.isFinite(n)&&n>=0)return n}return null}
function upProb(answer){
  const d=answer?.probabilities||answer?.distribution||answer?.choices;
  if(!d)throw new Error("distribution_missing");
  const u=Number(d.up),dn=Number(d.down);
  if(!Number.isFinite(u)||!Number.isFinite(dn)||u<0||dn<0||u+dn<=0)throw new Error("distribution_invalid");
  return u/(u+dn);
}
async function evaluate(state,questions){
  const token=process.env.AI_GATEWAY_API_KEY||process.env.VERCEL_OIDC_TOKEN||await getVercelOidcToken();
  if(!token)throw new Error("gateway_auth_unavailable");
  const runs=[];let knownCost=0,unknownCost=0;
  for(let i=0;i<3;i++){
    const r=await fetch(GATEWAY,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({model:MODEL,state,questions}),signal:AbortSignal.timeout(45000)});
    const text=await r.text();let body={};try{body=text?JSON.parse(text):{}}catch{throw new Error("gateway_non_json")}
    if(!r.ok)throw new Error("gateway_http_"+r.status);
    runs.push(body);const c=costOf(body);if(c==null)unknownCost++;else knownCost+=c;
  }
  return {runs,knownCost,unknownCost};
}
async function actuals(origin,cases){
  const q=marketData.QQQ.map(z=>new Date(z.t).toISOString().slice(0,10));
  const oi=q.indexOf(origin);if(oi<0||oi+5>=q.length)throw new Error("market_calendar_target_missing");
  const future=q.slice(oi+1,oi+6),idx=await fetchJson(RAW+"/index.json"),groups=new Map();
  for(const c of cases){const sh=idx.ticker_to_shard[c.ticker];if(!Number.isInteger(sh))continue;if(!groups.has(sh))groups.set(sh,[]);groups.get(sh).push(c.ticker)}
  const out={};
  for(const [sh,tickers] of groups){
    const obj=await fetchJson(RAW+`/shard-${String(sh).padStart(2,"0")}.json`);
    for(const tk of tickers){
      const rows=obj[tk]||[],mp=new Map(rows.map(r=>[String(r[0]).slice(0,10),r]));
      const a=future.map(d=>mp.get(d));if(a.some(x=>!x)){out[tk]={status:"missing_price"};continue}
      const entry=Number(a[0][1]),end=Number(a[4][4]);if(!(entry>0)&&!(end>0)){out[tk]={status:"invalid_price"};continue}
      out[tk]={status:"observed",entry_session:future[0],end_session:future[4],actual_5d_pct:(end/entry-1)*100};
    }
  }
  return out;
}
export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  const origin=String(req.query.origin||"");
  const snap=frozen.origins.find(x=>x.origin===origin);if(!snap)return res.status(400).json({ok:false,error:"origin_not_frozen"});
  try{
    const columns=Object.keys(snap.cases[0].features);
    const cases=snap.cases.map((c,i)=>({case_id:"c"+i,values:columns.map(k=>c.features[k]??null),missing:columns.filter(k=>c.features[k]==null)}));
    const state={contract:"Anonymized historical numeric forecast. Estimate whether each case's next-5-regular-session terminal simple return, measured from next-session OPEN to fifth-session CLOSE, will be strictly positive. Use only supplied numeric features. Do not infer security identity, date, news, or remembered outcomes.",feature_columns:columns,cases};
    const questions={};for(const c of cases)questions[c.case_id]={type:"choice",criteria:{up:"terminal return > 0",down:"terminal return <= 0"},instructions:"Return probabilities for both exhaustive directions. Do not estimate magnitude."};
    const stateText=JSON.stringify(state),questionText=JSON.stringify(questions);
    if(Buffer.byteLength(stateText,"utf8")>120000)throw new Error("state_too_large");
    // Critical ordering: all three Jev runs complete BEFORE any future-price request.
    const ev=await evaluate(state,questions);
    const preds=snap.cases.map((c,i)=>{const ps=ev.runs.map(r=>upProb(r.answers?.["c"+i]));return {ticker:c.ticker,origin,group:c.group,p_up:mean(ps),run_std:sd(ps),runs:ps}});
    const outcomes=await actuals(origin,snap.cases);
    const rows=preds.map(p=>({...p,...outcomes[p.ticker]}));
    return res.status(200).json({ok:true,version:"jev-5d-strong-stock-v1",model:MODEL,origin,input_sha256:snap.input_sha256,state_sha256:sha(stateText),questions_sha256:sha(questionText),runs_requested:3,cases:rows,known_gateway_cost_usd:ev.knownCost,cost_unknown_runs:ev.unknownCost,predictions_completed_before_outcomes:true});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1200)})}
}
