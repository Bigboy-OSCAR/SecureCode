"""Offline independent reconstruction of the hybrid experiment and its main claims."""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
from datetime import datetime
import itertools
import json
import math
from pathlib import Path
import re
from statistics import mean, median
import sys

sys.dont_write_bytecode = True
import experiment_hybrid as exp
import audit_v2 as offline
import verify_ab as independent


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-8, rel_tol=1e-10), (a, b)


def b_members(asset, question, call):
    match = re.search(r"memory://symbol/[^\s'\"`]+::[A-Za-z_][\w.]*", call['answer']) if call['ok'] else None
    uid = match.group() if match else None
    nodes = asset['nodes']
    valid = uid in nodes and uid in {n['uri'] for n in asset['index']['symbols']}
    if not valid:
        return [], uid, False
    fs = [uid]
    cs = []
    for other, node in nodes.items():
        if (node['kind'] == 'function' and node['path'] == nodes[uid]['path'] and
                node['name'].lower() in question.lower() and other not in fs and len(fs) < 8):
            fs.append(other)
    frontier = [uid]
    for _ in range(2):
        nxt = []
        for u in frontier:
            for dep in nodes[u]['deps']:
                if nodes[dep]['kind'] == 'constant':
                    if dep not in cs:
                        cs.append(dep)
                elif dep not in fs and len(fs) < 8:
                    fs.append(dep)
                    nxt.append(dep)
        frontier = nxt
    return fs + cs, uid, True


def metadata_from_ast(uid, node):
    n = ast.parse(node['source']).body[0]
    signature = node['name']
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [x.arg for x in n.args.posonlyargs + n.args.args]
        if n.args.vararg:
            args.append('*' + n.args.vararg.arg)
        elif n.args.kwonlyargs:
            args.append('*')
        args.extend(x.arg for x in n.args.kwonlyargs)
        if n.args.kwarg:
            args.append('**' + n.args.kwarg.arg)
        signature += '(' + ', '.join(args) + ')'
    return dict(uri=uid, kind=node['kind'], signature=signature, path=node['path'],
                start=node['start'], end=node['end'], deps=node['deps'])


def index_line(number, m):
    deps = ','.join(x.split('memory://symbol/', 1)[1] for x in m['deps']) or '-'
    return f"{number}. {m['kind']} {m['path']}:{m['start']}-{m['end']} {m['signature']} -> {deps}"


def parse_h(call, items):
    if not call['ok']:
        return [], False, 'selector_call_failed'
    text = call['answer'].strip()
    if text.startswith('```') and text.endswith('```'):
        text = text[3:-3]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
        if type(obj) is not dict or set(obj) != {'read'}:
            raise ValueError()
        nums = obj['read']
        if type(nums) is not list or not 1 <= len(nums) <= 8:
            raise ValueError()
        if not all(type(x) is int and 1 <= x <= len(items) for x in nums) or len(set(nums)) != len(nums):
            raise ValueError()
        return [items[x-1]['uri'] for x in nums], True, None
    except (ValueError, TypeError):
        return [], False, 'selector_invalid_or_empty'


def singles(nodes, ids):
    return [(0.0, dict(id=u, level=0, text=offline.fragment(nodes[u]), source_uris=[u])) for u in ids]


