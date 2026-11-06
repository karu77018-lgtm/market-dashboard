"""Yahoo daily bars 2013-, same as MC57 research/setups-2026-10/fetch_bars.py, plus meta."""
import json, sys, time, threading, os, concurrent.futures as cf
from curl_cffi import requests as cr
tickers = json.load(open(sys.argv[1]))
P1 = int(time.mktime(time.strptime('2013-01-01', '%Y-%m-%d')))
P2 = int(time.time())
local = threading.local()
os.makedirs('bars', exist_ok=True); os.makedirs('meta', exist_ok=True)
def sess():
    if not hasattr(local, 's'): local.s = cr.Session(impersonate="chrome")
    return local.s
def one(sym):
    path = f'bars/{sym}.csv'
    if os.path.exists(path) or os.path.exists(f'meta/{sym}.err'): return sym, 'cached'
    for attempt in range(6):
        try:
            r = sess().get(f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}',
                           params={'period1': P1, 'period2': P2, 'interval': '1d', 'events': 'split'}, timeout=30)
            if r.status_code == 429: time.sleep(10 * (attempt + 1)); continue
            if r.status_code == 404: open(f'meta/{sym}.err', 'w').write('404'); return sym, 'err'
            j = r.json()['chart']
            if j.get('error') or not j.get('result'): open(f'meta/{sym}.err', 'w').write('err'); return sym, 'err'
            res = j['result'][0]; ts = res.get('timestamp') or []
            m = res.get('meta', {})
            json.dump({'type': m.get('instrumentType'), 'first': m.get('firstTradeDate')}, open(f'meta/{sym}.json', 'w'))
            q = res['indicators']['quote'][0]
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                f.write('date,open,high,low,close,volume\n')
                for i, t in enumerate(ts):
                    vals = [q[k][i] for k in ('open', 'high', 'low', 'close', 'volume')]
                    if None in vals: continue
                    d = time.strftime('%Y-%m-%d', time.gmtime(t - 4 * 3600))
                    f.write(d + ',' + ','.join(f'{v:.6g}' if k != 4 else str(int(v)) for k, v in enumerate(vals)) + '\n')
            os.replace(tmp, path)
            return sym, 'ok'
        except Exception:
            time.sleep(3 * (attempt + 1))
    return sym, 'retry'
t0 = time.time(); stat = {}
with cf.ThreadPoolExecutor(int(sys.argv[2]) if len(sys.argv) > 2 else 3) as ex:
    for i, (s, st) in enumerate(ex.map(one, tickers)):
        stat[st] = stat.get(st, 0) + 1
        if i % 300 == 0: print(i, stat, round(time.time() - t0), flush=True)
print('done', stat, round(time.time() - t0), flush=True)
