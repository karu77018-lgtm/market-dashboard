#!/usr/bin/env python3
"""Independent adjusted-price history for explanation only; never a trading gate.

Cached Yahoo Adj Close, exact observed sessions, no fill/interpolation/substitution.
MAG7 is a fixed retrospective basket (not historical membership): arithmetic mean
of seven adjusted daily returns, rebalanced to 1/7 at each close. No fees/taxes.
GICS ranks are descending daily h-session total returns relative to SPY, ties
broken by ticker; a rank row exists ONLY when all eleven + SPY are observed.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from v38 import live_acquisition as la

WINDOWS = {'2y': 504, '5y': 1260, '10y': 2520}
MAG7 = ['AAPL','MSFT','NVDA','AMZN','META','GOOGL','TSLA']
SIZES = {'Small':'IWM','Mid':'MDY','Large':'SPY','Mega':'XLG'}
GICS = {'RSPT':'情報技術','RSPF':'金融','RSPN':'資本財','RSPD':'一般消費財',
        'RSPM':'素材','RSPC':'通信','RSPU':'公益','RSPS':'生活必需品',
        'RSPH':'ヘルスケア','RSPR':'不動産','RSPG':'エネルギー'}
SYMBOLS = list(dict.fromkeys(['SPY','RSP','QQQ','QQQE','IWM','MDY','XLG', *GICS, *MAG7,
    'TQQQ','SOXL','SOXX','^VIX','^VIX3M','HYG','IEI','LQD','XLY','XLP','XLV','XLU']))
GROUPS = {
    'MA参加率':['close_gt_sma10','close_gt_sma20','close_gt_sma50','close_gt_sma200'],
    'リターン参加率':['ret5_gt_0','ret21_gt_0','ret63_gt_0','ret252_gt_0'],
    'トレンド構造':['sma20_gt_sma50','sma50_gt_sma200','sma50_gt_sma50_shift20'],
    'ドローダウン耐性':['dd52_continuous_score'],
}
LABELS = {'close_gt_sma10':'10MA上','close_gt_sma20':'20MA上','close_gt_sma50':'50MA上','close_gt_sma200':'200MA上',
 'ret5_gt_0':'5Dプラス','ret21_gt_0':'21Dプラス','ret63_gt_0':'63Dプラス','ret252_gt_0':'252Dプラス',
 'sma20_gt_sma50':'20MA > 50MA','sma50_gt_sma200':'50MA > 200MA','sma50_gt_sma50_shift20':'50MA上向き（20D比較）',
 'dd52_continuous_score':'52週高値からの距離スコア'}


def write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')


def rows(s):
    return [[d.strftime('%Y-%m-%d'), float(v)] for d,v in s.dropna().items() if np.isfinite(v)]


def read_prices(path):
    if not path.exists(): return pd.DataFrame()
    j=json.loads(path.read_text()); out={}
    for tk, a in j.get('series',{}).items():
        out[tk]=pd.Series({pd.Timestamp(d):v for d,v in a},dtype=float)
    return pd.DataFrame(out).sort_index()


def acquire(target, cache):
    old=read_prices(cache)
    start=pd.Timestamp(target)-pd.DateOffset(years=12)
    old=old.loc[(old.index>=start)&(old.index<=pd.Timestamp(target))] if not old.empty else old
    series={}; errors={}
    for tk in SYMBOLS:
        prior=old[tk].dropna() if tk in old else pd.Series(dtype=float)
        # Same-session cache is explicit and dated, never yesterday masquerading as today.
        if len(prior)>1 and prior.index[-1]==pd.Timestamp(target):
            series[tk]=prior; continue
        incremental=len(prior)>252
        begin=prior.index[-10] if incremental else start
        def download(begin):
            raw=yf.download(tk,start=begin.strftime('%Y-%m-%d'),
                end=(pd.Timestamp(target)+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                auto_adjust=False,actions=False,progress=False,threads=False,timeout=20)
            f=la.select_yfinance_symbol_frame(raw,tk)
            if f.empty or 'adj_close' not in f: return pd.Series(dtype=float)
            s=pd.to_numeric(f['adj_close'],errors='coerce'); s.index=pd.to_datetime(s.index,utc=True).tz_localize(None).normalize()
            return s.loc[(s.index<=pd.Timestamp(target)) & (s>0)].dropna().sort_index()
        try:
            fresh=download(begin)
            if incremental and not fresh.empty:
                common=prior.index.intersection(fresh.index)
                # Dividends/splits revise all adjusted history; refetch instead of
                # splicing two adjustment bases or silently scaling old prices.
                if len(common) and not np.allclose(prior.loc[common],fresh.loc[common],rtol=2e-5,atol=1e-6):
                    fresh=download(start); prior=pd.Series(dtype=float)
            if fresh.empty: errors[tk]='Yahoo history unavailable'
            else:
                prior=pd.concat([prior,fresh]); prior=prior[~prior.index.duplicated(keep='last')].sort_index()
        except Exception as exc: errors[tk]=type(exc).__name__
        if not prior.empty: series[tk]=prior
        print(f'long history {tk}: {len(prior)} bars; latest {prior.index[-1].date() if len(prior) else "unavailable"}',flush=True)
    frame=pd.DataFrame(series).sort_index()
    write(cache,{'vendor':'Yahoo Finance / explicit Adj Close','session_date':target,
                 'series':{tk:rows(s) for tk,s in series.items()},'errors':errors})
    return frame,errors


def mag7_index(frame):
    if any(tk not in frame for tk in MAG7): return pd.Series(dtype=float)
    # Never bridge missing daily sessions with pct_change defaults or dropna first.
    p=frame[MAG7]; valid=p.notna().all(axis=1)
    r=p.pct_change(fill_method=None).mean(axis=1).where(valid & valid.shift(1,fill_value=False))
    if not valid.any(): return pd.Series(dtype=float)
    first=valid[valid].index[0]
    # Cumulative basket ceases at any gap. A fabricated continuous index is forbidden.
    r=r.loc[first:]; index=pd.Series(np.nan,index=r.index); index.iloc[0]=100.0
    level=100.0
    for i in range(1,len(r)):
        if pd.isna(r.iloc[i]): break
        level*=1+r.iloc[i]; index.iloc[i]=level
    return index


def returns(s,h,target):
    if target not in s.index or pd.isna(s.loc[target]): return None
    # h counts common observed ETF sessions, never calendar days.
    r=s.pct_change(h,fill_method=None).loc[target]
    return float(r*100) if pd.notna(r) and np.isfinite(r) else None


def rank_history(frame,h):
    if any(tk not in frame for tk in [*GICS,'SPY']): return []
    rets=frame[[*GICS,'SPY']].pct_change(h,fill_method=None)
    # Transparent excess total return; common SPY benchmark does not affect order.
    excess=rets[list(GICS)].sub(rets['SPY'],axis=0)
    valid=rets.notna().all(axis=1)
    result=[]
    for d,row in excess.loc[valid].iterrows():
        ordered=sorted(GICS,key=lambda tk:(-float(row[tk]),tk))
        result.append({'date':d.strftime('%Y-%m-%d'),'ranks':{tk:ordered.index(tk)+1 for tk in GICS},
                       'rs':{tk:float(row[tk]*100) for tk in GICS}})
    return result


def package_series(frame, target):
    out={name:frame[tk] for name,tk in SIZES.items() if tk in frame}
    out['MAG7']=mag7_index(frame)
    leaders={k:{str(h):returns(s,h,pd.Timestamp(target)) for h in (21,63)} for k,s in out.items()}
    # Leadership = descending 63-session return, ticker/name tie-break. No extra score.
    lead=sorted((k for k,v in leaders.items() if v['63'] is not None),key=lambda k:(-leaders[k]['63'],k))
    pairs={tk:frame[tk] for tk in ('SPY','RSP','QQQ','QQQE') if tk in frame}
    ratios={}
    for a,b in [('SPY','RSP'),('QQQ','QQQE')]:
        if a in pairs and b in pairs: ratios[a+'/'+b]=pairs[a]/pairs[b]
    idx={tk:{str(h):returns(s,h,pd.Timestamp(target)) for h in (21,63)} for tk,s in pairs.items()}
    spread={a+'-'+b:{str(h):idx[a][str(h)]-idx[b][str(h)] if idx.get(a,{}).get(str(h)) is not None and idx.get(b,{}).get(str(h)) is not None else None for h in (21,63)} for a,b in [('SPY','RSP'),('QQQ','QQQE')]}
    return out,pairs,ratios,{'leaders':leaders,'leading':lead[:2],'indices':idx,'spread':spread,'gics':{}}


def export_windows(outdir,name,series,target, *, mode='lines',normalized=False,meta=None):
    """Small separate files; 5Y/10Y fetched only on demand. Keep null gaps."""
    manifest={}
    all_dates=sorted(set().union(*(set(s.index) for s in series.values()))) if series else []
    for win,n in WINDOWS.items():
        dates=all_dates[-n:]; a={}; availability={}
        for k,s in series.items():
            v=s.reindex(dates); good=v.dropna()
            enough=len(good)>=n and len(dates)==n and good.index[-1]==pd.Timestamp(target)
            availability[k]={'status':'READY' if enough else 'INSUFFICIENT_HISTORY',
                'bars':len(good),'start':good.index[0].strftime('%Y-%m-%d') if len(good) else None,
                'end':good.index[-1].strftime('%Y-%m-%d') if len(good) else None}
            a[k]=[float(x) if pd.notna(x) and np.isfinite(x) else None for x in v]
        payload={'schema':'market-history.1','session_date':target,'window':win,'mode':mode,
                 'normalized':normalized,'dates':[d.strftime('%Y-%m-%d') for d in dates],
                 'series':a,'availability':availability,**(meta or {})}
        path=f'{name}-{win}.json'; write(outdir/path,payload); manifest[win]=path
    return manifest


def build(root,target, *, offline=False):
    outdir=root/'market-history'; cache=root/'work/market-history-prices.json'
    frame,errors=(read_prices(cache),{}) if offline else acquire(target,cache)
    if not frame.empty: frame=frame.reindex(frame.index.union([pd.Timestamp(target)])).sort_index()
    sizes,pairs,ratios,summary=package_series(frame,target)
    manifest={'schema':'market-history.index.1','session_date':target,'files':{},'errors':errors,
              'source':'Yahoo Finance explicit Adj Close; observed sessions only',
              'breadth_policy':'2Y only: historical point-in-time universe unavailable',
              'mag7_method':'fixed retrospective seven-stock basket; daily equal-weight rebalance; adjusted returns; no fees',
              'summary':summary}
    f=manifest['files']
    f['leadership']=export_windows(outdir,'leadership',sizes,target,normalized=True)
    f['concentration']=export_windows(outdir,'concentration',pairs,target,normalized=True)
    f['relative']=export_windows(outdir,'relative',ratios,target,normalized=True)
    f['indices']=export_windows(outdir,'indices',{k:frame[k] for k in ['QQQ','SPY','TQQQ','SOXX','SOXL','^VIX'] if k in frame},target,normalized=True)
    gics={}
    for h in (21,63,126):
        full=rank_history(frame,h)
        current=full[-1] if full and full[-1]['date']==target else None
        prev=full[-21] if len(full)>=21 and current else None
        summary['gics'][str(h)]={'current':current,'previous':prev}
        gics[str(h)]={}
        for win,n in WINDOWS.items():
            cut=full[-n:]
            if win!='2y' and cut: cut=cut[::5]+([cut[-1]] if cut[-1]!=cut[::5][-1] else [])
            path=f'gics11-{h}-{win}.json'; write(outdir/path,{'schema':'market-history.gics11.1',
                'session_date':target,'window':win,'horizon':h,'sectors':GICS,'rows':cut,
                'source_bars':min(len(full),n),'status':'READY' if len(full)>=n and current else 'INSUFFICIENT_HISTORY',
                'current':current,'previous':prev,'method':'daily excess adjusted total returns vs SPY; descending rank; ticker tie-break; all 11 required'})
            gics[str(h)][win]=path
    f['gics11']=gics
    # Derived long charts; exact existing trailing z convention, no missing-price fill.
    derived={}
    for name,num,dens in [('credit','HYG',['IEI']),('defensive','XLY',['XLP','XLV','XLU'])]:
        if all(k in frame for k in [num,*dens]):
            p=frame[[num,*dens]].dropna(how='all'); starts=p.iloc[0]
            denom=p[dens].div(starts[dens]).mean(axis=1).where(p[dens].notna().all(axis=1))
            ratio=(p[num]/starts[num])/denom
            z=(ratio-ratio.rolling(252,min_periods=84).mean())/ratio.rolling(252,min_periods=84).std()
            derived[name]=z
    if '^VIX' in frame and '^VIX3M' in frame: derived['vixterm']=frame['^VIX']/frame['^VIX3M']
    for name,s in derived.items(): f[name]=export_windows(outdir,name,{name:s},target)
    mcpath=root/'data/mc57.json'
    if mcpath.exists():
        mc=json.loads(mcpath.read_text()); fullpath=outdir/'mc57-full.json'
        full=json.loads(fullpath.read_text()) if fullpath.exists() else {'history':mc['history']}
        hist=full['history']; f['mc57']=export_windows(outdir,'mc57',{'MC57':pd.Series({pd.Timestamp(r['date']):r['mc57'] for r in hist})},target,
            meta={'source':mc['source'],'calculation_version':mc['calculation_version'],'current':mc['mc57'],
                  'historical_universe':'fixed57 ETF basket; inception-dependent valid denominators, not point-in-time stock breadth'})
        for label,keys in GROUPS.items():
            key='mc57-group-'+str(list(GROUPS).index(label))
            group={LABELS[k]:pd.Series({pd.Timestamp(r['date']):r['metrics'].get(k,np.nan) for r in hist}) for k in keys}
            f[key]=export_windows(outdir,key,group,target)
    write(outdir/'index.json',manifest)
    return manifest

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--session'); ap.add_argument('--offline',action='store_true')
    args=ap.parse_args(); root=Path(args.root); target=args.session or json.loads((root/'latest-manifest.json').read_text())['session_date']
    result=build(root,target,offline=args.offline); print(json.dumps({'session':target,'files':list(result['files']),'errors':result['errors']}))
