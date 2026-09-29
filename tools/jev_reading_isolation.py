#!/usr/bin/env python3
"""Separate repeated-batch, reordered-batch and single-case reading; no forecasts."""
import importlib.util,json,os,pathlib,sys,urllib.request,urllib.error
from datetime import datetime,timezone
P=pathlib.Path(__file__).resolve().parents[1]/'research/jev_material_reading/probe.py'
spec=importlib.util.spec_from_file_location('probe',P);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
OUT=pathlib.Path('reading-isolation-output');OUT.mkdir(exist_ok=True)
PRIOR_COST=.0026312579999999996
MAX_TOTAL=.02

def save(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
def jobs():
 c=p.cases();items=[]
 for start in [8,16]:items.append(('repeat_original_batch',c[start:start+8],p.payload(c[start:start+8],'plain')))
 for start in [8,16]:
  b=list(reversed(c[start:start+8]));items.append(('reordered_batch',b,p.payload(b,'plain')))
 for x in c:
  batch=[x];request=p.payload(batch,'plain');request['state']={'task':'Read this ONE supplied evidence passage only. This is a factual reading test, not a price forecast. Do not use external or remembered information.','evidence':x['text']}
  request['questions']['q0']['instructions']=x['question']+' Classify only what this evidence establishes. Missing evidence is unknown, not no. Do not infer any event from price movements.'
  items.append(('single_evidence',batch,request))
 fresh=[
 ('approval','Issuer Jori received a final refusal. The regulator explicitly rejected, rather than approved, the application.','What milestone was reached?','denied'),
 ('approval','Issuer Kumi obtained formal authorization from the regulator to market the product for the specified use. This is an approval, not merely acceptance for review.','What milestone was reached?','approved'),
 ('novelty','A report published today describes a contract. The contract date and earlier-publication history are absent.','Can the contract fact be verified as newly public today?','unknown'),
 ('novelty','A press release today states that its contract was signed and first announced today.','Does the item establish new information?','new')]
 for i,(g,t,q,gold) in enumerate(fresh):
  x={'id':f'f{i}','kind':'fresh_synthetic','group':g,'text':t,'question':q,'gold':gold,'sources':[]}
  req={'state':{'task':'Evaluate only the supplied evidence; do not use other cases or external knowledge.','evidence':t},'questions':{'q0':{'type':'choice','criteria':p.CHOICES[g],'instructions':q+' Missing evidence is unknown, not no.'}},'runs':3,'persist':False}
  items.append(('fresh_single_evidence',[x],req))
 return items

def main():
 j=jobs();assert len(j)==40
 for mode,b,req in j:assert 'gold' not in p.canon(req)
 save('frozen-plan.json',{'version':'jev-reading-isolation-v1','initial_run':36644478289,'initial_cost_usd':PRIOR_COST,'total_budget_usd':MAX_TOTAL,'planned_requests':len(j),'plans':[{'mode':m,'case_ids':[x['id'] for x in b],'payload_sha256':p.sha(r)} for m,b,r in j],'selection':'original failing batches, ALL 32 original tasks individually, four newly authored controls; original failures are preserved','production_changed':False,'not_stock_forecast':True})
 key=os.environ.get('JEV_API_SECRET');assert key
 rows=[];ledger=[];spent=0.;err=[];gids=[]
 for n,(mode,b,req) in enumerate(j,1):
  if PRIOR_COST+spent+.0015>MAX_TOTAL:err.append('BUDGET_CAP');break
  rec={'request_number':n,'mode':mode,'payload':req,'payload_sha256':p.sha(req),'started_at':datetime.now(timezone.utc).isoformat()}
  try:
   request=urllib.request.Request(p.URL,data=p.canon(req).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(request,timeout=155) as response:raw=response.read();rec['http_status']=response.status
   if key.encode() in raw:raise ValueError('SECRET_IN_RESPONSE')
   obj=json.loads(raw);rec['raw_response']=obj;cost,ids,tokens=p.costs(obj);spent+=cost;gids+=ids;rec['cost_usd']=cost;rec['usage']=tokens
   if obj.get('ok') is not True:raise ValueError('MODEL_RESPONSE_FAILED')
   decoded=p.decode(obj,req['questions'])
   for i,x in enumerate(b):
    a=decoded[f'q{i}'];rows.append({'id':x['id'],'mode':mode,'group':x['group'],'kind':x['kind'],'gold':x['gold'],**a,'correct':a['prediction']==x['gold'],'payload_sha256':p.sha(req)})
  except urllib.error.HTTPError as e:rec['error']='HTTP_'+str(e.code);err.append(rec['error'])
  except Exception as e:rec['error']=str(e) if isinstance(e,ValueError) else 'REQUEST_FAILED';err.append(rec['error'])
  save(f'call-{n:02d}.json',rec);ledger.append({k:v for k,v in rec.items() if k not in ['payload','raw_response']});save('scored-cases.json',rows)
  print(p.canon({'request':n,'mode':mode,'row_count':len(rows),'incremental_cost_usd':spent,'error':rec.get('error')}),flush=True)
  if err:break
 stats={}
 for mode in sorted({m for m,_,_ in j}):
  r=[x for x in rows if x['mode']==mode];stats[mode]={'n':len(r),'correct':sum(x['correct'] for x in r),'mean_agreement':sum(x['agreement'] for x in r)/len(r) if r else None,'wrong':[{'id':x['id'],'gold':x['gold'],'prediction':x['prediction'],'votes':x['votes']} for x in r if not x['correct']]}
 report={'version':'jev-reading-isolation-v1','status':'complete' if len(rows)==68 and not err else 'partial','requests':len(ledger),'unique_generation_ids':len(set(gids)),'incremental_cost_usd':spent,'total_with_initial_usd':spent+PRIOR_COST,'errors':err,'stats':stats,'new_price_forecasts':0,'production_changed':False,'limits':['Follow-up selected after observing two reading failures; not an unbiased benchmark','Single-case changes both format and workload, so improvement does not isolate a single mechanism','Four new controls test only local generalization, not trading skill']}
 save('report.json',report);save('cost-ledger.json',ledger);print(p.canon(report),flush=True)
 return 0 if report['status']=='complete' else 2
if __name__=='__main__':
 try:sys.exit(main())
 except Exception:print('{"status":"failed","error":"ISOLATION_TEST_FAILED"}');sys.exit(2)
