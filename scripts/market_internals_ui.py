#!/usr/bin/env python3
"""Persistent presentation adapter, independent from V38/NQSAR calculations.
Only documented display nodes are changed. Original CSS, cards, tabs and trading
state are untouched. Also used by the frozen generator and legacy recovery tests.
"""
from __future__ import annotations
import argparse
import html
import json
import math
import re
import hashlib
from pathlib import Path
from bs4 import BeautifulSoup
from market_history import GROUPS, LABELS, GICS

ROOT=Path(__file__).resolve().parents[1]


def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def fmt(v,suffix='%'):
    return f'{v:+.1f}{suffix}' if finite(v) else 'DATA UNAVAILABLE'


def narrative(mc57,breadth,summary):
    """No SAR/color parameter. Transparent observations, no trading instructions.
    Descriptive cutoffs: MC57<40/55, breadth<50/60; no derived score/hard gate.
    Narrow = positive 63D index return AND positive matched cap/equal spread AND
    breadth<50 (or NH-NL<0). Otherwise describe data, without inventing evidence.
    """
    score=mc57.get('mc57'); p50=breadth.get('p50'); net=breadth.get('net')
    hist=mc57.get('history',[]); slope=None
    if len(hist)>=6: slope=hist[-1]['mc57']-hist[-6]['mc57']
    weak=(finite(score) and score<40) or (finite(p50) and p50<50)
    strong=finite(score) and score>=55 and finite(p50) and p50>=60
    verdict='市場内部は弱い。' if weak else ('市場内部の広がりは良好。' if strong else '市場内部は強弱が混在。')
    inds=summary.get('indices',{}); spreads=summary.get('spread',{})
    narrow=any(finite(inds.get(a,{}).get('63')) and inds[a]['63']>0 and
               finite(spreads.get(a+'-'+b,{}).get('63')) and spreads[a+'-'+b]['63']>0
               for a,b in [('SPY','RSP'),('QQQ','QQQE')]) and (
                   (finite(p50) and p50<50) or (finite(net) and net<0))
    note='細い相場：指数は上昇、時価総額加重優位、内部の広がりは弱い' if narrow else '指数と等ウェイト、内部の広がりを併せて確認'
    parts=[verdict.rstrip('。')]
    if narrow: parts.append('広がりは乏しく、一部大型株主導の可能性')
    parts.append(f'MC57 {score:.1f} / 100' if finite(score) else 'MC57 DATA UNAVAILABLE')
    parts.append('5営業日変化 '+fmt(slope,'pt'))
    parts.append(f'50MA上 {p50:.1f}%' if finite(p50) else '50MA Breadth DATA UNAVAILABLE')
    parts.append(f'52週 新高値−新安値 {net:+.0f}' if finite(net) else '52週 High−Low DATA UNAVAILABLE')
    for name in ('SPY-RSP','QQQ-QQQE'):
        parts.append(name+' 63D差 '+fmt(spreads.get(name,{}).get('63'),'pt'))
    lead=summary.get('leading',[])
    parts.append('63D相対パフォーマンス上位：'+(' / '.join(lead) if lead else 'DATA UNAVAILABLE'))
    current=summary.get('gics',{}).get('63',{}).get('current')
    if current:
        top=sorted(current['ranks'],key=current['ranks'].get)[:3]
        parts.append('GICS11 63D上位：'+' / '.join(GICS[t] for t in top))
    else: parts.append('GICS11 DATA UNAVAILABLE')
    return {'verdict':verdict,'body':'。'.join(parts)+'。','note':note,'narrow':narrow}


