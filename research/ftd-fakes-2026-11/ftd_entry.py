"""Entry styles after a follow-through day, on the index that gave the signal (QQQ / SPY),
held at most 60 sessions after the FTD; exit at the close that ends below the FTD-day low."""
import pandas as pd, numpy as np, ftd
Y=pd.read_pickle('ftd_events2.pkl'); Y=Y[Y.n_after.notna()|(Y.date<'2026-09-01')].copy()
DF={tk:ftd.events(tk)[0] for tk in ('QQQ','SPY')}
H=60
def path(tk,d):
    df=DF[tk]; i=df.index.get_loc(d); c=df.close.to_numpy(float); l=df.low.to_numpy(float); v=df.volume.to_numpy(float)
    return i,c,l,v
def run(row,style,lev=1):
    """returns (return on full capital, days invested-weighted, exited_on_fail)"""
    i,c,l,v=path(row.tk,row.date); fl=l[i]; end=min(len(c)-1,i+H)
    # warnings known at close of i+k
    def warn_at(k):
        if i+k>end: return None
        down1=c[i+1]<c[i]
        dist=sum((c[i+t]<c[i+t-1]*0.998) and v[i+t]>v[i+t-1] for t in range(1,k+1))
        return int(down1)+int(dist>0)
    # entries: list of (session index, weight)
    risky=(row.day<=7) or (row.day>=16)
    if style=='全額・当日': E=[(i,1.0)]
    elif style=='全額・当日・損切りなし': E=[(i,1.0)]
    elif style=='半分→翌日プラスで残り': E=[(i,.5)]+([(i+1,.5)] if i+1<=end and c[i+1]>c[i] else [])
    elif style=='翌日プラスなら全額': E=[(i+1,1.0)] if i+1<=end and c[i+1]>c[i] else []
    elif style=='3日目に警告0なら全額': E=[(i+3,1.0)] if warn_at(3)==0 else []
    elif style=='半分→3日目警告0で残り': E=[(i,.5)]+([(i+3,.5)] if warn_at(3)==0 else [])
    elif style=='日数で量を変える': E=[(i,.5 if risky else 1.0)]
    elif style=='日数で量＋翌日確認': E=[(i,.33 if risky else .67)]+([(i+1,.67 if risky else .33)] if i+1<=end and c[i+1]>c[i] else [])
    stop=(style!='全額・当日・損切りなし')
    # simulate on daily closes
    pos=0.0; cash=1.0; units=0.0; exited=False; inv_days=0.0
    ent={k:w for k,w in E}
    for t in range(i,end+1):
        if units>0:
            r=(c[t]/c[t-1]-1)*lev
            units*=1+r
        if t in ent and not exited:
            if t>i and stop and c[t]<fl: pass  # do not enter after failure
            else:
                amt=ent[t]; units+=amt; cash-=amt
        if stop and t>i and units>0 and c[t]<fl:
            cash+=units; units=0; exited=True
        inv_days+=units
    total=cash+units
    return total-1, inv_days/(end-i+1), exited, len(E)>0
STY=['全額・当日・損切りなし','全額・当日','半分→翌日プラスで残り','翌日プラスなら全額','3日目に警告0なら全額','半分→3日目警告0で残り','日数で量を変える','日数で量＋翌日確認']
rows=[]
for lev in (1,3):
    for s in STY:
        R=pd.DataFrame([dict(zip(('ret','exp','stopped','entered'),run(r,s,lev)),date=r.date,tk=r.tk,fake=r.fake25) for r in Y.itertuples()])
        for nm,sub in (('全期間',R),('〜2009',R[R.date<'2010']),('2010〜',R[R.date>='2010'])):
            rows.append(dict(lev=lev,style=s,period=nm,n=len(sub),mean=sub.ret.mean()*100,med=sub.ret.median()*100,worst=sub.ret.min()*100,lossrate=(sub.ret<0).mean()*100,
                             big=(sub.ret>=0.10*lev).mean()*100,exp=sub.exp.mean()*100,eff=sub.ret.mean()/max(sub.exp.mean(),1e-9)*100,
                             fake_mean=sub[sub.fake==1].ret.mean()*100,real_mean=sub[sub.fake==0].ret.mean()*100))
T=pd.DataFrame(rows); pd.set_option('display.width',250)
for lev in (1,3):
    print(f'\n===== {"指数そのもの" if lev==1 else "3倍換算（TQQQ相当）"}：FTD1回あたり、60営業日以内 =====')
    print(T[(T.lev==lev)].pivot_table(index='style',columns='period',values=['mean','worst','lossrate'],sort=False).round(1).to_string())
    print(T[(T.lev==lev)&(T.period=='全期間')][['style','med','big','exp','eff','fake_mean','real_mean']].round(1).to_string(index=False))
T.to_pickle('ftd_entry.pkl')
