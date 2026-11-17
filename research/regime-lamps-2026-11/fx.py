"""F1/F2/F3 over 2013-2026 on the local panel (the card's definitions via scripts/regime_history)."""
import sys, pandas as pd
sys.path.insert(0,'/home/claude/md/scripts'); import regime_history as rh
W={k:pd.read_pickle(f+'.pkl').astype('float64') for k,f in (('Close','close'),('High','high'),('Volume','volume'))}
F=rh.series(W).dropna(); F.to_pickle('fseries.pkl'); print(F.index[0].date(),F.index[-1].date(),len(F)); print(F.describe().round(3))
