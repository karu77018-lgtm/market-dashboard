#!/usr/bin/env python3
"""Restore the published layout without reacquiring or redating any prices."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def embedded(text: str, name: str):
    match = re.search(r'window\.'+re.escape(name)+r'\s*=\s*', text)
    if not match:
        raise ValueError(f'Missing embedded {name}')
    return json.JSONDecoder().raw_decode(text[match.end():])[0]


def restore_text(text: str) -> tuple[str, int]:
    # Breadth cards are part of the intended Daily layout.  The restoration
    # workflow must never strip them from an already-published page.
    return text, 0


def restore(root: Path):
    path = root/'source-mc57.html'
    before = path.read_text(encoding='utf-8')
    after, removed = restore_text(before)
    styles_before = re.findall(r'<style>(.*?)</style>', before, re.S)
    styles_after = re.findall(r'<style>(.*?)</style>', after, re.S)
    assert styles_before == styles_after
    for name in ('DET','CALC'):
        assert embedded(before,name) == embedded(after,name)
    manifest = load(root/'latest-manifest.json')
    report = {'schema_version':'dashboard-restoration-v1',
              'session_date':manifest['session_date'],
              'active_universe':manifest['universe']['active_universe'],
              'price_generated_at':manifest['generated_at'],
              'removed_inserted_cards':removed,
              'original_styles_unchanged':True,
              'trading_data_unchanged':True,
              'before_html_sha256':digest(before),
              'restored_html_sha256':digest(after),
              'manifest_sha256':digest((root/'latest-manifest.json').read_text()),
              'original_style_sha256':[digest(x) for x in styles_before]}
    dump(root/'restoration-report.json',report)
    path.write_text(after,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


def diagnose(root: Path):
    import requests
    key = os.environ.get('MASSIVE_API_KEY','').strip()
    if not key:
        raise RuntimeError('MASSIVE_API_KEY is not configured')
    session = load(root/'latest-manifest.json')['session_date']
    cases = [
        ('reference','/v3/reference/tickers',{'ticker':'QQQ','limit':1}),
        ('news','/v2/reference/news',{'ticker':'QQQ','limit':1,'order':'desc'}),
        ('grouped_current',f'/v2/aggs/grouped/locale/us/market/stocks/{session}',{'adjusted':'true','include_otc':'false'}),
        ('qqq_current',f'/v2/aggs/ticker/QQQ/range/1/day/{session}/{session}',{'adjusted':'true'}),
    ]
    checks = []
    client = requests.Session()
    for index,(name,path,params) in enumerate(cases):
        if index:
            time.sleep(15)
        result = {'name':name,'endpoint':path,'session_date':session}
        try:
            response = client.get('https://api.massive.com'+path,
                                  params={**params,'apiKey':key},timeout=40)
            result['http_status']=response.status_code
            try: payload=response.json()
            except ValueError: payload={}
            if not isinstance(payload,dict):payload={}
            result['provider_status']=str(payload.get('status',''))[:60]
            result['result_count']=len(payload.get('results') or [])
            result['request_id']=str(payload.get('request_id',''))[:80]
            if response.status_code != 200:
                message=str(payload.get('message') or payload.get('error') or '')
                message=message.replace(key,'[REDACTED]')
                message=re.sub(r'(?i)(apiKey|token|secret)=[^&\s]+',r'\1=[REDACTED]',message)
                result['message']=message[:400]
        except requests.RequestException as exc:
            result['http_status']=None
            result['error_type']=type(exc).__name__
        checks.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    report={'schema_version':'massive-connectivity-v1',
            'checked_at':datetime.now(timezone.utc).isoformat(),
            'price_session_date':session,
            'checks':checks,
            'note':'Credential presence is not proof of price endpoint entitlement. No API key or vendor raw data is published.'}
    dump(root/'massive-api-status.json',report)


def validate(root: Path):
    text=(root/'source-mc57.html').read_text(encoding='utf-8')
    report=load(root/'restoration-report.json')
    manifest=load(root/'latest-manifest.json')
    ranking=load(root/'data/jev-ranking.json')
    summary=load(root/'.preservation/jev/live-shadow-summary.json')
    assert digest((root/'latest-manifest.json').read_text())==report['manifest_sha256']
    assert [digest(x) for x in re.findall(r'<style>(.*?)</style>',text,re.S)]==report['original_style_sha256']
    assert 'data-source-improvement="50ma-participation"' in text
    assert 'data-source-improvement="52week-high-low"' in text
    assert text.count('JEV_RANKING_NAV_START')==1
    assert text.count("id='t-jev'")==1
    assert ranking['session_date']==manifest['session_date']
    assert ranking['available_at']==manifest['generated_at']
    assert summary['error_count']==0, 'Jev incomplete; keep previous live publication'
    assert ranking['rows'], 'No actual Jev evaluations; refuse empty placeholder publication'
    assert len(ranking['rows'])==summary['evaluated_count']
    scores=[float(x['expected_value_score']) for x in ranking['rows']]
    assert all(-100<=x<=100 for x in scores)
    assert scores==sorted(scores,reverse=True)
    assert len({x['ticker'] for x in ranking['rows']})==len(scores)
    assert all(x.get('evaluation_id') for x in ranking['rows'])
    text=text.replace('<th>期待値</th>','<th>材料スコア</th>')
    text=text.replace('ニュース材料の期待値','Jev評価に基づく材料順位')
    selected=summary['selected_count']; evaluated=summary['evaluated_count']; skipped=summary['skipped_no_news_count']
    scope=(f'<div class="mut">対象は表示候補とRS21・63・189各上位を重複除外した{selected}候補。評価済み{evaluated}銘柄、'
           f'対象ニュースなし{skipped}銘柄。全{report["active_universe"]:,}銘柄の一括Jev評価ではありません。'
           '株価の5日・10日期待収益率は未算出です。</div>')
    needle="<div class='mut jev-asof'>"
    text=text.replace(needle,scope+needle,1)
    report.update({'jev_status':ranking['status'],'jev_selected':selected,'jev_evaluated':evaluated,
                   'jev_skipped_no_news':skipped,'jev_errors':summary['error_count'],
                   'jev_evidence_cutoff':ranking['available_at'],
                   'completed_at':datetime.now(timezone.utc).isoformat(),
                   'published_html_sha256':digest(text),
                   'github_run_id':os.environ.get('GITHUB_RUN_ID')})
    (root/'source-mc57.html').write_text(text,encoding='utf-8')
    dump(root/'restoration-report.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['restore','diagnose','validate']);p.add_argument('--root',default='.')
    a=p.parse_args();globals()[a.mode](Path(a.root).resolve())

if __name__=='__main__':main()
