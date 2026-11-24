import os, subprocess, pandas as pd, numpy as np
R=pd.read_pickle('g1.pkl'); sig=pd.read_pickle('honmei.pkl')
key=sig.merge(R[['date','t','ext','pmax','vcpt','sts']].rename(columns={'t':'ticker'}),on=['date','ticker'],how='left')
F=[('xFromMA 赤(>6)を見送る',~(key.ext>6)),('%MaxATRx 赤(>65)を見送る',~(key.pmax>65)),
   ('VCPT 赤(>25)を見送る',key.vcpt<=25),('STS 赤(<65)を見送る',key.sts>=65),
   ('3つとも赤なし(ext,pmax,VCPT)',~(key.ext>6)&~(key.pmax>65)&(key.vcpt<=25))]
cols=['date','ticker','rs189']
def run(name,df):
    df[cols].to_pickle('sig_tmp.pkl')
    out=subprocess.run(['python3','runeng.py'],env={**os.environ,'SIG':'sig_tmp.pkl','NAME':name},capture_output=True,text=True)
    print(out.stdout.strip() or out.stderr[-500:],flush=True)
for name,m in F:
    run(f'{name} (残す{m.mean()*100:.0f}%)',key[m])
    for s in range(6):
        r=np.random.default_rng(s).random(len(key))<m.mean()
        run(f'   ランダムに同じ割合を残す seed{s}',key[r])
