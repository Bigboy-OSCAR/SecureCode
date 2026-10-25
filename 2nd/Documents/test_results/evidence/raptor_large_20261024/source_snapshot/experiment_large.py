"""Four fresh, interleaved arms on behavior-preserving enlarged Python files."""
from __future__ import annotations
import argparse, ast, itertools, json, random, shutil, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
import experiment_full as small
import audit_v2 as offline

original, audited, ab = small.original, small.audited, small.ab
read = small.read
DEFAULT_OUT = original.DEFAULT_OUT / 'large_files_20261024'
ARMS = ['A', 'B', 'R0', 'FULL']
CONFIG = {
    'version':'LARGE-1.0', 'arms':ARMS, 'repeats':3, 'questions':96,
    'retrieved_code_cap':1024, 'full_file_cap':None, 'model_context':8192,
    'selector_candidates':24, 'selector_max_tokens':96, 'answer_max_tokens':128,
    'temperature':0, 'seed':1, 'order_seed':20261024, 'prompt_cache':False,
    'minimum_file_tokens':4096,
    'corpus':'Add unrelated executable utility functions to each of the five files. Preserve every original source node body, import and reference edge; reexecute all original gold operations. Original code block at beginning/middle/end, two evaluation projects per location.',
    'size_interpretation':'Controlled synthetic distractor growth, not naturally large independent repositories or intrinsically longer relevant functions. More candidate symbols and shifted line metadata accompany file growth.',
    'schedule':'96 task blocks per repeat shuffled; each contains all four fresh arms. Four Williams orders balanced four times per project per repeat.',
    'retrieval':'Unchanged A native same-file, B two-hop cross-file and R0 TF-IDF raw ranking/packing; no summaries, learned embeddings, shared inference, gold-based retrieval, or outcome-based tuning.',
    'full_file':'Target defining-file path supplied in advance; read whole file including distractors verbatim. No selector, truncation, added headers, or expansion to imported files.',
    'timing':'Physical query wall time includes selector/ranking/file-read, packing/tokenization, model answer and small call-log write; excludes graph/index/vector preparation, server startup and grading.',
    'primary_quality':'Exact JSON value, type and requested list order; selector failure counts as incorrect for A/B.',
    'primary_latency':'Mean over questions of three-run median query seconds.',
    'inference':'Six project-cluster bootstrap 6^6 draws, six new within-large quality contrasts with Holm-adjusted project sign-flip p values. Historical-small comparisons descriptive, especially timing.',
    'historical_small':'Preserved actual 1152 small-file answers; no newly generated small-file claims.',
}


def extra_function(module, index):
    names = ['event_text','batches','histogram','trimmed_text','unique_items','encoded_pair',
             'moving_average','table_rows','missing_fields','flat_cells','merged_fields','byte_count']
    name = f'aux_{module}_{index:03d}_{names[index%12]}'
    templates = [
        "(event, fields):\n    parts = [str(event).strip()]\n    for key in sorted(fields):\n        value = str(fields[key]).replace('\\n', ' ')\n        parts.append(str(key) + '=' + value)\n    return ' | '.join(parts)\n",
        "(values, width):\n    if width < 1:\n        raise ValueError('width must be positive')\n    batches = []\n    for offset in range(0, len(values), width):\n        batches.append(list(values[offset:offset + width]))\n    return batches\n",
        "(labels):\n    counts = {}\n    for label in labels:\n        text = str(label).strip().lower()\n        if text:\n            counts[text] = counts.get(text, 0) + 1\n    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))\n",
        "(value, limit):\n    text = ' '.join(str(value).split())\n    if limit < 0:\n        raise ValueError('negative text limit')\n    if len(text) <= limit:\n        return text\n    if limit < 3:\n        return text[:limit]\n    return text[:limit - 3] + '...'\n",
        "(values):\n    seen = set()\n    unique = []\n    for value in values:\n        marker = str(value).strip()\n        if marker not in seen:\n            seen.add(marker)\n            unique.append(value)\n    return unique\n",
        "(key, value):\n    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]\n    parts = []\n    for item in [key, value]:\n        text = str(item)\n        for source, target in replacements:\n            text = text.replace(source, target)\n        parts.append(text)\n    return '='.join(parts)\n",
        "(numbers, width):\n    if width < 1:\n        raise ValueError('width must be positive')\n    averages = []\n    for stop in range(1, len(numbers) + 1):\n        window = numbers[max(0, stop - width):stop]\n        averages.append(sum(window) / len(window))\n    return averages\n",
        "(records, columns):\n    rendered = []\n    rendered.append(','.join(str(column) for column in columns))\n    for record in records:\n        cells = []\n        for column in columns:\n            text = str(record.get(column, '')).replace(',', ';')\n            cells.append(text)\n        rendered.append(','.join(cells))\n    return '\\n'.join(rendered)\n",
        "(record, required):\n    missing = []\n    for field in required:\n        value = record.get(field)\n        if value is None or (isinstance(value, str) and not value.strip()):\n            missing.append(field)\n    return sorted(set(missing))\n",
        "(groups):\n    cells = []\n    for group in groups:\n        if group is None:\n            continue\n        for cell in group:\n            if cell is not None:\n                cells.append(str(cell))\n    return cells\n",
        "(base, overrides):\n    merged = dict(base)\n    for key, value in overrides.items():\n        if value is None:\n            merged.pop(key, None)\n        else:\n            merged[key] = value\n    return {key: merged[key] for key in sorted(merged)}\n",
        "(chunks, padding):\n    if padding < 0:\n        raise ValueError('negative padding')\n    total = 0\n    for chunk in chunks:\n        encoded = str(chunk).encode('utf-8')\n        total += len(encoded) + padding\n    return total\n",
    ]
    return 'def ' + name + templates[index%12]


