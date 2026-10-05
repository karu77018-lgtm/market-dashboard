import numpy as np, pandas as pd
exec(open('rsline3.py').read().split("for name, m in")[0])
core = f63 & TT & ~sel & (r189 >= 80)
for lo, hi in ((.03, .05), (.05, .08), (.02, .08), (.03, .10)):
    evaluate(core & (off > lo) & (off <= hi), f'最終形 高値-{lo:.0%}〜{hi:.0%}')
evaluate(core & (off > .03) & (off <= .08) & (r189 >= 90), '最終形×RS189上位10%')
evaluate(f63 & TT & (r189 >= 80) & (off > .03) & (off <= .08) & sel, '参考：本体の中')
M = (core & (off > .03) & (off <= .08) & elig)
last = M.iloc[-25:]
print({str(d.date()): list(r[r].index) for d, r in last.iterrows() if r.any()})
