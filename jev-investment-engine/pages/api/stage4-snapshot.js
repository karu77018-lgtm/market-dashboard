import crypto from "crypto";
import marketData from "../../data/stage4-market-bars.json";

const PRICE_COMMIT="d84a70dd46df011df502217f2737ed08a1e90fa2";
const RAW=`https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/${PRICE_COMMIT}/chart-data`;
const ORIGINS=new Set(["2026-08-07","2026-08-14","2026-08-21","2026-08-28","2026-09-04","2026-09-14","2026-09-21"]);
const FEATURES=["ret1","ret5","ret21","ret63","ret126","ret189","dist21","dist50","dist200","slope50","vol20","adr20","compression","rsi14","dist_high63","dist_high252","volume_ratio","log_ddv","gap","close_location","body","rs63","rs189","QQQ_ret5","QQQ_ret21","QQQ_ret63","QQQ_dist50","QQQ_vol20","SPY_ret5","SPY_ret21","SPY_ret63","SPY_dist50","SPY_vol20","IWM_ret5","IWM_ret21","IWM_ret63","IWM_dist50","IWM_vol20","HYG_ret5","HYG_ret21","HYG_ret63","HYG_dist50","HYG_vol20","IEF_ret5","IEF_ret21","IEF_ret63","IEF_dist50","IEF_vol20","^VIX_level","^VIX_change20","^TNX_level","^TNX_change20","breadth50","breadth200","breadth50_change20","nhnl252","beta63","corr63","excess21"];
let indexPromise, macroPromise;

