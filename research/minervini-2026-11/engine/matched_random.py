"""同じ日に同じ件数だけランダムに本命を残す（株を持つ時期を+100%条件と揃えた比較）。20通り。
結果: 72.4〜78.4%（中央75.6）、2015-20 中央<=67.3、2021-26 <=95.0。+100%条件は80.3 / 67.6 / 96.0。"""
import os, subprocess, re, pandas as pd, numpy as np
sig = pd.read_pickle('sig_feat.pkl').reset_index(drop=True); cols = ['date', 'ticker', 'rs189']
hi = (sig.above_low >= 1).to_numpy()


def run(m):
    sig[m][cols].to_pickle('sig_tmp.pkl')
    o = subprocess.run(['python3', 'runall.py'], env={**os.environ, 'SIG': 'sig_tmp.pkl', 'NAME': 'x'},
                       capture_output=True, text=True).stdout
    return [float(x) for x in re.findall(r'(-?\d+\.\d)%', o)]


rs = np.random.RandomState(3); R = []
grp = sig.groupby('date').indices
for k in range(20):
    m = np.zeros(len(sig), bool)
    for d, ix in grp.items():
        nkeep = hi[ix].sum()
        if nkeep: m[rs.choice(ix, nkeep, replace=False)] = True
    R.append(run(m))
R = np.array(R)
print(f'同じ日に同じ件数だけランダムに残す x20: 全 {R[:,0].min():.1f}〜{R[:,0].max():.1f}% (中央{np.median(R[:,0]):.1f}) | '
      f'15-20 {R[:,1].min():.1f}〜{R[:,1].max():.1f} | 21-26 {R[:,2].min():.1f}〜{R[:,2].max():.1f}')
print('+100%条件', run(hi)[:3])
