import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest

spec=importlib.util.spec_from_file_location('archive',Path(__file__).with_name('archive.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
START=a.stamp('2026-02-26T00:00:00Z');END=a.stamp('2026-03-01T00:00:00Z')


def article(id='one', published='2026-02-27T12:00:00Z', text='Valid supplied text'):
    return {'id':id,'published_utc':published,'article_url':'https://example.org/'+id,
            'title':'Example','description':text,'tickers':['ABC'],
            'insights':[{'sentiment':'positive','sentiment_reasoning':'not historical evidence'}]}


class Fake:
    calls=0
    key='mock-key-never-actually-a-credential'
    def __init__(self,pages):self.pages=iter(pages)
    def get(self,url):
        self.calls+=1
        result=next(self.pages)
        if isinstance(result,Exception):raise result
        return result


def page(rows,next_url=None):
    return {'status':'OK','results':rows,'request_id':'test','next_url':next_url}


@pytest.fixture
def store(tmp_path):
    db=a.connect(tmp_path/'news.sqlite',START,END)
    yield db
    db.close()


def test_month_windows():
    result=list(a.windows(START,a.stamp('2026-09-29T04:05:21Z')))
    assert len(result)==8 and result[0]==('2026-02-26T00:00:00Z','2026-03-01T00:00:00Z')
    assert all(result[i][1]==result[i+1][0] for i in range(7))
    assert result[-1][1]=='2026-09-29T04:05:21Z'


def test_timezone_required():
    with pytest.raises(a.SafeError):a.stamp('2026-02-26')


@pytest.mark.parametrize('url',[
    'http://api.massive.com/v2/reference/news','https://api.massive.com.evil.org/v2/reference/news',
    'https://evil.org/v2/reference/news','https://api.massive.com:444/v2/reference/news',
    'https://me@api.massive.com/v2/reference/news','https://api.massive.com/v1/account',
    'https://api.massive.com/v2/reference/news#secret','https://api.massive.com/v2/reference/news?ticker=SECRET'])
def test_reject_unsafe_page(url):
    with pytest.raises(a.SafeError):a.checked_url(url)


def test_next_url_sanitized():
    assert a.checked_url('https://api.polygon.io:443/v2/reference/news?cursor=abc&apiKey=secret')==a.API+'?cursor=abc'


def test_complete_empty_is_not_failure(store):
    a.collect(store,Fake([page([])]));r=a.report(store)
    assert r['status']=='complete' and r['unique_article_ids']==0


def test_pagination_dedupe_versions(store):
    c=Fake([page([article(),article()],a.API+'?cursor=second'),page([article(text='Revised version')])])
    a.collect(store,c);r=a.report(store,c.calls)
    assert r['status']=='complete' and r['article_versions']==2 and r['unique_article_ids']==1
    assert r['partitions'][0]['duplicates']==1 and r['partitions'][0]['pages']==2
    assert r['historical_revision_verified'] is False


def test_budget_resume_committed_page(store):
    c=Fake([page([article()],a.API+'?cursor=second'),a.SafeError('REQUEST_BUDGET_EXCEEDED')])
    with pytest.raises(a.SafeError):a.collect(store,c)
    assert a.report(store)['status']=='partial'
    c2=Fake([page([article('two')])]);a.collect(store,c2)
    assert a.report(store)['status']=='complete' and a.report(store)['unique_article_ids']==2
    a.collect(store,Fake([]))


def test_invalid_and_out_of_window_rows(store):
    a.collect(store,Fake([page([article(),{},article('old','2026-02-25T00:00:00Z'),article('future','2026-03-01T00:00:00Z')])]))
    r=a.report(store);assert r['status']=='complete_with_rejections'
    assert r['partitions'][0]['invalid']==3 and r['article_versions']==1


def test_cycle_rejected_without_committing(store):
    url=store.execute('SELECT next_url FROM partitions').fetchone()[0]
    with pytest.raises(a.SafeError):a.collect(store,Fake([page([article()],url)]))
    assert a.report(store)['article_versions']==0


def test_known_key_never_stored(store):
    with pytest.raises(a.SafeError):a.collect(store,Fake([page([article(text=Fake.key)])]))
    assert a.report(store)['article_versions']==0


def test_strict_cutoff_and_insights_exclusion(store):
    a.collect(store,Fake([page([article(),article('late','2026-02-28T22:00:00Z')])]))
    cut=a.stamp('2026-02-28T00:00:00Z')
    docs=a.slice_articles(store,'ABC',START,cut)
    assert len(docs)==1 and 'insights' not in docs[0]
    assert a.slice_articles(store,'ABC',START,cut,strict=True)==[]
    assert a.slice_articles(store,'OTHER',START,cut)==[]


def test_encrypted_archive_roundtrip_and_integrity(tmp_path):
    path=tmp_path/'news.sqlite';db=a.connect(path,START,END)
    a.collect(db,Fake([page([article()])]))
    db.close();encrypted=tmp_path/'archive.enc'
    h=a.encrypt(path,encrypted,'test passphrase not a secret')
    assert len(h)==64 and b'Valid supplied text' not in encrypted.read_bytes()
    recovered=tmp_path/'restored.sqlite'
    a.decrypt(encrypted,recovered,'test passphrase not a secret')
    assert path.read_bytes()==recovered.read_bytes()
    with pytest.raises(a.SafeError):a.decrypt(encrypted,tmp_path/'bad.sqlite','wrong')
    corrupted=bytearray(encrypted.read_bytes());corrupted[-1]^=1;encrypted.write_bytes(corrupted)
    with pytest.raises(a.SafeError):a.decrypt(encrypted,tmp_path/'bad.sqlite','test passphrase not a secret')


def test_resume_config_must_match(tmp_path):
    path=tmp_path/'news.sqlite';a.connect(path,START,END).close()
    with pytest.raises(a.SafeError):a.connect(path,START,a.stamp('2026-04-01T00:00:00Z'))


def test_public_report_contains_no_text(store):
    a.collect(store,Fake([page([article()])]))
    r=a.canonical(a.report(store))
    assert 'Valid supplied text' not in r and 'https://example.org' not in r
    assert 'ABC' not in r and r.count('RETROSPECTIVE_PUBLISHED_TIME_ONLY')==1