function mean(a){return a.reduce((x,y)=>x+y,0)/a.length}
function stdev(a){if(a.length<2)return null;const m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1))}
function pct(a,b){return (a!=null&&b)?(a/b-1)*100:null}
function sma(c,n,i){if(i-n+1<0)return null;const x=c.slice(i-n+1,i+1);return x.length===n&&x.every(Number.isFinite)?mean(x):null}
function ret(c,n,i){return i-n>=0&&Number.isFinite(c[i])&&Number.isFinite(c[i-n])?pct(c[i],c[i-n]):null}
function sha(s){return crypto.createHash("sha256").update(s).digest("hex")}
function normRows(rows){return rows.map(r=>[String(r[0]).slice(0,10),...r.slice(1,6).map(x=>x==null?null:Number(x))])}
function findIndex(rows,origin){for(let i=rows.length-1;i>=0;i--)if(rows[i][0]===origin)return i;return -1}
function median(a){const z=[...a].sort((x,y)=>x-y),n=z.length;return n? n%2?z[(n-1)/2]:(z[n/2-1]+z[n/2])/2:null}
function wilderRsi(c,i,n=14){
  if(i<n)return null;let ds=[];for(let j=1;j<=i;j++){if(!Number.isFinite(c[j])||!Number.isFinite(c[j-1]))continue;ds.push(c[j]-c[j-1])}
  if(ds.length<n)return null;let ag=mean(ds.slice(0,n).map(x=>Math.max(x,0))),al=mean(ds.slice(0,n).map(x=>Math.max(-x,0)));
  for(const d of ds.slice(n)){ag=(ag*(n-1)+Math.max(d,0))/n;al=(al*(n-1)+Math.max(-d,0))/n}
  return al===0?100:100-100/(1+ag/al)
}
function percentileMap(items,key){
  const vals=items.map(x=>x[key]).filter(Number.isFinite).sort((a,b)=>a-b);const out=new Map();
  for(const x of items){const v=x[key];if(!Number.isFinite(v)){out.set(x.ticker,null);continue}
    let lo=0,hi=vals.length;while(lo<hi){const m=(lo+hi)>>1;if(vals[m]<v)lo=m+1;else hi=m}const first=lo;
    lo=0;hi=vals.length;while(lo<hi){const m=(lo+hi)>>1;if(vals[m]<=v)lo=m+1;else hi=m}const last=lo;
    out.set(x.ticker,100*(first+(last-first+1)/2)/vals.length);
  }return out
}
function marketSeries(tk){
  return marketData[tk].map(z=>[new Date(z.t).toISOString().slice(0,10),Number(z.o),Number(z.h),Number(z.l),Number(z.c),Number(z.v)]);
}
function marketFeatures(tk,origin){
  const r=marketSeries(tk).filter(x=>x[0]<=origin),i=r.findIndex(x=>x[0]===origin);if(i<63)return {};
  const c=r.map(x=>x[4]),s50=sma(c,50,i),rr=[];for(let j=i-19;j<=i;j++)rr.push((c[j]/c[j-1]-1)*100);
  return {[`${tk}_ret5`]:ret(c,5,i),[`${tk}_ret21`]:ret(c,21,i),[`${tk}_ret63`]:ret(c,63,i),[`${tk}_dist50`]:pct(c[i],s50),[`${tk}_vol20`]:stdev(rr)}
}
async function fetchJson(url){const r=await fetch(url,{cache:"no-store",headers:{"User-Agent":"jev-5d-research"}});if(!r.ok)throw new Error("HTTP_"+r.status+"_"+url);return r.json()}
async function getIndex(){if(!indexPromise)indexPromise=fetchJson(RAW+"/index.json");return indexPromise}
async function getMacro(){
  if(!macroPromise)macroPromise=(async()=>{
    async function fred(id){const r=await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}&cosd=2025-10-01&coed=2026-09-28`,{cache:"no-store"});if(!r.ok)throw new Error("FRED_"+id+"_"+r.status);const t=await r.text();const lines=t.trim().split(/\r?\n/).slice(1);return lines.map(x=>x.split(",")).filter(x=>x.length>=2&&x[1]!==".").map(x=>[x[0],Number(x[1])]).filter(x=>Number.isFinite(x[1]))}
    return {VIX:await fred("VIXCLS"),TNX:await fred("DGS10")};
  })();return macroPromise
}
function macroAt(series,origin){const z=series.filter(x=>x[0]<=origin);if(!z.length)return [null,null];const i=z.length-1;return [z[i][1],i>=20?z[i][1]-z[i-20][1]:null]}

function basicStats(rows,origin){
  const r=normRows(rows),i=findIndex(r,origin);if(i<200)return null;
  const c=r.map(x=>x[4]),v=r.map(x=>x[5]),close=c[i],s50=sma(c,50,i),s200=sma(c,200,i);
  if(!Number.isFinite(close)||!Number.isFinite(s50)||!Number.isFinite(s200))return null;
  const dd=[];for(let j=i-19;j<=i;j++)if(Number.isFinite(c[j])&&Number.isFinite(v[j]))dd.push(c[j]*v[j]);
  const ddv=median(dd),r63=ret(c,63,i),r189=ret(c,189,i);
  const p50i=i-20,s50p=p50i>=49?sma(c,50,p50i):null;
  const above50past=Number.isFinite(s50p)&&Number.isFinite(c[p50i])?c[p50i]>s50p:null;
  let hi252=null,lo252=null;if(i>=251){const hs=r.slice(i-251,i+1).map(x=>x[2]).filter(Number.isFinite),ls=r.slice(i-251,i+1).map(x=>x[3]).filter(Number.isFinite);if(hs.length===252&&ls.length===252){hi252=Math.max(...hs);lo252=Math.min(...ls)}}
  return {ticker:null,rows:r,i,close,s50,s200,ddv,r63,r189,above50:close>s50,above200:close>s200,above50past,hi252,lo252};
}
function fullFeatures(s,rs63,rs189,origin,ctx){
  const r=s.rows,i=s.i,c=r.map(x=>x[4]),o=r.map(x=>x[1]),h=r.map(x=>x[2]),l=r.map(x=>x[3]),v=r.map(x=>x[5]),f={};
  for(const n of [1,5,21,63,126,189])f["ret"+n]=ret(c,n,i);
  for(const n of [21,50,200])f["dist"+n]=pct(c[i],sma(c,n,i));
  f.slope50=pct(sma(c,50,i),sma(c,50,i-10));
  const dr=[];for(let j=i-19;j<=i;j++)dr.push((c[j]/c[j-1]-1)*100);f.vol20=stdev(dr);
  const adr=[];for(let j=i-19;j<=i;j++)adr.push((h[j]/l[j]-1)*100);f.adr20=mean(adr);f.compression=mean(adr.slice(-5))/f.adr20;
  f.rsi14=wilderRsi(c,i);f.dist_high63=pct(c[i],Math.max(...h.slice(i-62,i+1)));f.dist_high252=i>=251?pct(c[i],Math.max(...h.slice(i-251,i+1))):null;
  f.volume_ratio=v[i]/mean(v.slice(i-19,i+1));const dd=[];for(let j=i-19;j<=i;j++)dd.push(c[j]*v[j]);f.log_ddv=Math.log1p(median(dd));
  f.gap=pct(o[i],c[i-1]);f.close_location=h[i]!==l[i]?(c[i]-l[i])/(h[i]-l[i]):null;f.body=pct(c[i],o[i]);f.rs63=rs63;f.rs189=rs189;
  Object.assign(f,ctx.market,ctx.macro,ctx.breadth);
  const q=ctx.qqq, qm=new Map(q.map(x=>[x[0],x[4]])),sm=new Map(r.map(x=>[x[0],x[4]]));const common=r.slice(0,i+1).map(x=>x[0]).filter(d=>qm.has(d)).slice(-64);
  if(common.length===64){const sr=[],qr=[];for(let j=1;j<64;j++){sr.push(sm.get(common[j])/sm.get(common[j-1])-1);qr.push(qm.get(common[j])/qm.get(common[j-1])-1)}const ms=mean(sr),mq=mean(qr),cov=sr.reduce((a,x,j)=>a+(x-ms)*(qr[j]-mq),0),vs=sr.reduce((a,x)=>a+(x-ms)**2,0),vq=qr.reduce((a,x)=>a+(x-mq)**2,0);f.beta63=vq?cov/vq:null;f.corr63=vs&&vq?cov/Math.sqrt(vs*vq):null}else{f.beta63=null;f.corr63=null}
  f.excess21=Number.isFinite(f.ret21)&&Number.isFinite(f.QQQ_ret21)?f.ret21-f.QQQ_ret21:null;
  return Object.fromEntries(FEATURES.map(k=>[k,Number.isFinite(f[k])?f[k]:null]));
}
export const config={maxDuration:60};
export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  const origin=String(req.query.origin||"");if(!ORIGINS.has(origin))return res.status(400).json({ok:false,error:"origin_not_frozen"});
  try{
    const idx=await getIndex(),rankBase=[],basic=[],breadthRaw={n50:0,a50:0,n200:0,a200:0,p50n:0,p50a:0,nh:0,nl:0,n252:0};
    for(let sh=0;sh<idx.shard_count;sh++){
      const obj=await fetchJson(RAW+`/shard-${String(sh).padStart(2,"0")}.json`);
      for(const [ticker,rows] of Object.entries(obj)){
        const s=basicStats(rows,origin);if(!s)continue;s.ticker=ticker;
        if(Number.isFinite(s.s50)){breadthRaw.n50++;if(s.above50)breadthRaw.a50++}
        if(Number.isFinite(s.s200)){breadthRaw.n200++;if(s.above200)breadthRaw.a200++}
        if(s.above50past!==null){breadthRaw.p50n++;if(s.above50past)breadthRaw.p50a++}
        if(Number.isFinite(s.hi252)&&Number.isFinite(s.lo252)){breadthRaw.n252++;if(s.close>=s.hi252)breadthRaw.nh++;if(s.close<=s.lo252)breadthRaw.nl++}
        if(s.close>=5&&s.ddv>=1e7&&Number.isFinite(s.r63)&&Number.isFinite(s.r189)){rankBase.push(s);if(s.s50>s.s200&&s.close>s.s200)basic.push(s)}
      }
    }
    const p63=percentileMap(rankBase,"r63"),p189=percentileMap(rankBase,"r189");
    const eligible=basic.map(s=>({...s,rs63:p63.get(s.ticker),rs189:p189.get(s.ticker)})).filter(s=>s.rs63>=85&&s.rs189>=85);
    eligible.sort((a,b)=>b.rs189-a.rs189||b.rs63-a.rs63||a.ticker.localeCompare(b.ticker));
    const leaders=eligible.slice(0,10);const used=new Set(leaders.map(x=>x.ticker));const controls=eligible.filter(x=>!used.has(x.ticker)).sort((a,b)=>sha(origin+"|"+a.ticker).localeCompare(sha(origin+"|"+b.ticker))).slice(0,10);
    const selected=[...leaders.map(x=>[x,"leader"]),...controls.map(x=>[x,"hash_control"])];
    const market={};for(const tk of ["QQQ","SPY","IWM","HYG","IEF"])Object.assign(market,marketFeatures(tk,origin));
    const qqq=marketSeries("QQQ").filter(x=>x[0]<=origin),macro=await getMacro(),[vix,vixchg]=macroAt(macro.VIX,origin),[tnx,tnxchg]=macroAt(macro.TNX,origin);
    const breadth={breadth50:breadthRaw.n50?100*breadthRaw.a50/breadthRaw.n50:null,breadth200:breadthRaw.n200?100*breadthRaw.a200/breadthRaw.n200:null,breadth50_change20:breadthRaw.n50&&breadthRaw.p50n?100*breadthRaw.a50/breadthRaw.n50-100*breadthRaw.p50a/breadthRaw.p50n:null,nhnl252:breadthRaw.n252/rankBase.length>=0.7?100*(breadthRaw.nh-breadthRaw.nl)/breadthRaw.n252:null};
    const mctx={market,macro:{"^VIX_level":vix,"^VIX_change20":vixchg,"^TNX_level":tnx,"^TNX_change20":tnxchg},breadth,qqq};
    const cases=selected.map(([s,group])=>({ticker:s.ticker,origin,group,features:fullFeatures(s,s.rs63,s.rs189,origin,mctx)}));
    const payload={ok:true,protocol:"jev-5d-strong-stock-v1",origin,eligible_count:eligible.length,rank_universe_count:rankBase.length,selected_count:cases.length,feature_count:FEATURES.length,selection:[...leaders.map(x=>x.ticker),...controls.map(x=>x.ticker)],cases,coverage:{breadth50:breadthRaw.n50,breadth200:breadthRaw.n200,nhnl252:breadthRaw.n252},future_outcomes_read:false};
    payload.input_sha256=sha(JSON.stringify(payload.cases));
    return res.status(200).json(payload);
  }catch(e){return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1200)})}
}