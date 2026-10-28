"""Lossless, question-blind prose adaptation of source nodes and references.

This is not a Python symbol/import parser. Real article boundaries and conservative
heading labels are supplemented by explicitly extractive opening previews. Edges
are literal title/heading mentions or continuation of one split paragraph only.
"""
from __future__ import annotations
import argparse, collections, json, os, re, time
from pathlib import Path
from common import DATASETS, OUT, Tokenizer, digest, dump, now, read, sha

NODE_CAP = 256
PREVIEW_WORDS = 12
VERSION = 'LOSSLESS-DOCUMENT-PREP-1.0'
PASSAGE = re.compile(r'^Passage ([1-9][0-9]*):[ \t]*\r?$', re.M)
WORD = re.compile(r"\b[\w]+(?:['’\-][\w]+)*\b", re.UNICODE)
SPEAKER = re.compile(r"^[A-Z][A-Za-z0-9 ._'’\-]{0,48}:[ \t]+\S")
COMMON_HEADINGS = {
    'abstract', 'introduction', 'background', 'related work', 'method', 'methods',
    'methodology', 'approach', 'model', 'models', 'experiments', 'results',
    'discussion', 'conclusion', 'conclusions', 'references', 'acknowledgments',
    'acknowledgements', 'appendix', 'history', 'early life', 'personal life',
    'career', 'plot', 'cast', 'production', 'release', 'reception', 'legacy',
    'development', 'education', 'biography', 'overview', 'external links',
    'bibliography', 'works', 'awards', 'honours', 'honors', 'see also',
}


def extract_input(dataset, row):
    """Return question, exact context, exact removed prefix, and original input."""
    source_input = row['input']
    assert isinstance(source_input, str) and source_input
    if dataset in {'hotpotqa', 'musique', 'multifieldqa_en'}:
        assert isinstance(row['context'], str) and row['context'].strip()
        return source_input, row['context'], '', source_input
    first = source_input.find('\n\n')
    assert first > 0, (dataset, row.get('id'), 'missing question separator')
    cutoff = first + 2
    if dataset == 'quality':
        # Some official choices contain blank lines (three validation rows have
        # one after B). Find all four ordered labels before looking for the
        # article delimiter, instead of treating the second blank line as it.
        markers = list(re.finditer(r'^[ \t]*\(([A-D])\)[ \t]+\S', source_input[cutoff:], re.M))[:4]
        labels = [m.group(1) for m in markers]
        assert labels == ['A', 'B', 'C', 'D'], (row['id'], labels)
        second = source_input.find('\n\n', cutoff + markers[-1].end())
        assert second > cutoff, (row['id'], 'missing option separator')
        cutoff = second + 2
    question, prefix, context = source_input[:cutoff-2], source_input[:cutoff], source_input[cutoff:]
    assert context.strip() and prefix + context == source_input
    return question, context, prefix, source_input


def document_ranges(context):
    """Only explicit, consecutively numbered Passage blocks create documents."""
    matches = list(PASSAGE.finditer(context))
    if (len(matches) >= 2 and not context[:matches[0].start()].strip()
            and [int(m.group(1)) for m in matches] == list(range(1, len(matches)+1))):
        result = []
        for i, match in enumerate(matches):
            start = 0 if i == 0 else match.start()
            end = matches[i+1].start() if i+1 < len(matches) else len(context)
            rest = context[match.end():end].lstrip('\r\n')
            title = rest.splitlines()[0].strip() if rest else ''
            if len(title) > 200: title = ''
            result.append({'doc_id':f'd{i+1:04d}', 'start':start, 'end':end,
                           'title':title, 'boundary':'explicit_passage_marker'})
        return result
    return [{'doc_id':'d0001', 'start':0, 'end':len(context), 'title':'',
             'boundary':'single_supplied_document'}]


