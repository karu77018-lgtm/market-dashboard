# Concentrated single-stock swing study (rankfx). Run from a work dir whose parent holds stocks_all.csv.gz and data/QQQ.csv.
exec(open("conc2.py").read().split("IS=(")[0])
import itertools
full=("2022-10-01","2026-09-30"); rows=[]
for L_,top,rsi,mh,K in itertools.product([63,126],[0.1,0.2,0.3],[5,10,20],[5,10],[1,3]):
    s,sc=A(L_,top,rsi); r=met(run(s,sc,K,exA,mh,None,*full)[0])[0]
    rnd=np.median([met(run(s,sc,K,exA,mh,None,*full,seed=k)[0])[0] for k in range(10)])
    # 前半/後半それぞれ
    h1=met(run(s,sc,K,exA,mh,None,"2022-10-01","2024-07-01")[0])[0]; h2=met(run(s,sc,K,exA,mh,None,"2024-07-01","2026-09-30")[0])[0]
    rows.append((L_,top,rsi,mh,K,r,rnd,h1,h2))
R=pd.DataFrame(rows,columns=["L","top","rsi","mh","K","ranked","random_med","h1","h2"])
R["edge"]=R.ranked-R.random_med
print(R.groupby("K")[["ranked","random_med","edge","h1","h2"]].median().map(lambda v:f"{v:+.1%}"))
print("順位付き>ランダム中央 の割合:",R.groupby("K").apply(lambda g:(g.edge>0).mean()).to_dict())
print("前半・後半とも+20%超:",R[(R.h1>0.2)&(R.h2>0.2)].to_string(float_format=lambda v:f"{v:+.1%}"))
R.to_pickle("rankfx.pkl")
