"""Robustness of the candidate uses: neighbours of the cuts, day-based counts, SPY as a second index, by year."""
import pandas as pd, numpy as np
X=pd.read_pickle('fx.pkl')
def idx(tk):
    s=pd.read_csv(f'ftd_{tk}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').close
    c=s.reindex(X.index).to_numpy(); n=len(c)
    r60=pd.Series([c[i+60]/c[i]-1 if i+60<n else np.nan for i in range(n)],X.index)
    dd=pd.Series([c[i+1:i+61].min()/c[i]-1 if i+60<n else np.nan for i in range(n)],X.index)
    s200=(s>s.rolling(200).mean()).reindex(X.index)
    return r60,dd,s200
for tk in ('QQQ','SPY'):
    r60,dd,up=idx(tk)
    print(f'\n######## {tk}  (day-based; baseline r60/DD10 by half)')
    def line(name,m):
        o=[]
        for h in ('2013-19','2020-26'):
            hm=X.half==h; mm=m&hm
            o.append(f'{h}: d={mm.sum():4d} r60 {r60[mm].mean()*100:+5.1f}({r60[hm].mean()*100:+.1f}) DD10 {(dd[mm]<=-.1).mean()*100:3.0f}%({(dd[hm]<=-.1).mean()*100:.0f}%)')
        print(f'{name:30s}',' | '.join(o))
    for th in (0.5,0.55,0.6,0.65,0.7):
        line(f'200日線下 & F3≥{th}',(~up.astype(bool))&(X.f3>=th))
    for th in (0.5,0.6,0.7):
        line(f'200日線上 & F3≥{th}',(up.astype(bool))&(X.f3>=th))
    line('200日線下 & F3<0.4',(~up.astype(bool))&(X.f3<0.4))
    for th in (0.15,0.2,0.25):
        line(f'F2<{th}',X.f2<th)
    line('F1<.2&F2<.25&F3<.4',(X.f1<0.2)&(X.f2<0.25)&(X.f3<0.4))
    w=X.f3.rolling(20).max()
    for a,b in ((0.55,0.35),(0.6,0.3),(0.6,0.35),(0.65,0.3),(0.6,0.25)):
        line(f'F3 {a}以上→{b}以下(20日内)',(w>=a)&(X.f3<=b))
# by year: F2<0.2 share and r60 gap; F3 clear
r60,dd,up=idx('QQQ'); X['r60q']=r60
X['yr']=X.index.year
g=X.groupby('yr')
print('\nby year QQQ r60: F2<0.2 vs rest; days with F2<0.2')
print(pd.DataFrame({'F2low_d':g.apply(lambda x:(x.f2<0.2).sum()),'F2low':g.apply(lambda x:x.r60q[x.f2<0.2].mean()*100),'rest':g.apply(lambda x:x.r60q[x.f2>=0.2].mean()*100)}).round(1).T.to_string())
