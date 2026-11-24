import os, subprocess, pandas as pd
C=pd.read_pickle('close.pkl').astype(float); q=C['QQQ']; days=[d.strftime('%Y-%m-%d') for d in C.index]
def bad_set(m): return [d for d,b in zip(days,m.fillna(False).to_numpy(bool)) if b]
def run(name,bad,**kw):
    pd.to_pickle(bad_set(bad),'bad_tmp.pkl')
    env={**os.environ,'BAD':'bad_tmp.pkl','NAME':name,**{k:str(v) for k,v in kw.items()}}
    o=subprocess.run(['python3','runall.py'],env=env,capture_output=True,text=True); print(o.stdout.strip() or o.stderr[-400:],flush=True)
run('現行',q<0,PILOT=1)
for n in (40,50,60):
    b=q<q.rolling(n).mean()
    for p in (0.5,0.33): run(f'{n}日線の下は初回{int(p*100)}%・買い増し通常',b,PILOT=p)
    run(f'{n}日線の下は初回50%・買い増しも50%',b,PILOT=0.5,FULLADDS=0)
    for s in (0.05,0.06): run(f'{n}日線の下は損切り−{int(s*100)}%',b,PILOT=1,STOPBAD=s)
