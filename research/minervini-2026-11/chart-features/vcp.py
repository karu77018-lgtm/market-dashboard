"""ミネルヴィニ型セットアップ（トレンド条件＋VCP＋ピボット突破）の売買シミュレーション。
シグナル判定は前日までの情報だけ。損切り＝2×ATR20（最大10%）。"""
import numpy as np, pandas as pd, warnings
from multiprocessing import Pool
warnings.filterwarnings('ignore')
K = 5          # スイング（ピボット）判定の左右本数
LOOK = 130     # ベースを探す期間（約6か月）


def roll(a, w, f):
    return getattr(pd.Series(a).rolling(w, min_periods=w), f)().to_numpy()


def sim_trade(o, h, l, c, ma50, t, entry, stop, mode):
    """t日にentryで建てた後の結果。mode: 'time60'=損切りor60日後の終値 / 'ma50'=損切りor終値50日線割れで翌寄り"""
    n = len(c)
    # 建てた日の安値で損切りに触れたら（保守的に）損切り扱い
    if l[t] <= stop:
        return stop / entry - 1, 0
    last = min(n - 1, t + (60 if mode == 'time60' else 252))
    for j in range(t + 1, last + 1):
        if o[j] <= stop: return o[j] / entry - 1, j - t          # 窓開けで損切り下抜け
        if l[j] <= stop: return stop / entry - 1, j - t
        if mode == 'ma50' and c[j] < ma50[j] and j + 1 < n:
            return o[j + 1] / entry - 1, j + 1 - t
    if last == n - 1 and last < t + (60 if mode == 'time60' else 252):
        return None, None                                         # 期間不足（未決済）
    return c[last] / entry - 1, last - t