def is_heading(line):
    value = line.strip()
    if not value or len(value) > 100 or len(WORD.findall(value)) > 12: return False
    if re.search(r'[.!?;,:"“”]$', value) or SPEAKER.match(value): return False
    if value.casefold() in COMMON_HEADINGS: return True
    if re.match(r'^(?:chapter|part|book|section|appendix)\s+[\wIVX]+\b', value, re.I): return True
    if re.match(r'^(?:\d+(?:\.\d+)*\.?)[ \t]+[A-Z]', value): return True
    return len(WORD.findall(value)) >= 2 and value.isupper() and any(c.isalpha() for c in value)


def paragraph_ranges(context, doc):
    start, end = doc['start'], doc['end']
    local = context[start:end]
    lines = list(re.finditer(r'[^\n]*(?:\n|$)', local))
    speaker_lines = [m for m in lines if SPEAKER.match(m.group().strip())]
    speaker_names = {m.group().split(':',1)[0].strip() for m in speaker_lines}
    # Only transcript-like blocks are segmented at speaker turns. Printed book
    # line wraps are never mistaken for independent paragraphs.
    transcript = len(speaker_lines) >= 10 and len(speaker_names) >= 3
    bounds = {start, end}
    bounds.update(start+m.end() for m in re.finditer(r'\n[ \t\r]*\n(?:[ \t\r]*\n)*', local))
    if transcript: bounds.update(start+m.start() for m in speaker_lines)
    headings = []
    for m in lines:
        line = m.group().rstrip('\r\n')
        if is_heading(line) and line.strip() != doc['title']:
            headings.append({'text':line.strip(), 'start':start+m.start(),
                             'end':start+m.end(), 'doc_id':doc['doc_id']})
            bounds.add(start+m.start())
    bounds = sorted(bounds)
    ranges = [(a,b) for a,b in zip(bounds,bounds[1:]) if a < b]
    # A short stand-alone heading remains attached to the following actual body.
    # Whitespace is retained, never stripped from the original source.
    merged = []
    pending = None
    heading_strings = {h['text'] for h in headings} | ({doc['title']} if doc['title'] else set())
    for a,b in ranges:
        if pending is not None: a = pending; pending = None
        stripped = context[a:b].strip()
        if not stripped or stripped in heading_strings:
            pending = a
        else:
            merged.append((a,b))
    if pending is not None:
        if merged: merged[-1] = (merged[-1][0], end)
        else: merged.append((pending,end))
    return merged, headings, transcript


def split_range(context, start, end, tokenizer, cap=NODE_CAP):
    """Contiguous character slices; every emitted slice is checked by the model tokenizer."""
    result = []
    while start < end:
        if tokenizer.tokens(context[start:end]) <= cap:
            result.append((start,end)); break
        lo, hi = start+1, min(end, start+cap*8)
        # Binary search is only a proposed boundary: token counts can be locally
        # nonmonotone, so the final chosen slice is independently checked below.
        best = start
        while lo <= hi:
            mid = (lo+hi)//2
            if tokenizer.tokens(context[start:mid]) <= cap: best=mid;lo=mid+1
            else: hi=mid-1
        assert best > start, 'Cannot fit one Unicode character in node budget'
        last_space = max(context.rfind(' ', start, best), context.rfind('\n', start, best))
        if last_space > start + (best-start)//2: best=last_space+1
        while tokenizer.tokens(context[start:best]) > cap: best-=1
        assert best > start
        result.append((start,best)); start=best
    return result


def mention_pattern(text):
    if len(WORD.findall(text)) < 2: return None
    return re.compile(r'(?<!\w)' + r'\s+'.join(re.escape(w) for w in text.split()) + r'(?!\w)', re.I)


