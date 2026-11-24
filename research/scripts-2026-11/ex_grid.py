import pandas as pd, numpy as np, x2, sys
H,L,C=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('high','low','close'))
tick=sorted(set(pd.read_pickle('honmei.pkl').ticker)); H,L,C=H[tick],L[tick],C[tick]
days=[d.strftime('%Y-%m-%d') for d in C.index]
n,m=int(sys.argv[1]),float(sys.argv[2])
ch=x2.chandelier_long(H,L,C,n,m); mask=C<ch
pd.to_pickle({t:pd.Series(mask[t].fillna(False).to_numpy(bool),index=days) for t in tick},'ex_tmp.pkl')
