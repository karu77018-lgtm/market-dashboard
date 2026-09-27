# Stock-selection study (pyr): meta-labeling / selection rules / pyramiding. Run from a work dir whose parent holds stocks_all.csv.gz and data/*.csv.
import itertools
exec(open("conc2.py").read().split("IS=(")[0])
def runp(sigv,score,K,exitf,stop,start,end,add_th=None,maxu=3,cost=0.001,seed=None,maxh=60):
    idx=C.index; i0=idx.searchsorted(pd.Timestamp(start)); i1=idx.searchsorted(pd.Timestamp(end))
    rng=np.random.default_rng(seed) if seed is not None else None
    pos={}; cash=1.0; curve=[]; nt=0
    # pos[j]=dict(sh=株数, cost=平均単価, ei, units, last=最終追加価格, ex=flag, add=flag)
    def val(i): return cash+sum(p["sh"]*(Cn[i,j] if not np.isnan(Cn[i,j]) else p["cost"]) for j,p in pos.items())
    for i in range(i0,min(i1,len(idx)-1)):
        tot=val(i-1)
        for j in list(pos):
            p=pos[j]
            if p["ex"]:
                px=On[i,j] if not np.isnan(On[i,j]) else Cn[i-1,j]
                cash+=p["sh"]*px*(1-cost); del pos[j]; nt+=1
            elif p["add"] and not np.isnan(On[i,j]):
                amt=min(cash,tot/K)
                if amt>0: sh=amt/On[i,j]; p["cost"]=(p["cost"]*p["sh"]+amt)/(p["sh"]+sh); p["sh"]+=sh; cash-=amt*(1+cost); p["units"]+=1; p["last"]=On[i,j]
                p["add"]=False
        used=sum(p["units"] for p in pos.values())
        if i>i0 and len(pos)<K:
            cand=[j for j in np.where(sigv[i-1])[0] if j not in pos and not np.isnan(On[i,j])]
            if rng is not None: rng.shuffle(cand)
            else: cand=sorted(cand,key=lambda j:-score[i-1,j])
            for j in cand[:K-len(pos)]:
                amt=min(cash,tot/K)
                if amt<=1e-9: break
                cash-=amt*(1+cost); pos[j]=dict(sh=amt/On[i,j],cost=On[i,j],ei=i,units=1,last=On[i,j],ex=False,add=False,e0=On[i,j])
        if stop:
            for j in list(pos):
                p=pos[j]; lvl=p["last"]*(1+stop)
                if Ln[i,j]<=lvl:
                    px=min(On[i,j],lvl) if not np.isnan(On[i,j]) else lvl
                    cash+=p["sh"]*px*(1-cost); del pos[j]; nt+=1
        for j,p in pos.items():
            if exitf(i,j) or i-p["ei"]+1>=maxh: p["ex"]=True
            elif add_th and p["units"]<maxu and Cn[i,j]>=p["last"]*(1+add_th): p["add"]=True
        curve.append((idx[i],val(i)))
    return pd.Series(dict(curve)),nt
full=("2022-10-01","2026-09-30"); H1=("2022-10-01","2024-07-01"); H2=("2024-07-01","2026-09-30")
rows=[]
for fam,(L_,top) in itertools.product(["B","A"],[(126,0.1),(126,0.2),(63,0.2)]):
    if fam=="B": s,sc=B(L_,top,0.15,1.5); ex=exB20; st=-0.08; mh=60
    else: s,sc=A(L_,top,10); ex=lambda i,j: Cn[i,j]<SMA10.values[i,j] and i>0; st=-0.08; mh=60
    for K,add in itertools.product([3,5],[None,0.08,0.15]):
        a=met(runp(s,sc,K,ex,st,*H1,add_th=add,maxh=mh)[0]); b=met(runp(s,sc,K,ex,st,*H2,add_th=add,maxh=mh)[0])
        rn=[met(runp(s,sc,K,ex,st,*full,add_th=add,seed=k,maxh=mh)[0])[0] for k in range(12)]
        rows.append((fam,L_,top,K,add,a[0],a[1],b[0],b[1],np.median(rn),np.percentile(rn,90)))
R=pd.DataFrame(rows,columns=["fam","L","top","K","add","h1","dd1","h2","dd2","rand_med","rand_p90"])
pd.set_option("display.width",200); print(R.to_string(float_format=lambda v:f"{v:+.1%}"))
print(R.groupby(["fam","add"],dropna=False)[["h1","h2","dd1","dd2","rand_med"]].median().map(lambda v:f"{v:+.1%}"))
R.to_pickle("pyr.pkl")
