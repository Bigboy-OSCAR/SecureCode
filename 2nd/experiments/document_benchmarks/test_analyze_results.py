import copy
import math
from pathlib import Path
import tempfile
import unittest

import analyze_results as a
from common import digest, dump
from metrics import aggregate_scores


def record(uid, arm, dataset='hotpotqa', cluster=None, value=1, **changes):
    components = ({k: value for k in a.ROUGE_TYPES} if dataset == 'qmsum'
                  else {'exact_match' if dataset == 'quality' else 'f1': value})
    r = {
        'task_id': uid, 'source_id': uid, 'dataset': dataset, 'arm': arm,
        'document_id': cluster or uid, 'cluster_id': cluster or uid, 'status': 'ok', 'prediction': 'answer',
        'components': components, 'input_tokens': 100, 'peak_input_tokens': 100,
        'output_tokens': 5, 'prepared_source_tokens': 50, 'actual_answer_source_tokens': 50,
        'context_tokens': 50, 'requested_answer_input_tokens': 100, 'completed_calls': 2 if arm in {'A', 'B'} else 1,
        'completed_call_seconds': 1.0, 'query_seconds': 1.2,
        'selection_valid': True if arm in {'A', 'B'} else None,
        'output_limit': False, 'resumed_partial_query': False,
    }
    r.update(changes)
    return r


