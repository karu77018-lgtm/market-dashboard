import pandas as pd, numpy as np, x2
O,H,L,C=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','high','low','close'))
tick=sorted(set(pd.read_pickle('honmei.pkl').ticker))
H,L,C=H[tick],L[tick],C[tick]
days=[d.strftime('%Y-%m-%d') for d in C.index]
def todict(mask):
    return {t:pd.Series(mask[t].fillna(False).to_numpy(bool),index=days) for t in tick}
ch=x2.chandelier_long(H,L,C); pd.to_pickle(todict(C<ch),'ex_chand.pkl')
a10=x2.atr(H,L,C,10)
ut={};st={}
for t in tick:
    c=C[t].to_numpy(); ok=~np.isnan(c)
    if ok.sum()<30: continue
    f=np.argmax(ok)
    ts=np.full(len(c),np.nan); ts[f:]=x2.utbot(c[f:],a10[t].to_numpy()[f:])
    ut[t]=pd.Series(c<ts,index=days)
    s,d=x2.supertrend(H[t].to_numpy()[f:],L[t].to_numpy()[f:],c[f:],a10[t].to_numpy()[f:])
    dd=np.zeros(len(c)); dd[f:]=d
    st[t]=pd.Series(dd==1,index=days)
pd.to_pickle(ut,'ex_ut.pkl'); pd.to_pickle(st,'ex_st.pkl')
print('ok',len(tick))