def enlarged(source, module, count, position):
    tree=ast.parse(source);lines=source.splitlines(keepends=True)
    imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    end=max((n.end_lineno for n in imports),default=0)
    prefix=''.join(lines[:end]).rstrip()
    original_body=''.join(lines[end:]).strip('\n')
    extras=[extra_function(module,i).rstrip() for i in range(count)]
    split={'beginning':0,'middle':count//2,'end':count}[position]
    return '\n\n'.join(([prefix] if prefix else [])+extras[:split]+[original_body]+extras[split:])+'\n'


def make_plan(tasks):
    rng=random.Random(CONFIG['order_seed']);plan=[]
    orders=[['A','B','FULL','R0'],['B','R0','A','FULL'],['R0','FULL','B','A'],['FULL','A','R0','B']]
    for repeat in range(3):
        blocks=[]
        for project in sorted({t['project'] for t in tasks}):
            selected=sorted([t for t in tasks if t['project']==project],key=lambda t:t['id'])
            rng.shuffle(selected);assigned=orders*4;rng.shuffle(assigned)
            assert len(selected)==16
            blocks.extend((t,order) for t,order in zip(selected,assigned))
        rng.shuffle(blocks)
        for task,order in blocks:
            plan.extend({'task_id':task['id'],'repeat':repeat,'arm':arm} for arm in order)
    return plan


def prepare(out):
    assert not (out/'protocol.json').exists(),'Choose a fresh output directory'
    small.validate_frozen(small.DEFAULT_OUT)
    ab.validate_frozen(ab.DEFAULT_OUT)
    out.mkdir(parents=True,exist_ok=True)
    source_inputs={}
    for name in ['tasks.json','dev_tasks.json','gold_operations.json']:
        source=ab.DEFAULT_OUT/name;shutil.copy2(source,out/name);source_inputs[str(source)]=original.sha(source)
    for directory in [ab.DEFAULT_OUT,small.r0.DEFAULT_OUT,small.DEFAULT_OUT]:
        for name in ['results.jsonl','summary.json','verification.json','protocol.json','environment.json']:
            source_inputs[str(directory/name)]=original.sha(directory/name)
    tasks,dev=read(out/'tasks.json'),read(out/'dev_tasks.json')
    projects=sorted({t['project'] for t in tasks})
    positions={p:['beginning','middle','end'][i%3] for i,p in enumerate(projects)}
    positions.update({t['project']:'middle' for t in dev})
    sources={}
    for project in sorted(positions):
        for source in sorted((ab.DEFAULT_OUT/'projects'/project).glob('*.py')):
            sources[(project,source.name)]=source.read_text()
            source_inputs[str(source)]=original.sha(source)
    # Choose the smallest function count crossing the declared token threshold.
    # Only tokenizer lengths are inspected here, never model answers or gold labels.
    grid={}
    for key,source in sources.items():
        project,file=key
        for count in [32,48,64,80]:grid[(key,count)]=enlarged(source,Path(file).stem,count,positions[project])
    lengths,tokenizer=offline.tokenize_many(sorted(set(grid.values())),original.MODEL)
    fine={}
    for key in sources:
        upper=min(n for n in [32,48,64,80] if lengths[grid[(key,n)]]>=4096)
        for n in range(max(0,upper-16),upper+1):fine[(key,n)]=enlarged(sources[key],Path(key[1]).stem,n,positions[key[0]])
    exact,_=offline.tokenize_many(sorted(set(fine.values())),original.MODEL)
    original_lengths,_=offline.tokenize_many(sorted(set(sources.values())),original.MODEL)
    files=[]
    for key,source in sources.items():
        n=min(n for k,n in fine if k==key and exact[fine[(k,n)]]>=4096)
        text=fine[(key,n)];project,file=key
        path=out/'projects'/project/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        before=ast.parse(source);after=ast.parse(text)
        kept=[node for node in after.body if not (isinstance(node,ast.FunctionDef) and node.name.startswith('aux_'))]
        assert ast.dump(ast.Module(body=kept,type_ignores=[]))==ast.dump(before),key
        assert 4096<=exact[text]<4500
        files.append({'project':project,'path':file,'original_tokens':original_lengths[source],'large_tokens':exact[text],
            'original_lines':len(source.splitlines()),'large_lines':len(text.splitlines()),'added_functions':n,
            'original_position':positions[project],'source_sha256':original.sha(path)})
    assets={};prep={};old_assets=read(ab.DEFAULT_OUT/'assets.json')
    for project in sorted(positions):
        root=out/'projects'/project;start=time.perf_counter()
        index=original.build_index(root);index_seconds=time.perf_counter()-start;start=time.perf_counter()
        nodes=original.source_nodes(root);graph_seconds=time.perf_counter()-start;start=time.perf_counter()
        raw=original.raw_items(nodes);raw_seconds=time.perf_counter()-start
        for uid,node in old_assets[project]['nodes'].items():
            for field in ['source','imports','refs','deps','kind']:assert nodes[uid][field]==node[field],(uid,field)
        assets[project]={'index':index,'nodes':nodes,'raw':raw}
        prep[project]={'index_seconds':index_seconds,'graph_seconds':graph_seconds,'raw_seconds':raw_seconds,
            'symbols':len(index['symbols']),'raw_candidates':len(raw),'scope':'One warm-filesystem build; not cold-start benchmarking'}
    original.dump(out/'assets.json',assets);original.dump(out/'preparation.json',prep)
    original.dump(out/'corpus_manifest.json',{'files':files,'positions':positions,'tokenizer':tokenizer,
        'original_nodes_preserved':True,'transform_uses_questions_or_answers':False})
    original.dump(out/'file_map.json',{t['id']:assets[t['project']]['nodes'][t['target_uri']]['path'] for t in tasks+dev})
    original.dump(out/'gold_recheck.json',ab.verify_gold(out,tasks,read(out/'gold_operations.json')))
    original.dump(out/'schedule.json',make_plan(tasks))
    history=out/'history';history.mkdir(exist_ok=True)
    shutil.copy2(small.r0.REPORT,history/'report_before_large_files.md')
    snapshots=out/'source_snapshot';snapshots.mkdir(exist_ok=True)
    code=list(dict.fromkeys([Path(__file__),Path(offline.__file__),Path(small.__file__),Path(small.r0.__file__),*ab.inputs()]))
    for path in code:shutil.copy2(path,snapshots/path.name)
    original.dump(out/'protocol.json',{**CONFIG,'frozen_at_utc':audited.now(),'source_input_hashes':source_inputs,
        'code_hashes':{str(p):original.sha(p) for p in code},
        'frozen_files':{str(p.relative_to(out)):original.sha(p) for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'status':'PREPARED','questions':96,'planned_answers':1152,'file_tokens':[min(f['large_tokens'] for f in files),max(f['large_tokens'] for f in files)],'gold_rechecked':96}),flush=True)


def validate_frozen(out):
    protocol=read(out/'protocol.json')
    assert all(protocol[k]==v for k,v in CONFIG.items())
    for group,root in [('code_hashes',None),('source_input_hashes',None),('frozen_files',out)]:
        for p,h in protocol[group].items():assert original.sha(root/p if root else p)==h,p


def run(out,url,dev=False):
    validate_frozen(out)
    client=audited.AuditedClient(out,url);environment=audited.runtime_environment(client)
    assert environment['fingerprint']==read(ab.DEFAULT_OUT/'environment.json')['fingerprint']
    if (out/'environment.json').exists():assert read(out/'environment.json')['fingerprint']==environment['fingerprint']
    else:original.dump(out/'environment.json',environment)
    tasks=read(out/('dev_tasks.json' if dev else 'tasks.json'));byid={t['id']:t for t in tasks}
    assets=read(out/'assets.json');file_map=read(out/'file_map.json');retrievers={};vector_times={}
    for project,asset in assets.items():
        start=time.perf_counter();retriever=original.Retriever(asset['raw']);retriever.ranked('',asset['raw'])
        vector_times[project]=time.perf_counter()-start;retrievers[project]=retriever
    plan=([{'task_id':t['id'],'repeat':0,'arm':arm} for t in tasks for arm in ARMS] if dev else read(out/'schedule.json'))
    dest=out/('results_dev.jsonl' if dev else 'results.jsonl');prior=audited.rows(dest)
    assert [{k:r[k] for k in ['task_id','repeat','arm']} for r in prior]==plan[:len(prior)]
    session_id=audited.digest([audited.now(),dev])[:20]
    original.dump(out/f'session_{session_id}.json',{'started_at_utc':audited.now(),'dev':dev,'resume_after_rows':len(prior),'environment':environment,'vector_build_seconds':vector_times})
    client.reset_query();assert client.complete('Return only {"answer":0}.','warmup',32,{'session_id':session_id})['ok']
    for i,entry in enumerate(plan):
        if i<len(prior):continue
        task,arm=byid[entry['task_id']],entry['arm'];asset=assets[task['project']];root=out/'projects'/task['project']
        meta={**entry,'dev':dev,'session_id':session_id};selector=None;selected=None;valid=None
        selection_seconds=expansion_seconds=retrieval_seconds=0.0
        client.reset_query();started,utc=time.perf_counter(),audited.now()
        if arm in ['A','B']:
            outline=original._candidate_symbol_outline(asset['index'],task['question'],24)
            selector=client.complete(original._selector_prompt(task['question'],outline),'select',96,meta)
            selection_seconds=time.perf_counter()-started;phase=time.perf_counter()
            ordered,selected,valid=(audited.baseline_ordered(asset,root,{'question':task['question']},selector) if arm=='A' else ab.b_ordered(asset,{'question':task['question']},selector))
            expansion_seconds=time.perf_counter()-phase
        elif arm=='R0':
            ordered=retrievers[task['project']].ranked(task['question'],asset['raw'])
            retrieval_seconds=time.perf_counter()-started
        else:
            context=(root/file_map[task['id']]).read_text()
            retrieval_seconds=time.perf_counter()-started
        phase=time.perf_counter()
        if arm=='FULL':
            token_count=client.tokens(context);chosen=[];rejected=[]
        else:context,token_count,chosen,rejected=original.pack(client,ordered,1024)
        packing_seconds=time.perf_counter()-phase;pre_answer=time.perf_counter()-started
        call=client.complete(original.answer_prompt(task['question'],context),'answer',128,meta)
        seconds,ended=time.perf_counter()-started,audited.now()
        correct,parsed,failure=original.evaluate_answer(call,task['expected'])
        if arm in ['A','B'] and not valid:correct,failure=False,'selector_invalid'
        target_path=file_map[task['id']]
        if arm=='FULL':
            sources={u for u,n in asset['nodes'].items() if n['path']==target_path}
            chosen=[{'id':'file://'+target_path,'level':0,'score':None,'source_uris':sorted(sources)}]
        else:sources={u for c in chosen for u in c['source_uris']}
        required=set(task['required_uris'])
        row={**entry,'session_id':session_id,'split':task['split'] if 'split' in task else 'development',
            'project':task['project'],'category':task['category'],'question':task['question'],'expected':task['expected'],
            'correct':correct,'parsed_answer':parsed,'failure':failure,'selector':selector,'answer_call':call,
            'selected_uri':selected,'selection_valid':valid,'selection_correct':selected==task['target_uri'] if selector else None,
            'provided_file':target_path if arm=='FULL' else None,'context':context,'context_tokens':token_count,
            'selected_context_tokens':token_count,'chosen':chosen,'rejected':rejected,
            'query_seconds':seconds,'select_seconds':selection_seconds,'expansion_seconds':expansion_seconds,
            'retrieval_seconds':retrieval_seconds,'packing_seconds':packing_seconds,'pre_answer_seconds':pre_answer,
            'started_at_utc':utc,'ended_at_utc':ended,'tokenize_http_calls':client.token_http_count,'tokenize_seconds':client.token_seconds,
            'input_tokens':call['input_tokens']+(selector['input_tokens'] if selector else 0),
            'output_tokens':(call['output_tokens'] or 0)+((selector['output_tokens'] or 0) if selector else 0),
            'raw_evidence_recall':len(required&sources)/len(required),'all_raw_evidence':required<=sources,
            'unique_source_count':len(sources),'cross_file_source_count':sum(asset['nodes'][u]['path']!=target_path for u in sources),
            'source_files':sorted({asset['nodes'][u]['path'] for u in sources}),'compaction_seconds':0}
        with dest.open('a') as handle:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(f"{'dev' if dev else 'eval'} {i+1}/{len(plan)} {task['id']} {arm} r{entry['repeat']} correct={int(correct)} code={token_count} input={row['input_tokens']} seconds={seconds:.3f}",flush=True)
        if 'error' in call or (selector and 'error' in selector):raise RuntimeError('Transport/context error recorded; inspect before resuming')
    original.dump(out/f"completed_{'dev' if dev else 'eval'}.json",{'completed_at_utc':audited.now(),'rows':len(plan),'results_sha256':original.sha(dest),'session_id':session_id})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','dev','run']);p.add_argument('--out',type=Path,default=DEFAULT_OUT);p.add_argument('--url',default='http://127.0.0.1:8766')
    args=p.parse_args();prepare(args.out) if args.phase=='prepare' else run(args.out,args.url,args.phase=='dev')
