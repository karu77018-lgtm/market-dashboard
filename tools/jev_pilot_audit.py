"""Read-only numerical audit of persisted Jev requests/responses; no article text output."""
from __future__ import annotations
import argparse,hashlib,json,math,sqlite3
from pathlib import Path

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def number(v):
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if math.isfinite(r) and not isinstance(v,bool) else None

def audit(path):
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    check=db.execute('PRAGMA integrity_check').fetchone()[0]
    out={'schema_version':'jev-news-pilot-readback-audit-v1','integrity_ok':check=='ok','evaluations':0,'successful':0,
         'raw_model_runs':0,'question_answers':0,'input_state_hash_failures':0,'future_article_count':0,
         'future_price_rows':0,'no_news_tickers':[],'models':[],'article_ids_total':0,'unique_article_ids':0,
         'generation_ids_present':0,'known_cost_runs':0,'known_cost_usd':0,'input_tokens':0,'output_tokens':0,
         'direction_distribution_conflicts':[],'supplied_history_bars_min':None,'supplied_history_bars_max':None,
         'price_session':None,'forecast_asof':None,'neon_persisted_evaluations':0,'request_kinds':[],
         'article_characters_supplied':0,'errors':[]}
    models=set();articles=set();lens=[];kinds=set()
    for ticker,state_hash,reqraw,resraw,derivedraw,status,error in db.execute('SELECT ticker,state_hash,request_json,response_json,derived_json,status,error FROM evaluations'):
        out['evaluations']+=1;req=json.loads(reqraw);s=req['state'];cut=s['asof_timestamp'];session=s['price_session']
        out['forecast_asof']=cut;out['price_session']=session;kinds.add(req.get('evaluationKind'))
        out['input_state_hash_failures']+=hashlib.sha256(canonical(s).encode()).hexdigest()!=state_hash
        docs=s['news']['documents'];out['article_ids_total']+=len(docs)
        out['article_characters_supplied']+=sum(len(d.get('title',''))+len(d.get('description','')) for d in docs)
        if not docs:out['no_news_tickers'].append(ticker)
        for d in docs:
            articles.add(d['id']);out['future_article_count']+=d['published_utc']>cut
        lens.append(len(s['daily_history_last126']))
        out['future_price_rows']+=sum(r[0]>session for r in s['daily_history_last126'])
        if status!='success':out['errors'].append({'ticker':ticker,'error':error})
        if not resraw:continue
        res=json.loads(resraw)
        if res.get('persistence',{}).get('saved'):out['neon_persisted_evaluations']+=1
        for r in res.get('rawRuns',[]):
            out['raw_model_runs']+=1;out['question_answers']+=len(r.get('answers',{}))
            models.add(str(r.get('model') or res.get('model') or 'unknown'))
            meta=r.get('providerMetadata') or r.get('provider_metadata') or {}; g=meta.get('gateway') or {}
            if g.get('generationId'):out['generation_ids_present']+=1
            for k in ('cost','gatewayCost','inferenceCost'):
                v=number(g.get(k))
                if v is not None:out['known_cost_usd']+=v;out['known_cost_runs']+=1;break
            usage=r.get('usage') or {}
            for target,keys in [('input_tokens',('inputTokens','input_tokens')),('output_tokens',('outputTokens','output_tokens'))]:
                v=next((number(usage.get(k)) for k in keys if number(usage.get(k)) is not None),0)
                out[target]+=v
        if status=='success':
            out['successful']+=1;d=json.loads(derivedraw)
            for h in ('5','10'):
                dist=d['questions'][f'terminal_{h}d']['probabilities'];g=s['forecast_grid'][h]['terminal']
                positive=sum(dist[k] for k,b in g.items() if b['lower_pct_inclusive'] is not None and b['lower_pct_inclusive']>=0)
                possible=sum(dist[k] for k,b in g.items() if b['upper_pct_exclusive'] is None or b['upper_pct_exclusive']>0)
                p=d['questions'][f'up_{h}d']['probability_mean']
                if p<positive-.05 or p>possible+.05:
                    out['direction_distribution_conflicts'].append({'ticker':ticker,'horizon':int(h),'boolean_p':round(p,5),'distribution_p_bounds':[round(positive,5),round(possible,5)]})
    db.close();out['models']=sorted(models);out['unique_article_ids']=len(articles);out['request_kinds']=sorted(kinds)
    if lens:out['supplied_history_bars_min']=min(lens);out['supplied_history_bars_max']=max(lens)
    out['known_cost_usd']=round(out['known_cost_usd'],9)
    out['transport_and_storage_verified']=out['integrity_ok'] and out['input_state_hash_failures']==0 and out['future_article_count']==0 and out['future_price_rows']==0 and out['successful']>0
    out['calibration_status']='NOT_CALIBRATED_OR_BACKTESTED'
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    try:
        result=audit(a.db);Path(a.out).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(canonical(result))
        raise SystemExit(0 if result['transport_and_storage_verified'] else 2)
    except Exception:print('{"error":"PILOT_READBACK_AUDIT_FAILED"}');raise SystemExit(2)
