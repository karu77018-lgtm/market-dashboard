"""6-slot swing rule (next-open fills) + idle money in the TQQQ-rule sleeve, share set by breakout health."""
import numpy as np, pandas as pd
C=pd.read_pickle('close.pkl').astype('float64'); O=pd.read_pickle('open.pkl').astype('float64'); Lw=pd.read_pickle('low.pkl').astype('float64')
EL=Lw.ewm(span=21,adjust=False).mean()
q=C['QQQ']; reg=(q>q.rolling(200).mean()).to_numpy()
sig=pd.read_pickle('honmei.pkl'); dates=C.index; n=len(dates); pos_of={d:i for i,d in enumerate(dates)}; col={t:j for j,t in enumerate(C.columns)}
Cn,On,Ln,En=C.to_numpy(),O.to_numpy(),Lw.to_numpy(),EL.to_numpy()
# --- breakout health (本命 10-day mean, 63 sessions ending 10 sessions ago), hysteresis 0 / +1.5%
sums=np.zeros(n); cnts=np.zeros(n)
for d,t in zip(sig.date,sig.ticker):
    i,j=pos_of[d],col[t]
    if i+10<n and Cn[i,j]>0 and not np.isnan(Cn[i+10,j]): sums[i]+=Cn[i+10,j]/Cn[i,j]-1; cnts[i]+=1
cs,ck=np.cumsum(sums),np.cumsum(cnts)
hv=np.full(n,np.nan)
for i in range(73,n):
    k=ck[i-10]-ck[i-73]
    if k>=5: hv[i]=(cs[i-10]-cs[i-73])/k
def hyst(vals,rec=0.015,lo=0.0):
    good=True; out=np.ones(len(vals),bool)
    for i,v in enumerate(vals):
        if not np.isnan(v):
            if good and v<lo: good=False
            elif not good and v>rec: good=True
        out[i]=good
    return out
good=hyst(hv)
F=pd.read_pickle('tqfund.pkl')
def fund(name):
    f=F[name].reindex(dates); return f.nav_o.to_numpy(), f.nav_c.to_numpy(), f.full.fillna(False).to_numpy(bool)
