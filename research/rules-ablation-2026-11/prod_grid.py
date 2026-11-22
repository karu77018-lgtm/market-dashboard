import pandas as pd, numpy as np
from prod_sim import simulate, stats
c = pd.read_pickle('prod_cands.pkl')
E = pd.read_pickle('eps_labels.pkl')
c['eps'] = [E.at[d, t] if (t in E.columns and d in E.index) else 'NO_DATA' for d, t in zip(c.date, c.ticker)]
b = c[c.buyable]
V = {
 '基準（本命＝現行ルール）': b,
 '−週足SAR/HL寄り（全条件OKを全部）': c,
 '−HL寄り除外のみ外す': c[c.sar_up == True],
 '+52週高値-3%以内': b[b.hi_dist >= -0.03],
 '+52週高値-5%以内': b[b.hi_dist >= -0.05],
 '+52週高値-7%以内': b[b.hi_dist >= -0.07],
 '+52週高値-10%以内': b[b.hi_dist >= -0.10],
 '+52週高値-15%以内': b[b.hi_dist >= -0.15],
 '+50MA乖離+25%以内': b[b.ext50 <= 0.25],
 '+52週-5%＋50MA乖離25%': b[(b.hi_dist >= -0.05) & (b.ext50 <= 0.25)],
 '+RS189≥95': b[b.rs189 >= 95],
 '+売買代金上位2%': b[b.dv >= 98],
 '+RS63≥80': b[b.rs63 >= 80],
 '+EPS 加速確定を除外': b[~b.eps.isin(['ACCEL_CONFIRMED', 'ACCEL_PERSISTENT'])],
 '+EPS 減速・減益を除外': b[~b.eps.isin(['DECEL_ONE_Q', 'DECEL_CONFIRMED', 'CONTRACTION'])],
}
rows = []
for k, sig in V.items():
    s, tr = simulate(sig, end=pd.Timestamp('2026-10-28'))
    s2, _ = simulate(sig)
    r = stats(s, tr); r['本命数'] = len(sig); r['〜11/5 CAGR'] = stats(s2)['CAGR']
    rows.append(pd.Series(r, name=k))
t = pd.DataFrame(rows)
pd.set_option('display.width', 250)
print(t[['本命数', '件数', 'CAGR', 'DD', '15-20', '21-26', '2022', '負年', 'PF', '〜11/5 CAGR']].round(1).to_string())
t.to_csv('prod_grid.csv')
