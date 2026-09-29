#!/usr/bin/env python3
"""Bounded all-market Massive news backfill. Raw data never goes to stdout.
Published time is not evidence of the historical version's availability.
The archive is retrospective and must not be called a point-in-time archive.
"""
from __future__ import annotations
import argparse
import calendar
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

UTC = timezone.utc
API = 'https://api.massive.com/v2/reference/news'
MAGIC = b'JEVNEWS1'
ITERATIONS = 600000
SCHEMA = 'jev-historical-news-v1'

class SafeError(Exception):
    """Only constant/sanitized codes belong in this exception."""


def stamp(value):
    if not isinstance(value, str): raise SafeError('INVALID_TIMESTAMP')
    try: out = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: raise SafeError('INVALID_TIMESTAMP') from None
    if out.tzinfo is None: raise SafeError('NAIVE_TIMESTAMP')
    return out.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def windows(start, end):
    if start >= end: raise SafeError('INVALID_WINDOW')
    while start < end:
        following = (start.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
        finish = min(following, end)
        yield iso(start), iso(finish)
        start = finish


def checked_url(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname not in {'api.massive.com', 'api.polygon.io'} or p.port not in {None, 443}:
            raise SafeError('UNSAFE_PAGINATION_URL')
    except (ValueError, TypeError): raise SafeError('UNSAFE_PAGINATION_URL') from None
    if p.path != '/v2/reference/news' or p.username or p.password or p.fragment:
        raise SafeError('UNSAFE_PAGINATION_URL')
    fields = []
    for key, value in parse_qsl(p.query, keep_blank_values=True):
        if key.lower() in {'apikey', 'api_key', 'token'}: continue
        if key not in {'cursor','limit','sort','order','published_utc.gte','published_utc.lt'}:
            raise SafeError('UNEXPECTED_PAGINATION_PARAMETER')
        fields.append((key, value))
    return urlunsplit(('https', 'api.massive.com', p.path, urlencode(fields), ''))


def connect(path, start, end):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript('''
    PRAGMA journal_mode=DELETE;
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS partitions (
      start TEXT PRIMARY KEY, finish TEXT NOT NULL, next_url TEXT NOT NULL,
      complete INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0,
      received INTEGER NOT NULL DEFAULT 0, invalid INTEGER NOT NULL DEFAULT 0,
      duplicates INTEGER NOT NULL DEFAULT 0, error TEXT);
    CREATE TABLE IF NOT EXISTS articles (
      id TEXT NOT NULL, hash TEXT NOT NULL, published TEXT NOT NULL,
      retrieved TEXT NOT NULL, url TEXT NOT NULL, payload TEXT NOT NULL,
      PRIMARY KEY(id, hash));
    CREATE INDEX IF NOT EXISTS article_time ON articles(published);
    CREATE TABLE IF NOT EXISTS pages (
      partition_start TEXT NOT NULL, page_number INTEGER NOT NULL,
      fetched_at TEXT NOT NULL, request_id TEXT, count INTEGER NOT NULL,
      response_hash TEXT NOT NULL, PRIMARY KEY(partition_start, page_number));
    CREATE TABLE IF NOT EXISTS requests_seen (url_hash TEXT PRIMARY KEY);
    ''')
    expected = {'schema':SCHEMA, 'start':iso(start), 'end':iso(end), 'scope':'all_market_no_holdings'}
    for key, value in expected.items():
        prior = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        if prior and prior[0] != value: raise SafeError('RESUME_CONFIGURATION_MISMATCH')
        db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', (key,value))
    for begin, finish in windows(start, end):
        url = API + '?' + urlencode({'published_utc.gte':begin, 'published_utc.lt':finish,
                                      'sort':'published_utc','order':'asc','limit':1000})
        db.execute('INSERT OR IGNORE INTO partitions(start,finish,next_url) VALUES (?,?,?)', (begin,finish,url))
    db.commit()
    return db


class Client:
    def __init__(self, key, maximum=200, seconds=3300, spacing=13):
        self.key, self.maximum, self.seconds, self.spacing = key, maximum, seconds, spacing
        self.calls, self.last, self.began = 0, 0.0, time.monotonic()
        self.session = requests.Session()

    def get(self, url):
        url = checked_url(url)
        for attempt in range(3):
            if self.calls >= self.maximum or time.monotonic()-self.began >= self.seconds:
                raise SafeError('REQUEST_BUDGET_EXCEEDED')
            time.sleep(max(0, self.spacing-(time.monotonic()-self.last)))
            self.last = time.monotonic()
            self.calls += 1
            try:
                response = self.session.get(url, headers={'Authorization':'Bearer '+self.key},
                                            timeout=(10,60), allow_redirects=False)
            except requests.RequestException:
                if attempt < 2: continue
                raise SafeError('NETWORK_FAILURE') from None
            if response.status_code in {401,403}: raise SafeError('API_ACCESS_DENIED_' + str(response.status_code))
            if response.status_code in {429,500,502,503,504}:
                if attempt < 2:
                    retry = response.headers.get('Retry-After', '')
                    delay = min(120, max(15, int(retry))) if retry.isdigit() else (60 if response.status_code==429 else 15)
                    time.sleep(delay)
                    continue
                raise SafeError('API_RETRY_EXHAUSTED_' + str(response.status_code))
            if response.status_code != 200: raise SafeError('HTTP_' + str(response.status_code))
            try: payload = response.json()
            except ValueError: raise SafeError('INVALID_API_JSON') from None
            if not isinstance(payload,dict) or payload.get('status') not in {'OK','DELAYED'}:
                raise SafeError('INVALID_API_STATUS')
            if not isinstance(payload.get('results'),list): raise SafeError('RESULTS_MISSING')
            return payload
        raise SafeError('RETRIES_EXHAUSTED')


def collect(db, client):
    for begin, finish, url, complete, pages in db.execute('SELECT start,finish,next_url,complete,pages FROM partitions ORDER BY start').fetchall():
        if complete: continue
        while url:
            safe = checked_url(url)
            if db.execute('SELECT 1 FROM requests_seen WHERE url_hash=?',(digest(safe),)).fetchone():
                raise SafeError('PAGINATION_CYCLE')
            payload = client.get(safe)
            following = checked_url(payload['next_url']) if payload.get('next_url') else ''
            if following == safe: raise SafeError('PAGINATION_CYCLE')
            now = iso(datetime.now(UTC))
            bad = dup = 0
            with db:
                for raw in payload['results']:
                    if not isinstance(raw,dict): bad+=1; continue
                    try: published = iso(stamp(raw.get('published_utc')))
                    except SafeError: bad+=1; continue
                    article_id, link = raw.get('id'), raw.get('article_url')
                    if not isinstance(article_id,str) or not article_id or not isinstance(link,str) or not link:
                        bad+=1; continue
                    if not begin <= published < finish: bad+=1; continue
                    try: encoded = canonical(raw)
                    except (ValueError,TypeError): bad+=1; continue
                    if getattr(client, 'key', None) and client.key in encoded:
                        raise SafeError('CREDENTIAL_IN_API_PAYLOAD')
                    changes = db.total_changes
                    db.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?)',
                               (article_id,digest(encoded),published,now,link,encoded))
                    dup += (db.total_changes == changes)
                pages += 1
                db.execute('INSERT INTO pages VALUES (?,?,?,?,?,?)',
                           (begin,pages,now,str(payload.get('request_id') or '')[:200],len(payload['results']),digest(canonical(payload['results']))))
                db.execute('INSERT INTO requests_seen VALUES (?)',(digest(safe),))
                db.execute('UPDATE partitions SET next_url=?,complete=?,pages=?,received=received+?,invalid=invalid+?,duplicates=duplicates+?,error=NULL WHERE start=?',
                           (following,not bool(following),pages,len(payload['results']),bad,dup,begin))
            print(canonical({'event':'page_saved','partition':begin[:7],'pages':pages,'received':len(payload['results']),'total_requests':client.calls}),flush=True)
            url = following


