import d0 from "../../data/numeric-v2-origins/2026-07-10.json";
import d1 from "../../data/numeric-v2-origins/2026-07-17.json";
import d2 from "../../data/numeric-v2-origins/2026-07-24.json";
import d3 from "../../data/numeric-v2-origins/2026-07-31.json";
import d4 from "../../data/numeric-v2-origins/2026-08-07.json";
import d5 from "../../data/numeric-v2-origins/2026-08-14.json";
import d6 from "../../data/numeric-v2-origins/2026-08-21.json";
import d7 from "../../data/numeric-v2-origins/2026-08-28.json";
import d8 from "../../data/numeric-v2-origins/2026-09-04.json";
import d9 from "../../data/numeric-v2-origins/2026-09-14.json";
import d10 from "../../data/numeric-v2-origins/2026-09-21.json";
import { loadPyodide } from "pyodide";

const DATA=[d0,d1,d2,d3,d4,d5,d6,d7,d8,d9,d10];
let runtimePromise;
async function runtime(){ if(!runtimePromise) runtimePromise=loadPyodide(); return runtimePromise; }
export const config={maxDuration:120};

const PY=String.raw`
import json, math, statistics
D=json.loads(data_json)
ORIGINS=[d["origin"] for d in D]
FEATURES=D[0]["feature_columns"]
DEV_ORIGINS=ORIGINS[:6]
CAL_ORIGINS=ORIGINS[6:8]
EVAL_ORIGINS=ORIGINS[8:]
STOCK_FEATURES=FEATURES[:23]
MARKET_FEATURES=FEATURES[23:]
rows=[]
for d in D:
    for z in d["cases"]:
        x=z["features"]
        vol=x.get("vol20")
        scale=(float(vol)*math.sqrt(5)) if vol is not None and math.isfinite(float(vol)) and float(vol)>0 else None
        rows.append({"origin":z["origin"],"ticker":z["ticker"],"group":z["group"],"x":x,
                     "actual":float(z["actual_5d_pct"]),"y":1 if float(z["actual_5d_pct"])>0 else 0,
                     "scale":scale})
if len(rows)!=330: raise Exception("CASE_COUNT_"+str(len(rows)))

def mean(x): return sum(x)/len(x)
def samplestd(x):
    if len(x)<2:return None
    m=mean(x);return math.sqrt(sum((a-m)**2 for a in x)/(len(x)-1))
def median(x):
    return statistics.median(x)
def quantile(v,q):
    s=sorted(v)
    if not s:return None
    idx=min(len(s)-1,max(0,math.ceil(q*len(s))-1))
    return s[idx]
def sigmoid(z):
    if z>=0:return 1/(1+math.exp(-min(z,60)))
    e=math.exp(max(z,-60));return e/(1+e)

# Contemporaneous cross-sectional standardization uses only current-date inputs.
for r in rows:r["rel"]=dict(r["x"])
for origin in ORIGINS:
    rr=[r for r in rows if r["origin"]==origin]
    for k in STOCK_FEATURES:
        vals=[float(r["x"][k]) for r in rr if r["x"].get(k) is not None and math.isfinite(float(r["x"][k]))]
        if not vals:continue
        m=mean(vals);sd=samplestd(vals)
        for r in rr:
            v=r["x"].get(k)
            if v is None or not math.isfinite(float(v)): r["rel"][k]=None
            elif sd is None or sd<1e-9:r["rel"][k]=0.0
            else:r["rel"][k]=(float(v)-m)/sd

COMPACT=[
 "ret5","ret21","ret63","dist21","dist50","slope50","vol20","adr20","compression","rsi14",
 "dist_high63","volume_ratio","gap","close_location","body","rs63","rs189","excess21",
 "QQQ_ret5","QQQ_ret21","QQQ_dist50","QQQ_vol20","IWM_ret21","HYG_ret21","IEF_ret21",
 "^VIX_level","^VIX_change20","^TNX_level","^TNX_change20","breadth50","breadth50_change20","nhnl252"
]
COMPACT=[k for k in COMPACT if k in FEATURES]
COMPACT_STOCK=[k for k in COMPACT if k in STOCK_FEATURES]
COMPACT_MARKET=[k for k in COMPACT if k in MARKET_FEATURES or k=="excess21"]

def source_value(r,k,relative):
    return r["rel"].get(k) if relative and k in STOCK_FEATURES else r["x"].get(k)

def prep(train,features,relative):
    med={};mu={};sig={};usable=[]
    for k in features:
        vals=[float(source_value(r,k,relative)) for r in train
              if source_value(r,k,relative) is not None and math.isfinite(float(source_value(r,k,relative)))]
        if not vals:continue
        m=median(vals)
        z=[float(source_value(r,k,relative)) if source_value(r,k,relative) is not None and math.isfinite(float(source_value(r,k,relative))) else m for r in train]
        av=mean(z);sd=(sum((v-av)**2 for v in z)/len(z))**0.5
        if sd<1e-9:continue
        med[k]=m;mu[k]=av;sig[k]=sd;usable.append(k)
    return med,mu,sig,usable
def vec(r,state,relative):
    med,mu,sig,usable=state;out=[]
    for k in usable:
        v=source_value(r,k,relative)
        v=float(v) if v is not None and math.isfinite(float(v)) else med[k]
        out.append((v-mu[k])/sig[k])
    return out

def fit_logit(train,features,relative,lam,iters=450):
    state=prep(train,features,relative);X=[vec(r,state,relative) for r in train];Y=[r["y"] for r in train]
    base=mean(Y);b=math.log(max(base,1e-6)/max(1-base,1e-6));w=[0.0]*len(state[3]);lr=.05
    for _ in range(iters):
        gb=0.0;gw=[0.0]*len(w)
        for x,y in zip(X,Y):
            p=sigmoid(b+sum(a*z for a,z in zip(w,x)));e=p-y;gb+=e
            for j in range(len(w)):gw[j]+=e*x[j]
        n=len(Y);b-=lr*gb/n
        for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
    return {"state":state,"w":w,"b":b,"base":base,"relative":relative}
def pred_logit(m,rr):
    return [sigmoid(m["b"]+sum(a*z for a,z in zip(m["w"],vec(r,m["state"],m["relative"])))) for r in rr]
def brier(y,p):return mean([(a-b)**2 for a,b in zip(p,y)])
def accuracy(y,p):return mean([int((a>=.5)==bool(b)) for a,b in zip(p,y)])
def auc_score(y,p):
    pos=[p[i] for i,v in enumerate(y) if v==1];neg=[p[i] for i,v in enumerate(y) if v==0]
    if not pos or not neg:return None
    score=0
    for a in pos:
        for b in neg: score+=1 if a>b else .5 if a==b else 0
    return score/(len(pos)*len(neg))
def ranks(v):
    order=sorted(range(len(v)),key=lambda i:v[i]);out=[0.0]*len(v);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and v[order[j]]==v[order[i]]:j+=1
        val=((i+1)+j)/2
        for q in range(i,j):out[order[q]]=val
        i=j
    return out
def spearman(a,b):
    if len(a)<2:return None
    ra,rb=ranks(a),ranks(b);ma,mb=mean(ra),mean(rb)
    va=sum((x-ma)**2 for x in ra);vb=sum((x-mb)**2 for x in rb)
    return sum((x-ma)*(y-mb) for x,y in zip(ra,rb))/math.sqrt(va*vb) if va and vb else None
def cross_section_stats(rr,p):
    tops=[];bots=[];sp=[]
    for o in sorted(set(r["origin"] for r in rr)):
        idx=[i for i,r in enumerate(rr) if r["origin"]==o]
        if len(idx)<5:continue
        order=sorted(idx,key=lambda i:p[i]);n=max(1,len(idx)//5)
        bots.extend([rr[i]["actual"] for i in order[:n]])
        tops.extend([rr[i]["actual"] for i in order[-n:]])
        spv=spearman([p[i] for i in idx],[rr[i]["actual"] for i in idx])
        if spv is not None:sp.append(spv)
    return {"top_quintile_n":len(tops),"top_quintile_mean_return_pct":mean(tops) if tops else None,
            "bottom_quintile_n":len(bots),"bottom_quintile_mean_return_pct":mean(bots) if bots else None,
            "top_bottom_spread_pct":mean(tops)-mean(bots) if tops and bots else None,
            "mean_within_origin_spearman":mean(sp) if sp else None}
def direction_metrics(rr,p):
    y=[r["y"] for r in rr];pred=[a>=.5 for a in p]
    pos=[i for i,v in enumerate(y) if v];neg=[i for i,v in enumerate(y) if not v]
    tpr=mean([pred[i] for i in pos]) if pos else None
    tnr=mean([not pred[i] for i in neg]) if neg else None
    up=[rr[i]["actual"] for i in range(len(rr)) if pred[i]]
    dn=[rr[i]["actual"] for i in range(len(rr)) if not pred[i]]
    return {"n":len(rr),"accuracy":accuracy(y,p),"balanced_accuracy":(tpr+tnr)/2 if tpr is not None and tnr is not None else None,
            "brier":brier(y,p),"auc":auc_score(y,p),"mean_p":mean(p),"up_frequency":mean(y),
            "predicted_up_mean_return_pct":mean(up) if up else None,
            "predicted_down_mean_return_pct":mean(dn) if dn else None,
            **cross_section_stats(rr,p)}

CANDIDATES=[
 ("full_raw_l20",FEATURES,False,20),
 ("full_raw_l50",FEATURES,False,50),
 ("compact_raw_l10",COMPACT,False,10),
 ("compact_raw_l30",COMPACT,False,30),
 ("compact_rel_l10",COMPACT,True,10),
 ("compact_rel_l30",COMPACT,True,30),
 ("stock_rel_l10",COMPACT_STOCK,True,10),
 ("market_raw_l10",COMPACT_MARKET,False,10)
]
cv=[]
for name,features,relative,lam in CANDIDATES:
    bs=[];acs=[]
    # strictly chronological expanding validation: first three origins seed training
    for j in range(3,len(DEV_ORIGINS)):
        tr=[r for r in rows if r["origin"] in DEV_ORIGINS[:j]]
        va=[r for r in rows if r["origin"]==DEV_ORIGINS[j]]
        m=fit_logit(tr,features,relative,lam)
        p=pred_logit(m,va);y=[r["y"] for r in va]
        bs.append(brier(y,p));acs.append(accuracy(y,p))
    cv.append({"name":name,"relative":relative,"lambda":lam,"feature_count":len(features),
               "cv_brier":mean(bs),"cv_accuracy":mean(acs),"fold_brier":bs,"fold_accuracy":acs})
best=min(cv,key=lambda z:(z["cv_brier"],-z["cv_accuracy"],z["feature_count"]))
spec=next(x for x in CANDIDATES if x[0]==best["name"])
dev=[r for r in rows if r["origin"] in DEV_ORIGINS]
cal=[r for r in rows if r["origin"] in CAL_ORIGINS]
ev=[r for r in rows if r["origin"] in EVAL_ORIGINS]
mdev=fit_logit(dev,spec[1],spec[2],spec[3])
pcal=pred_logit(mdev,cal);ycal=[r["y"] for r in cal];base=mdev["base"]
alphas=[0,.25,.5,.75,1]
alpha=min(alphas,key=lambda a:brier(ycal,[base+a*(p-base) for p in pcal]))
cal_raw=direction_metrics(cal,pcal)
cal_shrunk=direction_metrics(cal,[base+alpha*(p-base) for p in pcal])

train_final=dev+cal
mfinal=fit_logit(train_final,spec[1],spec[2],spec[3])
base_final=mfinal["base"]
pfrozen=[base_final+alpha*(p-base_final) for p in pred_logit(mfinal,ev)]
constant=[base_final]*len(ev)

# secondary live-like expanding refit, with model class/hyperparameters already frozen
pexpand=[];expand_rows=[]
for o in EVAL_ORIGINS:
    tr=[r for r in rows if ORIGINS.index(r["origin"])<ORIGINS.index(o)]
    te=[r for r in rows if r["origin"]==o]
    mm=fit_logit(tr,spec[1],spec[2],spec[3])
    pp=[mm["base"]+alpha*(p-mm["base"]) for p in pred_logit(mm,te)]
    pexpand.extend(pp);expand_rows.extend(te)

eval_by_origin={}
for o in EVAL_ORIGINS:
    idx=[i for i,r in enumerate(ev) if r["origin"]==o]
    eval_by_origin[o]=direction_metrics([ev[i] for i in idx],[pfrozen[i] for i in idx])
eval_by_group={}
for g in ["leader","hash_control"]:
    idx=[i for i,r in enumerate(ev) if r["group"]==g]
    eval_by_group[g]=direction_metrics([ev[i] for i in idx],[pfrozen[i] for i in idx])

# -------- Range model ----------
RANGE_CAND=[
 ("range_compact_raw_l10",COMPACT,False,10),
 ("range_compact_raw_l30",COMPACT,False,30),
 ("range_compact_rel_l10",COMPACT,True,10),
 ("range_compact_rel_l30",COMPACT,True,30)
]
def fit_huber(train,features,relative,lam,iters=450):
    valid=[r for r in train if r["scale"] is not None and r["scale"]>1e-9]
    state=prep(valid,features,relative);X=[vec(r,state,relative) for r in valid]
    Y=[r["actual"]/r["scale"] for r in valid]
    b=median(Y);w=[0.0]*len(state[3]);lr=.03;delta=2.0
    for _ in range(iters):
        gb=0.0;gw=[0.0]*len(w)
        for x,y in zip(X,Y):
            e=b+sum(a*z for a,z in zip(w,x))-y
            g=max(-delta,min(delta,e));gb+=g
            for j in range(len(w)):gw[j]+=g*x[j]
        n=len(Y);b-=lr*gb/n
        for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
    return {"state":state,"w":w,"b":b,"relative":relative}
def pred_huber(m,rr):
    return [m["b"]+sum(a*z for a,z in zip(m["w"],vec(r,m["state"],m["relative"]))) for r in rr]
range_cv=[]
for name,features,relative,lam in RANGE_CAND:
    maes=[]
    for j in range(3,len(DEV_ORIGINS)):
        tr=[r for r in rows if r["origin"] in DEV_ORIGINS[:j]]
        va=[r for r in rows if r["origin"]==DEV_ORIGINS[j]]
        mm=fit_huber(tr,features,relative,lam)
        z=pred_huber(mm,va)
        maes.append(mean([abs(zz*r["scale"]-r["actual"]) for zz,r in zip(z,va)]))
    range_cv.append({"name":name,"relative":relative,"lambda":lam,"feature_count":len(features),"cv_mae_pct":mean(maes),"fold_mae_pct":maes})
rbest=min(range_cv,key=lambda z:(z["cv_mae_pct"],z["feature_count"]))
rspec=next(x for x in RANGE_CAND if x[0]==rbest["name"])
rmdev=fit_huber(dev,rspec[1],rspec[2],rspec[3])
zcal=pred_huber(rmdev,cal)
resz=[(r["actual"]-zz*r["scale"])/r["scale"] for zz,r in zip(zcal,cal) if r["scale"] and r["scale"]>1e-9]
rq10,rq90=quantile(resz,.1),quantile(resz,.9)
rmfinal=fit_huber(train_final,rspec[1],rspec[2],rspec[3])
zev=pred_huber(rmfinal,ev)
center=[z*r["scale"] for z,r in zip(zev,ev)]
lower=[c+rq10*r["scale"] for c,r in zip(center,ev)]
upper=[c+rq90*r["scale"] for c,r in zip(center,ev)]
trainz=[r["actual"]/r["scale"] for r in train_final if r["scale"] and r["scale"]>1e-9]
bq10,bq50,bq90=quantile(trainz,.1),quantile(trainz,.5),quantile(trainz,.9)
bcenter=[bq50*r["scale"] for r in ev];bl=[bq10*r["scale"] for r in ev];bu=[bq90*r["scale"] for r in ev]
def range_metrics(rr,center,lo,hi):
    ae=[abs(c-r["actual"]) for c,r in zip(center,rr)]
    cov=[l<=r["actual"]<=u for l,u,r in zip(lo,hi,rr)]
    widths=[u-l for l,u in zip(lo,hi)]
    score=[u-l+10*max(l-r["actual"],0)+10*max(r["actual"]-u,0) for l,u,r in zip(lo,hi,rr)]
    return {"n":len(rr),"mae_pct":mean(ae),"median_ae_pct":median(ae),"coverage80":mean(cov),
            "mean_width_pct":mean(widths),"interval_score":mean(score),"mean_center_pct":mean(center)}
range_by_origin={}
for o in EVAL_ORIGINS:
    idx=[i for i,r in enumerate(ev) if r["origin"]==o]
    rr=[ev[i] for i in idx]
    range_by_origin[o]={
      "huber":range_metrics(rr,[center[i] for i in idx],[lower[i] for i in idx],[upper[i] for i in idx]),
      "vol_baseline":range_metrics(rr,[bcenter[i] for i in idx],[bl[i] for i in idx],[bu[i] for i in idx])
    }

out={
 "version":"numeric-v2-analysis-20260930",
 "cases":len(rows),"origins":ORIGINS,"development_origins":DEV_ORIGINS,"calibration_origins":CAL_ORIGINS,"evaluation_origins":EVAL_ORIGINS,
 "origin_summaries":[d["summary"] for d in D],
 "direction":{
   "candidate_cv":cv,"selected":best,"calibration_shrink_alpha":alpha,
   "calibration_raw":cal_raw,"calibration_shrunk":cal_shrunk,
   "evaluation_constant":direction_metrics(ev,constant),
   "evaluation_frozen":direction_metrics(ev,pfrozen),
   "evaluation_expanding":direction_metrics(expand_rows,pexpand),
   "evaluation_by_origin":eval_by_origin,"evaluation_by_group":eval_by_group
 },
 "range":{
   "candidate_cv":range_cv,"selected":rbest,"calibration_residual_q10":rq10,"calibration_residual_q90":rq90,
   "evaluation_huber":range_metrics(ev,center,lower,upper),
   "evaluation_vol_baseline":range_metrics(ev,bcenter,bl,bu),
   "evaluation_by_origin":range_by_origin
 },
 "missing_feature_counts":{k:sum(1 for r in rows if r["x"].get(k) is None) for k in FEATURES},
 "limitations":[
   "Current reconstructed universe; historical membership is not PIT.",
   "Structural clinical-biotech exclusion is unavailable historically and not fabricated.",
   "Evaluation dates were inspected in prior research; this is a locked retrospective replay, not a pristine unseen holdout.",
   "No Jev, news, or options are used in numeric-v2."
 ]
}
json.dumps(out,allow_nan=False)
`;

export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview")return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const py=await runtime();
    py.globals.set("data_json",JSON.stringify(DATA));
    const v=await py.runPythonAsync(PY);
    const out=JSON.parse(String(v));
    if(v?.destroy)v.destroy();
    return res.status(200).json({ok:true,...out});
  }catch(e){
    return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1600)});
  }
}
