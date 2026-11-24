import os, pandas as pd, numpy as np
from sl2 import P, idx, w0, full, go
def ramp(step):
    w=w0.copy()
    for i in range(1,len(w)):
        if w[i]>w[i-1]+1e-9 and not full[i]: w[i]=min(w0[i],w[i-1]+step)
    return w
os.environ['SIG']='sig_ud.pkl'
go('UD比フィルター＋現行の枠',w0)
go('UD比フィルター＋枠25%ずつ',ramp(0.25))
go('UD比フィルター＋枠50%ずつ',ramp(0.5))
# yearly check for ramp25 vs current (sleeve alone)
from sl2 import nav
a=pd.Series(nav(w0)[1],index=idx); b=pd.Series(nav(ramp(0.25))[1],index=idx)
ya=a.resample('YE').last().pct_change(); yb=b.resample('YE').last().pct_change()
print('枠単体の年別差(25%ずつ−現行, pt):',{d.year:round((yb[d]-ya[d])*100,1) for d in ya.index if d.year>=2015})