by_day={d:g.sort_values('rs189',ascending=False).ticker.tolist() for d,g in sig.groupby('date')}
def run(share, start='2015-01-02', end='2026-11-13', fundname='proxy', stock_cap=0.80, name_cap=0.40, trail=0.15):
    """share: array (per session, decided at that close) of sleeve share 0..1"""
    fo,fc,_=fund(fundname)
    cash,fu,pos,eq=1.0,0.0,{},[]
    pend_exit=set(); pend_buy=[]; pend_add=[]; pend_share=0.0
    idx=[i for i,d in enumerate(dates) if pd.Timestamp(start)<=d<=pd.Timestamp(end)]
    stock_w=[]; sleeve_w=[]
    for i in idx:
        def px_open(j): 
            o=On[i,j]; return o if not np.isnan(o) else pos[j]['last'] if j in pos else np.nan
        def val_open(): return cash+fu*fo[i]+sum(p['sh']*(On[i,j] if not np.isnan(On[i,j]) else p['last']) for j,p in pos.items())
        # ---- open: exits
        for j in list(pend_exit):
            if j in pos: cash+=pos[j]['sh']*px_open(j); del pos[j]
        pend_exit=set()
        equity=val_open(); stocks=sum(p['sh']*(On[i,j] if not np.isnan(On[i,j]) else p['last']) for j,p in pos.items())
        def avail(): return cash+fu*fo[i]
        def spend(amt):
            nonlocal cash,fu
            take=min(cash,amt); cash-=take; fu-=(amt-take)/fo[i]
        for j,amt0 in pend_add:
            if j not in pos or np.isnan(On[i,j]): continue
            p=pos[j]; room=min(name_cap*equity-p['sh']*On[i,j], stock_cap*equity-stocks)
            amt=min(amt0,max(0.0,room),avail())
            if amt>0: spend(amt); p['sh']+=amt/On[i,j]; p['inv']+=amt; stocks+=amt
        pend_add=[]
        for t in pend_buy:
            j=col[t]
            if j in pos or np.isnan(On[i,j]): continue
            if len(pos)>=6: break
            unit=equity/6; amt=min(unit,avail(),max(0.0,stock_cap*equity-stocks))
            if amt<=unit*0.25: continue
            spend(amt); o=On[i,j]; stocks+=amt
            pos[j]=dict(entry=o,stop=o*0.92,sh=amt/o,inv=amt,unit=unit,trig=[],last=o,hi=o)
        pend_buy=[]
        idle=cash+fu*fo[i]; fu=idle*pend_share/fo[i]; cash=idle-fu*fo[i]
        # ---- intraday stops, close decisions
        for j in list(pos):
            p=pos[j]; o,l,c,e=On[i,j],Ln[i,j],Cn[i,j],En[i,j]
            if np.isnan(c): continue
            if l<=p['stop'] and not (i==idx[0]):
                px=o if o<=p['stop'] else p['stop']
                if p['entry']==o and o<=p['stop']: px=p['stop']
                cash+=p['sh']*px; del pos[j]; continue
            p['last']=c; p['hi']=max(p['hi'],c)
            if c<e or c<=p['hi']*(1-trail): pend_exit.add(j); continue
            for k,lv in enumerate((0.10,0.20)):
                if k not in p['trig'] and round(c/p['entry']-1,9)>=lv: p['trig'].append(k); pend_add.append((j,p['unit']))
        if reg[i] and dates[i] in by_day: pend_buy=[t for t in by_day[dates[i]] if col[t] not in pos or col[t] in pend_exit]
        pend_share=float(share[i])
        v=cash+fu*fc[i]+sum(p['sh']*p['last'] for p in pos.values()); eq.append(v)
        stock_w.append(sum(p['sh']*p['last'] for p in pos.values())/v); sleeve_w.append(fu*fc[i]/v)
    e=pd.Series(eq,index=dates[idx]); run.stock=pd.Series(stock_w,index=e.index); run.sleeve=pd.Series(sleeve_w,index=e.index)
    return e
def stats(e,a=None,b=None):
    e=e[a:b]; yrs=(e.index[-1]-e.index[0]).days/365.25; r=e.pct_change().dropna()
    return (e.iloc[-1]/e.iloc[0])**(1/yrs)-1,(e/e.cummax()-1).min(), r.mean()/r.std()*np.sqrt(252)
if __name__=='__main__':
    _,_,full=fund('proxy')
    rule=np.where(full,1.0,np.where(good,0.0,1.0))
    H=pd.DataFrame({'hv':hv,'good':good,'full':full},index=dates); H.to_pickle('health.pkl')
    print('health latest',H.hv.iloc[-1].round(4),'good' if H.good.iloc[-1] else '不調','| 不調 share of days 2015-21',round((~H.good['2015':'2021']).mean()*100,1),'% 2022-',round((~H.good['2022':]).mean()*100,1),'%')
    print('不調 spells:',[(str(a.date()),int(b)) for a,b in ((g.index[0],len(g)) for _,g in H['2015':][~H.good['2015':]].groupby((H.good['2015':]!=H.good['2015':].shift()).cumsum()[~H.good['2015':]]))])
    for nm,sh in (('stocks only (sleeve 0%)',np.zeros(n)),('RULE 不調100/好調0',rule)):
        e=run(sh); print(f"{nm:28s} full {stats(e)[0]:.1%} DD {stats(e)[1]:.1%} | 2015-21 {stats(e,'2015','2021')[0]:.1%} DD {stats(e,'2015','2021')[1]:.1%} | 2022-26 {stats(e,'2022','2026')[0]:.1%} DD {stats(e,'2022','2026')[1]:.1%} | avg stocks {run.stock.mean():.0%} sleeve {run.sleeve.mean():.0%}")
