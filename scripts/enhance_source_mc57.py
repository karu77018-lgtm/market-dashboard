#!/usr/bin/env python3
"""Add independent candle shards without changing the recovered dashboard layout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

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
    ap.add_argument("--session", required=True)
    args = ap.parse_args()
    html_path, csv_path, chart_dir = Path(args.html), Path(args.ohlcv), Path(args.chart_dir)
    frame = pd.read_csv(csv_path, usecols=["ticker", "date", "open", "high", "low", "close", "volume"])
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame[frame["date"].notna() & (frame["date"] <= pd.Timestamp(args.session))]
    meta = write_candle_shards(frame, chart_dir, args.session)

    text = html_path.read_text(encoding="utf-8")
    spark = '<div id="dov-spark" class="dov-spark empty"></div>'
    if spark not in text:
        raise RuntimeError("ticker detail spark anchor not found")
    text = text.replace(spark, spark + '<div id="mc57-candle" class="mc57-candle"><div class="mc57-candle-msg">銘柄をタップするとローソク足を表示します。</div></div>', 1)
    text = text.replace('</head>', STYLE + '</head>', 1)
    text = text.replace('</body>', SCRIPT + '</body>', 1)
    html_path.write_text(text, encoding="utf-8")
    print(json.dumps({"session_date": args.session, "ticker_count": meta["ticker_count"],
                      "layout": "recovered-original",
                      "candle_route": "independent sharded JSON"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
