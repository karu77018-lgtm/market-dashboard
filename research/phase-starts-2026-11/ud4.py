"""Rally anatomy: in a 10%+ decline, the first close 10% above its lowest close (re-armed by a new low).
Types by what drove the rise from the low; what followed (new high first? undercut of the low? 60/120/250 sessions)."""
import pandas as pd, numpy as np, sys, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    sys.argv=['ud.py','NDX']; exec(open('ud.py').read().split("R=pd.DataFrame(rows)")[0])
rows=[]; indec=False
for t in range(260,len(n)):
    c=n.iloc[t]
    if not indec:
        if dd.iloc[t]<=-0.10: indec=True; trough=c; ti=t; armed=True; pki=idx.get_loc(n.iloc[t-252:t+1].idxmax())
        continue
    if dd.iloc[t]>=-0.02: indec=False; continue
    if c<trough: trough=c; ti=t; armed=True
    elif armed and c>=trough*1.10:
        armed=False; j=t; res=np.nan
        while j<len(n)-1:
            j+=1
            if n.iloc[j]<trough: res=0.0; break
            if dd.iloc[j]>=-0.02: res=1.0; break
        f=feats(ti,t,'up'); f.update(fwd(t))
        rows.append(dict(date=idx[t],low=idx[ti],peak=idx[pki],ok=res,drop=(trough/n.iloc[pki]-1)*100,**f))
E=pd.DataFrame(rows); E['half']=np.where(E.date<'2008-01-01','1990-2007','2008-2026')
def typ(r):
    if pd.notna(r.cred) and r.cred<=-15: return '信用回復型'
    if r.d10<=-20: return '金利低下型'
    if r.spx<=-5: return 'ハイテク主導型'
    if pd.notna(r.cyc) and r.small>=2 and r.cyc>=1: return '小型・景気敏感主導型'
    return '全面高型'
E['type']=E.apply(typ,axis=1); E.to_pickle('rally_ep.pkl')
pd.set_option('display.width',250)
print(E[['date','low','drop','days','ok','type','d10','cred','spx','small','cyc','a50','maxday','f60','f250']].round(1).to_string(index=False))
g=E.groupby('type'); print(pd.DataFrame({'n':g.size(),'本物の底%':g.ok.mean()*100,'f60':g.f60.median(),'f250':g.f250.median()}).round(1))
print('by half'); print(E.groupby(['half','type']).ok.agg(['size','mean']).round(2))
for k,cut in (('a50',0.5),('days',10),('maxday',4),('ftd',0.5),('drop',-20)):
    for h in ('1990-2007','2008-2026'):
        z=E[E.half==h].dropna(subset=[k]); gg=z[k]>cut
        print(f'{k}>{cut} {h}: {z[gg].ok.mean()*100:3.0f}% (n{gg.sum()}) vs {z[~gg].ok.mean()*100:3.0f}% (n{(~gg).sum()})')
