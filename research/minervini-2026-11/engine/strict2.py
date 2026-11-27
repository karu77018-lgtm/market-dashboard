import os, subprocess, pandas as pd, numpy as np, re
sig=pd.read_pickle('sig_feat.pkl'); cols=['date','ticker','rs189']
def run(name,m,quiet=False):
    sig[m][cols].to_pickle('sig_tmp.pkl')
    o=subprocess.run(['python3','runall.py'],env={**os.environ,'SIG':'sig_tmp.pkl','NAME':name},capture_output=True,text=True).stdout.strip()
    if not quiet: print(o,flush=True)
    return [float(x) for x in re.findall(r'(-?\d+\.\d)%',o)]
keep=(sig.above_low>=1.0).mean()
rs=np.random.RandomState(7); R=[]
for k in range(20):
    m=rs.rand(len(sig))<keep; R.append(run(f'random{k}',m,quiet=True))
R=np.array(R)
print(f'ランダムに{(1-keep)*100:.0f}%除外 x20: 全 {R[:,0].min():.1f}〜{R[:,0].max():.1f}% (中央{np.median(R[:,0]):.1f}) | 15-20 {R[:,1].min():.1f}〜{R[:,1].max():.1f} | 21-26 {R[:,2].min():.1f}〜{R[:,2].max():.1f} | DD {R[:,3].min():.1f}〜{R[:,3].max():.1f}')
# 同じ件数を「安値からの上昇率が低い順」でなく、RS189の低い順に落とした場合（単にRSの強さの代わりでないか）
th=sig.rs189.quantile(1-keep); run('RS189上位だけ(同じ件数)',sig.rs189>=th)
