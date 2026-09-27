# ML edge search (gap). Run from a work dir whose parent holds stocks_all.csv.gz, data/*.csv (QQQ,TQQQ,VIX,US10Y) and macro/*.csv (TradingView daily).
import pandas as pd, numpy as np, pickle
D=pickle.load(open("raw.pkl","rb")); C,O=D["C"],D["O"]
df=pd.read_csv("../stocks_all.csv.gz",parse_dates=["date"]); df=df[df.date>="2021-12-14"]
V=df.pivot(index="date",columns="sym",values="v").reindex(C.index)[C.columns]
H_=df.pivot(index="date",columns="sym",values="h").reindex(C.index)[C.columns]; L_=df.pivot(index="date",columns="sym",values="l").reindex(C.index)[C.columns]
on=O/C.shift(1)-1; vz=V/V.rolling(60).mean().shift(1)
cl_pos=(C-L_)/(H_-L_)          # 当日引けの位置（強い引け=1）
ew=C.pct_change(fill_method=None).mean(axis=1)                    # 等金額ユニバース
mkt=(1+ew.fillna(0)).cumprod()
rows=[]
ii=np.argwhere(((on.abs()>0.04)&(vz>2.5)).values)
for i,j in ii:
    if i<260 or i+61>=len(C): continue
    s=C.columns[j]; e=O.iat[i+1,j]          # 翌日寄りで買う
    if np.isnan(e): continue
    r={h:(C.iat[i+h,j]/e-1)-(mkt.iat[i+h]/mkt.iat[i]-1) for h in [5,20,60]}
    rows.append(dict(date=C.index[i],sym=s,gap=on.iat[i,j],day=C.iat[i,j]/O.iat[i,j]-1,clpos=cl_pos.iat[i,j],vz=vz.iat[i,j],
                     pre63=C.iat[i-1,j]/C.iat[i-64,j]-1,**{f"x{h}":v for h,v in r.items()}))
E=pd.DataFrame(rows); print("イベント数",len(E), E.date.min().date(),E.date.max().date())
def sh(nm,m):
    g=E[m]; print(f"  {nm:40s} n={len(g):5d} 超過5d={g.x5.mean():+.2%} 20d={g.x20.mean():+.2%} 60d={g.x60.mean():+.2%} (t60={g.x60.mean()/g.x60.std()*np.sqrt(len(g)):+.1f}) 勝率60d={(g.x60>0).mean():.0%}")
sh("ギャップアップ全体",E.gap>0); sh("ギャップダウン全体",E.gap<0)
sh("GU & 当日も上昇(寄り<引け)",(E.gap>0)&(E.day>0))
sh("GU & 当日上昇 & 引け上位25%",(E.gap>0)&(E.day>0)&(E.clpos>0.75))
sh("GU>8% & 当日上昇",(E.gap>0.08)&(E.day>0))
sh("GU & 当日上昇 & 出来高5倍",(E.gap>0)&(E.day>0)&(E.vz>5))
sh("GU & 当日下落(寄り天)",(E.gap>0)&(E.day<0))
sh("GD & 当日下落",(E.gap<0)&(E.day<0))
sh("GD & 当日上昇(下げ渋り)",(E.gap<0)&(E.day>0))
m=(E.gap>0)&(E.day>0)
for y,g in E[m].groupby(E.date.dt.year): print(f"    {y}: n={len(g)} 60d超過={g.x60.mean():+.2%} 20d={g.x20.mean():+.2%}")
E.to_pickle("gap_events.pkl")