def comment_card(mc,breadth,summary):
    n=narrative(mc,breadth,summary)
    score=mc.get('mc57'); score_text=f'{score:.0f}' if finite(score) else '—'
    return ('<div class="card cmt mkt20" data-internals-comment="1"><div class="mkt20-top"><div><h2>今日のマーケット</h2>'
        f'<div class="mkt20-verdict">{html.escape(n["verdict"])}</div></div><div class="mkt20-score"><b>{score_text}</b><span>MC57・市場内部</span></div></div>'
        f'<div class="mkt20-read">{html.escape(n["body"])}</div>'
        f'<div class="cmt-note cmt-{"neg" if n["narrow"] else "pos"}">{html.escape(n["note"])}</div>'
        '<details class="mkt-fold"><summary><span>数字と判定の根拠</span></summary><div class="mkt-fold-body">'
        '記述専用。内部弱い＝MC57&lt;40 または50MA上&lt;50%。広がり良好＝MC57≥55かつ50MA上≥60%。'
        '細い相場＝63D指数リターン&gt;0・対応する等ウェイトとの差&gt;0・50MA上&lt;50%または52週H−L&lt;0。'
        '主導層＝5群の63Dリターン上位。GICS＝63DのSPY対比順位。売買・配分は変更しません。'
        '<div class="mkt-post-tools"><span>市場内部 定点観測</span><button class="copybtn mkt-copy" onclick="copyBlock(event,\'mktPostText\')">コピー</button></div>'
        f'<div id="mktPostText" class="mkt-post">{html.escape(n["body"])}</div></div></details></div>')


def breakdown_panel(mc):
    scores=mc.get('metric_scores',{})
    text='<div class="mbd-h">MC57内訳（12指標 / 4グループ）</div>'
    for label,keys in GROUPS.items():
        vals=[scores.get(k) for k in keys]
        group=sum(vals)/len(vals) if all(finite(v) for v in vals) else None
        text+=f'<div class="mgrp">{label}（{len(keys)}指標）</div>'
        width=group if finite(group) else 0
        text+=(f'<div class="mrow"><span class="mk2">グループ平均</span><span class="mraw">'
               f'{f"{group:.1f}" if finite(group) else "—"}</span><span class="mbar"><i style="width:{width:.1f}%"></i></span>'
               '<span class="mpts">/100</span></div>')
        text+='<div class="mnote">'+' / '.join(html.escape(LABELS[k])+': '+(f'{scores[k]:.1f}' if finite(scores.get(k)) else 'DATA UNAVAILABLE') for k in keys)+'</div>'
    text+=('<div class="mnote">最終MC57＝12指標平均 → EMA2 → 過去3780日（最低756日）のμ・σ（前日まで）でz正規化 → '
           '100 / (1 + 3<sup>−z</sup>)。4グループを足す値ではありません。</div>')
    return text


def controls(key, *, disabled=False):
    why=('過去時点の構成銘柄を再現できないため長期化しません（現ユニバースの参考値）' if key=='unavailable' else '長期の元系列を保証できないため現表示を維持') if disabled else ''
    if disabled:
        # No nonfunctional or disabled period choices. RRG is not a time chart.
        return ''
    return ('<div class="mh-tools" data-history-key="'+key+'"><div class="mh-buttons" role="group" aria-label="表示期間">'+
        ''.join(f'<button type="button" data-window="{w}" class="{"on" if w=="2y" else ""}" aria-pressed="{"true" if w=="2y" else "false"}"'+
                (' disabled title="過去時点ユニバース未検証"' if disabled and w!='2y' else '')+f'>{w.upper()}</button>' for w in ('2y','5y','10y'))+
        '</div><span class="mh-status" aria-live="polite">'+why+'</span></div>')


def chart_card(key,title,desc):
    return (f'<div class="card mh-card" data-history-key="{key}"><div class="chd"><h2>{title}</h2></div>'+controls(key)+
        '<div class="mh-plot chart" aria-live="polite"><div class="sub">読み込み中…</div></div>'+
        f'<div class="sub">{desc}</div></div>')


