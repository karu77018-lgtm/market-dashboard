import pandas as pd, numpy as np, io, warnings; warnings.filterwarnings('ignore')
F=pd.read_pickle('episodes_x.pkl'); F=F.rename(columns={'gold_x':'gold'}).drop(columns=['gold_y'],errors='ignore')
def multpl(nm):
    t=pd.read_html(io.StringIO(open(f'ext/multpl_{nm}.html',encoding='utf-8').read()))[0]; t.columns=['date','v']
    t['date']=pd.to_datetime(t['date'],errors='coerce'); t['v']=pd.to_numeric(t['v'].astype(str).str.replace(r'[^0-9.\-]','',regex=True),errors='coerce')
    return t.dropna().set_index('date').v.sort_index()
pe,cape,eps=multpl('pe'),multpl('cape'),multpl('eps')
def fredf(p):
    s=pd.read_csv(p,parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; return pd.to_numeric(s,errors='coerce').dropna()
um=fredf('ext/F_UMCSENT.csv'); mm=fredf('ext/F_WRMFNS.csv'); d10=fredf('macro/F_DGS10.csv')
a=pd.read_excel('ext/aaii.xls',header=None); a=a[pd.to_datetime(a[0],errors='coerce').notna()][[0,1,2,3]].dropna(); a.columns=['date','bull','neut','bear']; a['date']=pd.to_datetime(a['date']); a=a.set_index('date').astype(float)*100; a['spread']=a.bull-a.bear
m=pd.read_excel('ext/finra.xlsx'); m.columns=['ym','debit','c1','c2']; m['date']=pd.to_datetime(m.ym.astype(str)+'-01')+pd.offsets.MonthEnd(0); md=m.set_index('date').debit.sort_index().astype(float)
def cboe(fs):
    import re
    d={}
    for f in fs:
        for ln in open('ext/'+f,encoding='latin-1').read().splitlines():
            p=[x.strip() for x in ln.split(',')]
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}$',p[0]) and len(p)>=5:
                try: d[pd.to_datetime(p[0])]=float(p[-1])
                except ValueError: pass
    return pd.Series(d).sort_index()
pce=cboe(['cboe_equity_arch.csv','cboe_equity.csv']); print('equity p/c',pce.index[0].date(),pce.index[-1].date())
asof=lambda s,d,lag=0: s[:d-pd.Timedelta(days=lag)].iloc[-1] if len(s[:d-pd.Timedelta(days=lag)]) else np.nan
rows=[]
for r in F.itertuples():
    pk,T=pd.Timestamp(r.peak),pd.Timestamp(r._2) if False else (pd.Timestamp(r.peak),pd.Timestamp(F.loc[r.Index,'T']))
    pk,T=pd.Timestamp(r.peak),pd.Timestamp(F.loc[r.Index,'T'])
    e0=asof(eps,pk,90); e12=asof(eps,pk,90+365); e6=asof(eps,pk,90+182); emax=eps[:pk-pd.Timedelta(days=90)].max()
    c=asof(cape,pk); c10=cape[pk-pd.Timedelta(days=3650):pk].mean()
    row=dict(peak=r.peak, pe=asof(pe,pk), cape=c, cape_rel=(c/c10-1)*100, erp=100/asof(pe,pk)-asof(d10,pk),
      epsg=(e0/e12-1)*100, eps6=(e0/e6-1)*100, eps_dd=(e0/emax-1)*100,
      aaii_pk=asof(a.spread,pk), aaii_T=asof(a.spread,T), aaii_d=asof(a.spread,T)-asof(a.spread,pk), bull_pk8=a.bull[:pk].iloc[-8:].mean(), bear_T=asof(a.bear,T),
      um=asof(um,pk,30), um6=asof(um,pk,30)-asof(um,pk,30+182),
      md_yoy=(asof(md,pk,30)/asof(md,pk,30+365)-1)*100 if pk>pd.Timestamp('1998-04-01') else np.nan, md_3m=(asof(md,pk,30)/asof(md,pk,30+91)-1)*100 if pk>pd.Timestamp('1997-07-01') else np.nan,
      mm13=(asof(mm,T,7)/asof(mm,T,7+91)-1)*100, mm_yoy=(asof(mm,pk,7)/asof(mm,pk,7+365)-1)*100,
      pc_T=pce[:T].iloc[-20:].mean() if pce.index[0]<pk and T<=pce.index[-1] else np.nan, pc_pk=pce[:pk].iloc[-20:].mean() if pce.index[0]+pd.Timedelta(days=40)<pk and pk<=pce.index[-1] else np.nan)
    rows.append(row)
