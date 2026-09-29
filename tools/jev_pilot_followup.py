"""Readback audit, one failed-name retry, and bounded six-name news ablation."""
import importlib.util,json,os,sqlite3,time,math,sys
from pathlib import Path
import requests

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    root=Path('.').resolve();work=root/'.private-pilot-check';out=root/'pilot-check-output';out.mkdir(exist_ok=True)
    p=load(root/'tools/jev_pilot/pilot.py','pilot');a=load(root/'tools/jev_pilot_audit.py','audit')
    audit=a.audit(work/'source.sqlite')
    db=sqlite3.connect(work/'source.sqlite');dest=sqlite3.connect(work/'followup.sqlite');db.backup(dest)
    dest.execute('CREATE TABLE followups(id INTEGER PRIMARY KEY,ticker TEXT,variant TEXT,state_hash TEXT,request_json TEXT,response_json TEXT,derived_json TEXT,http_status INTEGER,error TEXT,created_at TEXT)');dest.commit()
    example=db.execute("SELECT response_json FROM evaluations WHERE response_json IS NOT NULL LIMIT 1").fetchone()
    if example:
        r=json.loads(example[0]);raw=r.get('rawRuns',[{}])[0]
        audit['response_keys']=sorted(raw)
        audit['usage_example']=raw.get('usage')
        audit['metadata_key_shapes']={key:sorted(value) for key,value in raw.items() if isinstance(value,dict) and key not in ('answers','usage')}
    (out/'audit.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
    secret=os.environ['JEV_API_SECRET'];password=os.environ['ARCHIVE_PASSPHRASE']
    done=[];count=0
    tasks=[]
    for ticker,req in db.execute("SELECT ticker,request_json FROM evaluations WHERE status='failed' ORDER BY ticker LIMIT 1"):
        tasks.append((ticker,'retry_same_input',req,None))
    for ticker in ('HPE','NBIS','WDC','MRNA','TEAM','IOVA'):
        row=db.execute("SELECT request_json,derived_json FROM evaluations WHERE ticker=? AND status='success'",(ticker,)).fetchone()
        if row:tasks.append((ticker,'without_news',row[0],row[1]))
    for tk,variant,reqtext,original in tasks:
        if count>=7:break
        body=json.loads(reqtext)
        if variant=='without_news':
            body['state']['news']={'documents':[],'status':'INTENTIONALLY_WITHHELD_FOR_ABLATION_NOT_NO_NEWS'}
            body['state']['instructions']+=' News was intentionally withheld for a sensitivity comparison; do not conclude no material event exists.'
            body['state']['ablation']='news_withheld'
        encoded=p.canon(body)
        if secret in encoded or password in encoded:raise RuntimeError('unsafe')
        count+=1;payload=None;derived=None;error=None;status=None
        try:
            r=requests.post('https://jev-investment-engine.vercel.app/api/jev',headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'},data=encoded.encode(),timeout=(10,100),allow_redirects=False)
            status=r.status_code
            try:payload=r.json()
            except ValueError:payload=None
            if status!=200:raise p.SafeError('HTTP_'+str(status))
            derived=p.summarize(payload,body['state'])
        except p.SafeError as e:error=str(e)
        except requests.RequestException:error='NETWORK_OR_TIMEOUT'
        except Exception:error='PROCESSING_FAILED'
        dest.execute('INSERT INTO followups(ticker,variant,state_hash,request_json,response_json,derived_json,http_status,error,created_at) VALUES (?,?,?,?,?,?,?,?,?)',(tk,variant,p.sha(body['state']),encoded,p.canon(payload) if isinstance(payload,dict) else None,p.canon(derived) if derived else None,status,error,p.now()));dest.commit()
        result={'ticker':tk,'variant':variant,'http_status':status,'success':derived is not None,'error':error,'forecasts':derived['forecasts'] if derived else None}
        if error and isinstance(payload,dict):
            err=payload.get('error')
            result['api_error_code']=err if isinstance(err,str) and len(err)<80 and all(c.isalnum() or c in '_-' for c in err) else None
            result['error_response_keys']=sorted(payload)
        if original and derived:
            old=json.loads(original)
            result['change_from_with_news']={h:{'with_news_up_probability':old['forecasts'][h]['up_probability'],'without_news_up_probability':derived['forecasts'][h]['up_probability'],'delta_without_minus_with':round(derived['forecasts'][h]['up_probability']-old['forecasts'][h]['up_probability'],6)} for h in ('5','10')}
        done.append(result)
        print(json.dumps({'processed':count,'success':derived is not None,'variant':variant}),flush=True)
    db.close();dest.close()
    archive=load(root/'research/news_backfill/archive.py','archive')
    digest=archive.encrypt(work/'followup.sqlite',out/'followup.sqlite.gz.aesgcm',password)
    finalaudit=a.audit(work/'followup.sqlite')
    check=sqlite3.connect(work/'followup.sqlite');total_input=total_output=cost=0;known=0;rawcount=0
    for (text,) in check.execute('SELECT response_json FROM followups WHERE response_json IS NOT NULL'):
        resp=json.loads(text)
        for raw in resp.get('rawRuns',[]):
            rawcount+=1;md=raw.get('providerMetadata') or raw.get('provider_metadata') or {};g=md.get('gateway') or {}
            for key in ('cost','gatewayCost','inferenceCost'):
                n=a.number(g.get(key))
                if n is not None:cost+=n;known+=1;break
            use=raw.get('usage') or {}
            total_input+=a.number(use.get('inputTokens',use.get('input_tokens'))) or 0
            total_output+=a.number(use.get('outputTokens',use.get('output_tokens'))) or 0
    check.close()
    report={'schema_version':'jev-pilot-followup-v1','source_run':36581917771,'source_archive':11040085595,'api_requests':count,'max_reserved_budget_including_original':.32+count*.008,
            'new_raw_model_runs':rawcount,'new_known_cost_runs':known,'new_known_cost_usd':round(cost,9),'new_input_tokens':total_input,'new_output_tokens':total_output,
            'historical_validation_complete':False,'calibrated':False,'encrypted_sha256':digest,'results':done}
    (out/'followup-report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))

if __name__=='__main__':
    try:main()
    except Exception:print('{"error":"FOLLOWUP_FAILED"}');sys.exit(2)
