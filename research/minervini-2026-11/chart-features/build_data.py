import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
from features import features, K
px = pd.read_pickle('px.pkl')
R = json.load(open('results.json')); M = json.load(open('market_results.json'))
code = {f: open(f).read() for f in ['features.py', 'evaluate.py', 'market.py', 'build_data.py']}
inp = {'label': 'Input', 'value': 'Yahoo Finance日足(2015-01〜2026-11-25, 配当分割調整) / 対象: MC57 chart-dataで直近50日平均売買代金≥$30M・株価≥$10の1,500銘柄 / FRED WALCL・WTREGEN・RRPONTSYD'}
def meta(*fs): return [{'label': f, 'value': code[f], 'type': 'code', 'lang': 'python'} for f in fs] + [inp]
def r2(x, d=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)
def dump(name, rows, m):
    json.dump({'rows': rows, 'meta': m}, open(f'out/{name}.json', 'w'), ensure_ascii=False)
import os; os.makedirs('out', exist_ok=True)

GROUP = {'struct': '市場構造', 'dist_res': 'S/R', 'res_near': 'S/R', 'overhead': 'ボリュームプロファイル', 'thin_up': 'ボリュームプロファイル',
         'pos_poc': 'ボリュームプロファイル', 'd_avwap_hi': 'AVWAP', 'd_avwap_lo': 'AVWAP', 'ud50': '需給', 'dist25': '需給', 'acc25': '需給',
         'clv20': '需給', 'range_ratio': 'タイミング', 'vol_dry': 'タイミング', 'atr_ratio': 'タイミング', 'ldv50': '流動性', 'amihud': '流動性'}
rows = []
for k, v in R['cont'].items():
    sub, key = k.split('|')
    rows.append({'id': f'{sub}-{key}', 'subset': '全銘柄' if sub == 'ALL' else 'トレンドテンプレ通過', 'group': GROUP[key], 'feature': v['name'],
                 'ic': r2(v['ic'], 3), 't': r2(v['t'], 1), 'ic_16_20': r2(v['icA'], 3), 'ic_21_26': r2(v['icB'], 3),
                 'q1': v['q'][0], 'q5': v['q'][-1], 'spread_q5_q1': r2(v['spread']), 'mae_q1': r2(v['maeQ1'], 1), 'mae_q5': r2(v['maeQ5'], 1)})
dump('stock_cont', rows, meta('features.py', 'evaluate.py'))

EGROUP = {'brk20': '基準', 'bos_up': '市場構造', 'choch_up': '市場構造', 'bos_dn': '市場構造', 'sr3': 'S/R', 'sr1': 'S/R', 'pocket': '需給',
          'tight_bo': 'タイミング', 'loose_bo': 'タイミング', 'avwap_reclaim': 'AVWAP', 'brk_lowOH': 'ボリュームプロファイル',
          'brk_highOH': 'ボリュームプロファイル', 'brk_ud_hi': '需給', 'brk_ud_lo': '需給', 'brk_clv_hi': '需給', 'brk_dist_hi': '需給'}
rows = []
for k, v in R['event'].items():
    sub, key = k.split('|')
    rows.append({'id': f'{sub}-{key}', 'subset': '全銘柄' if sub == 'ALL' else 'トレンドテンプレ通過', 'group': EGROUP[key], 'event': v['name'],
                 'n': int(v['n']), 'x20': r2(v['x20']), 'base_x20': r2(v['base_x20']), 'diff_x20': r2(v['x20'] - v['base_x20']),
                 'win': r2(v['win'], 1), 'base_win': r2(v['base_win'], 1), 'mae': r2(v['mae'], 1), 'base_mae': r2(v['base_mae'], 1),
                 'x20_16_20': r2(v['xA']), 'x20_21_26': r2(v['xB']), 'x60': r2(v['x60'])})
dump('stock_events', rows, meta('features.py', 'evaluate.py'))