def summary_card(summary,breadth):
    body='<table class="tbl mh-table"><thead><tr><th class="l">主導層</th><th>21D</th><th>63D</th></tr></thead><tbody>'
    for k in ['MAG7','Mega','Large','Mid','Small']:
        v=summary.get('leaders',{}).get(k,{})
        body+=f'<tr><td class="l">{k}</td><td>{fmt(v.get("21"))}</td><td>{fmt(v.get("63"))}</td></tr>'
    body+='</tbody></table>'
    lead=summary.get('leading',[])
    for k in ('SPY-RSP','QQQ-QQQE'):
        body+=f'<div class="kv">{k}：21D {fmt(summary.get("spread",{}).get(k,{}).get("21"),"pt")} / 63D {fmt(summary.get("spread",{}).get(k,{}).get("63"),"pt")}</div>'
    body+='<div class="sub">現在の主導層（63Dリターン上位2群）：'+(' / '.join(lead) if lead else 'DATA UNAVAILABLE')+'</div>'
    return '<div class="card" id="market-leadership-summary"><div class="chd"><h2>何が指数を支えている？ <span class="h2en">Market Leadership</span></h2></div>'+body+'</div>'


def divergence_card(summary,breadth,mc):
    n=narrative(mc,breadth,summary); b=''
    for k in ('QQQ','QQQE','SPY','RSP'):
        b+=f'<div class="kv">{k} 63D <b>{fmt(summary.get("indices",{}).get(k,{}).get("63"))}</b></div>'
    p=breadth.get('p50'); net=breadth.get('net')
    b+=f'<div class="kv">50MA Breadth <b>{f"{p:.1f}%" if finite(p) else "DATA UNAVAILABLE"}</b></div>'
    b+=f'<div class="kv">52W High−Low <b>{f"{net:+.0f}" if finite(net) else "DATA UNAVAILABLE"}</b></div>'
    b+=f'<div class="cmt-note cmt-{"neg" if n["narrow"] else "pos"}">{html.escape(n["note"])}</div>'
    return '<div class="card" id="index-internals-divergence"><div class="chd"><h2>Index / Internals Divergence</h2></div>'+b+'<div class="sub">指数と広がりの乖離を説明する観測値。売買ゲートではありません。</div></div>'


def extract_breadth(soup):
    b={}
    for sel,key in [('[data-source-improvement="50ma-participation"]','p50'),('[data-source-improvement="52week-high-low"]','net')]:
        el=soup.select_one(sel+' .chd-now b')
        if el:
            try: b[key]=float(el.get_text().replace('%','').replace(',',''))
            except ValueError: pass
    return b


def strip_color_market_text(soup):
    """Relabel NQ-only historical/control texts, never modify their behavior.
    Static Publish narratives previously tied to SAR are replaced independently.
    Script/style nodes excluded; historical documents/logs never edited.
    """
    rules=[('トレンド判定','NQ運用判定'),('今日の運用','NQ運用判定'),('現在の地合い：','現在のNQレジーム：'),('4色の地合いゲート','4色のNQ運用ゲート'),
      ('地合いの帯','NQレジームの帯'),('地合いの色','NQレジームの色'),('NQトレンド色','NQ運用レジーム'),
      ('両ETFとも地合いで露出','両ETFともNQ運用判定で露出'),('保有は地合いルール','保有はNQ運用ルール')]
    for node in list(soup.find_all(string=True)):
        if node.parent.name in ('script','style'): continue
        text=str(node)
        for a,b in rules: text=text.replace(a,b)
        text=re.sub(r'地合い(?=\s*(?:青|緑|黄|赤|Blue|Green|Yellow|Red))','NQ運用レジーム ',text)
        text=re.sub(r'地合いは(?:青|緑|黄|赤)', 'NQ運用レジーム',text)
        if text!=str(node): node.replace_with(text)


