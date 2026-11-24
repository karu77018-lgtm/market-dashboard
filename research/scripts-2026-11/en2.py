import os, subprocess, pandas as pd, numpy as np
S=pd.read_pickle('en1.pkl'); sig=pd.read_pickle('honmei.pkl')
K=sig.merge(S[['date','ticker','sqz_fired','ud']],on=['date','ticker'],how='left')
cols=['date','ticker','rs189']
def run(name,df):
    df[cols].to_pickle('sig_tmp.pkl')
    o=subprocess.run(['python3','runeng3.py'],env={**os.environ,'SIG':'sig_tmp.pkl','NAME':name},capture_output=True,text=True)
    print(o.stdout.strip() or o.stderr[-400:],flush=True)
F=[('スクイーズ解放5日内を見送る',~K.sqz_fired.fillna(False).astype(bool)),
   ('UD比≥1.5を見送る',~(K.ud>=1.5)),('UD比≥1.3を見送る',~(K.ud>=1.3)),('UD比≥1.8を見送る',~(K.ud>=1.8)),
   ('両方',~K.sqz_fired.fillna(False).astype(bool)&~(K.ud>=1.5))]
for name,m in F:
    run(f'{name} 残{m.mean()*100:.0f}%',K[m])
    res=[]
    for s in range(8):
        r=np.random.default_rng(100+s).random(len(K))<m.mean()
        K[r][cols].to_pickle('sig_tmp.pkl')
        o=subprocess.run(['python3','runeng3.py'],env={**os.environ,'SIG':'sig_tmp.pkl','NAME':'r'},capture_output=True,text=True).stdout
        res.append([float(x.split('%')[0]) for x in o.split('2015-26')[1:2]+o.split('2015-20')[1:2]+o.split('2021-26')[1:2]])
    a=np.array(res); print(f'   ランダム8回: 全期間 {a[:,0].min():.1f}〜{a[:,0].max():.1f} (平均{a[:,0].mean():.1f}) | 2015-20 {a[:,1].min():.1f}〜{a[:,1].max():.1f} | 2021-26 {a[:,2].min():.1f}〜{a[:,2].max():.1f}',flush=True)
K2=K.copy(); K2['rs189']=-K2.ud.fillna(9); run('UD比が低い順に優先',K2)