def report(db, calls=0, error=None):
    parts = [dict(zip(['start','end','complete','pages','received','invalid','duplicates'],x))
             for x in db.execute('SELECT start,finish,complete,pages,received,invalid,duplicates FROM partitions ORDER BY start')]
    n, ids, first, last = db.execute('SELECT COUNT(*),COUNT(DISTINCT id),MIN(published),MAX(published) FROM articles').fetchone()
    filled = db.execute("SELECT COUNT(*) FROM articles WHERE json_type(payload,'$.description')='text' AND length(trim(json_extract(payload,'$.description')))>0").fetchone()[0]
    done = bool(parts) and all(p['complete'] for p in parts)
    invalid = sum(p['invalid'] for p in parts)
    return {'schema_version':SCHEMA,'scope':'all_market_no_holdings',
            'status':'complete' if done and not invalid and not error else 'complete_with_rejections' if done and not error else 'partial' if n else 'failed',
            'error_code':error,'partitions':parts,'article_versions':n,'unique_article_ids':ids,
            'description_present':filled,'description_missing':n-filled,'first_published_utc':first,'last_published_utc':last,
            'requests_this_run':calls,'historical_revision_verified':False,
            'point_in_time_status':'RETROSPECTIVE_PUBLISHED_TIME_ONLY',
            'retrieved_at':iso(datetime.now(UTC)), 'raw_publication':False,'jev_calls':0}


