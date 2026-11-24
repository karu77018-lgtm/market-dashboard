import sys, pandas as pd, numpy as np
sys.path.insert(0,'/home/claude/md/scripts')
import tqqq_rule as tr
from sl2 import P, idx, w0, full, go
hy=pd.read_csv('hy.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; hy=pd.to_numeric(hy,errors='coerce').dropna()
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna()
proxy=pd.concat([baa[:hy.index[0]-pd.Timedelta(days=1)]*(hy.iloc[0]/baa.asof(hy.index[0])), hy])
h=tr.known_before(proxy,idx); ratio=(h/h.rolling(40).mean()).to_numpy()
old=ratio>1.075
print('wide match with ledger flag', round((old==P.wide.fillna(False).to_numpy(bool)).mean()*100,1),'%')
if __name__=='__main__':
    def hyst(k_off,m):
        on=False; last=-999; out=np.zeros(len(ratio),bool)
        for i,r in enumerate(ratio):
            if np.isnan(r): out[i]=on; continue
            if r>1.075: on=True; last=i
            elif on and r<k_off and i-last>=m: on=False
            out[i]=on
        return out
    if __name__=="__main__": go("現行",w0)
    for k in (1.075,1.05,1.025,1.0):
        for m in (0,5,10,20):
            if k==1.075 and m==0: continue
            wide=hyst(k,m); w=w0.copy(); extra=wide&~old&~full
            w[extra]=np.minimum(w[extra],0.25)
            go(f'HY上限の解除: 比率<{k} かつ{m}日経過',w)
