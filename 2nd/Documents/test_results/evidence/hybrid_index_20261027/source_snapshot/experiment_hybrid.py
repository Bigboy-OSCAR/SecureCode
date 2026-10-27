"""Frozen TF-IDF -> body-free index -> explicit source selection experiment."""
from __future__ import annotations
import argparse, ast, itertools, json, math, os, random, re, shutil, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
import experiment_large as large

v1, audit, ab = large.original, large.audited, large.ab
read = large.read
OUT = v1.DEFAULT_OUT / 'hybrid_index_20261027'
REPORT = large.small.r0.REPORT
ARMS = ['B', 'R0', 'H']
CONFIG = {
    'version': 'HYBRID-1.0', 'arms': ARMS, 'questions': 96, 'repeats': 3,
    'order_seed': 20261027, 'model_context': 8192, 'temperature': 0, 'seed': 1,
    'answer_max_tokens': 128, 'selector_max_tokens': 96, 'prompt_cache': False,
    'raw_context_cap': 1024, 'index_text_cap': 512,
    'index_candidates': 24, 'max_selected_symbols': 8,
    'H_retrieval': 'Unchanged R0 word extraction, raw-only IDF and candidate cosine scores. A symbol receives the maximum score of its own rooted bundle and atomic candidate, never a score inherited from an ancestor. Positive-score symbols sorted by descending score then URI; top 24 considered.',
    'H_index': 'No bodies, assignment values, docstrings or summaries. AST-derived name/parameter signature, kind, path, line span and direct dependency names. Whole index rows packed into 512 model tokens in rank order; no partial rows.',
    'H_selection': 'One LLM request chooses 1..8 distinct row numbers. Exactly those single-symbol originals are considered in returned order. No automatic dependency expansion, no bundle promotion, no refill with unrequested symbols, no repair request.',
    'H_delivery': 'Unchanged raw fragment format and 1024-token pack. Oversize whole symbols skipped. One unchanged answer prompt after selection, including on invalid/empty selection; invalid selection counts as incorrect.',
    'controls': 'Fresh unchanged B and R0 in the same interleaved session. Historical A/FULL/RF/RH/C retained as explicitly historical reference, not new calls.',
    'schedule': 'Three-arm task blocks; all six permutations occur 16 times per repeat. Same 96 questions and three repetitions as prior large experiment.',
    'development': 'Eight separate-project development questions for protocol/transport smoke checks only; no quality-based parameter or prompt tuning.',
    'primary_contrasts': ['H-R0', 'H-B'],
    'inference': 'Six project-cluster exhaustive bootstrap and sign flips; Holm correction over two quality contrasts. No noninferiority or independent holdout claim.',
    'cost': 'All selector plus answer input tokens; mean per-question maximum call input reported separately. Index cap is additional to raw cap and is not hidden from total cost.',
    'timing': 'Physical query time including retrieval, index packing, selection, source packing and answer; excludes offline preparation and grading. Token cache reset per query, model cache disabled.',
    'limitations': 'Previously inspected synthetic tasks are reused. H is a fixed two-call design, not adaptive multiround retrieval. Existing graph has limited static import resolution. No parameter optimality or novelty claim.',
}


def symbol_metadata(nodes):
    result = {}
    for uid, node in nodes.items():
        tree = ast.parse(node['source']).body[0]
        if isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Names only: defaults and annotations can contain implementation details.
            args = tree.args
            names = [a.arg for a in args.posonlyargs + args.args]
            if args.vararg: names.append('*' + args.vararg.arg)
            elif args.kwonlyargs: names.append('*')
            names.extend(a.arg for a in args.kwonlyargs)
            if args.kwarg: names.append('**' + args.kwarg.arg)
            signature = node['name'] + '(' + ', '.join(names) + ')'
        else:
            signature = node['name']
        result[uid] = {'uri': uid, 'kind': node['kind'], 'signature': signature,
                       'path': node['path'], 'start': node['start'], 'end': node['end'],
                       'deps': list(node['deps'])}
    return result


def compact_uri(uid):
    return uid.removeprefix('memory://symbol/')


def rank_symbols(retriever, question, raw):
    scores = {}
    for score, item in retriever.ranked(question, raw):
        root = item['id'].removeprefix('atomic:')
        scores[root] = max(scores.get(root, 0.0), score)
    return sorted(((score, uid) for uid, score in scores.items() if score > 0),
                  key=lambda x: (-x[0], x[1]))


