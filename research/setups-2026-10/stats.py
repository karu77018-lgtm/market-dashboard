import pandas as pd, numpy as np, sys
def S(d, col='ret'):
    if len(d)==0: return dict(n=0)
    r=d[col]; pos=r[r>0].sum(); neg=-r[r<0].sum()
    return dict(n=len(d), win=round((r>0).mean()*100,1), avg=round(r.mean()*100,2), med=round(r.median()*100,2),
                pf=round(pos/neg,2) if neg>0 else np.inf, days=round(d.days.mean(),1), big=int((r>=0.5).sum()))
def show(name, d):
    print(f'\n=== {name}')
    print('  base   ', S(d)); print('  w/adds ', S(d,'ret_add'))
for f in sys.argv[1:]:
    d=pd.read_csv(f, parse_dates=['date']); d=d[d.date>='2015-01-01']
    on=d[d.regime]
    show(f+' ALL', d); show(f+' regime ON', on); show(f+' regime OFF', d[~d.regime])
    print('  by year (ON, base):'); print(on.groupby(on.date.dt.year).apply(lambda g: pd.Series(S(g))).to_string())
    if 'base_no' in on:
        print('  by base_no (ON):'); print(on.groupby(on.base_no.clip(upper=3)).apply(lambda g: pd.Series(S(g))).to_string())
        print('  by age (ON):'); print(on.groupby(pd.cut(on.age,[0,63,126,252,504])).apply(lambda g: pd.Series(S(g))).to_string())
        print('  dayret<3% (ON):', S(on[on.dayret<0.03])); print('  ext<=5% (ON):', S(on[on.ext<=0.05]))