def build_document(context, tokenizer):
    """Only source text and a tokenizer enter this function; no question or gold."""
    assert isinstance(context,str) and context.strip()
    docs = document_ranges(context); nodes=[]; headings=[]
    for doc in docs:
        paragraphs, found, transcript = paragraph_ranges(context,doc)
        doc['transcript_turn_segmentation'] = transcript
        headings.extend(found)
        for para_index,(start,end) in enumerate(paragraphs):
            pieces=split_range(context,start,end,tokenizer)
            group=[]
            for a,b in pieces:
                eligible=[h for h in found if h['start']<=a]
                heading=eligible[-1]['text'] if eligible else ''
                text=context[a:b]
                node={'id':f'n{len(nodes)+1:06d}', 'doc_id':doc['doc_id'],
                      'title':doc['title'], 'heading':heading,
                      'preview':' '.join(text.split()[:PREVIEW_WORDS]),
                      'start':a, 'end':b, 'deps':[], 'edge_types':{},
                      'paragraph_id':f"{doc['doc_id']}:p{para_index+1:06d}",
                      'tokens':tokenizer.tokens(text)}
                nodes.append(node);group.append(node)
            if len(group)>1:
                for i,node in enumerate(group):
                    for other in group[max(0,i-1):min(len(group),i+2)]:
                        if other is not node: node['edge_types'][other['id']]=['paragraph_continuation']
        own=[n for n in nodes if n['doc_id']==doc['doc_id']]
        doc['first_node']=own[0]['id']
    # The first node covering a heading also preserves the heading's exact bytes.
    for heading in headings:
        target=next(n for n in nodes if n['start']<=heading['start']<n['end'])
        heading['target_id']=target['id']
    byid={n['id']:n for n in nodes}
    title_count=collections.Counter(d['title'].casefold() for d in docs if d['title'])
    targets=[]
    for doc in docs:
        pattern=mention_pattern(doc['title'])
        if pattern and title_count[doc['title'].casefold()]==1:
            targets.append(('document_title_mention',doc['doc_id'],doc['first_node'],pattern))
    heading_count=collections.Counter((h['doc_id'],h['text'].casefold()) for h in headings)
    for h in headings:
        pattern=mention_pattern(h['text'])
        if pattern and heading_count[(h['doc_id'],h['text'].casefold())]==1:
            targets.append(('section_heading_mention',h['doc_id'],h['target_id'],pattern))
    for node in nodes:
        text=context[node['start']:node['end']]
        for kind,doc_id,target,pattern in targets:
            if target==node['id']:continue
            if kind=='document_title_mention' and node['doc_id']==doc_id:continue
            if kind=='section_heading_mention' and node['doc_id']!=doc_id:continue
            if pattern.search(text):
                node['edge_types'].setdefault(target,[]).append(kind)
        node['edge_types']={k:sorted(set(v)) for k,v in sorted(node['edge_types'].items())}
        node['deps']=list(node['edge_types'])
    assert nodes[0]['start']==0 and nodes[-1]['end']==len(context)
    assert all(a['end']==b['start'] for a,b in zip(nodes,nodes[1:]))
    assert all(0<n['tokens']<=NODE_CAP and all(x in byid for x in n['deps']) for n in nodes)
    assert ''.join(context[n['start']:n['end']] for n in nodes)==context
    return {'document_id':digest(context),'context':context,'nodes':nodes,
            'roots':docs,'headings':headings,'build':{'version':VERSION,
            'node_max_tokens':NODE_CAP,'preview_words':PREVIEW_WORDS,
            'graph_inputs':'context only; no question, options, answers, or evidence annotations',
            'node_count':len(nodes),'context_tokens':tokenizer.tokens(context),
            'edge_counts':dict(collections.Counter(k for n in nodes for ks in n['edge_types'].values() for k in ks))}}