class TestAnalysis(unittest.TestCase):
    def fixture_inputs(self):
        tasks = [{'task_id': 'q'+str(i), 'source_id': 'original'+str(i), 'dataset': d,
                  'document_id': 'doc'+str(i), 'references': ['answer']} for i, d in enumerate(a.DATASETS)]
        schedule = [{'task_id': t['task_id'], 'arm': arm} for t in tasks for arm in a.ARMS]
        results = [record(t['task_id'], arm, t['dataset'], cluster=t['document_id'])
                   for t in tasks for arm in a.ARMS]
        return tasks, schedule, results

    def test_final_gate_requires_exact_full_membership_order_and_four_arms(self):
        tasks, schedule, results = self.fixture_inputs()
        counts = {d: 1 for d in a.DATASETS}
        byid, complete = a.validate_inputs(tasks, schedule, results, expected_counts=counts)
        self.assertEqual(len(complete), 7)
        with self.assertRaises(AssertionError):
            a.validate_inputs(tasks, schedule, results)  # Real 7,317-question gate.
        for changed in [results[:-1], results+[results[-1]], [results[1], results[0]]+results[2:]]:
            with self.assertRaises(AssertionError):
                a.validate_inputs(tasks, schedule, changed, expected_counts=counts)
        badplan = copy.deepcopy(schedule); badplan[-1]['arm'] = 'A'
        with self.assertRaises(AssertionError):
            a.validate_inputs(tasks, badplan, results, expected_counts=counts)
        badrows = copy.deepcopy(results); badrows[0]['document_id'] = 'foreign'
        with self.assertRaises(AssertionError):
            a.validate_inputs(tasks, schedule, badrows, expected_counts=counts)

    def test_partial_uses_only_complete_four_arm_questions(self):
        tasks, schedule, results = self.fixture_inputs()
        _, ids = a.validate_inputs(tasks, schedule, results[:5], partial=True,
                                  expected_counts={d: 1 for d in a.DATASETS})
        self.assertEqual(ids, {'q0'})

    def test_qmsum_recomputes_geometric_mean_after_corpus_aggregation(self):
        left = [record('q1', 'B', 'qmsum'), record('q2', 'B', 'qmsum')]
        left[0]['components'] = dict(zip(a.ROUGE_TYPES, [1, 0, 1, .7]))
        left[1]['components'] = dict(zip(a.ROUGE_TYPES, [0, 1, 1, .9]))
        right = [record('q1', 'A', 'qmsum', value=0), record('q2', 'A', 'qmsum', value=0)]
        result = a.paired_contrast('qmsum', left, right, draws=1000)
        expected = aggregate_scores('qmsum', [r['components'] for r in left])['score_unrounded']
        self.assertAlmostEqual(result['score']['left'], expected)
        self.assertAlmostEqual(result['score']['difference_percentage_points'], 100*(.25**(1/3)))
        self.assertGreater(result['score']['left'], 60)  # Mean individual geometric scores would be zero.
        self.assertEqual(result['components']['rougeLsum']['left_percent'], 80)
        self.assertAlmostEqual(result['score']['ci95'][0], 0)
        self.assertAlmostEqual(result['score']['ci95'][1], expected)

    def test_cluster_bootstrap_preserves_unequal_cluster_sizes(self):
        left = [record(str(i), 'B', cluster='large' if i < 3 else 'small', value=float(i < 3)) for i in range(4)]
        right = [record(str(i), 'A', cluster='large' if i < 3 else 'small', value=0) for i in range(4)]
        result = a.paired_contrast('hotpotqa', left, right, draws=1000)
        self.assertEqual(result['context_clusters'], 2)
        self.assertEqual(result['score']['difference_percentage_points'], 75)
        self.assertEqual(result['score']['ci95'], [0, 100])
        self.assertEqual(result, a.paired_contrast('hotpotqa', left, right, draws=1000))

    def test_null_time_is_excluded_as_a_pair_and_never_zero_filled(self):
        left = [record('q1', 'R0', query_seconds=None, resumed_partial_query=True),
                record('q2', 'R0', query_seconds=2)]
        right = [record('q1', 'FULL', query_seconds=8), record('q2', 'FULL', query_seconds=10)]
        result = a.paired_contrast('hotpotqa', left, right, draws=100)
        timing = result['usage']['query_seconds']
        self.assertEqual(timing['n_pairs'], 1)
        self.assertEqual(timing['left_mean'], 2)
        self.assertEqual(timing['right_mean'], 10)
        self.assertIsNone(timing['ci95'])
        self.assertEqual(timing['savings_vs_FULL_percent']['estimate'], 80)
        self.assertEqual(result['usage']['input_tokens']['n_pairs'], 2)

    def test_full_fit_has_identical_questions_and_excludes_zero_call_overflow_cost(self):
        records = []
        for dataset in a.DATASETS:
            for i in range(2):
                uid = dataset+str(i)
                for arm in a.ARMS:
                    r = record(uid, arm, dataset, input_tokens=100 if arm == 'FULL' else 10,
                               peak_input_tokens=100 if arm == 'FULL' else 10)
                    if arm == 'FULL' and i == 0:
                        r.update(status='context_overflow', prediction='', input_tokens=0, peak_input_tokens=0,
                                 output_tokens=0, completed_calls=0, completed_call_seconds=None,
                                 query_seconds=None, actual_answer_source_tokens=0,
                                 components={k: 0 for k in r['components']})
                    records.append(r)
        result = a.summarize(records, draws=100)
        for dataset in a.DATASETS:
            d = result['datasets'][dataset]
            self.assertEqual(d['all_questions']['n_questions'], 2)
            self.assertEqual(d['all_questions']['arms']['FULL']['coverage'], .5)
            self.assertEqual(d['full_fit']['task_ids'], [dataset+'1'])
            self.assertTrue(all(r['n'] == 1 for r in d['full_fit']['arms'].values()))
            self.assertEqual(d['full_fit']['paired_contrasts']['R0-FULL']['usage']['input_tokens']['savings_vs_FULL_percent']['estimate'], 90)
            self.assertNotIn('R0-FULL', d['all_questions']['paired_contrasts'])

    def test_completed_call_evidence_excludes_overflow_bookkeeping_and_checks_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); uid = 'q'; arm = 'FULL'; key = digest(uid+'|'+arm+'|answer')
            row = record(uid, arm, status='context_overflow', prediction='', input_tokens=0,
                         peak_input_tokens=0, output_tokens=0, call_keys=[key])
            call = {'key': key, 'task_id': uid, 'arm': arm, 'stage': 'answer',
                    'status': 'context_overflow', 'answer': '', 'input_tokens': 0,
                    'output_tokens': 0, 'wall_seconds': 99}
            dump(out/'calls'/key[:2]/(key+'.json.gz'), call)
            evidence = a.call_evidence(row, out)
            self.assertEqual(evidence['completed_calls'], 0)
            self.assertIsNone(evidence['completed_call_seconds'])
            self.assertEqual(evidence['actual_answer_source_tokens'], 0)
            row['input_tokens'] = 1
            with self.assertRaises(AssertionError):
                a.call_evidence(row, out)

    def test_actual_selector_and_answer_costs_are_summed(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); row = record('q', 'A', input_tokens=120, peak_input_tokens=100, output_tokens=7)
            row['call_keys'] = []
            for stage, ntokens, output, wall in [('select', 20, 2, 1.0), ('answer', 100, 5, 2.0)]:
                key = digest('q|A|'+stage); row['call_keys'].append(key)
                dump(out/'calls'/key[:2]/(key+'.json.gz'), {
                    'key': key, 'task_id': 'q', 'arm': 'A', 'stage': stage, 'status': 'ok',
                    'answer': 'n000001' if stage == 'select' else 'answer',
                    'input_tokens': ntokens, 'output_tokens': output, 'wall_seconds': wall})
            result = a.call_evidence(row, out)
            self.assertEqual(result['completed_calls'], 2)
            self.assertEqual(result['completed_call_seconds'], 3)

    def test_plan_is_immutable_and_cannot_be_created_after_results(self):
        with tempfile.TemporaryDirectory() as temp:
            p = a.write_plan(temp)
            self.assertEqual(a.write_plan(temp), p)
            text = p.read_text().replace('10000', '9999')
            p.write_text(text)
            with self.assertRaises(AssertionError): a.write_plan(temp)
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'results.jsonl').touch()
            with self.assertRaises(AssertionError): a.write_plan(temp)

    def test_single_source_cluster_does_not_claim_an_interval(self):
        left = [record('q1', 'R0', cluster='only')]
        right = [record('q1', 'A', cluster='only', value=0)]
        result = a.paired_contrast('hotpotqa', left, right, draws=100)
        self.assertEqual(result['score']['difference_percentage_points'], 100)
        self.assertIsNone(result['score']['ci95'])
        self.assertEqual(result['score']['valid_draws'], 0)

    def test_outer_whitespace_variant_contexts_share_a_frozen_cluster(self):
        contexts = ['  Same source text\n', 'Same source text']
        mapping = {digest(s): digest(s.strip()) for s in contexts}
        document = {'document_to_cluster': mapping, 'exact_contexts': 2, 'clusters': 1}
        tasks = [{'document_id': digest(s)} for s in contexts]
        self.assertEqual(a.cluster_mapping(document, tasks), mapping)
        left = [record(str(i), 'B', document_id=digest(s), cluster_id=mapping[digest(s)]) for i, s in enumerate(contexts)]
        right = [record(str(i), 'A', document_id=digest(s), cluster_id=mapping[digest(s)], value=0) for i, s in enumerate(contexts)]
        result = a.paired_contrast('hotpotqa', left, right, draws=100)
        self.assertEqual(result['context_clusters'], 1)
        self.assertIsNone(result['score']['ci95'])
        with self.assertRaises(AssertionError):
            a.cluster_mapping(document, tasks+[{'document_id': digest('missing')}])


if __name__ == '__main__':
    unittest.main()
