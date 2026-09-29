#!/usr/bin/env python3
"""Read-only aggregate verification. Never emits article text, URL or ticker lists."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit


def audit(path, expected_index=None):
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    meta=dict(db.execute('SELECT key,value FROM meta'))
    counts={'hash_mismatches':0,'outside_requested_window':0,'missing_description':0,'invalid_article_urls':0,'tickerless_articles':0}
    seen=set();ids=set();times=[];months={};versions=0
    for identifier,stored_hash,published,retrieved,payload in db.execute('SELECT id,hash,published,retrieved,payload FROM articles'):
        versions+=1;ids.add(identifier);times.append(published)
        counts['hash_mismatches']+=hashlib.sha256(payload.encode()).hexdigest()!=stored_hash
        counts['outside_requested_window']+=not(meta['start']<=published<meta['end'])
        raw=json.loads(payload)
        description=raw.get('description')
        counts['missing_description']+=not isinstance(description,str) or not description.strip()
        try:
            url=urlsplit(raw.get('article_url',''));valid=url.scheme in {'http','https'} and bool(url.hostname) and not url.username and not url.password
        except (ValueError,TypeError):valid=False
        counts['invalid_article_urls']+=not valid
        ticks=raw.get('tickers');ticks=ticks if isinstance(ticks,list) else []
        seen.update(t for t in ticks if isinstance(t,str) and t)
        counts['tickerless_articles']+=not ticks
        months[published[:7]]=months.get(published[:7],0)+1
    partitions=db.execute('SELECT COUNT(*),SUM(complete),SUM(received),SUM(invalid),SUM(duplicates) FROM partitions').fetchone()
    db.close()
    balance=(partitions[2] or 0)==versions+(partitions[3] or 0)+(partitions[4] or 0)
    out={'schema_version':'jev-news-archive-audit-v1','sqlite_integrity_ok':integrity,'counts_reconcile':balance,
         'article_versions':versions,'unique_article_ids':len(ids),'distinct_ticker_tags':len(seen),
         'first_published_utc':min(times) if times else None,'last_published_utc':max(times) if times else None,
         'month_version_counts':months,'partitions_total':partitions[0],'partitions_completed':partitions[1] or 0,
         'checks':counts,'historical_revision_verified':False,'raw_publication':False}
    if expected_index:
        index=json.loads(Path(expected_index).read_text())
        tickers=set(index['ticker_to_shard'])
        out['current_universe_overlap']={'session_date':index.get('session_date'),'universe_size':len(tickers),
            'with_provider_articles':len(tickers&seen),'without_provider_articles':len(tickers-seen),
            'interpretation':'current_universe_only_not_historical_universe_coverage'}
    out['verification_passed']=integrity and balance and partitions[0]>0 and partitions[0]==(partitions[1] or 0) and not counts['hash_mismatches'] and not counts['outside_requested_window']
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='.private-news/archive.sqlite')
    p.add_argument('--expected-index')
    p.add_argument('--output',default='news-output/audit.json')
    args=p.parse_args()
    try:
        result=audit(args.db,args.expected_index)
        Path(args.output).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print(json.dumps(result,sort_keys=True))
        raise SystemExit(0 if result['verification_passed'] else 2)
    except Exception:
        print('{"status":"failed","error_code":"ARCHIVE_AUDIT_FAILED"}');raise SystemExit(2)
