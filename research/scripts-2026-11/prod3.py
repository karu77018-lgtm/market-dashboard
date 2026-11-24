"""Run the dashboard's production engine (scripts/track_portfolio.step) over history with rebuilt signals."""
import sys, copy, numpy as np, pandas as pd
sys.path.insert(0,'/home/claude/md/scripts')
import tp_x as tp
tp.EFFECTIVE_DATE='2000-01-01'; tp.GUARD_DATE='2000-01-01'     # current rule (80% cap, 利益保護) for every session
C=pd.read_pickle('close.pkl').astype('float64'); O=pd.read_pickle('open.pkl').astype('float64'); Lw=pd.read_pickle('low.pkl').astype('float64')
dates=C.index; days=[d.strftime('%Y-%m-%d') for d in dates]
import os; sig=pd.read_pickle(os.environ.get('SIG','honmei.pkl')); H=pd.read_pickle('health.pkl'); F=pd.read_pickle(os.environ.get('FUND','tqfund.pkl'))['proxy'].reindex(dates)
q=C['QQQ']; reg=(q>q.rolling(200).mean())
if os.environ.get('REG'): reg=pd.read_pickle(os.environ['REG']).reindex(dates).fillna(False).astype(bool)
share=np.where(H.full.to_numpy(bool),100,np.where(H.good.to_numpy(bool),0,100))
best={}
for d,t,r in zip(sig.date,sig.ticker,sig.rs189): best.setdefault(d.strftime('%Y-%m-%d'),[]).append({'t':t,'r189':float(r)})
sessions={day:{'regime':'on' if reg.iloc[i] else 'off','best':best.get(day,[]),'qqq_pct':int(share[i])} for i,day in enumerate(days)}
tick=sorted(set(sig.ticker))
bars={t:pd.DataFrame({'open':O[t],'low':Lw[t],'close':C[t]}).dropna() for t in tick}
qqq={day:{'open':float(O['QQQ'].iloc[i]),'close':float(C['QQQ'].iloc[i])} for i,day in enumerate(days)}
fund={day:{'open':float(F.nav_o.iloc[i]),'close':float(F.nav_c.iloc[i])} for i,day in enumerate(days) if not np.isnan(F.nav_c.iloc[i])}
def run(i0,i1,log=False):
    """fresh portfolio whose first recorded session is days[i0]; advance through days[i1]"""
    pf=tp.new_portfolio(days[i0]); pf['qqq_pct']=0; pf['equity']=[[days[i0],1.0,qqq[days[i0]]['close']]]
    rows=[]
    for i in range(i0+1,i1+1):
        day,prev=days[i],days[i-1]; u0=pf['qqq_sh']; f=fund[day]
        tp.step(pf,day,prev,qqq[day],sessions.get(prev),bars,f)
        if log:
            sl=u0*(f['open']-fund[prev]['close'])+pf['qqq_sh']*(f['close']-f['open'])
            rows.append((day,pf['equity'][-1][1],sl,sum(p['shares']*p['last'] for p in pf['positions'].values()),pf['qqq_sh']*f['close']))
    return (pf,pd.DataFrame(rows,columns=['day','eq','sleeve_pnl','stock_v','sleeve_v']).set_index('day')) if log else pf
if __name__=='__main__':
    i0=days.index('2015-01-02')
    for end in ('2026-10-28','2026-11-13'):
        pf,L=run(i0,days.index(end),log=True)
        e=L['eq'].copy(); e.index=pd.to_datetime(e.index); yrs=(e.index[-1]-pd.Timestamp('2015-01-02')).days/365.25
        print(end,'CAGR',round(e.iloc[-1]**(1/yrs)-1,3),'maxDD',round((e/e.cummax()-1).min(),3),'x',round(e.iloc[-1]),'trades',len(pf['closed']))
        for a,b in (('2015','2020'),('2021','2026')):
            s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25; print('   ',a,b,round((s.iloc[-1]/s.iloc[0])**(1/y)-1,3))
    L.to_pickle('prod_full.pkl'); m=e.resample('ME').last().pct_change().dropna(); print('worst months',(m.nsmallest(5)*100).round(1).to_dict())
    y=e.resample('YE').last(); print({k.year:round(v*100,1) for k,v in (y/y.shift(1).fillna(1)-1).items()})
