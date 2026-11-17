"""New factors at the starts of declines and rallies: liquidity, financial conditions, jobless claims, the yen,
futures positioning (CFTC), breadth of the local panel, calendar.  Each factor is split at its own median and
checked in two halves of the events it covers (halves split at the median event date)."""
import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
def fred(p,col=None):
    s=pd.read_csv(p); s.columns=['date','v']; s['date']=pd.to_datetime(s.date); s['v']=pd.to_numeric(s.v,errors='coerce'); return s.dropna().set_index('date').v.sort_index()
walcl,tga,rrp=fred('ext2/WALCL.csv'),fred('ext2/WTREGEN.csv'),fred('ext2/RRPONTSYD.csv')
nfci=fred('macro/F_NFCI.csv') if __import__('os').path.exists('macro/F_NFCI.csv') else fred('ext2/NFCI.csv')
icsa=fred('ext2/ICSA.csv'); jpy=fred('ext2/DEXJPUS.csv')
idx=pd.date_range('2002-12-01','2026-11-20',freq='D')
liq=(walcl.reindex(idx).ffill()-tga.reindex(idx).ffill()-rrp.reindex(idx).ffill().fillna(0)*1000)
cot=pd.read_pickle('ext2/cot_tff.pkl'); cot['date']=pd.to_datetime(cot['Report_Date_as_YYYY-MM-DD'])
def cotnet(name):
    c=cot[cot.Market_and_Exchange_Names.str.startswith(name)].set_index('date').sort_index()
    lev=(c.Lev_Money_Positions_Long_All-c.Lev_Money_Positions_Short_All)/c.Open_Interest_All*100
    am=(c.Asset_Mgr_Positions_Long_All-c.Asset_Mgr_Positions_Short_All)/c.Open_Interest_All*100
    z=lambda s:(s-s.rolling(156,min_periods=52).mean())/s.rolling(156,min_periods=52).std()
    return pd.DataFrame({'lev':lev,'levz':z(lev),'am':am,'amz':z(am)})
COT={'NDX':cotnet('NASDAQ-100 Consolidated'),'GSPC':cotnet('S&P 500 Consolidated')}
C=pd.read_pickle('close.pkl').astype(float); H=C.rolling(252,min_periods=200)
m200=C.rolling(200,min_periods=180).mean(); a200=(C>m200).astype(float).where(m200.notna())
p200=(a200.sum(axis=1)/a200.notna().sum(axis=1).replace(0,np.nan)*100)
m50=C.rolling(50,min_periods=45).mean(); a50=(C>m50).astype(float).where(m50.notna()); p50=a50.sum(axis=1)/a50.notna().sum(axis=1).replace(0,np.nan)*100
nh=(C>=C.rolling(252,min_periods=200).max()).sum(axis=1); nl=(C<=C.rolling(252,min_periods=200).min()).sum(axis=1); nn=C.notna().sum(axis=1)
nhnl=(nh-nl)/nn.replace(0,np.nan)*100
adv=(C.pct_change()>0).sum(axis=1); dec=(C.pct_change()<0).sum(axis=1); thrust=(adv/(adv+dec).replace(0,np.nan)).rolling(10).mean()
def asof(s,d,lag=0):
    x=s[:d-pd.Timedelta(days=lag)]; return x.iloc[-1] if len(x) else np.nan
def at(s,d): return s.get(d,np.nan)
def add(R,IDXN):
    R=R.copy(); cn=COT[IDXN]
    R['liq13']=[ (asof(liq,d,2)/asof(liq,d,2+91)-1)*100 if d>pd.Timestamp('2003-06-01') else np.nan for d in R.date]
    R['nfci']=[asof(nfci,d,7) for d in R.date]
    R['nfci4']=[asof(nfci,d,7)-asof(nfci,d,35) for d in R.date]
    R['claims']=[ (icsa[:d-pd.Timedelta(days=5)].tail(4).mean()/icsa[:d-pd.Timedelta(days=5)].tail(26).min()-1)*100 for d in R.date]
    R['yen20']=[ (asof(jpy,d,1)/asof(jpy,d,29)-1)*100 for d in R.date]   # negative = yen stronger
    R['levz']=[asof(cn.levz,d,3) for d in R.date]; R['amz']=[asof(cn.amz,d,3) for d in R.date]
    R['p200']=[at(p200,d) for d in R.date]; R['p50']=[at(p50,d) for d in R.date]; R['nhnl']=[at(nhnl,d) for d in R.date]; R['thrust']=[at(thrust,d) for d in R.date]
    R['opex']=[float(15<=d.day<=21) for d in R.date]; R['pres']=[float(d.year%4 in (1,2)) for d in R.date]   # first two years of a term
    R['dlow']=[float(d.month in (9,10)) for d in R.date]
    return R
NEW=['liq13','nfci','nfci4','claims','yen20','levz','amz','p200','p50','nhnl','thrust','opex','pres','dlow']
def screen(S,y):
    out=[]
    for k in NEW:
        x=S.dropna(subset=[k,y])
        if len(x)<16: out.append(dict(k=k,n=len(x))); continue
        med=x[k].median() if x[k].nunique()>2 else 0.5
        mid=x.date.sort_values().iloc[len(x)//2]
        res=[]
        for z in (x[x.date<mid],x[x.date>=mid]):
            hi_=z[z[k]>med][y]; lo_=z[z[k]<=med][y]
            res.append((hi_.mean()*100 if len(hi_) else np.nan, lo_.mean()*100 if len(lo_) else np.nan,len(hi_),len(lo_)))
        d1=res[0][0]-res[0][1]; d2=res[1][0]-res[1][1]
        out.append(dict(k=k,n=len(x),since=str(x.date.min().date())[:7],cut=round(med,2),split=str(mid.date())[:7],
                        hi1=np.round(res[0][0]),lo1=np.round(res[0][1]),hi2=np.round(res[1][0]),lo2=np.round(res[1][1]),
                        same=bool(np.sign(d1)==np.sign(d2) and min(abs(d1),abs(d2))>=10)))
    return pd.DataFrame(out)
pd.set_option('display.width',250)
for IDXN in ('NDX','GSPC'):
    R=add(pd.read_pickle(f'ud2_{IDXN}.pkl'),IDXN); R.to_pickle(f'ud5_{IDXN}.pkl')
    D=R[(R.kind=='down')&~R.open_.fillna(False).astype(bool)]; U=R[(R.kind=='up')].dropna(subset=['ok'])
    print(f'\n######## {IDXN} down start -> -10%  (rate % above/below the cut, early/late half)'); print(screen(D,'hit10').to_string(index=False))
    print(f'\n######## {IDXN} up start -> real bottom'); print(screen(U,'ok').to_string(index=False))
E=add(pd.read_pickle('rally_ep.pkl').dropna(subset=['ok']),'NDX'); E.to_pickle('ud5_rally.pkl')
print('\n######## NDX +10% rally -> real bottom'); print(screen(E,'ok').to_string(index=False))
