"""Event-style uses of F1-F3 for the index: divergence at highs, fast rises, washouts and their clearing."""
import pandas as pd, numpy as np
X=pd.read_pickle('fx.pkl')
q=pd.read_csv('ftd_QQQ.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').close
X['q']=q.reindex(X.index); X['hi']=q.rolling(252).max().reindex(X.index); X['offhi']=X.q/X.hi-1
X['s50']=q.rolling(50).mean().reindex(X.index); X['s200']=q.rolling(200).mean().reindex(X.index)
for k in ('f1','f2','f3'): X['d'+k]=X[k]-X[k].shift(10)
def events(mask,gap=20):
    out=[];last=-999
    for i,(d,m) in enumerate(mask.items()):
        if m and i-last>gap: out.append(d)
        if m: last=i
    return out
base=X.groupby('half')[['r20','r60','dd60']].agg(lambda x: x.mean() if x.name!='dd60' else (x<=-0.1).mean())
def show(name,mask):
    ev=events(mask.fillna(False)); E=X.loc[ev]
    out=[]
    for h in ('2013-19','2020-26'):
        e=E[E.half==h]; b=X[X.half==h]
        out.append(f"{h}: n={len(e):2d} r20 {e.r20.mean()*100:+.1f}({b.r20.mean()*100:+.1f}) r60 {e.r60.mean()*100:+.1f}({b.r60.mean()*100:+.1f}) DD10 {(e.dd60<=-0.1).mean()*100:3.0f}%({(b.dd60<=-0.1).mean()*100:.0f}%)")
    print(f'{name:38s}', ' | '.join(out))
print('event (baseline in brackets)')
for th in (0.35,0.40,0.45,0.50):
    show(f'高値圏(−3%以内)でF1≥{th}', (X.offhi>=-0.03)&(X.f1>=th))
for th in (0.5,0.6):
    show(f'高値圏でF2≥{th}', (X.offhi>=-0.03)&(X.f2>=th))
show('高値圏でF1≥0.4かつF2≥0.5', (X.offhi>=-0.03)&(X.f1>=0.4)&(X.f2>=0.5))
for th in (0.15,0.20,0.25):
    show(f'F1が10日で+{th}以上', X.df1>=th)
    show(f'F2が10日で+{th}以上', X.df2>=th)
    show(f'F3が10日で+{th}以上', X.df3>=th)
for th in (0.7,0.8):
    show(f'F3≥{th}（総崩れ）', X.f3>=th)
# clearing: F3 was >=0.6 within last 20 sessions, now <=0.4
was=X.f3.rolling(20).max()
for a,b in ((0.6,0.4),(0.6,0.3),(0.7,0.4)):
    show(f'F3が{a}以上→{b}以下に回復', (was>=a)&(X.f3<=b))
show('F1が警戒→注意以下に回復', (X.f1.rolling(20).min()>=0.30).shift(1)&(X.f1<0.2))
show('全灯平常（F1<.2,F2<.25,F3<.4）', (X.f1<0.2)&(X.f2<0.25)&(X.f3<0.4))
show('全灯警戒', (X.f1>=0.3)&(X.f2>=0.4)&(X.f3>=0.6))
show('200日線上でF3≥0.6', (X.q>X.s200)&(X.f3>=0.6))
show('200日線下でF3≥0.6', (X.q<X.s200)&(X.f3>=0.6))
