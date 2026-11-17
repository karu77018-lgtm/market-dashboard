"""Reference numbers for scripts/phase_check.py (NDX for rallies, S&P 500 + VIX for decline starts)."""
import pandas as pd, numpy as np, json
R=pd.read_pickle('ud2_NDX.pkl'); U=R[(R.kind=='up')].dropna(subset=['ok']).copy()
U['s']=(U.a50>0.5).astype(int)+(U.days>3).astype(int)+(U.maxday<3.7).astype(int)
E=pd.read_pickle('rally_ep.pkl').dropna(subset=['ok']).copy()
E['s']=(E.a50>0.5).astype(int)+(E.days>10).astype(int)+(E.maxday<4).astype(int)
S=pd.read_pickle('ud2_GSPC.pkl'); D=S[S.kind=='down'].copy()
out={}
def by(df,col):
    g=df.groupby(col)
    return {int(k):{'n':int(len(v)),'ok':int(v.ok.sum()),'ex':[str(d.date())[:7] for d in v.date.iloc[::-1][:4]]} for k,v in g}
out['up5']=by(U,'s'); out['up10']=by(E,'s')
for k,df in (('up5',U),('up10',E)):
    out[k+'_all']={'n':int(len(df)),'ok':int(df.ok.sum())}
    for h in ('1990-2007','2008-2026'):
        z=df[df.half==h] if 'half' in df else df
        out[k+'_'+h]={int(s):[int(len(v)),int(v.ok.sum())] for s,v in z.groupby('s')}
g=D.vix>=23
out['down5']={'hi':{'n':int(g.sum()),'hit':int(D[g].hit10.sum())},'lo':{'n':int((~g).sum()),'hit':int(D[~g].hit10.sum())},'all':{'n':len(D),'hit':int(D.hit10.sum())}}
for h in ('1990-2007','2008-2026'):
    z=D[D.half==h]; gg=z.vix>=23; out['down5_'+h]={'hi':[int(gg.sum()),int(z[gg].hit10.sum())],'lo':[int((~gg).sum()),int(z[~gg].hit10.sum())]}
out['types']={t:{'n':int(len(v)),'ok':int(v.ok.sum())} for t,v in E.groupby('type')}
# FTD at +10%
F=E.dropna(subset=['ftd']); out['ftd10']={'yes':[int((F.ftd>0.5).sum()),int(F[F.ftd>0.5].ok.sum())],'no':[int((F.ftd<0.5).sum()),int(F[F.ftd<0.5].ok.sum())]}
print(json.dumps(out,ensure_ascii=False,indent=1))
json.dump(out,open('phase_ref.json','w'),ensure_ascii=False,indent=1)