def index_line(number, meta):
    deps = ','.join(compact_uri(u) for u in meta['deps']) or '-'
    return (f"{number}. {meta['kind']} {meta['path']}:{meta['start']}-{meta['end']} "
            f"{meta['signature']} -> {deps}")


def make_index(client, ranked, metadata):
    text = ''; included = []; rejected = []; count = 0
    for score, uid in ranked[:CONFIG['index_candidates']]:
        number = len(included) + 1
        line = index_line(number, metadata[uid])
        proposed = text + ('\n' if text else '') + line
        tokens = client.tokens(proposed)
        if tokens <= CONFIG['index_text_cap']:
            text, count = proposed, tokens
            included.append({'number': number, 'uri': uid, 'score': score, 'line': line})
        else:
            rejected.append(uid)
    return {'text': text, 'tokens': count, 'items': included, 'rejected': rejected}


def selector_prompt(question, index):
    return (
        'Select the smallest set of source items needed to answer the Python code question. '
        'The index lists signatures and direct dependencies, not implementations. '
        'Choose the relevant functions and required dependencies/constants from the listed rows. '
        'Only selected individual items will be read; selecting a function does NOT automatically read its dependencies. '
        'Return only one JSON object {"read":[row_numbers]} with 1 to 8 distinct listed row numbers, '
        'in reading priority order. Do not answer the question. If none are relevant, return {"read":[]}.\n\n'
        f'Question:\n{question}\n\nSource index:\n{index}\n\nSelection:'
    )


def parse_selection(call, index):
    if not call['ok']: return [], False, 'selector_call_failed'
    text = call['answer'].strip()
    if text.startswith('```') and text.endswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, count=1).removesuffix('```').strip()
    try:
        obj = json.loads(text)
        assert isinstance(obj, dict) and set(obj) == {'read'}
        numbers = obj['read']; assert isinstance(numbers, list)
        assert 1 <= len(numbers) <= CONFIG['max_selected_symbols']
        assert all(type(n) is int and 1 <= n <= len(index['items']) for n in numbers)
        assert len(numbers) == len(set(numbers))
        return [index['items'][n-1]['uri'] for n in numbers], True, None
    except (ValueError, TypeError, AssertionError, KeyError):
        return [], False, 'selector_invalid_or_empty'


def selected_items(asset, uris):
    return [(0.0, {'id': uid, 'level': 0, 'text': v1.fragment(asset['nodes'][uid]),
                   'source_uris': [uid]}) for uid in uris]


def schedule(tasks):
    rng = random.Random(CONFIG['order_seed']); plan = []
    for repeat in range(CONFIG['repeats']):
        shuffled = list(tasks); rng.shuffle(shuffled)
        orders = list(itertools.permutations(ARMS)) * 16; rng.shuffle(orders)
        assert len(shuffled) == len(orders) == 96
        for task, order in zip(shuffled, orders):
            plan.extend({'task_id': task['id'], 'repeat': repeat, 'arm': a} for a in order)
    return plan


