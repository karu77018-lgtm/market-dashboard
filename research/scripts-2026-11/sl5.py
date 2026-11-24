import pandas as pd, numpy as np
from sl2 import P, idx, w0, full, go
for step in (0.25,0.5):
    for every in (1,2):
        w=w0.copy(); last=-99
        for i in range(1,len(w)):
            if w[i]>w[i-1]+1e-9 and not full[i]:
                if i-last>=every: w[i]=min(w0[i],w[i-1]+step); last=i
                else: w[i]=w[i-1]
        go(f'増やすときは{int(step*100)}%ずつ・{every}日ごと',w)