MNAME = {'nl_chg13': 'FRB純流動性 13週変化', 'q_dist25': 'QQQディストリビューション日数(25日)', 'struct_net': '構造ブレッドス(上昇構造%−下降構造%)',
         'tt': 'トレンドテンプレ通過率', 'ud': 'UD比>1の銘柄比率', 'lowoh': '上値しこり<10%の銘柄比率', 'brk_net10': '高値ブレイク−安値割れ(10日平均)', 'q_struct': 'QQQの構造'}
rows = []
for k, lst in M.items():
    for r in lst:
        b = str(r.get(k, r.get(list(r.keys())[0])))
        if k == 'q_struct': b = '上昇構造' if b.startswith('1') else '下降構造'
        rows.append({'id': f'{k}-{b}', 'indicator': MNAME[k], 'key': k, 'bucket': b, 'n': int(r['n']), 'qqq_20d': r['q20'], 'qqq_60d': r['q60'],
                     'win_60d': r['win60'], 'dd_60d': r['dd60']})
dump('market', rows, meta('features.py', 'market.py'))

m = pd.read_pickle('market_series.pkl')
last = m.iloc[-1]
def qlab(col):
    e = pd.qcut(m[col].dropna(), 5, retbins=True)[1]
    return ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'][int(np.clip(np.searchsorted(e, last[col]) - 1, 0, 4))]
d25 = last.q_dist25
cur = [{'key': 'nl_chg13', 'indicator': MNAME['nl_chg13'], 'value': r2(last.nl_chg13 * 100), 'unit': '%', 'bucket': qlab('nl_chg13')},
       {'key': 'q_dist25', 'indicator': MNAME['q_dist25'], 'value': float(d25), 'unit': '日',
        'bucket': '0-2' if d25 <= 2 else '3-4' if d25 <= 4 else '5-6' if d25 <= 6 else '7+'},
       {'key': 'struct_net', 'indicator': MNAME['struct_net'], 'value': r2(last.struct_net * 100, 1), 'unit': 'pt', 'bucket': qlab('struct_net')},
       {'key': 'tt', 'indicator': MNAME['tt'], 'value': r2(last.tt * 100, 1), 'unit': '%', 'bucket': qlab('tt')}]
for c in cur: c['as_of'] = str(m.index[-1].date())
dump('market_now', cur, meta('market.py', 'build_data.py'))

