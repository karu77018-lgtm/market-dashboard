import numpy as np, pandas as pd, json
L=pd.read_pickle('prod_full.pkl'); L.index=pd.to_datetime(L.index)
eq=L['eq']; prev=eq.shift(1).fillna(1.0)
tot=eq-prev; sl=L['sleeve_pnl']; stk=tot-sl
rs=sl/prev; rk=stk/prev
print('avg weights: stock %.0f%% sleeve %.0f%% cash %.0f%%'%((L.stock_v/eq).mean()*100,(L.sleeve_v/eq).mean()*100,(1-(L.stock_v+L.sleeve_v)/eq).mean()*100))
print('sum of daily contributions: stock %.0f pt, sleeve %.0f pt -> sleeve share %.0f%%'%(rk.sum()*100,rs.sum()*100,rs.sum()/(rs.sum()+rk.sum())*100))
for a,b in (('2015','2021'),('2022','2026')): print('  ',a,b,'stock %.0f pt sleeve %.0f pt'%(rk[a:b].sum()*100,rs[a:b].sum()*100))
n=29; w_tot=(eq/eq.shift(n)-1); w_s=rs.rolling(n).sum(); w_k=rk.rolling(n).sum()
bad=w_tot<=-0.10
print('29-session windows <= -10%%: %d days (%.1f%%)'%(bad.sum(),bad.mean()*100))
x=pd.DataFrame({'tot':w_tot,'stock':w_k,'sleeve':w_s})[bad]
print(x.describe().loc[['mean','25%','50%','75%','min']].round(3).to_string())
ep=(x.index.to_series().diff().dt.days.fillna(99)>20).cumsum().values
rows=[]
for _,g in x.groupby(ep):
    i=g.tot.idxmin(); rows.append((g.index[0].date(),g.index[-1].date(),round(g.tot.min(),3),round(g.stock[i],3),round(g.sleeve[i],3)))
print(pd.DataFrame(rows,columns=['from','to','worst29','stock','sleeve']).to_string())
live=json.load(open('/home/claude/md/track-record/signals.json'))['modeled_portfolio']
stock=sum(c['pnl'] for c in live['closed'])+sum(p['shares']*p['last']-p['invested'] for p in live['positions'].values()); tot_l=live['equity'][-1][1]-1
print('live: total %.3f stock %.3f sleeve %.3f'%(tot_l,stock,tot_l-stock))
print([(d,round(v,3)) for d,v,_ in live['equity'] if d in ('2026-10-16','2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23','2026-11-05','2026-11-13')])
t=json.load(open('/home/claude/md/track-record/tqqq-rule.json'))['days']
print({d[5:]:(t[d].get('target'),t[d].get('full')) for d in sorted(t) if d>='2026-10-14'})