def contrast(records, base):
    questions = defaultdict(list)
    for r in records:
        if r['arm'] in ['H',base]:
            questions[(r['task_id'],r['arm'])].append(r)
    values = {key:dict(score=mean(r['correct'] for r in rs), seconds=median(r['query_seconds'] for r in rs),
                       project=rs[0]['project']) for key,rs in questions.items()}
    tids = sorted({key[0] for key in questions})
    projects = sorted({v['project'] for v in values.values()})
    clusters=[]
    for p in projects:
        ids=[t for t in tids if values[(t,'H')]['project']==p]
        clusters.append(dict(delta=mean(values[(t,'H')]['score']-values[(t,base)]['score'] for t in ids),
            h=mean(values[(t,'H')]['seconds'] for t in ids),b=mean(values[(t,base)]['seconds'] for t in ids)))
    draws=[(100*mean(g['delta'] for g in choice),mean(g['h']-g['b'] for g in choice),
            100*(1-sum(g['h'] for g in choice)/sum(g['b'] for g in choice)))
           for choice in itertools.product(clusters,repeat=len(clusters))]
    cis=[[independent.quantile([d[i] for d in draws],p) for p in [.025,.975]] for i in range(3)]
    delta=mean(g['delta'] for g in clusters); ht=mean(g['h'] for g in clusters);bt=mean(g['b'] for g in clusters)
    flips=[abs(mean(sign*g['delta'] for sign,g in zip(signs,clusters)))
           for signs in itertools.product([-1,1],repeat=len(clusters))]
    return dict(delta_pp=100*delta,ci95_pp=cis[0],latency_delta_seconds=ht-bt,latency_ci95_seconds=cis[1],
        latency_ratio=ht/bt,latency_reduction_pct=100*(1-ht/bt),latency_reduction_ci95_pct=cis[2],
        win=sum(values[(t,'H')]['score']>values[(t,base)]['score'] for t in tids),
        loss=sum(values[(t,'H')]['score']<values[(t,base)]['score'] for t in tids),
        tie=sum(values[(t,'H')]['score']==values[(t,base)]['score'] for t in tids),
        unadjusted_project_signflip_p=sum(v>=abs(delta)-1e-12 for v in flips)/len(flips))


