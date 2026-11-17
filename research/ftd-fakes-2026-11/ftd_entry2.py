"""Entry after a follow-through day when the FTD close itself cannot be traded (orders placed
after the US close).  Entries at a later session's open; exits either at the next open after a
close below the FTD-day low, or by a stop order resting at the FTD-day low (filled at the lower
of the open and the stop).  Index that gave the signal, measured to the close 60 sessions after
the FTD.  Returns on full capital per FTD; lev=3 compounds 3x the daily moves (TQQQ-like)."""
import pandas as pd, numpy as np, ftd
Y=pd.read_pickle('ftd_events2.pkl'); Y=Y[Y.n_after.notna()|(Y.date<'2026-09-01')].copy()
DF={tk:ftd.events(tk)[0] for tk in ('QQQ','SPY')}
H=60
def run(row,style,exitrule,lev=1):
    df=DF[row.tk]; i=df.index.get_loc(row.date)
    o,h,l,c,v=(df[k].to_numpy(float) for k in ('open','high','low','close','volume'))
    fl=l[i]; end=min(len(c)-1,i+H); risky=(row.day<=7) or (row.day>=16)
    def warn_at(k):
        if i+k>end: return None
        d1=c[i+1]<c[i]; dist=any((c[i+t]<c[i+t-1]*0.998) and v[i+t]>v[i+t-1] for t in range(1,k+1))
        return int(d1)+int(dist)
    up1 = i+1<=end and c[i+1]>c[i]
    if style in ('翌日寄り・全額','翌日寄り・撤退なし'): E={i+1:1.0}
    elif style=='翌日寄り・日数で量': E={i+1:.5 if risky else 1.0}
    elif style=='翌日プラスなら翌々日寄り': E={i+2:1.0} if up1 else {}
    elif style=='半分→翌日プラスで翌々日に残り': E={i+1:.5, **({i+2:.5} if up1 else {})}
    elif style=='警告0なら4日目寄り': E={i+4:1.0} if warn_at(3)==0 else {}
    elif style=='（参考）FTD当日終値・全額': E={'close':1.0}
    stop = style!='翌日寄り・撤退なし'
    val=1.0; inv=0.0; units=0.0; days=0; done=False; pend_exit=False
    if 'close' in E: units=1.0; val=0.0  # invested at FTD close
    for t in range(i+1,end+1):
        # open: pending exit / new entries / stop at open
        if units>0:
            if pend_exit:
                units*=1+lev*(o[t]/c[t-1]-1); val+=units; units=0; done=True; pend_exit=False
            elif exitrule=='stop' and stop and o[t]<=fl:
                units*=1+lev*(o[t]/c[t-1]-1); val+=units; units=0; done=True
        if not done and t in E and o[t]>fl if exitrule=='stop' else (not done and t in E and c[t-1]>=fl):
            amt=E[t]; val-=amt; units_new=amt
        else: units_new=0.0
        # intraday from open (new) and from prior close (old)
        if units>0:
            if exitrule=='stop' and stop and l[t]<=fl:
                units*=1+lev*(fl/c[t-1]-1); val+=units; units=0; done=True
            else: units*=1+lev*(c[t]/c[t-1]-1)
        if units_new>0:
            if exitrule=='stop' and stop and l[t]<=fl:
                val+=units_new*(1+lev*(fl/o[t]-1)); done=True
            else: units+=units_new*(1+lev*(c[t]/o[t]-1))
        if exitrule=='close' and stop and units>0 and c[t]<fl: pend_exit=True
        inv+=units
    total=val+units
    return total-1, inv/(end-i), len(E)>0
STY=['（参考）FTD当日終値・全額','翌日寄り・撤退なし','翌日寄り・全額','翌日寄り・日数で量','半分→翌日プラスで翌々日に残り','翌日プラスなら翌々日寄り','警告0なら4日目寄り']
rows=[]
for lev in (1,3):
  for ex in ('close','stop'):
    for s in STY:
        R=pd.DataFrame([dict(zip(('ret','exp','entered'),run(r,s,ex,lev)),date=r.date,fake=r.fake25) for r in Y.itertuples()])
        for nm,sub in (('全期間',R),('〜2009',R[R.date<'2010']),('2010〜',R[R.date>='2010'])):
            rows.append(dict(lev=lev,ex=ex,style=s,period=nm,mean=sub.ret.mean()*100,worst=sub.ret.min()*100,loss=(sub.ret<0).mean()*100,
                             exp=sub.exp.mean()*100,eff=sub.ret.mean()/max(sub.exp.mean(),1e-9)*100))
T=pd.DataFrame(rows); pd.set_option('display.width',250)
for lev in (1,3):
  for ex in ('close','stop'):
    print(f'\n== lev{lev} exit={ex} ==')
    P=T[(T.lev==lev)&(T.ex==ex)].pivot_table(index='style',columns='period',values=['mean','worst'],sort=False).round(1)
    Q=T[(T.lev==lev)&(T.ex==ex)&(T.period=='全期間')].set_index('style')[['loss','exp','eff']].round(1)
    P.columns=[f'{a}{b}' for a,b in P.columns]; print(P.join(Q).to_string())
T.to_pickle('ftd_entry2.pkl')