def run(args):
    tk, df = args
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float).dropna()
    df = df[(df.Close > 0) & (df.High >= df.Low)]
    o, h, l, c, v = (df[x].to_numpy() for x in ['Open', 'High', 'Low', 'Close', 'Volume'])
    n = len(c)
    if n < 400: return []
    dates = df.index
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    atr20 = roll(tr, 20, 'mean')
    ma50, ma150, ma200 = roll(c, 50, 'mean'), roll(c, 150, 'mean'), roll(c, 200, 'mean')
    hi252, lo252 = roll(h, 252, 'max'), roll(l, 252, 'min')
    hi20 = roll(h, 20, 'max')
    v50 = roll(v, 50, 'mean')
    ret = c / pc - 1
    ud50 = roll(np.where(ret > 0, v, 0), 50, 'sum') / np.maximum(roll(np.where(ret < 0, v, 0), 50, 'sum'), 1)
    # 52週高値の更新：直近126日(約6か月)以内に、その時点の52週高値を更新した日があるか
    newhi = (h >= hi252).astype(float)
    newhi126 = roll(newhi, 126, 'max')
    ma200_up63 = (ma200 > np.r_[np.full(63, np.nan), ma200[:-63]]) & (ma200 > np.r_[np.full(21, np.nan), ma200[:-21]]) \
                 & (np.r_[np.full(21, np.nan), ma200[:-21]] > np.r_[np.full(42, np.nan), ma200[:-42]])
    ma200_up21 = ma200 > np.r_[np.full(21, np.nan), ma200[:-21]]
    # 文面どおりの条件
    text_tt = (c >= 0.75 * hi252) & ma200_up63 & (ma50 > ma200) & (c > ma200) & (c >= 2.0 * lo252) & (newhi126 > 0)
    # 原典のトレンドテンプレート（8条件、株価10ドル以上）
    orig_tt = (c > ma150) & (c > ma200) & (ma150 > ma200) & ma200_up21 & (ma50 > ma150) & (ma50 > ma200) & (c > ma50) \
              & (c >= 1.3 * lo252) & (c >= 0.75 * hi252) & (c >= 10)

    # 確定ピボット（j のピボットは j+K 日目に確定）
    ph = [j for j in range(K, n - K) if h[j] == h[j - K:j + K + 1].max()]
    pl = [j for j in range(K, n - K) if l[j] == l[j - K:j + K + 1].min()]
    out = []
    busy = {}  # 建玉中は同じルール・同じ銘柄で新規を取らない
    phi = 0
    for t in range(260, n):
        p = t - 1  # 前日までの情報で判定
        if not (text_tt[p] or orig_tt[p]): continue
        # 前日までに確定したピボット高値（直近LOOK日）
        highs = [j for j in ph if j + K <= p and j >= p - LOOK]
        if not highs: continue
        a = max(highs, key=lambda j: h[j])          # ベースの左端＝期間内の最高値
        hs = [j for j in highs if j >= a]
        # 各ピボット高値から次のピボット高値（最後は前日）までの押し＝収縮の深さ
        depths, vols = [], []
        for i, j in enumerate(hs):
            end = hs[i + 1] if i + 1 < len(hs) else p
            if end <= j: continue
            lo = l[j:end + 1].min()
            depths.append(1 - lo / h[j]); vols.append(v[j:end + 1].mean())
        if len(depths) < 2: continue
        last_hi = h[hs[-1]]
        if c[p] > last_hi: continue                  # すでに上抜け済みならベース中ではない
        dec = all(depths[i + 1] < depths[i] for i in range(len(depths) - 1))
        if not dec: continue
        trig_stop = h[t] > last_hi                   # 逆指値（ピボット上抜けで買い）
        trig_close = c[t] > last_hi                  # 終値で上抜け→翌日寄り
        if not (trig_stop or trig_close): continue
        ratios = [depths[i + 1] / depths[i] for i in range(len(depths) - 1)]
        feat = dict(tk=tk, date=dates[t], n_vcp=len(depths), d1=depths[0], dlast=depths[-1], max_ratio=max(ratios),
                    shrink2=depths[1] / depths[0], vol_dry=vols[-1] / vols[0], base_len=p - a,
                    text_tt=bool(text_tt[p]), orig_tt=bool(orig_tt[p]), price=c[p], ud50=ud50[p],
                    above_low=c[p] / lo252[p] - 1, rvol=v[t] / v50[p] if v50[p] > 0 else np.nan)
        for entry_mode in ('stop', 'nextopen'):
            if entry_mode == 'stop':
                if not trig_stop: continue
                te, entry = t, max(o[t], last_hi)
            else:
                if not trig_close or t + 1 >= n: continue
                te, entry = t + 1, o[t + 1]
            risk = min(2 * atr20[p], 0.10 * entry)
            stop = entry - risk
            for mode in ('time60', 'ma50'):
                key = (entry_mode, mode)
                if busy.get(key, -1) >= te: continue
                r, hold = sim_trade(o, h, l, c, ma50, te, entry, stop, mode)
                if r is None: continue
                busy[key] = te + hold
                out.append({**feat, 'entry_mode': entry_mode, 'exit': mode, 'ret': r, 'R': r / (risk / entry),
                            'risk_pct': risk / entry, 'hold': hold, 'kind': 'VCP'})
    # ---- 比較対象：同じトレンド条件で「普通の20日高値ブレイク」（VCP判定なし） ----
    busy = {}
    for t in range(260, n):
        p = t - 1
        if not (text_tt[p] or orig_tt[p]): continue
        lvl = hi20[p]
        if h[t] <= lvl or c[p] > lvl: continue
        entry = max(o[t], lvl); risk = min(2 * atr20[p], 0.10 * entry); stop = entry - risk
        for mode in ('time60', 'ma50'):
            key = mode
            if busy.get(key, -1) >= t: continue
            r, hold = sim_trade(o, h, l, c, ma50, t, entry, stop, mode)
            if r is None: continue
            busy[key] = t + hold
            out.append({'tk': tk, 'date': dates[t], 'text_tt': bool(text_tt[p]), 'orig_tt': bool(orig_tt[p]), 'price': c[p],
                        'ud50': ud50[p], 'entry_mode': 'stop', 'exit': mode, 'ret': r, 'R': r / (risk / entry),
                        'risk_pct': risk / entry, 'hold': hold, 'kind': 'BRK20'})
    # ---- 比較対象：同じトレンド条件の銘柄を毎週金曜の翌寄りで買うだけ ----
    busy = {}
    fri = set(np.where(pd.Index(dates).dayofweek == 4)[0])
    for t in range(260, n - 1):
        if t not in fri or not (text_tt[t] or orig_tt[t]): continue
        te = t + 1; entry = o[te]; risk = min(2 * atr20[t], 0.10 * entry); stop = entry - risk
        for mode in ('time60', 'ma50'):
            if busy.get(mode, -1) >= te: continue
            r, hold = sim_trade(o, h, l, c, ma50, te, entry, stop, mode)
            if r is None: continue
            busy[mode] = te + hold
            out.append({'tk': tk, 'date': dates[te], 'text_tt': bool(text_tt[t]), 'orig_tt': bool(orig_tt[t]), 'price': c[t],
                        'ud50': ud50[t], 'entry_mode': 'nextopen', 'exit': mode, 'ret': r, 'R': r / (risk / entry),
                        'risk_pct': risk / entry, 'hold': hold, 'kind': 'RANDOM'})
    return out


if __name__ == '__main__':
    px = pd.read_pickle('px.pkl')
    items = [(t, d) for t, d in px.items() if t not in ('SPY', 'QQQ')]
    with Pool(2) as pool: res = pool.map(run, items, chunksize=10)
    df = pd.DataFrame([r for rr in res for r in rr])
    df.to_pickle('vcp_trades.pkl'); print(df.shape); print(df.groupby(['kind', 'entry_mode', 'exit']).size())
