import pandas as pd, numpy as np, io, warnings, sys; warnings.filterwarnings('ignore')
IDXN=sys.argv[1] if len(sys.argv)>1 else 'NDX'
R=pd.read_pickle(f'ud_{IDXN}.pkl')
def multpl(nm):
    t=pd.read_html(io.StringIO(open(f'ext/multpl_{nm}.html',encoding='utf-8').read()))[0]; t.columns=['date','v']
    t['date']=pd.to_datetime(t['date'],errors='coerce'); t['v']=pd.to_numeric(t['v'].astype(str).str.replace(r'[^0-9.\-]','',regex=True),errors='coerce')
    return t.dropna().set_index('date').v.sort_index()
cape=multpl('cape')
def fredf(p):
    s=pd.read_csv(p,parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; return pd.to_numeric(s,errors='coerce').dropna()
mm=fredf('ext/F_WRMFNS.csv')
a=pd.read_excel('ext/aaii.xls',header=None); a=a[pd.to_datetime(a[0],errors='coerce').notna()][[0,1,2,3]].dropna(); a.columns=['date','bull','neut','bear']; a['date']=pd.to_datetime(a['date']); a=a.set_index('date').astype(float)*100; a['spread']=a.bull-a.bear
m=pd.read_excel('ext/finra.xlsx'); m.columns=['ym','debit','c1','c2']; m['date']=pd.to_datetime(m.ym.astype(str)+'-01')+pd.offsets.MonthEnd(0); md=m.set_index('date').debit.sort_index().astype(float)
asof=lambda s,d,lag=0: s[:d-pd.Timedelta(days=lag)].iloc[-1] if len(s[:d-pd.Timedelta(days=lag)]) else np.nan
R['cape']=[asof(cape,d,0) for d in R.date]
R['margin']=[(asof(md,d,25)/asof(md,d,25+365)-1)*100 for d in R.date]
R['mmf']=[(asof(mm,d,10)/asof(mm,d,10+365)-1)*100 for d in R.date]
R['aaii']=[asof(a.spread,d,0) for d in R.date]
R.to_pickle(f'ud2_{IDXN}.pkl')
import importlib.util
spec=importlib.util.spec_from_file_location('u','ud.py')
src=open('ud.py').read(); screen_src=src[src.index('def screen'):src.index("K=['days'")]
exec(screen_src)
D=R[R.kind=='down']; U=R[R.kind=='up']
pd.set_option('display.width',250)
print(IDXN,'slow factors: down -> -10%'); print(screen(D,'hit10',['cape','margin','mmf','aaii']).to_string(index=False))
print('down -> -20%'); print(screen(D,'hit20',['cape','margin','mmf','aaii','sox','curve','vix','cred']).to_string(index=False))
print('up -> real bottom'); print(screen(U,'ok',['cape','margin','mmf','aaii']).to_string(index=False))
# depth control for up starts
U=U.copy(); U['deep']=U.depth<=-17
for k,cut,dirn in (('days',3,'>'),('maxday',3.7,'<'),('a50',0.5,'>'),('ftd',0.5,'>'),('vix',26,'<'),('sec50',2,'>')):
    out=[]
    for dp in (False,True):
        z=U[(U.deep==dp)].dropna(subset=[k,'ok'])
        g=(z[k]>cut) if dirn=='>' else (z[k]<cut)
        out.append(f"{'深い' if dp else '浅い'}: {z[g].ok.mean()*100:3.0f}% (n{g.sum()}) vs {z[~g].ok.mean()*100:3.0f}% (n{(~g).sum()})")
    print(f'up {k}{dirn}{cut}: ',' | '.join(out))
