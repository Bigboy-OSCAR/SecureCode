"""Independent, full-validation QASPER audit; never runs inference or repairs evidence.

Run only after run_experiment and analyze_results finish. A missing row, call,
final analysis, or completion marker is an error: this verifier has no partial
PASS mode. It does not import the experiment's retrieval/packing functions or
the analyzer's aggregation/bootstrap functions. It reuses only the frozen
low-level tokenizer bridge and the official metric primitives (already tested
against the official wrappers). Numeric comparisons allow floating summation
roundoff, never missing observations or different selections.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import importlib.util
import importlib.metadata
import itertools
import json
import math
from pathlib import Path
import random
import re
import time

import numpy as np

from common import HERE, MODEL, OUT, Tokenizer, digest, dump, now, read, rows, sha

DATASETS = ('qasper',)
ARMS = ('A', 'B', 'R0', 'FULL')
COUNTS = {'qasper': 984}
EXPECTED_CONTEXTS = 273
METRICS = {'qasper': 'f1'}
USAGE = ('input_tokens', 'peak_input_tokens', 'output_tokens', 'prepared_source_tokens',
         'actual_answer_source_tokens', 'requested_answer_input_tokens', 'completed_call_seconds', 'query_seconds')
STOPWORDS = frozenset('answer class combine constant does exact file final for function given inside literal module number only return returns string the value what when with'.split())
CATALOG_FIELDS = ('id', 'doc_id', 'title', 'heading', 'start', 'end', 'preview')
BASE_CONTRASTS = (('B', 'A'), ('R0', 'A'), ('R0', 'B'))
FIT_CONTRASTS = BASE_CONTRASTS + tuple((arm, 'FULL') for arm in ARMS[:-1])


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(actual, expected, location='value'):
    """Compare complete JSON trees, permitting only numeric roundoff."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), f'{location}: dictionary keys differ')
        for key in expected:
            equal(actual[key], expected[key], f'{location}.{key}')
    elif isinstance(expected, (list, tuple)):
        require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), f'{location}: sequence length differs')
        for index, (left, right) in enumerate(zip(actual, expected)):
            equal(left, right, f'{location}[{index}]')
    elif isinstance(expected, (set, frozenset)):
        require(isinstance(actual, (set, frozenset)) and actual == expected, f'{location}: set membership differs')
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        require(type(actual) is type(expected) and actual == expected, f'{location}: {actual!r} != {expected!r}')
    elif isinstance(expected, int):
        require(type(actual) is int and actual == expected, f'{location}: integer differs')
    else:
        require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isfinite(actual) and math.isfinite(expected)
                and math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8),
                f'{location}: {actual!r} != {expected!r}')


def lexemes(text):
    text = re.sub('([a-z])([A-Z])', r'\1 \2', text).lower()
    tokens = []
    for match in re.finditer(r'[a-z][a-z0-9_]*|\d+', text):
        word = match.group()
        tokens.append(word)
        if '_' in word:
            tokens.extend(word.split('_'))
    return [word for word in tokens if len(word) > 1]


def closure(nodes, root, depth, same_document=False, limit=None):
    by_id = {node['id']: node for node in nodes}
    work = [(root, 0)]
    visited, output = set(), []
    while work and (limit is None or len(output) < limit):
        uid, distance = work.pop(0)
        if uid in visited:
            continue
        visited.add(uid)
        if same_document and by_id[uid]['doc_id'] != by_id[root]['doc_id']:
            continue
        output.append(uid)
        if distance < depth:
            work.extend((child, distance + 1) for child in by_id[uid]['deps'])
    return output


def fragment(document, node):
    return (f"### source {node['id']} document {node['doc_id']} chars {node['start']}-{node['end']}\n"
            + document['context'][node['start']:node['end']])


class RawSearch:
    """Independent candidate construction and sublinear TF-IDF calculations."""
    def __init__(self, document):
        self.candidates = []
        nodes = document['nodes']
        source = {node['id']: fragment(document, node) for node in nodes}
        for node in nodes:
            members = closure(nodes, node['id'], 3)
            self.candidates.append({'id': 'bundle:' + node['id'], 'source_ids': members,
                                    'text': '\n\n'.join(source[uid] for uid in members)})
            # This is essential: a one-node closure has no duplicate atomic item.
            if len(members) > 1:
                self.candidates.append({'id': 'atomic:' + node['id'], 'source_ids': [node['id']],
                                        'text': source[node['id']]})
        term_counts = [Counter(lexemes(item['text'])) for item in self.candidates]
        document_frequencies = Counter(word for terms in term_counts for word in terms)
        n = len(self.candidates)
        self.idf = {word: math.log((n + 1) / (frequency + 1)) + 1
                    for word, frequency in document_frequencies.items()}
        self.unseen = math.log(n + 1) + 1
        self.vectors = [self.vector(counts) for counts in term_counts]

    def vector(self, counts):
        weighted = {word: (1 + math.log(count)) * self.idf.get(word, self.unseen)
                    for word, count in counts.items()}
        length = math.sqrt(sum(value * value for value in weighted.values())) or 1
        return {word: value / length for word, value in weighted.items()}

    def rank(self, question):
        query = self.vector(Counter(lexemes(question)))
        scored = []
        for vector, item in zip(self.vectors, self.candidates):
            score = sum(weight * vector.get(word, 0) for word, weight in query.items())
            scored.append((score, item))
        return sorted(scored, key=lambda pair: (-pair[0], pair[1]['id']))


