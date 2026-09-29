#!/usr/bin/env python3
"""Independent read-only reconstruction of stored pilot metrics; no paid calls."""
import hashlib,io,json,math,os,statistics,subprocess,tarfile,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT=Path.cwd();PRIVATE=ROOT/'.private-pilot-audit';OUT=ROOT/'pilot-audit-output'

def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def h(x):return hashlib.sha256(x).hexdigest()
def mean(x):return statistics.mean(x)

def main():
    PRIVATE.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
    src=PRIVATE/'pilot.zip'
    with src.open('wb') as f:
        p=subprocess.run(['gh','api','repos/karu77018-lgtm/market-dashboard/actions/artifacts/11038369542/zip'],stdout=f,stderr=subprocess.PIPE)
    if p.returncode or h(src.read_bytes())!='3fdcb6dc2990f95aa4026714227efd5de0e2d569a4f72d3a1328b6629050ccf5':raise ValueError('ARTIFACT_CHECK_FAILED')
    with zipfile.ZipFile(src) as z:
        preservation=json.loads(z.read('preservation.json'));report=json.loads(z.read('report.json'))
        sealed=z.read(preservation['filename'])
    if h(sealed)!=preservation['encrypted_sha256'] or sealed[:8]!=b'JEVVAL01':raise ValueError('ENCRYPTED_HASH_FAILED')
    password=os.environ['ARCHIVE_PASSPHRASE']
    key=hashlib.pbkdf2_hmac('sha256',password.encode(),sealed[8:24],600000,32)
    raw=AESGCM(key).decrypt(sealed[24:36],sealed[36:],sealed[:36])
    if h(raw)!=preservation['plaintext_archive_sha256']:raise ValueError('PLAINTEXT_HASH_FAILED')
    data={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.endswith('.json'):
                with tf.extractfile(m) as f:data[m.name]=json.load(f)
    rows=data['scored-predictions.json'];calls=[v for k,v in data.items() if k.startswith('call-')]
    checks={'archive_authenticated':True,'state_hash_mismatches':0,'question_hash_mismatches':0,
            'model_run_count_errors':0,'forecast_state_contains_outcomes':0,'future_news_ages':0,
            'baseline_lookahead':0,'probability_errors':0,'interval_order_errors':0,'metric_mismatches':0}
    generations=set();model_counts=Counter();cost=0;input_tokens=output_tokens=0
    diagnostics=data['diagnoses.json'];diagnostic_evidence=[]
    def has_outcome(x):
        if isinstance(x,dict):return any(k in {'actual','actual_return','realized_return','future_return'} or has_outcome(v) for k,v in x.items())
        if isinstance(x,list):return any(has_outcome(v) for v in x)
        return False
    forecast_calls=[]
    for c in calls:
        model_counts[c['kind']]+=1
        checks['state_hash_mismatches']+=h(canonical(c['state']).encode())!=c['state_sha256']
        checks['question_hash_mismatches']+=h(canonical(c['questions']).encode())!=c['questions_sha256']
        rr=c.get('response',{}).get('rawRuns',[])
        checks['model_run_count_errors']+=len(rr)!=3
        for run in rr:
            gm=(run.get('providerMetadata') or {}).get('gateway') or {}
            if gm.get('generationId'):generations.add(gm['generationId'])
            usage=run.get('usage') or {};input_tokens+=usage.get('inputTokens',0) or 0;output_tokens+=usage.get('outputTokens',0) or 0
        cost+=c.get('actual_gateway_cost_usd',0)
        if c['kind']!='error_diagnosis':
            forecast_calls.append(c)
            checks['forecast_state_contains_outcomes']+=has_outcome(c['state'])
            docs=c['state'].get('market_materials',[])
            for case in c['state']['cases']:docs=docs+case.get('company_materials',[])
            checks['future_news_ages']+=sum(d.get('days_before_cutoff',0)<0 for d in docs)
    per_case={};group=defaultdict(list)
    for r in rows:
        group[(r['model'],r['horizon'])].append(r)
        if r.get('baseline_latest_label_session'):checks['baseline_lookahead']+=r['baseline_latest_label_session']>r['origin']
        for kind in ['terminal','up','down']:
            q=r[kind];checks['interval_order_errors']+=not q['q10_pct']<=q['q50_pct']<=q['q90_pct']
            if 'bin_probabilities' in q:
                p=q['bin_probabilities'];checks['probability_errors']+=len(p)!=7 or abs(sum(p)-1)>1e-9 or any(not 0<=v<=1 for v in p)
        if r['model']=='jev_news' and r['horizon']==5:per_case[r['case_id']]=r
    recomputed={};extreme=[]
    for (model,horizon),rs in sorted(group.items()):
        scored=[r for r in rs if r.get('actual') is not None]
        coverage=[];direction=[];width=[];interval=[];mederr=[];meanerr=[];brier=[]
        for r in scored:
            f=r['terminal'];y=r['actual']['terminal_pct'];lo=f['q10_pct'];hi=f['q90_pct'];p=f['p_positive']
            coverage.append(lo<=y<=hi);direction.append((p>=.5)==(y>0));width.append(hi-lo)
            interval.append(hi-lo+10*max(lo-y,0)+10*max(y-hi,0));mederr.append(abs(f['q50_pct']-y));meanerr.append(abs(f['mean_pct']-y));brier.append((p-int(y>0))**2)
            if abs(f['mean_pct'])>500:
                extreme.append({'case_id':r['case_id'],'ticker':r['ticker'],'origin':r['origin'],'horizon':horizon,'model':model,
                    'expected_pct':f['mean_pct'],'median_pct':f['q50_pct'],'lower_pct':lo,'upper_pct':hi,'realized_pct':y})
        result={'n':len(scored),'terminal80_coverage':mean(coverage),'direction_accuracy':mean(direction),
                'width_pp':mean(width),'interval_score_pp':mean(interval),'brier':mean(brier),
                'median_absolute_error_pp':mean(mederr),'mean_absolute_error_pp':mean(meanerr)}
        for k in ['n','terminal80_coverage','direction_accuracy','width_pp','interval_score_pp','brier','mean_absolute_error_pp']:
            checks['metric_mismatches']+=abs(result[k]-report['metrics'][model][str(horizon)][k])>1e-7
        recomputed.setdefault(model,{})[str(horizon)]=result
    debug=[]
    extreme_ids={r['case_id'] for r in extreme}
    for cid in extreme_ids:
        r=per_case.get(cid)
        if not r:continue
        call=next((c for c in forecast_calls if c['state_sha256']==r['state_sha256']),None)
        debug.append({'case_id':cid,'ticker':r['ticker'],'origin':r['origin'],
            'batch_features':[{'daily_log_vol20':x['features']['daily_log_vol20'],'return_63d_pct':x['features']['return_63d_pct'],
                               'adr20_pct':x['features']['adr20_pct'],'scale_5':x['scale_5'],'scale_10':x['scale_10']} for x in call['state']['cases']] if call else []})
    for d in diagnostics:
        r=per_case.get(d['case_id'])
        diagnostic_evidence.append({'case_id':d['case_id'],'ticker':r['ticker'] if r else None,
           'error_type':d['likely_error_type']['choice'],'evidence_id':d['evidence']['choice'],
           'agreement':d['likely_error_type']['agreement'],'causality_established':False})
    out={'schema_version':'jev-pilot-independent-audit-v1','source_run_id':36581174021,
         'checks':checks,'comparisons':recomputed,'model_call_counts':dict(model_counts),'http_calls':len(calls),
         'raw_model_runs':sum(len(c.get('response',{}).get('rawRuns',[])) for c in calls),'unique_gateway_generation_ids':len(generations),
         'actual_gateway_cost_usd':cost,'input_tokens':input_tokens,'output_tokens':output_tokens,
         'extreme_expected_value_rows':len(extreme),'extreme_expected_value_cases':len(extreme_ids),'extreme_values':extreme,
         'extreme_case_features':debug,'diagnoses':diagnostic_evidence,
         'mean_expected_return_status':'WITHHELD_UNSTABLE_TAIL_EXTRAPOLATION' if extreme else 'UNVALIDATED',
         'expected_return_not_approved_for_display':True,'new_model_calls':0,'new_vendor_calls':0,
         'raw_article_text_publication':False,'holdout_evaluated':False}
    (OUT/'audit.json').write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    (OUT/'source-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(out,sort_keys=True))
    return int(any(v for k,v in checks.items() if k!='archive_authenticated'))

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:print('{"status":"failed","error_code":"PILOT_AUDIT_FAILED"}');raise SystemExit(2)
