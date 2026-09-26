#!/usr/bin/env python3
"""Add post-2026-09-16 source-only improvements and independent candle shards."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def axis_html(dates: list[pd.Timestamp]) -> str:
    n = len(dates)
    positions = sorted({0, round((n - 1) * .25), round((n - 1) * .5),
                        round((n - 1) * .75), n - 1})
    return '<div class="dax">' + ''.join(
        f'<span>{dates[i].strftime("%y/%-m")}</span>' for i in positions
    ) + '</div>'


def svg_line(values: list[float], color: str, *, zero: bool = False) -> str:
    width, height, pad = 680, 180, 7
    good = [float(v) for v in values if np.isfinite(v)]
    lo, hi = min(good), max(good)
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    margin = max((hi - lo) * .08, 1.0)
    lo, hi = lo - margin, hi + margin
    span = hi - lo or 1.0
    x = lambda i: pad + i * (width - 2 * pad) / max(1, len(values) - 1)
    y = lambda v: pad + (1 - (v - lo) / span) * (height - 2 * pad)
    pts = ' '.join(f'{x(i):.1f},{y(float(v)):.1f}' for i, v in enumerate(values))
    zero_line = ''
    if zero and lo <= 0 <= hi:
        zero_line = (f'<line x1="{pad}" y1="{y(0):.1f}" x2="{width-pad}" y2="{y(0):.1f}" '
                     'stroke="#817e73" stroke-width="1" stroke-dasharray="4 3"/>')
    return (f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">{zero_line}'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{x(len(values)-1):.1f}" cy="{y(values[-1]):.1f}" r="3.5" fill="{color}"/>'
            '</svg>')


def breadth_cards(frame: pd.DataFrame) -> str:
    close = frame.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    sma50 = close.rolling(50, min_periods=50).mean()
    valid50 = sma50.notna().sum(axis=1)
    universe = close.notna().sum(axis=1)
    pct50 = ((close > sma50).sum(axis=1) / valid50.replace(0, np.nan) * 100)
    pct50 = pct50[valid50 >= (universe * .6).clip(lower=30)].dropna().iloc[-504:]

    high52 = close.rolling(252, min_periods=252).max()
    low52 = close.rolling(252, min_periods=252).min()
    nh = ((close >= high52) & high52.notna()).sum(axis=1)
    nl = ((close <= low52) & low52.notna()).sum(axis=1)
    valid252 = high52.notna().sum(axis=1)
    ok = valid252 >= (universe * .6).clip(lower=30)
    net = (nh - nl)[ok].dropna().iloc[-504:]
    dates50, dates_net = list(pct50.index), list(net.index)
    if len(pct50) < 5 or len(net) < 5:
        raise RuntimeError("not enough history for the 50MA and 52-week breadth cards")
    return (
        '<div class="card" data-source-improvement="50ma-participation">'
        '<div class="chd"><h2>ブレッドス推移（50日線上の割合）</h2>'
        f'<div class="chd-now" style="color:#7ff0a8"><b>{pct50.iloc[-1]:.0f}%</b><span>50日線上</span></div></div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        '全銘柄のうち終値が50日移動平均線を上回る割合。短中期の買い参加の広がり。</div></details>'
        f'<div class="chart">{svg_line(pct50.tolist(), "#37b56c")}{axis_html(dates50)}</div></div>'
        '<div class="card" data-source-improvement="52week-high-low">'
        '<div class="chd"><h2>52週 新高値 − 新安値</h2>'
        f'<div class="chd-now" style="color:{"#37b56c" if net.iloc[-1] >= 0 else "#d95b5b"}">'
        f'<b>{int(net.iloc[-1]):+d}</b><span>新高値 {int(nh.loc[net.index[-1]])} / 新安値 {int(nl.loc[net.index[-1]])}</span></div></div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        '当日の52週新高値銘柄数から新安値銘柄数を引いた値。0より上は内部拡大、下は内部悪化。</div></details>'
        f'<div class="chart">{svg_line(net.astype(float).tolist(), "#c65b55", zero=True)}{axis_html(dates_net)}</div></div>'
    )


def _num(value, digits: int = 2, signed: bool = False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(number):
        return "—"
    return f"{number:+.{digits}f}" if signed else f"{number:.{digits}f}"


def provider_cards(payload: dict) -> str:
    massive = payload.get("massive", {})
    structure = massive.get("market_structure", {})
    if structure.get("status") != "READY":
        raise RuntimeError("Massive market structure is not READY")
    advances = int(structure.get("advances", 0))
    declines = int(structure.get("declines", 0))
    ad_net = int(structure.get("advance_decline_net", 0))
    four_net = int(structure.get("four_pct_net", 0))
    ud_ratio = _num(structure.get("up_down_volume_ratio"), 2)
    compared = int(structure.get("compared_tickers", 0))
    cross = massive.get("cross_vendor", {})
    cross_pct = _num(float(cross.get("coverage", 0)) * 100, 1)

    fred = payload.get("fred", {})
    series = fred.get("series", {})
    hy = series.get("BAMLH0A0HYM2", {})
    real10 = series.get("DFII10", {})
    be10 = series.get("T10YIE", {})
    curve = series.get("T10Y2Y", {})
    nfci = series.get("NFCI", {})
    fred_status = str(fred.get("status", "ERROR"))
    fred_coverage = _num(float(fred.get("required_coverage", 0)) * 100, 0)
    fred_latest = max(
        (str(row.get("last_date")) for row in series.values() if row.get("last_date")),
        default="—",
    )
    return (
        '<div class="card" data-source-improvement="massive-market-structure">'
        '<div class="chd"><h2>全市場 内部構造（Massive）</h2>'
        f'<div class="chd-now" style="color:{"#37b56c" if ad_net >= 0 else "#d95b5b"}">'
        f'<b>{ad_net:+d}</b><span>上昇 {advances:,} / 下落 {declines:,}</span></div></div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        f'比較対象 {compared:,}銘柄。騰落差は上昇銘柄数−下落銘柄数。4%以上騰落差 {four_net:+d}、'
        f'上昇/下落出来高比 {ud_ratio}倍。Yahooとの当日終値照合率 {cross_pct}%です。'
        '</div></details></div>'
        '<div class="card" data-source-improvement="fred-macro-risk">'
        '<div class="chd"><h2>金利・信用環境（FRED）</h2>'
        f'<div class="chd-now" style="color:{"#d95b5b" if float(hy.get("last_value") or 0) >= 5 else "#6e6a5e"}">'
        f'<b>{_num(hy.get("last_value"), 2)}%</b><span>米HY OAS</span></div></div>'
        '<details class="cxpl" open><summary>公式系列</summary><div class="cxpl-b">'
        f'10年実質金利 {_num(real10.get("last_value"), 2)}% / 10年期待インフレ {_num(be10.get("last_value"), 2)}% / '
        f'10年−2年差 {_num(curve.get("last_value"), 2, signed=True)}%pt / NFCI {_num(nfci.get("last_value"), 2, signed=True)}。'
        f'状態 {fred_status}、必須系列 {fred_coverage}%、最新観測日 {fred_latest}。'
        '</div></details></div>'
    )


def write_candle_shards(frame: pd.DataFrame, out_dir: Path, session: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    shards: dict[int, dict[str, list[list]]] = {i: {} for i in range(32)}
    index: dict[str, int] = {}
    for ticker, group in frame.sort_values("date").groupby("ticker", sort=True):
        rows = []
        for r in group.tail(260).itertuples(index=False):
            values = [r.date.strftime("%Y-%m-%d"), r.open, r.high, r.low, r.close, r.volume]
            if any(pd.isna(v) for v in values[1:5]):
                continue
            rows.append([values[0], round(float(values[1]), 4), round(float(values[2]), 4),
                         round(float(values[3]), 4), round(float(values[4]), 4),
                         int(values[5]) if pd.notna(values[5]) else None])
        if not rows:
            continue
        shard = int(hashlib.sha256(str(ticker).encode()).hexdigest()[:8], 16) % 32
        shards[shard][str(ticker)] = rows
        index[str(ticker)] = shard
    for number, payload in shards.items():
        (out_dir / f"shard-{number:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    meta = {"schema": "source-mc57.candles.1", "session_date": session,
            "max_bars_per_ticker": 260, "ticker_count": len(index), "shard_count": 32,
            "ticker_to_shard": index}
    (out_dir / "index.json").write_text(
        json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return meta


STYLE = r'''
<style id="mc57-candle-style">
.mc57-candle{margin:2px 0 12px;border:1px solid #d8d6cd;border-radius:9px;background:#f8f7f3;padding:8px;min-height:178px;box-sizing:border-box}
.mc57-candle-h{display:flex;justify-content:space-between;align-items:center;font-size:10px;color:#565243;margin-bottom:5px}
.mc57-candle-btns{display:flex;gap:4px}.mc57-candle-btns button{border:1px solid #c9c6bc;background:#efeee9;color:#35332e;border-radius:5px;font-size:9px;padding:2px 6px}.mc57-candle-btns button.on{background:#2457a6;color:white}
.mc57-candle svg{width:100%;height:145px;display:block}.mc57-candle-msg{height:145px;display:flex;align-items:center;justify-content:center;color:#747167;font-size:11px}
</style>'''

SCRIPT = r'''
<script id="mc57-candle-script">
(function(){
var IDX=null,SH={},BARS={},RANGE=90;
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function chart(tk,n){var el=document.getElementById('mc57-candle');if(!el)return;var a=(BARS[tk]||[]).slice(-n);if(!a.length){el.innerHTML='<div class="mc57-candle-msg">ローソク足データなし</div>';return;}
var W=640,H=145,L=9,R=9,T=8,B=18,hi=Math.max.apply(null,a.map(function(x){return x[2]})),lo=Math.min.apply(null,a.map(function(x){return x[3]})),span=(hi-lo)||1,bw=(W-L-R)/a.length,cw=Math.max(1,Math.min(5,bw*.64)),z=[];
function y(v){return T+(hi-v)/span*(H-T-B)}
for(var i=0;i<a.length;i++){var x=L+(i+.5)*bw,o=y(a[i][1]),h=y(a[i][2]),l=y(a[i][3]),c=y(a[i][4]),up=a[i][4]>=a[i][1],col=up?'#239a55':'#c64e4e';z.push('<line x1="'+x.toFixed(1)+'" y1="'+h.toFixed(1)+'" x2="'+x.toFixed(1)+'" y2="'+l.toFixed(1)+'" stroke="'+col+'"/>');z.push('<rect x="'+(x-cw/2).toFixed(1)+'" y="'+Math.min(o,c).toFixed(1)+'" width="'+cw.toFixed(1)+'" height="'+Math.max(1,Math.abs(c-o)).toFixed(1)+'" fill="'+col+'"/>')}
var d0=a[0][0].slice(2,7).replace('-','/'),d1=a[a.length-1][0].slice(2,7).replace('-','/');el.innerHTML='<div class="mc57-candle-h"><b>'+esc(tk)+' ローソク足</b><span class="mc57-candle-btns"><button data-n="65">3M</button><button data-n="130">6M</button><button data-n="260">1Y</button></span></div><svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+z.join('')+'<text x="'+L+'" y="'+(H-3)+'" font-size="9" fill="#747167">'+d0+'</text><text x="'+(W-R)+'" y="'+(H-3)+'" text-anchor="end" font-size="9" fill="#747167">'+d1+'</text></svg>';var bs=el.querySelectorAll('button');for(var j=0;j<bs.length;j++){if(+bs[j].getAttribute('data-n')===n)bs[j].classList.add('on');bs[j].onclick=function(){RANGE=+this.getAttribute('data-n');chart(tk,RANGE)}}}
function load(tk){var el=document.getElementById('mc57-candle');if(!el)return;el.innerHTML='<div class="mc57-candle-msg">ローソク足を読み込み中…</div>';var p=IDX?Promise.resolve(IDX):fetch('chart-data/index.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw Error(r.status);return r.json()}).then(function(x){IDX=x;return x});p.then(function(x){var s=x.ticker_to_shard[tk];if(s===undefined)throw Error('ticker');if(SH[s])return SH[s];return fetch('chart-data/shard-'+String(s).padStart(2,'0')+'.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw Error(r.status);return r.json()}).then(function(q){SH[s]=q;return q})}).then(function(q){BARS[tk]=q[tk]||[];chart(tk,RANGE)}).catch(function(){el.innerHTML='<div class="mc57-candle-msg">ローソク足を取得できませんでした。再度開いてください。</div>'})}
var old=window.showDet;if(typeof old==='function'){window.showDet=function(tk){old(tk);load(tk)}}
})();
</script>'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    ap.add_argument("--ohlcv", default="work/ohlcv.csv")
    ap.add_argument("--chart-dir", default="chart-data")
    ap.add_argument("--provider-data", default="data/provider_inputs.json")
    ap.add_argument("--session", required=True)
    args = ap.parse_args()
    html_path, csv_path, chart_dir = Path(args.html), Path(args.ohlcv), Path(args.chart_dir)
    frame = pd.read_csv(csv_path, usecols=["ticker", "date", "open", "high", "low", "close", "volume"])
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame[frame["date"].notna() & (frame["date"] <= pd.Timestamp(args.session))]
    provider = json.loads(Path(args.provider_data).read_text(encoding="utf-8"))
    cards = provider_cards(provider) + breadth_cards(frame)
    meta = write_candle_shards(frame, chart_dir, args.session)

    text = html_path.read_text(encoding="utf-8")
    # The recovered page inserts an English subtitle inside the h2, so anchor
    # before the visible Japanese title rather than assuming an immediate </h2>.
    anchor = '<div class="card"><div class="chd"><h2>売買代金 参加度（200日平均比）'
    if anchor not in text:
        raise RuntimeError("volume participation anchor not found")
    text = text.replace(anchor, cards + anchor, 1)
    spark = '<div id="dov-spark" class="dov-spark empty"></div>'
    if spark not in text:
        raise RuntimeError("ticker detail spark anchor not found")
    text = text.replace(spark, spark + '<div id="mc57-candle" class="mc57-candle"><div class="mc57-candle-msg">銘柄をタップするとローソク足を表示します。</div></div>', 1)
    text = text.replace('</head>', STYLE + '</head>', 1)
    text = text.replace('</body>', SCRIPT + '</body>', 1)
    html_path.write_text(text, encoding="utf-8")
    print(json.dumps({"session_date": args.session, "ticker_count": meta["ticker_count"],
                      "cards": ["Massive market structure", "FRED macro risk", "50MA participation", "52-week new highs minus new lows"],
                      "candle_route": "independent sharded JSON"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
