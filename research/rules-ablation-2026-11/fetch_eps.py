"""Quarterly Reported EPS history (Yahoo, via yfinance get_earnings_dates) for tickers ever in the selection."""
import json, os, sys, time, concurrent.futures as cf
import yfinance as yf
os.makedirs('eps', exist_ok=True)
tick = json.load(open(sys.argv[1]))
def one(t):
    p = f'eps/{t}.csv'
    if os.path.exists(p): return t, 'cached'
    for a in range(4):
        try:
            d = yf.Ticker(t).get_earnings_dates(limit=100)
            if d is None or d.empty: open(p, 'w').write('date,eps\n'); return t, 'empty'
            d = d[['Reported EPS']].dropna().sort_index()
            with open(p, 'w') as f:
                f.write('date,eps\n')
                for ts, v in d['Reported EPS'].items():
                    f.write(f"{ts.isoformat()},{v}\n")
            return t, 'ok'
        except Exception as e:
            time.sleep(5 * (a + 1))
    return t, 'fail'
stat = {}
with cf.ThreadPoolExecutor(4) as ex:
    for i, (t, s) in enumerate(ex.map(one, tick)):
        stat[s] = stat.get(s, 0) + 1
        if i % 200 == 0: print(i, stat, flush=True)
print('done', stat, flush=True)
