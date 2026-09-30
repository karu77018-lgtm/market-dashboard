import marketData from "../../data/stage4-market-bars.json";
import expectedData from "../../data/stage4-direction-expand.json";

let runtimePromise;
async function getRuntime(){
  if(!runtimePromise){
    runtimePromise=(async()=>{
      const { loadPyodide } = await import("pyodide");
      return await loadPyodide();
    })();
  }
  return runtimePromise;
}
export const config={maxDuration:120};

async function fetchJson(url){
  const r=await fetch(url,{headers:{"User-Agent":"jev-research"}});
  if(!r.ok) throw new Error("FETCH_"+r.status+"_"+url);
  return await r.json();
}
async function fetchText(url){
  const r=await fetch(url,{headers:{"User-Agent":"jev-research"}});
  if(!r.ok) throw new Error("FETCH_"+r.status+"_"+url);
  return await r.text();
}

const PY = String.raw`
import json, math, statistics, hashlib, csv, io
from datetime import datetime, timezone

U=json.loads(universe_json)
M=json.loads(market_json)
E=json.loads(expected_json)
fred_text=fred_csv_text
ORIGINS=["2026-06-25","2026-07-02","2026-07-10","2026-07-17","2026-07-24","2026-07-31","2026-08-07","2026-08-14","2026-08-21","2026-08-28","2026-09-04","2026-09-14","2026-09-21"]
FEATURES=E["feature_columns"]

def mean(x): return sum(x)/len(x)
def samplestd(x):
    if len(x)<2:return None
    m=mean(x);return math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
def pct(a,b): return (a/b-1)*100 if b not in (None,0) else None
def sma(x,n,i):
    if i-n+1<0:return None
    z=x[i-n+1:i+1]
    return mean(z) if len(z)==n else None
def ret(x,n,i):
    if i-n<0:return None
    return pct(x[i],x[i-n])
def wilder_rsi(c,i,n=14):
    if i<n:return None
    d=[c[j]-c[j-1] for j in range(1,i+1)]
    if len(d)<n:return None
    ag=mean([max(x,0) for x in d[:n]]);al=mean([max(-x,0) for x in d[:n]])
    for x in d[n:]:
        ag=(ag*(n-1)+max(x,0))/n
        al=(al*(n-1)+max(-x,0))/n
    return 100.0 if al==0 else 100-100/(1+ag/al)
def avg_rank_pct(vals):
    items=sorted((v,k) for k,v in vals.items() if v is not None and math.isfinite(v))
    n=len(items); out={}; p=0
    while p<n:
        q=p+1
        while q<n and items[q][0]==items[p][0]: q+=1
        avg_rank=((p+1)+q)/2.0
        rank=100.0*avg_rank/n
        for j in range(p,q):out[items[j][1]]=rank
        p=q
    return out

def normalize_rows(rows):
    out=[]
    for r in rows:
        try:
            d=str(r[0])[:10]
            out.append((d,float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5])))
        except: pass
    return out

SER={k:normalize_rows(v) for k,v in U.items()}
# Massive market data
MARKET={}
for k,arr in M.items():
    rr=[]
    for z in arr:
        d=datetime.fromtimestamp(float(z["t"])/1000,timezone.utc).date().isoformat()
        rr.append((d,float(z["o"]),float(z["h"]),float(z["l"]),float(z["c"]),float(z["v"])))
    MARKET[k]=rr

# FRED VIXCLS,DGS10
FRED={"VIXCLS":{},"DGS10":{}}
reader=csv.DictReader(io.StringIO(fred_text))
for row in reader:
    d=row.get("DATE") or row.get("observation_date")
    if not d: continue
    for key in ["VIXCLS","DGS10"]:
        v=row.get(key)
        try:FRED[key][d]=float(v)
        except:pass

def context(rows,origin):
    dates=[r[0] for r in rows]
    if origin not in dates:return None
    i=dates.index(origin)
    sub=rows[:i+1]
    if len(sub)<21:return None
    o=[r[1] for r in sub];h=[r[2] for r in sub];l=[r[3] for r in sub];c=[r[4] for r in sub];v=[r[5] for r in sub]
    return dates,i,o,h,l,c,v

def basic_at(rows,origin):
    z=context(rows,origin)
    if not z:return None
    dates,i,o,h,l,c,v=z;i=len(c)-1
    s50=sma(c,50,i);s200=sma(c,200,i)
    ddv=None
    if len(c)>=20:
        ddv=statistics.median([c[j]*v[j] for j in range(i-19,i+1)])
    return {
      "close":c[i],"sma50":s50,"sma200":s200,"ddv20":ddv,
      "ret63":ret(c,63,i),"ret189":ret(c,189,i),
      "above50":(c[i]>s50) if s50 else None,
      "above200":(c[i]>s200) if s200 else None
    }

def market_feature(rows,origin,prefix):
    z=context(rows,origin)
    if not z:return {}
    dates,_,o,h,l,c,v=z;i=len(c)-1
    out={}
    for n in [5,21,63]:out[prefix+"_ret"+str(n)]=ret(c,n,i)
    s50=sma(c,50,i);out[prefix+"_dist50"]=pct(c[i],s50) if s50 else None
    if i>=20:
        rr=[(c[j]/c[j-1]-1)*100 for j in range(i-19,i+1)]
        out[prefix+"_vol20"]=samplestd(rr)
    else:out[prefix+"_vol20"]=None
    return out

def fred_pair(key,origin):
    dates=sorted(d for d in FRED[key] if d<=origin)
    if not dates:return (None,None)
    last=dates[-1]; val=FRED[key][last]
    ch=val-FRED[key][dates[-21]] if len(dates)>=21 else None
    return val,ch

def stock_features(tk,origin,rank63,rank189,b50,b200,b50chg,nhnl):
    rows=SER[tk];z=context(rows,origin)
    if not z:return None
    dates,_,o,h,l,c,v=z;i=len(c)-1
    if i<20:return None
    x={}
    for n in [1,5,21,63,126,189]:x["ret"+str(n)]=ret(c,n,i)
    for n in [21,50,200]:
        s=sma(c,n,i);x["dist"+str(n)]=pct(c[i],s) if s else None
    s0=sma(c,50,i);s10=sma(c,50,i-10)
    x["slope50"]=pct(s0,s10) if s0 and s10 else None
    rr=[(c[j]/c[j-1]-1)*100 for j in range(i-19,i+1)]
    x["vol20"]=samplestd(rr)
    adr=[(h[j]/l[j]-1)*100 for j in range(i-19,i+1)]
    x["adr20"]=mean(adr)
    x["compression"]=mean(adr[-5:])/mean(adr) if mean(adr) else None
    x["rsi14"]=wilder_rsi(c,i)
    x["dist_high63"]=pct(c[i],max(h[-63:])) if len(h)>=63 else None
    x["dist_high252"]=pct(c[i],max(h[-252:])) if len(h)>=252 else None
    x["volume_ratio"]=v[i]/mean(v[-20:]) if mean(v[-20:]) else None
    x["log_ddv"]=math.log1p(statistics.median([c[j]*v[j] for j in range(i-19,i+1)]))
    x["gap"]=pct(o[i],c[i-1])
    x["close_location"]=(c[i]-l[i])/(h[i]-l[i]) if h[i]!=l[i] else None
    x["body"]=pct(c[i],o[i])
    x["rs63"]=rank63.get(tk);x["rs189"]=rank189.get(tk)
    for key in ["QQQ","SPY","IWM","HYG","IEF"]:
        x.update(market_feature(MARKET[key],origin,key))
    vix,vixchg=fred_pair("VIXCLS",origin);tnx,tnxchg=fred_pair("DGS10",origin)
    x["^VIX_level"]=vix;x["^VIX_change20"]=vixchg
    x["^TNX_level"]=tnx;x["^TNX_change20"]=tnxchg
    x["breadth50"]=b50;x["breadth200"]=b200;x["breadth50_change20"]=b50chg;x["nhnl252"]=nhnl
    # beta/corr 63 aligned to QQQ
    qmap={r[0]:r[4] for r in MARKET["QQQ"]}
    smap={r[0]:r[4] for r in rows if r[0]<=origin}
    common=sorted(set(smap).intersection(qmap))
    common=[d for d in common if d<=origin]
    if len(common)>=64:
        common=common[-64:];sr=[];qr=[]
        for a,b in zip(common[:-1],common[1:]):
            sr.append(smap[b]/smap[a]-1);qr.append(qmap[b]/qmap[a]-1)
        ms,mq=mean(sr),mean(qr)
        cov=sum((a-ms)*(b-mq) for a,b in zip(sr,qr));vs=sum((a-ms)**2 for a in sr);vq=sum((b-mq)**2 for b in qr)
        x["beta63"]=cov/vq if vq else None;x["corr63"]=cov/math.sqrt(vs*vq) if vs and vq else None
    else:x["beta63"]=None;x["corr63"]=None
    qdates=sorted(d for d in qmap if d<=origin)
    if origin in qdates and qdates.index(origin)>=21:
        qi=qdates.index(origin);qret=(qmap[origin]/qmap[qdates[qi-21]]-1)*100
        x["excess21"]=x["ret21"]-qret if x["ret21"] is not None else None
    else:x["excess21"]=None
    return x

def breadth(origin):
    vals=[]
    for tk,rows in SER.items():
        b=basic_at(rows,origin)
        if b: vals.append(b)
    b50=100*sum(1 for b in vals if b["above50"] is True)/sum(1 for b in vals if b["above50"] is not None)
    b200=100*sum(1 for b in vals if b["above200"] is True)/sum(1 for b in vals if b["above200"] is not None)
    return b50,b200,len(vals)

# previous breadth date 20 QQQ sessions ago
qdates=[r[0] for r in MARKET["QQQ"]]
results=[]; summaries=[]
for origin in ORIGINS:
    basics={tk:basic_at(rows,origin) for tk,rows in SER.items()}
    basics={tk:b for tk,b in basics.items() if b}
    r63=avg_rank_pct({tk:b["ret63"] for tk,b in basics.items() if b["ret63"] is not None})
    r189=avg_rank_pct({tk:b["ret189"] for tk,b in basics.items() if b["ret189"] is not None})
    b50=100*sum(1 for b in basics.values() if b["above50"] is True)/sum(1 for b in basics.values() if b["above50"] is not None)
    b200=100*sum(1 for b in basics.values() if b["above200"] is True)/sum(1 for b in basics.values() if b["above200"] is not None)
    b50chg=None
    if origin in qdates:
        qi=qdates.index(origin)
        if qi>=20:
            old=qdates[qi-20];ob50,_,_=breadth(old);b50chg=b50-ob50
    # 252-day new-high minus new-low percentage, only where full history exists
    hi=lo=den=0
    for tk,rows in SER.items():
        z=context(rows,origin)
        if not z:continue
        dates,_,o,h,l,c,v=z;i=len(c)-1
        if len(c)>=252:
            den+=1
            if c[i]>=max(c[-252:]):hi+=1
            if c[i]<=min(c[-252:]):lo+=1
    nhnl=100*(hi-lo)/den if den else None
    eligible=[]
    for tk,b in basics.items():
        if b["close"]<5 or b["ddv20"] is None or b["ddv20"]<10000000:continue
        if b["sma50"] is None or b["sma200"] is None or not (b["sma50"]>b["sma200"] and b["close"]>b["sma200"]):continue
        if r63.get(tk,0)<85 or r189.get(tk,0)<85:continue
        eligible.append(tk)
    leaders=sorted(eligible,key=lambda t:(-r189.get(t,0),-r63.get(t,0),t))[:15]
    leadset=set(leaders)
    remaining=[t for t in eligible if t not in leadset]
    controls=sorted(remaining,key=lambda t:hashlib.sha256((origin+"|"+t+"|numeric-v2").encode()).hexdigest())[:15]
    chosen=[(t,"leader") for t in leaders]+[(t,"hash_control") for t in controls]
    for tk,group in chosen:
        feat=stock_features(tk,origin,r63,r189,b50,b200,b50chg,nhnl)
        rows=SER[tk];dates=[r[0] for r in rows]
        oi=dates.index(origin);future=rows[oi+1:oi+6]
        if len(future)<5:continue
        actual=(future[-1][4]/future[0][1]-1)*100
        results.append({"origin":origin,"ticker":tk,"group":group,"features":{k:feat.get(k) for k in FEATURES},"actual_5d_pct":actual})
    summaries.append({"origin":origin,"universe":len(basics),"eligible":len(eligible),"selected":len(chosen),"leaders":len(leaders),"controls":len(controls),"breadth50":b50,"breadth200":b200,"breadth50_change20":b50chg,"nhnl252":nhnl})


# -------- numeric v2 study: all tuning restricted to development/calibration ----------
DEV_ORIGINS=ORIGINS[:7]
CAL_ORIGINS=ORIGINS[7:9]
EVAL_ORIGINS=ORIGINS[9:]
STOCK_FEATURES=FEATURES[:23]
MARKET_FEATURES=FEATURES[23:]
COMPACT=[
 "ret5","ret21","ret63","dist21","dist50","slope50","vol20","adr20","compression","rsi14",
 "dist_high63","volume_ratio","gap","close_location","body","rs63","rs189","excess21",
 "QQQ_ret5","QQQ_ret21","QQQ_dist50","QQQ_vol20","IWM_ret21","HYG_ret21","IEF_ret21",
 "^VIX_level","^VIX_change20","breadth50","breadth50_change20","nhnl252"
]
COMPACT=[k for k in COMPACT if k in FEATURES]
COMPACT_STOCK=[k for k in COMPACT if k in STOCK_FEATURES]
COMPACT_MARKET=[k for k in COMPACT if k in MARKET_FEATURES or k=="excess21"]
rows=[]
for r in results:
    x=r["features"]
    scale=(x.get("vol20") or 0)*math.sqrt(5)
    rows.append({"origin":r["origin"],"ticker":r["ticker"],"group":r["group"],"x":x,
                 "actual":float(r["actual_5d_pct"]),"y":1 if float(r["actual_5d_pct"])>0 else 0,
                 "scale":scale})

# contemporaneous cross-sectional normalization uses no outcome information
for r in rows:r["rel"]=dict(r["x"])
for origin in ORIGINS:
    rr=[r for r in rows if r["origin"]==origin]
    for k in STOCK_FEATURES:
        vals=[float(r["x"][k]) for r in rr if r["x"].get(k) is not None and math.isfinite(float(r["x"][k]))]
        if not vals: continue
        m=mean(vals); sd=samplestd(vals)
        if not sd or sd<1e-9:
            for r in rr:r["rel"][k]=0.0 if r["x"].get(k) is not None else None
        else:
            for r in rr:
                v=r["x"].get(k)
                r["rel"][k]=(float(v)-m)/sd if v is not None and math.isfinite(float(v)) else None

def source_value(r,k,relative):
    return r["rel"].get(k) if relative and k in STOCK_FEATURES else r["x"].get(k)

def prep(train,features,relative):
    med={};mu={};sig={};usable=[]
    for k in features:
        vals=[float(source_value(r,k,relative)) for r in train if source_value(r,k,relative) is not None and math.isfinite(float(source_value(r,k,relative)))]
        if not vals:continue
        vals.sort();n=len(vals);m=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
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
def sigmoid(z):
    if z>=0:return 1/(1+math.exp(-min(z,60)))
    e=math.exp(max(z,-60));return e/(1+e)
def fit_logit(train,features,relative,lam,iters=350):
    state=prep(train,features,relative);X=[vec(r,state,relative) for r in train];Y=[r["y"] for r in train]
    base=sum(Y)/len(Y);b=math.log(max(base,1e-6)/max(1-base,1e-6));w=[0.0]*len(state[3]);lr=.06
    for _ in range(iters):
        gb=0.0;gw=[0.0]*len(w)
        for x,y in zip(X,Y):
            p=sigmoid(b+sum(a*z for a,z in zip(w,x)));e=p-y;gb+=e
            for j in range(len(w)):gw[j]+=e*x[j]
        n=len(Y);b-=lr*gb/n
        for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
    return {"state":state,"w":w,"b":b,"base":base,"features":features,"relative":relative}
def pred_logit(model,rr):
    return [sigmoid(model["b"]+sum(a*z for a,z in zip(model["w"],vec(r,model["state"],model["relative"])))) for r in rr]

CANDIDATES=[
 ("full_raw_l20",FEATURES,False,20),
 ("full_raw_l50",FEATURES,False,50),
 ("compact_raw_l10",COMPACT,False,10),
 ("compact_raw_l30",COMPACT,False,30),
 ("compact_rel_l10",COMPACT,True,10),
 ("compact_rel_l30",COMPACT,True,30),
 ("stock_rel_l10",COMPACT_STOCK,True,10),
 ("market_raw_l10",COMPACT_MARKET,False,10),
]
def brier(y,p):return sum((a-b)**2 for a,b in zip(p,y))/len(y)
def acc(y,p):return sum(int((a>=.5)==bool(b)) for a,b in zip(p,y))/len(y)
cv=[]
for name,features,relative,lam in CANDIDATES:
    scores=[];accs=[]
    for j in range(3,len(DEV_ORIGINS)):
        tr=[r for r in rows if r["origin"] in DEV_ORIGINS[:j]]
        va=[r for r in rows if r["origin"]==DEV_ORIGINS[j]]
        m=fit_logit(tr,features,relative,lam)
        p=pred_logit(m,va);y=[r["y"] for r in va]
        scores.append(brier(y,p));accs.append(acc(y,p))
    cv.append({"name":name,"features":features,"relative":relative,"lambda":lam,
               "cv_brier":mean(scores),"cv_accuracy":mean(accs),"fold_brier":scores})
best=min(cv,key=lambda z:(z["cv_brier"],-z["cv_accuracy"],len(z["features"])))
best_spec=next(c for c in CANDIDATES if c[0]==best["name"])
dev=[r for r in rows if r["origin"] in DEV_ORIGINS]
cal=[r for r in rows if r["origin"] in CAL_ORIGINS]
ev=[r for r in rows if r["origin"] in EVAL_ORIGINS]
mdev=fit_logit(dev,best_spec[1],best_spec[2],best_spec[3])
pcal=pred_logit(mdev,cal);ycal=[r["y"] for r in cal];base=mdev["base"]
alphas=[0,.25,.5,.75,1]
alpha=min(alphas,key=lambda a:brier(ycal,[base+a*(p-base) for p in pcal]))
train_final=dev+cal
mfinal=fit_logit(train_final,best_spec[1],best_spec[2],best_spec[3])
base_final=mfinal["base"]
pfrozen=[base_final+alpha*(p-base_final) for p in pred_logit(mfinal,ev)]

# expanding refit with fixed representation/lambda/alpha
pexpand=[];expand_rows=[]
for origin in EVAL_ORIGINS:
    tr=[r for r in rows if ORIGINS.index(r["origin"])<ORIGINS.index(origin)]
    te=[r for r in rows if r["origin"]==origin]
    mm=fit_logit(tr,best_spec[1],best_spec[2],best_spec[3])
    pp=[mm["base"]+alpha*(p-mm["base"]) for p in pred_logit(mm,te)]
    pexpand.extend(pp);expand_rows.extend(te)

def auc_score(y,p):
    pos=[p[i] for i,v in enumerate(y) if v==1];neg=[p[i] for i,v in enumerate(y) if v==0]
    if not pos or not neg:return None
    s=0
    for a in pos:
        for b in neg:s+=1 if a>b else .5 if a==b else 0
    return s/(len(pos)*len(neg))
def corr_rank(a,b):
    def ranks(x):
        order=sorted(range(len(x)),key=lambda i:x[i]);r=[0]*len(x);i=0
        while i<len(order):
            j=i+1
            while j<len(order) and x[order[j]]==x[order[i]]:j+=1
            v=((i+1)+j)/2
            for q in range(i,j):r[order[q]]=v
            i=j
        return r
    ra,rb=ranks(a),ranks(b);ma,mb=mean(ra),mean(rb)
    va=sum((x-ma)**2 for x in ra);vb=sum((x-mb)**2 for x in rb)
    return sum((x-ma)*(y-mb) for x,y in zip(ra,rb))/math.sqrt(va*vb) if va and vb else None
def direction_metrics(rr,p):
    y=[r["y"] for r in rr];actual=[r["actual"] for r in rr];pred=[x>=.5 for x in p]
    pos=[i for i,v in enumerate(y) if v];neg=[i for i,v in enumerate(y) if not v]
    tpr=sum(pred[i] for i in pos)/len(pos) if pos else None;tnr=sum(not pred[i] for i in neg)/len(neg) if neg else None
    n=max(1,len(rr)//5);order=sorted(range(len(rr)),key=lambda i:p[i])
    lo=[actual[i] for i in order[:n]];hi=[actual[i] for i in order[-n:]]
    up=[actual[i] for i in range(len(rr)) if pred[i]];dn=[actual[i] for i in range(len(rr)) if not pred[i]]
    return {"n":len(rr),"accuracy":acc(y,p),"balanced_accuracy":(tpr+tnr)/2 if tpr is not None and tnr is not None else None,
            "brier":brier(y,p),"auc":auc_score(y,p),"mean_p":mean(p),"up_frequency":mean(y),
            "spearman_p_vs_return":corr_rank(p,actual),
            "top_quintile_mean_return_pct":mean(hi),"bottom_quintile_mean_return_pct":mean(lo),
            "top_bottom_spread_pct":mean(hi)-mean(lo),
            "predicted_up_mean_return_pct":mean(up) if up else None,"predicted_down_mean_return_pct":mean(dn) if dn else None}
eval_by_origin={}
for origin in EVAL_ORIGINS:
    rr=[r for r in ev if r["origin"]==origin]
    idx=[i for i,r in enumerate(ev) if r["origin"]==origin]
    eval_by_origin[origin]=direction_metrics(rr,[pfrozen[i] for i in idx])

# Range: robust Huber ridge on normalized 5D return.
RANGE_CAND=[
 ("range_compact_raw_l10",COMPACT,False,10),
 ("range_compact_raw_l30",COMPACT,False,30),
 ("range_compact_rel_l10",COMPACT,True,10),
 ("range_compact_rel_l30",COMPACT,True,30)
]
def fit_huber(train,features,relative,lam,iters=350):
    state=prep(train,features,relative);X=[vec(r,state,relative) for r in train]
    Y=[r["actual"]/r["scale"] if r["scale"] and r["scale"]>1e-9 else 0 for r in train]
    b=statistics.median(Y);w=[0.0]*len(state[3]);lr=.035;delta=2.0
    for _ in range(iters):
        gb=0.0;gw=[0.0]*len(w)
        for x,y in zip(X,Y):
            e=b+sum(a*z for a,z in zip(w,x))-y
            g=max(-delta,min(delta,e));gb+=g
            for j in range(len(w)):gw[j]+=g*x[j]
        n=len(Y);b-=lr*gb/n
        for j in range(len(w)):w[j]-=lr*(gw[j]/n+lam*w[j]/n)
    return {"state":state,"w":w,"b":b,"features":features,"relative":relative}
def pred_huber(m,rr):
    return [m["b"]+sum(a*z for a,z in zip(m["w"],vec(r,m["state"],m["relative"]))) for r in rr]
range_cv=[]
for name,features,relative,lam in RANGE_CAND:
    maes=[]
    for j in range(3,len(DEV_ORIGINS)):
        tr=[r for r in rows if r["origin"] in DEV_ORIGINS[:j]]
        va=[r for r in rows if r["origin"]==DEV_ORIGINS[j]]
        mm=fit_huber(tr,features,relative,lam)
        z=pred_huber(mm,va);pred=[zz*r["scale"] for zz,r in zip(z,va)]
        maes.append(mean([abs(a-r["actual"]) for a,r in zip(pred,va)]))
    range_cv.append({"name":name,"features":features,"relative":relative,"lambda":lam,"cv_mae_pct":mean(maes),"fold_mae":maes})
rbest=min(range_cv,key=lambda z:z["cv_mae_pct"])
rbest_spec=next(c for c in RANGE_CAND if c[0]==rbest["name"])
rmdev=fit_huber(dev,rbest_spec[1],rbest_spec[2],rbest_spec[3])
zcal=pred_huber(rmdev,cal)
resz=[(r["actual"]-zz*r["scale"])/r["scale"] for zz,r in zip(zcal,cal) if r["scale"] and r["scale"]>1e-9]
def quantile(v,q):
    s=sorted(v);idx=min(len(s)-1,max(0,math.ceil(q*len(s))-1));return s[idx]
rq10,rq90=quantile(resz,.1),quantile(resz,.9)
rmfinal=fit_huber(train_final,rbest_spec[1],rbest_spec[2],rbest_spec[3])
zev=pred_huber(rmfinal,ev)
rpred=[z*r["scale"] for z,r in zip(zev,ev)]
lower=[p+rq10*r["scale"] for p,r in zip(rpred,ev)]
upper=[p+rq90*r["scale"] for p,r in zip(rpred,ev)]
# volatility-only comparator from pre-evaluation normalized returns
trainz=[r["actual"]/r["scale"] for r in train_final if r["scale"] and r["scale"]>1e-9]
bq10,bq50,bq90=quantile(trainz,.1),quantile(trainz,.5),quantile(trainz,.9)
bcenter=[bq50*r["scale"] for r in ev];bl=[bq10*r["scale"] for r in ev];bu=[bq90*r["scale"] for r in ev]
def range_metrics(rr,center,lo,hi):
    ae=[abs(c-r["actual"]) for c,r in zip(center,rr)]
    cov=[l<=r["actual"]<=u for l,u,r in zip(lo,hi,rr)]
    widths=[u-l for l,u in zip(lo,hi)]
    score=[u-l+10*max(l-r["actual"],0)+10*max(r["actual"]-u,0) for l,u,r in zip(lo,hi,rr)]
    return {"n":len(rr),"mae_pct":mean(ae),"median_ae_pct":statistics.median(ae),"coverage80":mean(cov),
            "mean_width_pct":mean(widths),"interval_score":mean(score),"mean_center_pct":mean(center)}
range_by_origin={}
for origin in EVAL_ORIGINS:
    idx=[i for i,r in enumerate(ev) if r["origin"]==origin];rr=[ev[i] for i in idx]
    range_by_origin[origin]={"huber":range_metrics(rr,[rpred[i] for i in idx],[lower[i] for i in idx],[upper[i] for i in idx]),
                             "vol_baseline":range_metrics(rr,[bcenter[i] for i in idx],[bl[i] for i in idx],[bu[i] for i in idx])}

out={"version":"numeric-v2-walkforward-20260930","cases":len(rows),"origins":ORIGINS,"development_origins":DEV_ORIGINS,
     "calibration_origins":CAL_ORIGINS,"evaluation_origins":EVAL_ORIGINS,"origin_summaries":summaries,
     "direction":{"candidate_cv":cv,"selected":best,"calibration_shrink_alpha":alpha,
                  "calibration":{"n":len(cal),"raw":direction_metrics(cal,pcal),
                                 "shrunk":direction_metrics(cal,[base+alpha*(p-base) for p in pcal])},
                  "evaluation_frozen":direction_metrics(ev,pfrozen),
                  "evaluation_expanding":direction_metrics(expand_rows,pexpand),
                  "evaluation_by_origin":eval_by_origin,
                  "evaluation_by_group":{"leader":direction_metrics([r for r in ev if r["group"]=="leader"],
                     [pfrozen[i] for i,r in enumerate(ev) if r["group"]=="leader"]),
                    "hash_control":direction_metrics([r for r in ev if r["group"]=="hash_control"],
                     [pfrozen[i] for i,r in enumerate(ev) if r["group"]=="hash_control"])}},
     "range":{"candidate_cv":range_cv,"selected":rbest,"residual_q10":rq10,"residual_q90":rq90,
              "evaluation_huber":range_metrics(ev,rpred,lower,upper),
              "evaluation_vol_baseline":range_metrics(ev,bcenter,bl,bu),
              "evaluation_by_origin":range_by_origin},
     "limitations":["Current reconstructed universe; historical membership is not PIT.","Structural clinical-biotech exclusion is unavailable historically and not fabricated.",
                    "Evaluation dates have been inspected in prior research; this is a locked retrospective replay, not a pristine unseen holdout.",
                    "No Jev, news or options are used in this numeric-v2 study."]}
json.dumps(out,allow_nan=False)

`;

export default async function handler(req,res){
  res.setHeader("Cache-Control","no-store");
  if(process.env.VERCEL_ENV!=="preview") return res.status(404).json({ok:false,error:"preview_only"});
  try{
    const base="https://raw.githubusercontent.com/karu77018-lgtm/market-dashboard/d84a70dd46df011df502217f2737ed08a1e90fa2/chart-data/";
    const shards=await Promise.all(Array.from({length:32},(_,i)=>fetchJson(base+`shard-${String(i).padStart(2,"0")}.json`)));
    const universe=Object.assign({},...shards);
    const fred=await fetchText("https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS,DGS10");
    const py=await getRuntime();
    py.globals.set("universe_json",JSON.stringify(universe));
    py.globals.set("market_json",JSON.stringify(marketData));
    py.globals.set("expected_json",JSON.stringify(expectedData));
    py.globals.set("fred_csv_text",fred);
    const val=await py.runPythonAsync(PY);
    const obj=JSON.parse(String(val));
    if(val?.destroy) val.destroy();
    return res.status(200).json({ok:true,...obj});
  }catch(e){
    return res.status(500).json({ok:false,error:String(e?.message||e),stack:String(e?.stack||"").slice(0,1400)});
  }
}