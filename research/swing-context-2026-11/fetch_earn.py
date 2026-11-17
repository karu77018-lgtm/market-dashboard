import pandas as pd, json, time, yfinance as yf
sig=pd.read_pickle('honmei.pkl'); out={}
for i,t in enumerate(sorted(sig.ticker.unique())):
    for k in range(3):
        try:
            d=yf.Ticker(t).get_earnings_dates(limit=100)
            out[t]=sorted({str(x.date()) for x in d.index}) if d is not None else []
            break
        except Exception as e:
            time.sleep(2+k); out[t]=[]
    time.sleep(0.5)
json.dump(out,open('earnings.json','w')); print('done',sum(1 for v in out.values() if v),len(out))
