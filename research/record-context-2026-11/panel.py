import pandas as pd, numpy as np, glob, os
fr={}
for k in ('open','high','low','close','volume'): fr[k]={}
for f in glob.glob('bars/*.csv'):
    t=os.path.basename(f)[:-4]
    d=pd.read_csv(f,index_col=0,parse_dates=True)
    d=d[~d.index.duplicated(keep='last')]
    if len(d)<60: continue
    for k in fr: fr[k][t]=d[k]
P={k:pd.DataFrame(v).sort_index() for k,v in fr.items()}
cal=P['close']['SPY'].dropna().index
for k in P: P[k]=P[k].reindex(cal).astype('float32'); P[k].to_pickle(f'{k}.pkl')
c=P['close']; print(c.shape, c.index[0], c.index[-1]); print(c.notna().sum(axis=1).iloc[[0,500,1000,2000,-1]])
# sanity: crazy daily moves
r=c.pct_change(fill_method=None); print('abs ret>3x count', int((r.abs()>3).sum().sum()))