def replay_catalog(document, question, tokenizer, config):
    terms = set(lexemes(question)).difference(STOPWORDS)
    positive = []
    for node in document['nodes']:
        heading = node.get('heading', '')
        label_words = set(lexemes((heading + ' ' + node['preview']).strip()))
        weight = 3 * len(terms.intersection(label_words)) + len(terms.intersection(lexemes(node.get('title', ''))))
        if heading.strip() and heading.casefold() in question.casefold():
            weight += 20
        if weight > 0:
            positive.append((weight, node))
    ranked = positive or [(1, node) for node in document['nodes']]
    ranked.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    text, accepted, rejected = '', [], []
    for _, node in ranked[:config['catalog_candidates']]:
        encoded = json.dumps({key: node[key] for key in CATALOG_FIELDS}, ensure_ascii=False, separators=(',', ':'))
        proposed = '\n'.join([text, encoded]) if text else encoded
        if tokenizer.tokens(proposed) <= config['catalog_budget']:
            text = proposed
            accepted.append(node['id'])
        else:
            rejected.append(node['id'])
    return {'text': text, 'ids': accepted, 'rejected': rejected, 'tokens': tokenizer.tokens(text)}


def replay_pack(ranked, tokenizer, budget):
    text, included, rejected, covered = '', [], [], set()
    for similarity, item in ranked:
        if all(uid in covered for uid in item['source_ids']):
            continue
        proposed = '\n\n'.join([text, item['text']]) if text else item['text']
        if tokenizer.tokens(proposed) > budget:
            rejected.append(item['id'])
            continue
        text = proposed
        covered.update(item['source_ids'])
        included.append({'id': item['id'], 'source_ids': item['source_ids'], 'score': similarity})
    return text, included, rejected


def selection_result(call, catalog):
    answer = call['answer'].strip()
    selected = answer if re.fullmatch(r'n\d{6}', answer) else None
    response = call.get('response', {})
    valid = (selected in catalog['ids'] and call['status'] == 'ok'
             and not response.get('stopped_limit', False) and response.get('stop_type') != 'limit')
    return selected, valid


def select_prompt(question, catalog_text):
    return ('Choose the one source passage most relevant to the question. The catalog gives document titles, locations and short opening previews, not full passages. '
            'Return exactly one listed source id (for example n000001), with no explanation or other text.\n\nQuestion:\n'
            + question + '\n\nSource catalog:\n' + catalog_text + '\n\nSource id:')


def final_prompt(dataset, question, context, templates):
    require(dataset == 'qasper', 'This verifier is limited to QASPER')
    return templates['qasper'].format(context=context, input=question)


def wrapped(prompt):
    return ('<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n'
            + prompt + '<|im_end|>\n<|im_start|>assistant\n')


def audit_call(call, task_id, arm, stage, prompt, max_tokens, tokenizer, config):
    expected_key = digest('|'.join((task_id, arm, stage)))
    equal([call[key] for key in ('key', 'task_id', 'arm', 'stage')],
          [expected_key, task_id, arm, stage], 'call.identity')
    prompt = wrapped(prompt)
    expected_request = {'prompt': prompt, 'n_predict': max_tokens, 'temperature': 0, 'seed': 1,
                        'cache_prompt': False, 'id_slot': 0, 'stop': ['<|im_end|>', '<|im_start|>'], 'stream': False}
    equal(call['request'], expected_request, 'call.request')
    token_count = tokenizer.tokens(prompt)
    equal(call['requested_input_tokens'], token_count, 'call.requested_input_tokens')
    require(math.isfinite(call['wall_seconds']) and call['wall_seconds'] >= 0, 'Invalid call wall time')
    require(datetime.fromisoformat(call['ended_at_utc']) >= datetime.fromisoformat(call['started_at_utc']), 'Reversed call timestamps')
    require(not call.get('execution_cost_unknown', False), 'Unknown-cost attempt cannot pass')
    if token_count + max_tokens > config['model_context']:
        equal(call['status'], 'context_overflow', 'call.overflow_status')
        equal([call['input_tokens'], call['output_tokens'], call['answer']], [0, 0, ''], 'call.overflow_cost')
        require('response' not in call, 'Overflow unexpectedly has a model response')
        return
    equal(call['status'], 'ok', 'call.status')
    response = call['response']
    equal(response['prompt'], prompt, 'response.prompt')
    equal(response['model'], MODEL.name, 'response.model')
    equal(response['tokens_evaluated'], token_count, 'response.tokens_evaluated')
    equal(call['input_tokens'], token_count, 'call.input_tokens')
    equal(call['output_tokens'], response['tokens_predicted'], 'call.output_tokens')
    require(type(call['output_tokens']) is int and 0 <= call['output_tokens'] <= max_tokens, 'Output budget exceeded')
    require(token_count + call['output_tokens'] <= config['model_context'], 'Actual context window exceeded')
    equal(call['answer'], response['content'].strip(), 'call.raw_prediction')
    require(response['truncated'] is False, 'Server truncated input')
    require(response.get('id_slot') == 0, 'Unexpected server slot')
    generation = response['generation_settings']
    for key, expected in {'seed': 1, 'temperature': 0.0, 'n_predict': max_tokens,
                          'max_tokens': max_tokens, 'stream': False,
                          'stop': ['<|im_end|>', '<|im_start|>']}.items():
        equal(generation[key], expected, f'generation_settings.{key}')
    equal(response['timings']['cache_n'], 0, 'response.timings.cache_n')
    equal(response['timings']['prompt_n'], token_count, 'response.timings.prompt_n')
    equal(response['timings']['predicted_n'], call['output_tokens'], 'response.timings.predicted_n')
    require(response.get('stop') is True, 'Response is not a completed generation')