N=pd.DataFrame(rows); G=F.merge(N,on='peak'); G.to_pickle('episodes_y.pkl')
cur=G.iloc[-1]; P=G.iloc[:-1]; P=P[pd.to_datetime(P['T'])<pd.Timestamp('2026-01-01')].reset_index(drop=True)
NEW=[c for c in N.columns if c!='peak']
pd.set_option('display.width',300); pd.set_option('display.max_columns',40)
print(G[['peak']+NEW+['more','f120']].round(1).to_string())
print('\n== current vs past')
for f in NEW:
    if pd.isna(cur[f]): print(f"  {f:9s} now NaN"); continue
    x=P[f].dropna(); print(f"  {f:9s} now {cur[f]:7.1f} | past median {x.median():7.1f} (n={len(x)}) z {(cur[f]-x.mean())/x.std():+.1f} pctile {(x<cur[f]).mean()*100:3.0f}")
OUT=['more','f60','f120','f250']; res=[]
for f in NEW:
    x=P[[f]+OUT].dropna(subset=[f])
    if len(x)<14: continue
    h=len(x)//2; A,B=x.iloc[:h],x.iloc[h:]
    for o in OUT:
        ra,rb,rall=A[f].corr(A[o],method='spearman'),B[f].corr(B[o],method='spearman'),x[f].corr(x[o],method='spearman')
        res.append((f,o,len(x),rall,ra,rb,(np.sign(ra)==np.sign(rb)) and min(abs(ra),abs(rb))>=0.3))
S=pd.DataFrame(res,columns=['factor','outcome','n','r_all','r_first','r_second','pass'])
print('\ntests',len(S),'passed',int(S['pass'].sum()),'chance ~',round(len(S)*0.06,1)); print(S[S['pass']].round(2).to_string(index=False))
print(S.pivot(index='factor',columns='outcome',values='r_all').round(2).to_string())
for nm,mk in (('EPS減少中 eps6<0',P.eps6<0),('EPS前年比マイナス',P.epsg<0),('EPS二桁増 epsg>=10',P.epsg>=10),('CAPE>=30',P.cape>=30),('CAPE<20',P.cape<20),('益回り-金利<0 erp<0',P.erp<0),('AAII弱気優勢(T) spread<=-10',P.aaii_T<=-10),('AAII強気優勢(高値時)>=+20',P.aaii_pk>=20),('信用買い残 前年比>=+20%',P.md_yoy>=20),('信用買い残 前年比<0',P.md_yoy<0),('MMF急増 mm13>=3%',P.mm13>=3)):
    a_,b_=P[mk],P[~mk & mk.notna()]
    print(f"{nm:26s} yes n={len(a_):2d} more中央値 {a_.more.median():6.1f} P(-10%超) {(a_.more<=-10).mean()*100:3.0f}% f120中央値 {a_.f120.median():5.1f} f250 {a_.f250.median():5.1f} 景気後退 {a_.rec12.mean()*100:3.0f}% | no n={len(b_):2d} {b_.more.median():6.1f} {(b_.more<=-10).mean()*100:3.0f}% {b_.f120.median():5.1f} {b_.f250.median():5.1f} {b_.rec12.mean()*100:3.0f}%")
print('latest: AAII',a.iloc[-1].round(1).to_dict(),'| margin debt',md.index[-1].date(),md.iloc[-1],'yoy',round((md.iloc[-1]/md.iloc[-13]-1)*100,1),'| UMich',um.iloc[-1],'| PE',pe.iloc[-1],'CAPE',cape.iloc[-1],'| EPS',eps.iloc[-1],'yoy',round((eps.iloc[-1]/eps.iloc[-13]-1)*100,1),'| retail MMF 13w',round((mm.iloc[-1]/mm.iloc[-14]-1)*100,1))
