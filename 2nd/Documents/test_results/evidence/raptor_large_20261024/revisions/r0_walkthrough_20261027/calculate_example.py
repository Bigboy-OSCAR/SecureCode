"""Reproduce the report's explanatory retrieval arithmetic without model inference."""
from pathlib import Path
from collections import Counter
import json
import math
import sys

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / '2nd/experiments/symbol_raptor/experiment.py').is_file())
sys.path.insert(0, str(ROOT / '2nd/experiments/symbol_raptor'))
import experiment as exp
import audit_v2


def calculate():
    # Only the exact function bodies below are candidate text in this teaching example.
    # Production candidates additionally include source headers and imports.
    candidates = [
        {'id': 'remaining', 'level': 0, 'source_uris': ['example:remaining'],
         'text': 'def remaining(stock, hold):\n    return stock - hold\n'},
        {'id': 'total', 'level': 0, 'source_uris': ['example:total'],
         'text': 'def total(price, quantity):\n    return price * quantity\n'},
    ]
    question = 'How are stock and hold used?'
    retriever = exp.Retriever(candidates)
    df = Counter()
    for item in candidates:
        df.update(set(exp.words(item['text'])))

    def describe(text):
        terms = exp.words(text)
        counts = Counter(terms)
        tf = {word: 1 + math.log(n) for word, n in counts.items()}
        weights = {word: value * retriever.idf.get(word, retriever.unseen_idf)
                   for word, value in tf.items()}
        norm = math.sqrt(sum(value ** 2 for value in weights.values())) or 1
        normalized = {word: value / norm for word, value in weights.items()}
        assert normalized == retriever.vector(text)
        assert math.isclose(sum(v ** 2 for v in normalized.values()), 1)
        return dict(text=text, terms=terms, counts=counts, tf=tf, weights=weights,
                    norm=norm, normalized=normalized)

    descriptions = {item['id']: describe(item['text']) for item in candidates}
    query = describe(question)
    ranked = retriever.ranked(question, candidates)
    ranking = []
    for score, item in ranked:
        products = {word: value * descriptions[item['id']]['normalized'].get(word, 0)
                    for word, value in query['normalized'].items()}
        assert math.isclose(sum(products.values()), score, abs_tol=1e-12)
        ranking.append(dict(id=item['id'], score=score, products=products))

    combined = candidates[0]['text'] + '\n\n' + candidates[1]['text']
    strings = [candidates[0]['text'], candidates[1]['text'], combined]
    counts, tokenizer = audit_v2.tokenize_many(strings, exp.MODEL)

    class OfflineCounter:
        def tokens(self, text):
            return counts[text]

    context, used, chosen, rejected = exp.pack(OfflineCounter(), ranked, 1024)
    assert [item['id'] for item in chosen] == ['remaining', 'total']
    assert not rejected and context == combined
    prompt = exp.answer_prompt(question, context)
    assert question in prompt and context in prompt

    legacy_candidates = [{'id': str(i), 'text': text} for i, text in enumerate(
        ['stock stock hold', 'stock price', 'price'])]
    legacy = exp.Retriever(legacy_candidates)
    legacy_weights = {word: legacy.idf[word] for word in ['stock', 'hold']}
    legacy_norm = math.sqrt(sum(v ** 2 for v in legacy_weights.values()))
    return {
        'scope': 'Two function bodies only; explanatory arithmetic, not benchmark data.',
        'model_inference_calls': 0,
        'implementation_sha256': exp.sha(exp.__file__),
        'N': len(candidates), 'df': df, 'idf': retriever.idf,
        'unseen_idf': retriever.unseen_idf,
        'candidates': descriptions, 'question': query, 'ranking': ranking,
        'packing': {'budget': 1024, 'individual_tokens': {
            item['id']: counts[item['text']] for item in candidates},
            'context_tokens': used, 'chosen': chosen, 'rejected': rejected,
            'context': context, 'answer_prompt': prompt, 'tokenizer': tokenizer},
        'legacy_example': {'candidate_texts': [item['text'] for item in legacy_candidates],
            'idf': legacy.idf, 'question': 'stock hold', 'weights': legacy_weights,
            'norm': legacy_norm, 'normalized': legacy.vector('stock hold'),
            'candidates': {item['text']: legacy.vector(item['text']) for item in legacy_candidates},
            'ranking': [{'id': item['id'], 'score': score}
                        for score, item in legacy.ranked('stock hold', legacy_candidates)]},
    }


if __name__ == '__main__':
    result = calculate()
    dest = Path(__file__).with_name('worked_example.json')
    exp.dump(dest, result)
    print(json.dumps({'output': str(dest), 'ranking': result['ranking'],
                      'individual_tokens': result['packing']['individual_tokens'],
                      'context_tokens': result['packing']['context_tokens'],
                      'model_inference_calls': result['model_inference_calls']}, ensure_ascii=False))
