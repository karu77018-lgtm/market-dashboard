import pandas as pd, numpy as np
R=pd.read_pickle('g1.pkl')
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
def line(z): return f'PF{pf(z.ret):5.2f} 平均{z.ret.mean()*100:+5.1f}% 勝率{(z.ret>0).mean()*100:3.0f}% n{len(z):4d}'
B={'xFromMA(ATR倍)':('ext',[-99,3.5,6,99],['緑≤3.5','黄3.5-6','赤>6']),
   '%MaxATRx':('pmax',[-999,40,65,999],['緑≤40','黄40-65','赤>65']),
   'VCPT':('vcpt',[-1,10,25,101],['緑≤10','黄≤25','赤>25']),
   'STS':('sts',[-1,64.9,89.9,101],['赤<65','黄65-89','緑≥90']),
   'ATR%':('atr_pct',[0,5,9,99],['<5','緑5-9','>9']),
   'MM':('mm',[-1,7.5,9],['≤7','8/8']),
   'VolBuzz':('buzz',[-999,-15,30,9999],['赤<-15','黄','緑≥30'])}
print('全体', ' | '.join(line(R[R.half==h]) for h in ('2014-19','2020-26')))
for name,(k,b,lab) in B.items():
    print('---',name)
    cut=pd.cut(R[k],b,labels=lab)
    for l in lab:
        print(f'  {l:8s}',' | '.join(line(R[(R.half==h)&(cut==l)]) for h in ('2014-19','2020-26')))
