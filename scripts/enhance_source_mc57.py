#!/usr/bin/env python3
"""Add breadth cards and independent candle shards to the recovered dashboard."""
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
    return '<div class="dax mc57-breadth-axis" aria-label="日付軸">' + ''.join(
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
.mc57-candle{margin:2px 0 12px;border:1px solid #d8d6cd;border-radius:9px;background:#f8f7f3;padding:8px;min-height:300px;box-sizing:border-box}
.mc57-candle-h{display:flex;justify-content:space-between;align-items:center;font-size:10px;color:#565243;margin-bottom:5px}
.mc57-candle-btns{display:flex;gap:4px}.mc57-candle-btns button{border:1px solid #c9c6bc;background:#efeee9;color:#35332e;border-radius:5px;font-size:10px;padding:3px 8px}.mc57-candle-btns button.on{background:#2457a6;color:white}
.mc57-candle svg{width:100%;height:auto;display:block}.mc57-candle-msg{height:280px;display:flex;align-items:center;justify-content:center;color:#747167;font-size:11px}
.mc57-candle-lg{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:10px;color:#565243;margin-top:4px}
.mc57-candle-lg i{display:inline-block;width:14px;height:0;border-top:2px dashed #2457a6;vertical-align:middle;margin-right:3px}
.mc57-candle-lg i.hl{border-top:2px solid #c0761a}.mc57-candle-lg i.z{height:8px;border:0;background:rgba(35,130,77,.22)}
.mc57-candle-lg b{color:#1f6b3f}
.dov-spark{cursor:pointer}
.dov-spark.mini{height:26px!important;padding:0 9px!important;overflow:hidden}
.dov-spark.mini>*:not(.lbl){display:none!important}
.dov-spark .lbl::after{content:' ▾';color:#8a877d}
.dov-spark.mini .lbl::after{content:' ▸ タップで表示';font-weight:600;color:#8a877d}
.mc57-breadth-axis{border-top:1px solid #cbc8bd;margin-top:4px;padding:8px 2px 1px;color:#575242;font-size:12px;font-weight:650;line-height:1;font-variant-numeric:tabular-nums}
</style>'''

SCRIPT = r'''
<script id="mc57-candle-script">
(function(){
var IDX=null,SH={},BARS={},RANGE=65,ST=null,CUR=null;
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function money(v){return '$'+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
function stLoad(){if(ST)return Promise.resolve(ST);return fetch('chart-data/structure.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():{}}).catch(function(){return {}}).then(function(x){ST=x||{};return ST})}
function chart(tk,n){var el=document.getElementById('mc57-candle');if(!el)return;var a=(BARS[tk]||[]).slice(-n);if(!a.length){el.innerHTML='<div class="mc57-candle-msg">ローソク足データなし</div>';return;}
var s=(ST||{})[tk];var W=Math.max(300,Math.round((el.clientWidth||656)-16)),H=Math.round(Math.min(340,Math.max(240,W*.62))),L=6,R=58,T=10,B=18;
var hi=Math.max.apply(null,a.map(function(x){return x[2]})),lo=Math.min.apply(null,a.map(function(x){return x[3]}));
if(s){hi=Math.max(hi,s.line);lo=Math.min(lo,s.hl)}
var span=(hi-lo)||1,bw=(W-L-R)/a.length,cw=Math.max(1,Math.min(7,bw*.66)),z=[],tags=[];
function y(v){return T+(hi-v)/span*(H-T-B)}
function xi(d){if(d<a[0][0])return -1;for(var i=0;i<a.length;i++){if(a[i][0]>=d)return i}return -1}
if(s){var hx=xi(s.hld),lx=xi(s.lld),x0=L+(Math.max(lx,0))*bw,xh=L+(Math.max(hx,0))*bw,xe=W-R;
var z0=s.hl+(s.line-s.hl)*.5,z1=s.hl+(s.line-s.hl)*.75;
z.push('<rect x="'+xh.toFixed(1)+'" y="'+y(z1).toFixed(1)+'" width="'+(xe-xh).toFixed(1)+'" height="'+(y(z0)-y(z1)).toFixed(1)+'" fill="rgba(35,130,77,.16)"/>');
z.push('<text x="'+(xh+3).toFixed(1)+'" y="'+((y(z0)+y(z1))/2+3).toFixed(1)+'" font-size="9" font-weight="700" fill="#1f6b3f">好位置</text>');
z.push('<line x1="'+x0.toFixed(1)+'" y1="'+y(s.line).toFixed(1)+'" x2="'+xe+'" y2="'+y(s.line).toFixed(1)+'" stroke="#2457a6" stroke-width="1.4" stroke-dasharray="5 3"/>');
tags.push([y(s.line),money(s.line),'#2457a6',400]);
z.push('<line x1="'+xh.toFixed(1)+'" y1="'+y(s.hl).toFixed(1)+'" x2="'+xe+'" y2="'+y(s.hl).toFixed(1)+'" stroke="#c0761a" stroke-width="1.4"/>');
tags.push([y(s.hl),money(s.hl),'#c0761a',400]);
if(lx>=0)z.push('<text x="'+(L+(lx+.5)*bw).toFixed(1)+'" y="'+Math.min(H-B+11,y(s.ll)+12).toFixed(1)+'" text-anchor="middle" font-size="9.5" font-weight="700" fill="#6f6c62">LL</text>');
if(hx>=0)z.push('<text x="'+(L+(hx+.5)*bw).toFixed(1)+'" y="'+Math.min(H-B+11,y(s.hl)+12).toFixed(1)+'" text-anchor="middle" font-size="9.5" font-weight="700" fill="#c0761a">HL</text>')}
for(var i=0;i<a.length;i++){var x=L+(i+.5)*bw,o=y(a[i][1]),h=y(a[i][2]),l=y(a[i][3]),c=y(a[i][4]),up=a[i][4]>=a[i][1],col=up?'#239a55':'#c64e4e';z.push('<line x1="'+x.toFixed(1)+'" y1="'+h.toFixed(1)+'" x2="'+x.toFixed(1)+'" y2="'+l.toFixed(1)+'" stroke="'+col+'"/>');z.push('<rect x="'+(x-cw/2).toFixed(1)+'" y="'+Math.min(o,c).toFixed(1)+'" width="'+cw.toFixed(1)+'" height="'+Math.max(1,Math.abs(c-o)).toFixed(1)+'" fill="'+col+'"/>')}
var last=a[a.length-1][4];tags.push([y(last),money(last),'#1c1b19',700]);
tags.sort(function(p,q){return p[0]-q[0]});for(var k=1;k<tags.length;k++){if(tags[k][0]-tags[k-1][0]<11)tags[k][0]=tags[k-1][0]+11}
for(var k2=0;k2<tags.length;k2++){z.push('<text x="'+(W-R+3)+'" y="'+(tags[k2][0]+3).toFixed(1)+'" font-size="9.5" font-weight="'+tags[k2][3]+'" fill="'+tags[k2][2]+'">'+tags[k2][1]+'</text>')}
var d0=a[0][0].slice(2,7).replace('-','/'),d1=a[a.length-1][0].slice(2,7).replace('-','/');
var lg='';if(s){var pos=(last-s.hl)/(s.line-s.hl);var ptxt=(last>s.line)?'ライン上抜け':(last<s.hl?'HL割れ':'位置 '+Math.round(pos*100)+'%'+((pos>=.5&&pos<=.75)?' <b>好位置</b>':''));lg='<div class="mc57-candle-lg"><span><i></i>ライン</span><span><i class="hl"></i>HL（割れたら崩れ）</span><span><i class="z"></i>好位置 50〜75%</span><span>'+ptxt+'</span></div>'}
else{lg='<div class="mc57-candle-lg"><span>HL構造なし（安値の切り上げ未確認）</span></div>'}
el.innerHTML='<div class="mc57-candle-h"><b>'+esc(tk)+' ローソク足</b><span class="mc57-candle-btns"><button data-n="65">3M</button><button data-n="130">6M</button><button data-n="260">1Y</button></span></div><svg viewBox="0 0 '+W+' '+H+'">'+z.join('')+'<text x="'+L+'" y="'+(H-3)+'" font-size="9.5" fill="#747167">'+d0+'</text><text x="'+(W-R)+'" y="'+(H-3)+'" text-anchor="end" font-size="9.5" fill="#747167">'+d1+'</text></svg>'+lg;var bs=el.querySelectorAll('button');for(var j=0;j<bs.length;j++){if(+bs[j].getAttribute('data-n')===n)bs[j].classList.add('on');bs[j].onclick=function(){RANGE=+this.getAttribute('data-n');chart(tk,RANGE)}}}
function load(tk){CUR=tk;var el=document.getElementById('mc57-candle');if(!el)return;el.innerHTML='<div class="mc57-candle-msg">ローソク足を読み込み中…</div>';var p=IDX?Promise.resolve(IDX):fetch('chart-data/index.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw Error(r.status);return r.json()}).then(function(x){IDX=x;return x});Promise.all([p.then(function(x){var s=x.ticker_to_shard[tk];if(s===undefined)throw Error('ticker');if(SH[s])return SH[s];return fetch('chart-data/shard-'+String(s).padStart(2,'0')+'.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw Error(r.status);return r.json()}).then(function(q){SH[s]=q;return q})}),stLoad()]).then(function(r){BARS[tk]=r[0][tk]||[];if(CUR===tk)chart(tk,RANGE)}).catch(function(){el.innerHTML='<div class="mc57-candle-msg">ローソク足を取得できませんでした。再度開いてください。</div>'})}
function sparkPref(){try{return localStorage.getItem('mc57_spark_open')==='1'}catch(e){return false}}
function sparkSetup(){var sp=document.getElementById('dov-spark');if(!sp)return;if(!sparkPref())sp.classList.add('mini');else sp.classList.remove('mini');if(!sp.getAttribute('data-tg')){sp.setAttribute('data-tg','1');sp.addEventListener('click',function(e){e.stopPropagation();var open=sp.classList.toggle('mini')?false:true;try{localStorage.setItem('mc57_spark_open',open?'1':'0')}catch(x){}})}}
var old=window.showDet;if(typeof old==='function'){window.showDet=function(tk){old(tk);sparkSetup();load(tk)}}
})();
</script>'''


def substitute_badge(text: str, manifest_path: Path) -> str:
    """Mark the page when part of today's data came from Massive instead of Yahoo."""
    try:
        status = json.loads(manifest_path.read_text(encoding="utf-8")).get("provider_status") or {}
    except Exception:
        return text
    sub = status.get("yahoo_substitute")
    if not sub or 'id="mc57-substitute"' in text:
        return text
    parts = []
    if sub.get("session_calendar"):
        parts.append("営業日判定")
    if sub.get("stock_bars_massive"):
        parts.append(f"個別{int(sub['stock_bars_massive']):,}銘柄")
    if sub.get("mc57_etfs_massive"):
        parts.append(f"MC57 ETF {len(sub['mc57_etfs_massive'])}本")
    market = sub.get("market_inputs") or {}
    if market.get("massive") or market.get("tradingview"):
        parts.append(f"市場指標{len(market.get('massive', [])) + len(market.get('tradingview', []))}本")
    detail = "・".join(parts) or "一部"
    badge = ('<span id="mc57-substitute" title="Yahoo取得失敗のため当日分をMassive（分割調整・配当未調整）'
             '等で代替" style="margin-left:8px;padding:1px 6px;border-radius:6px;font-size:11px;'
             'font-weight:700;background:#fff3cd;color:#7a5200;border:1px solid #e6c46a">'
             f'Massive代替：{detail}</span>')
    anchor = '</div></header>'
    return text.replace(anchor, badge + anchor, 1) if anchor in text else text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    ap.add_argument("--ohlcv", default="work/ohlcv.csv")
    ap.add_argument("--chart-dir", default="chart-data")
    ap.add_argument("--session", required=True)
    ap.add_argument("--themes", default="data/theme_membership.json")
    args = ap.parse_args()
    html_path, csv_path, chart_dir = Path(args.html), Path(args.ohlcv), Path(args.chart_dir)
    frame = pd.read_csv(csv_path, usecols=["ticker", "date", "open", "high", "low", "close", "volume"])
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame[frame["date"].notna() & (frame["date"] <= pd.Timestamp(args.session))]
    cards = breadth_cards(frame)
    meta = write_candle_shards(frame, chart_dir, args.session)
    from swing_screener import write_structure
    try:
        print(f"candle structure overlay: {write_structure(frame, chart_dir / 'structure.json')} tickers", flush=True)
    except Exception as exc:  # display-only
        print(f"candle structure overlay skipped: {exc!r}", flush=True)

    text = html_path.read_text(encoding="utf-8")
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
    from market_internals_ui import apply_html
    text = apply_html(text, html_path.resolve().parent)
    from dashboard_fixes import apply
    text = apply(text, html_path.resolve().parent)
    from theme_gate import apply as apply_theme_gate
    text = apply_theme_gate(text, frame, Path(args.themes))
    from swing_screener import apply as apply_swing_screener
    from options_walls import fetch_walls
    from swing_screener import regime_from_market
    regime = regime_from_market(html_path.resolve().parent / "data" / "market_inputs.json", args.session)
    import breakout_health
    try:
        health = breakout_health.compute(frame)
        print(f"breakout health: {None if not health else health['value']} ({None if not health else health['n']} signals)", flush=True)
    except Exception as exc:  # display-only
        print(f"breakout health skipped: {exc!r}", flush=True)
        health = None
    text = breakout_health.apply_daily(text, health, regime)
    from pickup_watch import apply as apply_pickup_watch
    text = apply_pickup_watch(text, frame, regime=regime)  # separate watch card, below the swing card
    text = apply_swing_screener(text, frame, walls_fn=fetch_walls, regime=regime, health=health)
    import putwall_touch
    text = putwall_touch.apply(text, frame)  # Setups card fed by the walls fetched above
    from rules_tab import apply as apply_rules_tab
    text = apply_rules_tab(text, regime=regime, health=health)
    import track_record
    try:  # display + ledger only; never blocks publication
        text = track_record.run(text, frame, args.session, html_path.resolve().parent)
    except Exception as exc:
        print(f"track record skipped: {exc!r}", flush=True)
    import audit_display
    text = audit_display.apply(text, html_path.resolve().parent, args.session)
    from archive_tab import apply as apply_archive_tab
    text = apply_archive_tab(text)  # Core 12 / old W30 rule -> アーカイブ tab (display only)
    from rotation_split import apply as apply_rotation_split
    text = apply_rotation_split(text)  # Rotation -> Rotation (資金の流れ) + Themes (display only)
    text = substitute_badge(text, html_path.resolve().parent / "latest-manifest.json")
    import design_system
    text = design_system.apply(text)  # one visual system, CSS only (last stylesheet)
    html_path.write_text(text, encoding="utf-8")
    print(json.dumps({"session_date": args.session, "ticker_count": meta["ticker_count"],
                      "cards": ["50MA participation", "52-week new highs minus new lows"],
                      "candle_route": "independent sharded JSON"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
