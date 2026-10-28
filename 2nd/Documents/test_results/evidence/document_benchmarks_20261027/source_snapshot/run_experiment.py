"""Document adaptations of A/B/R0 and unchanged FULL, with complete call evidence.

This is a controlled application of existing mechanisms to prose, not RAPTOR
reproduction and not the literal Python AST indexer. Protocol is frozen before
evaluation; inference never receives reference answers.
"""
from __future__ import annotations
import argparse, collections, fcntl, functools, gzip, itertools, json, math, os, random, re
import shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from types import SimpleNamespace
from common import ARMS, DATASETS, HERE, MODEL, OUT, Tokenizer, digest, dump, now, read, rows, sha, wrap

CONFIG={
 'version':'DOCUMENT-ABR0-FULL-1.0','arms':ARMS,'datasets':DATASETS,
 'scope':'Every unique publicly labelled SCROLLS validation question in four datasets; every LongBench v1 test item in three datasets. No subsampling.',
 'model_context':32768,'source_budget':1024,'catalog_budget':2048,
 'catalog_candidates':24,'selector_max_tokens':32,'max_expanded_nodes':8,
 'node_max_tokens':256,'preview_words':12,'repeats':1,'temperature':0,'seed':1,
 'order_seed':20261027,'prompt_cache':False,
 'answer_max_tokens':{'qmsum':512,'qasper':128,'narrative_qa':128,'quality':256,'hotpotqa':32,'musique':32,'multifieldqa_en':64},
 'A':'Lexical metadata/preview shortlist, one independent LLM selects one listed source ID; same-document reference expansion depth 1, at most 8 nodes; whole items within source budget.',
 'B':'Same catalog and independent LLM selection as A; references across supplied documents allowed, depth 2, at most 8 nodes; whole items within source budget.',
 'R0':'Original sublinear TF-IDF rules, raw-only IDF, atomic passages plus depth-3 rooted reference bundles. Descending cosine, whole candidate greedy packing; skip fully covered candidates; no semantic reranking.',
 'FULL':'Complete provided context, unchanged, no truncation. If wrapped prompt plus reserved output exceeds 32768, log context_overflow; no model request, empty prediction. Report completion coverage and matched fit-subset scores/cost separately.',
 'adaptation':'Prose has no Python functions/imports. Real source/heading/speaker/offset metadata plus first-12-word extractive previews replace symbols; explicit exact title/heading mentions and split-paragraph continuation replace references. They are document variants, not original code-index runs.',
 'catalog_scoring':'Same original code stopword list; 3*distinct overlap with preview/heading + distinct overlap with title; exact nonempty heading phrase bonus 20. Positive hits only; if none, source order. Stable ID tie break. Top 24, whole rows within 2048 tokens.',
 'selector_failure':'No repair/fallback. Invalid selection yields empty context and still one answer call. Score returned text with official metric; selector failure reported separately.',
 'metrics':'Official SCROLLS/LongBench task metrics, grouped references; truncated generation scored as emitted and flagged. No LLM judge. No ground-truth evidence recall invented.',
 'timing':'Per-query wall time includes metadata filtering/ranking, packing, selector and answer calls; prepared source/TF-IDF loading excluded and recorded separately. Independent calls for every arm; model prompt cache off.',
 'statistics':'Within each dataset paired differences; bootstrap clusters by SHA256(context.strip()), merging outer-whitespace variants without modifying inference text; 10000 draws seed 20261027. Multi-document inputs may share individual passages, so these are approximate source-context clusters, not proven independent documents. Descriptive 95% percentile intervals; no cross-task aggregate or confirmatory significance claim.',
 'prompts':'Pinned LongBench v1 templates for its 3 tasks and analogous QMSum/Qasper/NarrativeQA SCROLLS tasks; explicit answer-text instruction for QuALITY. Same answer template for every arm. This is zero-shot with a local coder model, not paper score reproduction.',
 'schedule':'Deterministically shuffle task IDs within each dataset, round-robin dataset blocks, all 24 arm permutations balanced cyclically. One deterministic pass; no quality-based tuning.',
}
STOPWORDS=set('answer class combine constant does exact file final for function given inside literal module number only return returns string the value what when with'.split())
PROMPTS=read(HERE/'official_sources/longbench/LongBench/config/dataset2prompt.json')

