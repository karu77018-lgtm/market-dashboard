"""本命が買われなかった理由の内訳（今のルール、2015-01〜2026-11-12）。
結果: 買った278 / すでに保有中835 / QQQが200日線の下で新規停止151 / 満杯・上限・データ157。
見送りの記録では 満杯35件(22日)、株80%上限124件(90日)。枠を増やしても効かない理由。"""
import sys, collections, pandas as pd
sys.path.insert(0, '.'); import prod3 as P   # SIG=s_base.pkl
sig = pd.read_pickle('s_base.pkl'); sig = sig[(sig.date >= '2015-01-01') & (sig.date <= '2026-11-12')]
pf = P.run(P.days.index('2015-01-02'), P.days.index('2026-11-13'))
print(collections.Counter(s['why'] for s in pf['skipped']).most_common(6))
held = [(c['t'], c['signal'], c['exit_day']) for c in pf['closed']] + [(t, p['signal'], '2099') for t, p in pf['positions'].items()]
cl = pd.DataFrame(held, columns=['t', 'sig', 'exit']); cnt = collections.Counter()
for d, t in zip(sig.date, sig.ticker):
    ds = d.strftime('%Y-%m-%d'); z = cl[cl.t == t]
    if not P.reg.loc[d]: cnt['新規停止'] += 1
    elif (z.sig == ds).any(): cnt['買った'] += 1
    elif ((z.sig < ds) & (z.exit > ds)).any(): cnt['すでに保有中'] += 1
    else: cnt['満杯・上限・データ'] += 1
print(dict(cnt))
