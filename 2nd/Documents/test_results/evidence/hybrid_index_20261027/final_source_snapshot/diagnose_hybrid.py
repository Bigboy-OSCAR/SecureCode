"""Descriptive failure/cost diagnostics, separate from the frozen primary analysis."""
from collections import Counter
import json
from statistics import mean
import sys
sys.dont_write_bytecode=True
import experiment_hybrid as exp


def invalid_reason(call, size):
    if not call['ok']:return 'call_failed_or_output_limit'
    text=call['answer'].strip()
    if text.startswith('```') and text.endswith('```'):
        text=text[3:-3].removeprefix('json').strip()
    try:obj=json.loads(text)
    except (ValueError,TypeError):return 'invalid_json'
    if type(obj) is not dict or set(obj)!={'read'}:return 'invalid_schema'
    nums=obj['read']
    if type(nums) is not list:return 'not_a_list'
    if not nums:return 'empty_selection'
    if len(nums)>8:return 'more_than_eight_items'
    if any(type(n) is not int for n in nums):return 'non_integer_row'
    if any(not 1<=n<=size for n in nums):return 'unlisted_row'
    if len(nums)!=len(set(nums)):return 'duplicate_row'
    return 'valid'


def main():
    out=exp.OUT;exp.validate(out)
    rows=exp.audit.rows(out/'results.jsonl')
    assert len(rows)==864 and exp.read(out/'completed_eval.json')['results_sha256']==exp.v1.sha(out/'results.jsonl')
    bykey={(r['task_id'],r['repeat'],r['arm']):r for r in rows}
    hs=[r for r in rows if r['arm']=='H']
    tasks={t['id']:t for t in exp.read(out/'tasks.json')}
    groups={}
    criteria={'all':lambda r:True,'valid_selection':lambda r:r['selection_valid'],
        'invalid_selection':lambda r:not r['selection_valid'],
        'all_required_raw':lambda r:r['all_raw_evidence'],
        'missing_required_raw':lambda r:not r['all_raw_evidence'],
        'both_H_R0_correct':lambda r:r['correct'] and bykey[(r['task_id'],r['repeat'],'R0')]['correct']}
    for label,predicate in criteria.items():
        subset=[r for r in hs if predicate(r)]
        entry={'query_executions':len(subset),'unique_questions':len({r['task_id'] for r in subset}),'arms':{}}
        for a in ['H','R0','B']:
            rs=[bykey[(r['task_id'],r['repeat'],a)] for r in subset]
            if rs:entry['arms'][a]={
                'accuracy':mean(r['correct'] for r in rs),'mean_total_input':mean(r['input_tokens'] for r in rs),
                'mean_peak_input':mean(max(c['input_tokens'] for c in [r['selector'],r['answer_call']] if c) for r in rs),
                'mean_raw_tokens':mean(r['context_tokens'] for r in rs),'mean_seconds':mean(r['query_seconds'] for r in rs)}
        if subset:entry['H_total_reduction_vs_matched_R0_pct']=100*(1-entry['arms']['H']['mean_total_input']/entry['arms']['R0']['mean_total_input'])
        groups[label]=entry
    reason_counts=Counter();missing_reasons=Counter();required_occurrences=0
    first_invalid=None
    for r in sorted(hs,key=lambda r:(r['task_id'],r['repeat'])):
        reason=invalid_reason(r['selector'],len(r['source_index']['items']))
        assert (reason=='valid')==r['selection_valid']
        reason_counts[reason]+=1
        if reason!='valid' and first_invalid is None:
            first_invalid={k:r[k] for k in ['task_id','repeat','question','source_index','requested_uris','selection_failure','context_tokens','input_tokens']}
            first_invalid.update(selector_answer=r['selector']['answer'],reason=reason)
        ranks={entry['uri']:i for i,entry in enumerate(r['symbol_ranking'])}
        shown={entry['uri'] for entry in r['source_index']['items']}
        for u in tasks[r['task_id']]['required_uris']:
            required_occurrences+=1
            if u in shown:missing_reasons['shown']+=1
            elif u not in ranks:missing_reasons['zero_score']+=1
            elif ranks[u]>=24:missing_reasons['outside_top_24']+=1
            else:missing_reasons['index_512_token_limit']+=1
    result=dict(created_at_utc=exp.audit.now(),analysis_type='post_hoc_descriptive',
        note='Failure inspection and conditional cost summaries. Primary estimates, thresholds and scoring are unchanged. Subgroups are selected by H outcomes and are not independent performance comparisons.',
        results_sha256=exp.v1.sha(out/'results.jsonl'),source_sha256=exp.v1.sha(__file__),groups=groups,
        selection_outcomes=dict(reason_counts),first_invalid=first_invalid,
        required_index_occurrences=required_occurrences,required_index_locations=dict(missing_reasons),
        required_items_per_question=dict(sorted(Counter(len(set(t['required_uris'])) for t in tasks.values()).items())),
        questions_requiring_more_than_eight_items=sum(len(set(t['required_uris']))>8 for t in tasks.values()))
    exp.v1.dump(out/'diagnostics_posthoc.json',result)
    print(json.dumps({'selection_outcomes':result['selection_outcomes'],
        'valid_selection_cost':groups['valid_selection'],'index_locations':result['required_index_locations']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
