"""Build wide panels (float32) for all current listings + QQQ. Saved as .npz-like pickles."""
import json, os, numpy as np, pandas as pd
m = json.load(open('meta.json'))
tick = sorted(k for k, v in m.items() if v.get('first') and v.get('type') == 'EQUITY' and os.path.exists(f'bars/{k}.csv'))
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date')
cal = q.index
fields = {k: {} for k in ('open', 'high', 'low', 'close', 'volume')}
for t in tick:
    f = pd.read_csv(f'bars/{t}.csv', parse_dates=['date']).drop_duplicates('date').set_index('date')
    f = f[(f.close > 0) & (f.high >= f.low)]
    for k in fields:
        fields[k][t] = f[k].astype('float32')
for k, d in fields.items():
    w = pd.DataFrame(d).reindex(cal).astype('float32')
    w.to_pickle(f'w_{k}.pkl')
    print(k, w.shape, flush=True)
