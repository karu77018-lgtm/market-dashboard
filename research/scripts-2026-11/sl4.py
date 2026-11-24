import sys, pandas as pd, numpy as np
from sl2 import P, idx, w0, full, go, qc
from sl3 import ratio, old
# after an HY-cap episode, stay at <=25% until the price confirms as well
e10=qc.ewm(span=10,adjust=False).mean(); e21=qc.ewm(span=21,adjust=False).mean(); m50=qc.rolling(50).mean()
conf={'QQQが10EMAの上':qc>e10,'QQQが21EMAの上':qc>e21,'QQQが50日線の上':qc>m50,'QQQが5日前より上':qc>qc.shift(5),'QQQが10日高値更新':qc>=qc.rolling(10).max()}
for k,c in conf.items():
    c=c.fillna(False).to_numpy(bool); held=False; w=w0.copy()
    for i in range(len(w)):
        if old[i]: held=True
        elif held and c[i]: held=False
        if held and not old[i] and not full[i]: w[i]=min(w[i],0.25)
    go('HY上限の解除に'+k+'を追加',w)
