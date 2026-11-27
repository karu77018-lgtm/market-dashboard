import pandas as pd, numpy as np, warnings
from multiprocessing import Pool
from features import features
warnings.filterwarnings('ignore')
px=pd.read_pickle('px.pkl')
def run(t):
    try:
        f=features(px[t]); f['tk']=t
        for col in f.columns:
            if f[col].dtype==np.float64: f[col]=f[col].astype(np.float32)
        return f
    except Exception as e:
        return None
if __name__=='__main__':
    with Pool(2) as p: res=p.map(run, list(px.keys()), chunksize=20)
    df=pd.concat([r for r in res if r is not None])
    df.index.name='date'; df=df.reset_index()
    df.to_parquet('feat.parquet'); print(df.shape)
