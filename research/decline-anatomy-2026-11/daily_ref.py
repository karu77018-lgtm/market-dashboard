"""Weekly market-state vectors 1999-2026 for 'which year does today look like' + validation."""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
rd=lambda n: pd.read_csv(f'macro/{n}.csv',parse_dates=['date']).drop_duplicates('date').set_index('date')['close']
q=rd('NDX'); idx=q.loc['1998-01-01':].index
S={k:rd(k).reindex(idx.union(rd(k).index)).ffill().reindex(idx) for k in ('GSPC','RUT','SOX','VIX','TNX','DXY','JPY','TLT','GOLD','OIL','RSP','IWF','IWD','SPY','XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB')}
q=q.reindex(idx)
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna(); baa=baa.reindex(idx.union(baa.index)).ffill().reindex(idx)
SEC=['XLK','XLF','XLE','XLP','XLU','XLV','XLY','XLI','XLB']
def ch(s,n=63): return (s/s.shift(n)-1)*100
F=pd.DataFrame(index=idx)
F['dd']=(q/q.rolling(252,min_periods=200).max()-1)*100
F['r63']=ch(q); F['r252']=ch(q,252); F['v200']=(q/q.rolling(200).mean()-1)*100
F['rv20']=q.pct_change().rolling(20).std()*np.sqrt(252)*100
F['vix']=S['VIX']
F['sox']=ch(S['SOX'])-F.r63; F['spx']=ch(S['GSPC'])-F.r63; F['small']=ch(S['RUT'])-ch(S['GSPC'])
F['eqw']=ch(S['RSP'])-ch(S['SPY']); F['gv']=ch(S['IWF'])-ch(S['IWD'])
F['dfn']=(ch(S['XLP'])+ch(S['XLU']))/2-ch(S['SPY']); F['fin']=ch(S['XLF'])-ch(S['SPY']); F['ene']=ch(S['XLE'])-ch(S['SPY'])
F['sec50']=sum((S[s]>S[s].rolling(50).mean()).astype(float).where(S[s].rolling(50).mean().notna()) for s in SEC)
F['d10']=(S['TNX']-S['TNX'].shift(63))*100; F['cred']=(baa-baa.shift(63))*100; F['usd']=ch(S['DXY'])
for h in (20,60,120,250): F[f'f{h}']=(q.shift(-h)/q-1)*100
W=F.loc['1999-06-01':].resample('W-FRI').last().dropna(subset=['dd','r63','vix','spx'])
W.to_pickle('weekly_state.pkl'); print(W.shape, W.index[0].date(), W.index[-1].date()); print(W.iloc[-1].round(1).to_dict())
