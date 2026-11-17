"""Entries chosen with the fake factors.  Known at the next open: day count (Day4-7/16+ risky),
long bonds down on the FTD day (tlt1<=-0.07%), dollar up over 20 sessions (usd20>=0.45%); cuts fixed
on 1993-2009.  Known later: next day's move, distribution days.  Entry at an open, exit at the next
open after a close below the FTD-day low; optional early exit at the day-4 open when both warnings
are on at day 3.  Index that gave the signal, to the close 60 sessions after the FTD."""
import pandas as pd, numpy as np, ftd
Y=pd.read_pickle('ftd_events2.pkl'); Y=Y[Y.n_after.notna()|(Y.date<'2026-09-01')].copy()
DF={tk:ftd.events(tk)[0] for tk in ('QQQ','SPY')}
H=60
def sim(row,E,early=False,lev=1):
    df=DF[row.tk]; i=df.index.get_loc(row.date)
    o,l,c,v=(df[k].to_numpy(float) for k in ('open','low','close','volume'))
    fl=l[i]; end=min(len(c)-1,i+H)
    w2 = i+3<=end and (c[i+1]<c[i]) and any((c[i+t]<c[i+t-1]*0.998) and v[i+t]>v[i+t-1] for t in (1,2,3))
    val=1.0; units=0.0; inv=0.0; done=False; pend=False
    for t in range(i+1,end+1):
        if units>0 and (pend or (early and w2 and t==i+4)):
            units*=1+lev*(o[t]/c[t-1]-1); val+=units; units=0; done=True; pend=False
        new=0.0
        if not done and t in E and c[t-1]>=fl and not (early and w2 and t>=i+4):
            new=E[t]; val-=new
        if units>0: units*=1+lev*(c[t]/c[t-1]-1)
        if new>0: units+=new*(1+lev*(c[t]/o[t]-1))
        if units>0 and c[t]<fl: pend=True
        inv+=units
    return val+units-1, inv/(end-i)
def facts(r,df,i):
    c=df.close.to_numpy(float)
    risky=(r.day<=7) or (r.day>=16)
    bond=(r.tlt1<=-0.07) if pd.notna(r.tlt1) else False
    usd=(r.usd20>=0.45) if pd.notna(r.usd20) else False
    up1= i+1<len(c) and c[i+1]>c[i]
    return risky,bond,usd,up1
def styles(r):
    df=DF[r.tk]; i=df.index.get_loc(r.date); risky,bond,usd,up1=facts(r,df,i)
    n=int(risky)+int(bond)+int(usd); a,b=i+1,i+2
    S={}
    S['A 翌日寄り・全額']=({a:1.0},False)
    S['B 日数で量（高リスク半分）']=({a:.5 if risky else 1.0},False)
    S['C 日数リスク高は見送り']=({a:1.0} if not risky else {},False)
    S['D 逆風の数で量 0:全額/1:2/3/2:1/3/3:見送り']=({a:[1.0,.67,.33,0][n]} if n<3 else {},False)
    S['E 逆風2つ以上は見送り']=({a:1.0} if n<2 else {},False)
    S['F 日数で量＋高リスクは翌日プラスで残り']=({a:.5, **({b:.5} if up1 else {})} if risky else {a:1.0},False)
    S['G 逆風で量＋翌日プラスで残り']=({a:[1.0,.67,.33,0][n], **({b:1-[1.0,.67,.33,0][n]} if up1 and n>0 else {})},False)
    S['H 全額＋3日目警告2つで4日目寄りに撤退']=({a:1.0},True)
    S['I 日数で量＋警告2つで撤退']=({a:.5 if risky else 1.0},True)
    S['J 逆風で量＋警告2つで撤退']=({a:[1.0,.67,.33,0][n]} if n<3 else {},True)
    return S,n
rows=[]
for lev in (1,3):
    for r in Y.itertuples():
        S,n=styles(r)
        for k,(E,early) in S.items():
            ret,exp=sim(r,E,early,lev); rows.append(dict(lev=lev,style=k,tk=r.tk,date=r.date,n=n,ret=ret*100,exp=exp*100))
R=pd.DataFrame(rows); pd.set_option('display.width',260); pd.set_option('display.max_colwidth',40)
for lev in (1,3):
    X=R[R.lev==lev]
    def agg(g): return pd.Series(dict(mean=g.ret.mean(),worst=g.ret.min(),exp=g.exp.mean(),eff=g.ret.mean()/max(g.exp.mean(),1e-9)*100))
    T=X.groupby('style').apply(agg)
    for nm,m in (('~09',X.date<'2010'),('10~',X.date>='2010')):
        T['mean'+nm]=X[m].groupby('style').ret.mean(); T['worst'+nm]=X[m].groupby('style').ret.min()
    for tk in ('QQQ','SPY'): T[tk]=X[X.tk==tk].groupby('style').ret.mean()
    print(f'\n=== lev{lev} ==='); print(T.round(2).to_string())
X=R[(R.lev==1)&(R['style']=='A 翌日寄り・全額')]
print('\nbaseline by headwinds:'); print(X.groupby('n').ret.agg(['count','mean','median']).round(2))
for nm,m in (('~09',X.date<'2010'),('10~',X.date>='2010')): print(nm, X[m].groupby('n').ret.mean().round(2).to_dict())
R.to_pickle('ftd_entry3.pkl')
