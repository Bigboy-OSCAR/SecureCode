"""Prespecified, paired document-benchmark analysis. No inference or answer repair.

Run ``plan`` before protocol freeze. Run ``analyze`` only after the complete run;
``analyze --partial`` writes separate, explicitly provisional artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path

import numpy as np

from common import ARMS, DATASETS, OUT, digest, dump, now, read, rows, sha
from metrics import DATASET_METRICS, ROUGE_TYPES, aggregate_scores, score_example

EXPECTED_COUNTS = dict(zip(DATASETS, [272, 984, 3425, 2086, 200, 200, 150]))
BOOTSTRAP_DRAWS = 10000
SEED = 20261027
BASE_CONTRASTS = [('B', 'A'), ('R0', 'A'), ('R0', 'B')]
FIT_CONTRASTS = BASE_CONTRASTS + [(a, 'FULL') for a in ARMS if a != 'FULL']
USAGE_FIELDS = (
    'input_tokens', 'peak_input_tokens', 'output_tokens', 'prepared_source_tokens',
    'actual_answer_source_tokens', 'requested_answer_input_tokens', 'completed_call_seconds', 'query_seconds',
)
PLAN = {
    'version': 'DOCUMENT-ABR0-FULL-ANALYSIS-1.0',
    'arms': ARMS, 'datasets': DATASETS, 'expected_unique_questions': EXPECTED_COUNTS,
    'expected_questions': sum(EXPECTED_COUNTS.values()),
    'expected_result_rows': sum(EXPECTED_COUNTS.values()) * len(ARMS),
    'final_gate': 'Exact task ID membership, four arms once per task, schedule order and completed.json results hash; no absent cases imputed.',
    'primary_population': 'Every unique question; context-overflow empty predictions retained in official task scores.',
    'fit_population': 'The fixed questions whose FULL answer status is ok, with all four arms present. Same membership for all four arms.',
    'partial_population': 'Only complete four-arm question blocks from the verified schedule prefix; never a final result.',
    'metrics': DATASET_METRICS,
    'qmsum_aggregation': 'Geometric mean of corpus mean ROUGE-1/2/L percentages, recomputed in every bootstrap draw; ROUGE-Lsum secondary.',
    'contrasts_all': BASE_CONTRASTS, 'contrasts_full_fit': FIT_CONTRASTS,
    'contrast_direction': 'left minus right, score difference in percentage points; cost savings vs FULL = 100*(FULL-left)/FULL.',
    'bootstrap': {'draws': BOOTSTRAP_DRAWS, 'seed': SEED, 'unit': 'cluster_id = SHA256(context.strip()), supplied by frozen source_clusters.json',
                  'algorithm': 'Sample K context clusters with replacement, preserve every question in each selected cluster, aggregate weighted sums/counts.',
                  'limitation': 'Outer-whitespace variants share a cluster while inference keeps exact original context. Multi-document contexts can still share individual passages across clusters; these are approximate context clusters, not guaranteed independent articles.',
                  'interval': 'Descriptive 2.5th/97.5th percentiles; no p-values, multiplicity correction or confirmatory significance claims.',
                  'generation_repeats': 1, 'less_than_two_clusters': 'No interval reported.'},
    'tokens': 'Actual input sums all completed selector and answer calls; peak is the maximum one-call input. Prepared source tokens include unsent FULL overflow text; actual answer-source tokens are zero if answer was not called.',
    'timing': 'Call seconds sum only status=ok call records. Query latency uses only completed answers with non-null non-resumed query_seconds. Every timing denominator is explicit. Index construction/loading is excluded by runner and reported separately.',
    'overflow_cost_policy': 'Actual zero-call FULL overflow remains visible but is never used as a cheap baseline. Savings and fair four-arm cost comparison use the identical FULL-fit question population.',
    'no_pooling': 'No cross-dataset quality average; no pooling with prior 8192-context experiments. This run uses 32768 context and 1024 source budget.',
}


def plan_document():
    # JSON roundtrip canonicalizes tuples before equality checks after loading.
    return json.loads(json.dumps(PLAN))


def write_plan(out=OUT):
    path = Path(out) / 'analysis_plan.json'
    if path.exists():
        existing = read(path)
        assert {k: v for k, v in existing.items() if k != 'created_at_utc'} == plan_document(), 'Analysis plan changed'
    else:
        assert not (Path(out) / 'results.jsonl').exists(), 'Create analysis plan before evaluation'
        dump(path, {**plan_document(), 'created_at_utc': now()})
    return path


def validate_inputs(tasks, schedule, results, *, partial=False, expected_counts=None):
    """Fail closed for missing, duplicate, reordered, or foreign examples."""
    expected_counts = EXPECTED_COUNTS if expected_counts is None else expected_counts
    assert Counter(t['dataset'] for t in tasks) == Counter(expected_counts), 'Question counts differ from full official sets'
    byid = {t['task_id']: t for t in tasks}
    assert len(byid) == len(tasks), 'Duplicate task IDs'
    assert len({(t['dataset'], t['source_id']) for t in tasks}) == len(tasks), 'Duplicate original question IDs'
    for t in tasks:
        assert t['document_id'] and t['source_id']
        assert isinstance(t['references'], list) and t['references'] and all(isinstance(x, str) for x in t['references'])
    expected_pairs = {(uid, arm) for uid in byid for arm in ARMS}
    pairs = [(r['task_id'], r['arm']) for r in schedule]
    assert len(pairs) == len(expected_pairs) and set(pairs) == expected_pairs, 'Schedule is not the full four-arm product'
    actual = [(r['task_id'], r['arm']) for r in results]
    assert len(actual) <= len(pairs) and actual == pairs[:len(actual)], 'Results must be an exact schedule prefix'
    if not partial:
        assert len(actual) == len(pairs), 'Incomplete results cannot produce a final summary'
    for r in results:
        t = byid[r['task_id']]
        assert r['dataset'] == t['dataset'] and r['document_id'] == t['document_id'], 'Result provenance differs from task'
        assert r['status'] in {'ok', 'context_overflow'}, 'Unresolved/failed request cannot be a committed result'
        assert isinstance(r['prediction'], str)
        if r['status'] == 'context_overflow':
            assert r['prediction'] == '', 'Overflow predictions must be empty'
        for key in ['input_tokens', 'output_tokens', 'peak_input_tokens', 'context_tokens']:
            assert isinstance(r[key], int) and r[key] >= 0, ('Invalid token count', key)
        assert r['peak_input_tokens'] <= r['input_tokens']
        assert r['query_seconds'] is None or (math.isfinite(r['query_seconds']) and r['query_seconds'] >= 0)
        assert not r['resumed_partial_query'] or r['query_seconds'] is None, 'Resumed query latency is not an uninterrupted measurement'
    complete_ids = {uid for uid, count in Counter(r['task_id'] for r in results).items() if count == len(ARMS)}
    return byid, complete_ids


def call_evidence(row, out=OUT):
    """Read completed-call costs; never treat an overflow bookkeeping time as inference."""
    stages = ['select', 'answer'] if row['arm'] in {'A', 'B'} else ['answer']
    assert row['call_keys'] == [digest(row['task_id']+'|'+row['arm']+'|'+s) for s in stages]
    calls = []
    for stage, key in zip(stages, row['call_keys']):
        c = read(Path(out) / 'calls' / key[:2] / (key+'.json.gz'))
        assert (c['key'], c['task_id'], c['arm'], c['stage']) == (key, row['task_id'], row['arm'], stage)
        assert c['status'] in {'ok', 'context_overflow'}
        if c['status'] == 'context_overflow':
            assert c['input_tokens'] == c['output_tokens'] == 0
        calls.append(c)
    assert calls[-1]['status'] == row['status'] and calls[-1]['answer'] == row['prediction']
    assert sum(c['input_tokens'] for c in calls) == row['input_tokens']
    assert sum(c['output_tokens'] for c in calls) == row['output_tokens']
    assert max(c['input_tokens'] for c in calls) == row['peak_input_tokens']
    completed = [c for c in calls if c['status'] == 'ok']
    return {
        'completed_calls': len(completed),
        'completed_call_seconds': sum(c['wall_seconds'] for c in completed) if completed else None,
        'actual_answer_source_tokens': row['context_tokens'] if row['status'] == 'ok' else 0,
    }


def cluster_mapping(document, tasks):
    mapping = document['document_to_cluster']
    assert {t['document_id'] for t in tasks} <= set(mapping), 'Source cluster map does not cover all task contexts'
    assert document['exact_contexts'] == len(mapping)
    assert document['clusters'] == len(set(mapping.values()))
    for key, value in mapping.items():
        assert isinstance(key, str) and isinstance(value, str)
        assert len(key) == len(value) == 64 and all(c in '0123456789abcdef' for c in key+value)
    return mapping


def score_rows(tasks_by_id, result_rows, clusters, out=OUT):
    scored = []
    for row in result_rows:
        t = tasks_by_id[row['task_id']]
        record = {k: row[k] for k in [
            'task_id', 'dataset', 'arm', 'document_id', 'status', 'prediction',
            'input_tokens', 'peak_input_tokens', 'output_tokens', 'selection_valid',
            'output_limit', 'resumed_partial_query', 'query_seconds', 'requested_answer_input_tokens',
        ]}
        record.update(source_id=t['source_id'], reference_count=len(t['references']),
                      cluster_id=clusters[t['document_id']],
                      components=score_example(t['dataset'], row['prediction'], t['references']),
                      prepared_source_tokens=row['context_tokens'],
                      **call_evidence(row, out))
        # Raw non-inference overflow bookkeeping latency is never reported as completed-answer latency.
        record['measured_query_seconds'] = row['query_seconds']
        if row['status'] != 'ok':
            record['query_seconds'] = None
        scored.append(record)
    return scored


def describe(values):
    finite = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not finite:
        return {'n': 0, 'sum': 0.0, 'mean': None, 'median': None, 'p95': None, 'min': None, 'max': None}
    a = np.asarray(finite, dtype=float)
    return {'n': len(a), 'sum': float(a.sum()), 'mean': float(a.mean()),
            'median': float(np.median(a)), 'p95': float(np.percentile(a, 95)),
            'min': float(a.min()), 'max': float(a.max())}


def summarize_arm(dataset, records):
    if not records:
        return {'n': 0, 'official': None, 'coverage': None, 'usage': {}}
    n = len(records)
    return {
        'n': n, 'context_clusters': len({r['cluster_id'] for r in records}),
        'official': aggregate_scores(dataset, [r['components'] for r in records]),
        'completed_answers': sum(r['status'] == 'ok' for r in records),
        'coverage': sum(r['status'] == 'ok' for r in records) / n,
        'context_overflow': sum(r['status'] == 'context_overflow' for r in records),
        'selector_invalid': sum(r['arm'] in {'A', 'B'} and r['selection_valid'] is not True for r in records),
        'output_limit': sum(bool(r['output_limit']) for r in records),
        'resumed_partial_queries': sum(bool(r['resumed_partial_query']) for r in records),
        'missing_completed_query_times': sum(r['status'] == 'ok' and r['query_seconds'] is None for r in records),
        'actual_completed_calls': sum(r['completed_calls'] for r in records),
        'usage': {field: describe(r[field] for r in records) for field in USAGE_FIELDS},
        'cost_interpretation': 'All-population usage is observed resource consumption, not a fair FULL cost comparison; use identical full_fit population for savings.',
    }


def _interval(values, cluster_count):
    finite = np.asarray(values)[np.isfinite(values)]
    return {
        'ci95': [float(x) for x in np.percentile(finite, [2.5, 97.5])] if len(finite) and cluster_count >= 2 else None,
        'valid_draws': int(len(finite)) if cluster_count >= 2 else 0,
        'reason': None if len(finite) and cluster_count >= 2 else 'fewer_than_two_usable_clusters_or_no_finite_draws',
    }


def paired_contrast(dataset, left, right, *, draws=BOOTSTRAP_DRAWS, seed=SEED):
    """One context-cluster resampling matrix for scores and all paired cost measures.

    Each draw resamples K clusters, not K questions or independent arm samples.
    Different cluster sizes remain intact. Missing times use explicitly counted
    complete timing pairs; no null time is replaced by zero.
    """
    assert len(left) == len(right)
    if not left:
        return {'n': 0, 'score': None, 'usage': {}, 'context_clusters': 0}
    assert [r['task_id'] for r in left] == [r['task_id'] for r in right]
    assert [r['document_id'] for r in left] == [r['document_id'] for r in right]
    assert [r['cluster_id'] for r in left] == [r['cluster_id'] for r in right]
    component_keys = list(ROUGE_TYPES) if dataset == 'qmsum' else [DATASET_METRICS[dataset]]
    names = component_keys + list(USAGE_FIELDS)
    def matrix(records):
        return np.asarray([[*[r['components'][k] for k in component_keys],
                            *[np.nan if r[k] is None else r[k] for k in USAGE_FIELDS]] for r in records], dtype=float)
    lv, rv = matrix(left), matrix(right)
    valid = np.isfinite(lv) & np.isfinite(rv)
    clusters, inverse = np.unique([r['cluster_id'] for r in left], return_inverse=True)
    k, m = len(clusters), len(names)
    counts, lsums, rsums = (np.zeros((k, m)) for _ in range(3))
    np.add.at(counts, inverse, valid.astype(float))
    np.add.at(lsums, inverse, np.where(valid, lv, 0))
    np.add.at(rsums, inverse, np.where(valid, rv, 0))
    denominator = counts.sum(axis=0)
    with np.errstate(divide='ignore', invalid='ignore'):
        lmean, rmean = lsums.sum(axis=0)/denominator, rsums.sum(axis=0)/denominator
    lb, rb = np.empty((draws, m)), np.empty((draws, m))
    rng = np.random.default_rng(seed)
    for start in range(0, draws, 256):
        stop = min(draws, start+256)
        weights = rng.multinomial(k, np.full(k, 1/k), size=stop-start)
        denom = weights @ counts
        with np.errstate(divide='ignore', invalid='ignore'):
            lb[start:stop] = (weights @ lsums)/denom
            rb[start:stop] = (weights @ rsums)/denom
    def primary(a):
        return 100*np.cbrt(a[..., 0]*a[..., 1]*a[..., 2]) if dataset == 'qmsum' else 100*a[..., 0]
    score = {'metric': DATASET_METRICS[dataset], 'left': float(primary(lmean)), 'right': float(primary(rmean)),
             'difference_percentage_points': float(primary(lmean)-primary(rmean)),
             **_interval(primary(lb)-primary(rb), k)}
    components = {}
    for j, name in enumerate(component_keys):
        components[name] = {'left_percent': float(100*lmean[j]), 'right_percent': float(100*rmean[j]),
                            'difference_percentage_points': float(100*(lmean[j]-rmean[j])),
                            **_interval(100*(lb[:, j]-rb[:, j]), k)}
    usage = {}
    for j in range(len(component_keys), m):
        usable_clusters = int(np.count_nonzero(counts[:, j]))
        finite_point = np.isfinite(lmean[j]) and np.isfinite(rmean[j])
        result = {'n_pairs': int(denominator[j]), 'usable_context_clusters': usable_clusters,
                  'left_mean': float(lmean[j]) if finite_point else None,
                  'right_mean': float(rmean[j]) if finite_point else None,
                  'difference': float(lmean[j]-rmean[j]) if finite_point else None,
                  **_interval(lb[:, j]-rb[:, j], usable_clusters)}
        if right[0]['arm'] == 'FULL':
            with np.errstate(divide='ignore', invalid='ignore'):
                savings = np.where(rb[:, j] > 0, 100*(1-lb[:, j]/rb[:, j]), np.nan)
            result['savings_vs_FULL_percent'] = {
                'estimate': float(100*(1-lmean[j]/rmean[j])) if finite_point and rmean[j] > 0 else None,
                **_interval(savings, usable_clusters),
            }
        usage[names[j]] = result
    return {'n': len(left), 'context_clusters': k, 'left_arm': left[0]['arm'], 'right_arm': right[0]['arm'],
            'score': score, 'components': components, 'usage': usage, 'bootstrap_draws': draws, 'seed': seed}


def summarize(scored, *, provisional=False, draws=BOOTSTRAP_DRAWS):
    result = {'provisional': provisional, 'generation_repeats': 1, 'datasets': {}}
    bypair = {(r['task_id'], r['arm']): r for r in scored}
    for dataset in DATASETS:
        ids = sorted({r['task_id'] for r in scored if r['dataset'] == dataset})
        assert all((uid, arm) in bypair for uid in ids for arm in ARMS), 'Analysis cohorts require four arms per question'
        fitids = [uid for uid in ids if bypair[uid, 'FULL']['status'] == 'ok']
        def cohort(uids, contrasts):
            records = {arm: [bypair[uid, arm] for uid in uids] for arm in ARMS}
            return {
                'n_questions': len(uids), 'task_ids': uids,
                'arms': {a: summarize_arm(dataset, records[a]) for a in ARMS},
                'paired_contrasts': {f'{a}-{b}': paired_contrast(dataset, records[a], records[b], draws=draws)
                                     for a, b in contrasts},
            }
        result['datasets'][dataset] = {
            'expected_questions': EXPECTED_COUNTS[dataset],
            'all_questions': cohort(ids, BASE_CONTRASTS),
            'full_fit': cohort(fitids, FIT_CONTRASTS),
            'excluded_from_full_fit': len(ids)-len(fitids),
        }
    return result


def write_jsonl(path, records):
    path = Path(path); temp = path.with_suffix(path.suffix+'.part')
    with temp.open('w', encoding='utf8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n')
        f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def analyze(out=OUT, *, partial=False):
    out = Path(out)
    plan_path = out/'analysis_plan.json'
    assert plan_path.exists(), 'Analysis plan must be saved before inference'
    assert {k: v for k, v in read(plan_path).items() if k != 'created_at_utc'} == plan_document()
    protocol = read(out/'protocol.json')
    assert protocol['config']['model_context'] == 32768 and protocol['config']['source_budget'] == 1024
    assert protocol['config']['arms'] == ARMS
    for name, ext in [('tasks', '.jsonl'), ('schedule', '.json'), ('data_manifest', '.json')]:
        assert sha(out/(name+ext)) == protocol[name+'_sha256'], ('Frozen input changed', name)
    assert sha(plan_path) == protocol['analysis_plan_sha256']
    assert sha(out/'source_clusters.json') == protocol['source_clusters_sha256']
    tasks, schedule, results = rows(out/'tasks.jsonl'), read(out/'schedule.json'), rows(out/'results.jsonl')
    cluster_document = read(out/'source_clusters.json')
    clusters = cluster_mapping(cluster_document, tasks)
    byid, complete_ids = validate_inputs(tasks, schedule, results, partial=partial)
    if not partial:
        completed = read(out/'completed.json')
        assert completed['rows'] == len(schedule) and completed['results_sha256'] == sha(out/'results.jsonl')
    chosen_rows = [r for r in results if r['task_id'] in complete_ids]
    scored = score_rows(byid, chosen_rows, clusters, out)
    summary = summarize(scored, provisional=partial)
    summary.update(created_at_utc=now(), analysis_plan_sha256=sha(plan_path),
                   tasks_sha256=sha(out/'tasks.jsonl'), results_sha256=sha(out/'results.jsonl'),
                   expected_result_rows=len(schedule), observed_result_rows=len(results),
                   analyzed_result_rows=len(scored), unfinished_question_rows_excluded=len(results)-len(scored),
                   numpy_version=np.__version__, source_clusters_sha256=sha(out/'source_clusters.json'),
                   clustering={k: v for k, v in cluster_document.items() if k != 'document_to_cluster'})
    suffix = '.provisional' if partial else ''
    score_path, summary_path = out/('task_scores'+suffix+'.jsonl'), out/('summary'+suffix+'.json')
    write_jsonl(score_path, scored)
    summary['task_scores_sha256'] = sha(score_path)
    dump(summary_path, summary)
    return summary_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['plan', 'analyze'])
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    print(write_plan() if args.phase == 'plan' else analyze(partial=args.partial))