def prepare(out):
    assert not (out/'protocol.json').exists(), 'Use a fresh evidence folder'
    large.validate_frozen(large.DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)
    historical = {}
    for name in ['tasks.json', 'dev_tasks.json', 'gold_operations.json', 'assets.json', 'file_map.json', 'corpus_manifest.json']:
        source = large.DEFAULT_OUT/name
        historical[str(source)] = v1.sha(source); shutil.copy2(source, out/name)
    shutil.copytree(large.DEFAULT_OUT/'projects', out/'projects', dirs_exist_ok=True)
    assets = read(out/'assets.json'); start = time.perf_counter()
    meta = {p: symbol_metadata(a['nodes']) for p, a in assets.items()}
    v1.dump(out/'symbol_metadata.json', meta)
    v1.dump(out/'preparation.json', {'metadata_seconds': time.perf_counter()-start,
        'note': 'Original code/graph/raw assets reused byte-for-byte; no summary LLM calls.'})
    tasks = read(out/'tasks.json'); v1.dump(out/'schedule.json', schedule(tasks))
    v1.dump(out/'gold_recheck.json', ab.verify_gold(out, tasks, read(out/'gold_operations.json')))
    history = out/'history'; history.mkdir(exist_ok=True)
    shutil.copy2(REPORT, history/REPORT.name)
    for folder in [large.DEFAULT_OUT, v1.DEFAULT_OUT/'raptor_large_20261024']:
        for name in ['results.jsonl', 'summary.json', 'verification.json', 'protocol.json', 'environment.json']:
            historical[str(folder/name)] = v1.sha(folder/name)
    code = list(dict.fromkeys([Path(__file__), Path(large.__file__), *ab.inputs()]))
    snapshots = out/'source_snapshot'; snapshots.mkdir(exist_ok=True)
    for p in code: shutil.copy2(p, snapshots/p.name)
    v1.dump(out/'protocol.json', {'config': CONFIG, 'frozen_at_utc': audit.now(),
        'historical_hashes': historical, 'source_hashes': {str(p): v1.sha(p) for p in code},
        'frozen_files': {str(p.relative_to(out)): v1.sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    print(json.dumps({'status': 'PREPARED', 'questions': len(tasks), 'new_evaluation_answers': 864,
                       'new_development_answers': 24, 'arms': ARMS}), flush=True)


def validate(out):
    protocol = read(out/'protocol.json'); assert protocol['config'] == CONFIG
    for group, root in [('historical_hashes', None), ('source_hashes', None), ('frozen_files', out)]:
        for path, expected in protocol[group].items():
            assert v1.sha(root/path if root else path) == expected, path


def run(out, url, dev=False):
    validate(out)
    client = audit.AuditedClient(out, url)
    environment = audit.runtime_environment(client)
    assert environment['fingerprint'] == read(large.DEFAULT_OUT/'environment.json')['fingerprint'], 'Runtime changed'
    if (out/'environment.json').exists():
        assert read(out/'environment.json')['fingerprint'] == environment['fingerprint']
    else: v1.dump(out/'environment.json', environment)
    tasks = read(out/('dev_tasks.json' if dev else 'tasks.json')); byid = {t['id']: t for t in tasks}
    assets = read(out/'assets.json'); metadata = read(out/'symbol_metadata.json'); retrievers = {}; prep = {}
    for project, asset in assets.items():
        start = time.perf_counter(); r = v1.Retriever(asset['raw']); r.ranked('', asset['raw'])
        retrievers[project] = r; prep[project] = time.perf_counter()-start
    plan = ([{'task_id': t['id'], 'repeat': 0, 'arm': a} for t in tasks for a in ARMS]
            if dev else read(out/'schedule.json'))
    dest = out/('results_dev.jsonl' if dev else 'results.jsonl'); prior = audit.rows(dest)
    assert [{k: r[k] for k in ['task_id', 'repeat', 'arm']} for r in prior] == plan[:len(prior)]
    session = audit.digest([audit.now(), dev])[:20]
    v1.dump(out/f'session_{session}.json', {'started_at_utc': audit.now(), 'pid': os.getpid(),
        'dev': dev, 'resume_after_rows': len(prior), 'vector_build_seconds': prep,
        'environment_sha256': v1.sha(out/'environment.json')})
    client.reset_query()
    assert client.complete('Return only {"answer":0}.', 'warmup', 32, {'session_id': session})['ok']
    for i, entry in enumerate(plan):
        if i < len(prior): continue
        task = byid[entry['task_id']]; arm = entry['arm']; asset = assets[task['project']]
        meta = {**entry, 'dev': dev, 'session_id': session}; root = out/'projects'/task['project']
        selector = None; selected = None; valid = None; selection_reason = None
        source_index = None; requested = []; rankings = []
        retrieval_seconds = select_seconds = expansion_seconds = index_seconds = 0.0
        client.reset_query(); start, utc = time.perf_counter(), audit.now()
        if arm == 'B':
            outline = v1._candidate_symbol_outline(asset['index'], task['question'], 24)
            selector = client.complete(v1._selector_prompt(task['question'], outline), 'select', 96, meta)
            select_seconds = time.perf_counter()-start; phase = time.perf_counter()
            ordered, selected, valid = ab.b_ordered(asset, {'question': task['question']}, selector)
            expansion_seconds = time.perf_counter()-phase
        elif arm == 'R0':
            ordered = retrievers[task['project']].ranked(task['question'], asset['raw'])
            retrieval_seconds = time.perf_counter()-start
        else:
            ranks = rank_symbols(retrievers[task['project']], task['question'], asset['raw'])
            rankings = [{'uri': uid, 'score': score} for score, uid in ranks]
            retrieval_seconds = time.perf_counter()-start; phase = time.perf_counter()
            source_index = make_index(client, ranks, metadata[task['project']])
            index_seconds = time.perf_counter()-phase; phase = time.perf_counter()
            selector = client.complete(selector_prompt(task['question'], source_index['text']), 'select', 96, meta)
            select_seconds = time.perf_counter()-phase; phase = time.perf_counter()
            requested, valid, selection_reason = parse_selection(selector, source_index)
            ordered = selected_items(asset, requested)
            expansion_seconds = time.perf_counter()-phase
        phase = time.perf_counter()
        context, tokens, chosen, rejected = v1.pack(client, ordered, 1024)
        packing_seconds = time.perf_counter()-phase; pre_answer = time.perf_counter()-start
        call = client.complete(v1.answer_prompt(task['question'], context), 'answer', 128, meta)
        seconds, ended = time.perf_counter()-start, audit.now()
        correct, parsed, failure = v1.evaluate_answer(call, task['expected'])
        if selector and not valid: correct, failure = False, 'selector_invalid'
        sources = {u for c in chosen for u in c['source_uris']}; required = set(task['required_uris'])
        target_path = asset['nodes'][task['target_uri']]['path']
        shown = {x['uri'] for x in source_index['items']} if source_index else set()
        row = {**entry, 'session_id': session, 'project': task['project'],
            'split': task.get('split', 'development'), 'category': task['category'],
            'question': task['question'], 'expected': task['expected'],
            'correct': correct, 'parsed_answer': parsed, 'failure': failure,
            'selector': selector, 'answer_call': call, 'selected_uri': selected,
            'selection_valid': valid, 'selection_failure': selection_reason,
            'selection_correct': selected == task['target_uri'] if arm == 'B' else None,
            'source_index': source_index, 'symbol_ranking': rankings, 'requested_uris': requested,
            'index_required_recall': len(shown & required)/len(required) if arm == 'H' else None,
            'index_has_all_required': required <= shown if arm == 'H' else None,
            'context': context, 'context_tokens': tokens, 'selected_context_tokens': tokens,
            'chosen': chosen, 'rejected': rejected,
            'query_seconds': seconds, 'retrieval_seconds': retrieval_seconds,
            'index_seconds': index_seconds, 'select_seconds': select_seconds,
            'expansion_seconds': expansion_seconds, 'packing_seconds': packing_seconds,
            'pre_answer_seconds': pre_answer, 'compaction_seconds': 0,
            'tokenize_http_calls': client.token_http_count, 'tokenize_seconds': client.token_seconds,
            'started_at_utc': utc, 'ended_at_utc': ended,
            'input_tokens': call['input_tokens'] + (selector['input_tokens'] if selector else 0),
            'output_tokens': (call['output_tokens'] or 0) + ((selector['output_tokens'] or 0) if selector else 0),
            'raw_evidence_recall': len(sources & required)/len(required),
            'all_raw_evidence': required <= sources, 'unique_source_count': len(sources),
            'cross_file_source_count': sum(asset['nodes'][u]['path'] != target_path for u in sources),
            'source_files': sorted({asset['nodes'][u]['path'] for u in sources})}
        with dest.open('a') as handle: handle.write(json.dumps(row, ensure_ascii=False)+'\n')
        v1.dump(out/'work_status.json', {'updated_at_utc': audit.now(), 'state': 'running',
            'phase': 'development' if dev else 'evaluation', 'pid': os.getpid(),
            'completed': i+1, 'target': len(plan), 'last': entry})
        print(f"{'dev' if dev else 'eval'} {i+1}/{len(plan)} {task['id']} {arm} r{entry['repeat']} "
              f"correct={int(correct)} code={tokens} input={row['input_tokens']} seconds={seconds:.3f}", flush=True)
        if 'error' in call or (selector and 'error' in selector):
            raise RuntimeError('Transport/context failure retained; investigate before any continuation')
    v1.dump(out/f"completed_{'dev' if dev else 'eval'}.json", {'completed_at_utc': audit.now(),
        'rows': len(plan), 'results_sha256': v1.sha(dest), 'session_id': session})


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['prepare', 'dev', 'run'])
    parser.add_argument('--out', type=Path, default=OUT); parser.add_argument('--url', default='http://127.0.0.1:8766')
    args = parser.parse_args()
    if args.phase == 'prepare': prepare(args.out)
    else: run(args.out, args.url, args.phase == 'dev')


if __name__ == '__main__': main()

