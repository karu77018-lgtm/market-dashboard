"""Outside-the-selection signal sets by EPS state (run after eps_state.py on out_universe.pkl)."""
import numpy as np, pandas as pd
U = pd.read_pickle('out_universe.pkl'); L = pd.read_pickle('eps_labels_out.pkl').fillna('NO_DATA')
det = pd.read_csv('eps_detail_out.csv', parse_dates=['day'])
ann = pd.DataFrame(False, index=U.index, columns=U.columns)
for t, g in det.groupby('ticker'):
    if t not in ann.columns: continue
    idx = U.index.searchsorted(g.day.values, side='right'); idx = idx[idx < len(U.index)]
    ann.iloc[idx, ann.columns.get_loc(t)] = True
pos = pd.DataFrame(np.arange(len(U.index))[:, None].repeat(U.shape[1], 1), index=U.index, columns=U.columns)
since = pos - pos.where(ann).ffill()  # sessions since the first session after the last announcement
isin = lambda xs: L.isin(xs).to_numpy()
A = ['ACCEL_CONFIRMED', 'ACCEL_PERSISTENT']
G = {
    '選定外 全体': U,
    '選定外×A 加速確定': U & isin(A),
    '選定外×A 加速確定・決算後20日以内': U & isin(A) & (since <= 20).to_numpy(),
    '選定外×B 加速系すべて': U & isin(A + ['ACCEL_ONE_Q', 'IMPROVING_3Q', 'ACCEL_CONFIRMED_LOWBASE', 'ACCEL_PERSISTENT_LOWBASE']),
    '選定外×D 減速・減益': U & isin(['DECEL_ONE_Q', 'DECEL_CONFIRMED', 'CONTRACTION']),
    '選定外×E 赤字・比較不能': U & isin(['LOSS', 'TURNAROUND', 'NON_COMPARABLE']),
    '選定外×加速確定以外': U & ~isin(A),
}
pd.to_pickle(G, 'sig_out.pkl')