def main():
    out = exp.OUT
    checks = []
    def check(name, ok, detail=None):
        assert ok, (name, detail)
        checks.append(dict(name=name, passed=True, detail=detail))
    exp.validate(out)
    check('frozen_sources_projects_tasks_and_historical_results', True)
    plan = exp.read(out/'analysis_plan.json')
    for path, sha in plan['files'].items():
        assert exp.v1.sha(exp.v1.REPO/path) == sha, path
    records = exp.audit.rows(out/'results.jsonl')
    dev = exp.audit.rows(out/'results_dev.jsonl')
    all_rows = records + dev
    tasks = {t['id']: t for t in exp.read(out/'tasks.json') + exp.read(out/'dev_tasks.json')}
    calls = exp.audit.rows(out/'model_calls.jsonl')
    summary = exp.read(out/'summary.json')
    done = exp.read(out/'completed_eval.json')
    check('terminal_completion_and_result_hash', done['rows'] == 864 and done['results_sha256'] == exp.v1.sha(out/'results.jsonl'))
    check('analysis_plan_precedes_evaluation', plan['frozen_at_utc'] < min(r['started_at_utc'] for r in records))
    check('exact_864_evaluation_and_24_development_rows', len(records) == 864 and len(dev) == 24 and
          [{k:r[k] for k in ['task_id','repeat','arm']} for r in records] == exp.read(out/'schedule.json'))
    check('96_questions_three_repeats_six_projects', len({r['task_id'] for r in records}) == 96 and
          len({r['project'] for r in records}) == 6 and all(v == 1 for v in Counter(
              (r['task_id'],r['repeat'],r['arm']) for r in records).values()))
    check('development_project_is_separate', not ({r['project'] for r in records} & {r['project'] for r in dev}))
    orders = defaultdict(Counter)
    for i in range(0, len(records), 3):
        block = records[i:i+3]
        assert len({(r['task_id'],r['repeat']) for r in block}) == 1
        orders[block[0]['repeat']][tuple(r['arm'] for r in block)] += 1
    check('all_six_arm_orders_balanced_each_repeat', all(
        c == Counter({o:16 for o in itertools.permutations(['B','R0','H'])}) for c in orders.values()))
    call_map = {c['call_id']: c for c in calls}
    row_calls = [c for r in all_rows for c in [r['selector'],r['answer_call']] if c]
    warmups = [c for c in calls if c['purpose'] == 'warmup']
    check('all_model_calls_retained_no_shared_inference', len(call_map) == len(calls) == 1482 and
          len(row_calls) == len({c['call_id'] for c in row_calls}) == 1480 and len(warmups) == 2 and
          all(c == call_map[c['call_id']] for c in row_calls))
    check('no_transport_errors_input_truncation_or_prompt_cache', all('error' not in c and not c['truncated'] and
          c['timings']['cache_n'] == 0 and c['request']['cache_prompt'] is False for c in calls))
    check('generation_limits_and_parameters_unchanged', all(c['request']['temperature'] == 0 and c['request']['seed'] == 1 and
          c['input_tokens'] + c['max_output_tokens'] <= 8192 and c['request']['n_predict'] ==
          {'select':96,'answer':128,'warmup':32}[c['purpose']] for c in calls))
    check('same_model_binary_and_server_settings_as_previous_large_run',
          exp.read(out/'environment.json')['fingerprint'] == exp.read(exp.large.DEFAULT_OUT/'environment.json')['fingerprint'])
    check('physical_call_and_query_times', all(datetime.fromisoformat(a['ended_at_utc']) <= datetime.fromisoformat(b['started_at_utc'])
          for a,b in zip(calls,calls[1:])) and all(abs((datetime.fromisoformat(r['ended_at_utc'])-
          datetime.fromisoformat(r['started_at_utc'])).total_seconds()-r['query_seconds']) < .02 for r in all_rows))
    for r in all_rows:
        task = tasks[r['task_id']]
        assert independent.equal(r['expected'],task['expected']) and r['question'] == task['question']
        graded = independent.grade({**r,'selection_valid':True if r['arm']=='R0' else r['selection_valid']},task)
        assert graded[0] == r['correct'] and independent.equal(graded[1],r['parsed_answer']) and graded[2] == r['failure']
    check('independent_typed_answer_grading', True)
    gold = exp.ab.verify_gold(out, exp.read(out/'tasks.json'), exp.read(out/'gold_operations.json'))
    check('all_96_gold_answers_reexecuted', gold['status'] == 'PASS' and gold['questions'] == 96)
    assets = exp.read(out/'assets.json')
    metadata = exp.read(out/'symbol_metadata.json')
    for project, asset in assets.items():
        nodes = offline.source_graph(out/'projects'/project)
        assert nodes == asset['nodes']
        assert offline.raw_from_nodes(nodes) == asset['raw']
        assert {u:metadata_from_ast(u,n) for u,n in nodes.items()} == metadata[project]
    check('independent_AST_graph_raw_bundles_and_body_free_metadata', True)
    rank_cache, ordered, strings, h_indices = {}, {}, set(), {}
    for r in all_rows:
        task = tasks[r['task_id']]; asset = assets[r['project']]
        key = (r['task_id'],r['repeat'],r['arm'])
        if r['arm'] != 'B' and r['task_id'] not in rank_cache:
            rank_cache[r['task_id']] = offline.rank(task['question'], asset['raw'], asset['raw'])
        if r['arm'] == 'B':
            ids, selected, valid = b_members(asset,task['question'],r['selector'])
            assert selected == r['selected_uri'] and valid == r['selection_valid']
            ranked = singles(asset['nodes'],ids)
            outline = exp.v1._candidate_symbol_outline(asset['index'],task['question'],24)
            assert r['selector']['prompt'] == exp.v1._selector_prompt(task['question'],outline)
        elif r['arm'] == 'R0':
            ranked = rank_cache[r['task_id']]
            assert r['selector'] is None
        else:
            scores = {}
            for score,item in rank_cache[r['task_id']]:
                u = item['id'][7:] if item['id'].startswith('atomic:') else item['id']
                scores[u] = max(score,scores.get(u,0))
            ranks = sorted(((s,u) for u,s in scores.items() if s>0), key=lambda x:(-x[0],x[1]))
            assert len(ranks) == len(r['symbol_ranking'])
            for (s,u),logged in zip(ranks,r['symbol_ranking']):
                assert u == logged['uri']; close(s,logged['score'])
            idx = r['source_index']; included = {i['uri'] for i in idx['items']}
            text = ''; numbered = []; attempts = []
            for score,u in ranks[:24]:
                line = index_line(len(numbered)+1,metadata[r['project']][u])
                proposed = text + ('\n' if text else '') + line
                strings.add(proposed); attempts.append((u,proposed,u in included))
                if u in included:
                    text = proposed
                    numbered.append(dict(number=len(numbered)+1,uri=u,score=score,line=line))
            assert text == idx['text']
            assert [i['uri'] for i in numbered] == [i['uri'] for i in idx['items']]
            for a,b in zip(numbered,idx['items']):
                close(a['score'],b['score']); assert all(a[k]==b[k] for k in ['number','uri','line'])
            assert [u for u,_,ok in attempts if not ok] == idx['rejected']
            h_indices[key] = attempts
            requested,valid,reason = parse_h(r['selector'],idx['items'])
            assert requested == r['requested_uris'] and valid == r['selection_valid'] and reason == r['selection_failure']
            assert r['selector']['prompt'] == exp.selector_prompt(task['question'],idx['text'])
            ranked = singles(asset['nodes'],requested)
            required = set(task['required_uris'])
            close(r['index_required_recall'],len(included & required)/len(required))
            assert r['index_has_all_required'] == (required <= included)
            strings.add(text)
        ordered[key] = ranked
        chosen = {c['id'] for c in r['chosen']}; context = ''; covered = set()
        for _,item in ranked:
            if set(item['source_uris']) <= covered:
                continue
            proposed = context + ('\n\n' if context else '') + item['text']
            strings.add(proposed)
            if item['id'] in chosen:
                context = proposed; covered.update(item['source_uris'])
        assert context == r['context']; strings.add(context)
        assert r['answer_call']['prompt'] == offline.answer_prompt(task['question'],context)
        for c in [r['selector'],r['answer_call']]:
            if c:
                assert c['request']['prompt'] == offline.wrap(c['prompt'])
                strings.add(c['request']['prompt'])
        required = set(task['required_uris'])
        close(r['raw_evidence_recall'],len(covered & required)/len(required))
        assert r['all_raw_evidence'] == (required <= covered) and r['unique_source_count'] == len(covered)
        assert r['source_files'] == sorted({asset['nodes'][u]['path'] for u in covered})
        target_path = asset['nodes'][task['target_uri']]['path']
        assert r['cross_file_source_count'] == sum(asset['nodes'][u]['path'] != target_path for u in covered)
        assert r['input_tokens'] == sum(c['input_tokens'] for c in [r['selector'],r['answer_call']] if c)
        assert r['output_tokens'] == sum(c['output_tokens'] or 0 for c in [r['selector'],r['answer_call']] if c)
    check('independent_TFIDF_ranks_root_mapping_explicit_selection_and_exact_payloads', True)
    check('unique_raw_coverage_and_all_call_token_sums', True)
    text_list = sorted(strings); cache_path = out/'offline_token_counts.json'
    if cache_path.exists():
        cached = exp.read(cache_path)
        assert cached['strings_sha256'] == exp.audit.digest(text_list)
        counts, tokenizer = cached['counts'], cached['tokenizer']
    else:
        counts, tokenizer = offline.tokenize_many(text_list,exp.v1.MODEL)
        exp.v1.dump(cache_path,dict(strings_sha256=exp.audit.digest(text_list),counts=counts,tokenizer=tokenizer))
    for r in all_rows:
        key = (r['task_id'],r['repeat'],r['arm'])
        text = ''; covered = set(); included = []; rejected = []
        for score,item in ordered[key]:
            if set(item['source_uris']) <= covered:
                continue
            proposed = text + ('\n\n' if text else '') + item['text']
            if counts[proposed] <= 1024:
                text = proposed; covered.update(item['source_uris'])
                included.append(dict(id=item['id'],level=0,score=score,source_uris=item['source_uris']))
            else:
                rejected.append(item['id'])
        assert text == r['context'] and counts[text] == r['context_tokens'] <= 1024 and rejected == r['rejected']
        assert len(included) == len(r['chosen'])
        for x,y in zip(included,r['chosen']):
            close(x['score'],y['score']); assert all(x[k] == y[k] for k in ['id','level','source_uris'])
        if r['arm'] == 'H':
            for u,text,ok in h_indices[key]:
                assert (counts[text] <= 512) == ok, (key,u)
            assert counts[r['source_index']['text']] == r['source_index']['tokens'] <= 512
        for c in [r['selector'],r['answer_call']]:
            if c:
                assert counts[c['request']['prompt']] == c['input_tokens']
    check('offline_tokenizer_index_cap_raw_cap_and_independent_packing', True,dict(strings=len(strings),tokenizer=tokenizer))
    numeric = 0
    for pop,data in summary['populations'].items():
        group = records if pop=='all96' else [r for r in records if r['split']==pop]
        for arm, values in data.items():
            rs = [r for r in group if r['arm']==arm]; m=values['metrics']; tok=values['tokens']
            qs = defaultdict(list)
            for r in rs: qs[r['task_id']].append(r)
            expected = dict(correct=sum(r['correct'] for r in rs), total=len(rs), accuracy=mean(r['correct'] for r in rs),
                unique_questions=len(qs), question_equivalent_correct=sum(mean(r['correct'] for r in q) for q in qs.values()),
                mean_query_seconds=mean(median(r['query_seconds'] for r in q) for q in qs.values()),
                raw_evidence_recall=mean(r['raw_evidence_recall'] for r in rs), all_raw_evidence=mean(r['all_raw_evidence'] for r in rs))
            for k,v in expected.items(): close(v,m[k]); numeric+=1
            values2=dict(context=mean(r['context_tokens'] for r in rs),index=mean(r['source_index']['tokens'] if r['source_index'] else 0 for r in rs),
                selector=mean(r['selector']['input_tokens'] if r['selector'] else 0 for r in rs),answer=mean(r['answer_call']['input_tokens'] for r in rs),
                total=mean(r['input_tokens'] for r in rs),peak=mean(max(c['input_tokens'] for c in [r['selector'],r['answer_call']] if c) for r in rs),
                output=mean(r['output_tokens'] for r in rs))
            for k,v in values2.items(): close(v,tok[k]); numeric+=1
    for base in ['R0','B']:
        calc=contrast(records,base); logged=summary['comparisons']['H-'+base]
        for k,v in calc.items():
            if isinstance(v,list):
                for a,b in zip(v,logged[k]): close(a,b);numeric+=1
            else: close(v,logged[k]);numeric+=1
        for field,getter in [('context',lambda r:r['context_tokens']),('total',lambda r:r['input_tokens']),
                             ('peak',lambda r:max(c['input_tokens'] for c in [r['selector'],r['answer_call']] if c))]:
            projects=sorted({r['project'] for r in records})
            pairs=[(mean(getter(r) for r in records if r['arm']=='H' and r['project']==p),
                    mean(getter(r) for r in records if r['arm']==base and r['project']==p)) for p in projects]
            values=[100*(1-sum(p[0] for p in draw)/sum(p[1] for p in draw)) for draw in itertools.product(pairs,repeat=6)]
            result=logged['cost'][field]
            close(result['reduction_pct'],100*(1-sum(p[0] for p in pairs)/sum(p[1] for p in pairs)))
            for p,v in zip([.025,.975],result['ci95_pct']): close(independent.quantile(values,p),v);numeric+=1
    pvals=sorted((c['unadjusted_project_signflip_p'],k) for k,c in summary['comparisons'].items()); prev=0
    for rank,(p,k) in enumerate(pvals):
        prev=max(prev,min(1,(2-rank)*p));close(prev,summary['comparisons'][k]['holm_p_two_quality_contrasts']);numeric+=1
    check('independent_accuracy_time_token_savings_cluster_intervals_and_Holm',True,dict(numeric_fields=numeric))
    exp.v1.dump(out/'verification.json',dict(status='PASS',checked_at_utc=exp.audit.now(),checks=checks,
        records=len(records),development_records=len(dev),model_calls=len(calls),numeric_fields=numeric,
        summary_sha256=exp.v1.sha(out/'summary.json'),results_sha256=exp.v1.sha(out/'results.jsonl'),
        verifier_sha256=exp.v1.sha(__file__),limitations=['Local audit, not external validation.',
        'B candidate outline and literal selector prompts are checked against preserved generators; TF-IDF, graph, H metadata, selection, packing, tokenization and primary statistics are independently reconstructed.']))
    print(json.dumps(dict(status='PASS',checks=len(checks),records=len(records),numeric_fields=numeric)))


if __name__ == '__main__':
    main()
