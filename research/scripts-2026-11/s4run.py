import pandas as pd, numpy as np, stage4, multiprocessing as mp
O,H,L,C=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','high','low','close'))
On,Hn,Ln,Cn=(x.to_numpy() for x in (O,H,L,C))
def one(j):
    c=Cn[:,j]; ok=~np.isnan(c)
    if ok.sum()<300: return j,None
    a=np.argmax(ok)  # first valid bar; panel rows are the SPY calendar
    st,brk,fail,pk,lw=stage4.run(On[a:,j],Hn[a:,j],Ln[a:,j],c[a:])
    S=np.zeros(len(c),np.int8); B=np.zeros(len(c),bool); F=np.zeros(len(c),bool)
    S[a:]=st; B[a:]=brk; F[a:]=fail
    return j,(S,B,F)
if __name__=='__main__':
    with mp.Pool(mp.cpu_count()) as p: res=p.map(one,range(C.shape[1]),chunksize=20)
    S=np.zeros(C.shape,np.int8); B=np.zeros(C.shape,bool); F=np.zeros(C.shape,bool)
    for j,r in res:
        if r: S[:,j],B[:,j],F[:,j]=r
    pd.to_pickle(dict(S=S,B=B,F=F,index=C.index,columns=C.columns),'s4.pkl')
    print('breaks',B.sum(),'fails',F.sum(),'S4 stock-days',(S==1).sum())