def audit_smoke(out, tokenizer, config, frozen_at_utc):
    """Audit the one known pre-evaluation transport smoke call, never a cohort row.

    Its exact identity, prompt, output limit, answer, and pre-freeze timestamp
    are allowlisted. A caller cannot excuse arbitrary extra calls by labelling
    them SMOKE or adding them to the transport sidecar.
    """
    key = digest('smoke_transport|SMOKE|answer')
    path = Path(out) / 'calls' / key[:2] / (key + '.json.gz')
    call = read(path)
    metadata_path = Path(out) / 'smoke_transport.json'
    metadata = read(metadata_path)
    audit_call(call, 'smoke_transport', 'SMOKE', 'answer', 'Return only the numeral 2.',
               16, tokenizer, config)
    equal(call['status'], 'ok', 'smoke.status')
    equal(call['answer'], '2', 'smoke.answer')
    require(datetime.fromisoformat(call['ended_at_utc']) < datetime.fromisoformat(frozen_at_utc),
            'Known smoke call must predate evaluation protocol freeze')
    equal(metadata, {'tokenizer_crosschecks': 3, 'status': call['status'],
                     'input_tokens': call['input_tokens'], 'output_tokens': call['output_tokens'],
                     'response': call['response']}, 'smoke_transport sidecar')
    return call, {'key': key, 'task_id': 'smoke_transport', 'arm': 'SMOKE', 'stage': 'answer',
                  'call_sha256': sha(path), 'metadata_sha256': sha(metadata_path),
                  'input_tokens': call['input_tokens'], 'output_tokens': call['output_tokens'],
                  'call_seconds': call['wall_seconds'],
                  'scope': 'One pre-freeze transport check; excluded from all evaluation scores, token means and timings.',
                  'tokenizer_crosschecks_note': 'Sidecar reports three preflight crosschecks; this audit independently recounts the smoke request with the frozen GGUF tokenizer.'}


def audit_call_inventory(relative_paths, evaluation_keys, smoke_key):
    expected = {key[:2] + '/' + key + '.json.gz' for key in evaluation_keys | {smoke_key}}
    equal(set(relative_paths), expected, 'Evaluation plus exactly one known smoke call inventory')
    require(smoke_key not in evaluation_keys, 'Smoke call was included in the evaluation population')


def official_components(dataset, prediction, references):
    """Invoke the pinned official low-level metric, not our metrics.py wrapper."""
    require(dataset == 'qasper', 'This verifier is limited to QASPER')
    module = official_qa_module('f1')
    return {'f1': float(max(module.f1_score(prediction, reference) for reference in references))}


