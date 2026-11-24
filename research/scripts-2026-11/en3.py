import os, subprocess, pandas as pd, numpy as np, x2
S=pd.read_pickle('en1.pkl')
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
print('年別 PF: UD<1.3 | UD≥1.3')
w=0
for y in range(2014,2027):
    z=S[S.date.dt.year==y]; a,b=z[z.ud<1.3],z[z.ud>=1.3]
    pa,pb=pf(a.ret),pf(b.ret); w+=pa>pb
    print(y, f'{pa:5.2f} (n{len(a):3d}) | {pb:5.2f} (n{len(b):3d})')
print('UD<1.3が上回った年', w, '/13')
# length sweep in the engine
C,V=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('close','volume'))
sig=pd.read_pickle('honmei.pkl'); tick=sorted(set(sig.ticker)); C,V=C[tick],V[tick]
cols=['date','ticker','rs189']
def run(name,df):
    df[cols].to_pickle('sig_tmp.pkl')
    o=subprocess.run(['python3','runeng3.py'],env={**os.environ,'SIG':'sig_tmp.pkl','NAME':name},capture_output=True,text=True)
    print(o.stdout.strip() or o.stderr[-400:],flush=True)
for n in (30,50,65):
    ud=x2.updn(C,V,n); u=np.array([ud.at[d,t] for d,t in zip(sig.date,sig.ticker)])
    for th in (1.1,1.2,1.3,1.4,1.5,1.6):
        m=~(u>=th); run(f'UD{n}日 ≥{th}を見送る 残{m.mean()*100:.0f}%',sig[m])
