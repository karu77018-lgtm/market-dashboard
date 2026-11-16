import time, numpy as np, pandas as pd, prod
from prod import run, days, tp, qqq, fund, sessions, bars
H=250; i_first=days.index('2015-01-02'); last=len(days)-1
starts=list(range(i_first,last-20,2))
t0=time.time(); EQ=np.full((len(starts),H+1),np.nan); ST=np.zeros((len(starts),3)); QQ=np.full((len(starts),H+1),np.nan)
for k,i0 in enumerate(starts):
    i1=min(last,i0+H); pf=run(i0,i1)
    e=[x[1] for x in pf['equity']]; EQ[k,:len(e)]=e
    QQ[k,:len(e)]=[x[2]/pf['equity'][0][2] for x in pf['equity']]
    d0=pd.Timestamp(days[i0])
    for w,col in ((10,0),(20,1),(30,2)):
        lim=days[min(last,i0+w)]
        ST[k,col]=sum(1 for c in pf['closed'] if c['exit_day']<=lim and c['reason'].startswith('損切り'))
    if k%200==0: print(k,len(starts),round(time.time()-t0),flush=True)
np.save('fresh_eq.npy',EQ); np.save('fresh_st.npy',ST); np.save('fresh_qq.npy',QQ); pd.Series([days[i] for i in starts]).to_pickle('fresh_starts.pkl')
print('done',round(time.time()-t0))
