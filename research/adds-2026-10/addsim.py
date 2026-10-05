"""6-slot portfolio on the rule-selection proxy with different add schemes (research, local)."""
import numpy as np, pandas as pd, sys
C = pd.read_pickle('w_close.pkl').loc['2015-01-01':]; O = pd.read_pickle('w_open.pkl').loc['2015-01-01':]
Lw = pd.read_pickle('w_low.pkl'); EL = Lw.ewm(span=21, adjust=False).mean().loc['2015-01-01':]; L = Lw.loc['2015-01-01':]
SEL = pd.read_pickle('setups_sel.pkl')['選定そのもの（全日）']
r189 = pd.read_pickle('ranks.pkl')['rs189'].loc['2015-01-01':]
q = pd.read_csv('bars/QQQ.csv', parse_dates=['date']).set_index('date').close.reindex(C.index)
cols = list(C.columns); dates = C.index
Cn, On, Ln, En, Sn, Rn = (x.to_numpy() for x in (C, O, L, EL, SEL, r189))
def run(add_size=1.0, cap=0.40, be_after=None, qpct=0.5):
    cash, qsh, pos, eq, worst = 1.0, 0.0, {}, [], 0.0
    for i, d in enumerate(dates):
        qc = q.iloc[i]
        val = lambda: cash + qsh * qc + sum(p['sh'] * (Cn[i, j] if not np.isnan(Cn[i, j]) else p['last']) for j, p in pos.items())
        for j in list(pos):
            p = pos[j]; o, l, c, e = On[i, j], Ln[i, j], Cn[i, j], En[i, j]
            if np.isnan(c): continue
            px = o if o <= p['stop'] else p['stop'] if l <= p['stop'] else c if c < e else None
            if px is not None:
                pnl = p['sh'] * px - p['inv']; worst = min(worst, pnl / p['eq0'])
                cash += p['sh'] * px; del pos[j]; continue
            p['last'] = c
            for n, lv in enumerate((0.10, 0.20)):
                if n not in p['trig'] and c / p['entry'] - 1 >= lv - 1e-9:
                    p['trig'].append(n)
                    if add_size > 0:
                        equity = val(); room = cap * equity - p['sh'] * c
                        amt = min(p['unit'] * add_size, max(0.0, room), cash + qsh * qc)
                        if amt > 0:
                            take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
                            p['sh'] += amt / c; p['inv'] += amt
                    if be_after is not None and n == be_after:
                        p['stop'] = max(p['stop'], p['inv'] / p['sh'])   # whole position at its average cost
        cand = [j for j in np.where(Sn[i])[0] if j not in pos]
        cand.sort(key=lambda j: -Rn[i, j])
        for j in cand:
            if len(pos) >= 6: break
            c = Cn[i, j]; equity = val(); unit = equity / 6; amt = min(unit, cash + qsh * qc)
            if amt <= 0: break
            take = min(cash, amt); cash -= take; qsh -= (amt - take) / qc
            pos[j] = dict(entry=c, stop=c * 0.92, sh=amt / c, inv=amt, unit=unit, trig=[], last=c, eq0=equity)
        idle = cash + qsh * qc; qsh = idle * qpct / qc; cash = idle - qsh * qc
        eq.append(val())
    e = pd.Series(eq, index=dates); yrs = (dates[-1] - dates[0]).days / 365.25
    cagr = e.iloc[-1] ** (1 / yrs) - 1; dd = (e / e.cummax() - 1).min()
    run.last = e
    return cagr, dd, worst
if __name__ == "__main__":
  for label, kw in [('買い増しなし', dict(add_size=0)), ('今のルール（同額×2・上限40%）', {}),
                  ('半額×2', dict(add_size=0.5)), ('同額×1回だけ（+10%のみ）', dict(add_size=1.0, cap=0.40)),
                  ('同額×2・上限25%', dict(cap=0.25)), ('同額×2・2回目の後は平均取得単価で逆指値', dict(be_after=1))]:
    if label.startswith('同額×1回'):
        import types
    r = run(**kw) if not label.startswith('同額×1回') else None
    if r: print(f'{label}: 年率 {r[0]:.1%} 最大DD {r[1]:.1%} 1銘柄の最大損失 {r[2]:.1%}', flush=True)

if __name__ == '__main__' and len(sys.argv) > 1:
    pass