@lru_cache(maxsize=2)
def official_qa_module(name):
    path = HERE / 'official_sources' / 'scrolls' / 'metrics' / (name + '.py')
    spec = importlib.util.spec_from_file_location('audit_official_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def aggregate_components(dataset, records):
    require(dataset == 'qasper', 'This verifier is limited to QASPER')
    n = len(records)
    values = {'f1': 100.0 * sum(record['components']['f1'] for record in records) / n}
    digits = 4
    return {'dataset': dataset, 'num_predicted': n, 'metric': METRICS[dataset],
            'score': round(values[METRICS[dataset]], digits), 'score_unrounded': values[METRICS[dataset]],
            **{key: round(value, digits) for key, value in values.items()}, 'components_unrounded': values}


def distribution(values):
    items = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not items:
        return {'n': 0, 'sum': 0.0, 'mean': None, 'median': None, 'p95': None, 'min': None, 'max': None}
    return {'n': len(items), 'sum': sum(items), 'mean': sum(items) / len(items),
            'median': float(np.percentile(items, 50)), 'p95': float(np.percentile(items, 95)),
            'min': min(items), 'max': max(items)}


def arm_summary(dataset, records):
    if not records:
        return {'n': 0, 'official': None, 'coverage': None, 'usage': {}}
    done = sum(record['status'] == 'ok' for record in records)
    return {'n': len(records), 'context_clusters': len({record['cluster_id'] for record in records}),
            'official': aggregate_components(dataset, records), 'completed_answers': done,
            'coverage': done / len(records), 'context_overflow': len(records) - done,
            'selector_invalid': sum(record['arm'] in ('A', 'B') and record['selection_valid'] is not True for record in records),
            'output_limit': sum(bool(record['output_limit']) for record in records),
            'resumed_partial_queries': sum(bool(record['resumed_partial_query']) for record in records),
            'missing_completed_query_times': sum(record['status'] == 'ok' and record['query_seconds'] is None for record in records),
            'actual_completed_calls': sum(record['completed_calls'] for record in records),
            'usage': {field: distribution(record[field] for record in records) for field in USAGE},
            'cost_interpretation': 'All-population usage is observed resource consumption, not a fair FULL cost comparison; use identical full_fit population for savings.'}


def interval(values, usable_clusters):
    finite = np.asarray(values)[np.isfinite(values)]
    valid = len(finite) > 0 and usable_clusters >= 2
    return {'ci95': [float(value) for value in np.percentile(finite, [2.5, 97.5])] if valid else None,
            'valid_draws': int(len(finite)) if usable_clusters >= 2 else 0,
            'reason': None if valid else 'fewer_than_two_usable_clusters_or_no_finite_draws'}


def contrast_summary(dataset, left, right, draws=10000, seed=20261027):
    """Independent grouped-loop aggregation and paired multinomial bootstrap."""
    require([r['task_id'] for r in left] == [r['task_id'] for r in right], 'Unpaired contrast')
    if not left:
        return {'n': 0, 'score': None, 'usage': {}, 'context_clusters': 0}
    require(dataset == 'qasper', 'This verifier is limited to QASPER')
    component_keys = ('f1',)
    fields = component_keys + USAGE
    groups = defaultdict(list)
    for i, (a, b) in enumerate(zip(left, right)):
        require(a['cluster_id'] == b['cluster_id'], 'Paired cluster differs')
        groups[a['cluster_id']].append(i)
    cluster_keys = sorted(groups)
    count = len(cluster_keys)
    totals_left = np.zeros((count, len(fields)))
    totals_right = np.zeros_like(totals_left)
    sizes = np.zeros_like(totals_left)
    for group_index, key in enumerate(cluster_keys):
        for field_index, field in enumerate(fields):
            for row_index in groups[key]:
                a = left[row_index]['components'][field] if field in component_keys else left[row_index][field]
                b = right[row_index]['components'][field] if field in component_keys else right[row_index][field]
                if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
                    totals_left[group_index, field_index] += a
                    totals_right[group_index, field_index] += b
                    sizes[group_index, field_index] += 1
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(count, np.full(count, 1 / count), size=draws)
    denominators = sizes.sum(axis=0)
    with np.errstate(divide='ignore', invalid='ignore'):
        point_left = totals_left.sum(axis=0) / denominators
        point_right = totals_right.sum(axis=0) / denominators
        replicate_left = (weights @ totals_left) / (weights @ sizes)
        replicate_right = (weights @ totals_right) / (weights @ sizes)
    def primary(values):
        return 100 * values[..., 0]
    result = {'n': len(left), 'context_clusters': count, 'left_arm': left[0]['arm'], 'right_arm': right[0]['arm'],
              'score': {'metric': METRICS[dataset], 'left': float(primary(point_left)), 'right': float(primary(point_right)),
                        'difference_percentage_points': float(primary(point_left) - primary(point_right)),
                        **interval(primary(replicate_left) - primary(replicate_right), count)},
              'components': {}, 'usage': {}, 'bootstrap_draws': draws, 'seed': seed}
    for index, field in enumerate(component_keys):
        result['components'][field] = {'left_percent': float(100 * point_left[index]), 'right_percent': float(100 * point_right[index]),
                                      'difference_percentage_points': float(100 * (point_left[index] - point_right[index])),
                                      **interval(100 * (replicate_left[:, index] - replicate_right[:, index]), count)}
    for index, field in enumerate(fields[len(component_keys):], start=len(component_keys)):
        usable = int(np.count_nonzero(sizes[:, index]))
        finite = np.isfinite(point_left[index]) and np.isfinite(point_right[index])
        values = {'n_pairs': int(denominators[index]), 'usable_context_clusters': usable,
                  'left_mean': float(point_left[index]) if finite else None,
                  'right_mean': float(point_right[index]) if finite else None,
                  'difference': float(point_left[index] - point_right[index]) if finite else None,
                  **interval(replicate_left[:, index] - replicate_right[:, index], usable)}
        if right[0]['arm'] == 'FULL':
            with np.errstate(divide='ignore', invalid='ignore'):
                savings = np.where(replicate_right[:, index] > 0,
                                   100 * (1 - replicate_left[:, index] / replicate_right[:, index]), np.nan)
            values['savings_vs_FULL_percent'] = {
                'estimate': float(100 * (1 - point_left[index] / point_right[index])) if finite and point_right[index] > 0 else None,
                **interval(savings, usable)}
        result['usage'][field] = values
    return result


def summary_datasets(scored, draws=10000, seed=20261027):
    lookup = {(record['task_id'], record['arm']): record for record in scored}
    result = {}
    for dataset in DATASETS:
        all_ids = sorted({record['task_id'] for record in scored if record['dataset'] == dataset})
        require(len(all_ids) == COUNTS[dataset], f'{dataset}: incomplete analysis population')
        fit_ids = [uid for uid in all_ids if lookup[uid, 'FULL']['status'] == 'ok']
        cohorts = {}
        for cohort_name, ids, contrasts in [('all_questions', all_ids, BASE_CONTRASTS), ('full_fit', fit_ids, FIT_CONTRASTS)]:
            records = {arm: [lookup[uid, arm] for uid in ids] for arm in ARMS}
            cohorts[cohort_name] = {'n_questions': len(ids), 'task_ids': ids,
                                    'arms': {arm: arm_summary(dataset, records[arm]) for arm in ARMS},
                                    'paired_contrasts': {a + '-' + b: contrast_summary(dataset, records[a], records[b], draws, seed)
                                                         for a, b in contrasts}}
        result[dataset] = {'expected_questions': COUNTS[dataset], **cohorts,
                           'excluded_from_full_fit': len(all_ids) - len(fit_ids)}
    return result


def independent_schedule(tasks, seed):
    rng = random.Random(seed)
    groups = {dataset: [task for task in tasks if task['dataset'] == dataset] for dataset in DATASETS}
    for group in groups.values():
        rng.shuffle(group)
    permutations = list(itertools.permutations(ARMS))
    rng.shuffle(permutations)
    result, index = [], 0
    while any(groups.values()):
        for dataset in DATASETS:
            if groups[dataset]:
                task = groups[dataset].pop()
                for arm in permutations[index % 24]:
                    result.append({'task_id': task['task_id'], 'arm': arm})
                index += 1
    return result


def audit_frozen(out):
    protocol = read(out / 'protocol.json')
    config = protocol['config']
    for key, expected in {'arms': list(ARMS), 'datasets': list(DATASETS), 'model_context': 32768,
                          'source_budget': 1024, 'catalog_budget': 2048, 'catalog_candidates': 24,
                          'selector_max_tokens': 32, 'max_expanded_nodes': 8, 'node_max_tokens': 256,
                          'preview_words': 12, 'repeats': 1, 'temperature': 0, 'seed': 1,
                          'order_seed': 20261027, 'prompt_cache': False,
                          'answer_max_tokens': {'qasper': 128}}.items():
        equal(config[key], expected, 'protocol.' + key)
    for name in ('data_manifest', 'tasks', 'schedule', 'analysis_plan', 'prepared_verification', 'source_clusters'):
        path = out / (name + ('.jsonl' if name == 'tasks' else '.json'))
        equal(sha(path), protocol[name + '_sha256'], 'frozen.' + name)
    for path_text, expected_hash in protocol['source_hashes'].items():
        path = Path(path_text)
        equal(sha(path), expected_hash, 'frozen.source.' + str(path))
        equal(sha(out / 'source_snapshot' / path.relative_to(HERE)), expected_hash, 'snapshot.' + str(path))
    equal(sha(MODEL), protocol['model_sha256'], 'frozen.model')
    equal(sha('/opt/homebrew/bin/llama-server'), protocol['server_binary_sha256'], 'frozen.server')
    for line in (HERE / 'requirements.lock').read_text().splitlines():
        if line.strip():
            package, version = line.strip().split('==')
            equal(importlib.metadata.version(package), version, 'installed_dependency.' + package)
    metric_check = read(HERE / 'metrics_verification.json')
    require(metric_check['status'] == 'pass' and metric_check['tests_run'] == 8, 'Official metric equivalence fixtures missing')
    for path, expected_hash in metric_check['source_and_resource_sha256'].items():
        equal(sha(path), expected_hash, 'metric_source_or_resource.' + path)
    import nltk
    require(Path(nltk.data.find('tokenizers/punkt_tab/english')).resolve()
            == Path(metric_check['nltk_english_resource']).resolve(), 'NLTK is using a different sentence resource')
    manifest = read(out / 'data_manifest.json')
    equal(set(manifest['datasets']), {'qasper'}, 'QASPER-only data manifest')
    equal(manifest['document_count'], EXPECTED_CONTEXTS, 'QASPER exact context count')
    for dataset in DATASETS:
        record = manifest['datasets'][dataset]
        raw = out / record['raw_file']
        equal(raw.stat().st_size, record['bytes'], 'raw_data_size.' + dataset)
        equal(sha(raw), record['sha256'], 'raw_data_hash.' + dataset)
    prepared = read(out / 'prepared_verification.json')
    require(prepared['status'] == 'PASS' and prepared['questions'] == sum(COUNTS.values()), 'Prepared-data audit is incomplete')
    equal(prepared['documents'], EXPECTED_CONTEXTS, 'Prepared QASPER exact contexts')
    env = read(out / 'environment.json')
    equal(env['server_props']['default_generation_settings']['n_ctx'], config['model_context'], 'environment.n_ctx')
    require(Path(env['server_props']['model_path']).resolve() == MODEL.resolve(), 'Server used another model path')
    return protocol


def verify(out=OUT):
    out = Path(out)
    started = time.perf_counter()
    # The full gate precedes heavy work. Never certify an active prefix.
    completed = read(out / 'completed.json')
    expected_rows = sum(COUNTS.values()) * len(ARMS)
    require(completed['rows'] == expected_rows, f'Run is not the full {expected_rows:,}-row QASPER experiment')
    equal(sha(out / 'results.jsonl'), completed['results_sha256'], 'completed.results_sha256')
    require((out / 'summary.json').is_file() and (out / 'task_scores.jsonl').is_file(), 'Final analysis not present')
    protocol = audit_frozen(out)
    config = protocol['config']
    task_list = rows(out / 'tasks.jsonl')
    equal(dict(Counter(task['dataset'] for task in task_list)), COUNTS, 'task_counts')
    require(len({task['document_id'] for task in task_list}) == EXPECTED_CONTEXTS, 'Incomplete QASPER source-context population')
    tasks = {task['task_id']: task for task in task_list}
    require(len(tasks) == len(task_list), 'Duplicate task IDs')
    schedule = read(out / 'schedule.json')
    equal(schedule, independent_schedule(task_list, config['order_seed']), 'schedule')
    canonical_files = sorted((out / 'results').glob('*.json.gz'))
    equal([path.name for path in canonical_files], [f'{i:08d}.json.gz' for i in range(expected_rows)], 'canonical row files')
    result_rows = rows(out / 'results.jsonl')
    require(len(result_rows) == expected_rows, 'Missing JSONL rows')
    manifest = read(out / 'data_manifest.json')
    clusters = read(out / 'source_clusters.json')
    mapping = clusters['document_to_cluster']
    equal(set(mapping), set(manifest['document_files']), 'source cluster document set')
    tokenizer = Tokenizer()
    smoke_call, smoke_evidence = audit_smoke(out, tokenizer, config, protocol['frozen_at_utc'])
    document_hashes = {}

    @lru_cache(maxsize=3)
    def document(uid):
        path = out / manifest['document_files'][uid]['path']
        hashed = sha(path)
        equal(hashed, manifest['document_files'][uid]['sha256'], 'prepared.document hash')
        data = read(path)
        equal(digest(data['context']), uid, 'prepared.exact_context')
        equal(digest(data['context'].strip()), mapping[uid], 'prepared.cluster')
        document_hashes[uid] = hashed
        return data

    @lru_cache(maxsize=3)
    def search(uid):
        return RawSearch(document(uid))

    templates = read(out / 'source_snapshot/official_sources/longbench/LongBench/config/dataset2prompt.json')
    used_calls, scored, tokens = set(), [], Counter()
    generation_settings = None
    corpus_counts = Counter()
    for index, row in enumerate(result_rows):
        equal(read(canonical_files[index]), row, f'canonical[{index}]')
        equal({key: row[key] for key in ('task_id', 'arm')}, schedule[index], f'schedule[{index}]')
        task, arm = tasks[row['task_id']], row['arm']
        equal(row['dataset'], task['dataset'], 'row.dataset')
        equal(row['document_id'], task['document_id'], 'row.document_id')
        doc = document(task['document_id'])
        by_id = {node['id']: node for node in doc['nodes']}
        stages = ['select', 'answer'] if arm in ('A', 'B') else ['answer']
        keys = [digest('|'.join((row['task_id'], arm, stage))) for stage in stages]
        equal(row['call_keys'], keys, 'row.call_keys')
        require(not used_calls.intersection(keys), 'Call reused by multiple result rows')
        used_calls.update(keys)
        calls = [read(out / 'calls' / key[:2] / (key + '.json.gz')) for key in keys]
        selected, valid, catalog = None, None, None
        chosen, rejected = [], []
        if arm == 'FULL':
            context = doc['context']
            equal(row['context'], None, 'FULL.context_storage')
        elif arm == 'R0':
            context, chosen, rejected = replay_pack(search(task['document_id']).rank(task['question']), tokenizer, 1024)
        else:
            catalog = replay_catalog(doc, task['question'], tokenizer, config)
            audit_call(calls[0], task['task_id'], arm, 'select', select_prompt(task['question'], catalog['text']),
                       config['selector_max_tokens'], tokenizer, config)
            selected, valid = selection_result(calls[0], catalog)
            expanded = closure(doc['nodes'], selected, 1 if arm == 'A' else 2,
                               same_document=arm == 'A', limit=8) if valid else []
            candidates = [(0, {'id': 'selected:' + uid, 'source_ids': [uid], 'text': fragment(doc, by_id[uid])}) for uid in expanded]
            context, chosen, rejected = replay_pack(candidates, tokenizer, 1024)
        equal(row['selected'], selected, 'row.selected')
        equal(row['selection_valid'], valid, 'row.selection_valid')
        equal(row['catalog'], catalog, 'row.catalog')
        equal(row['chosen'], chosen, 'row.chosen')
        equal(row['rejected'], rejected, 'row.rejected')
        if arm != 'FULL':
            equal(row['context'], context, 'row.context')
            require(tokenizer.tokens(context) <= 1024, 'Retrieved source budget exceeded')
        equal(row['context_sha256'], digest(context), 'row.context_sha256')
        equal(row['context_tokens'], tokenizer.tokens(context), 'row.context_tokens')
        audit_call(calls[-1], task['task_id'], arm, 'answer', final_prompt(task['dataset'], task['question'], context, templates),
                   config['answer_max_tokens'][task['dataset']], tokenizer, config)
        for call in calls:
            if call['status'] == 'ok':
                settings = {key: value for key, value in call['response']['generation_settings'].items()
                            if key not in {'max_tokens', 'n_predict'}}
                if generation_settings is None:
                    generation_settings = settings
                equal(settings, generation_settings, 'stable_generation_settings')
        answer = calls[-1]
        equal(row['status'], answer['status'], 'row.status')
        equal(row['prediction'], answer['answer'], 'row.prediction')
        for field in ('input_tokens', 'output_tokens'):
            equal(row[field], sum(call[field] for call in calls), 'row.' + field)
            tokens[field] += row[field]
        equal(row['peak_input_tokens'], max(call['input_tokens'] for call in calls), 'row.peak_input_tokens')
        equal(row['requested_answer_input_tokens'], answer['requested_input_tokens'], 'row.requested_answer_input_tokens')
        equal(row['calls_seconds'], sum(call['wall_seconds'] for call in calls), 'row.calls_seconds')
        limited = bool(answer.get('response', {}).get('stopped_limit', False) or answer.get('response', {}).get('stop_type') == 'limit')
        equal(row['output_limit'], limited, 'row.output_limit')
        require(math.isfinite(row['pre_answer_seconds']) and row['pre_answer_seconds'] >= 0, 'Invalid pre-answer time')
        if row['resumed_partial_query']:
            equal(row['query_seconds'], None, 'resumed.query_seconds')
        else:
            require(row['query_seconds'] is not None and math.isfinite(row['query_seconds'])
                    and row['query_seconds'] + 1e-6 >= row['calls_seconds']
                    and row['query_seconds'] >= row['pre_answer_seconds'], 'Invalid uninterrupted query time')
        require(datetime.fromisoformat(row['ended_at_utc']) >= datetime.fromisoformat(row['started_at_utc']), 'Reversed row timestamps')
        require((out / ('session_' + row['session_id'] + '.json')).is_file(), 'Missing row session')
        fields = ('task_id', 'dataset', 'arm', 'document_id', 'status', 'prediction', 'input_tokens', 'peak_input_tokens',
                  'output_tokens', 'selection_valid', 'output_limit', 'resumed_partial_query', 'query_seconds', 'requested_answer_input_tokens')
        record = {key: row[key] for key in fields}
        done = [call for call in calls if call['status'] == 'ok']
        record.update(source_id=task['source_id'], reference_count=len(task['references']), cluster_id=mapping[task['document_id']],
                      components=official_components(task['dataset'], row['prediction'], task['references']),
                      prepared_source_tokens=row['context_tokens'], completed_calls=len(done),
                      completed_call_seconds=sum(call['wall_seconds'] for call in done) if done else None,
                      actual_answer_source_tokens=row['context_tokens'] if row['status'] == 'ok' else 0,
                      measured_query_seconds=row['query_seconds'])
        if row['status'] != 'ok':
            record['query_seconds'] = None
        scored.append(record)
        corpus_counts[task['dataset'], arm] += 1
        if (index + 1) % 250 == 0:
            print(f'Audited {index + 1}/{expected_rows} complete result rows', flush=True)
    all_call_paths = sorted((out / 'calls').glob('*/*.json.gz'))
    audit_call_inventory({str(path.relative_to(out / 'calls')) for path in all_call_paths}, used_calls, smoke_call['key'])
    require(len(used_calls) == sum(COUNTS.values()) * 6, 'Wrong complete call-record count')
    equal({key: value for key, value in smoke_call['response']['generation_settings'].items()
           if key not in {'max_tokens', 'n_predict'}}, generation_settings, 'smoke_vs_evaluation_generation_settings')
    require(set(document_hashes) == set(manifest['document_files']), 'Not every prepared context was audited')
    equal(rows(out / 'task_scores.jsonl'), scored, 'task_scores')
    summary = read(out / 'summary.json')
    plan = read(out / 'analysis_plan.json')
    equal(plan['bootstrap']['draws'], 10000, 'analysis.bootstrap.draws')
    equal(plan['bootstrap']['seed'], 20261027, 'analysis.bootstrap.seed')
    expected_datasets = summary_datasets(scored, plan['bootstrap']['draws'], plan['bootstrap']['seed'])
    equal(summary['datasets'], expected_datasets, 'summary.datasets')
    metadata = {'provisional': False, 'generation_repeats': 1,
                'analysis_plan_sha256': sha(out / 'analysis_plan.json'), 'tasks_sha256': sha(out / 'tasks.jsonl'),
                'results_sha256': sha(out / 'results.jsonl'), 'expected_result_rows': expected_rows,
                'observed_result_rows': expected_rows, 'analyzed_result_rows': expected_rows,
                'unfinished_question_rows_excluded': 0, 'numpy_version': np.__version__,
                'source_clusters_sha256': sha(out / 'source_clusters.json'),
                'clustering': {key: value for key, value in clusters.items() if key != 'document_to_cluster'},
                'task_scores_sha256': sha(out / 'task_scores.jsonl')}
    for key, expected in metadata.items():
        equal(summary[key], expected, 'summary.' + key)
    require(set(summary) == set(metadata) | {'datasets', 'created_at_utc'}, 'Unexpected/unverified summary fields')
    require(datetime.fromisoformat(summary['created_at_utc']) >= datetime.fromisoformat(completed['completed_at_utc']), 'Summary predates completion')
    result = {'status': 'PASS', 'completed_at_utc': now(), 'questions': sum(COUNTS.values()),
              'result_rows': expected_rows, 'call_records': len(all_call_paths),
              'evaluation_call_records': len(used_calls), 'smoke_call_records': 1,
              'total_call_records': len(all_call_paths), 'dataset_question_counts': COUNTS,
              'dataset_arm_rows': {dataset: {arm: corpus_counts[dataset, arm] for arm in ARMS} for dataset in DATASETS},
              'protocol_sha256': sha(out / 'protocol.json'), 'results_sha256': sha(out / 'results.jsonl'),
              'summary_sha256': sha(out / 'summary.json'), 'task_scores_sha256': sha(out / 'task_scores.jsonl'),
              'data_manifest_sha256': sha(out / 'data_manifest.json'), 'completed_sha256': sha(out / 'completed.json'),
              'verifier_sha256': sha(Path(__file__)), 'test_verifier_sha256': sha(HERE / 'test_verify_results.py'),
              'document_count': len(document_hashes), 'evaluation_actual_token_totals': dict(tokens),
              'smoke_actual_token_totals': {field: smoke_call[field] for field in ('input_tokens', 'output_tokens')},
              'total_actual_token_totals': {field: tokens[field] + smoke_call[field] for field in ('input_tokens', 'output_tokens')},
              'smoke_evidence': smoke_evidence,
              'stable_generation_settings': generation_settings,
              'seconds': time.perf_counter() - started,
              'checks': ['Frozen sources, source snapshots, model, engine, protocol and prepared-data evidence unchanged',
                         'All 984 QASPER validation questions, 273 exact contexts, four arms and 3936 scheduled rows present',
                         'Every atomic result file equals its JSONL projection; all 5904 evaluation call records are uniquely accounted for',
                         'Exactly one known pre-freeze SMOKE call is separately audited; all other extra calls are rejected',
                         'Independent A/B catalog, selector, graph traversal and whole-item source packing replay',
                         'Independent R0 candidate population, TF-IDF, cosine ordering and greedy packing replay',
                         'Every answer/selector prompt rebuilt from question and selected source only; no gold injected',
                         'FULL context remains byte exact; every overflow has no response and zero actual token cost',
                         'Every requested prompt counted with actual GGUF tokenizer and matched against server input counts',
                         'Model parameters, no prompt-cache reuse, no input truncation and context/output budgets checked',
                         'Every prediction, strict selector result, token sum/peak, call time and output-limit flag reconciled',
                         'Every saved per-task metric recomputed using pinned official metric primitives',
                         'Every summary population, numeric aggregate, paired bootstrap interval and FULL saving independently recomputed'],
              'shared_primitives': ['Frozen common.Tokenizer GGUF bridge', 'Pinned official SCROLLS normalized token-F1 primitive',
                                    'NumPy numerical routines; no runner/analyzer functions imported'],
              'limitations': ['Protocol/source hashes and logs are internal audit evidence, not an external certification.',
                              'This verifier does not prove the scientific adequacy of the experimental design or independence of overlapping source contexts.']}
    dump(out / 'verification.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'questions', 'result_rows', 'call_records', 'seconds')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    verify(parser.parse_args().out)
