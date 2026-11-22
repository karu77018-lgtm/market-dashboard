"""Point-in-time EPS acceleration state using V38's own _eps_acceleration_from_dates (extracted verbatim)."""
import ast, json, os, sys, numpy as np, pandas as pd
# V38 build_dashboard.py (thanzo12wizu-stack/v38-watchlist); usage: eps_state.py SIGNALS.pkl TICKERS.json OUT_LABELS.pkl OUT_DETAIL.csv
SRC = os.environ.get('V38_BUILD_DASHBOARD', '../v38-watchlist/build_dashboard.py')
src = open(SRC, encoding='utf-8').read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_eps_acceleration_from_dates')
ns = dict(pd=pd, np=np, EPS_STREAK_STEP_PP=5.0, EPS_CONFIRMED_MIN_YOY=20.0, EPS_MIN_BASE=0.05, EPS_MAX_YOY_POINTS=4)
exec(compile(ast.Module([fn], []), SRC, 'exec'), ns)
eps_fn = ns['_eps_acceleration_from_dates']

SEL = pd.read_pickle(sys.argv[1])
dates = SEL.index
tick = json.load(open(sys.argv[2]))
cat = {}  # ticker -> Series of state labels on each trading date (point in time)
detail = []
for t in tick:
    p = f'eps/{t}.csv'
    lab = pd.Series('NO_DATA', index=dates, dtype=object)
    if os.path.exists(p):
        e = pd.read_csv(p)
        if len(e):
            e['date'] = pd.to_datetime(e['date'], utc=True)
            e['day'] = e['date'].dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
            e = e.drop_duplicates('day', keep='first').sort_values('day')
            for k in range(len(e)):
                hist = e.iloc[:k + 1]
                rows = pd.DataFrame({'Reported EPS': hist['eps'].to_numpy()}, index=hist['date'])
                r = eps_fn(rows)
                trend = r.get('trend')
                if trend in ('ACCEL_CONFIRMED', 'ACCEL_PERSISTENT') and r.get('low_base'):
                    trend = trend + '_LOWBASE'
                # strictly after the announcement day (conservative point in time)
                lab[dates > e['day'].iloc[k]] = trend
                detail.append((t, e['day'].iloc[k], trend, r.get('latest_yoy'), r.get('accel_streak')))
    cat[t] = lab
L = pd.DataFrame(cat).reindex(columns=SEL.columns)
pd.to_pickle(L, sys.argv[3])
pd.DataFrame(detail, columns=['ticker', 'day', 'trend', 'latest_yoy', 'streak']).to_csv(sys.argv[4], index=False)
on = L.where(SEL.to_numpy())
print(pd.Series(on.to_numpy().ravel()).value_counts().to_string())
