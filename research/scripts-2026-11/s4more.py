import pandas as pd, numpy as np
D=pd.read_pickle('s4eval.pkl'); D['y']=D.date.dt.year
a=D[D.name=='TLブレイク']; b=D[D.name=='大化け候補ブレイク(既存)']; s=D[D.name=='ステージ4の任意の日']
print('TLブレイク: RS別（2014-19 | 2020-25）  2倍到達% / −25%トレール平均%')
for lo,hi in ((0,50),(50,70),(70,80),(80,90),(90,101)):
    z=a[(a.rs>=lo)&(a.rs<hi)]
    print(f' RS{lo}-{hi}: ',' | '.join(f"{(w.dbl.mean()*100):5.1f} / {w.trail.mean()*100:+5.1f} (n{len(w)})" for w in (z[z.date<'2020'],z[z.date>='2020'])))
print('年別 −25%トレール平均%: TL+RS80 vs 既存の大化け候補ブレイク vs ステージ4任意日')
t=a[a.rs>=80]
for y in range(2014,2026):
    print(y, f"{t[t.y==y].trail.mean()*100:+6.1f} (n{(t.y==y).sum():4d})", f"{b[b.y==y].trail.mean()*100:+6.1f} (n{(b.y==y).sum():4d})", f"{s[s.y==y].trail.mean()*100:+6.1f}")
