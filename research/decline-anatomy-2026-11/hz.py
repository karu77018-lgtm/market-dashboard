import pandas as pd, numpy as np, io, contextlib, warnings; warnings.filterwarnings('ignore')
with contextlib.redirect_stdout(io.StringIO()):
    import epi
n=epi.n; idx=epi.idx
G=pd.read_pickle('episodes_y.pkl'); P=G.iloc[:-1].copy(); cur=G.iloc[-1]
HZ=[10,20,60,120,250,500]
for h in HZ:
    P[f'r{h}']=[(n.iloc[idx.get_loc(pd.Timestamp(t))+h]/n[pd.Timestamp(t)]-1)*100 if idx.get_loc(pd.Timestamp(t))+h<len(n) else np.nan for t in P['T']]
skip={'peak','T','depth','more','final','bot','d2bot','f20','f60','f120','f250','done','rec12','oil','btc','month','pres','term','vvix','pc_pk','d3m','fedlvl','curve','since'}
FE=[c for c in P.columns if c not in skip and not c.startswith('r') or c in ('runup','run3y','rv20')]
FE=[c for c in FE if c not in [f'r{h}' for h in HZ]]
rows=[]
for f in FE:
    row={'factor':f}
    for h in HZ:
        x=P[[f,f'r{h}']].dropna()
        if len(x)<14: row[h]=np.nan; row[f'ok{h}']=False; continue
        k=len(x)//2; a,b=x.iloc[:k],x.iloc[k:]
        ra,rb=a[f].corr(a[f'r{h}'],method='spearman'),b[f].corr(b[f'r{h}'],method='spearman')
        row[h]=x[f].corr(x[f'r{h}'],method='spearman'); row[f'ok{h}']=bool(np.sign(ra)==np.sign(rb) and min(abs(ra),abs(rb))>=0.25); row['n']=len(x)
    rows.append(row)
R=pd.DataFrame(rows).set_index('factor'); R.to_pickle('hz.pkl')
def fmt(r): return ' '.join(f"{r[h]:+.2f}{'*' if r[f'ok{h}'] else ' '}" for h in HZ)
print('n episodes with outcome: ',{h:int(P[f'r{h}'].notna().sum()) for h in HZ})
print('base: median return',{h:round(P[f'r{h}'].median(),1) for h in HZ},'| % positive',{h:round((P[f'r{h}']>0).mean()*100) for h in HZ})
print('factor (n)           10d    20d    60d    120d   250d   500d   (* = same sign and |r|>=0.25 in both halves)')
for f,r in R.iterrows(): print(f"{f:10s}({int(r['n']) if not pd.isna(r.get('n',np.nan)) else 0:2d})  {fmt(r)}")
tot=sum(R[f'ok{h}'].sum() for h in HZ); print('starred cells',int(tot),'of',int(R[HZ].notna().sum().sum()))
# classify
print('\nSIGN FLIP short(10/20) vs long(250/500), |r|>=0.25 on both sides:')
for f,r in R.iterrows():
    s=np.nanmean([r[10],r[20]]); l=np.nanmean([r[250],r[500]])
    if abs(s)>=0.25 and abs(l)>=0.25 and np.sign(s)!=np.sign(l): print(f"  {f}: short {s:+.2f} long {l:+.2f} now={cur[f]:.1f}")
print('SHORT ONLY (|short|>=0.3, |long|<0.12):',[f for f,r in R.iterrows() if abs(np.nanmean([r[10],r[20]]))>=0.3 and abs(np.nanmean([r[250],r[500]]))<0.12])
print('LONG ONLY (|long|>=0.3, |short|<0.12):',[f for f,r in R.iterrows() if abs(np.nanmean([r[250],r[500]]))>=0.3 and abs(np.nanmean([r[10],r[20]]))<0.12])
print('MID ONLY (|60/120|>=0.3, others<0.15):',[f for f,r in R.iterrows() if abs(np.nanmean([r[60],r[120]]))>=0.3 and abs(np.nanmean([r[10],r[20]]))<0.15 and abs(np.nanmean([r[250],r[500]]))<0.15])
