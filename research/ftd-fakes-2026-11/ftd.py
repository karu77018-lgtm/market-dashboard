"""Site FTD rules (build_dashboard_4.build_ftd) over full history, every event with its outcome."""
import pandas as pd, numpy as np
FTD_PCT=0.0125
def load(n):
    d=pd.read_csv(f'ftd_{n}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').sort_index()
    return d[d.volume>0] if n not in ('VIX','VIX3M','GSPC','IXIC') else d
def events(tk):
    df=load(tk); c,l,h,v=df.close.to_numpy(float),df.low.to_numpy(float),df.high.to_numpy(float),df.volume.to_numpy(float)
    s50=df.close.rolling(50).mean().to_numpy(); hi=df.close.rolling(252,min_periods=252).max().to_numpy()
    corr=(c<s50)|(c/hi-1<=-0.08); corr=np.where(np.isnan(s50),False,corr)
    N=len(c); low_v=low_i=day1=None; ftd=None; armed=False; post_max=np.nan; below50=0; out=[]
    for j in range(1,N):
        cj,cp,lj=c[j],c[j-1],l[j]
        if ftd is not None:
            post_max=cj if not np.isfinite(post_max) else max(post_max,cj)
            s=s50[j]
            if np.isfinite(s):
                below50=below50+1 if cj<s else 0
                if cj>=s: armed=True
            deep=np.isfinite(post_max) and cj/post_max-1<=-0.08
            if cj<ftd['low']: why='a'
            elif armed and (deep or below50>=5): why='b_deep' if deep else 'b_50'
            else: continue
            ftd.update(end=j,why=why); out.append(ftd)
            ftd=None; armed=False; below50=0; post_max=np.nan; day1,low_v,low_i=None,lj,j; continue
        if day1 is not None:
            if lj<low_v: low_v,low_i,day1=lj,j,None; continue
            att=j-day1+1
            if att>=4 and np.isfinite(v[j]) and np.isfinite(v[j-1]):
                chg=cj/cp-1
                if chg>=FTD_PCT and v[j]>v[j-1]:
                    ftd=dict(tk=tk,i=j,date=df.index[j],day=att,pct=chg,low=lj,low_i=low_i,day1=day1)
                    armed=False; below50=0; post_max=cj
            continue
        if not corr[j]: low_v=low_i=None; continue
        if low_v is None or lj<low_v:
            low_v,low_i=lj,j
            if cj>cp: day1=j
        elif cj>cp: day1=j
    if ftd is not None: ftd.update(end=None,why=None); out.append(ftd)
    return df,out
if __name__=='__main__':
    for tk in ('QQQ','SPY'):
        df,ev=events(tk); print(tk,len(ev),'events')
        for e in ev[-6:]:
            end=df.index[e['end']].date() if e['end'] is not None else None
            print('  ',e['date'].date(),'Day',e['day'],f"+{e['pct']*100:.1f}%",'low',df.index[e['low_i']].date(),'-> end',end,e['why'],'(',(e['end']-e['i']) if e['end'] else '-','sessions)')
