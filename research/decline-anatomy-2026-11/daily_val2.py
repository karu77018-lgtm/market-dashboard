import pandas as pd, numpy as np
W=pd.read_pickle('weekly_state.pkl')
FE=['dd','r63','r252','v200','rv20','vix','sox','spx','small','eqw','gv','dfn','fin','ene','sec50','d10','cred','usd']
OUT=['f20','f60','f120','f250']
def zmat(pe):
    P=W.iloc[:pe]; mu,sd=P[FE].mean(),P[FE].std(); return ((W[FE]-mu)/sd).to_numpy()
def nearest(i,pe,L=4,k=3,gap=26,Z=None):
    Z=zmat(pe) if Z is None else Z
    cand=np.arange(L-1,pe); D=np.zeros(len(cand)); C=np.zeros(len(cand))
    for l in range(L):
        a=Z[cand-l]; b=Z[i-l]; m=~np.isnan(a)&~np.isnan(b)
        D+=np.where(m,(a-b)**2,0).sum(1); C+=m.sum(1)
    d=np.sqrt(D/np.maximum(C,1)); ok=C>=12*L; order=cand[ok][np.argsort(d[ok])]; dd=np.sort(d[ok])
    picks=[]
    for j,v in zip(order,dd):
        if all(abs(j-p)>gap for p,_ in picks): picks.append((j,v))
        if len(picks)==k: break
    return picks
for L in (1,4,8):
    n=len(W); Z=zmat(n-52)
    tops=[nearest(i,n-52,L=L,k=1,Z=Z)[0][0] for i in range(n-60,n)]
    same=sum(abs(a-b)<=9 for a,b in zip(tops,tops[1:]))
    rows=[]
    for i in range(len(W)):
        if W.index[i]<pd.Timestamp('2008-01-01') or i%4: continue
        pe=i-52; pk=nearest(i,pe,L=L)
        r={o:W.iloc[i][o] for o in OUT}; r.update({o+'_k':np.nanmean([W.iloc[j][o] for j,_ in pk]) for o in OUT}); r.update({o+'_b':W.iloc[:pe][o].mean() for o in OUT}); rows.append(r)
    R=pd.DataFrame(rows)
    print(f"L={L}: top-1 stays within 2 months: {same}/59 | "+' '.join(f"{o} MAE {(R[o+'_k']-R[o]).abs().mean():.1f}/{(R[o+'_b']-R[o]).abs().mean():.1f}" for o in OUT))
    print('   last 6 weeks:',' ; '.join(W.index[i].strftime('%m/%d')+' '+'/'.join(W.index[j].strftime('%Y-%m') for j,_ in nearest(i,n-52,L=L,Z=Z)) for i in range(n-6,n)))
