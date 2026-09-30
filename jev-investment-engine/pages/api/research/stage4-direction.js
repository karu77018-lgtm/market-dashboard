import { getVercelOidcToken } from "@vercel/oidc";
import casesData from "../../../data/stage4-direction-expand.json";

const GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/evaluate";
const MODEL = "typesafe-ai/jev";

function mean(xs){ return xs.reduce((a,b)=>a+b,0)/xs.length; }

function decodeNoul(obj, qid){
  if(!obj || !obj.answers || !obj.answers[qid]) throw new Error("ANSWER_MISSING");
  const a=obj.answers[qid];
  const v=Number(a.noul ?? a.probability);
  if(!Number.isFinite(v) || v<0 || v>1) throw new Error("INVALID_NOUL");
  return v;
}

async function evaluateThree(state, questions){
  const token = process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || await getVercelOidcToken();
  if(!token) throw new Error("GATEWAY_AUTH_UNAVAILABLE");
  const runs=[]; let cost=0;
  for(let i=0;i<3;i++){
    const r=await fetch(GATEWAY_URL,{
      method:"POST",
      headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
      body:JSON.stringify({model:MODEL,state,questions}),
      signal:AbortSignal.timeout(45000)
    });
    const text=await r.text(); let obj={};
    try{obj=text?JSON.parse(text):{};}catch{throw new Error("NON_JSON");}
    if(!r.ok) throw new Error("GATEWAY_HTTP_"+r.status);
    runs.push(obj);
    const g=obj?.providerMetadata?.gateway||obj?.provider_metadata?.gateway||{};
    const c=Number(g.cost ?? g.gatewayCost ?? g.inferenceCost ?? 0);
    if(Number.isFinite(c)&&c>=0) cost+=c;
  }
  return {runs,cost};
}

export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  if(req.method!=="GET") return res.status(405).json({ok:false,error:"method_not_allowed"});
  const idx=Number(req.query.case);
  const mode=req.query.mode==="news"?"news":"technical";
  if(!Number.isInteger(idx)||idx<0||idx>=casesData.cases.length) return res.status(400).json({ok:false,error:"invalid_case"});
  const c=casesData.cases[idx];
  const features=Object.fromEntries(casesData.feature_columns.map((k,i)=>[k,c.features[i]??null]));
  let materials=[];
  if(mode==="news" && typeof req.query.facts==="string" && req.query.facts.length){
    try{
      const decoded=JSON.parse(Buffer.from(req.query.facts,"base64url").toString("utf8"));
      if(!Array.isArray(decoded)||decoded.length>12) return res.status(400).json({ok:false,error:"invalid_facts_shape"});
      materials=decoded.map((x,i)=>({
        evidence_id:String(x.id||("fact-"+i)),
        published_utc:String(x.published_utc||""),
        title:String(x.title||"").slice(0,240),
        description:String(x.description||"").slice(0,900),
        publisher:String(x.publisher||"Massive-derived factual summary")
      }));
    }catch{return res.status(400).json({ok:false,error:"invalid_facts"});}
  }
  const state={
    task:"Estimate only the probability that this ONE issuer's terminal simple return is positive over the next 5 and 10 regular sessions, measured from the OPEN of the next regular session to the CLOSE of the horizon session. Use only supplied past information. Do not browse, identify future outcomes from memory, or reinterpret missing news as neutral.",
    input_features:features,
    missing_fields:Object.entries(features).filter(([,v])=>v===null).map(([k])=>k),
    material_mode:mode==="news"?"supplied":"withheld_for_control_not_evidence_of_no_events",
    units:"ret/dist/slope/gap/body/excess/ADR/vol values are percent; vol20 is daily simple-return standard deviation in percentage points. RS, RSI and breadth are 0-100. volume_ratio/compression/close_location/beta/corr are ratios. VIX uses index points; TNX uses supplied quoted units."
  };
  if(mode==="news") state.company_materials=materials;
  const questions={
    up5:{type:"noul",instructions:"Probability from 0 to 1 that the 5-session terminal simple return defined in the task is strictly greater than 0. Do not output magnitude."},
    up10:{type:"noul",instructions:"Probability from 0 to 1 that the 10-session terminal simple return defined in the task is strictly greater than 0. Do not output magnitude."}
  };
  try{
    const raw=JSON.stringify({state,questions});
    if(Buffer.byteLength(raw,"utf8")>90000) return res.status(413).json({ok:false,error:"payload_too_large"});
    const out=await evaluateThree(state,questions);
    const p5=out.runs.map(x=>decodeNoul(x,"up5"));
    const p10=out.runs.map(x=>decodeNoul(x,"up10"));
    return res.status(200).json({ok:true,case_index:idx,ticker:c.ticker,origin:c.origin,mode,feature_count:59,news_count:materials.length,
      p_up5:mean(p5),p_up10:mean(p10),runs5:p5,runs10:p10,
      agreement5_std:Math.sqrt(mean(p5.map(x=>(x-mean(p5))**2))),
      agreement10_std:Math.sqrt(mean(p10.map(x=>(x-mean(p10))**2))),
      gatewayCostUsd:out.cost});
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||"direction_failed")});}
}
