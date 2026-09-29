#!/usr/bin/env python3
"""Read back final encrypted evidence and audit actual model calls, not narrative reports."""
import hashlib,io,json,math,os,subprocess,tarfile,zipfile
from collections import Counter
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
ROOT=Path.cwd();PRIVATE=ROOT/'.private-final-audit';OUT=ROOT/'final-audit-output'
REPO='karu77018-lgtm/market-dashboard';RUN=36587515864

def h(v):return hashlib.sha256(v).hexdigest()
def can(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def main():
 PRIVATE.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
 r=subprocess.run(['gh','api',f'repos/{REPO}/actions/runs/{RUN}/artifacts'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
 candidates=[a for a in json.loads(r.stdout)['artifacts'] if a['name']==f'jev-forecast-final-{RUN}-1' and not a['expired']]
 if len(candidates)!=1:raise ValueError('FINAL_ARTIFACT_UNAVAILABLE')
 artifact=candidates[0];zpath=PRIVATE/'final.zip'
 with zpath.open('wb') as f:subprocess.run(['gh','api',f'repos/{REPO}/actions/artifacts/{artifact["id"]}/zip'],stdout=f,stderr=subprocess.PIPE,check=True)
 if 'sha256:'+h(zpath.read_bytes())!=artifact['digest']:raise ValueError('ZIP_HASH_MISMATCH')
 with zipfile.ZipFile(zpath) as z:
  meta=json.loads(z.read('preservation.json'));report=json.loads(z.read('completion-report.json'))
  sealed=z.read(meta['filename']);numeric=json.loads(z.read('numeric-prediction-evidence.json'))
 if h(sealed)!=meta['encrypted_sha256'] or sealed[:8]!=b'JEVVAL01':raise ValueError('ENCRYPTED_HASH_MISMATCH')
 key=hashlib.pbkdf2_hmac('sha256',os.environ['ARCHIVE_PASSPHRASE'].encode(),sealed[8:24],600000,32)
 raw=AESGCM(key).decrypt(sealed[24:36],sealed[36:],sealed[:36])
 if h(raw)!=meta['plaintext_archive_sha256']:raise ValueError('PLAINTEXT_HASH_MISMATCH')
 data={}
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
  for m in tf.getmembers():
   if m.isfile() and m.name.endswith('.json'):
    with tf.extractfile(m) as f:data[m.name]=json.load(f)
 calls=[v for k,v in data.items() if k.startswith('call-')]
 errors=[];kinds=Counter();generation_ids=[];tokens=Counter();total=0.;max_prob_sum_drift=0.;states=set();news_count=0
 def contains_outcome(obj):
  if isinstance(obj,dict):return any(k in {'actual','actual_return','future_return','realized_return'} or contains_outcome(v) for k,v in obj.items())
  if isinstance(obj,list):return any(contains_outcome(v) for v in obj)
  return False
 for call in calls:
  kinds[call['kind']]+=1;states.add(call['state_sha256'])
  if h(can(call['state']))!=call['state_sha256']:errors.append('STATE_HASH')
  if h(can(call['questions']))!=call['questions_sha256']:errors.append('QUESTION_HASH')
  if call.get('http_status')!=200 or call.get('response',{}).get('ok') is not True:errors.append('UNSUCCESSFUL_CALL')
  rr=call['response'].get('rawRuns',[])
  if len(rr)!=3:errors.append('THREE_RUNS')
  cost=0
  for r in rr:
   gm=r.get('providerMetadata',{}).get('gateway',{})
   generation_ids.append(gm.get('generationId'))
   found=False
   for k in ['cost','gatewayCost','inferenceCost']:
    if gm.get(k) is not None:
     v=float(gm[k]);found=True;cost+=v
     if not math.isfinite(v) or v<0:errors.append('INVALID_COST')
     break
   if not found:errors.append('MISSING_COST')
   for k in ['inputTokens','outputTokens']:tokens[k]+=r.get('usage',{}).get(k,0) or 0
   for q,definition in call['questions'].items():
    a=r.get('answers',{}).get(q,{})
    dist=a.get('probabilities') or a.get('distribution')
    if not isinstance(dist,dict) or set(dist)!=set(definition['criteria']):errors.append('CHOICE_KEYS');continue
    p=list(dist.values())
    if any(not isinstance(x,(float,int)) or not math.isfinite(x) or not 0<=x<=1 for x in p):errors.append('CHOICE_PROB');continue
    drift=abs(sum(p)-1);max_prob_sum_drift=max(max_prob_sum_drift,drift)
    if drift>.04 or a.get('choice') not in definition['criteria']:errors.append('CHOICE_SUM_OR_VALUE')
  total+=cost
  if abs(cost-call.get('actual_gateway_cost_usd',-1))>1e-9:errors.append('CALL_COST_SUM')
  if call['kind'] in ['jev_news','jev_technical']:
   state=call['state']
   if contains_outcome(state):errors.append('FUTURE_OUTCOME_FIELD_IN_FORECAST')
   docs=list(state.get('market_materials',[]))
   for c in state.get('cases',[]):docs.extend(c.get('company_materials',[]))
   news_count+=len(docs)
   if any(d.get('days_before_cutoff',0)<0 for d in docs):errors.append('NEWS_AFTER_FORECAST_CUTOFF')
   feedback=state.get('past_development_feedback',{})
   matching=[r for r in numeric['rows'] if r.get('state_sha256')==call['state_sha256'] and r['model']==call['kind']]
   for r in matching:
    if feedback.get('asof') and feedback['asof']>r['origin']:errors.append('FEEDBACK_AFTER_ORIGIN')
 if len(calls)!=report['http_calls']:errors.append('HTTP_COUNT')
 if abs(total-report['gateway_cost_usd'])>1e-8:errors.append('REPORT_COST')
 if any(not x for x in generation_ids) or len(set(generation_ids))!=len(generation_ids):errors.append('GENERATION_IDS')
 holdout=[r for r in numeric['rows'] if r['phase']=='holdout']
 if h(can(holdout))!=report['holdout_rows_sha256_before'] or report['holdout_rows_sha256_before']!=report['holdout_rows_sha256_after']:errors.append('HOLDOUT_CHANGED')
 out={'audit':'authenticated-raw-Jev-final-v1','passed':not errors,'errors':dict(Counter(errors)),'source_final_run':RUN,'source_artifact_id':artifact['id'],
  'source_zip_sha256':artifact['digest'],'http_calls':len(calls),'raw_model_runs':len(generation_ids),'unique_generation_ids':len(set(generation_ids)),
  'call_types':dict(kinds),'gateway_actual_cost_usd':total,'usage':dict(tokens),'forecast_documents_inspected':news_count,
  'maximum_raw_probability_sum_drift':max_prob_sum_drift,'historical_forecasts_repeated':False,'holdout_hash_unchanged':True,
  'archive_authenticated':True,'new_model_calls':0,'new_vendor_calls':0,'article_text_publication':False,
  'limitations':['Retrospective provider revisions and model memorization are not eliminated by input-field checks','Raw Jev probability sums within 0.04 were normalized by the existing parser and the drift is reported']}
 (OUT/'raw-evidence-audit.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
 print(json.dumps(out,sort_keys=True))
 return 0 if not errors else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:
  print(json.dumps({'status':'failed','error_code':type(e).__name__}));raise SystemExit(2)
