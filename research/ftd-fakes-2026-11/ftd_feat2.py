import pandas as pd, numpy as np, io, re, warnings; warnings.filterwarnings('ignore')
import ftd
X=pd.read_pickle('ftd_events.pkl')
rd=lambda n,c='close': pd.read_csv(f'macro/{n}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date')[c]
SEC=['XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB']; S={k:rd(k) for k in SEC+['HYG','IEF','TLT','DXY']}
# panel 2013+
D=pd.read_pickle('core.pkl'); c,v,liq,ok,rs,hi=D['c'],D['v'],D['liquid'],D['ok'],D['rs'],D['hi']
r1=c.pct_change(fill_method=None); up=(r1>0)&liq; dn=(r1<0)&liq
upshare=up.sum(axis=1)/liq.sum(axis=1)*100
dv=(c*v).where(liq); upvol=dv.where(up).sum(axis=1)/dv.sum(axis=1)*100
lo=D['l'].rolling(252).min() if 'l' in D else c.rolling(252).min()
nhnl=(((c>=c.rolling(252).max())&liq).sum(axis=1)-((c<=c.rolling(252).min())&liq).sum(axis=1))/liq.sum(axis=1)*100
ttr=ok.sum(axis=1)/liq.sum(axis=1)*100
E_=pd.read_pickle('events.pkl'); bo=E_.groupby('date').size().reindex(c.index,fill_value=0)
b50=((c>D['s50'])&liq).sum(axis=1)/liq.sum(axis=1)*100
# sentiment / heat
a=pd.read_excel('ext/aaii.xls',header=None); a=a[pd.to_datetime(a[0],errors='coerce').notna()][[0,1,2,3]].dropna(); a.columns=['date','bull','neut','bear']; a['date']=pd.to_datetime(a['date']); a=a.set_index('date').astype(float)*100
m=pd.read_excel('ext/finra.xlsx'); m.columns=['ym','debit','c1','c2']; m['date']=pd.to_datetime(m.ym.astype(str)+'-01')+pd.offsets.MonthEnd(0); md=m.set_index('date').debit.sort_index().astype(float)
def cboe(fs):
    d={}
    for f in fs:
        for ln in open('ext/'+f,encoding='latin-1').read().splitlines():
            p=[x.strip() for x in ln.split(',')]
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}$',p[0]) and len(p)>=5:
                try: d[pd.to_datetime(p[0])]=float(p[-1])
                except ValueError: pass
    return pd.Series(d).sort_index()
pce=cboe(['cboe_equity_arch.csv','cboe_equity.csv'])
cape=pd.Series({pd.Timestamp(k):v for k,v in __import__('json').load(open('/home/claude/md/seed/decline-slow.json'))['series']['cape'].items()})
import sys; sys.path.insert(0,'/home/claude/md/scripts'); import decline_anatomy as da
cape=pd.Series({pd.Timestamp(k):v for k,v in da.parse_multpl(open('ext/multpl_cape.html',encoding='utf-8').read()).items()}).sort_index()
DF={tk:ftd.events(tk)[0] for tk in ('QQQ','SPY')}
def chg(s,d,n):
    s=s.dropna(); 
    if d not in s.index: return np.nan
    i=s.index.get_loc(d); return (s.iloc[i]/s.iloc[i-n]-1)*100 if i>=n else np.nan
def third_friday(d):
    f=pd.Timestamp(d.year,d.month,15); 
    while f.weekday()!=4: f+=pd.Timedelta(days=1)
    return f
rows=[]
for k,r in X.iterrows():
    tk,d=r.tk,r.date; df=DF[tk]; i=df.index.get_loc(d); cc,vv,oo=df.close,df.volume,df.open
    lo_i=None
    out={}
    # rally character
    e=[x for x in ftd.events(tk)[1] if x['date']==d][0] if False else None
    w=df.iloc[max(0,i-r.day-1):i+1]
    out['updays']=int((w.close.diff()>0).sum()); 
    seg=df.iloc[max(0,i-r.day-3):i+1]; li=seg.low.idxmin(); out['lowvol']=df.volume[li]/df.volume.rolling(50).mean().shift(1)[li]
    out['ema21']=float(cc.iloc[i]>cc.ewm(span=21,adjust=False).mean().iloc[i]); out['a50']=float(cc.iloc[i]>cc.rolling(50).mean().iloc[i])
    out['gapup']=float(oo.iloc[i]/cc.iloc[i-1]-1>=0.005)
    out['prevday']=(cc.iloc[i-1]/cc.iloc[i-2]-1)*100
    # sectors / intermarket
    sr=[chg(S[s],d,1) for s in SEC]; out['secup']=np.nansum([x>0 for x in sr]) if not np.isnan(sr).all() else np.nan
    out['hyg1']=chg(S['HYG'],d,1)-chg(S['IEF'],d,1); out['hyg20']=chg(S['HYG'],d,20)-chg(S['IEF'],d,20)
    out['usd20']=chg(S['DXY'],d,20); out['tlt1']=chg(S['TLT'],d,1); out['tlt20']=chg(S['TLT'],d,20)
    # panel
    if d in c.index:
        j=c.index.get_loc(d)
        out.update(upshare=upshare.iloc[j],upvol=upvol.iloc[j],nhnl=nhnl.iloc[j],nhnl_ch=nhnl.iloc[j]-nhnl.iloc[j-10],ttr=ttr.iloc[j],ttr_ch=ttr.iloc[j]-ttr.iloc[j-10],
                   bo_pre=bo.iloc[j-9:j+1].sum(),bo_post=bo.iloc[j+1:j+6].sum() if j+6<=len(bo) else np.nan,
                   b50_post=b50.iloc[j+5]-b50.iloc[j] if j+5<len(b50) else np.nan, upvol_post=upvol.iloc[j+1:j+6].max() if j+6<=len(upvol) else np.nan)
        out['ninety']=float(upvol.iloc[max(0,j-9):j+1].max()>=90)
    # sentiment / heat
    s=a.bear[:d]; out['aaii_bear']=s.iloc[-1] if len(s) else np.nan; s=(a.bull-a.bear)[:d]; out['aaii_spread']=s.iloc[-1] if len(s) else np.nan
    s=pce[:d]; out['pc10']=s.iloc[-10:].mean() if len(s) and (d-s.index[-1]).days<10 else np.nan
    s1,s0=md[:d-pd.Timedelta(days=30)],md[:d-pd.Timedelta(days=395)]; out['md_yoy']=(s1.iloc[-1]/s0.iloc[-1]-1)*100 if len(s1) and len(s0) else np.nan
    s=cape[:d]; out['cape']=s.iloc[-1] if len(s) else np.nan
    # calendar
    tf=third_friday(d); out['opex_wk']=float(0<= (tf-d).days <=4); out['earn']=float(d.month in (1,4,7,10) and 10<=d.day<=31); out['month']=d.month
    # post: second FTD within 10 days from other index or same index
    oth='SPY' if tk=='QQQ' else 'QQQ'
    od=[x['date'] for x in ftd.events(oth)[1]] if False else None
    rows.append(out)
N=pd.DataFrame(rows,index=X.index); Y=X.join(N); Y.to_pickle('ftd_events2.pkl'); print(Y.shape); print(N.describe().T[['count','mean','50%']].round(2).to_string())
