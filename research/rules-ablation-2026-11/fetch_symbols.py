"""US common-stock symbols from the nasdaqtrader directory -> symbols.json, fetch_list.json (QQQ first)."""
import csv, json, re
from curl_cffi import requests as cr
for name in ('nasdaqlisted.txt', 'otherlisted.txt'):
    r = cr.get(f'https://www.nasdaqtrader.com/dynamic/SymDir/{name}', impersonate='chrome', timeout=30)
    open(name, 'w').write(r.text)
syms = set()
def rd(fn, symcol):
    for r in csv.DictReader(open(fn), delimiter='|'):
        s = r.get(symcol) or ''
        if not s or s.startswith('File Creation') or r.get('ETF') == 'Y' or r.get('Test Issue') == 'Y':
            continue
        n = (r.get('Security Name') or '').lower()
        if re.search(r'warrant|\bunits?\b|\bright|preferred|depositary shares? repr|notes due|debenture|% ', n):
            continue
        if re.search(r'[\$\.\^=]', s):
            continue
        syms.add(s)
rd('nasdaqlisted.txt', 'Symbol'); rd('otherlisted.txt', 'ACT Symbol')
syms = sorted(syms)
json.dump(syms, open('symbols.json', 'w')); json.dump(['QQQ'] + syms, open('fetch_list.json', 'w'))
print(len(syms))
