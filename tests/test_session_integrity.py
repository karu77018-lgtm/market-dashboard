import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from session_universe import save_frozen, load_frozen, coverage_stats
from refresh_mc57 import preserve_same_session_mc57
from render_jev_ranking import render, source_hash
from scripts.phase_a0.content_hash import content_hash
from scripts.phase_a0.upload_google_drive import find_existing_content


def test_rerun_retains_membership_and_fundamentals(tmp_path):
    rows = [{'ticker': 'AAA', 'price': 10, 'market_cap': 200000000}]
    first = save_frozen(tmp_path/'work', '2026-09-30', rows, {}, {}, '2026-09-30T21:45:00Z')
    second = save_frozen(tmp_path/'work', '2026-09-30', [{'ticker':'BBB'}], {}, {}, '2026-10-01T15:00:00Z')
    assert first == second
    assert second['rows'] == rows
    assert coverage_stats(rows, {'AAA':{}, 'BBB':{}})['active_universe'] == 1
    assert coverage_stats(rows, {})['massive_current_missing'] == 1
    ledger = json.loads((tmp_path/'universe-snapshots/2026-09-30.json').read_text())
    assert ledger['tickers'] == ['AAA'] and 'rows' not in ledger


def test_missing_or_corrupt_cache_never_reselects(tmp_path):
    work = tmp_path/'work'
    save_frozen(work, '2026-09-30', [{'ticker':'AAA'}], {}, {}, '2026-09-30T21:45:00Z')
    ledger = tmp_path/'universe-snapshots/2026-09-30.json'
    ledger.unlink()
    assert load_frozen(work,'2026-09-30')['rows'][0]['ticker']=='AAA'
    assert ledger.exists()
    path = work/'universes/2026-09-30.json'
    payload = json.loads(path.read_text()); payload['rows'][0]['ticker'] = 'BBB'
    path.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match='modified'):
        load_frozen(work, '2026-09-30')
    path.unlink()
    with pytest.raises(RuntimeError, match='restore'):
        load_frozen(work, '2026-09-30')


def test_late_first_capture_is_not_claimed_as_point_in_time(tmp_path):
    value = save_frozen(tmp_path/'work', '2026-09-30', [{'ticker':'AAA'}], {}, {}, '2026-10-01T15:00:00Z')
    assert value['late_capture'] and not value['point_in_time_verified']


def test_correction_retains_old_calculation_and_uses_new_history(tmp_path):
    prior = {'session_date':'2026-09-30', 'calculation_version':'v1', 'status':'READY',
             'coverage':1.0, 'mc57':21.43, 'generated_at':'2026-09-30T21:00:00Z',
             'history':[{'date':'2026-09-30','mc57':21.43}]}
    fresh = {**prior, 'mc57':22.0, 'generated_at':'2026-10-01T10:00:00Z',
             'history':[{'date':'2026-09-30','mc57':22.0}]}
    (tmp_path/'data').mkdir(); (tmp_path/'market-history').mkdir()
    (tmp_path/'data/mc57.json').write_text(json.dumps(prior))
    full = tmp_path/'market-history/mc57-full.json'
    full.write_text(json.dumps({'history': fresh['history']}))
    held = preserve_same_session_mc57(tmp_path, copy.deepcopy(fresh))
    assert held['mc57'] == 21.43
    full.write_text(json.dumps({'history': fresh['history']}))
    fixed = preserve_same_session_mc57(tmp_path, fresh, correction_reason='Corrected input mapping')
    assert fixed['mc57'] == 22 and fixed['corrections'][-1]['previous_mc57'] == 21.43
    assert json.loads(full.read_text())['history'][-1]['mc57'] == 22
    archived = list((tmp_path/'work/mc57-corrections/2026-09-30').glob('*.json'))
    assert len(archived) == 1 and json.loads(archived[0].read_text())['mc57'] == 21.43


def test_archive_fingerprint_ignores_run_time_but_preserves_revisions(tmp_path):
    path = tmp_path/'input.json'
    value = {'generated_at':'2026-10-01T01:00:00Z', 'price':12, 'provider':'Yahoo', 'state':'provisional'}
    path.write_text(json.dumps(value))
    first = content_hash([(path,'input.json')], '2026-09-30','delta')
    value['generated_at'] = '2026-10-01T02:00:00Z'; path.write_text(json.dumps(value))
    assert content_hash([(path,'input.json')], '2026-09-30','delta') == first
    value['provider']='Massive'; value['state']='confirmed'; path.write_text(json.dumps(value))
    assert content_hash([(path,'input.json')], '2026-09-30','delta') != first
    value['correction']={'reason':'fixed', 'published_at':'2026-10-01T03:00:00Z'}; path.write_text(json.dumps(value))
    corrected = content_hash([(path,'input.json')], '2026-09-30','delta')
    value['correction']['reason']='other'; path.write_text(json.dumps(value))
    assert content_hash([(path,'input.json')], '2026-09-30','delta') != corrected


def test_drive_duplicate_lookup_is_scoped_to_folder_session_content():
    with patch('scripts.phase_a0.upload_google_drive.request_json', return_value=({'files':[{'id':'existing'}]},None)) as get:
        assert find_existing_content('token','private-folder',{'session':'2026-09-30','content_sha256':'abc','mode':'delta'})['id']=='existing'
        url = get.call_args.args[0]
        assert 'private-folder' in url and 'content_sha256' in url and '2026-09-30' in url


def test_html_hash_survives_attribute_order_and_detects_source_changes(tmp_path):
    html = tmp_path/'source.html'; ranking = tmp_path/'ranking.json'
    ranking.write_text('{"rows":[]}')
    html.write_text('<html><head></head><body><nav></nav><footer class=\'disc\'></footer></body></html>')
    render(html,ranking)
    first=html.read_text()
    import re
    swapped=re.sub(r'<meta name="dashboard-source-sha256" content="([a-f0-9]+)"/>', r'<meta content="\1" name="dashboard-source-sha256"/>', first)
    assert source_hash(first)==source_hash(swapped)
    html.write_text(swapped); render(html,ranking)
    assert html.read_text().count('name="dashboard-source-sha256"')==1
    assert source_hash(first.replace('<nav>', '<nav>changed'))!=source_hash(first)