def prepare(out=OUT, tokenizer=None):
    out=Path(out); tokenizer=tokenizer or Tokenizer();started=now();start=time.perf_counter()
    # A complete ZIP-member manifest proves extraction finished before parsing.
    downloads={}
    for name in DATASETS:
        path=out/'downloads'/f'{name}.json'
        assert path.exists(), f'Missing completed download manifest: {path}'
        rec=read(path)
        for member in rec['members']:
            path=out/'raw'/member['local_name']
            assert path.stat().st_size==member['bytes'] and sha(path)==member['sha256'],path
            downloads[member['local_name']]={'sha256':member['sha256'],'bytes':member['bytes']}
    tasks=[];document_files={};counts={}
    for dataset in DATASETS:
        path=out/'raw'/f'{dataset}.jsonl';byid={};raw_count=0
        with path.open(encoding='utf8') as f:
            for line in f:
                if not line.strip():continue
                row=json.loads(line);raw_count+=1
                question,context,prefix,raw_input=extract_input(dataset,row)
                source_id=row.get('id',row.get('_id'));assert isinstance(source_id,str)
                refs=row['answers'] if 'answers' in row else [row['output']]
                assert refs and all(isinstance(x,str) for x in refs)
                document_id=digest(context)
                if source_id in byid:
                    task=byid[source_id]
                    assert task['question']==question and task['document_id']==document_id
                    assert task['raw_input_sha256']==digest(raw_input)
                    task['references'].extend(refs);task['raw_rows']+=1
                    continue
                if document_id not in document_files:
                    dest=out/'documents'/f'{document_id}.json.gz'
                    if dest.exists():
                        document=read(dest)
                        assert document['context']==context and document['build']['version']==VERSION
                    else:
                        document=build_document(context,tokenizer);dump(dest,document)
                    document_files[document_id]={'path':str(dest.relative_to(out)),
                        'sha256':sha(dest),'context_sha256':document_id,
                        'context_chars':len(context),'context_tokens':document['build']['context_tokens'],
                        'node_count':len(document['nodes']),'source_document_count':len(document['roots']),
                        'edge_counts':document['build']['edge_counts']}
                    if len(document_files)%25==0:print(f'prepared {len(document_files)} unique contexts; {dataset}',flush=True)
                task={'task_id':f'{dataset}:{source_id}','dataset':dataset,'source_id':source_id,
                      'question':question,'document_id':document_id,'references':list(refs),
                      'input_prefix':prefix,'raw_input_sha256':digest(raw_input),
                      'raw_context_sha256':document_id,'raw_rows':1}
                byid[source_id]=task
        tasks.extend(byid.values())
        counts[dataset]={'raw_rows':raw_count,'unique_questions':len(byid),
                         'references':sum(len(t['references']) for t in byid.values()),
                         'unique_contexts':len({t['document_id'] for t in byid.values()}),
                         'raw_file':str(path.relative_to(out)),**downloads[path.name]}
        print(f'{dataset}: {raw_count} rows, {len(byid)} unique questions',flush=True)
    dest=out/'tasks.jsonl';temp=dest.with_suffix('.jsonl.part')
    with temp.open('w',encoding='utf8') as f:
        for task in tasks:f.write(json.dumps(task,ensure_ascii=False,separators=(',',':'))+'\n')
    os.replace(temp,dest)
    manifest={'status':'complete','version':VERSION,'started_at_utc':started,'completed_at_utc':now(),
              'preparation_seconds':time.perf_counter()-start,'datasets':counts,
              'task_count':len(tasks),'document_count':len(document_files),
              'tasks_sha256':sha(dest),'document_files':document_files,
              'source_sha256':sha(Path(__file__)),'model_tokenizer':'Qwen2.5-Coder-7B-Instruct GGUF tokenizer',
              'assumptions':[
                  'All unique labelled question IDs retained; all duplicate-ID references grouped.',
                  'Question/options removed before building documents; exact removed prefix preserved.',
                  'Every source character belongs to exactly one contiguous node; no context truncation.',
                  'Explicit consecutive Passage N markers define supplied-document boundaries; otherwise one document.',
                  'Conservative source heading lines and transcript-style speaker turns are deterministic heuristics.',
                  'Catalog previews copy the first 12 whitespace-separated source words; not body-free code metadata.',
                  'Only split-paragraph continuation and unique exact multiword title/heading mentions form edges.',
                  'Title links enter the first source node; heading links remain within that source document.',
                  'No query, gold answer, human evidence label, generated summary, proximity, or semantic similarity creates graph edges.',
                  'Document sha uses exact context UTF-8; identical contexts reuse identical assets across questions.']}
    dump(out/'data_manifest.json',manifest)
    print(f'COMPLETE: {len(tasks)} questions; {len(document_files)} exact unique contexts',flush=True)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    prepare(parser.parse_args().out)
