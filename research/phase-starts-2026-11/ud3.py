"""(1) VIX cut for decline starts on both indices; (2) rally anatomy: +10% off the low of a 10%+ decline."""
import pandas as pd, numpy as np, sys, io, contextlib
for nm in ('NDX','GSPC'):
    R=pd.read_pickle(f'ud2_{nm}.pkl'); D=R[R.kind=='down']
    for cut in (20,23,25,28):
        o=[]
        for h in ('1990-2007','2008-2026'):
            z=D[D.half==h]; g=z.vix>=cut
            o.append(f'{h}: VIX≥{cut} {z[g].hit10.mean()*100:3.0f}% (n{g.sum()}) / 未満 {z[~g].hit10.mean()*100:3.0f}% (n{(~g).sum()})')
        print(nm,'down->-10%',' | '.join(o))
    for cut in (-3,-5):
        o=[]
        for h in ('1990-2007','2008-2026'):
            z=D[D.half==h].dropna(subset=['sox']); g=z.sox<=cut
            o.append(f'{h}: 半導体{cut}pt以上劣後 {z[g].hit10.mean()*100:3.0f}% (n{g.sum()}) / 他 {z[~g].hit10.mean()*100:3.0f}%')
        print(nm,' '.join(o))
    U=R[R.kind=='up']
    o=[]
    for h in ('1990-2007','2008-2026'):
        z=U[U.half==h]; g=z.a50>0.5
        o.append(f'{h}: 50日線上 {z[g].ok.mean()*100:3.0f}% (n{g.sum()}) / 下 {z[~g].ok.mean()*100:3.0f}% (n{(~g).sum()})')
    print(nm,'up->bottom',' | '.join(o))