def words(text):
    text=re.sub(r'([a-z])([A-Z])',r'\1 \2',text).lower()
    result=[]
    for w in re.findall(r'[a-z][a-z0-9_]*|\d+',text):
        result.append(w)
        if '_' in w:result.extend(w.split('_'))
    return [w for w in result if len(w)>1]

def source_text(document,node):
    return f"### source {node['id']} document {node['doc_id']} chars {node['start']}-{node['end']}\n"+document['context'][node['start']:node['end']]

def expand(nodes,root,depth,same_doc=False,limit=None):
    byid={n['id']:n for n in nodes}; seen=set(); order=[];todo=collections.deque([(root,0)])
    while todo and (limit is None or len(order)<limit):
        uid,d=todo.popleft()
        if uid in seen:continue
        seen.add(uid)
        if same_doc and byid[uid]['doc_id']!=byid[root]['doc_id']:continue
        order.append(uid)
        if d<depth:todo.extend((x,d+1) for x in byid[uid]['deps'])
    return order

class Assets:
    def __init__(self,document):
        self.document=document;self.nodes=document['nodes'];self.byid={n['id']:n for n in self.nodes}
        self.items=[]
        fragments={n['id']:source_text(document,n) for n in self.nodes}
        for n in self.nodes:
            ids=expand(self.nodes,n['id'],3)
            self.items.append({'id':'bundle:'+n['id'],'root':n['id'],'source_ids':ids,'text':'\n\n'.join(fragments[u] for u in ids)})
            if len(ids)>1:
                self.items.append({'id':'atomic:'+n['id'],'root':n['id'],'source_ids':[n['id']],'text':fragments[n['id']]})
        df=collections.Counter()
        for item in self.items:df.update(set(words(item['text'])))
        self.idf={w:math.log((1+len(self.items))/(1+n))+1 for w,n in df.items()}
        self.unseen_idf=math.log(1+len(self.items))+1
        self.vectors=[self.vector(i['text']) for i in self.items]
    def vector(self,text):
        v={w:(1+math.log(n))*self.idf.get(w,self.unseen_idf) for w,n in collections.Counter(words(text)).items()}
        norm=math.sqrt(sum(x*x for x in v.values())) or 1
        return {w:x/norm for w,x in v.items()}
    def ranked(self,question):
        q=self.vector(question)
        scored=[(sum(x*v.get(w,0) for w,x in q.items()),i) for v,i in zip(self.vectors,self.items)]
        return sorted(scored,key=lambda p:(-p[0],p[1]['id']))

def catalog(asset,question,tok):
    terms=set(words(question))-STOPWORDS; q=question.casefold();scores=[]
    for n in asset.nodes:
        label=(n.get('heading','')+' '+n['preview']).strip()
        score=3*len(terms&set(words(label)))+len(terms&set(words(n.get('title',''))))
        if n.get('heading','').strip() and n['heading'].casefold() in q:score+=20
        if score:scores.append((score,n))
    if not scores:scores=[(1,n) for n in asset.nodes]
    scores.sort(key=lambda p:(-p[0],p[1]['id']))
    text='';chosen=[];rejected=[]
    for score,n in scores[:CONFIG['catalog_candidates']]:
        row=json.dumps({k:n[k] for k in ['id','doc_id','title','heading','start','end','preview']},ensure_ascii=False,separators=(',',':'))
        candidate=text+('\n' if text else '')+row
        if tok.tokens(candidate)<=CONFIG['catalog_budget']:
            text=candidate;chosen.append(n['id'])
        else:rejected.append(n['id'])
    return {'text':text,'ids':chosen,'rejected':rejected,'tokens':tok.tokens(text)}

def selector_prompt(question,index):
    return ('Choose the one source passage most relevant to the question. The catalog gives document titles, locations and short opening previews, not full passages. '
            'Return exactly one listed source id (for example n000001), with no explanation or other text.\n\nQuestion:\n'+question+'\n\nSource catalog:\n'+index+'\n\nSource id:')

def parse_selector(selection,index):
    match=re.fullmatch(r'n\d{6}',selection['answer'].strip())
    selected=match.group() if match else None
    response=selection.get('response',{})
    valid=selected in index['ids'] and selection['status']=='ok' and not response.get('stopped_limit',False) and response.get('stop_type')!='limit'
    return selected,valid

