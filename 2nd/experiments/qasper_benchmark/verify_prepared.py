"""Independent raw-to-task accounting and exact source coverage audit, before inference."""
from __future__ import annotations
import collections, functools, json, re, time
from common import DATASETS, OUT, Tokenizer, digest, dump, read, rows, sha

def verify():
    started=time.perf_counter();manifest=read(OUT/'data_manifest.json');tasks=rows(OUT/'tasks.jsonl')
    bykey={(t['dataset'],t['source_id']):t for t in tasks}
    assert len(bykey)==len(tasks)==len({t['task_id'] for t in tasks})
    expected=collections.defaultdict(list);raw_counts={};checks=[];tok=Tokenizer()
    @functools.lru_cache(maxsize=3)
    def doc(uid):
        p=OUT/'documents'/(uid+'.json.gz');m=manifest['document_files'][uid]
        assert sha(p)==m['sha256'];d=read(p);assert digest(d['context'])==uid
        return d
    for dataset in DATASETS:
        raw=OUT/'raw'/(dataset+'.jsonl');count=0
        with raw.open() as f:
            for line in f:
                r=json.loads(line);count+=1;source_id=r.get('id',r.get('_id'));key=(dataset,source_id)
                assert key in bykey,('Missing raw question',key)
                t=bykey[key];d=doc(t['document_id'])
                assert t['raw_input_sha256']==digest(r['input'])
                if 'context' in r:
                    assert t['question']==r['input'] and d['context']==r['context'] and t['input_prefix']==''
                    expected[key].extend(r['answers'])
                else:
                    assert t['input_prefix']+d['context']==r['input'],('Source reconstruction',key)
                    assert t['question']+'\n\n'==t['input_prefix'],('Question extraction',key)
                    expected[key].append(r['output'])
                    if dataset=='quality':
                        assert re.findall(r'^\s*\(([A-D])\)',t['question'],re.M)==list('ABCD'),key
        raw_counts[dataset]={'raw_rows':count,'unique_questions':sum(k[0]==dataset for k in expected),'sha256':sha(raw)}
    assert set(expected)==set(bykey)
    for key,refs in expected.items():
        assert collections.Counter(bykey[key]['references'])==collections.Counter(refs),('Lost reference answer',key)
    checks.extend(['Every raw unique ID appears exactly once','Every reference answer retained with multiplicity','Original input reconstructs exactly','Question and QuALITY choices retained outside document'])
    graph_counts={};clusters={};used={t['document_id'] for t in tasks}
    assert used==set(manifest['document_files'])
    for uid in sorted(used):
        d=doc(uid);context=d['context'];nodes=d['nodes'];node_ids={n['id'] for n in nodes}
        clusters[uid]=digest(context.strip())
        assert len(node_ids)==len(nodes)
        cursor=0;edge_count=0;cross_count=0;byid={n['id']:n for n in nodes}
        roots={x['doc_id']:x for x in d['roots']}
        headings=d['headings']
        for h in headings:
            assert context[h['start']:h['end']].strip()==h['text']
            target=byid[h['target_id']]
            assert target['start']<=h['start']<target['end'] and target['doc_id']==h['doc_id']
        def literal_mention(label,body):
            return re.search(r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in label.split())+r'(?!\w)',body,re.I) is not None
        for n in nodes:
            assert n['start']==cursor and n['end']>cursor,(uid,'Noncontiguous character coverage',n['id'])
            cursor=n['end'];assert cursor<=len(context)
            assert tok.tokens(context[n['start']:n['end']])<=256,(uid,n['id'])
            assert re.fullmatch(r'n\d{6}',n['id'])
            assert set(n['deps'])<=node_ids and n['id'] not in n['deps']
            assert set(n['edge_types'])==set(n['deps'])
            assert n['preview']==' '.join(context[n['start']:n['end']].split()[:12])
            assert roots[n['doc_id']]['start']<=n['start']<n['end']<=roots[n['doc_id']]['end']
            for dest,kinds in n['edge_types'].items():
                target=byid[dest];body=context[n['start']:n['end']]
                assert kinds and set(kinds)<={'paragraph_continuation','document_title_mention','section_heading_mention'}
                for kind in kinds:
                    if kind=='paragraph_continuation':
                        assert n['doc_id']==target['doc_id'] and n['paragraph_id']==target['paragraph_id']
                        assert n['end']==target['start'] or target['end']==n['start']
                    elif kind=='document_title_mention':
                        root=roots[target['doc_id']]
                        assert n['doc_id']!=target['doc_id'] and dest==root['first_node']
                        assert literal_mention(root['title'],body)
                        assert sum(r['title'].casefold()==root['title'].casefold() for r in roots.values())==1
                    else:
                        assert n['doc_id']==target['doc_id']
                        candidates=[h for h in headings if h['target_id']==dest and h['doc_id']==n['doc_id'] and literal_mention(h['text'],body)]
                        assert candidates,(uid,n['id'],dest,'Unproved heading reference')
                        assert any(sum(x['doc_id']==h['doc_id'] and x['text'].casefold()==h['text'].casefold() for x in headings)==1 for h in candidates)
            edge_count+=len(n['deps']);cross_count+=sum(byid[x]['doc_id']!=n['doc_id'] for x in n['deps'])
        assert cursor==len(context),(uid,'Dropped source tail')
        graph_counts[uid]={'nodes':len(nodes),'documents':len({n['doc_id'] for n in nodes}),'edges':edge_count,'cross_document_edges':cross_count}
    checks.extend(['Prepared file hash matches manifest','All document characters covered exactly once','Every original span at most 256 model tokens','All graph references resolve to supplied source nodes','Every reference has literal title/heading or split-paragraph adjacency evidence','Extractive previews match actual opening words'])
    dump(OUT/'source_clusters.json',{'rule':'SHA256 of context.strip(); exact inference contexts remain unchanged','document_to_cluster':clusters,
        'exact_contexts':len(clusters),'clusters':len(set(clusters.values())),
        'limitation':'Multi-document contexts may share individual passages; clusters do not prove independent underlying sources.'})
    result={'status':'PASS','checks':checks,'questions':len(tasks),'datasets':raw_counts,'documents':len(used),'graph_counts':graph_counts,
            'source_clusters_sha256':sha(OUT/'source_clusters.json'),
            'tasks_sha256':sha(OUT/'tasks.jsonl'),'data_manifest_sha256':sha(OUT/'data_manifest.json'),'seconds':time.perf_counter()-started}
    dump(OUT/'prepared_verification.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ['graph_counts']}),flush=True)
    return result

if __name__=='__main__':verify()