def encrypt(path, output, password):
    if not password: raise SafeError('ARCHIVE_PASSPHRASE_MISSING')
    plain = path.read_bytes()
    if not plain.startswith(b'SQLite format 3\x00'): raise SafeError('INVALID_ARCHIVE_DB')
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS, 32)
    compressed = gzip.compress(plain, mtime=0)
    sealed = header + AESGCM(key).encrypt(nonce, compressed, header)
    if AESGCM(key).decrypt(nonce,sealed[len(header):],header) != compressed: raise SafeError('ENCRYPTION_SELF_CHECK_FAILED')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    temporary.write_bytes(sealed); temporary.replace(output)
    return hashlib.sha256(sealed).hexdigest()


def decrypt(source, target, password):
    if target.exists(): raise SafeError('RESTORE_TARGET_EXISTS')
    sealed = source.read_bytes()
    if not sealed.startswith(MAGIC) or len(sealed)<68: raise SafeError('INVALID_ENCRYPTED_ARCHIVE')
    salt, nonce, header = sealed[8:24],sealed[24:36],sealed[:36]
    key = hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS,32)
    try: plain=gzip.decompress(AESGCM(key).decrypt(nonce,sealed[36:],header))
    except Exception: raise SafeError('ARCHIVE_AUTHENTICATION_FAILED') from None
    if not plain.startswith(b'SQLite format 3\x00'): raise SafeError('INVALID_ARCHIVE_DB')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(plain)
    db=sqlite3.connect(target)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise SafeError('ARCHIVE_INTEGRITY_FAILED')
    finally: db.close()


def slice_articles(db, ticker, start, asof, strict=False):
    """No provider-generated insights; strict mode uses actual first observation."""
    documents=[]
    for published,retrieved,payload in db.execute('SELECT published,retrieved,payload FROM articles WHERE published>=? AND published<=? ORDER BY published,id', (iso(start),iso(asof))):
        raw=json.loads(payload)
        if ticker not in (raw.get('tickers') or []): continue
        if strict and stamp(retrieved)>asof: continue
        documents.append({'id':raw['id'],'title':raw.get('title'),'description':raw.get('description'),
                          'article_url':raw['article_url'],'published_utc':published,'retrieved_utc':retrieved,
                          'historical_revision_verified':False,'evidence_grade':'RETROSPECTIVE'})
    return documents


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['acquire','restore','slice'])
    p.add_argument('--db',default='.private-news/archive.sqlite')
    p.add_argument('--config',default='research/news_backfill/config.json')
    p.add_argument('--output',default='news-output')
    p.add_argument('--archive')
    p.add_argument('--ticker');p.add_argument('--asof');p.add_argument('--strict',action='store_true')
    args=p.parse_args()
    password=os.environ.get('ARCHIVE_PASSPHRASE','')
    if args.command=='restore':
        decrypt(Path(args.archive),Path(args.db),password);return 0
    if args.command=='slice':
        if not args.ticker or not args.asof: raise SafeError('TICKER_AND_ASOF_REQUIRED')
        cut=stamp(args.asof);db=sqlite3.connect('file:'+str(Path(args.db).resolve())+'?mode=ro',uri=True)
        docs=slice_articles(db,args.ticker.upper(),cut-timedelta(days=30),cut,args.strict)
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(canonical({'asof':iso(cut),'strict':args.strict,'documents':docs})+'\n')
        return 0
    cfg=json.loads(Path(args.config).read_text())
    if not password: raise SafeError('ARCHIVE_PASSPHRASE_MISSING')
    key=next((os.environ[k] for k in ['MASSIVE_API_KEY','POLYGON_API_KEY'] if os.environ.get(k)),None)
    if not key: raise SafeError('MASSIVE_API_KEY_MISSING')
    db_path=Path(args.db)
    db=connect(db_path,stamp(cfg['news_start']),stamp(cfg['news_cutoff']))
    client=Client(key,maximum=cfg['max_requests'],seconds=cfg['max_seconds'],spacing=cfg['request_spacing_seconds'])
    error=None
    try:collect(db,client)
    except SafeError as exc:error=str(exc)
    except Exception:error='UNEXPECTED_FAILURE'
    result=report(db,client.calls,error);db.close()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    result['encrypted_sha256']=encrypt(db_path,output/'news.sqlite.gz.aesgcm',password)
    result['storage']='encrypted_artifact_pending_upload'
    result['config_sha256']=digest(canonical(cfg))
    result['code_sha']=os.environ.get('GITHUB_SHA')
    (output/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(canonical(result))
    return 0 if result['status']=='complete' else 2

if __name__=='__main__':
    try:sys.exit(main())
    except SafeError as exc:
        print(canonical({'status':'failed','error_code':str(exc)}));sys.exit(2)
    except Exception:
        print(canonical({'status':'failed','error_code':'UNEXPECTED_FAILURE'}));sys.exit(2)
