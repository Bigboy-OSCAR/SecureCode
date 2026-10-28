"""Small adversarial fixtures for the post-run independent verifier.

These do not read live result/progress files or call the model. Equivalence
fixtures call frozen runner/analyzer *only from this test module*, to check the
separately implemented audit logic on known small inputs.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import analyze_results as analysis_reference
import run_experiment as run_reference
from types import SimpleNamespace

import verify_results as audit


class CharacterTokenizer:
    def tokens(self, text):
        return len(text)


class WordTokenizer:
    def tokens(self, text):
        return len(text.split())


def tiny_document():
    context = 'alpha stock hold\n\nbeta price stock\n\ngamma rare detail'
    starts = [0, context.index('beta'), context.index('gamma')]
    ends = starts[1:] + [len(context)]
    nodes = []
    for i, (start, end) in enumerate(zip(starts, ends)):
        nodes.append({'id': f'n{i+1:06d}', 'doc_id': 'd0001' if i < 2 else 'd0002',
                      'start': start, 'end': end, 'title': 'First Article' if i < 2 else 'Second Article',
                      'heading': 'Stock Rules' if i == 0 else '', 'preview': context[start:end].strip(),
                      'deps': ['n000002', 'n000003'] if i == 0 else []})
    return {'context': context, 'nodes': nodes}


def make_call(prompt='Question and source only.', max_tokens=10, context_limit=1000):
    task_id, arm, stage = 'fixture:one', 'R0', 'answer'
    text = audit.wrapped(prompt)
    n = len(text)
    request = {'prompt': text, 'n_predict': max_tokens, 'temperature': 0, 'seed': 1,
               'cache_prompt': False, 'id_slot': 0, 'stop': ['<|im_end|>', '<|im_start|>'], 'stream': False}
    result = {'key': audit.digest('|'.join((task_id, arm, stage))), 'task_id': task_id, 'arm': arm, 'stage': stage,
              'request': request, 'requested_input_tokens': n, 'input_tokens': 0, 'output_tokens': 0,
              'answer': '', 'status': 'context_overflow', 'wall_seconds': 0.01,
              'started_at_utc': '2026-10-27T00:00:00+00:00', 'ended_at_utc': '2026-10-27T00:00:00.01+00:00'}
    if n + max_tokens <= context_limit:
        result.update(status='ok', input_tokens=n, output_tokens=2, answer='answer', response={
            'prompt': text, 'content': ' answer\n', 'model': audit.MODEL.name,
            'tokens_evaluated': n, 'tokens_predicted': 2, 'truncated': False, 'id_slot': 0, 'stop': True,
            'generation_settings': {'seed': 1, 'temperature': 0.0, 'n_predict': max_tokens,
                                    'max_tokens': max_tokens, 'stream': False,
                                    'stop': ['<|im_end|>', '<|im_start|>']},
            'timings': {'cache_n': 0, 'prompt_n': n, 'predicted_n': 2}})
    return result


def score_records(dataset, arm):
    records = []
    for index in range(7):
        components = ({'rouge1': (index+1)/8, 'rouge2': index/9, 'rougeL': (index+2)/10, 'rougeLsum': (index+2)/10}
                      if dataset == 'qmsum' else {'f1': (index+1)/8})
        if arm == 'FULL':
            components = {key: value * 0.9 for key, value in components.items()}
        records.append({'task_id': f'x{index}', 'arm': arm, 'document_id': f'd{index//2}',
                        'cluster_id': f'c{index//2}', 'components': components,
                        **{key: (index+1) * (10.0 if arm == 'FULL' else 8.0) for key in audit.USAGE}})
    records[0]['query_seconds'] = None
    records[-1]['completed_call_seconds'] = None
    return records


class VerifyResultsTests(unittest.TestCase):
    def test_candidate_population_has_no_duplicate_one_node_atomic(self):
        document = tiny_document()
        search = audit.RawSearch(document)
        self.assertEqual([item['id'] for item in search.candidates],
                         ['bundle:n000001', 'atomic:n000001', 'bundle:n000002', 'bundle:n000003'])
        expected = run_reference.Assets(document).ranked('stock unseen_query')
        actual = search.rank('stock unseen_query')
        self.assertEqual([item['id'] for _, item in actual], [item['id'] for _, item in expected])
        for (score, _), (reference, _) in zip(actual, expected):
            self.assertAlmostEqual(score, reference, places=14)

    def test_zero_overlap_ties_are_retained_in_stable_id_order(self):
        search = audit.RawSearch(tiny_document())
        ranked = search.rank('zzzzzz')
        self.assertTrue(all(score == 0 for score, _ in ranked))
        self.assertEqual([item['id'] for _, item in ranked], sorted(item['id'] for item in search.candidates))

    def test_graph_depth_and_document_restriction(self):
        nodes = tiny_document()['nodes']
        nodes[1]['deps'] = ['n000003']
        self.assertEqual(audit.closure(nodes, 'n000001', 1, True), ['n000001', 'n000002'])
        self.assertEqual(audit.closure(nodes, 'n000001', 2, False), ['n000001', 'n000002', 'n000003'])
        self.assertEqual(audit.closure(nodes, 'n000001', 2, False, 2), ['n000001', 'n000002'])

    def test_pack_skips_whole_oversized_and_covered_but_not_partial_overlap(self):
        candidates = [(1, {'id': 'huge', 'source_ids': ['h'], 'text': 'word '*20}),
                      (0.9, {'id': 'first', 'source_ids': ['a', 'b'], 'text': 'one two three'}),
                      (0.8, {'id': 'covered', 'source_ids': ['b'], 'text': 'four'}),
                      (0.7, {'id': 'overlap', 'source_ids': ['b', 'c'], 'text': 'five six seven'})]
        text, chosen, rejected = audit.replay_pack(candidates, WordTokenizer(), 6)
        self.assertEqual(text, 'one two three\n\nfive six seven')
        self.assertEqual([item['id'] for item in chosen], ['first', 'overlap'])
        self.assertEqual(rejected, ['huge'])

    def test_catalog_preview_scoring_and_whole_row_cap_match_frozen_runner(self):
        doc = tiny_document()
        asset = SimpleNamespace(nodes=doc['nodes'])
        for question in ['Stock Rules and alpha', 'unmatched-query']:
            for budget in [1, 200, 2048]:
                config = {**run_reference.CONFIG, 'catalog_budget': budget}
                old = run_reference.CONFIG['catalog_budget']
                try:
                    run_reference.CONFIG['catalog_budget'] = budget
                    expected = run_reference.catalog(asset, question, CharacterTokenizer())
                finally:
                    run_reference.CONFIG['catalog_budget'] = old
                self.assertEqual(audit.replay_catalog(doc, question, CharacterTokenizer(), config), expected)

    def test_strict_selector_no_unlisted_or_multiple_or_limited_ids(self):
        catalog = {'ids': ['n000001']}
        for text, expected in [('n000001', True), (' n000001\n', True), ('n000002', False),
                               ('n000001 n000002', False), ('```n000001```', False), ('', False)]:
            self.assertEqual(audit.selection_result({'answer': text, 'status': 'ok'}, catalog)[1], expected)
        self.assertFalse(audit.selection_result({'answer': 'n000001', 'status': 'ok', 'response': {'stop_type': 'limit'}}, catalog)[1])

    def test_call_checks_exact_prompt_no_hidden_gold_or_token_cache(self):
        call = make_call()
        kwargs = ('fixture:one', 'R0', 'answer', 'Question and source only.', 10, CharacterTokenizer(), {'model_context': 1000})
        audit.audit_call(call, *kwargs)
        mutations = [lambda c: c['request'].__setitem__('prompt', c['request']['prompt']+'GOLD ANSWER'),
                     lambda c: c['response'].__setitem__('tokens_evaluated', 1),
                     lambda c: c['response']['timings'].__setitem__('cache_n', 1),
                     lambda c: c['response'].__setitem__('truncated', True),
                     lambda c: c.__setitem__('answer', 'repaired answer'),
                     lambda c: c['request'].__setitem__('temperature', 0.7)]
        for mutate in mutations:
            changed = copy.deepcopy(call)
            mutate(changed)
            with self.assertRaises(AssertionError):
                audit.audit_call(changed, *kwargs)

    def test_overflow_is_not_truncation_or_free_successful_inference(self):
        call = make_call(context_limit=10)
        args = ('fixture:one', 'R0', 'answer', 'Question and source only.', 10, CharacterTokenizer(), {'model_context': 10})
        audit.audit_call(call, *args)
        for key, value in [('input_tokens', 3), ('answer', 'hallucinated'), ('status', 'ok'), ('response', {})]:
            changed = copy.deepcopy(call); changed[key] = value
            with self.assertRaises(AssertionError):
                audit.audit_call(changed, *args)

    def test_known_smoke_is_audited_separately_and_sidecar_must_match(self):
        call = make_call(prompt='Return only the numeral 2.', max_tokens=16)
        call.update(task_id='smoke_transport', arm='SMOKE', stage='answer',
                    key=audit.digest('smoke_transport|SMOKE|answer'), answer='2')
        call['response']['content'] = '2'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = call['key']
            audit.dump(root/'calls'/key[:2]/(key+'.json.gz'), call)
            metadata = {'tokenizer_crosschecks': 3, 'status': 'ok', 'input_tokens': call['input_tokens'],
                        'output_tokens': call['output_tokens'], 'response': call['response']}
            audit.dump(root/'smoke_transport.json', metadata)
            checked, evidence = audit.audit_smoke(root, CharacterTokenizer(), {'model_context': 1000}, '2026-10-27T00:00:01+00:00')
            self.assertEqual(checked, call)
            self.assertEqual(evidence['input_tokens'], call['input_tokens'])
            metadata['input_tokens'] += 1
            audit.dump(root/'smoke_transport.json', metadata)
            with self.assertRaises(AssertionError):
                audit.audit_smoke(root, CharacterTokenizer(), {'model_context': 1000}, '2026-10-27T00:00:01+00:00')

    def test_smoke_allowlist_does_not_allow_arbitrary_extra_calls(self):
        evaluation = {'aa' + '0'*62, 'bb' + '1'*62}
        smoke = audit.digest('smoke_transport|SMOKE|answer')
        paths = {key[:2]+'/'+key+'.json.gz' for key in evaluation | {smoke}}
        audit.audit_call_inventory(paths, evaluation, smoke)
        with self.assertRaises(AssertionError):
            audit.audit_call_inventory(paths | {'cc/'+'c'*64+'.json.gz'}, evaluation, smoke)
        with self.assertRaises(AssertionError):
            audit.audit_call_inventory(paths, evaluation | {smoke}, smoke)

    def test_official_primitives_and_corpus_geomean_match_frozen_metric_wrapper(self):
        import metrics
        predictions = ['one two three', '', 'The blue whale.']
        references = [['one three two', 'one two'], ['missing'], ['blue whale']]
        for dataset in audit.DATASETS:
            records = []
            for prediction, refs in zip(predictions, references):
                actual = audit.official_components(dataset, prediction, refs)
                audit.equal(actual, metrics.score_example(dataset, prediction, refs))
                records.append({'components': actual})
            audit.equal(audit.aggregate_components(dataset, records),
                        metrics.aggregate_scores(dataset, [r['components'] for r in records]))

    def test_independent_bootstrap_matches_frozen_analyzer_with_missing_timings(self):
        for dataset in ['qmsum', 'qasper']:
            left, right = score_records(dataset, 'R0'), score_records(dataset, 'FULL')
            actual = audit.contrast_summary(dataset, left, right, draws=513, seed=123)
            expected = analysis_reference.paired_contrast(dataset, left, right, draws=513, seed=123)
            audit.equal(actual, expected)
        self.assertEqual(actual['usage']['query_seconds']['n_pairs'], 6)

    def test_single_cluster_interval_is_unavailable(self):
        left, right = score_records('qasper', 'R0')[:1], score_records('qasper', 'FULL')[:1]
        actual = audit.contrast_summary('qasper', left, right, draws=20)
        self.assertIsNone(actual['score']['ci95'])
        self.assertEqual(actual['score']['valid_draws'], 0)
        audit.equal(actual, analysis_reference.paired_contrast('qasper', left, right, draws=20))

    def test_incomplete_run_cannot_produce_final_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'completed.json').write_text(json.dumps({'rows': 4}))
            with self.assertRaisesRegex(AssertionError, 'full 29,268'):
                audit.verify(path)
            self.assertFalse((path/'verification.json').exists())

    def test_comparison_rejects_missing_keys_wrong_types_and_numeric_changes(self):
        audit.equal({'x': [1, 1.0], 'set': {'a', 'b'}}, {'x': [1, 1.0], 'set': {'b', 'a'}})
        for actual in [{'x': [1, 1.0], 'extra': 1}, {'x': [True, 1.0]}, {'x': [1, 1.1]}]:
            with self.assertRaises(AssertionError):
                audit.equal(actual, {'x': [1, 1.0]})


if __name__ == '__main__':
    unittest.main()
