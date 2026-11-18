"""Which alerts lead the entry gate turning off (QQQ closes below its 200-day average)?  Local study, not run in CI.

An alert counts when it first fires (after 20 quiet sessions) while the gate is still on.  For each alert:
- prec: share of firings followed by the gate turning off within H sessions (vs base: any gate-on day)
- recall: share of gate-off turns that had a firing in the H sessions before
- lead: median sessions from firing to the gate turning off
- dd: share of firings followed by a QQQ fall of 7%+ from that close within H sessions (vs base)
Halves: 2014-2019 and 2020-2026.
"""
import json
import sys
import pandas as pd
import numpy as np

BT = "/home/claude/bt"
MD = "/home/claude/md"
H = 40
x = pd.read_csv(f"{BT}/x_QQQ_full.csv", parse_dates=["date"], index_col="date").close
gate = x > x.rolling(200).mean()
idx = x.loc["2014-01-01":"2026-11-13"].index
gate = gate.reindex(idx)
q = x.reindex(idx)

# gate-off turns after 20 sessions on
on20 = gate.rolling(20).sum() == 20
off_turn = (~gate) & on20.shift(1).fillna(False)
turns = list(idx[off_turn.values])
fut_min = pd.Series([q.iloc[i + 1:i + 1 + H].min() if i + 1 < len(q) else np.nan for i in range(len(q))], index=idx)
dd7 = (fut_min / q - 1) <= -0.07
turn_pos = np.array([idx.get_loc(t) for t in turns])


def next_off(i):
    later = turn_pos[turn_pos > i]
    return later[0] - i if len(later) else None


def firings(cond: pd.Series) -> list[int]:
    cond = cond.reindex(idx).fillna(False).astype(bool).values
    out, quiet = [], 20
    for i, c in enumerate(cond):
        if c and quiet >= 20:
            out.append(i)
        quiet = 0 if c else quiet + 1
    return out


def evaluate(name, cond):
    f = firings(cond)
    rows = []
    for lo, hi in (("2014", "2019"), ("2020", "2026")):
        fi = [i for i in f if lo <= str(idx[i].year) <= hi and gate.iloc[i]]
        base_days = [i for i in range(len(idx) - H) if lo <= str(idx[i].year) <= hi and gate.iloc[i]]
        lead = [next_off(i) for i in fi]
        hit = [l for l in lead if l is not None and l <= H]
        base = np.mean([(next_off(i) or 999) <= H for i in base_days])
        tp = [p for p in turn_pos if lo <= str(idx[p].year) <= hi]
        rec = np.mean([any(0 < p - i <= H for i in fi) for p in tp]) if tp else np.nan
        d = np.mean([dd7.iloc[i] for i in fi]) if fi else np.nan
        db = dd7.iloc[base_days].mean()
        rows.append(f"{lo}-{hi}: n={len(fi):2d} prec={len(hit) / max(len(fi), 1):.0%} (base {base:.0%}) "
                    f"recall={rec:.0%} of {len(tp)} lead={int(np.median(hit)) if hit else '-'} dd7={d:.0%} (base {db:.0%})")
    print(f"{name:28s} | " + " | ".join(rows))


sys.path.insert(0, f"{MD}/scripts")
F = pd.read_pickle(f"{BT}/fseries.pkl")
hlth = pd.read_pickle(f"{BT}/health.pkl")
mc = json.load(open(f"{MD}/market-history/mc57-10y.json"))
pulse = pd.Series(mc["series"]["MC57"], index=pd.to_datetime(mc["dates"]))
spx = pd.read_csv(f"{BT}/macro/GSPC.csv", parse_dates=["date"], index_col="date").close
vix = pd.read_csv(f"{BT}/x_VIX.csv", parse_dates=["date"], index_col="date").close
nf = pd.read_csv(f"{BT}/macro/F_NFCI.csv", parse_dates=[0], index_col=0).iloc[:, -1]
sphb = pd.Series(dict(json.load(open(f"{BT}/ext3/SPHB.json")))); sphb.index = pd.to_datetime(sphb.index)
splv = pd.Series(dict(json.load(open(f"{BT}/ext3/SPLV.json")))); splv.index = pd.to_datetime(splv.index)
gv = pd.Series(dict(json.load(open(f"{BT}/ext3/GVIP.json")))); gv.index = pd.to_datetime(gv.index)
spy = pd.Series(dict(json.load(open(f"{BT}/ext3/SPY.json")))); spy.index = pd.to_datetime(spy.index)

print(f"gate-off turns 2014-2026: {len(turns)}  H={H}")
evaluate("QQQ < 50日線 (参考)", x < x.rolling(50).mean())
evaluate("F1 >= 注意", F.f1 >= 0.20)
evaluate("F1 >= 警戒", F.f1 >= 0.30)
evaluate("F2 >= 注意", F.f2 >= 0.25)
evaluate("F2 >= 警戒", F.f2 >= 0.40)
evaluate("F3 >= 注意", F.f3 >= 0.40)
evaluate("F3 >= 警戒", F.f3 >= 0.60)
evaluate("ブレイク成功度 不調", hlth.hv < 0)
evaluate("地合いスコア < 40", pulse < 40)
evaluate("地合いスコア < 30", pulse < 30)
dd_spx = spx / spx.rolling(252, min_periods=50).max() - 1
evaluate("S&P -5% & VIX>=23", (dd_spx <= -0.05) & (vix.reindex(spx.index).ffill() >= 23))
evaluate("VIX >= 25", vix >= 25)
nfd = nf.resample("D").ffill()
evaluate("NFCI 4週で上昇", (nfd - nfd.shift(28)) > 0.05)
r = (sphb / splv.reindex(sphb.index).ffill())
evaluate("SPHB/SPLV 20日 -5%", r / r.shift(20) - 1 <= -0.05)
g = gv / spy.reindex(gv.index).ffill()
evaluate("GVIP/SPY 20日 -4%", g / g.shift(20) - 1 <= -0.04)
