import { getVercelOidcToken } from "@vercel/oidc";
import frozen from "../../data/jev-5d-frozen-inputs.json";
const GATEWAY="https://ai-gateway.vercel.sh/v1/evaluate";
const MODEL="typesafe-ai/jev";
function mean(a){return a.reduce((x,y)=>x+y,0)/a.length}
function sd(a){if(a.length<2)return 0;const m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/a.length)}
function upProb(a){const d=a?.probabilities||a?.distribution||a?.choices;if(!d)throw new Error("distribution_missing");const u=Number(d.up),dn=Number(d.down);if(!Number.isFinite(u)||!Number.isFinite(dn)||u<0||dn<0||u+dn<=0)throw new Error("distribution_invalid");return u/(u+dn)}
async function runOnce(state,questions,token){
 const r=await fetch(GATEWAY,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({model:MODEL,state,questions}),signal:AbortSignal.timeout(45000)});
 const text=await r.text();let body={};try{body=text?JSON.parse(text):{}}catch{throw new Error("gateway_non_json")};if(!r.ok)throw new Error("gateway_http_"+r.status);return body
}
export const config={maxDuration:60};
export default async function handler(req,res){
 res.setHeader("Cache-Control","no-store");
 if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
 const origin=String(req.query.origin||"");const idx=Number(req.query.case);
 const snap=frozen.origins.find(x=>x.origin===origin);if(!snap||!Number.isInteger(idx)||idx<0||idx>=snap.cases.length)return res.status(400).json({ok:false,error:"invalid_frozen_case"});
 try{
  const c=snap.cases[idx],columns=Object.keys(c.features),state={contract:"Anonymized historical numeric forecast. Estimate whether this ONE case's next-5-regular-session terminal simple return, measured from next-session OPEN to fifth-session CLOSE, will be strictly positive. Use only supplied numeric features. Do not infer security identity, date, news, or remembered outcomes.",feature_columns:columns,case:{case_id:"c0",values:columns.map(k=>c.features[k]??null),missing:columns.filter(k=>c.features[k]==null)}};
  const questions={c0:{type:"choice",criteria:{up:"terminal return > 0",down:"terminal return <= 0"},instructions:"Return probabilities for both exhaustive directions. Do not estimate magnitude."}};
  const token=process.env.AI_GATEWAY_API_KEY||process.env.VERCEL_OIDC_TOKEN||await getVercelOidcToken();if(!token)throw new Error("gateway_auth_unavailable");
  const runs=[];for(let i=0;i<3;i++){const b=await runOnce(state,questions,token);runs.push(upProb(b.answers?.c0))}
  return res.status(200).json({ok:true,origin,case_index:idx,ticker:c.ticker,group:c.group,p_up:mean(runs),run_std:sd(runs),runs});
 }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e)})}
}