import numpy as np, pandas as pd
src = open('rsline_study.py').read().split('\nlead = first')[0]
src = src.replace("    print(f\"{name:34s}", "    evaluate.last = T\n    print(f\"{name:34s}")
exec(src)
pf = lambda s: s[s > 0].sum() / -s[s < 0].sum() if (s < 0).any() else np.nan
def yearly(T):
    g = T.groupby(T.d.dt.year)['radd']
    return ' '.join(f"{y%100:02d}:{pf(s):.1f}({len(s)})" for y, s in g)
base = evaluate(TT, 'TT（比較）'); print('   ', yearly(base))
m = first & (off > .03) & (off <= .08) & TT
T = evaluate(m, 'RSL先行×TT×高値-3〜8%'); print('   ', yearly(T))
for w in (63, 126):
    nh = RSL >= RSL.rolling(w, min_periods=w).max()
    f = nh & ~nh.shift(1, fill_value=False).rolling(20, min_periods=1).max().astype(bool)
    T = evaluate(f & (off > .03) & (off <= .08) & TT, f'RSL {w}日新高値×TT×高値-3〜8%'); print('   ', yearly(T))
for lo, hi in ((.02, .06), (.03, .10), (.05, .10)):
    evaluate(first & (off > lo) & (off <= hi) & TT, f'RSL先行×TT×高値-{lo:.0%}〜{hi:.0%}')
# does it beat the matched baseline: TT and price 3-8% below high, any day (flat)
evaluate(TT & (off > .03) & (off <= .08), 'TT×高値-3〜8%（RSL条件なし）')
