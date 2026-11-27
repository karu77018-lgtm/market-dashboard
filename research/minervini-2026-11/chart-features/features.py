"""チャート側の「インジに出ない」要素を数値化する。全て当日終値までの情報だけで計算（先読みなし）。
ピボットは確定（K本後）した日から使う。"""
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

K = 5  # ピボット確定に必要な左右の本数


def roll(a, w, f):
    s = pd.Series(a)
    return getattr(s.rolling(w, min_periods=w), f)().to_numpy()


def features(df: pd.DataFrame) -> pd.DataFrame:
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
    df = df[(df.Close > 0) & (df.High >= df.Low)]
    o, h, l, c, v = (df[x].to_numpy() for x in ['Open', 'High', 'Low', 'Close', 'Volume'])
    n = len(c)
    pc = np.r_[np.nan, c[:-1]]
    ret = c / pc - 1
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    atr = roll(tr, 14, 'mean')
    atr10, atr50 = roll(tr, 10, 'mean'), roll(tr, 50, 'mean')
    ma10, ma50, ma150, ma200 = (roll(c, w, 'mean') for w in (10, 50, 150, 200))
    hi252, lo252 = roll(h, 252, 'max'), roll(l, 252, 'min')
    v50 = roll(v, 50, 'mean')
    v50p = np.r_[np.nan, v50[:-1]]
    tt = ((c > ma50) & (ma50 > ma150) & (ma150 > ma200) & (ma200 > np.r_[np.full(20, np.nan), ma200[:-20]])
          & (c >= 0.75 * hi252) & (c >= 1.3 * lo252))

    out = {}
    # ---------- 1. 市場構造（ピボット→HH/HL, BOS, CHoCH） ----------
    struct = np.zeros(n); bos_up = np.zeros(n, bool); choch_up = np.zeros(n, bool); bos_dn = np.zeros(n, bool)
    ph, pl = [], []  # (idx, price) 確定済み
    # 2. S/R
    sr_touch_bo = np.zeros(n)            # 突破したレベルのタッチ回数（0=突破なし）
    res_near = np.zeros(n)               # 上方1ATR内の確定ピボット数（上値の壁）
    dist_res = np.full(n, np.nan)        # 直上のピボット高値までの距離(ATR)
    st = 0
    for i in range(n):
        j = i - K
        newp = False
        if j >= K:
            if h[j] == h[j - K:j + K + 1].max(): ph.append((j, h[j])); newp = True
            if l[j] == l[j - K:j + K + 1].min(): pl.append((j, l[j])); newp = True
        if newp and len(ph) >= 2 and len(pl) >= 2:   # 新しいピボットが確定した日だけ判定し直す
            if ph[-1][1] > ph[-2][1] and pl[-1][1] > pl[-2][1]: st = 1
            elif ph[-1][1] < ph[-2][1] and pl[-1][1] < pl[-2][1]: st = -1
        if ph and i > 0:
            lv = ph[-1][1]
            if c[i] > lv >= c[i - 1]:
                bos_up[i] = True
                if st == -1: choch_up[i] = True
                st = 1 if st == -1 else st
        if pl and i > 0:
            lv = pl[-1][1]
            if c[i] < lv <= c[i - 1]:
                bos_dn[i] = True
                if st == 1: st = -1   # 直近ピボット安値割れ＝上昇構造の否定
        struct[i] = st
        a = atr[i]
        if np.isnan(a) or i == 0: continue
        lv_hi = [p for (k, p) in ph if i - k <= 250]
        lv_all = lv_hi + [p for (k, p) in pl if i - k <= 250]
        if lv_all:
            arr = np.array(lv_all)
            above = arr[arr > c[i]]
            res_near[i] = ((arr > c[i]) & (arr <= c[i] + a)).sum()
            if above.size: dist_res[i] = min((above.min() - c[i]) / a, 10)
            else: dist_res[i] = 10
        if lv_hi:
            arr = np.array(lv_hi)
            crossed = arr[(arr <= c[i]) & (arr > c[i - 1])]
            if crossed.size:
                L = crossed.max()
                sr_touch_bo[i] = (np.abs(arr - L) <= 0.5 * a).sum()
    out.update(struct=struct, bos_up=bos_up, choch_up=choch_up, bos_dn=bos_dn,
               sr_touch_bo=sr_touch_bo, res_near=res_near, dist_res=dist_res)

    # ---------- 3. ボリュームプロファイル（252日：上値のしこり／薄い上空、120日：POC・VAH） ----------
    os_ = np.full(n, np.nan); thin_up = np.full(n, np.nan)
    W = 252
    if n > W:
        H, Lw, V = swv(h, W), swv(l, W), swv(v, W)
        C = c[W - 1:][:, None]; A = atr[W - 1:][:, None]
        rng = np.maximum(H - Lw, 1e-9)
        f_above = np.clip((H - C) / rng, 0, 1)
        f_above2 = np.clip((H - (C + 2 * A)) / rng, 0, 1)
        tv = V.sum(1)
        os_[W - 1:] = (V * f_above).sum(1) / tv
        thin_up[W - 1:] = (V * (f_above - f_above2)).sum(1) / tv   # 現値〜+2ATRに乗っている出来高比率
    pos_poc = np.full(n, np.nan); above_vah = np.zeros(n, bool)
    W2 = 120; tp = (h + l + c) / 3
    for i in range(W2 - 1, n, 1):
        if np.isnan(atr[i]): continue
        s = slice(i - W2 + 1, i + 1)
        lo, hi = l[s].min(), h[s].max()
        if hi <= lo: continue
        hist, edges = np.histogram(tp[s], bins=40, range=(lo, hi), weights=v[s])
        k = hist.argmax(); poc = (edges[k] + edges[k + 1]) / 2
        order = np.argsort(hist)[::-1]; cum = np.cumsum(hist[order]); tot = hist.sum()
        if tot <= 0: continue
        va = order[:np.searchsorted(cum, 0.7 * tot) + 1]
        vah = edges[va.max() + 1]
        pos_poc[i] = (c[i] - poc) / atr[i]
        above_vah[i] = c[i] > vah
    out.update(overhead=os_, thin_up=thin_up, pos_poc=pos_poc, above_vah=above_vah)

    # ---------- アンカードVWAP（52週高値日・安値日から） ----------
    cpv, cv = np.cumsum(tp * v), np.cumsum(v)
    av_hi = np.full(n, np.nan); av_lo = np.full(n, np.nan)
    if n > 252:
        Hh, Ll = swv(h, 252), swv(l, 252)
        ahi = Hh.argmax(1) + np.arange(n - 251); alo = Ll.argmin(1) + np.arange(n - 251)
        idx = np.arange(251, n)
        def avw(a):
            pv = cpv[idx] - np.where(a > 0, cpv[np.maximum(a - 1, 0)], 0)
            vv = cv[idx] - np.where(a > 0, cv[np.maximum(a - 1, 0)], 0)
            return pv / np.maximum(vv, 1)
        av_hi[251:] = avw(ahi); av_lo[251:] = avw(alo)
    d_avhi = c / av_hi - 1
    below_prev = roll((c < av_hi).astype(float), 10, 'sum')
    avwap_reclaim = (c > av_hi) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, av_hi[:-1]]) & (np.r_[np.nan, below_prev[:-1]] >= 10)
    out.update(d_avwap_hi=d_avhi, d_avwap_lo=c / av_lo - 1, avwap_reclaim=avwap_reclaim)

    # ---------- 4. 需給 ----------
    up, dn = ret > 0, ret < 0
    ud50 = roll(np.where(up, v, 0), 50, 'sum') / np.maximum(roll(np.where(dn, v, 0), 50, 'sum'), 1)
    vprev = np.r_[np.nan, v[:-1]]
    dist25 = roll(((ret < -0.002) & (v > vprev)).astype(float), 25, 'sum')
    acc25 = roll(((ret > 0.002) & (v > 1.5 * v50p)).astype(float), 25, 'sum')
    rvol = v / v50p
    clv = np.where(h > l, ((c - l) - (h - c)) / np.maximum(h - l, 1e-9), 0)
    clv20 = roll(clv * v, 20, 'sum') / np.maximum(roll(v, 20, 'sum'), 1)
    dnv = np.where(dn, v, 0)
    maxdn10 = np.r_[np.nan, roll(dnv, 10, 'max')[:-1]]
    pocket = up & (v > maxdn10) & (np.abs(c / ma10 - 1) < 0.03) & (c > ma50)
    out.update(ud50=ud50, dist25=dist25, acc25=acc25, rvol=rvol, clv20=clv20, pocket=pocket)

    # ---------- 5. タイミング（収縮→放れ） ----------
    rr = (roll(h, 10, 'max') - roll(l, 10, 'min')) / (roll(h, 60, 'max') - roll(l, 60, 'min'))
    vdry = roll(v, 10, 'mean') / v50
    atr_ratio = atr10 / atr50
    hi20p = np.r_[np.nan, roll(h, 20, 'max')[:-1]]
    rrp, vdp = np.r_[np.nan, rr[:-1]], np.r_[np.nan, vdry[:-1]]
    brk = (c > hi20p)
    tight_bo = brk & (rrp < 0.35) & (vdp < 0.85) & (rvol > 1.4)
    loose_bo = brk & (rrp >= 0.5)
    out.update(range_ratio=rr, vol_dry=vdry, atr_ratio=atr_ratio, brk20=brk, tight_bo=tight_bo, loose_bo=loose_bo)

    # ---------- 6. 流動性 ----------
    dv = c * v
    out.update(ldv50=np.log10(np.maximum(roll(dv, 50, 'mean'), 1)),
               amihud=roll(np.abs(ret) / np.maximum(dv, 1), 20, 'mean') * 1e9)

    # ---------- 先行リターン（翌日寄りで買う前提） ----------
    o1 = np.r_[o[1:], np.nan]
    for hz in (20, 60):
        cf = np.r_[c[hz:], np.full(hz, np.nan)]
        out[f'f{hz}'] = cf / o1 - 1
    lw = swv(np.r_[l[1:], np.full(21, np.nan)], 20)[:n]
    out['mae20'] = np.nanmin(lw, axis=1) / o1 - 1 if len(lw) == n else np.nan
    out['tt'] = tt
    res = pd.DataFrame(out, index=df.index)
    return res