def apply_html(text,root, *, mc=None,summary=None,breadth=None):
    if 'id="market-history-script"' in text: return text
    mc=mc or json.loads((root/'data/mc57.json').read_text())
    idxpath=root/'market-history/index.json'
    idx=json.loads(idxpath.read_text()) if idxpath.exists() else {'session_date':mc['session_date'],'files':{},'summary':{}}
    summary=summary if summary is not None else idx.get('summary',{})
    soup=BeautifulSoup(text,'html.parser')
    breadth=breadth if breadth is not None else extract_breadth(soup)
    # Exact authoritative current value, complete breakdown, original panel classes.
    for panel in soup.select('#mri-bd'):
        panel.clear(); panel.append(BeautifulSoup(breakdown_panel(mc),'html.parser'))
    for el in soup.select('.banner .lab'):
        if 'マーケットステータス' in el.get_text():
            el.clear(); el.append(BeautifulSoup('マーケットステータス（MC57・市場内部）<span class="lab-en">MARKET STATUS</span><span class="tap">タップで内訳 ▾</span>','html.parser'))
    # Legacy warning lamps remain independent diagnostics, never MC57 components.
    for el in soup.select('.banner .aux .a'):
        if '警戒' in el.get_text(): el.insert(0,'補助リスク（MC57外） ')
    for card in list(soup.select('.card.cmt.mkt20')):
        # Preserve the existing five-category layout, macro/index commentary and
        # copy controls. Only conflicting conclusions and SAR-dependent prose change.
        if not card.select_one('.mkt20-read'):
            card.replace_with(BeautifulSoup(comment_card(mc,breadth,summary),'html.parser'))
            continue
        n=narrative(mc,breadth,summary)
        for el in card.select('.mkt20-verdict'): el.string=n['verdict']
        for el in card.select('.mkt20-read'): el.string=n['body']
        for el in card.select('.cmt-note'):
            el.string=n['note']
            el['class']=['cmt-note','cmt-neg' if n['narrow'] else 'cmt-pos']
        for el in card.select('.cctxt'):
            if '地合いは' in el.get_text():
                el.string=n['verdict']+' MC57 '+str(round(mc['mc57']))+'。50MA上 '+(str(breadth.get('p50'))+'%' if finite(breadth.get('p50')) else 'DATA UNAVAILABLE')+'。'
        for el in card.select('#mktPostText'):
            el.clear(); el.append(n['body'])
    strip_color_market_text(soup)
    for frame in soup.select('iframe[srcdoc]'):
        doc=BeautifulSoup(frame['srcdoc'],'html.parser'); strip_color_market_text(doc)
        # Publish narrative needs the same internal-state evidence as Daily.
        for el in doc.select('.mkt20-read'):
            el.string=narrative(mc,breadth,summary)['body']
        # Publish headline/MC57 label derives solely from MC57, never SAR.
        for el in doc.select('.state'):
            el.string=narrative(mc,breadth,summary)['verdict'].rstrip('。')
        for el in doc.select('.acc'):
            if el.get_text(strip=True) in ('強気','堅調','やや注意','警戒','中立','弱含み'):
                el.string='内部弱い' if mc['mc57']<40 else ('内部良好' if mc['mc57']>=55 else '内部混在')
        for el in doc.select('.cx'):
            if re.search(r'レジーム(?:Blue|Green|Yellow|Red)|地合いは',el.get_text()):
                el.string=narrative(mc,breadth,summary)['verdict']+' MC57 '+str(round(mc['mc57']))+'。63D上位 '+(' / '.join(summary.get('leading',[])) or 'DATA UNAVAILABLE')+'。'
        for node in list(doc.find_all(string=True)):
            if node.parent.name in ('script','style'): continue
            if 'レジーム判定' in str(node): node.replace_with(str(node).replace('レジーム判定','NQ露出上限'))
            elif '警戒灯' == str(node).strip(): node.replace_with('補助リスク（MC57外）')
        # Relabel SAR panels explicitly and remove embedded SAR prose conclusions.
        for node in list(doc.find_all(string=True)):
            if node.parent.name in ('script','style'): continue
            s=str(node)
            if re.search(r'地合いは|Blueなので|押し目を積極的に拾う',s):
                node.replace_with(narrative(mc,breadth,summary)['body'])
        frame['srcdoc']=str(doc)
    # Existing exact card structures/CSS remain; only add scoped controls/hosts.
    mappings={'マーケットステータス推移':'mc57','攻守ローテーション（一般消費財 / ディフェンシブ）':'defensive',
              'クレジット推移（HYG / IEI）':'credit','VIX期間構造':'vixterm','VIX反転シーケンス':'vixcycle'}
    for card in soup.select('.card'):
        title=card.select_one('h2'); plot=card.select_one('.chart')
        if not title or not plot: continue
        name=title.get_text(' ',strip=True)
        key=next((v for k,v in mappings.items() if name.startswith(k)),None)
        if key:
            if key=='vixcycle':
                for el in card.select('.vixwtabs,.vixleg,.zoomhint'): el.decompose()
                for el in card.select('.vixpane')[1:]: el.decompose()
                plot['class']=[c for c in plot.get('class',[]) if c!='zoomable']
                plot.attrs.pop('data-zoomstep',None)
            card['data-history-key']=key; card['class']=card.get('class',[])+['mh-existing']
            if key=='mc57': title.clear(); title.append('MC57推移')
            plot['class']=plot.get('class',[])+['mh-plot']
            plot.insert_before(BeautifulSoup(controls(key),'html.parser'))
        elif not card.select_one('.mh-tools'):
            # Charts with no audited historical constituent/source contract stay 2Y.
            is_universe=any(k in name for k in ('ブレッドス','52週','騰落ライン','売買代金','リーダー','集積'))
            if is_universe:
                reading=card.select_one('details.cxpl')
                if reading is None:
                    reading=BeautifulSoup('<details class="cxpl"><summary>読み方</summary></details>','html.parser').details
                    plot.insert_before(reading)
                if reading:
                    reading.append(BeautifulSoup('<div class="sub mh-history-note">現ユニバースの参考値。過去時点の構成を再現できないため長期履歴は表示しません。</div>','html.parser'))
    rotation=soup.select_one('#t-rotation')
    if rotation is None: raise RuntimeError('Rotation tab missing')
    added=(summary_card(summary,breadth)+chart_card('leadership','サイズ別相対推移 / Market Leadership',
        'Small=IWM / Mid=MDY / Large=SPY / Mega=XLG。選択期間開始=100。MAG7はAAPL/MSFT/NVDA/AMZN/META/GOOGL/TSLAの調整後日次リターン平均を複利化、毎日等ウェイトへリバランス。固定7社の遡及比較であり当時の主導株や指数寄与率ではありません。')+
        chart_card('concentration','Cap Weight vs Equal Weight','SPY / RSP と QQQ / QQQE。調整後終値・選択期間開始=100。')+
        chart_card('relative','時価総額加重 / 等ウェイト 相対強度','SPY÷RSP・QQQ÷QQQE。選択期間開始=100、上昇=時価総額加重優位、低下=等ウェイト優位。')+
        '<div class="card mh-card" data-history-key="gics11"><div class="chd"><h2>GICS11 Rotation Heatmap</h2></div>'+controls('gics11')+
        '<div class="mh-buttons mh-horizons" role="group" aria-label="RS期間">'+''.join(f'<button type="button" data-horizon="{h}" class="{"on" if h==63 else ""}" aria-pressed="{"true" if h==63 else "false"}">{h}D</button>' for h in (21,63,126))+'</div>'+
        '<div class="mh-plot"></div><div class="sub">11セクターの調整後リターン−SPYリターンを日次順位化（1位=上位）。同値はティッカー順。全11セクターが揃う日のみ計算。2Y日次、5Y/10Yは日次計算を5営業日間隔で表示。資金流入額ではありません。</div>'+
        '<h3>GICS11 Rank Flow</h3><div class="mh-rank-flow"></div></div>'+divergence_card(summary,breadth,mc))
    rotation.insert(0,BeautifulSoup(added,'html.parser'))
    daily=soup.select_one('#t-market')
    if daily:
        anchor=daily.select_one('.card.cmt.mkt20')
        if anchor: anchor.insert_after(BeautifulSoup(divergence_card(summary,breadth,mc).replace('id="index-internals-divergence"','id="daily-index-internals-divergence"'),'html.parser'))
        daily.append(BeautifulSoup(chart_card('indices','指数・ボラティリティ 長期推移','QQQ / SPY / TQQQ / SOXX / SOXL / VIX。選択期間開始=100。VIXは価格水準の相対比較で投資リターンではありません。'),'html.parser'))
        daily.append(BeautifulSoup(chart_card('leadership','時価総額別の強さ推移 / Market Leadership','Small=IWM / Mid=MDY / Large=SPY / Mega=XLG / MAG7=固定7社の調整後日次リターン等ウェイト合成。期間開始=100。'),'html.parser'))
        component_cards=''.join(chart_card('mc57-group-'+str(i),'MC57構成指標：'+label,'固定57ETFの有効データによる参加率・スコア（0–100）。ETF設定前は分母から除外。個別株Breadthとは別系列。') for i,label in enumerate(GROUPS))
        fold='<div class="card"><details class="cxpl" id="mc57-component-fold"><summary>MC57 12指標の推移</summary>'+component_cards+'</details></div>'
        main_mc57=daily.select_one('.mh-existing[data-history-key="mc57"]')
        if main_mc57: main_mc57.insert_after(BeautifulSoup(fold,'html.parser'))
    # Only offer complete, actually exported periods. A shorter inception series
    # is never presented as a selectable "10Y". No fetch is needed for this gate.
    def ready_file(file):
        if not file: return False
        path=root/'market-history'/file
        if not path.exists(): return False
        data=json.loads(path.read_text())
        if 'rows' in data: return data.get('status')=='READY' and bool(data['rows'])
        avail=data.get('availability',{})
        return bool(avail) and all(v.get('status')=='READY' for v in avail.values())
    for card in list(soup.select('.mh-card,.mh-existing')):
        key=card.get('data-history-key'); entry=idx.get('files',{}).get(key,{})
        allowed=[w for w in ('2y','5y','10y') if
                 (all(ready_file(entry.get(str(h),{}).get(w)) for h in (21,63,126)) if key=='gics11' else ready_file(entry.get(w)))]
        for button in list(card.select('[data-window]')):
            if button.get('data-window') not in allowed: button.decompose()
        if not allowed:
            if 'mh-card' in card.get('class',[]): card.decompose();continue
            for tool in card.select('.mh-tools'): tool.decompose()
        elif '2y' not in allowed:
            # Initial period must always be 2Y; never auto-load a longer history.
            card.decompose();continue
        if key=='gics11' and '10y' not in allowed:
            card.append(BeautifulSoup('<details class="cxpl"><summary>読み方</summary><div class="sub mh-history-note">全11セクターの10年実履歴がないため、10Yは表示しません。</div></details>','html.parser'))
    # Existing base styles unchanged byte-for-byte; new styles only .mh-* nodes.
    assets=[root/'assets/market-history.js',root/'assets/market-history.css']
    revision=hashlib.sha256(b''.join(p.read_bytes() for p in assets if p.exists())).hexdigest()[:12]
    link=soup.new_tag('link',rel='stylesheet',href='assets/market-history.css?v='+revision); link['id']='market-history-style'; soup.head.append(link)
    config=soup.new_tag('script',id='market-history-config',type='application/json')
    config.string=json.dumps({'session_date':mc['session_date'],'files':idx.get('files',{})},ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'); soup.body.append(config)
    script=soup.new_tag('script',src='assets/market-history.js?v='+revision,id='market-history-script'); script['defer']=''; soup.body.append(script)
    # Preserve the frozen generator's exact anchor consumed by the Jev adapter.
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


def install(module,root,data_dir):
    """Generator hook: narrative code never sees SAR. Trading functions untouched."""
    mc=json.loads((data_dir/'mc57.json').read_text())
    p=root/'market-history/index.json'; idx=json.loads(p.read_text()) if p.exists() else {}
    original_spark=getattr(module,'_spark',None)
    if original_spark:
        def spark(vals,asof=None,days=60,color='#6f93c9'):
            # Same observations and cutoff as the legacy renderer: display only.
            output=original_spark(vals,asof,days,color)
            if not output: return output
            import pandas as pd
            pairs=list(vals or [])
            if asof is not None:
                cutoff=pd.Timestamp(asof).date()
                pairs=[(d,v) for d,v in pairs if pd.Timestamp(d).date()<=cutoff]
            pairs=pairs[-days:]
            labels=[pd.Timestamp(pairs[round((len(pairs)-1)*p)][0]).strftime('%y/%m/%d') for p in (0,.5,1)]
            return output+'<div class="mh-spark-axis" aria-label="日付軸">'+''.join('<span>'+d+'</span>' for d in labels)+'</div>'
        module._spark=spark
    original_comment=getattr(module,'_market_comment',None)
    original_categories=getattr(module,'build_categorized_commentary',None)
    def comment(aux,mkt,sar,breadth,cat_html=''):
        if original_comment is not None:
            # Neutral input prevents NQSAR from entering commentary generation.
            return original_comment(aux,mkt,(None,None),breadth,cat_html)
        return comment_card(mc,{'p50':breadth.get('pa50')},idx.get('summary',{}))
    def categories(mkt,m,breadth,sar,aux):
        return original_categories(mkt,m,breadth,(None,None),aux) if original_categories else ''
    module._market_comment=comment
    module.build_categorized_commentary=categories
    # Display-only export from the unchanged native VIX model. Its 1990 monthly
    # calibration, EVENT rules and LWMA/state calculations remain authoritative.
    original_cycle=getattr(module,'build_vix_cycle',None)
    original_cycle_card=getattr(module,'_vix_cycle_card',None)
    if original_cycle and original_cycle_card:
        records_by_context={}
        def cycle(*args,**kwargs):
            requested=kwargs.get('lookback',getattr(module,'VIX_CYCLE_SPARK_DAYS',60))
            if len(args)>2: return original_cycle(*args,**kwargs)
            kwargs['lookback']=2520
            ctx=original_cycle(*args,**kwargs)
            records_by_context[id(ctx)]=ctx.get('series',[])
            ctx['series']=ctx.get('series',[])[-requested:]
            return ctx
        def cycle_card(ctx):
            # Export only the displayed production context, never integration-test
            # fixtures. Native VIX may end earlier than the stock session; expose
            # that actual date and insufficient-current status without a fake bar.
            records=records_by_context.pop(id(ctx),[])
            if records and ctx.get('available'):
                import pandas as pd
                from market_history import export_windows,write
                dates=pd.to_datetime([r['date'] for r in records])
                labels={'close':'VIX','wma5':'LWMA5','wma10':'LWMA10','sigma1':'+1σ','sigma2':'+2σ'}
                files=export_windows(root/'market-history','vixcycle',
                    {name:pd.Series([r.get(k) for r in records],index=dates,dtype=float) for k,name in labels.items()},mc['session_date'],
                    meta={'observed_asof':ctx.get('asof'),'source':'unchanged native Yahoo VIX High/monthly model'})
                index_path=root/'market-history/index.json'
                index=json.loads(index_path.read_text()); index['files']['vixcycle']=files;write(index_path,index)
                ctx['windows']=[{'label':'2Y','rows':records[-504:],'from':records[-min(504,len(records))]['date'][:7],'to':records[-1]['date'][:7]}]
            return original_cycle_card(ctx)
        module.build_vix_cycle=cycle
        module._vix_cycle_card=cycle_card

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--html',default='source-mc57.html')
    a=ap.parse_args(); root=Path(a.root); path=root/a.html; path.write_text(apply_html(path.read_text(),root),encoding='utf-8')