def answer_prompt(dataset,question,context):
    if dataset=='quality':
        return ('Read the article and answer the multiple-choice question. Return only the complete text of the correct option exactly as written, without its letter label or any explanation.\n\nArticle:\n'+context+'\n\nQuestion and options:\n'+question+'\n\nAnswer:')
    key='narrativeqa' if dataset=='narrative_qa' else dataset
    return PROMPTS[key].format(context=context,input=question)

def pack(ordered,tok):
    text='';seen=set();chosen=[];rejected=[]
    for score,item in ordered:
        if set(item['source_ids'])<=seen:continue
        candidate=text+('\n\n' if text else '')+item['text']
        if tok.tokens(candidate)<=CONFIG['source_budget']:
            text=candidate;seen.update(item['source_ids'])
            chosen.append({'id':item['id'],'source_ids':item['source_ids'],'score':score})
        else:rejected.append(item['id'])
    return text,chosen,rejected

class Client:
    def __init__(self,url,tok):self.url=url;self.tok=tok
    def get(self,path):
        with urllib.request.urlopen(self.url+path,timeout=30) as r:return json.load(r)
    def post(self,path,data,timeout=7200):
        req=urllib.request.Request(self.url+path,json.dumps(data).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
    def complete(self,prompt,max_tokens,task_id,arm,stage):
        key=digest(task_id+'|'+arm+'|'+stage);dest=OUT/'calls'/key[:2]/(key+'.json.gz')
        wrapped=wrap(prompt);n=self.tok.tokens(wrapped)
        request={'prompt':wrapped,'n_predict':max_tokens,'temperature':0,'seed':1,'cache_prompt':False,'id_slot':0,
                 'stop':['<|im_end|>','<|im_start|>'],'stream':False}
        if dest.exists():
            rec=read(dest);assert rec['request']==request
            assert rec['status'] in {'ok','context_overflow'}, ('Unresolved prior attempt; audit server/session before retry',str(dest),rec['status'])
            return rec,True
        start=time.perf_counter()
        rec={'key':key,'task_id':task_id,'arm':arm,'stage':stage,'request':request,'started_at_utc':now(),
             'requested_input_tokens':n,'input_tokens':0,'output_tokens':0,'answer':'','status':'pending'}
        if n+max_tokens>CONFIG['model_context']:
            rec['status']='context_overflow'
        else:
            # Persist intent before an actual request; an uncertain request is never silently retried.
            dump(dest,rec)
            try:
                response=self.post('/completion',request)
            except Exception as exc:
                rec.update(status='transport_error',error=repr(exc),ended_at_utc=now(),wall_seconds=time.perf_counter()-start,
                           execution_cost_unknown=True)
                dump(dest,rec);raise
            rec.update(response=response,answer=response.get('content','').strip(),input_tokens=n,
                       output_tokens=response.get('tokens_predicted',0),status='received',
                       ended_at_utc=now(),wall_seconds=time.perf_counter()-start)
            dump(dest,rec)
            if response.get('truncated',False) or response.get('tokens_evaluated',n)!=n:
                rec['status']='response_invalid';dump(dest,rec)
                raise RuntimeError(('Input truncation or token count mismatch; response retained',n,response.get('tokens_evaluated')))
            rec['status']='ok'
        rec.update(ended_at_utc=now(),wall_seconds=time.perf_counter()-start)
        dump(dest,rec)
        return rec,False

def make_schedule(tasks):
    rng=random.Random(CONFIG['order_seed']);groups={d:[] for d in DATASETS};plan=[]
    for t in tasks:groups[t['dataset']].append(t)
    for group in groups.values():rng.shuffle(group)
    orders=list(itertools.permutations(ARMS));rng.shuffle(orders);i=0
    while any(groups.values()):
        for d in DATASETS:
            if not groups[d]:continue
            t=groups[d].pop();order=orders[i%len(orders)];i+=1
            plan.extend({'task_id':t['task_id'],'arm':a} for a in order)
    return plan

def freeze():
    assert not (OUT/'protocol.json').exists(),'Protocol already frozen'
    manifest=read(OUT/'data_manifest.json');tasks=rows(OUT/'tasks.jsonl')
    assert set(t['dataset'] for t in tasks)==set(DATASETS)
    assert len(tasks)==len({t['task_id'] for t in tasks})
    verified=read(OUT/'prepared_verification.json')
    assert verified['status']=='PASS' and verified['questions']==len(tasks)
    assert verified['tasks_sha256']==sha(OUT/'tasks.jsonl') and verified['data_manifest_sha256']==sha(OUT/'data_manifest.json')
    assert set(verified['datasets'])==set(DATASETS)
    assert (OUT/'analysis_plan.json').is_file(),'Analysis plan must be fixed before evaluation'
    dump(OUT/'schedule.json',make_schedule(tasks))
    sources=[p for p in HERE.glob('*') if p.suffix in {'.py','.cpp','.dylib','.md','.json','.lock'}]+[p for p in (HERE/'official_sources').rglob('*') if p.is_file()]
    hashes={str(p):sha(p) for p in sources}
    for p in sources:
        dest=OUT/'source_snapshot'/p.relative_to(HERE);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    report=OUT.parent.parent/'03_현재색인_A와_파일간확장_B_재실험_비교보고서.md'
    (OUT/'history').mkdir(exist_ok=True);shutil.copy2(report,OUT/'history'/report.name)
    dump(OUT/'protocol.json',{'config':CONFIG,'frozen_at_utc':now(),'source_hashes':hashes,
        'data_manifest_sha256':sha(OUT/'data_manifest.json'),'tasks_sha256':sha(OUT/'tasks.jsonl'),
        'schedule_sha256':sha(OUT/'schedule.json'),'analysis_plan_sha256':sha(OUT/'analysis_plan.json'),
        'prepared_verification_sha256':sha(OUT/'prepared_verification.json'),
        'source_clusters_sha256':sha(OUT/'source_clusters.json'),'model_sha256':sha(MODEL),
        'server_binary_sha256':sha('/opt/homebrew/bin/llama-server'),'report_before_sha256':sha(report)})
    print(json.dumps({'status':'frozen','questions':len(tasks),'evaluation_answers':len(tasks)*len(ARMS)}),flush=True)

def validate():
    p=read(OUT/'protocol.json');assert p['config']==CONFIG
    for name in ['data_manifest','tasks','schedule']:
        path=OUT/(name+('.jsonl' if name=='tasks' else '.json'));assert sha(path)==p[name+'_sha256']
    for path,h in p['source_hashes'].items():assert sha(path)==h,path
    assert sha(OUT/'analysis_plan.json')==p['analysis_plan_sha256']
    assert sha(OUT/'prepared_verification.json')==p['prepared_verification_sha256']
    assert sha(OUT/'source_clusters.json')==p['source_clusters_sha256']
    assert sha(MODEL)==p['model_sha256'],'Model file changed'
    assert sha('/opt/homebrew/bin/llama-server')==p['server_binary_sha256'],'Inference engine changed'

def committed_results():
    files=sorted((OUT/'results').glob('*.json.gz'))
    assert [p.name for p in files]==[f'{i:08d}.json.gz' for i in range(len(files))], 'Noncontiguous committed results'
    return [read(p) for p in files]

def run(url,limit=None):
    validate();tok=Tokenizer();client=Client(url,tok);props=client.get('/props')
    assert props['default_generation_settings']['n_ctx']==CONFIG['model_context']
    assert Path(props['model_path']).resolve()==MODEL.resolve()
    if not (OUT/'environment.json').exists():dump(OUT/'environment.json',{'started_at_utc':now(),'server_props':props,'python':sys.version,'pid':os.getpid()})
    tasks={t['task_id']:t for t in rows(OUT/'tasks.jsonl')};plan=read(OUT/'schedule.json')
    prior=committed_results();assert [{k:r[k] for k in ['task_id','arm']} for r in prior]==plan[:len(prior)]
    # JSONL is a convenient projection; atomic per-query files are authoritative on restart.
    temp=OUT/'results.jsonl.part'
    with temp.open('w') as f:
        for r in prior:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
    os.replace(temp,OUT/'results.jsonl')
    manifest=read(OUT/'data_manifest.json')
    @functools.lru_cache(maxsize=3)
    def load_document(document_id):
        start=time.perf_counter();path=OUT/'documents'/(document_id+'.json.gz')
        assert sha(path)==manifest['document_files'][document_id]['sha256'],('Changed prepared document',document_id)
        d=read(path);assert digest(d['context'])==document_id
        with (OUT/'asset_load_times.jsonl').open('a') as f:f.write(json.dumps({'document_id':document_id,'phase':'read_document','seconds':time.perf_counter()-start,'at':now()})+'\n')
        return d
    @functools.lru_cache(maxsize=3)
    def load_assets(document_id):
        start=time.perf_counter();asset=Assets(load_document(document_id))
        with (OUT/'asset_load_times.jsonl').open('a') as f:f.write(json.dumps({'document_id':document_id,'phase':'build_tfidf','seconds':time.perf_counter()-start,'at':now()})+'\n')
        return asset
    session=digest(now())[:16];dump(OUT/f'session_{session}.json',{'pid':os.getpid(),'started_at_utc':now(),'resumed_rows':len(prior)})
    total=0
    for i,entry in enumerate(plan):
        if i<len(prior):continue
        t=tasks[entry['task_id']];arm=entry['arm'];document=load_document(t['document_id'])
        asset=load_assets(t['document_id']) if arm=='R0' else SimpleNamespace(document=document,nodes=document['nodes'],byid={n['id']:n for n in document['nodes']})
        tok.tokens.cache_clear()
        start=time.perf_counter();started=now()
        selected=None;index=None;selection_valid=None;calls=[];resumed=False;chosen=[];rejected=[]
        if arm=='FULL':context=asset.document['context']
        elif arm=='R0':context,chosen,rejected=pack(asset.ranked(t['question']),tok)
        else:
            index=catalog(asset,t['question'],tok)
            selection,cached=client.complete(selector_prompt(t['question'],index['text']),CONFIG['selector_max_tokens'],t['task_id'],arm,'select')
            calls.append(selection);resumed|=cached
            selected,selection_valid=parse_selector(selection,index)
            ids=expand(asset.nodes,selected,1 if arm=='A' else 2,same_doc=arm=='A',limit=CONFIG['max_expanded_nodes']) if selection_valid else []
            ordered=[(0,{'id':'selected:'+uid,'source_ids':[uid],'text':source_text(asset.document,asset.byid[uid])}) for uid in ids]
            context,chosen,rejected=pack(ordered,tok)
        preparation=time.perf_counter()-start
        call,cached=client.complete(answer_prompt(t['dataset'],t['question'],context),CONFIG['answer_max_tokens'][t['dataset']],t['task_id'],arm,'answer')
        calls.append(call);resumed|=cached
        wall=time.perf_counter()-start
        row={**entry,'dataset':t['dataset'],'document_id':t['document_id'],'session_id':session,
            'started_at_utc':started,'ended_at_utc':now(),'status':call['status'],'prediction':call['answer'],
            'call_keys':[c['key'] for c in calls],'selected':selected,'selection_valid':selection_valid,'catalog':index,
            'chosen':chosen,'rejected':rejected,'context':context if arm!='FULL' else None,
            'context_sha256':digest(context),'context_tokens':tok.tokens(context),
            'input_tokens':sum(c['input_tokens'] for c in calls),'output_tokens':sum(c['output_tokens'] for c in calls),
            'peak_input_tokens':max(c['input_tokens'] for c in calls),'requested_answer_input_tokens':call['requested_input_tokens'],
            'query_seconds':wall if not resumed else None,'calls_seconds':sum(c['wall_seconds'] for c in calls),
            'pre_answer_seconds':preparation,'resumed_partial_query':resumed,
            'output_limit':bool(call.get('response',{}).get('stopped_limit',False) or call.get('response',{}).get('stop_type')=='limit')}
        dump(OUT/'results'/f'{i:08d}.json.gz',row)
        with (OUT/'results.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
        dump(OUT/'progress.json',{'pid':os.getpid(),'session_id':session,'completed':i+1,'planned':len(plan),'last':entry,'at':now(),'status':'running'})
        print(json.dumps({'completed':i+1,'planned':len(plan),'dataset':t['dataset'],'arm':arm,'status':call['status'],'input_tokens':row['input_tokens'],'seconds':round(wall,2)}),flush=True)
        total+=1
        if limit and total>=limit:return
    dump(OUT/'completed.json',{'completed_at_utc':now(),'rows':len(plan),'results_sha256':sha(OUT/'results.jsonl')})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','run']);p.add_argument('--url',default='http://127.0.0.1:8766');p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.phase=='freeze':freeze()
    else:
        with (OUT/'runner.lock').open('a+') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            lock.seek(0);lock.truncate();lock.write(str(os.getpid())+'\n');lock.flush()
            run(a.url,a.limit)