# ---------- 銘柄チャート例 ----------
TK = ['QQQ', 'NVDA', 'AAPL', 'LLY', 'MRNA', 'ABNB']
bars, levels, now = [], [], []
for t in TK:
    df = px[t][['Open', 'High', 'Low', 'Close', 'Volume']]
    f = features(df)
    o, h, l, c, v = (df[x].to_numpy() for x in ['Open', 'High', 'Low', 'Close', 'Volume'])
    n = len(c); N = 250; s0 = n - N
    tp = (h + l + c) / 3
    i_hi = s0 + int(np.argmax(h[s0:])); i_lo = s0 + int(np.argmin(l[s0:]))  # 表示区間の高値・安値（=52週）起点
    cpv, cv = np.cumsum(tp * v), np.cumsum(v)
    def avw(a, i): return (cpv[i] - (cpv[a - 1] if a else 0)) / (cv[i] - (cv[a - 1] if a else 0)) if i >= a else None
    piv_h, piv_l = [], []
    for j in range(K, n - K):
        if h[j] == h[j - K:j + K + 1].max(): piv_h.append(j)
        if l[j] == l[j - K:j + K + 1].min(): piv_l.append(j)
    sh, sl = set(piv_h), set(piv_l)
    # HH/HL ラベル
    lab = {}
    for arr, src, a, b in ((piv_h, h, 'HH', 'LH'), (piv_l, l, 'HL', 'LL')):
        for p, q in zip(arr[:-1], arr[1:]): lab[q] = a if src[q] > src[p] else b
    for i in range(s0, n):
        ev = []
        if f.bos_up.iloc[i]: ev.append('構造ブレイク')
        if f.bos_dn.iloc[i]: ev.append('安値割れ')
        if f.pocket.iloc[i]: ev.append('ポケットピボット')
        if f.tight_bo.iloc[i]: ev.append('VCP型ブレイク')
        bars.append({'key': f'{t}|{df.index[i].date()}', 'tk': t, 'date': str(df.index[i].date()), 'o': r2(o[i]), 'h': r2(h[i]), 'l': r2(l[i]), 'c': r2(c[i]),
                     'v': int(v[i]), 'avwap_hi': r2(avw(i_hi, i)), 'avwap_lo': r2(avw(i_lo, i)),
                     'pivot': 'H' if i in sh else ('L' if i in sl else None), 'pivot_label': lab.get(i), 'event': '・'.join(ev) or None})
    # S/R ゾーン（直近250日の確定ピボットを0.5ATRでクラスタ）
    atr = float(np.nanmean(np.maximum(h[-14:] - l[-14:], 0)))
    pts = sorted([h[j] for j in piv_h if j >= s0 and j <= n - 1 - K] + [l[j] for j in piv_l if j >= s0 and j <= n - 1 - K])
    zones = []
    for p in pts:
        if zones and p - zones[-1][-1] <= 0.5 * atr: zones[-1].append(p)
        else: zones.append([p])
    for z in zones:
        if len(z) >= 2:
            levels.append({'key': f'{t}|sr|{z[0]:.2f}', 'tk': t, 'kind': 'S/Rゾーン', 'lo': r2(min(z)), 'hi': r2(max(z)), 'value': len(z), 'tag': None})
    # ボリュームプロファイル（252日・40区分、各バーの出来高を値幅に均等配分）
    W = 252; ss = slice(n - W, n)
    lo_, hi_ = l[ss].min(), h[ss].max(); edges = np.linspace(lo_, hi_, 41); prof = np.zeros(40)
    for hh, ll, vv in zip(h[ss], l[ss], v[ss]):
        rng = max(hh - ll, 1e-9)
        ov = np.clip(np.minimum(edges[1:], hh) - np.maximum(edges[:-1], ll), 0, None)
        prof += vv * ov / rng if hh > ll else vv * ((edges[:-1] <= hh) & (edges[1:] > hh))
    prof /= prof.sum()
    k = int(prof.argmax()); order = np.argsort(prof)[::-1]
    va = order[:np.searchsorted(np.cumsum(prof[order]), 0.7) + 1]
    for b in range(40):
        tag = 'POC' if b == k else ('VA' if b in va else None)
        levels.append({'key': f'{t}|vp|{b}', 'tk': t, 'kind': '出来高分布', 'lo': r2(edges[b]), 'hi': r2(edges[b + 1]), 'value': r2(prof[b] * 100, 3), 'tag': tag})
    x = f.iloc[-1]
    now.append({'tk': t, 'as_of': str(df.index[-1].date()), 'struct': {1: '上昇(HH/HL)', -1: '下降(LH/LL)', 0: '混在'}[int(x.struct)],
                'overhead_pct': r2(x.overhead * 100, 1), 'dist_res_atr': r2(x.dist_res, 1), 'ud50': r2(x.ud50), 'dist25': int(x.dist25),
                'range_ratio': r2(x.range_ratio), 'vol_dry': r2(x.vol_dry), 'avwap_hi_pct': r2(x.d_avwap_hi * 100, 1), 'tt': '通過' if x.tt else '—'})
dump('example_bars', bars, meta('features.py', 'build_data.py'))
dump('example_levels', levels, meta('build_data.py'))
dump('example_now', now, meta('features.py', 'build_data.py'))
for fn in os.listdir('out'): print(fn, os.path.getsize('out/' + fn))
print(now)
