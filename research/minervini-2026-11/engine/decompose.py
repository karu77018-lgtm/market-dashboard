"""+100%条件で消えた取引・残った取引・新しく入った取引、株とTQQQ枠の平均比率、株だけ（TQQQ枠0%）の成績。
結果: 買った 278→174件。消えた121件 平均+1.0%・勝率36% / 共通157件 平均+6.4%。
株の平均比率 27.4→18.6%、TQQQ枠 47.8→54.0%（ランダム除外は株24〜25%・枠49〜50%）。株だけは22.0%で同じ。"""
import os, sys, pandas as pd, numpy as np
sig = pd.read_pickle('sig_feat.pkl'); cols = ['date', 'ticker', 'rs189']


def go(m):
    sig[m][cols].to_pickle('s_x.pkl'); os.environ['SIG'] = 's_x.pkl'
    sys.modules.pop('prod3', None); sys.modules.pop('tp_x', None)
    import prod3 as P
    pf, Lg = P.run(P.days.index('2015-01-02'), P.days.index('2026-11-13'), log=True)
    e = Lg['eq']
    return pd.DataFrame(pf['closed']), (Lg.stock_v / e).mean(), (Lg.sleeve_v / e).mean(), e.iloc[-1] ** (1 / 11.87) - 1


hi = (sig.above_low >= 1).to_numpy()
b, bs, bq, bc = go(np.ones(len(sig), bool)); h, hs, hq, hc = go(hi)
rs = np.random.RandomState(7)
for k in range(5):
    _, s, q, c = go(rs.rand(len(sig)) < hi.mean()); print(f'ランダム除外 株{s*100:.1f}% 枠{q*100:.1f}% 年率{c*100:.1f}%')
print(f'今のルール 株{bs*100:.1f}% 枠{bq*100:.1f}% {bc*100:.1f}% | +100% 株{hs*100:.1f}% 枠{hq*100:.1f}% {hc*100:.1f}%')
kb, kh = set(zip(b.t, b.entry_day)), set(zip(h.t, h.entry_day))
for nm, d in (('消えた', b[[k not in kh for k in zip(b.t, b.entry_day)]]), ('共通', b[[k in kh for k in zip(b.t, b.entry_day)]]),
              ('新しく入った', h[[k not in kb for k in zip(h.t, h.entry_day)]])):
    print(f'{nm}: {len(d)}件 平均 {d.ret.mean()*100:+.1f}% 勝率 {(d.ret>0).mean()*100:.0f}%')

# 株だけ（TQQQ枠0%）：record-context-2026-11/sim.py の run を本命ファイルだけ差し替えて使う
src = open('sim.py').read().split("if __name__")[0]
for nm, m in (('今のルール', np.ones(len(sig), bool)), ('+100%条件', hi)):
    sig[m][cols].to_pickle('honmei_tmp.pkl')
    g = {}
    exec(src.replace("'honmei.pkl'", "'honmei_tmp.pkl'")
         .replace("good=hyst(hv)", "good=pd.read_pickle('health.pkl').good.to_numpy()"), g)
    e = g['run'](np.zeros(g['n'])); s = g['stats']
    print(f"{nm} 株だけ: 年率 {s(e)[0]*100:.1f}% DD {s(e)[1]*100:.1f}% | 2015-20 {s(e,'2015','2020')[0]*100:.1f}% | "
          f"2021-26 {s(e,'2021','2026')[0]*100:.1f}%")
